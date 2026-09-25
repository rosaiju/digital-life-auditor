from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import EncryptedString
from app.utils import utcnow


class PlaidItem(Base):
    __tablename__ = "plaid_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    access_token: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    item_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    institution_name: Mapped[str | None] = mapped_column(String, nullable=True)
    cursor: Mapped[str | None] = mapped_column(String, nullable=True)  # Plaid sync cursor
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user = relationship("User", back_populates="plaid_items")
