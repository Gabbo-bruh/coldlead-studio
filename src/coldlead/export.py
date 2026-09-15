"""Standardized serializers. Every format is derived from :class:`LeadDossier` (schema v1.0.0)."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence

from coldlead import SCHEMA_VERSION, __version__
from coldlead.config import ScoringConfig
from coldlead.models import ActionKit, LeadDossier, Tier
from coldlead.scoring import ScoredLead, tier_counts
from coldlead.variables import VARIABLES

SCHEMA_ID = (
    "https://raw.githubusercontent.com/Gabbo-bruh/coldlead-studio/main/schema/"
    "pos-lead-dossier.schema.json"
)
FORMATS: tuple[str, ...] = ("json", "jsonl", "compact", "csv", "markdown")
EXTENSIONS = {"json": "json", "jsonl": "jsonl", "compact": "json", "csv": "csv", "markdown": "md"}
MEDIA_TYPES = {
    "json": "application/json",
    "jsonl": "application/x-ndjson",
    "compact": "application/json",
    "csv": "text/csv",
    "markdown": "text/markdown",
}
TIER_BADGES = {
    Tier.HOT: "🔥 Hot",
    Tier.WARM: "⚡ Warm",
    Tier.COLD: "🧊 Low",
    Tier.RED_FLAG: "🛑 Red flag",
}


def dossier_json_schema() -> dict:
    """The published JSON Schema of :class:`LeadDossier` (``coldlead schema``)."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,  # must resolve: JSON Schema validators may dereference it
        **LeadDossier.model_json_schema(),
    }


def dossiers(
    scored: Sequence[ScoredLead], kits: dict[str, ActionKit] | None = None
) -> list[LeadDossier]:
    kits = kits or {}
    return [item.to_dossier(kits.get(item.lead.id)) for item in scored]


def to_json(
    scored: Sequence[ScoredLead],
    config: ScoringConfig,
    kits: dict[str, ActionKit] | None = None,
    meta: dict | None = None,
) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generator": f"coldlead-studio {__version__}",
        "scoring": config.model_dump(
            include={"preset", "weights", "multipliers", "thresholds", "season"}
        ),
        "summary": tier_counts(scored),
        **(meta or {}),
        "leads": [d.model_dump(mode="json") for d in dossiers(scored, kits)],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def to_jsonl(scored: Sequence[ScoredLead], kits: dict[str, ActionKit] | None = None) -> str:
    return "".join(d.model_dump_json() + "\n" for d in dossiers(scored, kits))


def compact_record(item: ScoredLead) -> dict:
    lead, ev = item.lead, item.evaluation
    return {
        "rank": item.rank,
        "id": lead.id,
        "name": lead.company.name,
        "city": lead.company.city,
        "pos": ev.final_score,
        "tier": ev.tier_code.value,
        "phone": lead.company.phone or None,
        "email": lead.company.email or None,
        "website": lead.raw_signals.website_url,
        "opportunity": lead.enrichment.vibe_opportunity_summary,
        "red_flags": [f.code for f in ev.discard_reasons] or None,
    }


def to_compact(scored: Sequence[ScoredLead]) -> str:
    """Token-light JSON for LLM prompts: one line, no nulls."""
    records = [{k: v for k, v in compact_record(item).items() if v is not None} for item in scored]
    return json.dumps(records, ensure_ascii=False, separators=(",", ":"))


CSV_FIELDS = (
    "rank",
    "id",
    "name",
    "niche",
    "city",
    "pos_score",
    "raw_score",
    "tier",
    "is_discarded",
    "red_flags",
    "phone",
    "email",
    "website",
    "address",
    "legal_form",
    "contact_person",
    "contact_channels",
    "cms",
    "performance",
    "mobile_friendly",
    "ssl",
    "multilingual",
    "booking",
    "running_ads",
    "reviews",
    "rating",
    "owner_reply_rate",
    *[v.key for v in VARIABLES],
    "opportunity",
    "recommendation",
    "source",
)


def to_csv(scored: Sequence[ScoredLead]) -> str:
    """RFC 4180 CSV (CRLF line endings, quoted when needed) — imports cleanly into any CRM."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\r\n")
    writer.writeheader()
    for item in scored:
        lead, ev = item.lead, item.evaluation
        c, s = lead.company, lead.raw_signals
        writer.writerow(
            {
                "rank": item.rank,
                "id": lead.id,
                "name": c.name,
                "niche": c.niche,
                "city": c.city,
                "pos_score": ev.final_score,
                "raw_score": ev.raw_score,
                "tier": ev.tier_code.value,
                "is_discarded": ev.is_discarded,
                "red_flags": "|".join(f.code for f in ev.discard_reasons),
                "phone": c.phone,
                "email": c.email,
                "website": s.website_url or "",
                "address": c.address,
                "legal_form": c.legal_form.value,
                "contact_person": c.direct_contact_person,
                "contact_channels": "|".join(c.contact_channels),
                "cms": s.cms_stack or "",
                "performance": "" if s.lighthouse_performance is None else s.lighthouse_performance,
                "mobile_friendly": _b(s.mobile_friendly),
                "ssl": _b(s.has_ssl),
                "multilingual": _b(s.has_multilingual),
                "booking": _b(s.has_booking_system),
                "running_ads": _b(s.is_running_ads),
                "reviews": "" if s.reviews_count is None else s.reviews_count,
                "rating": "" if s.average_rating is None else s.average_rating,
                "owner_reply_rate": "" if s.owner_reply_rate is None else s.owner_reply_rate,
                **ev.variables,
                "opportunity": lead.enrichment.vibe_opportunity_summary,
                "recommendation": ev.recommendation,
                "source": lead.source,
            }
        )
    return buffer.getvalue()


def _b(value: bool | None) -> str:
    return "" if value is None else ("yes" if value else "no")


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def to_markdown(
    scored: Sequence[ScoredLead],
    config: ScoringConfig,
    title: str = "",
    kits: dict[str, ActionKit] | None = None,
) -> str:
    counts = tier_counts(scored)
    lines = [
        f"# 🎯 ColdLead Report{f' — {title}' if title else ''}",
        "",
        f"**Preset:** `{config.preset}` · **Season:** `{config.season}` · "
        f"**Leads:** {counts['total']} · 🔥 {counts['hot']} · ⚡ {counts['warm']} · "
        f"🧊 {counts['cold']} · 🛑 {counts['red_flag']}",
        "",
        "## 🏆 Leaderboard",
        "",
        "| # | Company | City | POS | Tier | Opportunity |",
        "|---:|---|---|---:|---|---|",
    ]
    for item in scored:
        ev, c = item.evaluation, item.lead.company
        lines.append(
            f"| {item.rank} | **{_md(c.name)}** | {_md(c.city)} | **{ev.final_score:.1f}** | "
            f"{TIER_BADGES[ev.tier_code]} | {_md(item.lead.enrichment.vibe_opportunity_summary)} |"
        )
    lines += ["", "## 📋 Dossiers", ""]
    header = " | ".join(v.key for v in VARIABLES)
    for item in scored:
        lead, ev = item.lead, item.evaluation
        c, s = lead.company, lead.raw_signals
        lines += [
            f"### {item.rank}. {c.name} — POS {ev.final_score:.1f} ({ev.tier})",
            "",
            f"- **Contacts:** {c.phone or '—'} · {c.email or '—'} · {', '.join(c.contact_channels) or '—'}",
            f"- **Website:** {s.website_url or 'none'} · stack: {s.cms_stack or 'unknown'} · "
            f"performance: {s.lighthouse_performance if s.lighthouse_performance is not None else 'n/a'}",
            f"- **Reputation:** {s.average_rating or 'n/a'}★ ({s.reviews_count or 0} reviews) · "
            f"owner tone: {s.owner_sentiment_tone or 'unknown'}",
            f"- **Opportunity:** {lead.enrichment.vibe_opportunity_summary}",
            f"- **Next step:** {ev.recommendation}",
            "",
            f"| {header} |",
            "|" + "---:|" * len(VARIABLES),
            "| " + " | ".join(f"{ev.variables[v.key]:.1f}" for v in VARIABLES) + " |",
            "",
        ]
        for flag in ev.discard_reasons:
            lines.append(
                f"> ⚠️ **{flag.code}** ({flag.severity}) — {flag.description} _{_md(flag.evidence)}_"
            )
        if ev.discard_reasons:
            lines.append("")
        kit = (kits or {}).get(lead.id)
        if kit:
            lines += [
                "<details><summary>🚀 Action Kit</summary>",
                "",
                "**Loom script (90s)**",
                "",
                "```text",
                kit.loom_script_90s,
                "```",
                "",
                f"**Cold email** — _{kit.cold_email_subject}_",
                "",
                "```text",
                kit.cold_email,
                "```",
                "",
                "**WhatsApp**",
                "",
                "```text",
                kit.whatsapp_opener,
                "```",
                "",
                "**VibeCoding prompt**",
                "",
                "```text",
                kit.vibecoding_prompt,
                "```",
                "",
                "</details>",
                "",
            ]
    lines.append(f"_Generated by coldlead-studio {__version__} · schema {SCHEMA_VERSION}_")
    return "\n".join(lines)


def render(
    fmt: str,
    scored: Sequence[ScoredLead],
    config: ScoringConfig,
    *,
    title: str = "",
    kits: dict[str, ActionKit] | None = None,
    meta: dict | None = None,
) -> str:
    fmt = fmt.lower()
    if fmt == "json":
        return to_json(scored, config, kits, meta)
    if fmt == "jsonl":
        return to_jsonl(scored, kits)
    if fmt == "compact":
        return to_compact(scored)
    if fmt == "csv":
        return to_csv(scored)
    if fmt in ("markdown", "md"):
        return to_markdown(scored, config, title, kits)
    raise ValueError(f"Unknown format '{fmt}'. Choose from: {', '.join(FORMATS)}")
