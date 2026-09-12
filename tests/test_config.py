from __future__ import annotations

import json
from datetime import date

import pytest

from coldlead.config import (
    ConfigError,
    all_presets,
    normalize_weight_key,
    parse_overrides,
    resolve_config,
    resolve_season,
)


def test_factory_default_preset():
    cfg = resolve_config(user_config={}, env={}, season="spring")
    assert cfg.preset == "default_vibe_coding"
    assert cfg.weights == {
        "w_G": 3.0,
        "w_T": 2.5,
        "w_F": 2.0,
        "w_P": 1.5,
        "w_I": 1.5,
        "w_D": 1.5,
        "w_C": 1.0,
        "w_A": 1.0,
    }
    assert sum(cfg.weights.values()) == 14.0
    assert cfg.thresholds == {"tier_1_min": 85.0, "tier_2_min": 65.0}
    assert cfg.t_win == 1.0
    assert cfg.sources == ["factory", "runtime"]


@pytest.mark.parametrize("preset", ["automation_first", "high_ticket_luxury", "speedy_cashflow"])
def test_all_factory_presets_resolve(preset):
    cfg = resolve_config(preset=preset, user_config={}, env={})
    assert cfg.preset == preset


def test_preset_values_match_vision():
    presets = all_presets()
    assert presets["automation_first"]["weights"]["w_A"] == 3.0
    assert presets["automation_first"]["weights"]["w_D"] == 2.0
    assert presets["high_ticket_luxury"]["weights"]["w_T"] == 3.5
    assert presets["high_ticket_luxury"]["weights"]["w_I"] == 2.5
    assert presets["speedy_cashflow"]["weights"]["w_G"] == 4.0
    assert presets["speedy_cashflow"]["weights"]["w_D"] == 3.0


def test_cascade_factory_user_env_runtime():
    user = {"default_preset": "automation_first", "weights": {"w_G": 5}}
    env = {"COLDLEAD_W_A": "7", "COLDLEAD_SEASON": "summer_peak"}
    cfg = resolve_config(user_config=user, env=env)
    assert cfg.preset == "automation_first"
    assert cfg.weights["w_G"] == 5.0  # user layer
    assert cfg.weights["w_A"] == 7.0  # env layer
    assert cfg.season == "summer_peak"
    assert cfg.sources == ["factory", "user", "env"]

    runtime = resolve_config(weights={"w_A": 1}, season="spring", user_config=user, env=env)
    assert runtime.weights["w_A"] == 1.0  # runtime beats env
    assert runtime.weights["w_G"] == 5.0
    assert runtime.season == "spring"
    assert runtime.sources[-1] == "runtime"


def test_env_preset_beats_user_default():
    cfg = resolve_config(
        user_config={"default_preset": "automation_first"},
        env={"COLDLEAD_PRESET": "speedy_cashflow"},
    )
    assert cfg.preset == "speedy_cashflow"


def test_user_config_file_on_disk(isolated):
    isolated.mkdir(parents=True)
    (isolated / "config.json").write_text(
        json.dumps(
            {
                "presets": {"mine": {"extends": "high_ticket_luxury", "weights": {"w_A": 9}}},
                "default_preset": "mine",
            }
        ),
        encoding="utf-8",
    )
    cfg = resolve_config(env={})
    assert cfg.preset == "mine"
    assert cfg.weights["w_A"] == 9.0
    assert cfg.weights["w_T"] == 3.5  # inherited
    assert cfg.sources[1].startswith("user:")


def test_invalid_user_config_raises(isolated):
    isolated.mkdir(parents=True)
    (isolated / "config.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="Invalid JSON"):
        resolve_config(env={})


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [
        ("w_A", "w_A"),
        ("W_a", "w_A"),
        ("automation", "w_A"),
        ("U_vibe", "w_A"),
        ("G_dig", "w_G"),
        ("ticket", "w_T"),
    ],
)
def test_weight_aliases(alias, canonical):
    assert normalize_weight_key(alias) == canonical


def test_unknown_weight_rejected():
    with pytest.raises(ConfigError, match="Unknown weight"):
        resolve_config(weights={"w_Z": 1}, user_config={}, env={})


@pytest.mark.parametrize(
    "text", ['{"w_A": 4, "w_G": 3}', "w_A=4,w_G=3", "w_A=4 w_G=3", "w_A:4;w_G:3"]
)
def test_parse_overrides_formats(text):
    assert parse_overrides(text) == {"w_A": 4.0, "w_G": 3.0}


def test_parse_overrides_errors():
    with pytest.raises(ConfigError):
        parse_overrides("w_A")
    with pytest.raises(ConfigError):
        parse_overrides("w_A=abc")
    assert parse_overrides("") == {}


@pytest.mark.parametrize(
    ("weights", "thresholds", "message"),
    [
        ({"w_A": 11}, None, "out of range"),
        (
            {k: 0 for k in ("w_G", "w_T", "w_F", "w_P", "w_I", "w_D", "w_C", "w_A")},
            None,
            "greater than zero",
        ),
        (None, {"tier_1_min": 50, "tier_2_min": 60}, "Thresholds"),
    ],
)
def test_validation(weights, thresholds, message):
    with pytest.raises(ConfigError, match=message):
        resolve_config(weights=weights, thresholds=thresholds, user_config={}, env={})


def test_unknown_preset():
    with pytest.raises(ConfigError, match="Unknown preset"):
        resolve_config(preset="nope", user_config={}, env={})


@pytest.mark.parametrize(
    ("month", "season"),
    [
        (1, "autumn_winter"),
        (2, "autumn_winter"),
        (3, "spring"),
        (4, "spring"),
        (5, "year_round"),
        (7, "summer_peak"),
        (9, "year_round"),
        (10, "autumn_winter"),
        (12, "autumn_winter"),
    ],
)
def test_auto_season(month, season):
    assert resolve_season("auto", date(2026, month, 15)) == season


def test_explicit_season_and_invalid():
    assert resolve_season("spring") == "spring"
    with pytest.raises(ConfigError):
        resolve_season("monsoon")
