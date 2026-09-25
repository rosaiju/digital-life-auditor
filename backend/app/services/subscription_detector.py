"""Detect recurring charges (subscriptions) in a list of bank transactions.

Pipeline:
  1. Normalize each transaction (ORM objects and dicts are both accepted).
  2. Group by normalized merchant name.
  3. Drop refunds/credits and non-subscription categories (bank fees, transfers,
     loan payments), collapse same-day duplicates.
  4. Require a stable amount (allowing a price change: the newest run of
     similar charges is used when it has enough occurrences).
  5. Classify the gap between charges as weekly/biweekly/monthly/quarterly/annual.
  6. Score confidence from occurrence count and interval tightness; require
     enough charges for the frequency (see MIN_CHARGES_UNKNOWN_SHORT_INTERVAL).
  7. Enrich with known-service metadata (display name, category, cancel URL).
"""
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, NamedTuple

from app.services.money import monthly_cost

KNOWN_SUBS_PATH = Path(__file__).parent / "known_subscriptions.json"
with open(KNOWN_SUBS_PATH, encoding="utf-8") as f:
    KNOWN_SUBS: dict[str, dict] = json.load(f)

# Frequency buckets: (label, target_days, tolerance_days)
FREQUENCIES = [
    ("weekly", 7, 2),
    ("biweekly", 14, 3),
    ("monthly", 30, 5),
    ("quarterly", 90, 10),
    ("annual", 365, 20),
]

MAX_AMOUNT_VARIANCE = 0.10   # charges within 10% of each other count as "the same"
MIN_CONFIDENCE = 0.3
MIN_OCCURRENCES_AFTER_PRICE_CHANGE = 3

# Two charges are enough evidence for a yearly/quarterly bill, or for a service we
# recognise. For anything that recurs more often, coincidences are common (two
# dry-cleaning visits a week apart), so an unrecognised merchant needs three.
LONG_INTERVALS = {"quarterly", "annual"}
MIN_CHARGES_UNKNOWN_SHORT_INTERVAL = 3

# Plaid personal-finance categories that recur but are not cancellable subscriptions.
EXCLUDED_CATEGORIES = {"BANK_FEES", "INCOME", "TRANSFER_IN", "TRANSFER_OUT", "LOAN_PAYMENTS", "LOAN_DISBURSEMENTS"}

_SUFFIX_WORDS = r"(?:inc|llc|ltd|corp|co|com|net|org|usa?|online|app|web|mobile|digital|premium)"
_STRIP_PATTERNS = [
    r"[*#@].*$",                       # NETFLIX*12345, SQ *SHOP  -> everything after the marker
    r"\s+\d{3,}$",                     # trailing store/reference numbers
    rf"[\s.]+{_SUFFIX_WORDS}\.?$",     # "Hulu Inc", "netflix.com", "Spotify USA"
    r"\s+plus$",                       # "Disney Plus" == "Disney+"
    r"\s*\+$",
]


def normalize_merchant(name: str) -> str:
    name = name.lower().strip()
    previous = None
    while previous != name:            # suffixes can stack: "netflix.com inc"
        previous = name
        for pattern in _STRIP_PATTERNS:
            name = re.sub(pattern, "", name).strip()
    return re.sub(r"\s+", " ", name)


def _field(txn: Any, name: str, default: Any = None) -> Any:
    """Read a field from an ORM object, namedtuple-like object or dict."""
    if isinstance(txn, dict):
        return txn.get(name, default)
    return getattr(txn, name, default)


def _to_date(value: Any) -> date:
    if isinstance(value, date):
        return value  # datetime is a date subclass; only the day matters here
    return date.fromisoformat(str(value)[:10])


def _classify_frequency(intervals_days: list[int]) -> tuple[str, float] | None:
    if not intervals_days:
        return None
    avg = mean(intervals_days)
    for label, target, tolerance in FREQUENCIES:
        if abs(avg - target) <= tolerance:
            spread = pstdev(intervals_days) if len(intervals_days) > 1 else 0.0
            tightness = max(0.0, 1.0 - spread / target)
            occurrence_score = min(1.0, len(intervals_days) / 5)
            confidence = round(tightness * 0.6 + occurrence_score * 0.4, 2)
            return label, confidence
    return None


def _stable_run(charges: list[tuple[date, float]]) -> list[tuple[date, float]] | None:
    """Return the charges to analyse, or None when amounts are too erratic.

    If all amounts are within tolerance, every charge is used. Otherwise the
    newest run of similar amounts is used (a price change), provided it has
    enough occurrences to be convincing.
    """
    def variance(run):
        amounts = [a for _, a in run]
        return (max(amounts) - min(amounts)) / max(amounts)

    if variance(charges) <= MAX_AMOUNT_VARIANCE:
        return charges

    for start in range(1, len(charges)):
        run = charges[start:]
        if len(run) < MIN_OCCURRENCES_AFTER_PRICE_CHANGE:
            return None
        if variance(run) <= MAX_AMOUNT_VARIANCE:
            return run
    return None


def _lookup_known(norm_name: str) -> dict | None:
    """Match a merchant against known services on whole words only."""
    words = set(re.findall(r"[a-z0-9]+", norm_name))
    best: tuple[int, dict] | None = None
    for key, data in KNOWN_SUBS.items():
        key_words = key.split()
        if all(w in words for w in key_words):
            if best is None or len(key_words) > best[0]:
                best = (len(key_words), data)
    return best[1] if best else None


class DetectedSubscription(NamedTuple):
    merchant_name: str
    display_name: str | None
    amount: float
    frequency: str
    last_charge_date: date
    next_charge_date: date
    confidence: float
    category: str | None
    cancel_url: str | None
    monthly_cost: float


def detect(transactions: list) -> list[DetectedSubscription]:
    """
    transactions: objects or dicts exposing merchant_name, amount and date.
    Returns detected subscriptions sorted by monthly cost, highest first.
    """
    groups: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for txn in transactions:
        merchant = _field(txn, "merchant_name") or ""
        amount = _field(txn, "amount")
        charge_date = _field(txn, "date")
        if not merchant or amount is None or charge_date is None:
            continue
        if amount <= 0:  # Plaid: positive = money out; negatives are refunds/income
            continue
        if _field(txn, "category") in EXCLUDED_CATEGORIES:
            continue
        key = normalize_merchant(merchant)
        if key:
            groups[key].append((_to_date(charge_date), float(amount)))

    results: list[DetectedSubscription] = []
    for norm_name, charges in groups.items():
        # One charge per day: duplicates (e.g. pending + posted) would skew intervals.
        by_day: dict[date, float] = {}
        for day, amount in charges:
            by_day[day] = max(by_day.get(day, 0.0), amount)
        charges = sorted(by_day.items())
        if len(charges) < 2:
            continue

        run = _stable_run(charges)
        if run is None:
            continue

        dates = [d for d, _ in run]
        intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        classified = _classify_frequency(intervals)
        if not classified:
            continue
        frequency, confidence = classified
        if confidence < MIN_CONFIDENCE:
            continue

        known = _lookup_known(norm_name)
        if known is None and frequency not in LONG_INTERVALS and len(run) < MIN_CHARGES_UNKNOWN_SHORT_INTERVAL:
            continue

        # Use the newest amount: it is what the user pays now.
        amount = round(run[-1][1], 2)
        last_charge = dates[-1]
        next_charge = last_charge + timedelta(days=round(mean(intervals)))

        results.append(
            DetectedSubscription(
                merchant_name=norm_name,
                display_name=known["display_name"] if known else norm_name.title(),
                amount=amount,
                frequency=frequency,
                last_charge_date=last_charge,
                next_charge_date=next_charge,
                confidence=confidence,
                category=known["category"] if known else None,
                cancel_url=known.get("cancel_url") if known else None,
                monthly_cost=monthly_cost(amount, frequency),
            )
        )

    results.sort(key=lambda s: s.monthly_cost, reverse=True)
    return results
