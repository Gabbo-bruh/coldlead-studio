"""Rich terminal renderers for the CLI."""

from __future__ import annotations

from collections.abc import Sequence

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from coldlead.config import ScoringConfig
from coldlead.enrich.tech_audit import AuditResult
from coldlead.models import ActionKit, Tier
from coldlead.scoring import ScoredLead, tier_counts
from coldlead.storage import SessionSummary
from coldlead.variables import VARIABLES

TIER_STYLE = {
    Tier.HOT: "bold red",
    Tier.WARM: "bold yellow",
    Tier.COLD: "cyan",
    Tier.RED_FLAG: "dim",
}
TIER_BADGE = {
    Tier.HOT: "🔥 HOT",
    Tier.WARM: "⚡ WARM",
    Tier.COLD: "🧊 LOW",
    Tier.RED_FLAG: "🛑 FLAG",
}


def bar(value: float, maximum: float = 10.0, width: int = 10, style: str = "green") -> Text:
    filled = round(max(0.0, min(value, maximum)) / maximum * width)
    return Text("█" * filled, style=style) + Text("░" * (width - filled), style="grey30")


def _flag(value: bool | None, good: str, bad: str) -> str:
    if value is None:
        return "·"
    return good if value else bad


def signal_icons(item: ScoredLead) -> Text:
    s = item.lead.raw_signals
    parts = [
        ("🌐" if s.has_website else "✗site", "" if s.has_website else "bold red"),
        (_flag(s.mobile_friendly, "📱", "✗📱"), "red" if s.mobile_friendly is False else ""),
        (_flag(s.has_ssl, "🔒", "✗🔒"), "red" if s.has_ssl is False else ""),
        (
            _flag(s.has_multilingual, "🌍", "1-lang"),
            "yellow" if s.has_multilingual is False else "",
        ),
        (
            _flag(s.has_booking_system, "📅", "no-booking"),
            "yellow" if s.has_booking_system is False else "",
        ),
    ]
    if s.is_running_ads:
        parts.append(("📢ads", "magenta"))
    text = Text()
    for label, style in parts:
        if s.has_website or label.startswith("✗site"):
            text.append(label + " ", style=style)
    return text


def summary_line(scored: Sequence[ScoredLead], config: ScoringConfig) -> Text:
    c = tier_counts(scored)
    text = Text()
    text.append(f"{c['total']} leads  ", style="bold")
    text.append(f"🔥 {c['hot']} hot  ", style=TIER_STYLE[Tier.HOT])
    text.append(f"⚡ {c['warm']} warm  ", style=TIER_STYLE[Tier.WARM])
    text.append(f"🧊 {c['cold']} low  ", style=TIER_STYLE[Tier.COLD])
    text.append(f"🛑 {c['red_flag']} red flags", style="bold dim")
    text.append(f"   preset={config.preset} season={config.season}", style="grey50")
    return text


def leaderboard(
    scored: Sequence[ScoredLead],
    config: ScoringConfig,
    *,
    show_variables: bool = False,
    title: str = "",
) -> Table:
    table = Table(
        box=box.SIMPLE_HEAVY, title=title or None, title_style="bold", expand=True, pad_edge=False
    )
    table.add_column("#", justify="right", style="grey50", no_wrap=True)
    table.add_column("POS", justify="right", no_wrap=True)
    table.add_column("Tier", no_wrap=True)
    table.add_column("Company", ratio=3, overflow="fold")
    table.add_column("Signals", ratio=2, overflow="fold")
    if show_variables:
        for spec in VARIABLES:
            table.add_column(spec.key, justify="right", no_wrap=True)
    else:
        table.add_column("VibeCoding opportunity", ratio=4, overflow="fold")
    for item in scored:
        ev, c = item.evaluation, item.lead.company
        style = TIER_STYLE[ev.tier_code]
        company = Text(c.name, style="bold" if ev.tier_code in (Tier.HOT, Tier.WARM) else "")
        company.append(f"\n{c.city}", style="grey50")
        company.append(f"  {item.lead.id}", style="grey35")
        row: list = [
            str(item.rank),
            Text(f"{ev.final_score:5.1f}", style=style),
            Text(TIER_BADGE[ev.tier_code], style=style),
            company,
            signal_icons(item),
        ]
        if show_variables:
            row += [f"{ev.variables[spec.key]:.1f}" for spec in VARIABLES]
        else:
            opp = Text(item.lead.enrichment.vibe_opportunity_summary or "—")
            if ev.discard_reasons:
                opp.append("\n⚠ " + ", ".join(f.code for f in ev.discard_reasons), style="red")
            row.append(opp)
        table.add_row(*row)
    return table


def explain(item: ScoredLead) -> Panel:
    lead, ev = item.lead, item.evaluation
    table = Table(box=box.SIMPLE, expand=True, pad_edge=False)
    table.add_column("Variable", no_wrap=True)
    table.add_column("Value", no_wrap=True)
    table.add_column("w", justify="right", no_wrap=True)
    table.add_column("w·V", justify="right", no_wrap=True)
    table.add_column("Why", overflow="fold", ratio=1)
    total_w = sum(ev.weights_applied.values())
    for spec in VARIABLES:
        value, weight = ev.variables[spec.key], ev.weights_applied[spec.weight_key]
        table.add_row(
            Text(f"{spec.key}\n", style="bold") + Text(spec.short, style="grey50"),
            bar(value) + Text(f" {value:4.1f}"),
            f"{weight:g}",
            f"{value * weight:.1f}",
            "\n".join(ev.explanations.get(spec.key, [])),
        )
    m = ev.multipliers_applied
    formula = Text()
    formula.append(f"Σ(w·V)/Σw×10 = {ev.raw_score:.1f}", style="bold")
    formula.append(
        f"  × ads {m['m_ads']:g} × friction {m['m_friction']:g} × season {m['t_win']:g}"
        f" × lock-in {m['m_lockin']:g}  =  "
    )
    formula.append(f"{ev.uncapped_score:.2f}", style="bold")
    formula.append(
        f"  →  POS {ev.final_score:.1f}/100 (Σw={total_w:g})", style=TIER_STYLE[ev.tier_code]
    )
    parts: list = [table, formula, Text(f"\n{ev.recommendation}", style="italic")]
    for flag in ev.discard_reasons:
        parts.append(
            Text(
                f"⚠ {flag.code} [{flag.severity}] {flag.description} — {flag.evidence}", style="red"
            )
        )
    if lead.enrichment.vibe_opportunity_summary:
        parts.append(Text(f"💡 {lead.enrichment.vibe_opportunity_summary}", style="green"))
    return Panel(
        Group(*parts),
        title=f"#{item.rank} {lead.company.name} — {ev.tier}",
        subtitle=f"{lead.id} · {lead.source}",
        border_style=TIER_STYLE[ev.tier_code].replace("bold ", ""),
    )


def kit_panels(kit: ActionKit, channel: str = "all") -> list[Panel]:
    sections = {
        "loom": ("🎬 Loom script (90s)", kit.loom_script_90s),
        "email": (f"📧 Cold email — {kit.cold_email_subject}", kit.cold_email),
        "whatsapp": (f"💬 WhatsApp opener ({len(kit.whatsapp_opener)} chars)", kit.whatsapp_opener),
        "prompt": ("🤖 VibeCoding prompt", kit.vibecoding_prompt),
    }
    keys = list(sections) if channel == "all" else [channel]
    return [
        Panel(Text(sections[k][1]), title=sections[k][0], title_align="left", border_style="cyan")
        for k in keys
    ]


def presets_table(presets: dict[str, dict], active: str) -> Table:
    table = Table(box=box.SIMPLE_HEAVY, expand=True)
    table.add_column("Preset", no_wrap=True)
    for spec in VARIABLES:
        table.add_column(spec.weight_key, justify="right", no_wrap=True)
    table.add_column("Tiers", no_wrap=True)
    table.add_column("Description", overflow="fold", ratio=1)
    for name, preset in presets.items():
        label = Text(
            ("● " if name == active else "  ") + name, style="bold green" if name == active else ""
        )
        if preset.get("custom"):
            label.append(" (custom)", style="magenta")
        t = preset["thresholds"]
        table.add_row(
            label,
            *[f"{preset['weights'][s.weight_key]:g}" for s in VARIABLES],
            f"{t['tier_1_min']:g}/{t['tier_2_min']:g}",
            preset.get("description", ""),
        )
    return table


def sessions_table(sessions: Sequence[SessionSummary]) -> Table:
    table = Table(box=box.SIMPLE_HEAVY, expand=True)
    for col in ("Session", "Niche", "Location", "Source", "Leads", "Created (UTC)"):
        table.add_column(col, overflow="fold")
    for i, s in enumerate(sessions):
        table.add_row(
            Text(s.id, style="bold" if i == 0 else ""),
            s.niche,
            s.location,
            s.source,
            str(s.lead_count),
            f"{s.created_at:%Y-%m-%d %H:%M}",
        )
    return table


def audit_panel(result: AuditResult) -> Panel:
    table = Table(box=box.SIMPLE, show_header=False, expand=True)
    table.add_column("Signal", style="bold", no_wrap=True)
    table.add_column("Value", overflow="fold")
    for key, value in result.signals.items():
        if isinstance(value, list):
            value = ", ".join(value) or "—"
        table.add_row(key, "unknown" if value is None else str(value))
    for label, values in (
        ("emails", result.emails),
        ("phones", result.phones),
        ("channels", result.channels),
    ):
        if values:
            table.add_row(label, ", ".join(values))
    parts: list = [table, *[Text(f"• {n}", style="grey50") for n in result.notes]]
    return Panel(
        Group(*parts),
        title=f"🔎 Audit — {result.url}",
        border_style="green" if result.reachable else "red",
    )
