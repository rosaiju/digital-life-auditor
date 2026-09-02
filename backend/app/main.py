from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine
from app.models import User, PlaidItem, Transaction, Subscription, Insight  # noqa: F401
from app.database import Base
from app.routers import auth, plaid, subscriptions, insights

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Digital Life Auditor API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(plaid.router, prefix="/plaid", tags=["plaid"])
app.include_router(subscriptions.router, prefix="/subscriptions", tags=["subscriptions"])
app.include_router(insights.router, prefix="/insights", tags=["insights"])


@app.get("/health")
def health():
    return {"status": "ok"}
