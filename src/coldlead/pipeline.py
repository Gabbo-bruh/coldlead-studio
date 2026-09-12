"""Phase 1 of the architecture: collect raw signals once (discovery → audit → enrichment).

Slow, networked work lives here. Its only output is a :class:`Session` of raw leads, which the
pure scoring engine (phase 2) re-ranks instantly as many times as needed.
"""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from coldlead import knowledge
from coldlead.enrich.ads import has_active_meta_ads
from coldlead.enrich.insights import heuristic_enrich, llm_enrich
from coldlead.enrich.tech_audit import AuditResult, audit_website
from coldlead.models import Company, Lead, RawSignals, Session, make_lead_id
from coldlead.providers import DemoProvider, Provider
from coldlead.providers.google_places import GooglePlacesProvider
from coldlead.providers.osm import OSMProvider, ProviderError
from coldlead.settings import USER_AGENT, Settings, get_settings
from coldlead.storage import SessionStore, new_session_id

log = logging.getLogger(__name__)
Progress = Callable[[str, int, int], None]


def _noop(stage: str, done: int, total: int) -> None:
    return None


# ------------------------------------------------------------------------------------------
# Discovery
# ------------------------------------------------------------------------------------------


def discover(
    niche: str, location: str, limit: int, source: str, settings: Settings
) -> tuple[list[Lead], str, list[str]]:
    """Find leads, falling back gracefully. Returns ``(leads, source_used, notices)``."""
    notices: list[str] = []
    chain: list[tuple[str, Callable[[], Provider]]] = []
    if source in ("auto", "google"):
        if settings.google_places_api_key:
            chain.append(
                (
                    "google",
                    lambda: GooglePlacesProvider(
                        settings.google_places_api_key or "", language=settings.language
                    ),
                )
            )
        elif source == "google":
            raise ProviderError("GOOGLE_PLACES_API_KEY is not set")
    if source in ("auto", "osm"):
        chain.append(("osm", OSMProvider))
    if source in ("auto", "demo"):
        chain.append(("demo", DemoProvider))
    if not chain:
        raise ProviderError(f"Unknown source '{source}'")

    for name, factory in chain:
        try:
            leads = factory().search(niche, location, limit)
        except (ProviderError, httpx.HTTPError, ValueError) as exc:
            if source != "auto":
                raise ProviderError(str(exc)) from exc
            notices.append(f"{name} unavailable ({exc}); falling back")
            continue
        if leads:
            if name == "demo":
                notices.append(
                    "DEMO DATA: synthetic prospects for trying the tool. Use --source osm or set "
                    "GOOGLE_PLACES_API_KEY for real businesses."
                )
            return leads, name, notices
        notices.append(f"{name} returned no results for '{niche}' in '{location}'")
    return [], "none", notices


# ------------------------------------------------------------------------------------------
# Audit
# ------------------------------------------------------------------------------------------


def merge_audit(lead: Lead, result: AuditResult) -> Lead:
    """Fill signals from an audit without overwriting data a provider already supplied."""
    current = lead.raw_signals.model_dump()
    updates = {}
    for key, value in result.signals.items():
        if key not in current or value is None:
            continue
        if key == "ads_evidence":
            updates[key] = sorted(set(current[key]) | set(value))
        elif current[key] in (None, [], "") or key in ("has_website", "website_url"):
            updates[key] = value
    signals = lead.raw_signals.model_copy(update=updates)

    company = lead.company
    channels = list(dict.fromkeys([*company.contact_channels, *result.channels]))
    company = company.model_copy(
        update={
            "email": company.email or (result.emails[0] if result.emails else ""),
            "phone": company.phone or (result.phones[0] if result.phones else ""),
            "contact_channels": channels,
        }
    )
    notes = "; ".join(filter(None, [lead.notes, *result.notes]))
    return lead.model_copy(update={"raw_signals": signals, "company": company, "notes": notes})


def audit_leads(
    leads: list[Lead],
    settings: Settings,
    *,
    pagespeed: bool = False,
    respect_robots: bool = True,
    workers: int = 8,
    progress: Progress = _noop,
) -> list[Lead]:
    targets = [
        i for i, ld in enumerate(leads) if ld.raw_signals.website_url and ld.source != "demo"
    ]
    if not targets:
        return leads
    result = list(leads)
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "it,en;q=0.8"}
    with httpx.Client(
        headers=headers, timeout=settings.http_timeout, follow_redirects=True
    ) as client:

        def work(index: int) -> tuple[int, Lead]:
            lead = leads[index]
            audit = audit_website(
                lead.raw_signals.website_url or "",
                client,
                pagespeed=pagespeed,
                pagespeed_key=settings.pagespeed_api_key,
                respect_robots=respect_robots,
            )
            updated = merge_audit(lead, audit)
            if settings.meta_ads_token and updated.raw_signals.is_running_ads is not True:
                active = has_active_meta_ads(
                    updated.company.name, settings.meta_ads_token, settings.country
                )
                if active is not None:
                    evidence = [
                        *updated.raw_signals.ads_evidence,
                        *(["Meta Ad Library: active ads"] if active else []),
                    ]
                    updated = updated.model_copy(
                        update={
                            "raw_signals": updated.raw_signals.model_copy(
                                update={"is_running_ads": active, "ads_evidence": evidence}
                            )
                        }
                    )
            return index, updated

        done = 0
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            for index, lead in pool.map(work, targets):
                result[index] = lead
                done += 1
                progress("audit", done, len(targets))
    return result


def enrich_leads(
    leads: list[Lead],
    settings: Settings,
    *,
    ai: str = "auto",
    lang: str = "it",
    progress: Progress = _noop,
) -> list[Lead]:
    use_llm = settings.llm_enabled and ai in ("auto", "on")
    if ai == "on" and not settings.llm_enabled:
        log.warning("AI enrichment requested but no LLM key configured; using heuristics")
    if not use_llm:
        return [heuristic_enrich(lead, lang) for lead in leads]
    out: list[Lead] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for done, lead in enumerate(pool.map(lambda ld: llm_enrich(ld, settings, lang), leads), 1):
            out.append(lead)
            progress("enrich", done, len(leads))
    return out


# ------------------------------------------------------------------------------------------
# Entry points
# ------------------------------------------------------------------------------------------


def scout(
    niche: str,
    location: str,
    limit: int = 10,
    *,
    source: str = "auto",
    audit: bool = True,
    ai: str = "auto",
    pagespeed: bool = False,
    respect_robots: bool = True,
    lang: str | None = None,
    settings: Settings | None = None,
    store: SessionStore | None = None,
    progress: Progress = _noop,
) -> Session:
    """Discover, audit and enrich leads, then persist the raw session (never the scores)."""
    settings = settings or get_settings()
    lang = lang or settings.language
    limit = max(1, min(int(limit), 60))
    progress("discover", 0, 1)
    leads, used, notices = discover(niche, location, limit, source, settings)
    progress("discover", 1, 1)
    if audit:
        leads = audit_leads(
            leads, settings, pagespeed=pagespeed, respect_robots=respect_robots, progress=progress
        )
    leads = enrich_leads(leads, settings, ai=ai, lang=lang, progress=progress)
    if used == "osm":
        notices.append("Business data © OpenStreetMap contributors (ODbL).")
    session = Session(
        id=new_session_id(niche, location),
        niche=niche,
        location=location,
        source=used,
        leads=leads,
        notices=notices,
    )
    (store or SessionStore()).save(session)
    return session


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "company", "azienda", "ragione sociale", "business", "nome"),
    "website_url": ("website", "website_url", "url", "sito", "sito web", "site"),
    "niche": ("niche", "sector", "settore", "categoria", "category", "industry"),
    "city": ("city", "città", "citta", "location", "comune", "town"),
    "phone": ("phone", "telefono", "tel", "cellulare", "mobile"),
    "email": ("email", "e-mail", "mail"),
    "address": ("address", "indirizzo"),
    "vat_number": ("vat", "vat_number", "piva", "p.iva", "partita iva"),
    "direct_contact_person": ("contact", "referente", "owner", "titolare", "direct_contact_person"),
}


def _flat_to_lead(row: dict, niche: str, city: str) -> Lead | None:
    lowered = {str(k).strip().lower(): v for k, v in row.items() if k is not None}

    def pick(field: str) -> str:
        for alias in FIELD_ALIASES[field]:
            value = lowered.get(alias)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    name = pick("name")
    if not name:
        return None
    website = pick("website_url")
    signal_fields = set(RawSignals.model_fields)
    extra = {k: v for k, v in lowered.items() if k in signal_fields and v not in (None, "")}
    for key, value in list(extra.items()):
        if isinstance(value, str) and value.lower() in ("true", "false", "yes", "no", "si", "sì"):
            extra[key] = value.lower() in ("true", "yes", "si", "sì")
    signals = RawSignals.model_validate(
        {**extra, "has_website": bool(website), "website_url": website or None}
    )
    lead_niche, lead_city = pick("niche") or niche, pick("city") or city
    return Lead(
        id=make_lead_id("import", name, lead_city),
        company=Company(
            name=name,
            niche=lead_niche,
            city=lead_city,
            address=pick("address"),
            phone=pick("phone"),
            email=pick("email"),
            vat_number=pick("vat_number"),
            legal_form=knowledge.parse_legal_form(name),
            direct_contact_person=pick("direct_contact_person"),
        ),
        raw_signals=signals,
        source="import",
    )


def read_leads_file(path: Path, niche: str = "", city: str = "") -> list[Lead]:
    """Read leads from CSV (any common column names, IT/EN) or JSON (dossiers or flat rows)."""
    text = path.read_text(encoding="utf-8-sig")
    rows: Iterable[dict]
    if path.suffix.lower() in (".json", ".jsonl"):
        if path.suffix.lower() == ".jsonl":
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            data = json.loads(text)
            rows = data.get("leads", data) if isinstance(data, dict) else data
    else:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t") if text.strip() else csv.excel
        rows = list(csv.DictReader(text.splitlines(), dialect=dialect))
    leads: list[Lead] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if "company" in row and isinstance(row["company"], dict):
            lead = Lead.model_validate(
                {
                    **row,
                    "id": row.get("id")
                    or make_lead_id(
                        "import", row["company"].get("name", ""), row["company"].get("city", "")
                    ),
                }
            )
            lead = lead.model_copy(update={"source": row.get("source", "import")})
        else:
            lead = _flat_to_lead(row, niche, city)
        if lead:
            leads.append(lead)
    return leads


def import_leads(
    path: Path,
    *,
    niche: str = "",
    city: str = "",
    audit: bool = True,
    ai: str = "auto",
    pagespeed: bool = False,
    lang: str | None = None,
    settings: Settings | None = None,
    store: SessionStore | None = None,
    progress: Progress = _noop,
) -> Session:
    settings = settings or get_settings()
    lang = lang or settings.language
    leads = read_leads_file(path, niche, city)
    if audit:
        leads = audit_leads(leads, settings, pagespeed=pagespeed, progress=progress)
    leads = enrich_leads(leads, settings, ai=ai, lang=lang, progress=progress)
    session = Session(
        id=new_session_id("import", path.stem),
        niche=niche or "imported",
        location=city,
        source="import",
        leads=leads,
        notices=[f"Imported {len(leads)} leads from {path.name}"],
    )
    (store or SessionStore()).save(session)
    return session


def single_lead(
    name: str,
    niche: str,
    city: str,
    website: str | None = None,
    *,
    audit: bool = True,
    settings: Settings | None = None,
    lang: str = "it",
    **signals: object,
) -> Lead:
    """Build (and optionally audit) one lead from minimal facts — used by ``coldlead_score``."""
    settings = settings or get_settings()
    known = {k: v for k, v in signals.items() if k in RawSignals.model_fields and v is not None}
    lead = Lead(
        id=make_lead_id("manual", name, city),
        company=Company(
            name=name, niche=niche, city=city, legal_form=knowledge.parse_legal_form(name)
        ),
        raw_signals=RawSignals.model_validate(
            {**known, "has_website": bool(website), "website_url": website}
        ),
        source="manual",
    )
    if website and audit:
        lead = audit_leads([lead], settings)[0]
    return heuristic_enrich(lead, lang)
