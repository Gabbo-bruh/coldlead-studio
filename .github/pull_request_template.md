## What & why

<!-- One or two sentences. Link the issue if there is one. -->

## Checklist

- [ ] `uv run pytest` passes
- [ ] `uv run ruff check . && uv run ruff format --check .` pass
- [ ] Scoring stays pure (no I/O in `variables.py` / `scoring.py`)
- [ ] Schema regenerated if models changed (`coldlead schema -o schema/pos-lead-dossier.schema.json`)
- [ ] Docs / CHANGELOG updated when user-facing
