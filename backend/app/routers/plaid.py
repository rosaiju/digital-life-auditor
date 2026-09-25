import hmac
import json
import logging
from contextlib import contextmanager

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.models.connection import PlaidItem
from app.models.user import User
from app.routers.auth import get_current_user
from app.services import plaid_service, plaid_webhooks, sync
from app.services.plaid_service import PlaidError

logger = logging.getLogger(__name__)
router = APIRouter()


class ExchangeRequest(BaseModel):
    public_token: str = Field(min_length=1, max_length=512)
    institution_name: str | None = Field(default=None, max_length=200)


def _plaid_failure(exc: PlaidError) -> HTTPException:
    return HTTPException(status_code=502, detail=f"Bank provider error: {exc.message}")


# ---------- Routes ----------

@router.post("/link-token")
def create_link_token(current_user: User = Depends(get_current_user)):
    try:
        return {"link_token": plaid_service.create_link_token(current_user.id)}
    except PlaidError as exc:
        raise _plaid_failure(exc)


@router.post("/exchange")
def exchange_token(
    body: ExchangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = plaid_service.exchange_public_token(body.public_token)
    except PlaidError as exc:
        raise _plaid_failure(exc)

    item = db.query(PlaidItem).filter(PlaidItem.item_id == data["item_id"]).first()
    if item and item.user_id != current_user.id:
        raise HTTPException(status_code=409, detail="This bank connection belongs to another account")
    if item is None:
        item = PlaidItem(
            user_id=current_user.id,
            access_token=data["access_token"],
            item_id=data["item_id"],
            institution_name=body.institution_name,
        )
        db.add(item)
        db.commit()
        db.refresh(item)

    try:
        stats = sync.sync_item(db, item)
    except PlaidError as exc:
        # The connection is saved; the daily sync or a manual sync will retry.
        logger.warning("Initial sync failed for item %s: %s", item.id, exc.message)
        return {"status": "connected", "institution": item.institution_name, "synced": False}
    return {
        "status": "connected",
        "institution": item.institution_name,
        "synced": True,
        "transactions_added": stats.added,
        "subscriptions_found": stats.subscriptions,
    }


@router.post("/sync")
def sync_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sync every connected bank. One bank failing doesn't stop the others."""
    items = db.query(PlaidItem).filter(PlaidItem.user_id == current_user.id).order_by(PlaidItem.id).all()
    if not items:
        raise HTTPException(status_code=404, detail="No connected accounts")
    added = 0
    subscriptions = 0
    failed = []
    first_error: PlaidError | None = None
    for item in items:
        try:
            stats = sync.sync_item(db, item)
        except PlaidError as exc:
            first_error = first_error or exc
            failed.append({
                "id": item.id,
                "institution_name": item.institution_name,
                "status": item.status,
                "error": exc.message,
            })
            continue
        added += stats.added
        subscriptions = stats.subscriptions
    if len(failed) == len(items):
        raise _plaid_failure(first_error)
    return {
        "status": "partial" if failed else "synced",
        "accounts": len(items),
        "transactions_added": added,
        "subscriptions_found": subscriptions,
        "failed": failed,
    }


@router.get("/items")
def list_items(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = db.query(PlaidItem).filter(PlaidItem.user_id == current_user.id).order_by(PlaidItem.id).all()
    return [
        {
            "id": i.id,
            "institution_name": i.institution_name,
            "connected_at": i.created_at.isoformat(),
            "status": i.status,
            "last_synced_at": i.last_synced_at.isoformat() if i.last_synced_at else None,
            "last_error": i.last_error,
        }
        for i in items
    ]


def _owned_item(db: Session, user: User, item_id: int) -> PlaidItem:
    item = db.query(PlaidItem).filter(PlaidItem.id == item_id, PlaidItem.user_id == user.id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    return item


@router.post("/items/{item_id}/link-token")
def create_reconnect_link_token(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Link token in update mode: lets the user re-authenticate a connection that broke."""
    item = _owned_item(db, current_user, item_id)
    try:
        return {"link_token": plaid_service.create_link_token(current_user.id, access_token=item.access_token)}
    except PlaidError as exc:
        raise _plaid_failure(exc)


@router.post("/items/{item_id}/reconnected")
def item_reconnected(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Called after update-mode Link succeeds: clear the error state and sync right away."""
    item = _owned_item(db, current_user, item_id)
    try:
        stats = sync.sync_item(db, item)
    except PlaidError as exc:
        raise _plaid_failure(exc)
    return {"status": "synced", "transactions_added": stats.added, "subscriptions_found": stats.subscriptions}


@router.delete("/items/{item_id}", status_code=204)
def disconnect_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = _owned_item(db, current_user, item_id)
    try:
        plaid_service.remove_item(item.access_token)
    except PlaidError as exc:
        # Still remove it locally so the user isn't stuck with a dead connection.
        logger.warning("Plaid item removal failed for item %s: %s", item.id, exc.message)
    db.delete(item)
    db.commit()


@router.post("/sync-all")
def sync_all(
    x_airflow_secret: str = Header(default=""),
    db: Session = Depends(get_db),
):
    """Internal endpoint called by the Airflow DAG. Protected by a shared secret."""
    if not hmac.compare_digest(x_airflow_secret, settings.airflow_sync_secret):
        raise HTTPException(status_code=403, detail="Forbidden")

    items = db.query(PlaidItem).all()
    synced = 0
    failed: list[int] = []
    for item in items:
        try:
            sync.sync_item(db, item)
            synced += 1
        except Exception:  # one bad connection must not stop the whole batch
            db.rollback()
            logger.exception("Sync failed for plaid item %s", item.id)
            failed.append(item.id)
    return {"status": "ok" if not failed else "partial", "items_synced": synced, "items_failed": failed}


# ---------- Webhooks ----------

# ITEM webhook codes after which the user has to re-authenticate with their bank.
_REAUTH_CODES = {"PENDING_EXPIRATION", "USER_PERMISSION_REVOKED"}
_REAUTH_ERRORS = {"ITEM_LOGIN_REQUIRED"}
_SYNC_CODES = {"SYNC_UPDATES_AVAILABLE", "DEFAULT_UPDATE", "INITIAL_UPDATE", "HISTORICAL_UPDATE"}


@contextmanager
def session_scope():
    """A session for work that outlives the request (background tasks)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sync_in_background(plaid_item_id: str) -> None:
    with session_scope() as db:
        item = db.query(PlaidItem).filter(PlaidItem.item_id == plaid_item_id).first()
        if item is None:
            return
        try:
            sync.sync_item(db, item)
        except Exception:
            db.rollback()
            logger.exception("Webhook-triggered sync failed for item %s", item.id)


def _flag_reauth(plaid_item_id: str, message: str) -> None:
    with session_scope() as db:
        item = db.query(PlaidItem).filter(PlaidItem.item_id == plaid_item_id).first()
        if item is not None:
            item.status = "login_required"
            item.last_error = message
            db.commit()


@router.post("/webhook")
async def plaid_webhook(
    request: Request,
    background: BackgroundTasks,
    plaid_verification: str | None = Header(default=None),
):
    """Receives Plaid webhooks. Every request must carry a valid Plaid signature.

    Heavy work runs after the response because Plaid expects an answer within seconds.
    """
    body = await request.body()
    try:
        await run_in_threadpool(plaid_webhooks.verify, body, plaid_verification)
    except plaid_webhooks.WebhookVerificationError as exc:
        logger.warning("Rejected webhook: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    except PlaidError as exc:
        logger.error("Could not fetch Plaid webhook verification key: %s", exc.message)
        raise HTTPException(status_code=503, detail="Could not verify webhook")

    try:
        payload = json.loads(body)
        webhook_type = payload.get("webhook_type")
        code = payload.get("webhook_code")
        plaid_item_id = payload.get("item_id")
        error_code = (payload.get("error") or {}).get("error_code")
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Malformed webhook body")
    if not plaid_item_id:
        return {"status": "ignored"}

    if webhook_type == "TRANSACTIONS" and code in _SYNC_CODES:
        background.add_task(_sync_in_background, plaid_item_id)
    elif webhook_type == "ITEM" and (code in _REAUTH_CODES or (code == "ERROR" and error_code in _REAUTH_ERRORS)):
        message = "Bank access expires soon" if code == "PENDING_EXPIRATION" else "Your bank needs you to sign in again"
        background.add_task(_flag_reauth, plaid_item_id, message)
    else:
        return {"status": "ignored"}
    return {"status": "accepted"}
