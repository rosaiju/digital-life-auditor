from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.insight import Insight
from app.models.subscription import Subscription
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.ai_insights import generate_insights

router = APIRouter()


@router.get("")
def get_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    insight = (
        db.query(Insight)
        .filter(Insight.user_id == current_user.id)
        .order_by(Insight.generated_at.desc())
        .first()
    )
    if not insight:
        return {"message": "No insights yet. POST /insights/generate to create them."}
    return insight.content


@router.post("/generate")
def generate(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    subscriptions = (
        db.query(Subscription)
        .filter(
            Subscription.user_id == current_user.id,
            Subscription.status == "active",
        )
        .all()
    )

    content = generate_insights(subscriptions)

    insight = Insight(user_id=current_user.id, content=content)
    db.add(insight)
    db.commit()
    db.refresh(insight)
    return insight.content
