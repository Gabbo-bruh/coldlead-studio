"""Session cache: raw signals persisted once, re-scored forever.

Sessions are plain JSON files under ``~/.coldlead/sessions/`` (or ``$COLDLEAD_HOME``), so they
are diff-able, portable and easy to feed to other tools.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from coldlead.config import coldlead_home
from coldlead.models import Session, utcnow


class SessionNotFound(LookupError):
    pass


@dataclass(frozen=True)
class SessionSummary:
    id: str
    niche: str
    location: str
    source: str
    created_at: datetime
    lead_count: int


def _slug(text: str, max_len: int = 32) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "session"


def new_session_id(niche: str, location: str) -> str:
    return f"{utcnow():%Y%m%d-%H%M%S}-{_slug(f'{niche} {location}')}"


class SessionStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else coldlead_home() / "sessions"

    def _path(self, session_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", session_id):
            raise SessionNotFound(f"Invalid session id '{session_id}'")
        return self.root / f"{session_id}.json"

    def save(self, session: Session) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(session.id)
        fd, tmp = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(session.model_dump_json(indent=2))
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return path

    def load(self, session_id: str | None = None) -> Session:
        """Load a session by id (or unique id prefix). ``None`` loads the most recent one."""
        if session_id in (None, "", "latest"):
            summaries = self.list()
            if not summaries:
                raise SessionNotFound("No sessions yet. Run `coldlead scout <niche> <city>` first.")
            session_id = summaries[0].id
        path = self._path(session_id)
        if not path.exists():
            matches = [s.id for s in self.list() if s.id.startswith(session_id)]
            if len(matches) != 1:
                raise SessionNotFound(f"Session '{session_id}' not found")
            path = self._path(matches[0])
        return Session.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> list[SessionSummary]:
        if not self.root.exists():
            return []
        summaries = []
        for path in self.root.glob("*.json"):
            try:
                session = Session.model_validate_json(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            summaries.append(
                SessionSummary(
                    id=session.id,
                    niche=session.niche,
                    location=session.location,
                    source=session.source,
                    created_at=session.created_at,
                    lead_count=len(session.leads),
                )
            )
        return sorted(summaries, key=lambda s: (s.created_at, s.id), reverse=True)

    def delete(self, session_id: str) -> None:
        path = self._path(session_id)
        if not path.exists():
            raise SessionNotFound(f"Session '{session_id}' not found")
        path.unlink()
