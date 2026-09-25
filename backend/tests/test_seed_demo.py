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
    active = db_session.query(Subscription).filter(Subscription.status == "active")
    assert {s.display_name: (s.amount, s.frequency) for s in active} == EXPECTED
    assert result["subscriptions_found"] == len(EXPECTED)
    # The cancelled one is kept for history but not counted as a current subscription.
    ended = db_session.query(Subscription).filter(Subscription.status == "ended").all()
    assert [s.display_name for s in ended] == ["Peloton"]


def test_refund_does_not_break_detection(monkeypatch, db_session):
    run_seed(monkeypatch, db_session)
    assert db_session.query(Transaction).filter(Transaction.amount < 0).count() == 1
    hulu = db_session.query(Subscription).filter(Subscription.merchant_name == "hulu").one()
    assert hulu.amount == 17.99


def test_seed_is_idempotent_and_reset_recreates(monkeypatch, db_session):
    first = run_seed(monkeypatch, db_session)
    second = run_seed(monkeypatch, db_session)
    assert second["transactions_added"] == 0
    total = db_session.query(Subscription).count()
    assert total == first["subscriptions_found"] + 1        # + the ended one

    run_seed(monkeypatch, db_session, reset=True)
    assert db_session.query(Transaction).count() > 0
    assert db_session.query(Subscription).count() == total


def test_cli_refuses_to_run_outside_the_sandbox(monkeypatch):
    import pytest

    monkeypatch.setattr(seed_demo.settings, "plaid_env", "production")
    monkeypatch.setattr("sys.argv", ["seed_demo"])
    with pytest.raises(SystemExit, match="Refusing to seed demo data"):
        seed_demo.main()
