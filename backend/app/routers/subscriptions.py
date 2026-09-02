from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.subscription import Subscription
from app.models.user import User
from app.routers.auth import get_current_user

router = APIRouter()


class SubscriptionOut(BaseModel):
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
    monthly_cost: float

    class Config:
        from_attributes = True


def _monthly_cost(amount: float, frequency: str) -> float:
    multipliers = {
        "weekly": 4.33,
        "biweekly": 2.17,
        "monthly": 1.0,
        "quarterly": 1 / 3,
        "annual": 1 / 12,
    }
    return round(amount * multipliers.get(frequency, 1.0), 2)


@router.get("", response_model=list[SubscriptionOut])
def list_subscriptions(
    status: Literal["active", "dismissed", "all"] = "active",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Subscription).filter(Subscription.user_id == current_user.id)
    if status != "all":
        query = query.filter(Subscription.status == status)
    subs = query.order_by(Subscription.amount.desc()).all()

    result = []
    for s in subs:
        out = SubscriptionOut(
            id=s.id,
            merchant_name=s.merchant_name,
            display_name=s.display_name,
            amount=s.amount,
            frequency=s.frequency,
            category=s.category,
            last_charge_date=s.last_charge_date,
            next_charge_date=s.next_charge_date,
            confidence=s.confidence,
            status=s.status,
            cancel_url=s.cancel_url,
            monthly_cost=_monthly_cost(s.amount, s.frequency),
        )
        result.append(out)
    return result


@router.patch("/{subscription_id}/dismiss", response_model=SubscriptionOut)
def dismiss(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sub = db.query(Subscription).filter(
        Subscription.id == subscription_id,
        Subscription.user_id == current_user.id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    sub.status = "dismissed"
    db.commit()
    db.refresh(sub)
    return SubscriptionOut(
        **{c.name: getattr(sub, c.name) for c in sub.__table__.columns},
        monthly_cost=_monthly_cost(sub.amount, sub.frequency),
    )


@router.patch("/{subscription_id}/restore", response_model=SubscriptionOut)
def restore(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sub = db.query(Subscription).filter(
        Subscription.id == subscription_id,
        Subscription.user_id == current_user.id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    sub.status = "active"
    db.commit()
    db.refresh(sub)
    return SubscriptionOut(
        **{c.name: getattr(sub, c.name) for c in sub.__table__.columns},
        monthly_cost=_monthly_cost(sub.amount, sub.frequency),
    )
