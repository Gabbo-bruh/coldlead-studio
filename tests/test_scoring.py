from __future__ import annotations

import copy
import time

import pytest

from coldlead.config import resolve_config
from coldlead.models import Tier
from coldlead.scoring import peer_pressures, score_lead, score_leads, tier_counts
from coldlead.variables import VARIABLES, compute_variables
from tests.conftest import make_lead


def test_formula_matches_hand_calculation(config):
    lead = make_lead()
    ev = score_lead(lead, config)
    values, _ = compute_variables(lead)
    expected_base = sum(config.weights[v.weight_key] * values[v.key] for v in VARIABLES) / 14.0 * 10
    assert ev.raw_score == round(expected_base, 1)
    # ads active (1.25), no friction, year_round season (1.0), no lock-in
    assert ev.multipliers_applied == {
        "m_ads": 1.25,
        "m_friction": 1.0,
        "t_win": 1.0,
        "m_lockin": 1.0,
    }
    assert ev.uncapped_score == pytest.approx(expected_base * 1.25, abs=0.01)
    assert ev.final_score == round(min(100.0, expected_base * 1.25), 1)


def test_vision_example_variables(config):
    """The dossier example from PROJECT_VISION.md: G_dig 4.7, V_ticket 9.5, M_reach 9.5 …"""
    values = score_lead(make_lead(), config).variables
    assert values["G_dig"] == 4.7
    assert values["V_ticket"] == 9.5
    assert values["F_fin"] == 9.0
    assert values["M_reach"] == 9.5
    assert values["B_care"] == 9.0


def test_score_is_capped_but_uncapped_kept():
    cfg = resolve_config(season="autumn_winter", user_config={}, env={})
    ev = score_lead(make_lead(mobile_friendly=False), cfg)
    assert ev.final_score == 100.0
    assert ev.uncapped_score > 100.0
    assert ev.tier_code is Tier.HOT
    assert ev.tier == "Tier 1 — Hot Lead (POS >= 85)"


def test_scoring_is_pure_and_deterministic(leads, config):
    snapshot = copy.deepcopy([lead.model_dump() for lead in leads])
    first = [s.evaluation.model_dump() for s in score_leads(leads, config)]
    second = [s.evaluation.model_dump() for s in score_leads(leads, config)]
    assert first == second
    assert [lead.model_dump() for lead in leads] == snapshot  # inputs untouched


def test_weights_change_ranking(leads):
    base = score_leads(leads, resolve_config(season="year_round", user_config={}, env={}))
    tuned = score_leads(
        leads,
        resolve_config(
            weights={"w_G": 0, "w_A": 10, "w_T": 0}, season="year_round", user_config={}, env={}
        ),
    )
    assert [s.lead.id for s in base] != [s.lead.id for s in tuned]


def test_ranking_order(leads, config):
    scored = score_leads(leads, config)
    assert [s.rank for s in scored] == list(range(1, len(scored) + 1))
    discarded = [s.evaluation.is_discarded for s in scored]
    assert discarded == sorted(discarded)  # red flags always at the bottom
    alive = [s.evaluation.uncapped_score for s in scored if not s.evaluation.is_discarded]
    assert alive == sorted(alive, reverse=True)


def test_red_flag_discards(config):
    toxic = make_lead(is_toxic_owner=True, sample_owner_replies=["Ti querelo, bugiardo!"])
    ev = score_lead(toxic, config)
    assert ev.is_discarded and ev.tier_code is Tier.RED_FLAG
    assert ev.recommendation.startswith("DISCARD")


def test_lockin_is_penalty_or_discard(config):
    locked = make_lead(footer_agency_credit="Pixel Web Agency")
    ev = score_lead(locked, config)
    assert not ev.is_discarded
    assert ev.multipliers_applied["m_lockin"] == 0.85
    strict = resolve_config(discard_on_lockin=True, season="year_round", user_config={}, env={})
    assert score_lead(locked, strict).is_discarded


def test_friction_multiplier(config):
    assert score_lead(make_lead(has_ssl=False), config).multipliers_applied["m_friction"] == 1.15
    no_site = make_lead(has_website=False, website_url=None, mobile_friendly=None, has_ssl=None)
    assert score_lead(no_site, config).multipliers_applied["m_friction"] == 1.0


def test_thresholds_drive_tiers(config):
    lead = make_lead(is_running_ads=False)
    score = score_lead(lead, config).final_score
    above = resolve_config(
        thresholds={"tier_1_min": score - 1, "tier_2_min": 10},
        season="year_round",
        user_config={},
        env={},
    )
    below = resolve_config(
        thresholds={"tier_1_min": 100, "tier_2_min": 99.9},
        season="year_round",
        user_config={},
        env={},
    )
    assert score_lead(lead, above).tier_code is Tier.HOT
    assert score_lead(lead, below).tier_code is Tier.COLD


def test_peer_pressure(leads):
    pressures = peer_pressures(leads)
    assert set(pressures) == {lead.id for lead in leads}  # one city, one sector → one group
    assert all(0 <= p <= 10 for p in pressures.values())
    assert peer_pressures(leads[:2]) == {}  # too few peers


def test_tier_counts(leads, config):
    counts = tier_counts(score_leads(leads, config))
    assert counts["total"] == 12
    assert sum(counts[t.value] for t in Tier) == 12
    assert counts["red_flag"] >= 1


def test_rescoring_is_fast(config):
    from coldlead.providers.demo import demo_leads

    many = demo_leads("Ristorante", "Firenze", 60) * 4  # 240 leads
    started = time.perf_counter()
    score_leads(many, config)
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert elapsed_ms < 500, f"rescoring 240 leads took {elapsed_ms:.0f} ms"
