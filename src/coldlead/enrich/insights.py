"""Qualitative enrichment: owner tone, toxicity, psychological lever, VibeCoding idea.

Heuristic by default; upgraded by an LLM when one is configured.
"""

from __future__ import annotations

import json

from coldlead.enrich.llm import complete_json
from coldlead.models import Enrichment, Lead
from coldlead.outreach import playbooks
from coldlead.red_flags import evaluate_red_flags
from coldlead.settings import Settings

SYSTEM = (
    "You are a B2B sales psychologist for a studio that builds AI micro-apps and fast websites "
    "in 24-48 hours (VibeCoding). Be concrete and evidence-based. Reply with one JSON object."
)


def heuristic_enrich(lead: Lead, lang: str = "en") -> Lead:
    signals = lead.raw_signals
    updates: dict = {}
    if signals.is_toxic_owner is None and any(
        f.code == "LITIGIOUS_OWNER" for f in evaluate_red_flags(lead)
    ):
        updates["is_toxic_owner"] = True
    new_signals = signals.model_copy(update=updates)
    probe = lead.model_copy(update={"raw_signals": new_signals})
    new_signals = new_signals.model_copy(
        update={"owner_sentiment_tone": playbooks.sentiment_tone(probe)}
    )
    enrichment = Enrichment(
        vibe_opportunity_summary=playbooks.opportunity_summary(probe, lang),
        psychological_lever=playbooks.psychological_lever(probe, lang),
        enriched_by="heuristic",
    )
    return lead.model_copy(update={"raw_signals": new_signals, "enrichment": enrichment})


def llm_enrich(lead: Lead, settings: Settings, lang: str = "en") -> Lead:
    base = heuristic_enrich(lead, lang)
    if not settings.llm_enabled:
        return base
    language = "Italian" if lang == "it" else "English"
    data = base.model_dump(mode="json", include={"company", "raw_signals"})
    prompt = (
        "Analyse this prospect for a VibeCoding studio.\n"
        f"Data: {json.dumps(data, ensure_ascii=False)}\n\n"
        "Return JSON with:\n"
        '- "tone": owner tone of voice in review replies, one of "Empathetic & Professional", '
        '"Friendly", "Defensive", "Aggressive & Litigious", "Ghost/Absent", "Unknown";\n'
        '- "is_toxic": true only if replies insult customers or threaten legal action;\n'
        f'- "psychological_lever": the single best persuasion lever, one sentence in {language};\n'
        f'- "vibecoding_idea": one specific micro-product buildable in 24-48h, one sentence in {language}.'
    )
    result = complete_json(prompt, settings, system=SYSTEM)
    if not result:
        return base
    signals = base.raw_signals.model_copy(
        update={
            "owner_sentiment_tone": str(
                result.get("tone") or base.raw_signals.owner_sentiment_tone
            ),
            # An LLM may raise a toxicity flag from evidence, but never clears one found by rules.
            "is_toxic_owner": bool(base.raw_signals.is_toxic_owner) or bool(result.get("is_toxic")),
        }
    )
    enrichment = Enrichment(
        vibe_opportunity_summary=str(
            result.get("vibecoding_idea") or base.enrichment.vibe_opportunity_summary
        ),
        psychological_lever=str(
            result.get("psychological_lever") or base.enrichment.psychological_lever
        ),
        enriched_by=f"llm:{settings.llm_provider}",
    )
    return base.model_copy(update={"raw_signals": signals, "enrichment": enrichment})
