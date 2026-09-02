import json
from collections import defaultdict
from datetime import datetime

from openai import OpenAI

from app.config import settings

client = OpenAI(api_key=settings.openai_api_key)


def generate_insights(subscriptions: list) -> dict:
    """
    Takes a list of Subscription ORM objects, calls GPT-4o to produce
    categorized insights, redundancy flags, and spend recommendations.
    """
    if not subscriptions:
        return _empty_insights()

    # Build summary for the prompt
    monthly_total = sum(
        _monthly_cost(s.amount, s.frequency) for s in subscriptions
    )
    yearly_total = round(monthly_total * 12, 2)

    sub_list = [
        {
            "name": s.display_name or s.merchant_name,
            "amount": s.amount,
            "frequency": s.frequency,
            "monthly_cost": round(_monthly_cost(s.amount, s.frequency), 2),
            "category": s.category or "Unknown",
            "last_charge": str(s.last_charge_date) if s.last_charge_date else None,
        }
        for s in subscriptions
    ]

    prompt = f"""You are a personal finance AI analyzing a user's active subscriptions.

Subscriptions (JSON):
{json.dumps(sub_list, indent=2)}

Monthly total: ${monthly_total:.2f}
Yearly total: ${yearly_total:.2f}

Respond ONLY with a valid JSON object (no markdown) with this exact structure:
{{
  "summary": "One sentence overview of their subscription spending.",
  "insights": [
    {{
      "type": "redundant|savings|warning|tip",
      "title": "Short title (max 8 words)",
      "detail": "1-2 sentence explanation with specific names and dollar amounts.",
      "potential_savings": 0.00
    }}
  ],
  "category_breakdown": {{
    "CategoryName": 0.00
  }},
  "top_opportunity": "Single most impactful action they could take to save money."
}}

Rules:
- Flag redundant services in the same category (e.g. 3 streaming services)
- Flag any subscription over $50/month as worth reviewing
- Suggest consolidation where applicable
- Be specific: name the services, state exact amounts
- Limit to 4-6 most impactful insights
- category_breakdown values are monthly costs
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)
    result["generated_at"] = datetime.utcnow().isoformat()
    result["monthly_total"] = round(monthly_total, 2)
    result["yearly_total"] = yearly_total
    result["subscription_count"] = len(subscriptions)
    return result


def _monthly_cost(amount: float, frequency: str) -> float:
    multipliers = {
        "weekly": 4.33,
        "biweekly": 2.17,
        "monthly": 1.0,
        "quarterly": 1 / 3,
        "annual": 1 / 12,
    }
    return amount * multipliers.get(frequency, 1.0)


def _empty_insights() -> dict:
    return {
        "summary": "No active subscriptions found. Connect a bank account to get started.",
        "insights": [],
        "category_breakdown": {},
        "top_opportunity": None,
        "monthly_total": 0.0,
        "yearly_total": 0.0,
        "subscription_count": 0,
        "generated_at": datetime.utcnow().isoformat(),
    }
