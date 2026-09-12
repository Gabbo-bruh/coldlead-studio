"""Local dashboard backend (FastAPI). Every rescoring request is pure math over the cached session."""

from __future__ import annotations

import time
from importlib import resources
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from coldlead import SCHEMA_VERSION, __version__
from coldlead.config import SEASONS, ConfigError, ScoringConfig, list_presets, resolve_config
from coldlead.export import EXTENSIONS, FORMATS, MEDIA_TYPES, render
from coldlead.models import Session
from coldlead.outreach.action_kit import generate_action_kit
from coldlead.providers import SOURCES
from coldlead.providers.osm import LocationNotFound, ProviderError
from coldlead.scoring import score_leads, tier_counts
from coldlead.settings import get_settings
from coldlead.storage import SessionNotFound, SessionStore
from coldlead.variables import VARIABLES


class ScoreRequest(BaseModel):
    session_id: str | None = None
    preset: str | None = None
    weights: dict[str, float] = Field(default_factory=dict)
    season: str | None = None
    thresholds: dict[str, float] = Field(default_factory=dict)
    discard_on_lockin: bool | None = None


class ScoutRequest(BaseModel):
    niche: str = Field(min_length=1, max_length=120)
    location: str = Field(default="", max_length=120)
    limit: int = Field(default=10, ge=1, le=60)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float = Field(default=5.0, ge=0.2, le=25)
    expand: bool = True
    source: str = "auto"
    audit: bool = True
    lang: str | None = None


class ExportRequest(ScoreRequest):
    format: str = "csv"
    with_kits: bool = False
    lang: str | None = None


def _summary(session: Session) -> dict[str, Any]:
    return {
        "id": session.id,
        "niche": session.niche,
        "location": session.location,
        "source": session.source,
        "created_at": session.created_at.isoformat(),
        "lead_count": len(session.leads),
        "notices": session.notices,
    }


def create_app(store: SessionStore | None = None) -> FastAPI:
    store = store or SessionStore()
    app = FastAPI(
        title="ColdLead Studio", version=__version__, docs_url="/api/docs", redoc_url=None
    )
    static = resources.files("coldlead.web").joinpath("static")
    app.mount("/static", StaticFiles(directory=str(static)), name="static")

    def load(session_id: str | None) -> Session:
        try:
            return store.load(session_id)
        except SessionNotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    def config_for(req: ScoreRequest) -> ScoringConfig:
        try:
            return resolve_config(
                preset=req.preset,
                weights=req.weights or None,
                season=req.season,
                thresholds=req.thresholds or None,
                discard_on_lockin=req.discard_on_lockin,
            )
        except ConfigError as exc:
            raise HTTPException(422, str(exc)) from exc

    def scored_payload(session: Session, config: ScoringConfig) -> dict[str, Any]:
        started = time.perf_counter()
        scored = score_leads(session.leads, config)
        elapsed = (time.perf_counter() - started) * 1000
        return {
            "session": _summary(session),
            "config": config.model_dump(),
            "counts": tier_counts(scored),
            "elapsed_ms": round(elapsed, 2),
            "leads": [item.to_dossier().model_dump(mode="json") for item in scored],
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return static.joinpath("index.html").read_text(encoding="utf-8")

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        settings = get_settings()
        try:
            default = resolve_config()
        except ConfigError:
            default = resolve_config(user_config={}, env={})
        return {
            "version": __version__,
            "schema_version": SCHEMA_VERSION,
            "variables": [spec.__dict__ for spec in VARIABLES],
            "presets": list_presets(),
            "default": default.model_dump(),
            "seasons": list(SEASONS),
            "sources": list(SOURCES),
            "formats": list(FORMATS),
            "language": settings.language,
            "llm": f"{settings.llm_provider}:{settings.llm_model}"
            if settings.llm_enabled
            else None,
            "live_discovery": "google" if settings.google_places_api_key else "osm",
        }

    @app.get("/api/sessions")
    def sessions() -> list[dict[str, Any]]:
        return [{**s.__dict__, "created_at": s.created_at.isoformat()} for s in store.list()]

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: str) -> dict[str, str]:
        try:
            store.delete(session_id)
        except SessionNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"deleted": session_id}

    @app.post("/api/score")
    def score(req: ScoreRequest) -> dict[str, Any]:
        return scored_payload(load(req.session_id), config_for(req))

    @app.post("/api/scout")
    def scout(req: ScoutRequest) -> dict[str, Any]:
        from coldlead.pipeline import scout as run_scout

        if req.source not in SOURCES:
            raise HTTPException(422, f"Unknown source '{req.source}'")
        near = (req.lat, req.lon) if req.lat is not None and req.lon is not None else None
        if not req.location.strip() and near is None:
            raise HTTPException(422, "Type a location or drop a pin on the map.")
        try:
            session = run_scout(
                req.niche,
                req.location.strip(),
                req.limit,
                near=near,
                radius_km=req.radius_km,
                expand=req.expand,
                source=req.source,
                audit=req.audit,
                lang=req.lang,
                store=store,
            )
        except LocationNotFound as exc:
            raise HTTPException(422, str(exc)) from exc
        except ProviderError as exc:
            raise HTTPException(502, str(exc)) from exc
        if not session.leads:
            raise HTTPException(404, "No leads found. " + " ".join(session.notices))
        return scored_payload(session, config_for(ScoreRequest()))

    @app.get("/api/geocode")
    def geocode_place(q: str) -> dict[str, Any]:
        """Centre the map on a typed place (same resolver as the OSM provider)."""
        import httpx

        from coldlead.providers.osm import geocode
        from coldlead.settings import USER_AGENT

        try:
            with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15) as client:
                scope = geocode(client, q, get_settings().country)
        except LocationNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"OpenStreetMap unreachable: {exc}") from exc
        lat, lon = scope.center or (0.0, 0.0)
        return {"lat": lat, "lon": lon, "name": scope.name, "label": scope.label}

    @app.get("/api/kit/{session_id}/{lead_id}")
    def kit(
        session_id: str, lead_id: str, lang: str | None = None, ai: bool = False
    ) -> dict[str, Any]:
        session = load(session_id)
        lead = session.get_lead(lead_id)
        if lead is None:
            raise HTTPException(404, f"Lead '{lead_id}' not found")
        settings = get_settings()
        return generate_action_kit(
            lead, lang or settings.language, ai=ai, settings=settings
        ).model_dump()

    @app.post("/api/export")
    def export(req: ExportRequest) -> Response:
        if req.format not in FORMATS:
            raise HTTPException(422, f"Unknown format '{req.format}'")
        session = load(req.session_id)
        config = config_for(req)
        scored = score_leads(session.leads, config)
        kits = None
        if req.with_kits:
            language = req.lang or get_settings().language
            kits = {
                i.lead.id: generate_action_kit(i.lead, language)
                for i in scored
                if not i.evaluation.is_discarded
            }
        body = render(
            req.format,
            scored,
            config,
            title=f"{session.niche} · {session.location}",
            kits=kits,
            meta={"session": _summary(session)},
        )
        filename = f"coldlead-{session.id}.{EXTENSIONS[req.format]}"
        return Response(
            content=body.encode("utf-8"),
            media_type=f"{MEDIA_TYPES[req.format]}; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app
