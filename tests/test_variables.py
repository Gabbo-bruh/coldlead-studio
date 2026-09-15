from __future__ import annotations

import pytest

from coldlead import knowledge
from coldlead.models import Company, LegalForm
from coldlead.variables import (
    automation_surface,
    brand_care,
    competitive_pressure,
    digital_gap,
    financial_strength,
    foreign_reach,
    owner_access,
    ticket_value,
)
from tests.conftest import make_lead


def test_no_website_is_max_gap():
    value, reasons = digital_gap(make_lead(has_website=False, website_url=None))
    assert value == 10.0
    assert "No website" in reasons[0]


def test_digital_gap_penalties():
    good = digital_gap(
        make_lead(lighthouse_performance=95, has_booking_system=True, cms_stack="Next.js")
    )[0]
    bad = digital_gap(
        make_lead(
            lighthouse_performance=20, mobile_friendly=False, has_ssl=False, cms_stack="Joomla 3"
        )
    )[0]
    assert good < 1.0
    assert bad == 10.0


def test_unknown_performance_is_neutral():
    value, reasons = digital_gap(
        make_lead(lighthouse_performance=None, has_booking_system=None, cms_stack=None)
    )
    assert value == 3.0
    assert any("unknown" in r for r in reasons)


@pytest.mark.parametrize(
    ("niche", "expected"),
    [
        ("Yacht charter", 10.0),
        ("Charter nautico", 9.5),
        ("Noleggio barche", 8.0),  # 'barche' must not match the 'bar ' rule
        ("Studio dentistico", 9.0),
        ("Ristorante di pesce", 6.5),
        ("Bar pizzeria", 4.5),
        ("Bar", 3.5),
        ("Barbiere", 4.0),
        ("Something else", knowledge.DEFAULT_TICKET_VALUE),
    ],
)
def test_ticket_value(niche, expected):
    company = Company(name="X", niche=niche, city="Milano")
    assert ticket_value(make_lead(company=company))[0] == expected


def test_ticket_value_hint_overrides():
    assert ticket_value(make_lead(ticket_value_hint=2.0))[0] == 2.0


@pytest.mark.parametrize(
    ("name", "form"),
    [
        ("Rossi S.r.l.", LegalForm.SRL),
        ("Rossi SRL", LegalForm.SRL),
        ("Rossi S.r.l.s.", LegalForm.SRLS),
        ("Bianchi S.p.A.", LegalForm.SPA),
        ("Da Vittorio & Figli S.n.c.", LegalForm.SNC_SAS),
        ("Tigullio Marine D.I.", LegalForm.SOLE_TRADER),
        ("Studio Legale Verdi", LegalForm.PROFESSIONAL),
        ("Acme Ltd", LegalForm.LTD),
        ("Bar Centrale", LegalForm.UNKNOWN),
    ],
)
def test_legal_form_parsing(name, form):
    assert knowledge.parse_legal_form(name) == form


def test_financial_strength_uses_parsed_name_and_employees():
    company = Company(name="Grande Hotel S.p.A.", niche="Hotel", city="Como", employees_estimate=50)
    assert financial_strength(make_lead(company=company))[0] == 10.0
    tiny = Company(
        name="Gianni",
        niche="Officina",
        city="Asti",
        legal_form=LegalForm.SOLE_TRADER,
        employees_estimate=0,
    )
    assert financial_strength(make_lead(company=tiny))[0] == 2.0
    # explanations read in English; the stored enum value (schema contract) is unchanged
    assert financial_strength(make_lead(company=tiny))[1][0] == "Legal form: sole trader → 3.0"
    assert tiny.legal_form.value == "Ditta Individuale"
    assert set(knowledge.LEGAL_FORM_LABELS) == set(knowledge.LEGAL_FORM_SCORES)


def test_competitive_pressure_sources():
    assert competitive_pressure(make_lead(competitor_pressure=7.5))[0] == 7.5
    assert competitive_pressure(make_lead(), peer_pressure=8.2)[0] == 8.2
    assert competitive_pressure(make_lead(competitor_notes="Rivals dominate Google"))[0] == 8.0
    assert competitive_pressure(make_lead())[0] == 5.0


def test_foreign_reach():
    assert foreign_reach(make_lead())[0] == 9.5  # tourist hub + single language
    assert foreign_reach(make_lead(has_multilingual=True))[0] == 4.0
    local = Company(name="Officina", niche="Autofficina", city="Voghera")
    assert foreign_reach(make_lead(company=local))[0] == 3.0
    assert foreign_reach(make_lead(company=local, international_clientele=True))[0] == 9.5


def test_owner_access_ladder():
    assert owner_access(make_lead())[0] == 9.5
    chain = make_lead(is_chain=True)
    assert owner_access(chain)[0] == 1.5
    mobile_only = Company(name="Gianni", niche="x", city="y", phone="+39 347 000 0001")
    assert owner_access(make_lead(company=mobile_only))[0] == 7.5
    landline = Company(name="Gianni", niche="x", city="y", phone="+39 0185 000002")
    assert owner_access(make_lead(company=landline))[0] == 6.0
    nothing = Company(name="Gianni", niche="x", city="y")
    assert owner_access(make_lead(company=nothing))[0] == 3.0
    # North American numbers carry no mobile prefix: only an explicit channel says "mobile".
    us_mobile = Company(name="Joe", niche="x", city="Miami", phone="+1 305-555-0101")
    assert owner_access(make_lead(company=us_mobile))[0] == 6.0
    us_mobile.contact_channels.append("Mobile")
    assert owner_access(make_lead(company=us_mobile))[0] == 7.5


@pytest.mark.parametrize(
    ("rate", "expected"), [(90, 9.0), (50, 6.0), (10, 4.0), (0, 2.0), (None, 5.0)]
)
def test_brand_care(rate, expected):
    assert brand_care(make_lead(owner_reply_rate=rate))[0] == expected


def test_brand_care_toxic():
    assert brand_care(make_lead(is_toxic_owner=True))[0] == 1.0


def test_automation_surface():
    assert automation_surface(make_lead(has_pdf_menu=True))[0] == 10.0
    assert automation_surface(make_lead(has_booking_system=True, has_ai_chat=True))[0] == 3.0


def test_keyword_boundaries():
    assert knowledge.detect_category("Noleggio barche") == "nautical"
    assert knowledge.detect_category("Barber shop") == "beauty"
    assert knowledge.detect_category("Bar tabacchi") == "cafe_bar"
    assert knowledge.detect_category("Studio dentistico") == "clinic"
    assert knowledge.detect_category("Qualcosa di strano") == "generic"
    assert knowledge.is_tourist_hub("Santa Margherita Ligure")
    assert not knowledge.is_tourist_hub("Voghera")


@pytest.mark.parametrize(
    ("english", "italian"),
    [
        ("Lawyer", "Avvocato"),
        ("Architect", "Architetto"),
        ("Notary", "Notaio"),
        ("Accountant", "Commercialista"),
        ("Orthodontist", "Ortodontista"),
        ("Physiotherapist", "Fisioterapista"),
        ("Auto mechanic", "Autofficina"),
        ("Optician", "Ottica"),
        ("Florist", "Fiorista"),
        ("Pastry shop", "Pasticceria"),
        ("Limousine service", "NCC"),
    ],
)
def test_english_niches_score_like_their_italian_twins(english, italian):
    assert knowledge.detect_category(english) == knowledge.detect_category(italian) != "generic"
    assert knowledge.ticket_value(english)[0] == knowledge.ticket_value(italian)[0]


@pytest.mark.parametrize(
    "niche", ["Surgelati", "Limoncello", "Consultorio familiare", "Salone del mobile"]
)
def test_english_stems_do_not_capture_italian_words(niche):
    assert knowledge.detect_category(niche) == "generic"
    assert knowledge.ticket_value(niche) == (knowledge.DEFAULT_TICKET_VALUE, None)
