from datetime import date

from sqlalchemy.orm import sessionmaker

from app import seed_demo
from app.models.subscription import Subscription
from app.models.transaction import Transaction

EXPECTED = {
    # display name: (amount, frequency)
    "Adobe Creative Cloud": (599.88, "annual"),
    "Planet Fitness": (24.99, "monthly"),
    "ChatGPT": (20.00, "monthly"),
    "New York Times": (4.25, "weekly"),
    "Hulu": (17.99, "monthly"),
    "Netflix": (15.49, "monthly"),
    "Disney+": (13.99, "monthly"),          # price rose from 10.99
    "Spotify": (10.99, "monthly"),
    "Amazon Prime": (8.99, "monthly"),
    "Apple Services": (2.99, "monthly"),
}


def run_seed(monkeypatch, db_session, **kwargs):
    # Point the seeder at the test database (it opens its own sessions).
    monkeypatch.setattr(seed_demo, "SessionLocal", sessionmaker(bind=db_session.get_bind()))
    return seed_demo.seed(today=date(2026, 9, 24), **kwargs)


def test_detects_exactly_the_seeded_subscriptions_and_no_everyday_spending(monkeypatch, db_session):
    result = run_seed(monkeypatch, db_session)
    found = {s.display_name: (s.amount, s.frequency) for s in db_session.query(Subscription).all()}
    assert found == EXPECTED
    assert result["subscriptions_found"] == len(EXPECTED)


def test_refund_does_not_break_detection(monkeypatch, db_session):
    run_seed(monkeypatch, db_session)
    assert db_session.query(Transaction).filter(Transaction.amount < 0).count() == 1
    hulu = db_session.query(Subscription).filter(Subscription.merchant_name == "hulu").one()
    assert hulu.amount == 17.99


def test_seed_is_idempotent_and_reset_recreates(monkeypatch, db_session):
    first = run_seed(monkeypatch, db_session)
    second = run_seed(monkeypatch, db_session)
    assert second["transactions_added"] == 0
    assert db_session.query(Subscription).count() == first["subscriptions_found"]

    run_seed(monkeypatch, db_session, reset=True)
    assert db_session.query(Transaction).count() > 0
    assert db_session.query(Subscription).count() == first["subscriptions_found"]
