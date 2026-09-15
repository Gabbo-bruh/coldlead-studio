# Contributing

Thanks for helping make ColdLead Studio better! 🎯

## Setup

```bash
git clone https://github.com/Gabbo-bruh/coldlead-studio && cd coldlead-studio
uv sync --all-extras
uv run pytest            # the whole suite is offline and runs in seconds
uv run ruff check . && uv run ruff format --check .
```

Start with [docs/architecture.md](docs/architecture.md): it maps every module and explains the
collect-once / score-forever split that the rules below protect.

## Core Invariants

These five rules are what make the product work. A change that breaks one of them will not be
merged, whoever — or whatever agent — wrote it.

1. **`score_lead()` stays pure and deterministic.** `score_lead` / `score_leads` in
   `src/coldlead/scoring.py`, every variable in `src/coldlead/variables.py` and
   `src/coldlead/red_flags.py` take leads plus a `ScoringConfig` and return a result: no network,
   no file or environment access, no clock, no randomness. Same input, same output, every time.
   Anything slow or impure belongs in `pipeline.py`, `providers/` or `enrich/`.
2. **The session cache persists raw signals — never scores.** `SessionStore`
   (`src/coldlead/storage.py`) saves `Session` objects made of `Company` + `RawSignals` +
   `Enrichment`. Never add a score, tier or rank to a cached model: derived data is recomputed.
3. **The output contract stays compatible.** Every surface emits `LeadDossier`
   (`src/coldlead/models.py`), published as `schema/pos-lead-dossier.schema.json`. Add optional
   fields only; never rename, remove or change the type of an existing one within a major version.
   Regenerate the schema with `uv run coldlead schema -o schema/pos-lead-dossier.schema.json`
   (a test fails when it is stale).
4. **Rescoring never touches the network.** `rescore`, `explain`, `export`, `kit` (without
   `--ai`), the dashboard's `/api/score` and the `coldlead_rescore` / `coldlead_explain` MCP tools
   must work on a laptop in airplane mode, from the cache alone. Only `scout`, `import`, `audit`,
   `coldlead_score` and explicit LLM polishing (`--ai`, `ai_polish`) may use the network.
5. **Demo data is safe and always labelled.** `providers/demo.py` output must stay deterministic
   and obviously fictitious: `source="demo"`, names ending in `(demo)`, reserved `.example`
   domains, fictitious phone numbers (zero-filled, or `555-01xx` in North America) and invalid VAT
   numbers. Live sources must never fall back to demo data silently.

## Other ground rules

- **Unknown is neutral.** New signals must be optional (`None` = unknown) and every variable must
  explain itself with human-readable reasons.
- **Fetch safely.** Third-party URLs go through `tech_audit.fetch_page` / `audit_client`, which
  enforce the SSRF guard and the response-size cap. Don't add raw `httpx.get(url)` calls on URLs
  that come from scraped data, imports or agents.
- **Skills stay in sync.** Edit `skills/coldlead-scout/SKILL.md`, then copy it to
  `.claude/skills/coldlead-scout/` and `.agents/skills/coldlead-scout/` (a test enforces this).
- **Translations stay in sync.** `README.it.md` mirrors `README.md`: update both in the same PR.
- **Be a good citizen.** Providers must identify themselves, keep request volumes low and honour
  robots.txt and API terms.

## Good first contributions

- **A locale pack for your country.** Copy `src/coldlead/locales/en_US.py` to e.g. `de_DE.py`,
  fill in names, company templates and legal suffixes, fictitious phone/address formats, review
  replies and — the valuable part — your language's sector keywords, legal-form patterns and
  review red flags. Register it in `PACKS` (`src/coldlead/locales/__init__.py`);
  `test_locale_packs_are_complete_and_consistent` tells you what is still missing.
- New sector keywords in `knowledge.py` (English) or a locale pack (other languages), or offers in
  `outreach/playbooks.py`
- More tourism hubs, legacy CMS fingerprints or booking/chat widgets
- New presets in `presets.json`
- Translations of the Action Kit templates

Please open an issue before large changes. Use [Conventional Commits](https://www.conventionalcommits.org/)
for commit messages (`feat:`, `fix:`, `docs:` …).
