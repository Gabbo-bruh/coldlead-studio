"""Model Context Protocol server: ColdLead Studio as tools for Claude, Cursor, Antigravity, Windsurf…

Run with ``coldlead mcp`` (stdio) or ``coldlead mcp --transport streamable-http``.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import webbrowser
from typing import Any, Literal

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from coldlead import __version__
from coldlead.config import ConfigError, list_presets, parse_overrides, resolve_config
from coldlead.enrich.tech_audit import audit_website
from coldlead.export import render
from coldlead.outreach.action_kit import generate_action_kit
from coldlead.pipeline import scout, single_lead
from coldlead.providers.osm import ProviderError
from coldlead.scoring import score_lead, score_leads
from coldlead.settings import get_settings
from coldlead.storage import SessionNotFound, SessionStore

Format = Literal["markdown", "compact", "json", "csv"]
Season = Literal["auto", "autumn_winter", "spring", "summer_peak", "year_round"]

INSTRUCTIONS = """\
ColdLead Studio scores local businesses as prospects for fast AI/web micro-products (VibeCoding)
with the Precision Opportunity Score (POS, 0-100) built from 8 variables and context multipliers.

Workflow: coldlead_search once (slow: discovery + website audits, cached as a session), then
coldlead_rescore as often as you like (instant, no scraping) to try presets or custom weights,
coldlead_explain to justify a score, and coldlead_generate_pitch for the outreach Action Kit.
Weights: w_G digital gap, w_T ticket value, w_F financial strength, w_P competition,
w_I foreign reach, w_D owner access, w_C brand care, w_A automation potential (each 0-10).
Leads with source "demo" are synthetic examples, never present them as real businesses.
"""


def _weights(custom_weights: dict[str, float] | str | None) -> dict[str, float]:
    if isinstance(custom_weights, str):
        return parse_overrides(custom_weights)
    return dict(custom_weights or {})


def _config(preset: str | None, custom_weights: Any, season: str | None):
    try:
        return resolve_config(preset=preset, weights=_weights(custom_weights), season=season)
    except ConfigError as exc:
        raise ValueError(str(exc)) from exc


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def build_server(store: SessionStore | None = None) -> MCPServer:
    store = store or SessionStore()
    server = MCPServer("coldlead-studio", version=__version__, instructions=INSTRUCTIONS)
    read_only = ToolAnnotations(read_only_hint=True, open_world_hint=False)

    @server.tool(annotations=ToolAnnotations(open_world_hint=True))
    def coldlead_search(
        niche: str,
        location: str = "",
        limit: int = 10,
        preset: str | None = None,
        source: Literal["auto", "demo", "osm", "google"] = "auto",
        audit: bool = True,
        format: Format = "markdown",
        latitude: float | None = None,
        longitude: float | None = None,
        radius_km: float = 5.0,
        expand: bool = True,
    ) -> str:
        """Find businesses in a niche and location, audit their websites, score and rank them.

        Search a named place (location) or a map pin (latitude + longitude, radius_km up to 25).
        With expand, too few results widen the area automatically.
        Results are cached as a session so they can be re-scored instantly with coldlead_rescore.
        source: auto (Google if key → OpenStreetMap → offline demo), demo, osm or google.
        """
        near = (latitude, longitude) if latitude is not None and longitude is not None else None
        try:
            session = scout(
                niche,
                location,
                limit,
                near=near,
                radius_km=radius_km,
                expand=expand,
                source=source,
                audit=audit,
                store=store,
            )
        except ProviderError as exc:
            return f"Discovery failed: {exc}"
        if not session.leads:
            return "No leads found. " + " ".join(session.notices)
        config = _config(preset, None, None)
        scored = score_leads(session.leads, config)
        header = f"Session `{session.id}` · source: {session.source}\n" + "".join(
            f"> {n}\n" for n in session.notices
        )
        return header + "\n" + render(format, scored, config, title=f"{niche} · {session.location}")

    @server.tool(annotations=read_only)
    def coldlead_rescore(
        custom_weights: dict[str, float] | None = None,
        preset: str | None = None,
        season: Season | None = None,
        session_id: str | None = None,
        top: int | None = None,
        format: Format = "markdown",
    ) -> str:
        """Instantly re-rank a cached session with another preset and/or custom weights. No scraping.

        custom_weights example: {"w_A": 4, "w_G": 1.5} (aliases like "automation" also work).
        session_id defaults to the latest session.
        """
        try:
            session = store.load(session_id)
        except SessionNotFound as exc:
            return str(exc)
        config = _config(preset, custom_weights, season)
        started = time.perf_counter()
        scored = score_leads(session.leads, config)
        elapsed = (time.perf_counter() - started) * 1000
        body = render(
            format,
            scored[:top] if top else scored,
            config,
            title=f"{session.niche} · {session.location}",
        )
        return f"Re-scored {len(scored)} leads of `{session.id}` in {elapsed:.1f} ms.\n\n{body}"

    @server.tool(annotations=read_only)
    def coldlead_explain(
        lead: str,
        session_id: str | None = None,
        preset: str | None = None,
        custom_weights: dict[str, float] | None = None,
    ) -> str:
        """Explain a lead's score: each variable's value, weight, contribution and reasons.

        lead: rank number (e.g. "1"), lead id or part of the company name.
        """
        try:
            session = store.load(session_id)
        except SessionNotFound as exc:
            return str(exc)
        scored = score_leads(session.leads, _config(preset, custom_weights, None))
        item = next(
            (
                i
                for i in scored
                if lead == str(i.rank)
                or lead == i.lead.id
                or lead.lower() in i.lead.company.name.lower()
            ),
            None,
        )
        if item is None:
            return f"Lead '{lead}' not found in session {session.id}."
        ev = item.evaluation
        lines = [f"#{item.rank} {item.lead.company.name} — POS {ev.final_score} ({ev.tier})", ""]
        for key, value in ev.variables.items():
            lines.append(f"- {key} = {value}: " + "; ".join(ev.explanations.get(key, [])))
        m = ev.multipliers_applied
        lines += [
            "",
            f"raw {ev.raw_score} × ads {m['m_ads']} × friction {m['m_friction']} × season "
            f"{m['t_win']} × lock-in {m['m_lockin']} = {ev.uncapped_score} → {ev.final_score}",
        ]
        lines += [
            f"⚠ {f.code} ({f.severity}): {f.description} — {f.evidence}" for f in ev.discard_reasons
        ]
        lines += ["", ev.recommendation]
        return "\n".join(lines)

    @server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
    def coldlead_audit(url: str, pagespeed: bool = False) -> str:
        """Technical audit of one website: stack/CMS, estimated or Lighthouse performance, mobile,
        HTTPS, multilingual, booking, chat, PDF menus, ad pixels, agency credits, contacts."""
        settings = get_settings()
        result = audit_website(url, pagespeed=pagespeed, pagespeed_key=settings.pagespeed_api_key)
        return json.dumps(
            {
                "url": result.url,
                "reachable": result.reachable,
                "signals": result.signals,
                "emails": result.emails,
                "phones": result.phones,
                "channels": result.channels,
                "notes": result.notes,
            },
            indent=2,
            ensure_ascii=False,
        )

    @server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
    def coldlead_score(
        company_name: str,
        niche: str,
        city: str,
        website_url: str | None = None,
        is_running_ads: bool | None = None,
        owner_reply_rate: float | None = None,
        custom_weights: dict[str, float] | None = None,
        preset: str | None = None,
        season: Season | None = None,
    ) -> str:
        """Score a single company on the fly (audits the website if given). Returns the full POS
        evaluation with variables, explanations and recommendation as JSON."""
        lead = single_lead(
            company_name,
            niche,
            city,
            website_url,
            is_running_ads=is_running_ads,
            owner_reply_rate=owner_reply_rate,
        )
        evaluation = score_lead(lead, _config(preset, custom_weights, season))
        return json.dumps(
            {
                "company": lead.company.model_dump(mode="json"),
                "raw_signals": lead.raw_signals.model_dump(mode="json", exclude_none=True),
                "pos_evaluation": evaluation.model_dump(mode="json"),
                "vibe_opportunity": lead.enrichment.vibe_opportunity_summary,
            },
            indent=2,
            ensure_ascii=False,
        )

    @server.tool(annotations=read_only)
    def coldlead_generate_pitch(
        lead: str = "1",
        session_id: str | None = None,
        language: Literal["it", "en"] = "it",
        ai_polish: bool = False,
    ) -> str:
        """Generate the outreach Action Kit for a cached lead: 90s Loom script, cold email,
        WhatsApp opener (<300 chars) and a VibeCoding prompt to build the prototype.

        lead: rank number, lead id or part of the company name (default: the top lead).
        """
        try:
            session = store.load(session_id)
        except SessionNotFound as exc:
            return str(exc)
        scored = score_leads(session.leads, _config(None, None, None))
        item = next(
            (
                i
                for i in scored
                if lead == str(i.rank)
                or lead == i.lead.id
                or lead.lower() in i.lead.company.name.lower()
            ),
            None,
        )
        if item is None:
            return f"Lead '{lead}' not found in session {session.id}."
        kit = generate_action_kit(item.lead, language, ai=ai_polish, settings=get_settings())
        warning = (
            f"⚠ This lead is red-flagged: {item.evaluation.recommendation}\n\n"
            if item.evaluation.is_discarded
            else ""
        )
        return (
            f"{warning}# 🚀 Action Kit — {item.lead.company.name} (POS {item.evaluation.final_score})\n\n"
            f"**Opportunity:** {kit.vibe_opportunity_summary}\n\n"
            f"## 🎬 Loom script (90s)\n\n{kit.loom_script_90s}\n\n"
            f"## 📧 Cold email\n\n**Subject:** {kit.cold_email_subject}\n\n{kit.cold_email}\n\n"
            f"## 💬 WhatsApp ({len(kit.whatsapp_opener)} chars)\n\n{kit.whatsapp_opener}\n\n"
            f"## 🤖 VibeCoding prompt\n\n{kit.vibecoding_prompt}\n"
        )

    @server.tool(annotations=read_only)
    def coldlead_list(what: Literal["sessions", "presets"] = "sessions") -> str:
        """List cached scouting sessions or available weight presets."""
        if what == "presets":
            return json.dumps(
                {
                    k: {
                        "description": v.get("description"),
                        "weights": v["weights"],
                        "thresholds": v["thresholds"],
                    }
                    for k, v in list_presets().items()
                },
                indent=2,
            )
        return json.dumps(
            [{**s.__dict__, "created_at": s.created_at.isoformat()} for s in store.list()], indent=2
        )

    @server.tool(annotations=ToolAnnotations(open_world_hint=False))
    def coldlead_open_dashboard(port: int = 8000) -> str:
        """Start the local dashboard (live weight sliders, radar charts, Action Kits) and open the browser."""
        url = f"http://127.0.0.1:{port}"
        if not _port_open(port):
            subprocess.Popen(
                [sys.executable, "-m", "coldlead", "web", "--port", str(port), "--no-browser"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            for _ in range(30):
                if _port_open(port):
                    break
                time.sleep(0.2)
        webbrowser.open(url)
        return f"Dashboard running at {url}"

    return server


if __name__ == "__main__":
    build_server().run("stdio")
