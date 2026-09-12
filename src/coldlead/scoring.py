"""Precision Opportunity Score engine — pure, deterministic, network-free.

    POS = [ Σ(w_i · V_i) / Σw_i × 10 ] × M_ads × M_friction × T_win (× lock-in penalty)

Scoring takes raw leads + a resolved :class:`ScoringConfig` and never mutates its inputs, so it
can run thousands of times per second over cached sessions (sliders, ``rescore``, MCP calls).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from coldlead import knowledge
from coldlead.config import ScoringConfig
from coldlead.models import ActionKit, Lead, LeadDossier, POSEvaluation, Tier
from coldlead.red_flags import evaluate_red_flags, is_discarding
from coldlead.variables import VARIABLES, compute_variables, digital_quality

RECOMMENDATIONS: dict[Tier, str] = {
    Tier.HOT: (
        "HOT LEAD — record a personalised 90-second Loom showing the mobile issue and send an "
        "interactive VibeCoding micro-prototype. Expected conversion > 20%."
    ),
    Tier.WARM: "WARM LEAD — send a surgical cold email with 2 screenshots of the specific issues found.",
    Tier.COLD: "LOW PRIORITY — low expected return. Don't invest time in mockups or custom audits.",
    Tier.RED_FLAG: "DISCARD — critical red flag (toxic owner or insolvency). Do not contact.",
}


@dataclass(frozen=True)
class ScoredLead:
    lead: Lead
    evaluation: POSEvaluation
    rank: int

    def to_dossier(self, action_kit: ActionKit | None = None) -> LeadDossier:
        return LeadDossier(
            id=self.lead.id,
            rank=self.rank,
            company=self.lead.company,
            raw_signals=self.lead.raw_signals,
            enrichment=self.lead.enrichment,
            source=self.lead.source,
            pos_evaluation=self.evaluation,
            action_kit=action_kit,
        )


def tier_label(tier: Tier, config: ScoringConfig) -> str:
    t1, t2 = config.thresholds["tier_1_min"], config.thresholds["tier_2_min"]
    return {
        Tier.HOT: f"Tier 1 — Hot Lead (POS >= {t1:g})",
        Tier.WARM: f"Tier 2 — Warm Lead ({t2:g} <= POS < {t1:g})",
        Tier.COLD: f"Tier 3 — Low Priority (POS < {t2:g})",
        Tier.RED_FLAG: "Discarded — Red Flag",
    }[tier]


def peer_pressures(leads: Iterable[Lead], min_group: int = 3) -> dict[str, float]:
    """Competitive pressure from the session itself.

    Leads are grouped by (sector category, city). For each lead we compare its digital quality
    with the average of its two strongest competitors: the further behind it is, the higher the
    pressure (and the more urgent the need). Groups smaller than ``min_group`` are skipped.
    """
    groups: dict[tuple[str, str], list[Lead]] = defaultdict(list)
    for lead in leads:
        key = (knowledge.detect_category(lead.company.niche), lead.company.city.strip().lower())
        groups[key].append(lead)
    result: dict[str, float] = {}
    for members in groups.values():
        if len(members) < min_group:
            continue
        quality = {lead.id: digital_quality(lead) for lead in members}
        for lead in members:
            rivals = sorted((q for lid, q in quality.items() if lid != lead.id), reverse=True)[:2]
            gap = sum(rivals) / len(rivals) - quality[lead.id]
            result[lead.id] = round(min(10.0, max(0.0, 5.0 + gap * 0.8)), 1)
    return result


def score_lead(
    lead: Lead, config: ScoringConfig, peer_pressure: float | None = None
) -> POSEvaluation:
    """Score a single lead. Pure function of (lead, config, peer_pressure)."""
    values, explanations = compute_variables(lead, peer_pressure)
    weights = config.weights
    total_weight = sum(weights.values())
    weighted = sum(weights[spec.weight_key] * values[spec.key] for spec in VARIABLES)
    base = weighted / total_weight * 10.0

    s = lead.raw_signals
    running_ads = bool(s.is_running_ads)
    friction = s.has_website and (s.has_ssl is False or s.mobile_friendly is False)
    flags = evaluate_red_flags(lead)
    lockin = any(f.code == "VENDOR_LOCKIN" for f in flags)

    multipliers = {
        "m_ads": config.multipliers["m_ads_active"] if running_ads else 1.0,
        "m_friction": config.multipliers["m_friction_high"] if friction else 1.0,
        "t_win": config.t_win,
        "m_lockin": config.multipliers["m_lockin_penalty"] if lockin else 1.0,
    }
    uncapped = base
    for factor in multipliers.values():
        uncapped *= factor
    final = round(min(100.0, uncapped), 1)

    discarded = any(is_discarding(f, config.discard_on_lockin) for f in flags)
    t1, t2 = config.thresholds["tier_1_min"], config.thresholds["tier_2_min"]
    if discarded:
        tier = Tier.RED_FLAG
    elif final >= t1:
        tier = Tier.HOT
    elif final >= t2:
        tier = Tier.WARM
    else:
        tier = Tier.COLD

    return POSEvaluation(
        final_score=final,
        raw_score=round(base, 1),
        uncapped_score=round(uncapped, 2),
        tier=tier_label(tier, config),
        tier_code=tier,
        is_discarded=discarded,
        discard_reasons=flags,
        variables=values,
        explanations=explanations,
        weights_applied=dict(weights),
        multipliers_applied=multipliers,
        preset=config.preset,
        season=config.season,
        recommendation=RECOMMENDATIONS[tier],
    )


def score_leads(leads: Sequence[Lead], config: ScoringConfig) -> list[ScoredLead]:
    """Score and rank leads: best opportunities first, red-flagged leads last.

    Ties at the 100-point cap are broken by the uncapped score, so ranking stays meaningful
    even when multipliers push several leads over the ceiling.
    """
    pressures = peer_pressures(leads)
    evaluated = [(lead, score_lead(lead, config, pressures.get(lead.id))) for lead in leads]
    evaluated.sort(
        key=lambda pair: (pair[1].is_discarded, -pair[1].uncapped_score, pair[0].company.name)
    )
    return [
        ScoredLead(lead, evaluation, rank) for rank, (lead, evaluation) in enumerate(evaluated, 1)
    ]


def tier_counts(scored: Iterable[ScoredLead]) -> dict[str, int]:
    counts = {tier.value: 0 for tier in Tier}
    total = 0
    for item in scored:
        counts[item.evaluation.tier_code.value] += 1
        total += 1
    counts["total"] = total
    return counts
