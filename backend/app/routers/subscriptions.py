from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.subscription import Subscription
from app.models.user import User
from app.routers.auth import get_current_user
from app.services import sync

router = APIRouter()


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant_name: str
    display_name: str | None
    amount: float
    frequency: str
    category: str | None
    last_charge_date: date | None
    next_charge_date: date | None
    confidence: float
    status: str
    cancel_url: str | None
    monthly_cost: float  # read from the Subscription.monthly_cost property


def _get_owned(db: Session, user: User, subscription_id: int) -> Subscription:
    sub = (
        db.query(Subscription)
        .filter(Subscription.id == subscription_id, Subscription.user_id == user.id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


def _set_status(db: Session, user: User, subscription_id: int, status: str) -> Subscription:
    sub = _get_owned(db, user, subscription_id)
    sub.status = status
    db.commit()
    db.refresh(sub)
    return sub


@router.get("", response_model=list[SubscriptionOut])
def list_subscriptions(
    status: Literal["active", "dismissed", "ended", "all"] = "active",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sync.expire_lapsed(db, current_user.id)  # charges may have stopped since the last sync
    query = db.query(Subscription).filter(Subscription.user_id == current_user.id)
    if status != "all":
        query = query.filter(Subscription.status == status)
    return sorted(query.all(), key=lambda s: s.monthly_cost, reverse=True)


@router.patch("/{subscription_id}/dismiss", response_model=SubscriptionOut)
def dismiss(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _set_status(db, current_user, subscription_id, "dismissed")


@router.patch("/{subscription_id}/restore", response_model=SubscriptionOut)
def restore(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _set_status(db, current_user, subscription_id, "active")
