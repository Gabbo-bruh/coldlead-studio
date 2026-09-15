"""Locale packs: country- and language-specific knowledge, isolated from the engine.

Each module (``en_US.py``, ``it_IT.py`` …) defines one :class:`Locale` with

* the **demo data** the offline provider uses when that market is selected, and
* the **vocabulary** (sector keywords, tourism hubs, legal forms, review red flags) that
  :mod:`coldlead.knowledge` merges for every lead.

Adding a country is one new module plus one entry in :data:`PACKS` — see CONTRIBUTING.md.
"""

from __future__ import annotations

from coldlead.locales import en_US, it_IT
from coldlead.locales.base import Locale, fold

# Registry order matters only for vocabulary merging; en-US is also the fallback locale.
PACKS: tuple[Locale, ...] = (en_US.LOCALE, it_IT.LOCALE)
DEFAULT_LOCALE: Locale = en_US.LOCALE


def get_locale(code: str) -> Locale:
    """A pack by BCP 47 code (``"it-IT"``, ``"it_IT"``), language (``"it"``) or country (``"IT"``)."""
    wanted = code.strip().replace("_", "-").lower()
    for pack in PACKS:
        if wanted in (pack.code.lower(), pack.language, *(c.lower() for c in pack.countries)):
            return pack
    raise KeyError(f"No locale pack for '{code}'. Available: {', '.join(p.code for p in PACKS)}")


def locale_for_country(country: str | None) -> Locale | None:
    """The pack serving an ISO country code, or ``None`` when there is none."""
    wanted = (country or "").strip().upper()
    return next((pack for pack in PACKS if wanted and wanted in pack.countries), None)


def detect_locale(location: str, country: str | None = None) -> Locale:
    """Pick the market of a search: the place named in ``location`` first (the rightmost, most
    specific mention wins, so "Naples, Florida" is American), then ``country``, then en-US."""
    matches = [(match, pack) for pack in PACKS if (match := pack.place_match(location))]
    if matches:
        return max(matches, key=lambda item: item[0])[1]
    return locale_for_country(country) or DEFAULT_LOCALE


__all__ = [
    "DEFAULT_LOCALE",
    "PACKS",
    "Locale",
    "detect_locale",
    "fold",
    "get_locale",
    "locale_for_country",
]
