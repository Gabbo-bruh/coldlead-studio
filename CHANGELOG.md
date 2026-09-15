# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.1.0] — 2026-09-16

Supersedes 1.0.0, which lacks the SSRF protection below and defaults to Italian: upgrade.

### Security
- **SSRF protection for website audits** (`coldlead audit`, `coldlead_audit`, `coldlead_score`,
  `scout`): only `http`/`https`; hosts resolving to loopback, private, link-local (cloud metadata),
  multicast, reserved or shared addresses are refused, also behind IPv4-mapped/6to4 IPv6; redirects
  are followed by hand and every hop is re-checked; the address is validated again at connection
  time (no DNS rebinding); responses are capped at 5 MB (`robots.txt` at 512 KB).

### Changed
- **English by default.** The outreach language defaults to `en` (also in the published schema,
  `ActionKit.language`). `COLDLEAD_COUNTRY` is now unset by default (no geographic bias); when set,
  it implies the language unless `COLDLEAD_LANG` says otherwise. **Upgrade note:** Italian users
  get the previous behaviour back with `COLDLEAD_COUNTRY=IT`.
- Every HTTP request sends a neutral `Accept-Language: *`, and multilingual sites are detected from
  their declared `hreflang` alternates first. Asking servers for Italian made multilingual sites
  look single-language and inflated `M_reach`.
- Meta Ad Library checks search every market unless a country is configured.
- Demo data follows the searched place: Miami (and any unknown place) gets American businesses
  (`LLC`/`Inc.`, `+1 … 555-01xx` numbers, English review replies); Italian places are unchanged.
- Mobile-number detection comes from the locale packs; an explicit "Mobile" channel counts too.
- English niches score like their Italian twins: "Lawyer" = "Avvocato", "Optician" = "Ottica",
  "Orthodontist" = "Ortodontista"… (sector keywords, ticket values and OpenStreetMap tags). A
  generic "shop" no longer outranks the sector it names ("coffee shop" is valued as coffee).
- Score explanations name legal forms in plain English ("sole trader"); the stored values of the
  schema are unchanged.
- The schema `$id` now resolves (GitHub raw URL) instead of pointing at an unregistered domain.
- `examples/my_leads.csv` uses English columns; the Italian aliases are shown in
  `examples/my_leads.it.csv`.
- Documentation: `PROJECT_VISION.md` moved to
  [`docs/design-notes/`](docs/design-notes/2026-09-initial-vision.it.md) as a historical note; new
  [`docs/architecture.md`](docs/architecture.md); *Core Invariants* in `CONTRIBUTING.md`.

### Added
- **Locale packs** (`src/coldlead/locales/`: `en-US`, `it-IT`) isolating names, legal forms, phone
  and address formats, review replies and local vocabulary; adding a country is one module.
- **MCP resources** (`coldlead://sessions`, `coldlead://sessions/{session_id}`,
  `…/leads/{lead_id}`, `coldlead://schema/pos-lead-dossier`), **MCP prompts** (`prospecting_run`,
  `audit_and_pitch`, `refine_ranking`) and the **`coldlead_doctor`** tool; `coldlead doctor --network`.
- `py.typed`: the package ships its type hints to library users.

## [1.0.0] — 2026-09-13

First public release: a ground-up rewrite of the original prototype around the
[project vision](docs/design-notes/2026-09-initial-vision.it.md).

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
- 📍 **Map pin search** (CLI `--near`, MCP coordinates, Leaflet map in the dashboard) and automatic
  widening up to 25 km when an area has fewer leads than requested.
- **Live scout progress** in the dashboard (background jobs with stages, counters and activity log)
  and in the CLI.
- Robust geocoding: only real places, home-country preference, resolved area always reported;
  Overpass errors are retried on other servers and never mistaken for empty results.
- Exports: JSON (schema v1.0.0), JSONL, compact LLM JSON, RFC 4180 CSV, Markdown report with kits.
- Published JSON Schema, 161 offline tests, CI on Linux/macOS/Windows × Python 3.10–3.13.
