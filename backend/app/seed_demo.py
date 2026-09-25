"""Load realistic demo data so the app can be shown without connecting a bank.

    python -m app.seed_demo                     # creates demo@example.com
    python -m app.seed_demo --reset             # wipe and recreate the demo data
    docker compose exec backend python -m app.seed_demo

Creates a demo user with ~14 months of synthetic transactions (recurring
subscriptions, one of them cancelled, mixed with everyday spending and a refund), then runs the same
detection pipeline a real bank sync would. Nothing here touches Plaid.
"""
import argparse
import random
from datetime import date, timedelta

from app.config import settings
from app.database import SessionLocal
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import hash_password
from app.services import sync

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-password"

# (merchant as it appears on a statement, amount, every N days, days since last charge, price change)
RECURRING = [
    ("NETFLIX.COM", 15.49, 30, 9, None),
    ("Spotify USA", 10.99, 30, 3, None),
    ("HULU *8842", 17.99, 30, 14, None),
    ("Disney Plus", 13.99, 30, 20, (10.99, 4)),       # was $10.99 until 4 charges ago
    ("APPLE.COM/BILL iCloud", 2.99, 30, 6, None),
    ("OPENAI *CHATGPT SUBSCR", 20.00, 30, 11, None),
    ("PLANET FITNESS", 24.99, 30, 17, None),
    ("Adobe Creative Cloud", 599.88, 365, 40, None),
    ("NYTimes Digital", 4.25, 7, 2, None),
    ("Amazon Prime Video", 8.99, 30, 24, None),
    ("Peloton Membership", 44.00, 30, 75, None),       # cancelled ~2 months ago: shows up as "ended"
]

# One-off merchants; amounts vary so they must not be detected as subscriptions.
EVERYDAY = [("Starbucks", 4, 9), ("Uber", 8, 35), ("Whole Foods", 25, 120), ("Shell Gas", 20, 55), ("Amazon.com", 9, 90)]


def build_transactions(today: date, rng: random.Random) -> list[dict]:
    txns: list[dict] = []
    for merchant, amount, every, last_ago, price_change in RECURRING:
        n = 15 if every == 30 else 2 if every == 365 else 20
        for i in range(n):
            day = today - timedelta(days=last_ago + i * every)
            price = amount
            if price_change and i >= price_change[1]:
                price = price_change[0]
            txns.append({"merchant": merchant, "amount": price, "date": day})

    for merchant, low, high in EVERYDAY:
        for _ in range(rng.randint(12, 20)):
            txns.append({
                "merchant": merchant,
                "amount": round(rng.uniform(low, high), 2),
                "date": today - timedelta(days=rng.randint(1, 420)),
            })

    txns.append({"merchant": "HULU *8842", "amount": -17.99, "date": today - timedelta(days=100)})  # refund
    return txns


def seed(email: str = DEMO_EMAIL, password: str = DEMO_PASSWORD, reset: bool = False, today: date | None = None) -> dict:
    today = today or date.today()
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        if user and reset:
            db.delete(user)
            db.commit()
            user = None
        if user is None:
            user = User(email=email, hashed_password=hash_password(password))
            db.add(user)
            db.commit()
            db.refresh(user)

        rng = random.Random(42)
        rows = build_transactions(today, rng)
        existing = {
            t for (t,) in db.query(Transaction.plaid_transaction_id).filter(Transaction.user_id == user.id)
        }
        added = 0
        for i, row in enumerate(rows):
            txn_id = f"demo-{user.id}-{i}"
            if txn_id in existing:
                continue
            db.add(Transaction(
                user_id=user.id,
                plaid_transaction_id=txn_id,
                merchant_name=row["merchant"],
                amount=row["amount"],
                date=row["date"],
                raw_json={"demo": True},
            ))
            added += 1
        db.commit()
        found = sync.refresh_subscriptions(db, user.id, today=today)
        return {"email": email, "transactions_added": added, "subscriptions_found": found}


def main() -> None:
    if settings.plaid_env != "sandbox":
        # The demo user has a well-known password: never create it next to real bank data.
        raise SystemExit(f"Refusing to seed demo data with PLAID_ENV={settings.plaid_env}; it is for sandbox/dev only.")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", default=DEMO_EMAIL)
    parser.add_argument("--password", default=DEMO_PASSWORD, help="only used when creating the user")
    parser.add_argument("--reset", action="store_true", help="delete the demo user and its data first")
    args = parser.parse_args()

    result = seed(args.email, args.password, args.reset)
    print(f"Demo user:      {result['email']}  (password: {args.password})")
    print(f"Transactions:   {result['transactions_added']} added")
    print(f"Subscriptions:  {result['subscriptions_found']} detected")


if __name__ == "__main__":
    main()
