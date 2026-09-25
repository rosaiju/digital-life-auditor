import json
from datetime import date
from types import SimpleNamespace

import pytest

from app.config import settings
from app.models.subscription import Subscription
from app.services import ai_insights


def sub(name, amount, frequency="monthly", category=None):
    return SimpleNamespace(
        display_name=name, merchant_name=name.lower(), amount=amount,
        frequency=frequency, category=category, last_charge_date=date(2026, 8, 1),
    )


STREAMING = [
    sub("Netflix", 15.49, category="Entertainment"),
    sub("Hulu", 17.99, category="Entertainment"),
    sub("Spotify", 10.99, category="Entertainment"),
    sub("Adobe", 599.88, "annual", category="Productivity"),   # $49.99/mo
]


@pytest.fixture()
def groq_key(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "test-key")


def fake_groq(monkeypatch, content=None, error=None):
    """Replace the Groq SDK client with a stub returning `content` (or raising `error`)."""
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if error:
                raise error
            message = SimpleNamespace(content=content if isinstance(content, str) else json.dumps(content))
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class FakeGroq:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=Completions())

    import groq
    monkeypatch.setattr(groq, "Groq", FakeGroq)
    return calls


# ---------- deterministic parts ----------

def test_empty_subscriptions():
    result = ai_insights.generate_insights([])
    assert result["subscription_count"] == 0
    assert result["monthly_total"] == 0.0
    assert result["insights"] == []


def test_totals_and_breakdown_are_computed_locally():
    result = ai_insights.generate_insights(STREAMING)  # no API key -> rules path
    assert result["monthly_total"] == round(15.49 + 17.99 + 10.99 + 49.99, 2)
    assert result["yearly_total"] == round(result["monthly_total"] * 12, 2)
    assert result["category_breakdown"]["Entertainment"] == round(15.49 + 17.99 + 10.99, 2)
    assert result["category_breakdown"]["Productivity"] == 49.99
    assert result["subscription_count"] == 4


# ---------- rule-based fallback ----------

def test_without_api_key_uses_rules_and_flags_redundancy():
    result = ai_insights.generate_insights(STREAMING)
    assert result["source"] == "rules"
    redundant = [i for i in result["insights"] if i["type"] == "redundant"]
    assert len(redundant) == 1
    assert "3 overlapping Entertainment" in redundant[0]["title"]
    assert redundant[0]["potential_savings"] == 10.99            # cheapest overlapping service
    assert "Spotify" in redundant[0]["detail"] and "Netflix" in redundant[0]["detail"]
    assert result["top_opportunity"]


def test_rules_flag_high_cost_subscription():
    result = ai_insights.generate_insights([sub("Peloton", 120.0), sub("Notes", 2.0)])
    warnings = [i for i in result["insights"] if i["type"] == "warning"]
    assert [w["title"] for w in warnings] == ["Peloton is a large expense"]


def test_rules_summary_handles_singular():
    result = ai_insights.generate_insights([sub("Netflix", 15.49)])
    assert "1 active subscription." in result["summary"]


# ---------- LLM path ----------

GOOD_LLM = {
    "summary": "You spend a lot on streaming.",
    "insights": [
        {"type": "redundant", "title": "Too many streaming apps", "detail": "Cut Hulu.", "potential_savings": 17.99},
    ],
    "top_opportunity": "Cancel Hulu.",
}


def test_llm_narrative_is_used_but_totals_stay_local(groq_key, monkeypatch):
    calls = fake_groq(monkeypatch, {**GOOD_LLM, "monthly_total": 1.0, "category_breakdown": {"Lies": 1}})
    result = ai_insights.generate_insights(STREAMING)
    assert result["source"] == "ai"
    assert result["summary"] == GOOD_LLM["summary"]
    assert result["monthly_total"] == 94.46                       # not the model's 1.0
    assert "Lies" not in result["category_breakdown"]
    assert calls[0]["model"] == settings.groq_model
    assert calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    "content",
    ["this is not json", {"insights": []}, ["a", "list"], {"summary": 42}],
    ids=["not-json", "missing-summary", "wrong-shape", "bad-summary-type"],
)
def test_unusable_llm_output_falls_back_to_rules(groq_key, monkeypatch, content):
    fake_groq(monkeypatch, content)
    result = ai_insights.generate_insights(STREAMING)
    assert result["source"] == "rules"
    assert result["insights"]


def test_llm_exception_falls_back_to_rules(groq_key, monkeypatch):
    fake_groq(monkeypatch, error=RuntimeError("rate limited"))
    assert ai_insights.generate_insights(STREAMING)["source"] == "rules"


def test_llm_insights_are_sanitized(groq_key, monkeypatch):
    fake_groq(monkeypatch, {
        "summary": "ok",
        "insights": [
            {"type": "made-up", "title": "T", "detail": "D", "potential_savings": "12.5"},
            {"type": "tip", "title": "Negative", "detail": "D", "potential_savings": -50},
            {"type": "tip", "title": "", "detail": "missing title"},
            "garbage",
        ],
        "top_opportunity": None,
    })
    result = ai_insights.generate_insights(STREAMING)
    assert [(i["type"], i["potential_savings"]) for i in result["insights"]] == [("tip", 12.5), ("tip", 0.0)]
    assert result["top_opportunity"] is None


# ---------- endpoints ----------

def test_generate_then_get_latest(client, register, db_session):
    headers, user_id = register()
    assert "message" in client.get("/insights", headers=headers).json()

    db_session.add_all([
        Subscription(user_id=user_id, merchant_name="netflix", display_name="Netflix", amount=15.49,
                     frequency="monthly", category="Entertainment", confidence=0.9),
        Subscription(user_id=user_id, merchant_name="hulu", display_name="Hulu", amount=17.99,
                     frequency="monthly", category="Entertainment", confidence=0.9),
        Subscription(user_id=user_id, merchant_name="old", display_name="Old", amount=99.0,
                     frequency="monthly", confidence=0.9, status="dismissed"),
    ])
    db_session.commit()

    generated = client.post("/insights/generate", headers=headers)
    assert generated.status_code == 200
    assert generated.json()["subscription_count"] == 2            # dismissed excluded
    assert client.get("/insights", headers=headers).json() == generated.json()


def test_insights_are_per_user(client, register):
    alice, _ = register("alice@example.com")
    bob, _ = register("bob@example.com")
    client.post("/insights/generate", headers=alice)
    assert "message" in client.get("/insights", headers=bob).json()
