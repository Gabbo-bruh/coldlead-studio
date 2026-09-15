"""Offline demo provider: realistic, deterministic prospects for any niche and city.

The same (niche, city) pair always yields the same leads, so demos, docs and tests are
reproducible. Every lead is clearly marked ``source="demo"`` and uses reserved ``.example``
domains: nothing here points at a real business.

Names, legal forms, phone and address formats and review replies come from the locale pack of
the searched market (:mod:`coldlead.locales`): Miami gets "Harbor Grill LLC" and +1 305-555-01xx
numbers, Portofino gets "Trattoria da Marco S.r.l." and +39 numbers. Unknown places use en-US.
"""

from __future__ import annotations

import hashlib
import random
import re
from collections.abc import Callable

from coldlead import knowledge
from coldlead.locales import Locale, detect_locale, get_locale
from coldlead.models import Company, Lead, LegalForm, RawSignals, make_lead_id

DEMO_MARK = " (demo)"

Archetype = Callable[[random.Random, Locale], dict]


def _legacy_gem(r: random.Random, loc: Locale) -> dict:
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


def _modern_leader(r: random.Random, loc: Locale) -> dict:
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


def _no_website(r: random.Random, loc: Locale) -> dict:
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


def _broken_mobile(r: random.Random, loc: Locale) -> dict:
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


def _toxic_owner(r: random.Random, loc: Locale) -> dict:
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


def _agency_locked(r: random.Random, loc: Locale) -> dict:
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
        agency=r.choice(loc.agencies),
    )


def _wix_midrange(r: random.Random, loc: Locale) -> dict:
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


def _chain(r: random.Random, loc: Locale) -> dict:
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


def _insolvent(r: random.Random, loc: Locale) -> dict:
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


def _solid_pdf(r: random.Random, loc: Locale) -> dict:
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


def _name(
    r: random.Random, loc: Locale, category: str, niche: str, city: str, used: set[str]
) -> str:
    """A base business name (no legal suffix) not yet in ``used``."""
    templates = loc.name_templates.get(category, loc.name_templates["generic"])
    niche_title = niche.strip().title() or loc.generic_niche
    for attempt in range(50):
        name = r.choice(templates).format(
            surname=r.choice(loc.surnames),
            first=r.choice(loc.first_names),
            place=r.choice(loc.place_words),
            city=city,
            niche=niche_title,
        )
        if attempt >= 40:
            name = f"{name} {r.choice(loc.surnames)}"
        if name not in used:
            used.add(name)
            return name
    return f"{name} {len(used) + 1}"


def demo_leads(
    niche: str,
    location: str,
    limit: int = 10,
    *,
    locale: Locale | str | None = None,
    country: str | None = None,
) -> list[Lead]:
    """Deterministic synthetic prospects.

    ``locale`` forces a pack (a :class:`Locale` or a code such as ``"it-IT"``); by default it is
    detected from ``location``, then ``country`` (ISO code), falling back to en-US.
    """
    if isinstance(locale, str):
        loc = get_locale(locale)
    else:
        loc = locale or detect_locale(location, country)
    niche = niche.strip() or loc.default_niche
    city = location.strip().title() or loc.default_city
    category = knowledge.detect_category(niche)
    rng = random.Random(_seed(niche, city))
    leads: list[Lead] = []
    used_names: set[str] = set()

    for index in range(max(0, limit)):
        profile = ARCHETYPES[index % len(ARCHETYPES)](rng, loc)
        archetype_form = profile["legal"]
        suffix, legal = loc.legal_name(archetype_form)
        base_name = _name(rng, loc, category, niche, city, used_names)
        slug = _slug(base_name)
        name = base_name + suffix
        if profile.get("insolvent"):
            name += loc.insolvency_suffix
        # Demo names can coincide with real businesses in real towns: always mark them as fictitious.
        name = f"{name}{DEMO_MARK}"
        website = f"https://www.{slug}.example" if profile["website"] else None
        if website and profile.get("ssl") is False:
            website = website.replace("https://", "http://")

        contact = profile["contact"]
        person = f"{rng.choice(loc.first_names)} {rng.choice(loc.surnames)}"
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

        reviewer = rng.choice(loc.reviewers)
        if profile.get("toxic"):
            replies = list(loc.toxic_replies)
        elif profile.get("reply", 0) > 0:
            replies = [rng.choice(loc.polite_replies).format(reviewer=reviewer, city=city)]
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
        # Keyword arguments are evaluated in order: address → phone → VAT → staff keeps every
        # pack's random sequence stable, hence its output reproducible.
        company = Company(
            name=name,
            niche=niche,
            city=city,
            address=loc.address(rng, city),
            phone=loc.phone(rng, contact in ("mobile", "owner_whatsapp"), city),
            email=f"info@{slug}.example" if contact != "mobile" else "",
            vat_number=loc.vat_number(rng),
            legal_form=legal,
            employees_estimate={LegalForm.SPA: 80, LegalForm.SRL: rng.randint(4, 25)}.get(
                archetype_form
            ),
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
