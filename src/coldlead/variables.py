"""The 8 normalized POS variables (each in [0, 10]) with human-readable explanations.

Every function here is pure: raw signals in, ``(value, reasons)`` out. No I/O, no clock.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from coldlead import knowledge
from coldlead.models import Lead, LegalForm


@dataclass(frozen=True)
class VariableSpec:
    key: str
    weight_key: str
    name: str
    short: str
    description: str


VARIABLES: tuple[VariableSpec, ...] = (
    VariableSpec(
        "G_dig",
        "w_G",
        "Digital & AI Readiness Gap",
        "Digital gap",
        "How obsolete the web presence is: slow, not mobile, legacy CMS, or no site at all.",
    ),
    VariableSpec(
        "V_ticket",
        "w_T",
        "Ticket Value & Margin",
        "Ticket value",
        "Sector margin: +5% conversions on a yacht charter is worth far more than on a bar.",
    ),
    VariableSpec(
        "F_fin",
        "w_F",
        "Financial Strength & Legal Form",
        "Financial strength",
        "Ability to pay: S.p.A./S.r.l. with staff vs. tiny sole traders.",
    ),
    VariableSpec(
        "C_press",
        "w_P",
        "Local Competitive Pressure",
        "Competition",
        "How far the top local competitors are ahead online (speed, booking, reviews).",
    ),
    VariableSpec(
        "M_reach",
        "w_I",
        "Foreign Market Friction",
        "Foreign reach",
        "International customers (tourism hubs, luxury) served by a single-language site.",
    ),
    VariableSpec(
        "A_decision",
        "w_D",
        "Decision-Maker Accessibility",
        "Owner access",
        "How easy it is to reach whoever signs the cheque (WhatsApp, mobile, LinkedIn).",
    ),
    VariableSpec(
        "B_care",
        "w_C",
        "Brand Care & Digital Sensitivity",
        "Brand care",
        "Does the owner reply to reviews, promptly and politely?",
    ),
    VariableSpec(
        "U_vibe",
        "w_A",
        "VibeCoding Surface (Automation Potential)",
        "Automation",
        "Manual processes replaceable in 24h by a micro-tool: PDF menus, no booking, no bot.",
    ),
)
VARIABLE_KEYS: tuple[str, ...] = tuple(v.key for v in VARIABLES)
WEIGHT_TO_VARIABLE: dict[str, str] = {v.weight_key: v.key for v in VARIABLES}

Result = tuple[float, list[str]]


def _clamp(value: float) -> float:
    return round(min(10.0, max(0.0, value)), 1)


def digital_gap(lead: Lead) -> Result:
    s = lead.raw_signals
    if not s.has_website or not s.website_url:
        return 10.0, ["No website at all → maximum digital gap"]
    reasons: list[str] = []
    if s.lighthouse_performance is None:
        perf = 50
        reasons.append("Performance unknown → assumed 50/100")
    else:
        perf = s.lighthouse_performance
    value = (100 - perf) / 10 * 0.6
    origin = " (estimated)" if s.performance_source == "estimated" else ""
    reasons.append(f"Performance {perf}/100{origin} → +{value:.1f}")
    if s.mobile_friendly is False:
        value += 2.0
        reasons.append("Not mobile-friendly (no responsive viewport) → +2.0")
    if s.has_ssl is False:
        value += 1.5
        reasons.append("No HTTPS/SSL → +1.5")
    if s.has_booking_system is False:
        value += 1.0
        reasons.append("No online booking or quote tool → +1.0")
    penalty, label = knowledge.legacy_stack_penalty(s.cms_stack)
    if penalty:
        value += penalty
        reasons.append(f"{label} → +{penalty}")
    return _clamp(value), reasons


def ticket_value(lead: Lead) -> Result:
    if lead.raw_signals.ticket_value_hint is not None:
        value = lead.raw_signals.ticket_value_hint
        return _clamp(value), [f"Ticket value provided explicitly → {value}"]
    value, keyword = knowledge.ticket_value(lead.company.niche)
    if keyword:
        return value, [f"Sector '{lead.company.niche}' matches '{keyword}' → {value}"]
    return value, [
        f"Sector '{lead.company.niche or 'unknown'}' not in high-margin tables → {value}"
    ]


def financial_strength(lead: Lead) -> Result:
    form = lead.company.legal_form
    if form is LegalForm.UNKNOWN:
        form = knowledge.parse_legal_form(lead.company.name)
    if form is LegalForm.UNKNOWN:
        value, reasons = 5.0, ["Legal form unknown → neutral 5.0"]
    else:
        value = knowledge.LEGAL_FORM_SCORES[form]
        reasons = [f"Legal form: {knowledge.LEGAL_FORM_LABELS.get(form, form.value)} → {value}"]
    employees = lead.company.employees_estimate
    if employees is not None:
        if employees >= 10:
            value += 1.0
            reasons.append(f"{employees} employees → +1.0")
        elif employees == 0:
            value -= 1.0
            reasons.append("No employees → -1.0")
    return _clamp(value), reasons


def competitive_pressure(lead: Lead, peer_pressure: float | None = None) -> Result:
    s = lead.raw_signals
    if s.competitor_pressure is not None:
        return _clamp(s.competitor_pressure), [
            f"Competitor pressure provided → {s.competitor_pressure}"
        ]
    if peer_pressure is not None:
        return _clamp(peer_pressure), [
            f"Top-2 local competitors in this session vs. this lead → {peer_pressure:.1f}"
        ]
    notes = s.competitor_notes.lower()
    if any(k in notes for k in ("domin", "forte", "strong", "booking online", "moderni", "modern")):
        return 8.0, ["Competitor notes describe strong, modern rivals → 8.0"]
    return 5.0, ["No competitor data → neutral 5.0"]


def foreign_reach(lead: Lead) -> Result:
    s = lead.raw_signals
    city, niche = lead.company.city, lead.company.niche
    reasons: list[str] = []
    if s.international_clientele is not None:
        exposed = s.international_clientele
        reasons.append("International clientele " + ("confirmed" if exposed else "excluded"))
    else:
        hub = knowledge.is_tourist_hub(city)
        intl_niche = any(knowledge.keyword_in(k, niche) for k in knowledge.INTERNATIONAL_NICHES)
        exposed = hub or intl_niche
        if hub:
            reasons.append(f"{city} is an international tourism hub")
        if intl_niche:
            reasons.append(f"'{niche}' serves international customers")
    if not exposed:
        return (2.0 if s.has_multilingual else 3.0), [
            *reasons,
            "Mostly local market → low friction",
        ]
    if not s.has_website:
        return 9.0, [*reasons, "No website to serve foreign customers → 9.0"]
    if s.has_multilingual is False:
        return 9.5, [*reasons, "Site is single-language → foreign revenue lost daily (9.5)"]
    if s.has_multilingual is None:
        return 6.5, [*reasons, "Multilingual support unknown → 6.5"]
    return 4.0, [*reasons, "Site already multilingual → residual friction 4.0"]


def _is_mobile_number(phone: str) -> bool:
    """Mobile by national prefix (locale packs); an empty prefix list never matches."""
    digits = "".join(c for c in phone if c.isdigit() or c == "+")
    return (
        bool(knowledge.MOBILE_PREFIXES)
        and digits.startswith(knowledge.MOBILE_PREFIXES)
        and len(digits.lstrip("+")) >= 9
    )


def owner_access(lead: Lead) -> Result:
    c = lead.company
    channels = " ".join(c.contact_channels).lower()
    if lead.raw_signals.is_chain:
        return 1.5, ["Chain / franchise: decisions taken elsewhere → 1.5"]
    if c.direct_contact_person and "whatsapp" in channels:
        return 9.5, [f"Owner named ({c.direct_contact_person}) and reachable on WhatsApp → 9.5"]
    if c.direct_contact_person or "whatsapp" in channels:
        who = c.direct_contact_person or "WhatsApp channel"
        return 9.0, [f"Direct line to the decision maker ({who}) → 9.0"]
    if "linkedin" in channels:
        return 8.0, ["Decision maker on LinkedIn → 8.0"]
    if c.phone and ("mobile" in channels or _is_mobile_number(c.phone)):
        return 7.5, ["Mobile phone number published → 7.5"]
    if c.phone:
        return 6.0, ["Landline only → 6.0"]
    if c.email:
        return 4.5, ["Generic email only → 4.5"]
    return 3.0, ["No direct contact channel found → 3.0"]


def brand_care(lead: Lead) -> Result:
    s = lead.raw_signals
    if s.is_toxic_owner:
        return 1.0, ["Hostile replies to reviews → 1.0"]
    if s.owner_reply_rate is None:
        return 5.0, ["Owner reply rate unknown → neutral 5.0"]
    rate = s.owner_reply_rate
    if rate >= 70:
        return 9.0, [f"Owner replies to {rate:.0f}% of reviews → 9.0"]
    if rate >= 30:
        return 6.0, [f"Owner replies to {rate:.0f}% of reviews → 6.0"]
    if rate > 0:
        return 4.0, [f"Owner rarely replies ({rate:.0f}%) → 4.0"]
    return 2.0, ["Owner never replies to reviews → 2.0"]


def automation_surface(lead: Lead) -> Result:
    s = lead.raw_signals
    value, reasons = 5.0, ["Baseline 5.0"]
    if s.has_booking_system is False or not s.has_website:
        value += 2.5
        reasons.append("Bookings/quotes handled manually → +2.5")
    if s.has_ai_chat is False or not s.has_website:
        value += 1.5
        reasons.append("No chat or FAQ bot → +1.5")
    if s.has_pdf_menu:
        value += 1.5
        reasons.append("Heavy PDF menu/price list → +1.5")
    if s.has_booking_system and s.has_ai_chat:
        value -= 2.0
        reasons.append("Booking and chat already automated → -2.0")
    return _clamp(value), reasons


CALCULATORS: dict[str, Callable[..., Result]] = {
    "G_dig": digital_gap,
    "V_ticket": ticket_value,
    "F_fin": financial_strength,
    "C_press": competitive_pressure,
    "M_reach": foreign_reach,
    "A_decision": owner_access,
    "B_care": brand_care,
    "U_vibe": automation_surface,
}


def compute_variables(
    lead: Lead, peer_pressure: float | None = None
) -> tuple[dict[str, float], dict[str, list[str]]]:
    values: dict[str, float] = {}
    explanations: dict[str, list[str]] = {}
    for key, fn in CALCULATORS.items():
        value, reasons = fn(lead, peer_pressure) if key == "C_press" else fn(lead)
        values[key] = float(value)
        explanations[key] = reasons
    return values, explanations


def digital_quality(lead: Lead) -> float:
    """0-10 composite of how strong a business is online. Used to compare local peers."""
    s = lead.raw_signals
    if not s.has_website:
        base = 0.0
    else:
        base = (
            s.lighthouse_performance if s.lighthouse_performance is not None else 50
        ) / 20  # 0-5
        base += 1.5 if s.has_booking_system else 0.0
        base += 1.0 if s.has_multilingual else 0.0
        base += 0.5 if s.mobile_friendly else 0.0
    if s.average_rating is not None and s.reviews_count:
        base += max(0.0, s.average_rating - 3.0)  # 0-2
    return min(10.0, base)
