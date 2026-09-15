"""Domain knowledge used by the heuristics: sectors, tourism hubs, legacy stacks, legal forms.

Everything here is plain data so it is easy to review, extend and test. Keywords are matched
case-insensitively as word prefixes of the niche / city.

This module holds the English and language-neutral vocabulary. Every locale pack in
:mod:`coldlead.locales` (Italian keywords, S.r.l. patterns, US tourism hubs …) is merged in at
import time, so a niche typed in any supported language matches wherever the business is.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import TypeVar

from coldlead.locales import PACKS
from coldlead.models import LegalForm

K = TypeVar("K")


def keyword_in(keyword: str, text: str) -> bool:
    """Prefix match at a word boundary. A trailing space in ``keyword`` demands a whole word
    (``"bar "`` matches "bar pizzeria" but not "barche")."""
    return re.search(r"\b" + re.escape(keyword), f" {text.lower()} ") is not None


def _merge(
    base: Mapping[K, tuple[str, ...]], extras: Iterable[Mapping[K, tuple[str, ...]]]
) -> dict[K, tuple[str, ...]]:
    """Base keywords first, then each pack's, without duplicates; keys keep the base order."""
    merged = {key: list(words) for key, words in base.items()}
    for extra in extras:
        for key, words in extra.items():
            bucket = merged.setdefault(key, [])
            bucket.extend(w for w in words if w not in bucket)
    return {key: tuple(words) for key, words in merged.items()}


# fmt: off
# --------------------------------------------------------------------------------------------
# Niche categories: drive demo data, OSM tags and outreach playbooks. First match wins.
# --------------------------------------------------------------------------------------------

# Beware of prefixes that start other languages' words: "surg" would catch "surgelati", "limo"
# "limoncello", "consult" "consultorio" — use whole words (trailing space) or longer stems.
_NICHE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "nautical": ("charter", "yacht", "boat", "nautic", "marina", "sailing"),
    "real_estate": ("real estate", "realty", "realtor", "propert"),
    "hospitality": ("hotel", "resort", "b&b", "bed and breakfast", "bed & breakfast", "guest house",
                    "villa", "glamping", "camping", "hostel", "motel", "inn ", "lodge",
                    "vacation rental", "holiday rental"),
    "restaurant": ("pizzeria", "sushi", "gourmet", "restaurant", "bistro", "wine bar", "steakhouse",
                   "food", "diner", "grill", "tavern", "eatery"),
    "clinic": ("dent", "clinic", "medic", "veterinar", "vet ", "animal hospital", "oculist",
               "optometr", "dermatolog", "surgeon", "surgery", "surgical", "physio",
               "physical therap", "orthodont", "chiropract", "psycholog", "psychotherap",
               "nutritionist", "dietitian", "med spa"),
    "beauty": ("barber", "beauty", "beautician", "spa ", "nail", "hair", "salon ", "massage",
               "wellness", "esthetic"),
    "cafe_bar": ("bar ", "cafe", "coffee", "pub ", "bakery", "pastry", "patisserie", "ice cream",
                 "gelato"),
    "professional": ("lawyer", "attorney", "law firm", "law office", "accountant", "cpa ",
                     "tax advis", "notary", "architect", "engineer", "consultant", "consulting",
                     "consultancy", "travel agen", "insurance"),
    "fitness": ("gym", "fitness", "yoga", "pilates", "crossfit", "padel", "tennis", "swim",
                "boxing", "martial art", "personal train"),
    "automotive": ("car ", "auto ", "taxi", "moto", "mechanic", "garage", "body shop", "dealership",
                   "limo ", "limousine", "chauffeur"),
    "retail": ("boutique", "jewel", "fashion", "clothing", "apparel", "optician", "eyewear",
               "florist", "flower", "shop"),
    "events": ("wedding", "event", "catering", "photograph", "location", "venue"),
}
NICHE_CATEGORIES: dict[str, tuple[str, ...]] = _merge(
    _NICHE_CATEGORIES, (pack.niche_keywords for pack in PACKS)
)

# --------------------------------------------------------------------------------------------
# Ticket value / sector margin (V_ticket). Rules are checked from the highest value down.
# --------------------------------------------------------------------------------------------

_TICKET_VALUE_RULES: dict[float, tuple[str, ...]] = {
    10.0: ("yacht", "superyacht", "private jet", "cosmetic surgery", "plastic surg"),
    9.5: ("charter", "villa", "luxury", "jewel", "prestige"),
    9.0: ("boutique hotel", "resort", "clinic", "dentist", "dental", "dent", "surgeon", "surgery",
          "surgical", "chauffeur", "limousine", "limo "),
    8.5: ("wedding", "car dealer", "dealership", "orthodont", "med spa", "medical spa",
          "aesthetic medicine"),
    8.0: ("real estate", "realty", "realtor", "hotel", "nautic", "boat", "marina"),
    7.0: ("gourmet", "fine dining", "michelin", "spa ", "architect", "law firm", "notary"),
    6.5: ("restaurant", "wine bar", "wine shop", "beach club", "lawyer", "attorney", "accountant",
          "cpa ", "b&b", "wellness", "physio", "physical therap", "chiropract", "veterinar", "vet ",
          "animal hospital", "catering", "event"),
    5.5: ("gym", "fitness", "diner", "tavern", "mechanic", "garage", "auto repair", "car repair",
          "body shop", "optician", "eyewear"),
    4.5: ("pizzeria", "barber", "hair", "salon ", "beautician", "esthetic", "shop", "florist",
          "flower", "sushi"),
    3.5: ("bar ", "cafe", "coffee", "pub ", "bakery", "pastry", "patisserie", "ice cream", "gelato"),
}
TICKET_VALUE_RULES: tuple[tuple[float, tuple[str, ...]], ...] = tuple(
    sorted(_merge(_TICKET_VALUE_RULES, (pack.ticket_keywords for pack in PACKS)).items(), reverse=True)
)
DEFAULT_TICKET_VALUE = 4.0
# Words that only say "a shop": a more specific sector keyword in the same niche wins.
GENERIC_TICKET_WORDS: frozenset[str] = frozenset({"shop"})

# Niches whose customers are structurally international, regardless of the city.
INTERNATIONAL_NICHES: tuple[str, ...] = (
    "yacht", "charter", "villa", "luxury", "resort", "boutique hotel", "prestige",
    "wedding", "destination", "tour operator", "guided tour", "wine tour",
    *(word for pack in PACKS for word in pack.international_niches),
)

# --------------------------------------------------------------------------------------------
# International tourism hubs (M_reach): major European destinations here, the rest (Italy, US…)
# comes from the locale packs.
# --------------------------------------------------------------------------------------------

TOURIST_HUBS: tuple[str, ...] = (
    *(hub for pack in PACKS for hub in pack.tourist_hubs),
    "paris", "parigi", "london", "londra", "barcelona", "barcellona", "nice", "nizza", "monaco",
    "cannes", "saint-tropez", "ibiza", "mallorca", "maiorca", "marbella", "lisbon", "lisbona",
    "santorini", "mykonos", "dubrovnik", "split", "amsterdam", "prague", "praga", "vienna",
)

# --------------------------------------------------------------------------------------------
# Legacy / slow stacks (G_dig penalty). Page builders are not listed: their cost is already
# captured by the performance score.
# --------------------------------------------------------------------------------------------

LEGACY_STACK_PENALTIES: tuple[tuple[str, float, str], ...] = (
    (r"wordpress\s*[1-4](\.|\b)", 1.5, "WordPress 4.x or older"),
    (r"joomla", 1.5, "Joomla (legacy CMS)"),
    (r"drupal\s*[5-7]\b", 1.5, "Drupal 7 or older"),
    (r"flash|frontpage|dreamweaver", 2.0, "Pre-2010 technology"),
    (r"jimdo|weebly|site123|webnode|register\.it|aruba site ?builder", 1.0, "Entry-level site builder"),
    (r"\bwix\b", 1.0, "Wix (slow for performance-critical sites)"),
)

# --------------------------------------------------------------------------------------------
# Legal forms (F_fin) and their parsing from company names.
# --------------------------------------------------------------------------------------------

LEGAL_FORM_SCORES: dict[LegalForm, float] = {
    LegalForm.SPA: 10.0,
    LegalForm.SRL: 9.0,
    LegalForm.LTD: 8.5,
    LegalForm.PROFESSIONAL: 7.0,
    LegalForm.SRLS: 6.5,
    LegalForm.COOP: 6.0,
    LegalForm.SNC_SAS: 5.5,
    LegalForm.SOLE_TRADER: 3.0,
}

# Readable names for explanations. The enum values stay the stable identifiers of the schema
# and of cached sessions, so they are never renamed here.
LEGAL_FORM_LABELS: dict[LegalForm, str] = {
    LegalForm.SPA: "S.p.A. (joint-stock company)",
    LegalForm.SRL: "S.r.l. (limited company)",
    LegalForm.SRLS: "S.r.l.s. (simplified limited company)",
    LegalForm.SNC_SAS: "partnership (S.n.c. / S.a.s. / LLP)",
    LegalForm.COOP: "cooperative",
    LegalForm.SOLE_TRADER: "sole trader",
    LegalForm.PROFESSIONAL: "professional practice",
    LegalForm.LTD: "limited company (Ltd / LLC / Inc. / GmbH)",
}

# Locale-specific forms (S.r.l., LLP …) are tried first; the international catch-all comes last.
_LEGAL_FORM_PATTERNS: tuple[tuple[str, LegalForm], ...] = (
    *(pattern for pack in PACKS for pattern in pack.legal_form_patterns),
    (r"\b(ltd|llc|inc|gmbh|sarl|s\.?a\.?r\.?l|bv|plc)\b\.?", LegalForm.LTD),
)

# --------------------------------------------------------------------------------------------
# Red-flag vocabularies (English here, other languages from the locale packs).
# --------------------------------------------------------------------------------------------

TOXIC_REPLY_PATTERNS: tuple[str, ...] = (
    *(pattern for pack in PACKS for pattern in pack.toxic_reply_patterns),
    r"\bsue you\b", r"\bmy lawyer\b", r"\bdefamation\b", r"\bliar\b", r"\bidiot\b",
    r"\bfake review(er)?\b",
)

INSOLVENCY_PATTERNS: tuple[str, ...] = (
    *(pattern for pack in PACKS for pattern in pack.insolvency_patterns),
    r"\bin liquidation\b", r"\bbankrupt(cy)?\b", r"\binsolvenc[ey]\b", r"\bpermanently closed\b",
)

CLOSED_STATUSES: frozenset[str] = frozenset({"CLOSED_PERMANENTLY", "IN_LIQUIDATION", "BANKRUPT", "CEASED"})

# National mobile prefixes (owner reachability): North American numbers carry no such signal.
MOBILE_PREFIXES: tuple[str, ...] = tuple(p for pack in PACKS for p in pack.mobile_prefixes)
# fmt: on


def detect_category(niche: str) -> str:
    for category, keywords in NICHE_CATEGORIES.items():
        if any(keyword_in(k, niche) for k in keywords):
            return category
    return "generic"


def ticket_value(niche: str) -> tuple[float, str | None]:
    """Highest matching sector rule; generic words ("shop") only when nothing specific matches,
    so a "coffee shop" is valued as coffee, like a "caffè"."""
    fallback: tuple[float, str] | None = None
    for value, keywords in TICKET_VALUE_RULES:
        for keyword in keywords:
            if keyword_in(keyword, niche):
                if keyword.strip() not in GENERIC_TICKET_WORDS:
                    return value, keyword.strip()
                fallback = fallback or (value, keyword.strip())
    return fallback or (DEFAULT_TICKET_VALUE, None)


def is_tourist_hub(city: str) -> bool:
    return any(keyword_in(hub, city) for hub in TOURIST_HUBS)


def legacy_stack_penalty(cms: str | None) -> tuple[float, str | None]:
    if not cms:
        return 0.0, None
    text = cms.lower()
    for pattern, penalty, label in LEGACY_STACK_PENALTIES:
        if re.search(pattern, text):
            return penalty, label
    return 0.0, None


def parse_legal_form(name: str) -> LegalForm:
    text = name.lower()
    for pattern, form in _LEGAL_FORM_PATTERNS:
        if re.search(pattern, text):
            return form
    return LegalForm.UNKNOWN
