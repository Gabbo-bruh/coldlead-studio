# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- 📍 Map pin search: `--near LAT,LON --radius KM` in the CLI, `latitude`/`longitude`/`radius_km`
  in MCP, and a Leaflet map (vendored, BSD-2) in the dashboard to drop a pin and pick a radius.
- Automatic widening (up to 25 km) when a search returns fewer leads than requested.

### Fixed
- Geocoding only accepts real places and prefers the configured country ("Tigullio" no longer
  resolves to a nightclub in Malta); Overpass timeouts are no longer read as empty results; live
  searches with no results never fall back to demo data.
- Dashboard cards no longer replay their entry animation on every re-rank.

## [1.0.0] — 2026-09-12

First public release: a ground-up rewrite of the original prototype around the
[project vision](PROJECT_VISION.md).

### Added
- Pure, explainable **Precision Opportunity Score** engine: 8 variables with human-readable reasons,
  ads / friction / seasonal / lock-in multipliers, red-flag discards, uncapped tie-breaking and
  competitive pressure computed from session peers.
- **Decoupled architecture**: raw signals cached as JSON sessions, instant re-scoring (~1 ms).
- **Cascading configuration**: factory presets → `~/.coldlead/config.json` (custom presets with
  `extends`) → environment variables → runtime overrides; weight aliases.
- **Discovery providers**: offline deterministic demo, OpenStreetMap (free), Google Places API (New),
  CSV/JSON import of your own lists (IT/EN headers).
- **Website auditor**: CMS/stack, estimated or Lighthouse performance, mobile, HTTPS fallback,
  multilingual, booking widgets, chat widgets, PDF menus, ad pixels, agency credits, contacts;
  respects robots.txt.
- Optional **LLM insights and copy polish** via Gemini, Anthropic, OpenRouter, OpenAI or Ollama.
- **Action Kit** in Italian and English: 90s Loom script, cold email, WhatsApp opener (< 300 chars),
  VibeCoding prototype prompt; signal-driven offer playbooks per sector.
- **Surfaces**: `coldlead` CLI (Typer + Rich), MCP server (stdio and streamable HTTP), agent skill for
  Claude Code and Antigravity, Claude Code plugin marketplace, local dashboard (FastAPI + vanilla JS).
- Exports: JSON (schema v1.0.0), JSONL, compact LLM JSON, RFC 4180 CSV, Markdown report with kits.
- Published JSON Schema, 148 offline tests, CI on Linux/macOS/Windows × Python 3.10–3.13.
