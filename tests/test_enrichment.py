from __future__ import annotations

import httpx

from coldlead import pipeline
from coldlead.enrich import ads, insights
from coldlead.enrich.tech_audit import AuditResult
from coldlead.models import Company, Lead, RawSignals
from coldlead.settings import Settings
from tests.conftest import make_lead

LLM = Settings(llm_provider="gemini", llm_api_key="k", llm_model="m")


def test_heuristic_enrich_detects_litigious_replies():
    lead = make_lead(is_toxic_owner=None, sample_owner_replies=["Vergognati, ti querelo!"])
    enriched = insights.heuristic_enrich(lead, "it")
    assert enriched.raw_signals.is_toxic_owner is True
    assert enriched.raw_signals.owner_sentiment_tone == "Aggressive & Litigious"
    assert enriched.enrichment.enriched_by == "heuristic"
    assert lead.raw_signals.is_toxic_owner is None  # original untouched


def test_llm_enrich_applies_and_never_clears_toxicity(monkeypatch):
    monkeypatch.setattr(
        insights,
        "complete_json",
        lambda *a, **k: {
            "tone": "Friendly",
            "is_toxic": False,
            "psychological_lever": "Leva",
            "vibecoding_idea": "Idea 24h",
        },
    )
    toxic = make_lead(is_toxic_owner=True)
    enriched = insights.llm_enrich(toxic, LLM, "it")
    assert enriched.raw_signals.is_toxic_owner is True
    assert enriched.enrichment.vibe_opportunity_summary == "Idea 24h"
    assert enriched.enrichment.enriched_by == "llm:gemini"


def test_llm_enrich_falls_back(monkeypatch):
    monkeypatch.setattr(insights, "complete_json", lambda *a, **k: None)
    assert insights.llm_enrich(make_lead(), LLM).enrichment.enriched_by == "heuristic"
    assert insights.llm_enrich(make_lead(), Settings()).enrichment.enriched_by == "heuristic"


def test_enrich_leads_uses_llm_only_when_allowed(monkeypatch):
    monkeypatch.setattr(insights, "complete_json", lambda *a, **k: {"vibecoding_idea": "X"})
    leads = [make_lead()]
    assert pipeline.enrich_leads(leads, LLM, ai="off")[0].enrichment.enriched_by == "heuristic"
    assert pipeline.enrich_leads(leads, LLM, ai="auto")[0].enrichment.enriched_by == "llm:gemini"
    assert (
        pipeline.enrich_leads(leads, Settings(), ai="on")[0].enrichment.enriched_by == "heuristic"
    )


def test_meta_ad_library():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["ad_active_status"] == "ACTIVE"
        assert request.url.params["ad_reached_countries"] == '["IT"]'
        return httpx.Response(200, json={"data": [{"page_name": "Portofino Charter Deluxe"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert ads.has_active_meta_ads("Portofino Charter Deluxe S.r.l.", "t", client=client) is True
    empty = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"data": []}))
    )
    assert ads.has_active_meta_ads("Nobody", "t", client=empty) is False
    broken = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400)))
    assert ads.has_active_meta_ads("Nobody", "t", client=broken) is None


def test_audit_leads_skips_demo_and_merges(monkeypatch):
    calls = []

    def fake_audit(url, client, **kwargs):
        calls.append(url)
        return AuditResult(
            url=url,
            signals={
                "has_website": True,
                "website_url": url,
                "cms_stack": "Wix",
                "is_running_ads": None,
                "ads_evidence": [],
            },
            emails=["hi@x.example"],
            channels=["WhatsApp"],
        )

    monkeypatch.setattr(pipeline, "audit_website", fake_audit)
    monkeypatch.setattr(pipeline, "has_active_meta_ads", lambda *a, **k: True)
    real = Lead(
        id="lead_real",
        company=Company(name="Real", niche="Bar", city="Asti"),
        raw_signals=RawSignals(has_website=True, website_url="https://real.example"),
        source="osm",
    )
    demo = real.model_copy(update={"id": "lead_demo", "source": "demo"})
    progress = []
    out = pipeline.audit_leads(
        [real, demo], Settings(meta_ads_token="tok"), progress=lambda *a: progress.append(a)
    )
    assert calls == ["https://real.example"]
    assert out[0].raw_signals.cms_stack == "Wix"
    assert out[0].raw_signals.is_running_ads is True
    assert "Meta Ad Library: active ads" in out[0].raw_signals.ads_evidence
    assert out[0].company.email == "hi@x.example"
    assert out[1] is demo
    assert progress == [("audit", 1, 1)]
