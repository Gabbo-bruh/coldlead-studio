"""Lead discovery providers.

``auto`` picks the best available source: Google Places (if a key is set), then OpenStreetMap
(free, needs network), then the offline demo dataset — so ``coldlead scout`` always works.
"""

from __future__ import annotations

from typing import Protocol

from coldlead.models import Lead

SOURCES: tuple[str, ...] = ("auto", "demo", "osm", "google")


class Provider(Protocol):
    name: str

    def search(self, niche: str, location: str, limit: int = 10) -> list[Lead]: ...


class DemoProvider:
    name = "demo"

    def search(self, niche: str, location: str, limit: int = 10) -> list[Lead]:
        from coldlead.providers.demo import demo_leads

        return demo_leads(niche, location, limit)
