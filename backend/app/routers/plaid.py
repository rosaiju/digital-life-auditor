from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.connection import PlaidItem
from app.models.transaction import Transaction
from app.models.subscription import Subscription
from app.models.user import User
from app.routers.auth import get_current_user
from app.services import plaid_service, subscription_detector

router = APIRouter()


class ExchangeRequest(BaseModel):
    public_token: str
    institution_name: str | None = None


# ---------- Routes ----------

@router.post("/link-token")
def create_link_token(current_user: User = Depends(get_current_user)):
    token = plaid_service.create_link_token(current_user.id)
    return {"link_token": token}


@router.post("/exchange")
def exchange_token(
    body: ExchangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = plaid_service.exchange_public_token(body.public_token)

    # Upsert Plaid item
    item = db.query(PlaidItem).filter(PlaidItem.item_id == data["item_id"]).first()
    if not item:
        item = PlaidItem(
            user_id=current_user.id,
            access_token=data["access_token"],
            item_id=data["item_id"],
            institution_name=body.institution_name,
        )
        db.add(item)
        db.commit()
        db.refresh(item)

    # Immediately sync + detect
    _sync_and_detect(item, current_user.id, db)
    return {"status": "connected", "institution": item.institution_name}


@router.post("/sync")
def sync(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = db.query(PlaidItem).filter(PlaidItem.user_id == current_user.id).all()
    if not items:
        raise HTTPException(status_code=404, detail="No connected accounts")
    for item in items:
        _sync_and_detect(item, current_user.id, db)
    return {"status": "synced", "accounts": len(items)}


@router.post("/sync-all")
def sync_all(
    x_airflow_secret: str = Header(None),
    db: Session = Depends(get_db),
):
    """Internal endpoint called by Airflow DAG. Protected by shared secret."""
    if x_airflow_secret != settings.airflow_sync_secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    items = db.query(PlaidItem).all()
    for item in items:
        try:
            _sync_and_detect(item, item.user_id, db)
        except Exception:
            pass  # Don't fail entire batch for one user
    return {"status": "ok", "items_synced": len(items)}


# ---------- Internal ----------

def _sync_and_detect(item: PlaidItem, user_id: int, db: Session):
    sync_result = plaid_service.sync_transactions(item.access_token, item.cursor)

    for txn in sync_result["transactions"]:
        exists = db.query(Transaction).filter(
            Transaction.plaid_transaction_id == txn["transaction_id"]
        ).first()
        if exists:
            continue

        merchant = txn.get("merchant_name") or txn.get("name", "")
        db_txn = Transaction(
            user_id=user_id,
            plaid_transaction_id=txn["transaction_id"],
            merchant_name=merchant,
            amount=txn["amount"],
            date=txn["date"],
            category=txn.get("personal_finance_category", {}).get("primary"),
            raw_json=txn,
        )
        db.add(db_txn)

    # Update cursor
    item.cursor = sync_result["cursor"]
    db.commit()

    # Re-run detection on all user transactions
    all_txns = db.query(Transaction).filter(Transaction.user_id == user_id).all()
    detected = subscription_detector.detect(all_txns)

    for sub in detected:
        existing = db.query(Subscription).filter(
            Subscription.user_id == user_id,
            Subscription.merchant_name == sub.merchant_name,
        ).first()

        if existing:
            if existing.status == "dismissed":
                continue
            existing.amount = sub.amount
            existing.frequency = sub.frequency
            existing.last_charge_date = sub.last_charge_date
            existing.next_charge_date = sub.next_charge_date
            existing.confidence = sub.confidence
            if sub.category and not existing.category:
                existing.category = sub.category
        else:
            db.add(Subscription(
                user_id=user_id,
                merchant_name=sub.merchant_name,
                display_name=sub.display_name,
                amount=sub.amount,
                frequency=sub.frequency,
                category=sub.category,
                last_charge_date=sub.last_charge_date,
                next_charge_date=sub.next_charge_date,
                confidence=sub.confidence,
                cancel_url=sub.cancel_url,
            ))

    db.commit()
