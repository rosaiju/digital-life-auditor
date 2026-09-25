from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services.subscription_detector import detect, normalize_merchant

START = date(2026, 1, 5)


def charges(merchant, amount, count, every=30, start=START, jitter=None):
    """Recurring charges as plain dicts."""
    jitter = jitter or [0] * count
    return [
        {"merchant_name": merchant, "amount": amount, "date": start + timedelta(days=every * i + jitter[i])}
        for i in range(count)
    ]


def by_name(results):
    return {r.merchant_name: r for r in results}


# ---------- input handling (regression: crashed on ORM objects) ----------

def test_accepts_orm_style_objects():
    txns = [SimpleNamespace(**t) for t in charges("Netflix", 15.49, 5)]
    [sub] = detect(txns)
    assert sub.display_name == "Netflix"
    assert sub.frequency == "monthly"


def test_accepts_dicts_and_iso_date_strings():
    txns = [{**t, "date": t["date"].isoformat()} for t in charges("Spotify", 10.99, 4)]
    [sub] = detect(txns)
    assert sub.merchant_name == "spotify"


def test_ignores_rows_with_missing_fields():
    txns = charges("Netflix", 15.49, 4) + [
        {"merchant_name": None, "amount": 5, "date": START},
        {"merchant_name": "", "amount": 5, "date": START},
        {"merchant_name": "X", "amount": None, "date": START},
        SimpleNamespace(merchant_name="Y", amount=3, date=None),
    ]
    assert [s.merchant_name for s in detect(txns)] == ["netflix"]


# ---------- frequency classification ----------

@pytest.mark.parametrize(
    "every,expected",
    [(7, "weekly"), (14, "biweekly"), (30, "monthly"), (91, "quarterly"), (365, "annual")],
)
def test_classifies_frequency(every, expected):
    [sub] = detect(charges("Some Service", 20.0, 4, every=every))
    assert sub.frequency == expected


def test_monthly_charges_with_calendar_drift():
    # Real billing dates drift by a few days (28-31 day months).
    [sub] = detect(charges("Hulu", 17.99, 5, jitter=[0, 1, 0, -1, 2]))
    assert sub.frequency == "monthly"


def test_irregular_intervals_are_not_a_subscription():
    dates = [START, START + timedelta(days=3), START + timedelta(days=50), START + timedelta(days=53)]
    txns = [{"merchant_name": "Corner Cafe", "amount": 12.0, "date": d} for d in dates]
    assert detect(txns) == []


def test_single_charge_is_not_a_subscription():
    assert detect(charges("Netflix", 15.49, 1)) == []


# ---------- amounts ----------

def test_varying_purchase_amounts_are_not_a_subscription():
    amounts = [12.0, 48.0, 7.5, 63.0, 22.0]
    txns = [
        {"merchant_name": "Grocery Mart", "amount": a, "date": START + timedelta(days=30 * i)}
        for i, a in enumerate(amounts)
    ]
    assert detect(txns) == []


def test_small_amount_variation_is_tolerated():
    amounts = [9.99, 10.29, 9.99, 10.49]
    txns = [
        {"merchant_name": "Gym Club", "amount": a, "date": START + timedelta(days=30 * i)}
        for i, a in enumerate(amounts)
    ]
    assert len(detect(txns)) == 1


def test_price_increase_uses_newest_run_and_current_price():
    amounts = [10.99, 10.99, 15.49, 15.49, 15.49]
    txns = [
        {"merchant_name": "Streamly", "amount": a, "date": START + timedelta(days=30 * i)}
        for i, a in enumerate(amounts)
    ]
    [sub] = detect(txns)
    assert sub.amount == 15.49


def test_refunds_and_credits_are_ignored():
    txns = charges("Netflix", 15.49, 4) + [
        {"merchant_name": "Netflix", "amount": -15.49, "date": START + timedelta(days=45)}
    ]
    [sub] = detect(txns)
    assert sub.amount == 15.49
    assert sub.last_charge_date == START + timedelta(days=90)


def test_same_day_duplicates_are_collapsed():
    txns = charges("Netflix", 15.49, 4)
    txns += [dict(t) for t in txns]  # e.g. pending + posted copies
    [sub] = detect(txns)
    assert sub.frequency == "monthly"


# ---------- results ----------

def test_next_charge_date_and_monthly_cost():
    [sub] = detect(charges("Adobe", 120.0, 3, every=365))
    assert sub.frequency == "annual"
    assert sub.next_charge_date == sub.last_charge_date + timedelta(days=365)
    assert sub.monthly_cost == 10.0


def test_results_sorted_by_monthly_cost_descending():
    txns = charges("Cheap Tool", 3.0, 4) + charges("Pricey Tool", 60.0, 4)
    assert [s.merchant_name for s in detect(txns)] == ["pricey tool", "cheap tool"]


def test_confidence_grows_with_more_occurrences():
    few = detect(charges("Service A", 9.0, 2))[0].confidence
    many = detect(charges("Service A", 9.0, 8))[0].confidence
    assert many > few
    assert 0.3 <= few <= many <= 1.0


def test_merchant_variants_are_grouped_together():
    txns = [
        {"merchant_name": "NETFLIX.COM", "amount": 15.49, "date": START},
        {"merchant_name": "Netflix", "amount": 15.49, "date": START + timedelta(days=30)},
        {"merchant_name": "NETFLIX*A1B2", "amount": 15.49, "date": START + timedelta(days=60)},
    ]
    [sub] = detect(txns)
    assert sub.merchant_name == "netflix"


# ---------- known-service enrichment ----------

def test_known_service_gets_metadata():
    [sub] = detect(charges("Netflix", 15.49, 4))
    assert sub.category == "Entertainment"
    assert sub.cancel_url.startswith("https://")


def test_unknown_service_has_no_metadata():
    [sub] = detect(charges("Local Yoga Studio", 45.0, 4))
    assert sub.display_name == "Local Yoga Studio"
    assert sub.category is None and sub.cancel_url is None


def test_known_match_uses_whole_words_only():
    # "pineapple" contains "apple" but is not Apple.
    [sub] = detect(charges("Pineapple Grill Club", 25.0, 4))
    assert sub.category is None


def test_multiword_known_service():
    [sub] = detect(charges("Amazon Prime Video", 8.99, 4))
    assert sub.display_name == "Amazon Prime"


# ---------- merchant normalization ----------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Netflix", "netflix"),
        ("NETFLIX.COM", "netflix"),
        ("Netflix Inc", "netflix"),
        ("NETFLIX*12345", "netflix"),
        ("Spotify USA", "spotify"),
        ("Spotify Premium", "spotify"),
        ("Disney Plus", "disney"),
        ("Disney+", "disney"),
        ("Gym Membership 48213", "gym membership"),
        ("  Hulu   Online ", "hulu"),
        # Regression: the old regex stripped a trailing "us" from real names.
        ("Bonus", "bonus"),
        ("Campus Fitness", "campus fitness"),
    ],
)
def test_normalize_merchant(raw, expected):
    assert normalize_merchant(raw) == expected
