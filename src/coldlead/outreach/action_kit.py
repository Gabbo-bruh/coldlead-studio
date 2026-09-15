"""Action Kit generator: 90s Loom script, cold email, WhatsApp opener and VibeCoding prompt.

Templates are deterministic and bilingual. When an LLM is configured, ``ai=True`` asks it to
rewrite the kit with the same structure, falling back to templates on any failure.
"""

from __future__ import annotations

import json

from coldlead.enrich.llm import complete_json
from coldlead.models import ActionKit, Lead
from coldlead.outreach import playbooks
from coldlead.settings import Settings

WHATSAPP_MAX_CHARS = 300


def _first_name(lead: Lead) -> str:
    person = lead.company.direct_contact_person.strip()
    return person.split()[0] if person else ""


def _opportunity(lead: Lead, lang: str) -> str:
    enriched = lead.enrichment
    if enriched.vibe_opportunity_summary and enriched.enriched_by != "heuristic":
        return enriched.vibe_opportunity_summary
    return playbooks.opportunity_summary(lead, lang)


def _rating_hook(lead: Lead, lang: str) -> str:
    s = lead.raw_signals
    if s.average_rating and s.reviews_count and s.average_rating >= 4.2:
        return (
            f"le vostre {s.reviews_count} recensioni con una media di {s.average_rating}/5"
            if lang == "it"
            else f"your {s.reviews_count} reviews averaging {s.average_rating}/5"
        )
    return (
        f"il lavoro che fate a {lead.company.city}"
        if lang == "it"
        else f"the work you do in {lead.company.city}"
    )


def _whatsapp(lead: Lead, lang: str, opportunity: str, issue: str) -> str:
    name = _first_name(lead)
    if lang == "it":
        greet = f"Ciao {name}!" if name else "Buongiorno!"
        text = (
            f"{greet} Ho visto {lead.company.name} e noto che {issue[0].lower() + issue[1:]}. "
            f"Ho preparato una demo gratuita: {opportunity[0].lower() + opportunity[1:]}. "
            "Te la giro qui da provare dal telefono?"
        )
    else:
        greet = f"Hi {name}!" if name else "Hi!"
        text = (
            f"{greet} I came across {lead.company.name} and noticed {issue[0].lower() + issue[1:]}. "
            f"I built a free demo: {opportunity[0].lower() + opportunity[1:]}. "
            "Can I send it here so you can try it on your phone?"
        )
    if len(text) <= WHATSAPP_MAX_CHARS:
        return text
    short_offer = opportunity.split(",")[0].split(" con ")[0].split(" with ")[0]
    text = (
        f"{greet} Ho visto {lead.company.name}: ho preparato una demo gratuita ({short_offer.lower()}). "
        "Te la mando qui da provare dal telefono?"
        if lang == "it"
        else f"{greet} I saw {lead.company.name} and built a free demo ({short_offer.lower()}). "
        "Can I send it here for you to try?"
    )
    return text[:WHATSAPP_MAX_CHARS]


def template_kit(lead: Lead, lang: str = "en") -> ActionKit:
    lang = lang if lang in playbooks.LANGUAGES else "en"
    c, s = lead.company, lead.raw_signals
    opportunity = _opportunity(lead, lang)
    issues = playbooks.frictions(lead, lang) or [
        "il sito non trasforma le visite in richieste"
        if lang == "it"
        else "the site doesn't turn visits into requests"
    ]
    top_issues = issues[:2]
    name = _first_name(lead)
    site = s.website_url or ("la vostra scheda Google" if lang == "it" else "your Google listing")
    hook = _rating_hook(lead, lang)
    llm_lever = lead.enrichment.enriched_by != "heuristic" and lead.enrichment.psychological_lever
    lever = llm_lever or playbooks.psychological_lever(lead, lang)

    if lang == "it":
        hello = f"Ciao {name}" if name else "Buongiorno"
        loom = "\n".join(
            [
                f"SCRIPT LOOM 90 SECONDI — {c.name} ({c.city})",
                f"Inquadratura: {site} aperto su smartphone (o emulatore), la tua faccia in basso a sinistra.",
                "",
                "[00:00–00:15] GANCIO E COMPLIMENTO SINCERO",
                f"“{hello}, sono [Tuo Nome]. Ho guardato {hook}: complimenti davvero, si vede la cura che ci mettete.”",
                "",
                "[00:15–00:45] IL COLLO DI BOTTIGLIA",
                (
                    "“Aprendo il sito dal telefono"
                    if s.has_website
                    else "“Cercandovi su Google dal telefono"
                )
                + (
                    " ho notato due cose che oggi vi fanno perdere richieste:"
                    if len(top_issues) > 1
                    else " ho notato una cosa che oggi vi fa perdere richieste:"
                ),
                *[f"  {i}. {issue}." for i, issue in enumerate(top_issues, 1)],
                "Chi cerca da mobile decide in pochi secondi, e se non trova subito cosa gli serve va altrove.”",
                "",
                "[00:45–01:15] LA SOLUZIONE VIBECODING (GIÀ PRONTA)",
                f"“Invece del solito progetto da tre mesi, ho già preparato una demo funzionante: {opportunity}. "
                "Si apre in mezzo secondo e porta il cliente dalla visita alla richiesta in 30 secondi.”",
                "",
                "[01:15–01:30] CALL TO ACTION A ZERO ATTRITO",
                "“Nessun impegno: ti va se ti giro il link su WhatsApp e la provi due minuti dal telefono? "
                "Se non ti convince, ti tieni comunque l'analisi. Buon lavoro!”",
                "",
                f"Leva psicologica: {lever}.",
            ]
        )
        subject = f"Un dettaglio sul sito di {c.name} da smartphone ({c.city})"
        email = "\n".join(
            [
                f"{hello},",
                "",
                f"ho guardato {site} dal telefono e ho notato che {top_issues[0][0].lower() + top_issues[0][1:]}"
                + (
                    f", e che {top_issues[1][0].lower() + top_issues[1][1:]}"
                    if len(top_issues) > 1
                    else ""
                )
                + ".",
                "",
                f"Visto {hook}, mi sembrava un peccato: così ho preparato un'anteprima funzionante di",
                f"→ {opportunity}.",
                "",
                "Carica in meno di un secondo ed è pensata per trasformare le visite in richieste dirette.",
                "Ti va di vederla? Sono 60 secondi, da telefono, senza impegno.",
                "",
                "Un saluto,",
                "[Tuo Nome] · [WhatsApp]",
                "",
                "P.S. Se preferisci non ricevere altre email, rispondi “no grazie” e non ti scriverò più.",
            ]
        )
    else:
        hello = f"Hi {name}" if name else "Hi there"
        loom = "\n".join(
            [
                f"90-SECOND LOOM SCRIPT — {c.name} ({c.city})",
                f"Framing: {site} open on a phone (or emulator), your face bottom-left.",
                "",
                "[00:00–00:15] HOOK & GENUINE COMPLIMENT",
                f"“{hello}, I'm [Your Name]. I looked at {hook} — genuinely impressive, the care really shows.”",
                "",
                "[00:15–00:45] THE BOTTLENECK",
                (
                    "“Opening your site on my phone"
                    if s.has_website
                    else "“Searching for you on Google from my phone"
                )
                + (
                    " I noticed two things that are costing you enquiries today:"
                    if len(top_issues) > 1
                    else " I noticed one thing that is costing you enquiries today:"
                ),
                *[f"  {i}. {issue}." for i, issue in enumerate(top_issues, 1)],
                "Mobile visitors decide in seconds; if they can't find what they need, they go elsewhere.”",
                "",
                "[00:45–01:15] THE VIBECODING SOLUTION (ALREADY BUILT)",
                f"“Instead of a three-month project, I already built a working demo: {opportunity}. "
                "It loads in half a second and takes a visitor from browsing to enquiry in 30 seconds.”",
                "",
                "[01:15–01:30] ZERO-FRICTION CALL TO ACTION",
                "“No strings attached: can I send you the link on WhatsApp so you can try it for two minutes? "
                "If it's not for you, keep the audit anyway. Have a great day!”",
                "",
                f"Psychological lever: {lever}.",
            ]
        )
        subject = f"A detail about {c.name}'s website on mobile ({c.city})"
        email = "\n".join(
            [
                f"{hello},",
                "",
                f"I opened {site} on my phone and noticed that {top_issues[0][0].lower() + top_issues[0][1:]}"
                + (
                    f", and that {top_issues[1][0].lower() + top_issues[1][1:]}"
                    if len(top_issues) > 1
                    else ""
                )
                + ".",
                "",
                f"Given {hook}, that felt like a shame — so I put together a working preview of",
                f"→ {opportunity}.",
                "",
                "It loads in under a second and is built to turn visits into direct enquiries.",
                "Would you like to see it? It takes 60 seconds, from your phone, no strings attached.",
                "",
                "Best,",
                "[Your Name] · [WhatsApp]",
                "",
                "P.S. If you'd rather not hear from me again, just reply “no thanks”.",
            ]
        )

    ui_language = "Italian" if lang == "it" else "English"
    contact_line = c.phone or "[phone]"
    rating = (
        f"{s.average_rating}★ ({s.reviews_count} reviews)"
        if s.average_rating
        else "no rating badge"
    )
    prompt = "\n".join(
        [
            f"Build a production-quality, mobile-first single-page prototype for “{c.name}”, "
            f"a {c.niche} business in {c.city}.",
            "",
            f"Core feature: {playbooks.opportunity_summary(lead, 'en')}.",
            f"Problems it must solve: {'; '.join(playbooks.frictions(lead, 'en')[:3]) or 'low conversion from mobile visits'}.",
            "",
            "Stack: Next.js (App Router) + TypeScript + Tailwind CSS, no backend required (static export).",
            f"Copy language: {ui_language}"
            + (" with an EN/DE language switch." if lang == "it" else "."),
            "",
            "Sections:",
            f"1. Sticky header: logo wordmark, Google rating badge ({rating}), “Call / WhatsApp” button ({contact_line}).",
            "2. Hero with a benefit-driven headline for local and international customers, one primary CTA.",
            "3. The interactive component: step-by-step selector with live price/availability preview.",
            "4. Two-field final form that opens https://wa.me/<number>?text=<pre-filled summary>.",
            "5. Social proof strip and a compact FAQ (5 questions).",
            "",
            "Quality bar: Lighthouse 95+ on mobile, accessible (WCAG AA), no layout shift, "
            "fluid micro-interactions, premium typography, realistic placeholder content.",
        ]
    )

    return ActionKit(
        language=lang,
        vibe_opportunity_summary=opportunity,
        loom_script_90s=loom,
        cold_email_subject=subject,
        cold_email=email,
        whatsapp_opener=_whatsapp(lead, lang, opportunity, top_issues[0]),
        vibecoding_prompt=prompt,
        generated_by="templates",
    )


AI_SYSTEM = (
    "You are a senior B2B copywriter for a VibeCoding studio that ships micro-apps in 24-48 hours. "
    "You write warm, specific, non-pushy outreach. Never invent facts beyond the data provided. "
    "Reply with one JSON object only."
)


def generate_action_kit(
    lead: Lead, lang: str = "en", *, ai: bool = False, settings: Settings | None = None
) -> ActionKit:
    base = template_kit(lead, lang)
    if not ai or settings is None or not settings.llm_enabled:
        return base
    language = "Italian" if base.language == "it" else "English"
    prompt = (
        f"Rewrite this outreach kit in {language}, keeping structure and facts, making it more natural "
        "and specific to the business. Keep the Loom script timed sections (0:00-0:15, 0:15-0:45, "
        "0:45-1:15, 1:15-1:30), the WhatsApp opener under 300 characters, and the email under 140 words.\n\n"
        f"Business data: {json.dumps(lead.model_dump(mode='json', include={'company', 'raw_signals'}), ensure_ascii=False)}\n\n"
        f"Draft kit: {base.model_dump_json(include={'loom_script_90s', 'cold_email_subject', 'cold_email', 'whatsapp_opener'})}\n\n"
        'Return JSON with keys: "loom_script_90s", "cold_email_subject", "cold_email", "whatsapp_opener".'
    )
    data = complete_json(prompt, settings, system=AI_SYSTEM)
    if not data:
        return base
    updates = {
        k: str(v)
        for k, v in data.items()
        if k in {"loom_script_90s", "cold_email_subject", "cold_email", "whatsapp_opener"} and v
    }
    if len(updates.get("whatsapp_opener", "")) > WHATSAPP_MAX_CHARS:
        updates.pop("whatsapp_opener")
    return base.model_copy(update={**updates, "generated_by": f"llm:{settings.llm_provider}"})
