from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import jsonschema
import pytest

from coldlead.enrich import llm
from coldlead.export import CSV_FIELDS, render, to_compact, to_csv, to_json, to_markdown
from coldlead.models import LeadDossier
from coldlead.outreach import action_kit, playbooks
from coldlead.outreach.action_kit import generate_action_kit, template_kit
from coldlead.scoring import score_leads
from coldlead.settings import Settings

SCHEMA_FILE = Path(__file__).parent.parent / "schema" / "pos-lead-dossier.schema.json"


def test_csv_is_rfc4180_and_parses_back(leads, config):
    text = to_csv(score_leads(leads, config))
    assert "\r\n" in text
    rows = list(csv.DictReader(io.StringIO(text, newline="")))
    assert len(rows) == len(leads)
    assert list(rows[0]) == list(CSV_FIELDS)
    assert rows[0]["rank"] == "1"


def test_json_export_matches_published_schema(leads, config):
    payload = json.loads(to_json(score_leads(leads, config), config))
    assert payload["schema_version"] == "1.0.0"
    assert payload["summary"]["total"] == len(leads)
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    for dossier in payload["leads"]:
        jsonschema.validate(dossier, schema)
        assert set(dossier) >= {"schema_version", "id", "company", "raw_signals", "pos_evaluation"}


def test_committed_schema_is_up_to_date():
    committed = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    generated = LeadDossier.model_json_schema()
    assert committed["$defs"] == generated["$defs"], (
        "run: coldlead schema -o schema/pos-lead-dossier.schema.json"
    )
    assert committed["properties"] == generated["properties"]


def test_compact_has_no_nulls(leads, config):
    records = json.loads(to_compact(score_leads(leads, config)))
    assert all(None not in r.values() for r in records)
    assert records[0]["rank"] == 1


def test_markdown_report(leads, config):
    scored = score_leads(leads, config)
    kits = {scored[0].lead.id: template_kit(scored[0].lead)}
    md = to_markdown(scored, config, "Charter · Portofino", kits)
    assert md.startswith("# 🎯 ColdLead Report — Charter · Portofino")
    assert "## 🏆 Leaderboard" in md and "🚀 Action Kit" in md
    assert "⚠️ **TOXIC_OWNER**" in md


def test_render_rejects_unknown_format(leads, config):
    with pytest.raises(ValueError):
        render("xml", score_leads(leads, config), config)


@pytest.mark.parametrize("lang", ["it", "en"])
def test_action_kit_constraints(leads, lang):
    for lead in leads:
        kit = template_kit(lead, lang)
        assert len(kit.whatsapp_opener) <= action_kit.WHATSAPP_MAX_CHARS
        for stamp in ("[00:00–00:15]", "[00:15–00:45]", "[00:45–01:15]", "[01:15–01:30]"):
            assert stamp in kit.loom_script_90s
        assert lead.company.name in kit.cold_email_subject
        assert "Next.js" in kit.vibecoding_prompt
        assert kit.language == lang


def test_action_kit_languages_differ(leads):
    it, en = template_kit(leads[0], "it"), template_kit(leads[0], "en")
    assert "Ciao" in it.cold_email or "Buongiorno" in it.cold_email
    assert "Hi" in en.cold_email
    assert template_kit(leads[0], "fr").language == "en"  # unknown → English


def test_opportunity_is_signal_driven(leads):
    no_site = next(ld for ld in leads if not ld.raw_signals.has_website)
    assert playbooks.offers(no_site)[0].code == "landing_24h"
    modern = next(
        ld for ld in leads if ld.raw_signals.has_booking_system and ld.raw_signals.has_ai_chat
    )
    assert playbooks.offers(modern)[0].code == "ai_ops_agent"


def test_ai_polish_falls_back_and_applies(monkeypatch, leads):
    settings = Settings(llm_provider="gemini", llm_api_key="k", llm_model="m")
    monkeypatch.setattr(action_kit, "complete_json", lambda *a, **k: None)
    assert (
        generate_action_kit(leads[0], "it", ai=True, settings=settings).generated_by == "templates"
    )
    monkeypatch.setattr(
        action_kit,
        "complete_json",
        lambda *a, **k: {"cold_email": "Ciao!", "whatsapp_opener": "x" * 400},
    )
    kit = generate_action_kit(leads[0], "it", ai=True, settings=settings)
    assert kit.cold_email == "Ciao!"
    assert len(kit.whatsapp_opener) <= 300  # over-long AI output rejected
    assert kit.generated_by == "llm:gemini"


def test_extract_json():
    assert llm._extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm._extract_json('Sure! {"a": {"b": 2}} hope it helps') == {"a": {"b": 2}}
    assert llm._extract_json("no json here") is None


@pytest.mark.parametrize(
    ("provider", "base_url", "response", "host"),
    [
        (
            "gemini",
            None,
            {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]},
            "generativelanguage",
        ),
        (
            "anthropic",
            None,
            {"content": [{"type": "text", "text": '{"ok": true}'}]},
            "api.anthropic.com",
        ),
        (
            "openai",
            "https://api.openai.com/v1",
            {"choices": [{"message": {"content": '{"ok": true}'}}]},
            "api.openai.com",
        ),
    ],
)
def test_llm_providers(provider, base_url, response, host):
    import httpx

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["headers"] = dict(request.headers)
        return httpx.Response(200, json=response)

    settings = Settings(
        llm_provider=provider, llm_api_key="secret", llm_model="m", llm_base_url=base_url
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert llm.complete_json("hi", settings, client=client) == {"ok": True}
    assert host in seen["host"]
    assert "secret" in json.dumps(seen["headers"])


def test_llm_disabled_and_errors():
    import httpx

    assert llm.complete_json("hi", Settings()) is None
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    settings = Settings(llm_provider="anthropic", llm_api_key="k", llm_model="m")
    assert llm.complete_json("hi", settings, client=client) is None


def test_settings_autodetect(monkeypatch):
    from coldlead.settings import get_settings

    assert get_settings(load_env_files=False).llm_enabled is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    s = get_settings(load_env_files=False)
    assert (s.llm_provider, s.llm_model, s.llm_enabled) == ("anthropic", "claude-sonnet-5", True)
    monkeypatch.setenv("COLDLEAD_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("COLDLEAD_LLM_MODEL", "qwen3")
    s = get_settings(load_env_files=False)
    assert (s.llm_provider, s.llm_model, s.llm_base_url, s.llm_enabled) == (
        "ollama",
        "qwen3",
        "http://localhost:11434/v1",
        True,
    )


def test_dotenv_loader(tmp_path, monkeypatch):
    from coldlead.settings import get_settings

    (tmp_path / "work" / ".env").write_text(
        "GOOGLE_PLACES_API_KEY='abc'\n# comment\nexport COLDLEAD_LANG=en\n", encoding="utf-8"
    )
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    s = get_settings()
    assert s.google_places_api_key == "abc"
    assert s.language == "en"
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    monkeypatch.delenv("COLDLEAD_LANG", raising=False)
