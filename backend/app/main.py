from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.routers import auth, insights, plaid, subscriptions

# The schema is managed by Alembic (`alembic upgrade head`); see backend/alembic.

app = FastAPI(title="Digital Life Auditor API", version="1.0.0")

_origins = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # Credentials are only allowed with an explicit origin list, never with "*".
    allow_credentials=_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(plaid.router, prefix="/plaid", tags=["plaid"])
app.include_router(subscriptions.router, prefix="/subscriptions", tags=["subscriptions"])
app.include_router(insights.router, prefix="/insights", tags=["insights"])


@app.get("/health")
def health(db: Session = Depends(get_db)):
    """Liveness plus a database round-trip."""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
