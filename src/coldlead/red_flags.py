"""Penalty filter: discard toxic owners and insolvent businesses before wasting a minute on them."""

from __future__ import annotations

import re

from coldlead import knowledge
from coldlead.models import Lead, RedFlag


def _first_match(patterns: tuple[str, ...], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def evaluate_red_flags(lead: Lead) -> list[RedFlag]:
    s = lead.raw_signals
    flags: list[RedFlag] = []

    if s.is_toxic_owner:
        sample = f" e.g. “{s.sample_owner_replies[0][:100]}”" if s.sample_owner_replies else ""
        flags.append(
            RedFlag(
                code="TOXIC_OWNER",
                severity="CRITICAL",
                description="Owner answers reviews aggressively, threatening or insulting customers.",
                evidence=f"Tone classified as '{s.owner_sentiment_tone or 'toxic'}'{sample}",
            )
        )
    else:
        for reply in s.sample_owner_replies:
            hit = _first_match(knowledge.TOXIC_REPLY_PATTERNS, reply)
            if hit:
                flags.append(
                    RedFlag(
                        code="LITIGIOUS_OWNER",
                        severity="CRITICAL",
                        description="Owner threatens legal action or insults reviewers publicly.",
                        evidence=f"“{hit}” in reply: “{reply[:120]}”",
                    )
                )
                break

    status = (s.business_status or "").upper()
    if status in knowledge.CLOSED_STATUSES:
        flags.append(
            RedFlag(
                code="INSOLVENCY_RISK",
                severity="CRITICAL",
                description="Business is closed, in liquidation or under insolvency proceedings.",
                evidence=f"Business status: {status}",
            )
        )
    else:
        haystack = " ".join((lead.company.name, s.competitor_notes, lead.notes))
        hit = _first_match(knowledge.INSOLVENCY_PATTERNS, haystack)
        if hit:
            flags.append(
                RedFlag(
                    code="INSOLVENCY_RISK",
                    severity="CRITICAL",
                    description="Signals of liquidation, bankruptcy or cessation.",
                    evidence=f"“{hit}” associated with the company",
                )
            )

    if s.footer_agency_credit:
        flags.append(
            RedFlag(
                code="VENDOR_LOCKIN",
                severity="MEDIUM",
                description="Site maintained by a web agency credited in the footer: likely retainer or contract.",
                evidence=f"Footer credit: “{s.footer_agency_credit.strip()}”",
            )
        )

    return flags


def is_discarding(flag: RedFlag, discard_on_lockin: bool = False) -> bool:
    return flag.severity == "CRITICAL" or (discard_on_lockin and flag.code == "VENDOR_LOCKIN")
