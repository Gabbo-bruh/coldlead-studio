"""VibeCoding playbooks: which 24-48h micro-product to pitch, and why, for each lead.

All functions are pure and bilingual (``it`` / ``en``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from coldlead import knowledge
from coldlead.models import Lead

LANGUAGES = ("it", "en")


@dataclass(frozen=True)
class Offer:
    code: str
    it: str
    en: str
    applies: Callable[[Lead], bool]

    def text(self, lang: str) -> str:
        return self.it if lang == "it" else self.en


def _always(_: Lead) -> bool:
    return True


def _exposed(lead: Lead) -> bool:
    s = lead.raw_signals
    if s.international_clientele is not None:
        return s.international_clientele
    return knowledge.is_tourist_hub(lead.company.city) or any(
        knowledge.keyword_in(k, lead.company.niche) for k in knowledge.INTERNATIONAL_NICHES
    )


def _manual(lead: Lead) -> bool:
    return not lead.raw_signals.has_booking_system


CATEGORY_OFFERS: dict[str, Offer] = {
    "nautical": Offer(
        "charter_calculator",
        "Calcolatore istantaneo di preventivi charter (barca, skipper, extra, disponibilità) in IT/EN/DE con conferma su WhatsApp",
        "Instant charter quote calculator (boat, skipper, extras, availability) in IT/EN/DE with WhatsApp confirmation",
        _always,
    ),
    "restaurant": Offer(
        "digital_menu",
        "Menù digitale interattivo con filtri allergeni, traduzioni automatiche e prenotazione tavolo su WhatsApp",
        "Interactive digital menu with allergen filters, auto-translations and WhatsApp table booking",
        _always,
    ),
    "cafe_bar": Offer(
        "qr_menu",
        "Menù digitale con QR code, ordini al tavolo e carta fedeltà digitale",
        "QR digital menu with table ordering and a digital loyalty card",
        _always,
    ),
    "hospitality": Offer(
        "direct_booking",
        "Booking engine diretto con concierge AI multilingua: meno commissioni OTA, più prenotazioni dirette",
        "Direct booking engine with a multilingual AI concierge: fewer OTA fees, more direct bookings",
        _always,
    ),
    "real_estate": Offer(
        "property_showcase",
        "Vetrina immobili ultra-veloce in Next.js con AI property matcher e raccolta lead riservata",
        "Ultra-fast Next.js property showcase with an AI property matcher and private lead capture",
        _always,
    ),
    "clinic": Offer(
        "appointments",
        "Prenotazione visite online + assistente WhatsApp per FAQ pre/post visita e promemoria automatici",
        "Online appointment booking + WhatsApp assistant for pre/post-visit FAQs and automatic reminders",
        _always,
    ),
    "beauty": Offer(
        "booking_bot",
        "Bot WhatsApp per prenotazioni con listino servizi e promemoria automatici anti no-show",
        "WhatsApp booking bot with service menu and automatic no-show reminders",
        _always,
    ),
    "professional": Offer(
        "fee_calculator",
        "Calcolatore preventivi/parcelle istantaneo + onboarding clienti con upload documenti",
        "Instant fee/quote calculator + client onboarding flow with document upload",
        _always,
    ),
    "fitness": Offer(
        "class_booking",
        "Prenotazione corsi e calcolatore abbonamenti con pass di prova in un tap",
        "Class booking and membership calculator with one-tap trial pass",
        _always,
    ),
    "automotive": Offer(
        "quote_configurator",
        "Configuratore preventivi (riparazione, noleggio, transfer) con passaggio diretto su WhatsApp",
        "Quote configurator (repair, rental, transfers) with direct WhatsApp handoff",
        _always,
    ),
    "retail": Offer(
        "whatsapp_catalog",
        "Catalogo prodotti mobile-first con ordini e prenotazioni via WhatsApp",
        "Mobile-first product catalogue with WhatsApp ordering and reservations",
        _always,
    ),
    "events": Offer(
        "event_configurator",
        "Configuratore pacchetti evento con stima istantanea del budget e richiesta disponibilità",
        "Event package configurator with instant budget estimate and availability request",
        _always,
    ),
    "generic": Offer(
        "quote_calculator",
        "Calcolatore di preventivi interattivo con invio diretto della richiesta su WhatsApp",
        "Interactive quote calculator that sends the request straight to WhatsApp",
        _always,
    ),
}

LANDING_OFFER = Offer(
    "landing_24h",
    "Landing page one-page ultra-veloce con modulo preventivo e pulsante WhatsApp, online in 24 ore",
    "Ultra-fast one-page landing site with quote form and WhatsApp button, live in 24 hours",
    lambda lead: not lead.raw_signals.has_website,
)
MULTILINGUAL_OFFER = Offer(
    "multilingual_replatform",
    "Replatforming veloce in Next.js con versione multilingua (EN/DE/FR) per intercettare i clienti esteri",
    "Fast Next.js replatforming with a multilingual version (EN/DE/FR) to capture foreign customers",
    lambda lead: _exposed(lead) and lead.raw_signals.has_multilingual is False,
)
REPLATFORM_OFFER = Offer(
    "replatform",
    "Replatforming da CMS lento a Next.js + Tailwind con Lighthouse 95+ e conversioni misurabili",
    "Replatforming from a slow CMS to Next.js + Tailwind with 95+ Lighthouse and measurable conversions",
    lambda lead: (
        (lead.raw_signals.lighthouse_performance or 100) < 45
        or lead.raw_signals.mobile_friendly is False
    ),
)
REVIEW_OFFER = Offer(
    "review_responder",
    "Risponditore AI alle recensioni Google nel tono di voce del brand",
    "AI Google-review responder in the brand's own tone of voice",
    lambda lead: (
        (lead.raw_signals.owner_reply_rate or 0) < 30
        and (lead.raw_signals.reviews_count or 0) >= 20
    ),
)


AUTOMATION_OFFER = Offer(
    "ai_ops_agent",
    "Agente AI operativo su WhatsApp collegato al booking esistente: FAQ, upsell e risposte alle recensioni",
    "Operational AI agent on WhatsApp wired to the existing booking system: FAQs, upsells and review replies",
    _always,
)


def _relevance(offer: Offer, lead: Lead) -> float:
    """How well an offer fits the observed signals (higher = pitch first)."""
    s = lead.raw_signals
    if offer is LANDING_OFFER:
        return 100.0
    if offer is REPLATFORM_OFFER:
        penalty, _ = knowledge.legacy_stack_penalty(s.cms_stack)
        return 62.0 + (10 if s.mobile_friendly is False else 0) + penalty * 4
    if offer is MULTILINGUAL_OFFER:
        return 64.0
    if offer is REVIEW_OFFER:
        return 45.0
    if offer is AUTOMATION_OFFER:
        return 40.0
    # Category offer: strongest when the manual process it replaces is visible.
    return (
        60.0
        + (15 if s.has_booking_system is False else -25 if s.has_booking_system else 0)
        + (8 if s.has_pdf_menu else 0)
    )


def offers(lead: Lead) -> list[Offer]:
    """Candidate offers that apply to this lead, most relevant first."""
    category = CATEGORY_OFFERS.get(
        knowledge.detect_category(lead.company.niche), CATEGORY_OFFERS["generic"]
    )
    candidates = [
        LANDING_OFFER,
        category,
        MULTILINGUAL_OFFER,
        REPLATFORM_OFFER,
        REVIEW_OFFER,
        AUTOMATION_OFFER,
    ]
    applicable = [offer for offer in candidates if offer.applies(lead)]
    return sorted(applicable, key=lambda offer: -_relevance(offer, lead))


def opportunity_summary(lead: Lead, lang: str = "it") -> str:
    return offers(lead)[0].text(lang)


def frictions(lead: Lead, lang: str = "it") -> list[str]:
    """Concrete, verifiable problems to mention in outreach (most persuasive first)."""
    s, city = lead.raw_signals, lead.company.city
    it = lang == "it"
    items: list[str] = []
    if not s.has_website:
        items.append(
            "Non avete un sito: chi vi cerca su Google trova solo i concorrenti"
            if it
            else "There is no website: people searching on Google only find your competitors"
        )
        return items
    if s.lighthouse_performance is not None and s.lighthouse_performance < 50:
        items.append(
            f"Il sito è lento da smartphone (performance {s.lighthouse_performance}/100)"
            if it
            else f"The site is slow on smartphones (performance {s.lighthouse_performance}/100)"
        )
    if s.mobile_friendly is False:
        items.append(
            "La pagina non si adatta allo schermo del telefono"
            if it
            else "The page does not adapt to phone screens"
        )
    if s.has_ssl is False:
        items.append(
            "Il sito non è protetto (HTTP): Chrome lo segnala come “Non sicuro”"
            if it
            else "The site is not secure (HTTP): Chrome flags it as “Not secure”"
        )
    if _exposed(lead) and s.has_multilingual is False:
        items.append(
            f"Il sito è solo in italiano, ma a {city} arrivano molti clienti internazionali"
            if it
            else f"The site is single-language, yet {city} attracts many international customers"
        )
    if s.has_pdf_menu:
        items.append(
            "Menù/listino in PDF pesante, scomodo da leggere da mobile"
            if it
            else "Heavy PDF menu/price list, painful to read on mobile"
        )
    if s.has_booking_system is False:
        items.append(
            "Non c'è modo di prenotare o chiedere un preventivo in 30 secondi"
            if it
            else "There is no way to book or get a quote in 30 seconds"
        )
    penalty, _ = knowledge.legacy_stack_penalty(s.cms_stack)
    if penalty >= 1.0:
        items.append(
            f"Tecnologia datata ({s.cms_stack})" if it else f"Outdated technology ({s.cms_stack})"
        )
    return items


def psychological_lever(lead: Lead, lang: str = "it") -> str:
    s = lead.raw_signals
    it = lang == "it"
    if _exposed(lead) and s.has_multilingual is False:
        return (
            "Fatturato estero perso ogni giorno: i turisti internazionali prenotano dai concorrenti"
            if it
            else "Foreign revenue lost every day: international visitors book with competitors"
        )
    if s.is_running_ads:
        return (
            "Stanno pagando pubblicità che atterra su un sito che non converte"
            if it
            else "They pay for ads that land on a site that doesn't convert"
        )
    if (s.competitor_pressure or 0) >= 7:
        return (
            "Invidia competitiva: i concorrenti vicini sono già più avanti online"
            if it
            else "Competitive envy: nearby competitors are already ahead online"
        )
    if not s.has_website or s.has_booking_system is False:
        return (
            "Tempo liberato: meno telefonate e messaggi ripetitivi, più richieste qualificate"
            if it
            else "Time freed up: fewer repetitive calls and messages, more qualified requests"
        )
    return (
        "Coerenza di brand: il sito non è all'altezza della reputazione che avete costruito"
        if it
        else "Brand consistency: the website doesn't live up to the reputation they've built"
    )


def sentiment_tone(lead: Lead) -> str:
    s = lead.raw_signals
    if s.is_toxic_owner:
        return "Aggressive & Litigious"
    if s.owner_reply_rate is None:
        return s.owner_sentiment_tone or "Unknown"
    if s.owner_reply_rate >= 60:
        return "Empathetic & Professional"
    if s.owner_reply_rate == 0:
        return "Ghost/Absent"
    return "Occasional"
