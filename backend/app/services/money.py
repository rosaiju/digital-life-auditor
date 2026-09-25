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
