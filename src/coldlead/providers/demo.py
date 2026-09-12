"""Offline demo provider: realistic, deterministic prospects for any niche and city.

The same (niche, city) pair always yields the same leads, so demos, docs and tests are
reproducible. Every lead is clearly marked ``source="demo"`` and uses reserved ``.example``
domains: nothing here points at a real business.
"""

from __future__ import annotations

import hashlib
import random
import re
from collections.abc import Callable

from coldlead import knowledge
from coldlead.models import Company, Lead, LegalForm, RawSignals, make_lead_id

# fmt: off
SURNAMES = (
    "Rossi", "Bianchi", "Ferrari", "Esposito", "Romano", "Colombo", "Ricci", "Marino", "Greco",
    "Bruno", "Gallo", "Conti", "Costa", "Giordano", "Mancini", "Lombardi", "Moretti", "Barbieri",
    "Fontana", "Caruso", "Benvenuti", "Castaldi", "Canale", "De Luca", "Serra", "Pellegrini",
)
FIRST_NAMES = (
    "Marco", "Giulia", "Luca", "Francesca", "Alessandro", "Chiara", "Matteo", "Sara", "Andrea",
    "Elena", "Davide", "Valentina", "Stefano", "Martina", "Paolo", "Federica", "Gianni", "Laura",
)
PLACES = ("del Porto", "al Mare", "Riviera", "del Golfo", "Belvedere", "Centrale", "Aurora", "Stella")

NAME_TEMPLATES: dict[str, tuple[str, ...]] = {
    "nautical": ("{city} Charter", "Yacht Service {surname}", "Noleggio Barche {place}",
                 "{surname} Boats", "Blue Horizon Charter", "Marina {place}"),
    "real_estate": ("Immobiliare {surname}", "{city} Prestige Properties", "Casa & Mare {place}",
                    "Agenzia Immobiliare {place}", "{surname} Real Estate"),
    "hospitality": ("Hotel {place}", "Villa {surname}", "B&B {place}", "Residenza {surname}",
                    "{city} Boutique Hotel", "Agriturismo {surname}"),
    "restaurant": ("Ristorante {place}", "Trattoria da {first}", "Osteria {surname}",
                   "Da {first} & Figli", "Pizzeria {place}", "Il Gusto di {first}"),
    "cafe_bar": ("Bar {place}", "Caffè {surname}", "Pasticceria {surname}", "Gelateria {place}"),
    "clinic": ("Studio Dentistico {surname}", "Clinica {place}", "Poliambulatorio {city}",
               "Centro Medico {surname}", "Studio Medico {surname}"),
    "beauty": ("Salone {first}", "Beauty Lab {surname}", "Centro Estetico {place}", "Barber {surname}"),
    "professional": ("Studio Legale {surname}", "Studio {surname} & Associati",
                     "Commercialista {first} {surname}", "Architetti {surname}"),
    "fitness": ("Palestra {place}", "{city} Fitness Club", "Studio Pilates {first}", "CrossFit {place}"),
    "automotive": ("Autofficina {surname}", "{city} Car Service", "Noleggio {surname}", "NCC {surname}"),
    "retail": ("Boutique {first}", "Gioielleria {surname}", "Ottica {place}", "Negozio {surname}"),
    "events": ("{first} Wedding Planner", "Eventi {place}", "Catering {surname}", "Foto {first} {surname}"),
    "generic": ("{niche} {surname}", "{surname} {niche}", "{niche} {place}", "{city} {niche}"),
}

LEGAL_SUFFIX = {
    LegalForm.SRL: " S.r.l.", LegalForm.SRLS: " S.r.l.s.", LegalForm.SNC_SAS: " S.n.c.",
    LegalForm.SOLE_TRADER: "", LegalForm.SPA: " S.p.A.",
}

POLITE_REPLIES_IT = (
    "Gentile {reviewer}, grazie di cuore per le belle parole! Vi aspettiamo presto a {city}.",
    "Grazie mille {reviewer}, è stato un piacere avervi nostri ospiti. A presto!",
    "Caro {reviewer}, felici che l'esperienza vi sia piaciuta. Un saluto da tutto lo staff.",
)
TOXIC_REPLIES_IT = (
    "Sei un bugiardo, ti querelo per diffamazione e porto il tuo IP alla polizia postale!",
    "Vergognati, questa è una recensione falsa scritta da un concorrente. Non farti più vedere.",
)
REVIEWERS = ("James", "Sophie", "Marco", "Anna", "Thomas", "Claire", "Giorgio", "Hannah")
DEMO_MARK = " (demo)"
# fmt: on

Archetype = Callable[[random.Random], dict]


def _legacy_gem(r: random.Random) -> dict:
    return dict(
        legal=r.choice([LegalForm.SRL, LegalForm.SRL, LegalForm.SNC_SAS]),
        website=True,
        perf=r.randint(28, 45),
        mobile=True,
        ssl=True,
        cms=r.choice(["WordPress (Elementor)", "WordPress 4.9", "Joomla 3"]),
        multilingual=False,
        booking=False,
        chat=False,
        pdf=r.random() < 0.5,
        reviews=r.randint(60, 260),
        rating=round(r.uniform(4.5, 4.9), 1),
        reply=r.uniform(75, 95),
        tone="Empathetic & Professional",
        ads=r.random() < 0.6,
        contact="owner_whatsapp",
    )


def _modern_leader(r: random.Random) -> dict:
    return dict(
        legal=r.choice([LegalForm.SRL, LegalForm.SPA]),
        website=True,
        perf=r.randint(88, 98),
        mobile=True,
        ssl=True,
        cms="Next.js",
        multilingual=True,
        booking=True,
        chat=True,
        pdf=False,
        reviews=r.randint(250, 900),
        rating=round(r.uniform(4.6, 4.9), 1),
        reply=r.uniform(85, 100),
        tone="Empathetic & Professional",
        ads=True,
        contact="email_only",
    )


def _no_website(r: random.Random) -> dict:
    return dict(
        legal=LegalForm.SOLE_TRADER,
        website=False,
        reviews=r.randint(5, 40),
        rating=round(r.uniform(3.9, 4.6), 1),
        reply=0.0,
        tone="Ghost/Absent",
        ads=False,
        contact="mobile",
    )


def _broken_mobile(r: random.Random) -> dict:
    return dict(
        legal=r.choice([LegalForm.SRLS, LegalForm.SNC_SAS, LegalForm.SRL]),
        website=True,
        perf=r.randint(18, 35),
        mobile=False,
        ssl=r.random() < 0.4,
        cms=r.choice(["WordPress 4.7", "Joomla 2.5", "Custom / Static (tables layout)"]),
        multilingual=False,
        booking=False,
        chat=False,
        pdf=True,
        reviews=r.randint(30, 150),
        rating=round(r.uniform(4.1, 4.6), 1),
        reply=r.uniform(20, 55),
        tone="Professional",
        ads=False,
        contact="landline",
    )


def _toxic_owner(r: random.Random) -> dict:
    return dict(
        legal=LegalForm.SOLE_TRADER,
        website=True,
        perf=r.randint(30, 50),
        mobile=True,
        ssl=True,
        cms="WordPress",
        multilingual=False,
        booking=False,
        chat=False,
        pdf=False,
        reviews=r.randint(80, 200),
        rating=round(r.uniform(2.6, 3.4), 1),
        reply=r.uniform(80, 95),
        tone="Aggressive & Litigious",
        toxic=True,
        ads=False,
        contact="mobile",
    )


def _agency_locked(r: random.Random) -> dict:
    return dict(
        legal=LegalForm.SRL,
        website=True,
        perf=r.randint(55, 72),
        mobile=True,
        ssl=True,
        cms="WordPress (Divi)",
        multilingual=r.random() < 0.5,
        booking=False,
        chat=False,
        pdf=False,
        reviews=r.randint(40, 180),
        rating=round(r.uniform(4.2, 4.7), 1),
        reply=r.uniform(40, 70),
        tone="Professional",
        ads=r.random() < 0.5,
        contact="linkedin",
        agency=f"{r.choice(['Pixel', 'Digitalia', 'WebStudio', 'Creativa'])} Web Agency",
    )


def _wix_midrange(r: random.Random) -> dict:
    return dict(
        legal=r.choice([LegalForm.SRLS, LegalForm.SRL]),
        website=True,
        perf=r.randint(40, 58),
        mobile=True,
        ssl=True,
        cms="Wix",
        multilingual=False,
        booking=r.random() < 0.3,
        chat=False,
        pdf=False,
        reviews=r.randint(20, 120),
        rating=round(r.uniform(4.3, 4.8), 1),
        reply=r.uniform(35, 75),
        tone="Friendly",
        ads=r.random() < 0.4,
        contact="owner_whatsapp",
    )


def _chain(r: random.Random) -> dict:
    return dict(
        legal=LegalForm.SPA,
        website=True,
        perf=r.randint(60, 80),
        mobile=True,
        ssl=True,
        cms="Adobe Experience Manager",
        multilingual=True,
        booking=True,
        chat=r.random() < 0.5,
        pdf=False,
        reviews=r.randint(300, 1500),
        rating=round(r.uniform(3.8, 4.3), 1),
        reply=r.uniform(10, 40),
        tone="Corporate",
        ads=True,
        contact="email_only",
        chain=True,
    )


def _insolvent(r: random.Random) -> dict:
    return dict(
        legal=LegalForm.SRL,
        website=True,
        perf=r.randint(25, 45),
        mobile=True,
        ssl=False,
        cms="WordPress 4.2",
        multilingual=False,
        booking=False,
        chat=False,
        pdf=True,
        reviews=r.randint(10, 60),
        rating=round(r.uniform(3.2, 4.0), 1),
        reply=0.0,
        tone="Ghost/Absent",
        ads=False,
        contact="landline",
        insolvent=True,
    )


def _solid_pdf(r: random.Random) -> dict:
    return dict(
        legal=LegalForm.SRL,
        website=True,
        perf=r.randint(45, 62),
        mobile=True,
        ssl=True,
        cms="WordPress 6.4",
        multilingual=False,
        booking=False,
        chat=False,
        pdf=True,
        reviews=r.randint(90, 400),
        rating=round(r.uniform(4.3, 4.7), 1),
        reply=r.uniform(55, 80),
        tone="Professional",
        ads=r.random() < 0.5,
        contact="owner",
    )


# Order chosen so that even small demos show the full spectrum of outcomes.
ARCHETYPES: tuple[Archetype, ...] = (
    _legacy_gem,
    _modern_leader,
    _no_website,
    _broken_mobile,
    _toxic_owner,
    _wix_midrange,
    _agency_locked,
    _solid_pdf,
    _legacy_gem,
    _chain,
    _insolvent,
    _no_website,
)


def _seed(*parts: str) -> int:
    return int(
        hashlib.sha256("|".join(p.lower().strip() for p in parts).encode()).hexdigest()[:12], 16
    )


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())[:28] or "business"


def _phone(r: random.Random, mobile: bool) -> str:
    """Obviously fictitious numbers (zero-filled subscriber part) so no real person is exposed."""
    if mobile:
        return f"+39 3{r.randint(20, 49)} 000 00{r.randint(10, 99)}"
    return f"+39 0{r.randint(10, 99)} 000 0{r.randint(10, 99)}"


def _name(r: random.Random, category: str, niche: str, city: str, used: set[str]) -> str:
    """A base business name (no legal suffix) not yet in ``used``."""
    templates = NAME_TEMPLATES.get(category, NAME_TEMPLATES["generic"])
    niche_title = niche.strip().title() or "Servizi"
    for attempt in range(50):
        name = r.choice(templates).format(
            surname=r.choice(SURNAMES),
            first=r.choice(FIRST_NAMES),
            place=r.choice(PLACES),
            city=city,
            niche=niche_title,
        )
        if attempt >= 40:
            name = f"{name} {r.choice(SURNAMES)}"
        if name not in used:
            used.add(name)
            return name
    return f"{name} {len(used) + 1}"


def demo_leads(niche: str, location: str, limit: int = 10) -> list[Lead]:
    niche = niche.strip() or "Charter nautico"
    city = location.strip().title() or "Rapallo"
    category = knowledge.detect_category(niche)
    rng = random.Random(_seed(niche, city))
    leads: list[Lead] = []
    used_names: set[str] = set()

    for index in range(max(0, limit)):
        profile = ARCHETYPES[index % len(ARCHETYPES)](rng)
        legal = profile["legal"]
        base_name = _name(rng, category, niche, city, used_names)
        slug = _slug(base_name)
        name = base_name + LEGAL_SUFFIX.get(legal, "")
        if profile.get("insolvent"):
            name = f"{name} in liquidazione"
        # Demo names can coincide with real businesses in real towns: always mark them as fictitious.
        name = f"{name}{DEMO_MARK}"
        website = f"https://www.{slug}.example" if profile["website"] else None
        if website and profile.get("ssl") is False:
            website = website.replace("https://", "http://")

        contact = profile["contact"]
        person = f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}"
        channels, direct = [], ""
        if contact == "owner_whatsapp":
            channels, direct = ["WhatsApp", "Phone", "Email"], person
        elif contact == "owner":
            channels, direct = ["Phone", "Email"], person
        elif contact == "linkedin":
            channels, direct = ["LinkedIn", "Email"], ""
        elif contact == "mobile":
            channels = ["Mobile"]
        elif contact == "landline":
            channels = ["Phone", "Email"]
        else:
            channels = ["Email", "Contact form"]

        reviewer = rng.choice(REVIEWERS)
        if profile.get("toxic"):
            replies = list(TOXIC_REPLIES_IT)
        elif profile.get("reply", 0) > 0:
            replies = [rng.choice(POLITE_REPLIES_IT).format(reviewer=reviewer, city=city)]
        else:
            replies = []

        signals = RawSignals(
            has_website=profile["website"],
            website_url=website,
            lighthouse_performance=profile.get("perf"),
            performance_source="estimated" if profile["website"] else None,
            mobile_friendly=profile.get("mobile"),
            has_ssl=profile.get("ssl"),
            cms_stack=profile.get("cms"),
            has_multilingual=profile.get("multilingual"),
            has_booking_system=profile.get("booking"),
            has_ai_chat=profile.get("chat"),
            has_pdf_menu=profile.get("pdf"),
            has_contact_form=profile["website"] or None,
            footer_agency_credit=profile.get("agency"),
            reviews_count=profile["reviews"],
            average_rating=profile["rating"],
            owner_reply_rate=round(profile.get("reply", 0.0), 1),
            owner_sentiment_tone=profile.get("tone"),
            is_toxic_owner=bool(profile.get("toxic")),
            sample_owner_replies=replies,
            is_running_ads=profile.get("ads"),
            ads_evidence=["Meta Pixel + Google Ads tag (demo)"] if profile.get("ads") else [],
            is_chain=bool(profile.get("chain")),
            business_status="IN_LIQUIDATION" if profile.get("insolvent") else "OPERATIONAL",
        )
        company = Company(
            name=name,
            niche=niche,
            city=city,
            address=f"Via {rng.choice(SURNAMES)} {rng.randint(1, 120)}, {city}",
            phone=_phone(rng, mobile=contact in ("mobile", "owner_whatsapp")),
            email=f"info@{slug}.example" if contact != "mobile" else "",
            vat_number=f"IT000000{rng.randint(10000, 99999)}",  # invalid on purpose
            legal_form=legal,
            employees_estimate={LegalForm.SPA: 80, LegalForm.SRL: rng.randint(4, 25)}.get(legal),
            direct_contact_person=direct,
            contact_channels=channels,
        )
        leads.append(
            Lead(
                id=make_lead_id("demo", niche, city, name),
                company=company,
                raw_signals=signals,
                source="demo",
            )
        )
    return leads
