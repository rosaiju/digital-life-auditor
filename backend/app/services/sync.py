"""Sync a connected bank account and refresh detected subscriptions."""
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.connection import PlaidItem
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.services import plaid_service, subscription_detector
from app.services.money import lapse_grace_days
from app.services.plaid_service import PlaidError
from app.utils import utcnow

logger = logging.getLogger(__name__)

# Plaid errors that mean the user has to act (re-authenticate) rather than us retrying.
LOGIN_REQUIRED_CODES = {"ITEM_LOGIN_REQUIRED"}


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


def is_lapsed(next_charge_date: date | None, frequency: str, today: date) -> bool:
    """True when the expected next charge is long overdue, i.e. the user likely cancelled."""
    if next_charge_date is None:
        return False
    return today > next_charge_date + timedelta(days=lapse_grace_days(frequency))


def expire_lapsed(db: Session, user_id: int, today: date | None = None) -> int:
    """Mark active subscriptions whose charges stopped as "ended". Returns how many changed."""
    today = today or date.today()
    changed = 0
    for sub in db.query(Subscription).filter(Subscription.user_id == user_id, Subscription.status == "active"):
        if is_lapsed(sub.next_charge_date, sub.frequency, today):
            sub.status = "ended"
            changed += 1
    if changed:
        db.commit()
    return changed


def refresh_subscriptions(db: Session, user_id: int, today: date | None = None) -> int:
    """Re-run detection over all of a user's transactions and upsert the results.

    Returns the number of subscriptions currently in effect (detected and not ended).
    Status rules: "dismissed" is the user's choice and always sticks; otherwise a
    subscription is "ended" once its charges stop and "active" again if they resume.
    """
    today = today or date.today()
    transactions = db.query(Transaction).filter(Transaction.user_id == user_id).all()
    detected = subscription_detector.detect(transactions)

    existing = {
        s.merchant_name: s for s in db.query(Subscription).filter(Subscription.user_id == user_id).all()
    }
    seen: set[str] = set()
    current = 0
    for sub in detected:
        seen.add(sub.merchant_name)
        status = "ended" if is_lapsed(sub.next_charge_date, sub.frequency, today) else "active"
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
                status=status,
            ))
            current += status == "active"
            continue
        row.amount = sub.amount
        row.frequency = sub.frequency
        row.last_charge_date = sub.last_charge_date
        row.next_charge_date = sub.next_charge_date
        row.confidence = sub.confidence
        row.category = row.category or sub.category
        row.cancel_url = row.cancel_url or sub.cancel_url
        if row.status != "dismissed":
            row.status = status
            current += status == "active"

    # Evidence disappeared (e.g. the bank removed the charges): don't keep it active.
    for name, row in existing.items():
        if name not in seen and row.status == "active":
            row.status = "ended"

    db.commit()
    return current


def _record_failure(db: Session, item: PlaidItem, exc: PlaidError) -> None:
    db.rollback()
    item.status = "login_required" if exc.code in LOGIN_REQUIRED_CODES else "error"
    item.last_error = exc.message[:500]
    db.commit()


def _sync_once(db: Session, item: PlaidItem) -> SyncStats:
    result = plaid_service.sync_transactions(item.access_token, item.cursor)
    stats = apply_changes(db, item.user_id, result["added"], result["modified"], result["removed"])
    item.cursor = result["cursor"]
    item.status = "ok"
    item.last_error = None
    item.last_synced_at = utcnow()
    db.commit()
    return stats


def sync_item(db: Session, item: PlaidItem) -> SyncStats:
    """Fetch new transactions for one bank connection and refresh subscriptions.

    The cursor is only advanced after the transactions are stored, so a failure
    part-way through is retried from the same point on the next sync. A Plaid failure
    is recorded on the item (so the app can ask the user to reconnect) and re-raised.
    Two syncs of the same item can overlap (manual + daily + webhook); the loser hits
    the unique transaction id constraint, so it starts over and sees the winner's rows.
    """
    try:
        try:
            stats = _sync_once(db, item)
        except IntegrityError:
            db.rollback()
            db.refresh(item)
            logger.info("Concurrent sync of item %s; retrying", item.id)
            stats = _sync_once(db, item)
    except PlaidError as exc:
        _record_failure(db, item, exc)
        raise
    stats.subscriptions = refresh_subscriptions(db, item.user_id)
    return stats
