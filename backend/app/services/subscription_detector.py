import json
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, stdev
from typing import NamedTuple

KNOWN_SUBS_PATH = Path(__file__).parent / "known_subscriptions.json"
with open(KNOWN_SUBS_PATH) as f:
    KNOWN_SUBS: dict = json.load(f)

# Frequency buckets: (label, target_days, tolerance_days)
FREQUENCIES = [
    ("weekly", 7, 2),
    ("biweekly", 14, 3),
    ("monthly", 30, 5),
    ("quarterly", 90, 10),
    ("annual", 365, 20),
]

_STRIP_PATTERNS = [
    r"\s*(usa?|inc\.?|llc\.?|com\.?|corp\.?|ltd\.?)$",
    r"\s*\*+\d+$",          # NETFLIX*12345
    r"\s+\d{3,}$",          # trailing digits
    r"[*#@].*$",            # anything after special chars
    r"\s+(online|app|web|mobile|digital|plus|\+|premium)$",
]


def normalize_merchant(name: str) -> str:
    name = name.lower().strip()
    for pattern in _STRIP_PATTERNS:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE).strip()
    return name


def _classify_frequency(intervals_days: list[float]) -> tuple[str, float] | None:
    if not intervals_days:
        return None
    avg = mean(intervals_days)
    for label, target, tolerance in FREQUENCIES:
        if abs(avg - target) <= tolerance:
            # Confidence: more occurrences + tighter clustering = higher score
            spread = stdev(intervals_days) if len(intervals_days) > 1 else 0
            tightness = max(0.0, 1.0 - spread / target)
            occurrence_score = min(1.0, len(intervals_days) / 5)
            confidence = round((tightness * 0.6 + occurrence_score * 0.4), 2)
            return label, confidence
    return None


def _monthly_equivalent(amount: float, frequency: str) -> float:
    multipliers = {
        "weekly": 4.33,
        "biweekly": 2.17,
        "monthly": 1.0,
        "quarterly": 1 / 3,
        "annual": 1 / 12,
    }
    return round(amount * multipliers.get(frequency, 1.0), 2)


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
    transactions: list of objects/dicts with .merchant_name, .amount, .date
    Returns detected subscriptions sorted by monthly_cost descending.
    """
    # Group by normalized merchant
    groups: dict[str, list] = defaultdict(list)
    for txn in transactions:
        merchant = getattr(txn, "merchant_name", None) or txn.get("merchant_name", "")
        if not merchant:
            continue
        key = normalize_merchant(merchant)
        groups[key].append(txn)

    results: list[DetectedSubscription] = []

    for norm_name, txns in groups.items():
        if len(txns) < 2:
            continue

        # Sort by date ascending
        txns_sorted = sorted(txns, key=lambda t: getattr(t, "date", t.get("date")))

        # Check amount stability (allow ±10% variance)
        amounts = [getattr(t, "amount", t.get("amount", 0)) for t in txns_sorted]
        if max(amounts) == 0:
            continue
        amount_variance = (max(amounts) - min(amounts)) / max(amounts)
        if amount_variance > 0.10:
            continue

        avg_amount = round(mean(amounts), 2)

        # Calculate intervals
        dates = [getattr(t, "date", t.get("date")) for t in txns_sorted]
        intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]

        classified = _classify_frequency(intervals)
        if not classified:
            continue

        frequency, confidence = classified
        if confidence < 0.3:
            continue

        last_charge = dates[-1]
        avg_interval = int(mean(intervals))
        next_charge = last_charge + timedelta(days=avg_interval)

        # Lookup known subscription metadata
        known = None
        for key, data in KNOWN_SUBS.items():
            if key in norm_name or norm_name in key:
                known = data
                break

        results.append(
            DetectedSubscription(
                merchant_name=norm_name,
                display_name=known["display_name"] if known else norm_name.title(),
                amount=avg_amount,
                frequency=frequency,
                last_charge_date=last_charge,
                next_charge_date=next_charge,
                confidence=confidence,
                category=known["category"] if known else None,
                cancel_url=known["cancel_url"] if known else None,
                monthly_cost=_monthly_equivalent(avg_amount, frequency),
            )
        )

    results.sort(key=lambda s: s.monthly_cost, reverse=True)
    return results
