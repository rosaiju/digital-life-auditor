"""Subscription insights.

Totals and the category breakdown are always computed here in plain Python.
The LLM (Groq) only writes the narrative: summary, individual insights and the
top opportunity. If no API key is configured, or the call fails or returns
something unusable, a deterministic rule-based analysis is returned instead so
the endpoint never fails because of the model.
"""
import json
import logging
from collections import defaultdict

from app.config import settings
from app.services.money import monthly_cost
from app.utils import utcnow

logger = logging.getLogger(__name__)

INSIGHT_TYPES = {"redundant", "savings", "warning", "tip"}
HIGH_COST_THRESHOLD = 50.0  # monthly, USD
LLM_TIMEOUT_SECONDS = 30


def generate_insights(subscriptions: list) -> dict:
    """Takes Subscription ORM objects and returns the insights payload."""
    if not subscriptions:
        return _empty_insights()

    facts = _facts(subscriptions)
    narrative = None
    if settings.groq_api_key:
        try:
            narrative = _llm_narrative(facts)
        except Exception:  # network, auth, rate limit, malformed JSON...
            logger.warning("Groq insight generation failed; using rule-based fallback", exc_info=True)

    source = "ai"
    if narrative is None:
        narrative, source = _rule_based_narrative(facts), "rules"

    return {
        **narrative,
        "category_breakdown": facts["category_breakdown"],
        "monthly_total": facts["monthly_total"],
        "yearly_total": facts["yearly_total"],
        "subscription_count": len(facts["subscriptions"]),
        "source": source,
        "generated_at": utcnow().isoformat(),
    }


def _facts(subscriptions: list) -> dict:
    items = [
        {
            "name": s.display_name or s.merchant_name,
            "amount": round(s.amount, 2),
            "frequency": s.frequency,
            "monthly_cost": monthly_cost(s.amount, s.frequency),
            "category": s.category or "Other",
        }
        for s in subscriptions
    ]
    breakdown: dict[str, float] = defaultdict(float)
    for item in items:
        breakdown[item["category"]] += item["monthly_cost"]
    monthly_total = round(sum(i["monthly_cost"] for i in items), 2)
    return {
        "subscriptions": items,
        "monthly_total": monthly_total,
        "yearly_total": round(monthly_total * 12, 2),
        "category_breakdown": {k: round(v, 2) for k, v in sorted(breakdown.items(), key=lambda kv: -kv[1])},
    }


# ---------- LLM ----------

def _llm_narrative(facts: dict) -> dict | None:
    from groq import Groq  # imported lazily so the app runs without the SDK configured

    client = Groq(api_key=settings.groq_api_key, timeout=LLM_TIMEOUT_SECONDS)
    prompt = f"""You are a personal finance assistant reviewing a user's active subscriptions.

Subscriptions (JSON):
{json.dumps(facts["subscriptions"], indent=2)}

Monthly total: ${facts["monthly_total"]:.2f}
Yearly total: ${facts["yearly_total"]:.2f}

Respond ONLY with a JSON object of exactly this shape:
{{
  "summary": "One sentence overview of their subscription spending.",
  "insights": [
    {{
      "type": "redundant|savings|warning|tip",
      "title": "Short title (max 8 words)",
      "detail": "1-2 sentences naming specific services and dollar amounts.",
      "potential_savings": 0.00
    }}
  ],
  "top_opportunity": "The single most impactful action they could take to save money."
}}

Rules:
- Flag overlapping services in the same category (for example several streaming services)
- Flag any single subscription costing over ${HIGH_COST_THRESHOLD:.0f}/month as worth reviewing (the total is not subject to this rule)
- Be specific: name the services and state exact amounts
- 4-6 insights at most; potential_savings is a monthly USD amount
"""
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    return _validate_narrative(json.loads(response.choices[0].message.content))


def _validate_narrative(data: object) -> dict | None:
    """Keep only well-formed fields from the model output; None if unusable."""
    if not isinstance(data, dict) or not isinstance(data.get("summary"), str):
        return None
    insights = []
    for raw in data.get("insights") or []:
        if not isinstance(raw, dict) or not raw.get("title") or not raw.get("detail"):
            continue
        try:
            savings = max(0.0, float(raw.get("potential_savings") or 0))
        except (TypeError, ValueError):
            savings = 0.0
        kind = raw.get("type") if raw.get("type") in INSIGHT_TYPES else "tip"
        insights.append({
            "type": kind,
            "title": str(raw["title"]),
            "detail": str(raw["detail"]),
            "potential_savings": round(savings, 2),
        })
    top = data.get("top_opportunity")
    return {
        "summary": data["summary"],
        "insights": insights[:6],
        "top_opportunity": top if isinstance(top, str) and top else None,
    }


# ---------- Rule-based fallback ----------

def _rule_based_narrative(facts: dict) -> dict:
    subs = facts["subscriptions"]
    insights: list[dict] = []

    by_category: dict[str, list[dict]] = defaultdict(list)
    for s in subs:
        if s["category"] != "Other":
            by_category[s["category"]].append(s)

    for category, group in by_category.items():
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda s: s["monthly_cost"], reverse=True)
        names = ", ".join(f"{s['name']} (${s['monthly_cost']:.2f}/mo)" for s in group)
        cheapest = group[-1]
        insights.append({
            "type": "redundant",
            "title": f"{len(group)} overlapping {category} services",
            "detail": f"You pay for {names}. Cancelling {cheapest['name']} would save ${cheapest['monthly_cost']:.2f}/month.",
            "potential_savings": cheapest["monthly_cost"],
        })

    for s in sorted(subs, key=lambda s: s["monthly_cost"], reverse=True):
        if s["monthly_cost"] > HIGH_COST_THRESHOLD:
            insights.append({
                "type": "warning",
                "title": f"{s['name']} is a large expense",
                "detail": f"{s['name']} costs ${s['monthly_cost']:.2f}/month (${s['monthly_cost'] * 12:.2f}/year). Make sure you still use it.",
                "potential_savings": 0.0,
            })

    insights.sort(key=lambda i: i["potential_savings"], reverse=True)
    insights = insights[:6]

    priciest = max(subs, key=lambda s: s["monthly_cost"])
    if insights and insights[0]["potential_savings"] > 0:
        top = insights[0]["detail"]
    else:
        top = (
            f"Review {priciest['name']}: at ${priciest['monthly_cost']:.2f}/month it is your largest "
            "subscription, and cancelling anything you rarely use is the fastest way to save."
        )

    count = len(subs)
    summary = (
        f"You spend ${facts['monthly_total']:.2f}/month (${facts['yearly_total']:.2f}/year) "
        f"across {count} active subscription{'s' if count != 1 else ''}."
    )
    return {"summary": summary, "insights": insights, "top_opportunity": top}


def _empty_insights() -> dict:
    return {
        "summary": "No active subscriptions found. Connect a bank account to get started.",
        "insights": [],
        "category_breakdown": {},
        "top_opportunity": None,
        "monthly_total": 0.0,
        "yearly_total": 0.0,
        "subscription_count": 0,
        "source": "rules",
        "generated_at": utcnow().isoformat(),
    }
