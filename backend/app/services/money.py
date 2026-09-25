"""Shared money helpers."""

# How many charges of each frequency happen in an average month.
_MONTHLY_MULTIPLIERS = {
    "weekly": 52 / 12,
    "biweekly": 26 / 12,
    "monthly": 1.0,
    "quarterly": 1 / 3,
    "annual": 1 / 12,
}


def monthly_cost(amount: float, frequency: str) -> float:
    """Normalize a recurring charge to its average monthly cost."""
    return round(amount * _MONTHLY_MULTIPLIERS.get(frequency, 1.0), 2)


# Typical days between charges of each frequency.
FREQUENCY_DAYS = {"weekly": 7, "biweekly": 14, "monthly": 30, "quarterly": 90, "annual": 365}


def lapse_grace_days(frequency: str) -> int:
    """How long past its expected date a charge may be before we assume it was cancelled.

    Banks post charges late and billing dates drift, so allow a quarter of the interval
    (at least a week).
    """
    return max(7, round(FREQUENCY_DAYS.get(frequency, 30) * 0.25))
