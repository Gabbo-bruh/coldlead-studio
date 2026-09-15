"""Capability report shared by ``coldlead doctor`` and the ``coldlead_doctor`` MCP tool.

It tells a human — or an agent planning its next step — what works right now: which extras are
installed, which optional keys are set (never their values), which discovery sources are usable
and how scoring is configured. Offline by default; ``network=True`` adds one polite request.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import asdict, dataclass

import httpx

from coldlead import __version__
from coldlead.config import ConfigError, coldlead_home, resolve_config
from coldlead.settings import HTTP_HEADERS, Settings, get_settings
from coldlead.storage import SessionStore

NETWORK_PROBE_URL = "https://nominatim.openstreetmap.org/status"


@dataclass(frozen=True)
class Check:
    key: str  # stable machine name, e.g. "google_places"
    label: str
    ok: bool
    detail: str


def network_reachable(client: httpx.Client | None = None) -> bool:
    """One lightweight request to OpenStreetMap's status endpoint."""
    owns = client is None
    client = client or httpx.Client(headers=HTTP_HEADERS, timeout=5.0)
    try:
        return client.get(NETWORK_PROBE_URL).status_code < 500
    except httpx.HTTPError:
        return False
    finally:
        if owns:
            client.close()


def run_checks(
    settings: Settings | None = None, *, network: bool = False, client: httpx.Client | None = None
) -> list[Check]:
    settings = settings or get_settings()
    checks = [
        Check("python", "Python", True, sys.version.split()[0]),
        Check("data_dir", "Data directory", True, str(coldlead_home())),
        Check(
            "web",
            "Dashboard (web extra)",
            importlib.util.find_spec("fastapi") is not None,
            'pip install "coldlead-studio[web]"',
        ),
        Check(
            "mcp",
            "MCP server (mcp extra)",
            importlib.util.find_spec("mcp") is not None,
            'pip install "coldlead-studio[mcp]"',
        ),
        Check(
            "google_places",
            "Google Places discovery",
            bool(settings.google_places_api_key),
            "GOOGLE_PLACES_API_KEY",
        ),
        Check("osm", "OpenStreetMap discovery", True, "free, no key (needs network)"),
        Check("demo", "Offline demo data", True, "always available, synthetic"),
        Check(
            "pagespeed",
            "PageSpeed Lighthouse",
            bool(settings.pagespeed_api_key),
            "PAGESPEED_API_KEY (or --pagespeed, rate-limited)",
        ),
        Check(
            "meta_ads",
            "Meta Ad Library",
            bool(settings.meta_ads_token),
            "META_AD_LIBRARY_ACCESS_TOKEN",
        ),
        Check(
            "llm",
            "LLM insights",
            settings.llm_enabled,
            f"{settings.llm_provider}:{settings.llm_model}"
            if settings.llm_enabled
            else "GEMINI / ANTHROPIC / OPENROUTER / OPENAI key, or COLDLEAD_LLM_PROVIDER=ollama",
        ),
        Check("language", "Outreach language", True, settings.language),
        Check(
            "country",
            "Target country",
            True,
            settings.country or "worldwide (COLDLEAD_COUNTRY unset)",
        ),
    ]
    try:
        resolved = resolve_config()
        checks.append(
            Check(
                "scoring",
                "Scoring config",
                True,
                f"preset={resolved.preset} season={resolved.season} ({' → '.join(resolved.sources)})",
            )
        )
    except ConfigError as exc:
        checks.append(Check("scoring", "Scoring config", False, str(exc)))
    if network:
        reachable = network_reachable(client)
        checks.append(
            Check(
                "network",
                "Network (OpenStreetMap)",
                reachable,
                "reachable" if reachable else "unreachable: use source=demo or check the proxy",
            )
        )
    return checks


def report(
    settings: Settings | None = None,
    *,
    network: bool = False,
    client: httpx.Client | None = None,
    store: SessionStore | None = None,
) -> dict:
    """JSON-ready capability report for agents. Never contains secret values."""
    settings = settings or get_settings()
    checks = run_checks(settings, network=network, client=client)
    active = {c.key: c.ok for c in checks}
    sources = [
        name
        for name, usable in (
            ("google", active["google_places"]),
            ("osm", active.get("network", True)),
            ("demo", True),
        )
        if usable
    ]
    return {
        "version": __version__,
        "checks": [asdict(c) for c in checks],
        "discovery_sources": sources,
        "language": settings.language,
        "country": settings.country,
        "cached_sessions": len((store or SessionStore()).list()),
    }
