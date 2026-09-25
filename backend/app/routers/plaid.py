import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.connection import PlaidItem
from app.models.user import User
from app.routers.auth import get_current_user
from app.services import plaid_service, sync
from app.services.plaid_service import PlaidError

logger = logging.getLogger(__name__)
router = APIRouter()


class ExchangeRequest(BaseModel):
    public_token: str
    institution_name: str | None = None


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
    items = db.query(PlaidItem).filter(PlaidItem.user_id == current_user.id).all()
    if not items:
        raise HTTPException(status_code=404, detail="No connected accounts")
    added = 0
    subscriptions = 0
    try:
        for item in items:
            stats = sync.sync_item(db, item)
            added += stats.added
            subscriptions = stats.subscriptions
    except PlaidError as exc:
        raise _plaid_failure(exc)
    return {
        "status": "synced",
        "accounts": len(items),
        "transactions_added": added,
        "subscriptions_found": subscriptions,
    }


@router.get("/items")
def list_items(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = db.query(PlaidItem).filter(PlaidItem.user_id == current_user.id).order_by(PlaidItem.id).all()
    return [
        {"id": i.id, "institution_name": i.institution_name, "connected_at": i.created_at.isoformat()}
        for i in items
    ]


@router.delete("/items/{item_id}", status_code=204)
def disconnect_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(PlaidItem).filter(PlaidItem.id == item_id, PlaidItem.user_id == current_user.id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Connection not found")
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
