"""Sync a connected bank account and refresh detected subscriptions."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.models.connection import PlaidItem
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.services import plaid_service, subscription_detector


@dataclass
class SyncStats:
    added: int = 0
    modified: int = 0
    removed: int = 0
    subscriptions: int = 0


def _apply_fields(db_txn: Transaction, txn: dict) -> None:
    category = (txn.get("personal_finance_category") or {}).get("primary")
    db_txn.merchant_name = txn.get("merchant_name") or txn.get("name") or ""
    db_txn.amount = txn["amount"]
    db_txn.date = date.fromisoformat(txn["date"])
    db_txn.category = category
    db_txn.raw_json = txn


def apply_changes(db: Session, user_id: int, added: list[dict], modified: list[dict], removed: list[str]) -> SyncStats:
    """Upsert added/modified transactions and delete removed ones."""
    stats = SyncStats()
    incoming = {t["transaction_id"]: t for t in [*added, *modified]}
    existing = {}
    if incoming:
        rows = db.query(Transaction).filter(Transaction.plaid_transaction_id.in_(list(incoming))).all()
        existing = {row.plaid_transaction_id: row for row in rows}

    for txn_id, txn in incoming.items():
        row = existing.get(txn_id)
        if row is None:
            row = Transaction(user_id=user_id, plaid_transaction_id=txn_id)
            db.add(row)
            stats.added += 1
        elif row.user_id != user_id:
            continue  # never touch another user's rows
        else:
            stats.modified += 1
        _apply_fields(row, txn)

    if removed:
        stats.removed = (
            db.query(Transaction)
            .filter(Transaction.user_id == user_id, Transaction.plaid_transaction_id.in_(removed))
            .delete(synchronize_session=False)
        )
    return stats


def refresh_subscriptions(db: Session, user_id: int) -> int:
    """Re-run detection over all of a user's transactions and upsert the results."""
    transactions = db.query(Transaction).filter(Transaction.user_id == user_id).all()
    detected = subscription_detector.detect(transactions)

    existing = {
        s.merchant_name: s for s in db.query(Subscription).filter(Subscription.user_id == user_id).all()
    }
    for sub in detected:
        row = existing.get(sub.merchant_name)
        if row is None:
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
            continue
        if row.status == "dismissed":
            continue  # the user hid it; keep it hidden
        row.amount = sub.amount
        row.frequency = sub.frequency
        row.last_charge_date = sub.last_charge_date
        row.next_charge_date = sub.next_charge_date
        row.confidence = sub.confidence
        row.category = row.category or sub.category
        row.cancel_url = row.cancel_url or sub.cancel_url
    db.commit()
    return len(detected)


def sync_item(db: Session, item: PlaidItem) -> SyncStats:
    """Fetch new transactions for one bank connection and refresh subscriptions.

    The cursor is only advanced after the transactions are stored, so a failure
    part-way through is retried from the same point on the next sync.
    """
    result = plaid_service.sync_transactions(item.access_token, item.cursor)
    stats = apply_changes(db, item.user_id, result["added"], result["modified"], result["removed"])
    item.cursor = result["cursor"]
    db.commit()
    stats.subscriptions = refresh_subscriptions(db, item.user_id)
    return stats
