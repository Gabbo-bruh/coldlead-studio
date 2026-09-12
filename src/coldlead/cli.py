"""``coldlead`` — the universal CLI.

Scrape once with ``scout``; re-rank forever with ``rescore``, ``explain``, ``kit`` and ``export``.
"""

from __future__ import annotations

import contextlib
import json
import sys
import threading
import time
import webbrowser
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from coldlead import SCHEMA_VERSION, __version__
from coldlead.config import (
    SEASONS,
    ConfigError,
    ScoringConfig,
    coldlead_home,
    list_presets,
    load_user_config,
    parse_overrides,
    resolve_config,
    user_config_path,
)
from coldlead.export import EXTENSIONS, render
from coldlead.models import LeadDossier, Session
from coldlead.outreach.action_kit import generate_action_kit
from coldlead.providers.osm import ProviderError
from coldlead.scoring import ScoredLead, score_leads
from coldlead.settings import get_settings
from coldlead.storage import SessionNotFound, SessionStore

app = typer.Typer(
    name="coldlead",
    help="🎯 ColdLead Studio — scientific B2B lead scouting with the Precision Opportunity Score.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
    pretty_exceptions_show_locals=False,
)
console = Console()
err = Console(stderr=True)


class OutputFormat(str, Enum):
    table = "table"
    json = "json"
    jsonl = "jsonl"
    compact = "compact"
    csv = "csv"
    markdown = "markdown"


class Source(str, Enum):
    auto = "auto"
    demo = "demo"
    osm = "osm"
    google = "google"


class AIMode(str, Enum):
    auto = "auto"
    on = "on"
    off = "off"


class Channel(str, Enum):
    all = "all"
    loom = "loom"
    email = "email"
    whatsapp = "whatsapp"
    prompt = "prompt"


# ------------------------------------------------------------------------------------------
# Shared options
# ------------------------------------------------------------------------------------------

PresetOpt = Annotated[
    str | None, typer.Option("--preset", "-p", help="Weight preset (see `coldlead presets`).")
]
WeightOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--weight",
        "-w",
        help="Override one weight, e.g. [bold]-w w_A=3[/] or [bold]-w automation=3[/]. Repeatable.",
    ),
]
WeightsOpt = Annotated[
    str | None,
    typer.Option("--weights", help='Several overrides: \'{"w_A": 3}\' or "w_A=3,w_G=4".'),
]
SeasonOpt = Annotated[
    str | None, typer.Option("--season", "-s", help=f"Seasonal window: {', '.join(SEASONS)}.")
]
SessionOpt = Annotated[
    str | None, typer.Option("--session", help="Session id or prefix (default: latest).")
]
FormatOpt = Annotated[OutputFormat, typer.Option("--format", "-f", help="Output format.")]
OutOpt = Annotated[Path | None, typer.Option("--out", "-o", help="Write output to a file.")]
LangOpt = Annotated[str | None, typer.Option("--lang", "-l", help="Outreach language: it | en.")]


def _die(message: str, code: int = 1) -> typer.Exit:
    err.print(f"[bold red]✗[/] {escape(message)}")
    return typer.Exit(code)


def build_config(
    preset: str | None = None,
    weight: list[str] | None = None,
    weights: str | None = None,
    season: str | None = None,
    thresholds: dict[str, float] | None = None,
    discard_on_lockin: bool | None = None,
) -> ScoringConfig:
    overrides: dict[str, float] = {}
    for item in weight or []:
        overrides.update(parse_overrides(item))
    overrides.update(parse_overrides(weights))
    return resolve_config(
        preset=preset,
        weights=overrides,
        season=season,
        thresholds=thresholds,
        discard_on_lockin=discard_on_lockin,
    )


def _title(session: Session) -> str:
    return " · ".join(p for p in (session.niche, session.location) if p)


def _parse_pin(text: str | None) -> tuple[float, float] | None:
    if not text:
        return None
    try:
        lat, lon = (float(part) for part in text.replace(";", ",").split(","))
    except ValueError as exc:
        raise ProviderError(f'--near expects "LAT,LON", got {text!r}') from exc
    return lat, lon


def _load(store: SessionStore, session_id: str | None) -> Session:
    try:
        return store.load(session_id)
    except SessionNotFound as exc:
        raise _die(str(exc)) from exc


def _find(scored: list[ScoredLead], ref: str) -> ScoredLead:
    if ref.isdigit() and 1 <= int(ref) <= len(scored):
        return scored[int(ref) - 1]
    for item in scored:
        if item.lead.id == ref or item.lead.id.removeprefix("lead_") == ref.removeprefix("lead_"):
            return item
    matches = [i for i in scored if ref.lower() in i.lead.company.name.lower()]
    if len(matches) == 1:
        return matches[0]
    raise _die(f"Lead '{ref}' not found. Use a rank number, a lead id or part of the name.")


def _emit(text: str, out: Path | None) -> None:
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="")
        err.print(f"[green]✓[/] Saved to [bold]{out}[/]")
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _show(
    session: Session,
    config: ScoringConfig,
    fmt: OutputFormat,
    out: Path | None,
    top: int | None = None,
    variables: bool = False,
) -> list[ScoredLead]:
    started = time.perf_counter()
    scored = score_leads(session.leads, config)
    elapsed = (time.perf_counter() - started) * 1000
    shown = scored[:top] if top else scored
    if fmt is OutputFormat.table and not out:
        from coldlead import terminal

        for notice in session.notices:
            err.print(f"[yellow]ℹ[/] {notice}")
        console.print(
            terminal.leaderboard(
                shown,
                config,
                show_variables=variables,
                title=f"{escape(_title(session))}  [grey50]({session.id})[/]",
            )
        )
        console.print(terminal.summary_line(scored, config))
        console.print(
            f"[grey50]Scored {len(scored)} leads in {elapsed:.1f} ms · "
            "next: [bold]coldlead explain 1[/] · [bold]coldlead kit 1[/] · "
            "[bold]coldlead rescore -p automation_first[/][/]"
        )
    else:
        fmt_name = "markdown" if fmt is OutputFormat.table else fmt.value
        meta = {
            "session": {
                "id": session.id,
                "niche": session.niche,
                "location": session.location,
                "source": session.source,
            }
        }
        _emit(
            render(fmt_name, shown, config, title=_title(session), meta=meta),
            out,
        )
    return scored


def _progress_callback(progress: Progress):
    tasks: dict[str, int] = {}
    labels = {
        "discover": "Discovering businesses",
        "audit": "Auditing websites",
        "enrich": "AI insights",
    }

    def update(stage: str, done: int, total: int) -> None:
        if stage not in tasks:
            tasks[stage] = progress.add_task(labels.get(stage, stage), total=total)
        progress.update(tasks[stage], completed=done, total=total)

    return update


# ------------------------------------------------------------------------------------------
# Commands
# ------------------------------------------------------------------------------------------


@app.command()
def scout(
    niche: Annotated[
        str, typer.Argument(help='Business niche, e.g. "Charter nautico", "dentists".')
    ],
    location: Annotated[
        str, typer.Argument(help='City or area, e.g. "Portofino". Optional with --near.')
    ] = "",
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, max=60, help="Max leads.")] = 10,
    near: Annotated[
        str | None,
        typer.Option(
            "--near", help='Search around a map pin instead: "LAT,LON" (e.g. "44.35,9.15").'
        ),
    ] = None,
    radius: Annotated[
        float, typer.Option("--radius", "-r", min=0.2, max=25, help="Pin radius in km.")
    ] = 5.0,
    expand: Annotated[
        bool,
        typer.Option("--expand/--no-expand", help="Widen the area when fewer leads than --limit."),
    ] = True,
    source: Annotated[
        Source, typer.Option(help="auto = Google (if key) → OpenStreetMap → demo.")
    ] = Source.auto,
    preset: PresetOpt = None,
    weight: WeightOpt = None,
    weights: WeightsOpt = None,
    season: SeasonOpt = None,
    audit: Annotated[bool, typer.Option("--audit/--no-audit", help="Audit each website.")] = True,
    ai: Annotated[
        AIMode, typer.Option(help="LLM insights when a key is configured.")
    ] = AIMode.auto,
    pagespeed: Annotated[
        bool, typer.Option(help="Official Lighthouse scores via PageSpeed (slow).")
    ] = False,
    robots: Annotated[
        bool, typer.Option("--robots/--no-robots", help="Respect robots.txt.")
    ] = True,
    lang: LangOpt = None,
    fmt: FormatOpt = OutputFormat.table,
    out: OutOpt = None,
) -> None:
    """Find, audit and score businesses. Raw signals are cached for instant re-scoring."""
    from coldlead.pipeline import scout as run_scout

    try:
        pin = _parse_pin(near)
        config = build_config(preset, weight, weights, season)
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=err,
            transient=True,
        ) as progress:
            session = run_scout(
                niche,
                location,
                limit,
                near=pin,
                radius_km=radius,
                expand=expand,
                source=source.value,
                audit=audit,
                ai=ai.value,
                pagespeed=pagespeed,
                respect_robots=robots,
                lang=lang,
                progress=_progress_callback(progress),
            )
    except (ConfigError, ProviderError) as exc:
        raise _die(str(exc)) from exc
    if not session.leads:
        for notice in session.notices:
            err.print(f"[yellow]ℹ[/] {notice}")
        raise _die("No leads found. Try a broader niche, another city or --source demo.")
    _show(session, config, fmt, out)


@app.command()
def rescore(
    session_id: SessionOpt = None,
    preset: PresetOpt = None,
    weight: WeightOpt = None,
    weights: WeightsOpt = None,
    season: SeasonOpt = None,
    tier1: Annotated[float | None, typer.Option("--tier1", help="Hot threshold.")] = None,
    tier2: Annotated[float | None, typer.Option("--tier2", help="Warm threshold.")] = None,
    discard_lockin: Annotated[
        bool | None,
        typer.Option("--discard-lockin/--keep-lockin", help="Treat agency lock-in as a discard."),
    ] = None,
    top: Annotated[int | None, typer.Option("--top", "-t", help="Show only the top N.")] = None,
    variables: Annotated[
        bool, typer.Option("--vars", help="Show the 8 variables instead of opportunities.")
    ] = False,
    fmt: FormatOpt = OutputFormat.table,
    out: OutOpt = None,
) -> None:
    """Re-rank cached leads instantly with different weights — no scraping."""
    thresholds = {k: v for k, v in (("tier_1_min", tier1), ("tier_2_min", tier2)) if v is not None}
    try:
        config = build_config(preset, weight, weights, season, thresholds or None, discard_lockin)
    except ConfigError as exc:
        raise _die(str(exc)) from exc
    _show(_load(SessionStore(), session_id), config, fmt, out, top, variables)


@app.command()
def explain(
    lead: Annotated[str, typer.Argument(help="Rank number, lead id or part of the company name.")],
    session_id: SessionOpt = None,
    preset: PresetOpt = None,
    weight: WeightOpt = None,
    weights: WeightsOpt = None,
    season: SeasonOpt = None,
) -> None:
    """Show why a lead got its score: every variable, weight, multiplier and reason."""
    from coldlead import terminal

    try:
        config = build_config(preset, weight, weights, season)
    except ConfigError as exc:
        raise _die(str(exc)) from exc
    scored = score_leads(_load(SessionStore(), session_id).leads, config)
    console.print(terminal.explain(_find(scored, lead)))


@app.command()
def kit(
    lead: Annotated[
        str, typer.Argument(help="Rank number, lead id or part of the company name.")
    ] = "1",
    session_id: SessionOpt = None,
    channel: Annotated[
        Channel, typer.Option("--channel", "-c", help="Only one piece of the kit.")
    ] = Channel.all,
    lang: LangOpt = None,
    ai: Annotated[
        bool, typer.Option("--ai", help="Let the configured LLM polish the copy.")
    ] = False,
    preset: PresetOpt = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the kit as JSON.")] = False,
    out: OutOpt = None,
) -> None:
    """Generate the outreach Action Kit: Loom script, cold email, WhatsApp, VibeCoding prompt."""
    from coldlead import terminal

    settings = get_settings()
    config = build_config(preset)
    item = _find(score_leads(_load(SessionStore(), session_id).leads, config), lead)
    action_kit = generate_action_kit(item.lead, lang or settings.language, ai=ai, settings=settings)
    if as_json or out:
        payload = (
            item.to_dossier(action_kit).model_dump_json(indent=2)
            if as_json
            else "\n\n".join(
                [
                    action_kit.loom_script_90s,
                    f"Subject: {action_kit.cold_email_subject}\n\n{action_kit.cold_email}",
                    action_kit.whatsapp_opener,
                    action_kit.vibecoding_prompt,
                ]
            )
        )
        _emit(payload, out)
        return
    if item.evaluation.is_discarded:
        err.print(
            f"[red]⚠ {item.lead.company.name} is red-flagged — {item.evaluation.recommendation}[/]"
        )
    console.rule(
        f"🚀 Action Kit · #{item.rank} {item.lead.company.name} · POS {item.evaluation.final_score}"
    )
    for panel in terminal.kit_panels(action_kit, channel.value):
        console.print(panel)


@app.command()
def export(
    fmt: Annotated[OutputFormat, typer.Option("--format", "-f")] = OutputFormat.csv,
    out: OutOpt = None,
    session_id: SessionOpt = None,
    preset: PresetOpt = None,
    weight: WeightOpt = None,
    weights: WeightsOpt = None,
    season: SeasonOpt = None,
    with_kits: Annotated[
        bool, typer.Option("--with-kits", help="Embed Action Kits (json/jsonl/markdown).")
    ] = False,
    lang: LangOpt = None,
) -> None:
    """Export the current ranking: csv (CRM), json/jsonl (schema v1.0.0), compact (LLM), markdown."""
    session = _load(SessionStore(), session_id)
    try:
        config = build_config(preset, weight, weights, season)
    except ConfigError as exc:
        raise _die(str(exc)) from exc
    scored = score_leads(session.leads, config)
    kits = None
    if with_kits:
        language = lang or get_settings().language
        kits = {
            i.lead.id: generate_action_kit(i.lead, language)
            for i in scored
            if not i.evaluation.is_discarded
        }
    fmt_name = "markdown" if fmt is OutputFormat.table else fmt.value
    if out and out.is_dir():
        out = out / f"coldlead-{session.id}.{EXTENSIONS[fmt_name]}"
    meta = {"session": {"id": session.id, "niche": session.niche, "location": session.location}}
    _emit(
        render(
            fmt_name,
            scored,
            config,
            title=_title(session),
            kits=kits,
            meta=meta,
        ),
        out,
    )


@app.command()
def audit(
    url: Annotated[str, typer.Argument(help="Website to audit.")],
    pagespeed: Annotated[
        bool, typer.Option(help="Also fetch official Lighthouse score (slow).")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Technical audit of a single website (stack, speed, mobile, SSL, booking, chat, ads, agency)."""
    from coldlead import terminal
    from coldlead.enrich.tech_audit import audit_website

    settings = get_settings()
    with err.status(f"Auditing {url}…"):
        result = audit_website(url, pagespeed=pagespeed, pagespeed_key=settings.pagespeed_api_key)
    if as_json:
        _emit(
            json.dumps(
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
            ),
            None,
        )
    else:
        console.print(terminal.audit_panel(result))


@app.command("import")
def import_cmd(
    file: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="CSV or JSON of your own leads.")
    ],
    niche: Annotated[str, typer.Option(help="Default niche for rows without one.")] = "",
    city: Annotated[str, typer.Option(help="Default city for rows without one.")] = "",
    audit_sites: Annotated[bool, typer.Option("--audit/--no-audit")] = True,
    ai: Annotated[AIMode, typer.Option()] = AIMode.auto,
    preset: PresetOpt = None,
) -> None:
    """Import your own lead list (CSV/JSON, IT or EN headers), audit it and score it."""
    from coldlead.pipeline import import_leads

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=err,
        transient=True,
    ) as progress:
        session = import_leads(
            file,
            niche=niche,
            city=city,
            audit=audit_sites,
            ai=ai.value,
            progress=_progress_callback(progress),
        )
    if not session.leads:
        raise _die("No valid rows found (a 'name' / 'azienda' column is required).")
    _show(session, build_config(preset), OutputFormat.table, None)


@app.command()
def sessions(
    delete: Annotated[str | None, typer.Option("--delete", help="Delete a session by id.")] = None,
) -> None:
    """List cached scouting sessions (newest first)."""
    from coldlead import terminal

    store = SessionStore()
    if delete:
        try:
            store.delete(delete)
        except SessionNotFound as exc:
            raise _die(str(exc)) from exc
        err.print(f"[green]✓[/] Deleted {delete}")
        return
    summaries = store.list()
    if not summaries:
        err.print(
            'No sessions yet. Try: [bold]coldlead scout "Charter nautico" Portofino --source demo[/]'
        )
        return
    console.print(terminal.sessions_table(summaries))
    console.print(f"[grey50]Stored in {store.root}[/]")


@app.command()
def presets() -> None:
    """List weight presets (factory + your custom ones)."""
    from coldlead import terminal

    try:
        active = resolve_config().preset
    except ConfigError:
        active = "default_vibe_coding"
    console.print(terminal.presets_table(list_presets(), active))
    console.print(
        f"[grey50]Add custom presets in {user_config_path()} — run `coldlead config --init`.[/]"
    )


CONFIG_TEMPLATE = {
    "default_preset": "default_vibe_coding",
    "season": "auto",
    "discard_on_lockin": False,
    "weights": {},
    "presets": {
        "my_luxury_automation": {
            "extends": "high_ticket_luxury",
            "description": "Luxury targets, but automation counts double",
            "weights": {"w_A": 2.0},
        }
    },
}


@app.command()
def config(
    init: Annotated[
        bool, typer.Option("--init", help="Create a commented starter config file.")
    ] = False,
    path: Annotated[bool, typer.Option("--path", help="Only print the config file path.")] = False,
) -> None:
    """Show the resolved configuration and where every layer comes from."""
    target = user_config_path()
    if path:
        console.print(str(target))
        return
    if init:
        if target.exists():
            raise _die(f"{target} already exists — edit it directly.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(CONFIG_TEMPLATE, indent=2), encoding="utf-8")
        err.print(f"[green]✓[/] Created {target}")
    try:
        resolved = resolve_config()
        user = load_user_config()
    except ConfigError as exc:
        raise _die(str(exc)) from exc
    console.print_json(
        data={
            "resolved": resolved.model_dump(),
            "user_config_file": str(target),
            "user_config": user,
        }
    )


@app.command()
def web(
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port.")] = 8000,
    browser: Annotated[
        bool, typer.Option("--browser/--no-browser", help="Open the browser.")
    ] = True,
) -> None:
    """Launch the local dashboard (live weight sliders, radar charts, Action Kits)."""
    try:
        import uvicorn

        from coldlead.web.app import create_app
    except ImportError as exc:
        raise _die(
            'The dashboard needs extra packages: pip install "coldlead-studio[web]"'
        ) from exc
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}"
    if browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    err.print(f"🚀 ColdLead Studio dashboard on [bold]{url}[/] (Ctrl+C to stop)")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


@app.command()
def mcp(
    transport: Annotated[
        str, typer.Option(help="stdio (Claude/Cursor/AGY) or streamable-http.")
    ] = "stdio",
    port: Annotated[int, typer.Option(help="Port for streamable-http.")] = 8765,
) -> None:
    """Run the Model Context Protocol server (stdio by default)."""
    try:
        from coldlead.mcp_server import build_server
    except ImportError as exc:
        raise _die(
            'The MCP server needs extra packages: pip install "coldlead-studio[mcp]"'
        ) from exc
    server = build_server()
    if transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", port=port)


@app.command()
def schema(out: OutOpt = None) -> None:
    """Print the JSON Schema of the POSLeadDossier (v1.0.0) output record."""
    data = LeadDossier.model_json_schema()
    data = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://coldlead.dev/schema/pos-lead-dossier/{SCHEMA_VERSION}.json",
        **data,
    }
    _emit(json.dumps(data, indent=2, ensure_ascii=False), out)


@app.command()
def doctor() -> None:
    """Check optional capabilities, API keys and paths."""
    import importlib.util

    settings = get_settings()

    def row(ok: bool, label: str, detail: str) -> None:
        console.print(
            f"{'[green]✓[/]' if ok else '[grey50]○[/]'} {label:<28} [grey50]{escape(detail)}[/]"
        )

    console.rule(f"ColdLead Studio {__version__}")
    row(True, "Python", sys.version.split()[0])
    row(True, "Data directory", str(coldlead_home()))
    row(
        importlib.util.find_spec("fastapi") is not None,
        "Dashboard (web extra)",
        'pip install "coldlead-studio[web]"',
    )
    row(
        importlib.util.find_spec("mcp") is not None,
        "MCP server (mcp extra)",
        'pip install "coldlead-studio[mcp]"',
    )
    row(bool(settings.google_places_api_key), "Google Places discovery", "GOOGLE_PLACES_API_KEY")
    row(True, "OpenStreetMap discovery", "free, no key (needs network)")
    row(
        bool(settings.pagespeed_api_key),
        "PageSpeed Lighthouse",
        "PAGESPEED_API_KEY (or --pagespeed, rate-limited)",
    )
    row(bool(settings.meta_ads_token), "Meta Ad Library", "META_AD_LIBRARY_ACCESS_TOKEN")
    row(
        settings.llm_enabled,
        "LLM insights",
        f"{settings.llm_provider}:{settings.llm_model}"
        if settings.llm_enabled
        else "GEMINI / ANTHROPIC / OPENROUTER / OPENAI key, or COLDLEAD_LLM_PROVIDER=ollama",
    )
    row(True, "Outreach language", settings.language)
    try:
        resolved = resolve_config()
        row(
            True,
            "Scoring config",
            f"preset={resolved.preset} season={resolved.season} ({' → '.join(resolved.sources)})",
        )
    except ConfigError as exc:
        row(False, "Scoring config", str(exc))


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"coldlead-studio {__version__} (schema {SCHEMA_VERSION})")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    """🎯 ColdLead Studio — scrape once, re-score forever."""


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # UTF-8 on legacy Windows consoles
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    app()


if __name__ == "__main__":
    main()
