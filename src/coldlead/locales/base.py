"""The :class:`Locale` pack definition shared by every country module."""

from __future__ import annotations

import random
import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from coldlead.models import LegalForm

PhoneFormat = Callable[[random.Random, bool, str], str]  # (rng, mobile, city) -> number
AddressFormat = Callable[[random.Random, str], str]  # (rng, city) -> street address
VatFormat = Callable[[random.Random], str]  # rng -> VAT / tax id ("" where not public)


def fold(text: str) -> str:
    """Lowercase and strip accents: "Cefalù" and "cefalu" must match the same place."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


@dataclass(frozen=True, eq=False)
class Locale:
    """Everything country- or language-specific, in one place.

    Two kinds of knowledge live here:

    * **Demo data** for :mod:`coldlead.providers.demo` — used only when this locale is selected.
      Formats must stay obviously fictitious (see CONTRIBUTING.md, Core Invariants).
    * **Vocabulary** merged into :mod:`coldlead.knowledge` for *every* lead, whatever its country,
      so a niche typed in Italian still matches in Miami and vice versa.
    """

    code: str  # BCP 47, e.g. "it-IT"
    # ISO 3166-1 alpha-2 codes this pack serves; the first one is the main market.
    countries: tuple[str, ...]
    language: str  # outreach language this market expects ("en", "it", …)
    # Whole words (cities, regions, country names) that identify this market in a location query.
    places: tuple[str, ...]
    default_city: str
    default_niche: str

    # --- demo data ------------------------------------------------------------------------------
    surnames: tuple[str, ...]
    first_names: tuple[str, ...]
    place_words: tuple[str, ...]  # "{place}" in name templates: "del Porto", "Harbor"…
    # Niche category (knowledge.NICHE_CATEGORIES) -> name templates; "generic" is required.
    name_templates: Mapping[str, tuple[str, ...]]
    generic_niche: str  # "{niche}" when the niche is blank
    # Archetype legal form -> (name suffix, legal form recorded in the dossier).
    legal_forms: Mapping[LegalForm, tuple[str, LegalForm]]
    insolvency_suffix: str  # appended to the name of the insolvent archetype
    polite_replies: tuple[str, ...]  # "{reviewer}" and "{city}" placeholders
    toxic_replies: tuple[str, ...]
    reviewers: tuple[str, ...]
    agencies: tuple[str, ...]  # web agencies credited in the footer of agency-locked sites
    phone: PhoneFormat
    address: AddressFormat
    vat_number: VatFormat

    # --- vocabulary merged into knowledge.py -----------------------------------------------------
    niche_keywords: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    ticket_keywords: Mapping[float, tuple[str, ...]] = field(default_factory=dict)
    international_niches: tuple[str, ...] = ()
    tourist_hubs: tuple[str, ...] = ()
    legal_form_patterns: tuple[tuple[str, LegalForm], ...] = ()
    toxic_reply_patterns: tuple[str, ...] = ()
    insolvency_patterns: tuple[str, ...] = ()
    mobile_prefixes: tuple[str, ...] = ()  # national mobile prefixes, digits only (with "+")

    @property
    def country(self) -> str:
        return self.countries[0]

    def legal_name(self, form: LegalForm) -> tuple[str, LegalForm]:
        """``(suffix, recorded legal form)`` for a demo archetype's legal form."""
        return self.legal_forms.get(form, ("", form))

    def place_match(self, location: str) -> tuple[int, int] | None:
        """Where this locale's rightmost, longest place name occurs in ``location``.

        Returns ``(end position, length)`` so that "Naples, Florida" prefers the later, more
        specific word; ``None`` when no place of this locale is mentioned.
        """
        text = fold(location)
        best: tuple[int, int] | None = None
        for place in self.places:
            for match in re.finditer(rf"(?<!\w){re.escape(fold(place))}(?!\w)", text):
                candidate = (match.end(), len(place))
                best = candidate if best is None or candidate > best else best
        return best
