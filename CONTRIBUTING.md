# Contributing

Thanks for helping make ColdLead Studio better! 🎯

## Setup

```bash
git clone https://github.com/gabrielecrema/coldlead-studio && cd coldlead-studio
uv sync --all-extras
uv run pytest            # the whole suite is offline and runs in seconds
uv run ruff check . && uv run ruff format --check .
```

## Ground rules

1. **Keep scoring pure.** `score_lead` / `score_leads` and everything in `variables.py` must stay
   deterministic and network-free. Slow work belongs in `pipeline.py`, `providers/` and `enrich/`.
2. **Never cache scores.** Sessions store raw signals only, so any weight change is instant.
3. **Unknown is neutral.** New signals must be optional (`None` = unknown) and every variable must
   explain itself with human-readable reasons.
4. **Respect the contract.** Output changes must keep `POSLeadDossier` compatible; regenerate the
   schema with `uv run coldlead schema -o schema/pos-lead-dossier.schema.json`.
5. **Skills stay in sync.** Edit `skills/coldlead-scout/SKILL.md`, then copy it to
   `.claude/skills/coldlead-scout/` and `.agents/skills/coldlead-scout/` (a test enforces this).
6. **Be a good citizen.** Providers must identify themselves, keep request volumes low and honour
   robots.txt and API terms.

## Good first contributions

- New sector keywords in `knowledge.py` or offers in `outreach/playbooks.py`
- More tourism hubs, legacy CMS fingerprints or booking/chat widgets
- New presets in `presets.json`
- Translations of the Action Kit templates

Please open an issue before large changes. Use [Conventional Commits](https://www.conventionalcommits.org/)
for commit messages (`feat:`, `fix:`, `docs:` …).
