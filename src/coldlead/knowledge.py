"""Domain knowledge used by the heuristics: sectors, tourism hubs, legacy stacks, legal forms.

Everything here is plain data so it is easy to review, extend and test. Keywords are matched
case-insensitively as word prefixes of the niche / city, in Italian and English.
"""

from __future__ import annotations

import re

from coldlead.models import LegalForm


def keyword_in(keyword: str, text: str) -> bool:
    """Prefix match at a word boundary. A trailing space in ``keyword`` demands a whole word
    (``"bar "`` matches "bar pizzeria" but not "barche")."""
    return re.search(r"\b" + re.escape(keyword), f" {text.lower()} ") is not None


# fmt: off
# --------------------------------------------------------------------------------------------
# Niche categories: drive demo data, OSM tags and outreach playbooks. First match wins.
# --------------------------------------------------------------------------------------------

NICHE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "nautical": ("charter", "yacht", "barc", "boat", "nautic", "marina", "gommon", "vela", "sailing"),
    "real_estate": ("immobiliar", "real estate", "realty", "propert", "case vacanza"),
    "hospitality": ("hotel", "albergo", "resort", "b&b", "bed and breakfast", "agriturismo", "guest house",
                    "affittacamere", "villa", "glamping", "camping", "ostello", "hostel"),
    "restaurant": ("ristorant", "ristorazione", "trattoria", "osteria", "pizzeria", "sushi", "gourmet",
                   "restaurant", "bistro", "enoteca", "wine bar", "steakhouse", "food"),
    "clinic": ("dent", "clinic", "medic", "chirurg", "estetica medica", "fisioterap", "poliambulator",
               "veterinar", "ortodon", "oculist", "dermatolog", "psicolog", "nutrizionist"),
    "beauty": ("parrucch", "estetist", "barber", "beauty", "spa ", "benessere", "nail", "centro estetico"),
    "cafe_bar": ("bar ", "caffè", "caffe", "cafe", "pasticceria", "gelateria", "pub ", "bakery"),
    "professional": ("avvocat", "studio legale", "lawyer", "commercialist", "accountant", "notai",
                     "architett", "ingegner", "consulen", "agenzia viaggi", "assicuraz", "insurance"),
    "fitness": ("palestra", "gym", "fitness", "yoga", "pilates", "crossfit", "piscina", "padel", "tennis"),
    "automotive": ("autofficina", "officina", "concessionari", "car ", "auto ", "ncc", "noleggio auto",
                   "taxi", "moto"),
    "retail": ("negozio", "boutique", "gioiell", "jewel", "abbigliament", "fashion", "ottica", "shop",
               "fiorist"),
    "events": ("wedding", "matrimon", "eventi", "event", "catering", "fotograf", "photograph", "location"),
}

# --------------------------------------------------------------------------------------------
# Ticket value / sector margin (V_ticket). Rules are checked from the highest value down.
# --------------------------------------------------------------------------------------------

TICKET_VALUE_RULES: tuple[tuple[float, tuple[str, ...]], ...] = (
    (10.0, ("yacht", "superyacht", "jet privat", "private jet", "chirurgia estetica", "cosmetic surgery")),
    (9.5, ("charter", "villa", "lusso", "luxury", "gioiell", "jewel", "immobiliare di pregio", "prestige")),
    (9.0, ("boutique hotel", "resort", "clinic", "chirurg", "dentist", "dental", "dent", "ncc")),
    (8.5, ("wedding", "matrimon", "medicina estetica", "ortodon", "concessionari", "car dealer")),
    (8.0, ("immobiliar", "real estate", "hotel", "albergo", "nautic", "boat", "barc", "marina")),
    (7.0, ("gourmet", "stellato", "fine dining", "agriturismo", "spa ", "architett", "studio legale", "notai")),
    (6.5, ("ristorant", "restaurant", "enoteca", "stabilimento balneare", "beach club", "avvocat",
           "commercialist", "b&b", "centro benessere", "fisioterap", "veterinar", "catering", "eventi")),
    (5.5, ("palestra", "gym", "fitness", "trattoria", "osteria", "officina", "autofficina", "ottica")),
    (4.5, ("pizzeria", "parrucch", "barber", "estetist", "negozio", "shop", "fiorist", "sushi")),
    (3.5, ("bar ", "caffè", "caffe", "cafe", "pub ", "gelateria", "pasticceria", "bakery")),
)
DEFAULT_TICKET_VALUE = 4.0

# Niches whose customers are structurally international, regardless of the city.
INTERNATIONAL_NICHES: tuple[str, ...] = (
    "yacht", "charter", "villa", "luxury", "lusso", "resort", "boutique hotel", "prestige",
    "wedding", "destination", "tour operator", "guided tour", "wine tour",
)

# --------------------------------------------------------------------------------------------
# International tourism hubs (M_reach). Italian focus, plus major European destinations.
# --------------------------------------------------------------------------------------------

TOURIST_HUBS: tuple[str, ...] = (
    # Liguria
    "portofino", "santa margherita", "rapallo", "camogli", "sestri levante", "cinque terre",
    "monterosso", "vernazza", "riomaggiore", "portovenere", "lerici", "sanremo", "alassio",
    "genova", "chiavari", "zoagli", "finale ligure",
    # Tuscany
    "firenze", "florence", "siena", "pisa", "lucca", "forte dei marmi", "viareggio",
    "san gimignano", "montepulciano", "chianti", "val d'orcia", "elba", "cortona",
    "castiglione della pescaia",
    # Big cities & art cities
    "roma", "rome", "venezia", "venice", "milano", "milan", "verona", "bologna", "napoli",
    "naples", "torino", "turin", "palermo", "matera", "lecce",
    # Lakes & mountains
    "como", "bellagio", "menaggio", "varenna", "garda", "sirmione", "riva del garda", "malcesine",
    "stresa", "lago maggiore", "cortina", "courmayeur", "madonna di campiglio", "livigno", "bormio",
    "val gardena", "ortisei", "merano", "bolzano", "cervinia",
    # South & islands
    "amalfi", "positano", "ravello", "sorrento", "capri", "ischia", "procida", "taormina", "cefalù",
    "siracusa", "ortigia", "noto", "costa smeralda", "porto cervo", "olbia", "alghero",
    "villasimius", "polignano", "ostuni", "otranto", "gallipoli", "tropea", "maratea", "salento",
    "costiera",
    # Europe
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

_LEGAL_FORM_PATTERNS: tuple[tuple[str, LegalForm], ...] = (
    (r"\bs\.?\s?r\.?\s?l\.?\s?s\b\.?", LegalForm.SRLS),
    (r"\bs\.?\s?p\.?\s?a\b\.?", LegalForm.SPA),
    (r"\bs\.?\s?r\.?\s?l\b\.?", LegalForm.SRL),
    (r"\bs\.?\s?n\.?\s?c\b\.?|\bs\.?\s?a\.?\s?s\b\.?", LegalForm.SNC_SAS),
    (r"\bsoc(ietà|\.)?\s*coop|\bcooperativa\b", LegalForm.COOP),
    (r"\bd\.\s?i\.?(?=\s|$)|\bditta individuale\b", LegalForm.SOLE_TRADER),
    (r"\bstudio (legale|associato|medico|dentistico|notarile|tecnico)\b", LegalForm.PROFESSIONAL),
    (r"\b(ltd|llc|inc|gmbh|sarl|s\.?a\.?r\.?l|bv|plc)\b\.?", LegalForm.LTD),
)

# --------------------------------------------------------------------------------------------
# Red-flag vocabularies.
# --------------------------------------------------------------------------------------------

TOXIC_REPLY_PATTERNS: tuple[str, ...] = (
    r"\bti querelo\b", r"\bquerela\b", r"\bdenunci(o|a|ato|erò)\b", r"\bdiffamazione\b",
    r"\bavvocat[oi] (mio|nostro)\b", r"\bmio legale\b", r"\bpolizia postale\b", r"\btribunale\b",
    r"\bvergognati\b", r"\bidiot[ae]\b", r"\bstronz[oa]\b", r"\bbugiard[oa]\b", r"\bcretin[oa]\b",
    r"\bfals[oi] profil[oi]\b", r"\bnon farti più vedere\b", r"\bchiudi quella bocca\b",
    r"\bsue you\b", r"\bmy lawyer\b", r"\bdefamation\b", r"\bliar\b", r"\bidiot\b",
    r"\bfake review(er)?\b",
)

INSOLVENCY_PATTERNS: tuple[str, ...] = (
    r"\bin liquidazione\b", r"\bliquidazione\b", r"\bfallimento\b", r"\bfallit[ao]\b",
    r"\bconcordato preventivo\b", r"\bprocedura concorsuale\b", r"\bcessata attività\b",
    r"\bchiuso definitivamente\b", r"\bprotest[io]\b", r"\bin liquidation\b", r"\bbankrupt(cy)?\b",
    r"\binsolvenc[ey]\b", r"\bpermanently closed\b",
)

CLOSED_STATUSES: frozenset[str] = frozenset({"CLOSED_PERMANENTLY", "IN_LIQUIDATION", "BANKRUPT", "CEASED"})
# fmt: on


def detect_category(niche: str) -> str:
    for category, keywords in NICHE_CATEGORIES.items():
        if any(keyword_in(k, niche) for k in keywords):
            return category
    return "generic"


def ticket_value(niche: str) -> tuple[float, str | None]:
    for value, keywords in TICKET_VALUE_RULES:
        for keyword in keywords:
            if keyword_in(keyword, niche):
                return value, keyword.strip()
    return DEFAULT_TICKET_VALUE, None


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
