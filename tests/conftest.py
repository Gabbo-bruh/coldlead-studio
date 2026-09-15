from __future__ import annotations

import pytest

from coldlead.config import resolve_config
from coldlead.enrich.insights import heuristic_enrich
from coldlead.models import Company, Lead, LegalForm, RawSignals
from coldlead.providers.demo import demo_leads
from coldlead.storage import SessionStore

ENV_KEYS = (
    "COLDLEAD_PRESET",
    "COLDLEAD_SEASON",
    "COLDLEAD_LANG",
    "COLDLEAD_COUNTRY",
    "COLDLEAD_LLM_PROVIDER",
    "COLDLEAD_LLM_MODEL",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "GOOGLE_PLACES_API_KEY",
    "PAGESPEED_API_KEY",
    "META_AD_LIBRARY_ACCESS_TOKEN",
    *(f"COLDLEAD_W_{k}" for k in "GTFPIDCA"),
    "COLDLEAD_TIER_1_MIN",
    "COLDLEAD_TIER_2_MIN",
)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own COLDLEAD_HOME, no API keys and no stray .env file."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    home = tmp_path / "home"
    monkeypatch.setenv("COLDLEAD_HOME", str(home))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return home


PUBLIC_IP = "93.184.215.14"


@pytest.fixture(autouse=True)
def offline_dns(monkeypatch):
    """No test touches real DNS: every hostname resolves to one public address.

    SSRF tests override ``resolve_host`` again to simulate private or rebinding answers.
    """
    monkeypatch.setattr("coldlead.enrich.tech_audit.resolve_host", lambda host, port: [PUBLIC_IP])


@pytest.fixture
def config():
    return resolve_config(season="year_round", user_config={}, env={})


@pytest.fixture
def leads():
    return [heuristic_enrich(lead) for lead in demo_leads("Charter nautico", "Portofino", 12)]


@pytest.fixture
def store(isolated):
    return SessionStore(isolated / "sessions")


def make_lead(**signals) -> Lead:
    company = signals.pop("company", None) or Company(
        name="Portofino Charter Deluxe S.r.l.",
        niche="Charter nautico",
        city="Santa Margherita Ligure",
        phone="+39 0185 000001",
        email="info@example.it",
        legal_form=LegalForm.SRL,
        direct_contact_person="Marco Benvenuti",
        contact_channels=["WhatsApp", "Phone", "Email"],
    )
    base = dict(
        has_website=True,
        website_url="https://portofino.example",
        lighthouse_performance=38,
        mobile_friendly=True,
        has_ssl=True,
        cms_stack="WordPress (Elementor)",
        has_multilingual=False,
        has_booking_system=False,
        has_ai_chat=False,
        reviews_count=84,
        average_rating=4.7,
        owner_reply_rate=85.0,
        is_toxic_owner=False,
        is_running_ads=True,
    )
    base.update(signals)
    return Lead(
        id="lead_test0001", company=company, raw_signals=RawSignals(**base), source="manual"
    )
