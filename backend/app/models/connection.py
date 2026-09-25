from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
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
    # ok | login_required (the user must re-authenticate with their bank) | error
    status: Mapped[str] = mapped_column(String, default="ok", server_default="ok", nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    user = relationship("User", back_populates="plaid_items")
