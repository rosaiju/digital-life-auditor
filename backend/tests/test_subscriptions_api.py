from datetime import date

from app.models.subscription import Subscription


def add_sub(db, user_id, name="netflix", amount=15.49, frequency="monthly", status="active"):
    sub = Subscription(
        user_id=user_id,
        merchant_name=name,
        display_name=name.title(),
        amount=amount,
        frequency=frequency,
        confidence=0.9,
        status=status,
        last_charge_date=date(2026, 8, 1),
        next_charge_date=date(2026, 9, 1),
    )
    db.add(sub)
    db.commit()
    return sub


def test_list_is_sorted_by_monthly_cost_and_includes_it(client, register, db_session):
    headers, user_id = register()
    add_sub(db_session, user_id, "cheap", 5.0)
    add_sub(db_session, user_id, "adobe", 120.0, "annual")      # $10/mo
    add_sub(db_session, user_id, "gym", 30.0, "monthly")
    body = client.get("/subscriptions", headers=headers).json()
    assert [s["merchant_name"] for s in body] == ["gym", "adobe", "cheap"]
    assert body[1]["monthly_cost"] == 10.0


def test_list_filters_by_status(client, register, db_session):
    headers, user_id = register()
    add_sub(db_session, user_id, "a")
    add_sub(db_session, user_id, "b", status="dismissed")
    names = lambda status: sorted(s["merchant_name"] for s in client.get(f"/subscriptions?status={status}", headers=headers).json())
    assert names("active") == ["a"]
    assert names("dismissed") == ["b"]
    assert names("all") == ["a", "b"]
    assert client.get("/subscriptions?status=bogus", headers=headers).status_code == 422


def test_dismiss_and_restore(client, register, db_session):
    headers, user_id = register()
    sub = add_sub(db_session, user_id)
    dismissed = client.patch(f"/subscriptions/{sub.id}/dismiss", headers=headers)
    assert dismissed.status_code == 200 and dismissed.json()["status"] == "dismissed"
    assert client.get("/subscriptions", headers=headers).json() == []
    restored = client.patch(f"/subscriptions/{sub.id}/restore", headers=headers)
    assert restored.json()["status"] == "active"
    assert len(client.get("/subscriptions", headers=headers).json()) == 1


def test_users_cannot_see_or_modify_each_others_subscriptions(client, register, db_session):
    alice, alice_id = register("alice@example.com")
    bob, _ = register("bob@example.com")
    sub = add_sub(db_session, alice_id)
    assert client.get("/subscriptions", headers=bob).json() == []
    assert client.patch(f"/subscriptions/{sub.id}/dismiss", headers=bob).status_code == 404
    assert client.patch(f"/subscriptions/{sub.id}/restore", headers=bob).status_code == 404
    assert client.get("/subscriptions", headers=alice).json()[0]["status"] == "active"


def test_dismiss_unknown_subscription_is_404(client, auth_headers):
    assert client.patch("/subscriptions/12345/dismiss", headers=auth_headers).status_code == 404
