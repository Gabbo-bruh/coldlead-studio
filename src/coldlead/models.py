"""Data contract: the ``POSLeadDossier`` schema v1.0.0.

Two families of models live here:

* **Raw data** (``Company``, ``RawSignals``, ``Lead``, ``Session``) is what scraping produces.
  It is persisted in the session cache and never contains scores.
* **Derived data** (``POSEvaluation``, ``ActionKit``, ``LeadDossier``) is recomputed on demand
  from raw data + a scoring configuration. It is cheap and deterministic.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def make_lead_id(*parts: str) -> str:
    """Stable, human-friendly id derived from identifying fields."""
    digest = hashlib.sha1("|".join(p.strip().lower() for p in parts).encode("utf-8")).hexdigest()
    return f"lead_{digest[:8]}"


class LegalForm(str, Enum):
    SPA = "S.p.A."
    SRL = "S.r.l."
    SRLS = "S.r.l.s."
    SNC_SAS = "S.n.c. / S.a.s."
    COOP = "Soc. Coop."
    SOLE_TRADER = "Ditta Individuale"
    PROFESSIONAL = "Studio Professionale"
    LTD = "Ltd / LLC / GmbH"
    UNKNOWN = "Unknown"


class Tier(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    RED_FLAG = "red_flag"


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True, use_enum_values=False)


class Company(_Model):
    name: str
    niche: str = ""
    city: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    vat_number: str = ""
    legal_form: LegalForm = LegalForm.UNKNOWN
    employees_estimate: int | None = None
    direct_contact_person: str = ""
    contact_channels: list[str] = Field(default_factory=list)


class RawSignals(_Model):
    """Objective signals collected once by providers and auditors.

    ``None`` always means *unknown*: the scoring engine treats it as neutral and says so.
    """

    # Website & technology
    has_website: bool = False
    website_url: str | None = None
    lighthouse_performance: int | None = Field(default=None, ge=0, le=100)
    performance_source: Literal["lighthouse", "estimated", "provided"] | None = None
    mobile_friendly: bool | None = None
    has_ssl: bool | None = None
    cms_stack: str | None = None
    has_multilingual: bool | None = None
    has_booking_system: bool | None = None
    has_ai_chat: bool | None = None
    has_pdf_menu: bool | None = None
    has_contact_form: bool | None = None
    footer_agency_credit: str | None = None
    page_weight_kb: int | None = None
    response_time_ms: int | None = None

    # Reputation & owner psychology
    reviews_count: int | None = None
    average_rating: float | None = Field(default=None, ge=0, le=5)
    owner_reply_rate: float | None = Field(default=None, ge=0, le=100)
    owner_sentiment_tone: str | None = None
    is_toxic_owner: bool | None = None
    sample_owner_replies: list[str] = Field(default_factory=list)

    # Market & context
    is_running_ads: bool | None = None
    ads_evidence: list[str] = Field(default_factory=list)
    is_chain: bool | None = None
    business_status: str | None = None  # e.g. OPERATIONAL, CLOSED_PERMANENTLY, IN_LIQUIDATION
    international_clientele: bool | None = None
    competitor_pressure: float | None = Field(default=None, ge=0, le=10)
    competitor_notes: str = ""
    ticket_value_hint: float | None = Field(default=None, ge=0, le=10)


class Enrichment(_Model):
    """Qualitative insights (heuristic or LLM generated)."""

    vibe_opportunity_summary: str = ""
    psychological_lever: str = ""
    enriched_by: str = "heuristic"


class Lead(_Model):
    id: str
    company: Company
    raw_signals: RawSignals = Field(default_factory=RawSignals)
    enrichment: Enrichment = Field(default_factory=Enrichment)
    source: str = "manual"
    collected_at: datetime = Field(default_factory=utcnow)
    notes: str = ""


class RedFlag(_Model):
    code: str
    severity: Literal["CRITICAL", "HIGH", "MEDIUM"]
    description: str
    evidence: str = ""


class POSEvaluation(_Model):
    final_score: float
    raw_score: float
    uncapped_score: float
    tier: str
    tier_code: Tier
    is_discarded: bool
    discard_reasons: list[RedFlag] = Field(default_factory=list)
    variables: dict[str, float]
    explanations: dict[str, list[str]] = Field(default_factory=dict)
    weights_applied: dict[str, float]
    multipliers_applied: dict[str, float]
    preset: str
    season: str
    recommendation: str


class ActionKit(_Model):
    language: str = "en"
    vibe_opportunity_summary: str
    loom_script_90s: str
    cold_email_subject: str
    cold_email: str
    whatsapp_opener: str
    vibecoding_prompt: str
    generated_by: str = "templates"


class LeadDossier(_Model):
    """The standardized output record shared by every surface (CLI, web, MCP, exports)."""

    schema_version: str = "1.0.0"
    id: str
    rank: int | None = None
    company: Company
    raw_signals: RawSignals
    enrichment: Enrichment
    source: str
    pos_evaluation: POSEvaluation
    action_kit: ActionKit | None = None


class Session(_Model):
    """A persisted scouting run: raw leads only, ready for unlimited instant re-scoring."""

    id: str
    niche: str = ""
    location: str = ""
    source: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    leads: list[Lead] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)

    def get_lead(self, lead_id: str) -> Lead | None:
        for lead in self.leads:
            if lead.id == lead_id or lead.id.removeprefix("lead_") == lead_id:
                return lead
        return None
