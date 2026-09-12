"""Cascading configuration.

Precedence (lowest → highest), each layer only overrides the keys it sets:

1. Factory presets shipped with the package (``presets.json``)
2. User config file ``~/.coldlead/config.json`` (or ``$COLDLEAD_HOME/config.json``)
3. Environment variables (``COLDLEAD_PRESET``, ``COLDLEAD_SEASON``, ``COLDLEAD_W_G`` …)
4. Runtime overrides (CLI flags, dashboard sliders, MCP tool arguments)
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from datetime import date
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

WEIGHT_KEYS: tuple[str, ...] = ("w_G", "w_T", "w_F", "w_P", "w_I", "w_D", "w_C", "w_A")
MULTIPLIER_KEYS: tuple[str, ...] = (
    "m_ads_active",
    "m_friction_high",
    "m_lockin_penalty",
    "t_win_autumn_winter",
    "t_win_spring",
    "t_win_summer_peak",
    "t_win_year_round",
)
THRESHOLD_KEYS: tuple[str, ...] = ("tier_1_min", "tier_2_min")
SEASONS: tuple[str, ...] = ("auto", "autumn_winter", "spring", "summer_peak", "year_round")

# Every spelling people naturally use for a weight maps to its canonical ``w_*`` key.
_WEIGHT_ALIASES: dict[str, str] = {}
for _canonical, _aliases in {
    "w_G": ("g", "g_dig", "gap", "digital", "digital_gap"),
    "w_T": ("t", "v_ticket", "ticket", "ticket_value"),
    "w_F": ("f", "f_fin", "fin", "finance", "financial"),
    "w_P": ("p", "c_press", "press", "pressure", "competition", "competitive_pressure"),
    "w_I": ("i", "m_reach", "reach", "international", "market_reach"),
    "w_D": ("d", "a_decision", "decision", "decision_maker", "access"),
    "w_C": ("c", "b_care", "care", "brand_care"),
    "w_A": ("a", "u_vibe", "vibe", "automation", "automation_potential"),
}.items():
    _WEIGHT_ALIASES[_canonical.lower()] = _canonical
    for _alias in _aliases:
        _WEIGHT_ALIASES[_alias] = _canonical


class ConfigError(ValueError):
    """Raised for invalid presets, keys or values."""


class ScoringConfig(BaseModel):
    """A fully resolved, validated scoring configuration. Immutable by convention."""

    preset: str
    weights: dict[str, float]
    multipliers: dict[str, float]
    thresholds: dict[str, float]
    season: str
    discard_on_lockin: bool = False
    sources: list[str] = Field(default_factory=list)

    @property
    def t_win(self) -> float:
        return self.multipliers[f"t_win_{self.season}"]


# ------------------------------------------------------------------------------------------
# Paths & files
# ------------------------------------------------------------------------------------------


def coldlead_home() -> Path:
    return Path(os.environ.get("COLDLEAD_HOME") or Path.home() / ".coldlead").expanduser()


def user_config_path() -> Path:
    return coldlead_home() / "config.json"


@lru_cache(maxsize=1)
def _factory() -> dict[str, Any]:
    text = resources.files("coldlead").joinpath("presets.json").read_text(encoding="utf-8")
    return json.loads(text)


def load_user_config(path: Path | None = None) -> dict[str, Any]:
    path = path or user_config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object")
    return data


def all_presets(user_config: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Factory presets merged with user-defined ones (which may ``extends`` another preset)."""
    presets = {name: dict(p) for name, p in _factory()["presets"].items()}
    for name, custom in (user_config or {}).get("presets", {}).items():
        base = presets.get(custom.get("extends", ""), presets["default_vibe_coding"])
        presets[name] = {
            "name": custom.get("name", name),
            "description": custom.get("description", f"Custom preset ({name})"),
            "weights": {**base["weights"], **custom.get("weights", {})},
            "multipliers": {**base["multipliers"], **custom.get("multipliers", {})},
            "thresholds": {**base["thresholds"], **custom.get("thresholds", {})},
            "custom": True,
        }
    return presets


def list_presets() -> dict[str, dict[str, Any]]:
    try:
        return all_presets(load_user_config())
    except ConfigError:
        return all_presets()


# ------------------------------------------------------------------------------------------
# Parsing helpers
# ------------------------------------------------------------------------------------------


def normalize_weight_key(key: str) -> str:
    canonical = _WEIGHT_ALIASES.get(key.strip().lower())
    if canonical is None:
        raise ConfigError(f"Unknown weight '{key}'. Valid keys: {', '.join(WEIGHT_KEYS)}")
    return canonical


def normalize_weights(weights: Mapping[str, Any] | None) -> dict[str, float]:
    return {normalize_weight_key(k): _to_float(k, v) for k, v in (weights or {}).items()}


def parse_overrides(text: str | None) -> dict[str, float]:
    """Parse ``'{"w_A": 4}'`` (JSON) or ``'w_A=4,w_G=3'`` / ``'w_A=4 w_G=3'`` (shell friendly)."""
    if not text or not text.strip():
        return {}
    text = text.strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON overrides: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError("JSON overrides must be an object")
        return {str(k): _to_float(k, v) for k, v in data.items()}
    result: dict[str, float] = {}
    for chunk in re.split(r"[,;\s]+", text):
        if not chunk:
            continue
        if "=" not in chunk and ":" not in chunk:
            raise ConfigError(f"Expected KEY=VALUE, got '{chunk}'")
        key, value = re.split(r"[=:]", chunk, maxsplit=1)
        result[key.strip()] = _to_float(key, value)
    return result


def _to_float(key: Any, value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Value for '{key}' must be a number, got {value!r}") from exc


def resolve_season(season: str | None, today: date | None = None) -> str:
    """``auto`` maps the current month to the seasonal window defined by the POS model."""
    season = (season or "auto").strip().lower()
    if season not in SEASONS:
        raise ConfigError(f"Unknown season '{season}'. Valid: {', '.join(SEASONS)}")
    if season != "auto":
        return season
    month = (today or date.today()).month
    if month in (10, 11, 12, 1, 2):
        return "autumn_winter"
    if month in (3, 4):
        return "spring"
    if month in (6, 7, 8):
        return "summer_peak"
    return "year_round"


def _env_layer(env: Mapping[str, str]) -> dict[str, Any]:
    layer: dict[str, Any] = {"weights": {}, "thresholds": {}}
    if env.get("COLDLEAD_PRESET"):
        layer["preset"] = env["COLDLEAD_PRESET"]
    if env.get("COLDLEAD_SEASON"):
        layer["season"] = env["COLDLEAD_SEASON"]
    for key in WEIGHT_KEYS:
        raw = env.get(f"COLDLEAD_{key.upper()}")
        if raw:
            layer["weights"][key] = _to_float(key, raw)
    for key in THRESHOLD_KEYS:
        raw = env.get(f"COLDLEAD_{key.upper()}")
        if raw:
            layer["thresholds"][key] = _to_float(key, raw)
    return layer


# ------------------------------------------------------------------------------------------
# Resolution
# ------------------------------------------------------------------------------------------


def resolve_config(
    preset: str | None = None,
    weights: Mapping[str, Any] | None = None,
    multipliers: Mapping[str, Any] | None = None,
    thresholds: Mapping[str, Any] | None = None,
    season: str | None = None,
    *,
    discard_on_lockin: bool | None = None,
    env: Mapping[str, str] | None = None,
    user_config: Mapping[str, Any] | None = None,
    today: date | None = None,
) -> ScoringConfig:
    """Resolve the four configuration layers into a validated :class:`ScoringConfig`."""
    env = os.environ if env is None else env
    user = load_user_config() if user_config is None else dict(user_config)
    env_layer = _env_layer(env)
    presets = all_presets(user)
    sources = ["factory"]

    preset_name = (
        preset
        or env_layer.get("preset")
        or user.get("default_preset")
        or _factory()["default_preset"]
    )
    if preset_name not in presets:
        raise ConfigError(f"Unknown preset '{preset_name}'. Available: {', '.join(presets)}")
    base = presets[preset_name]
    resolved_weights = dict(base["weights"])
    resolved_multipliers = dict(base["multipliers"])
    resolved_thresholds = dict(base["thresholds"])
    resolved_season = user.get("season", "auto")
    lockin = bool(user.get("discard_on_lockin", False))

    if user:
        sources.append(f"user:{user_config_path()}" if user_config is None else "user")
        resolved_weights.update(normalize_weights(user.get("weights")))
        resolved_multipliers.update(user.get("multipliers", {}))
        resolved_thresholds.update(user.get("thresholds", {}))

    if (
        env_layer["weights"]
        or env_layer["thresholds"]
        or "season" in env_layer
        or "preset" in env_layer
    ):
        sources.append("env")
        resolved_weights.update(env_layer["weights"])
        resolved_thresholds.update(env_layer["thresholds"])
        resolved_season = env_layer.get("season", resolved_season)

    runtime = any(x for x in (weights, multipliers, thresholds, season, preset)) or (
        discard_on_lockin is not None
    )
    if runtime:
        sources.append("runtime")
    resolved_weights.update(normalize_weights(weights))
    for key, value in (multipliers or {}).items():
        if key not in MULTIPLIER_KEYS:
            raise ConfigError(f"Unknown multiplier '{key}'. Valid: {', '.join(MULTIPLIER_KEYS)}")
        resolved_multipliers[key] = _to_float(key, value)
    for key, value in (thresholds or {}).items():
        if key not in THRESHOLD_KEYS:
            raise ConfigError(f"Unknown threshold '{key}'. Valid: {', '.join(THRESHOLD_KEYS)}")
        resolved_thresholds[key] = _to_float(key, value)
    if season:
        resolved_season = season
    if discard_on_lockin is not None:
        lockin = discard_on_lockin

    _validate(resolved_weights, resolved_multipliers, resolved_thresholds)
    return ScoringConfig(
        preset=preset_name,
        weights={k: float(resolved_weights[k]) for k in WEIGHT_KEYS},
        multipliers={k: float(resolved_multipliers[k]) for k in MULTIPLIER_KEYS},
        thresholds={k: float(resolved_thresholds[k]) for k in THRESHOLD_KEYS},
        season=resolve_season(resolved_season, today),
        discard_on_lockin=lockin,
        sources=sources,
    )


def _validate(
    weights: dict[str, Any], multipliers: dict[str, Any], thresholds: dict[str, Any]
) -> None:
    for key in WEIGHT_KEYS:
        value = float(weights.get(key, 0))
        if not 0 <= value <= 10:
            raise ConfigError(f"Weight {key}={value} out of range [0, 10]")
    if sum(float(weights.get(k, 0)) for k in WEIGHT_KEYS) <= 0:
        raise ConfigError("At least one weight must be greater than zero")
    for key in MULTIPLIER_KEYS:
        value = float(multipliers.get(key, 1))
        if not 0 < value <= 5:
            raise ConfigError(f"Multiplier {key}={value} out of range (0, 5]")
    t1, t2 = float(thresholds["tier_1_min"]), float(thresholds["tier_2_min"])
    if not 0 <= t2 <= t1 <= 100:
        raise ConfigError(
            f"Thresholds must satisfy 0 <= tier_2_min ({t2}) <= tier_1_min ({t1}) <= 100"
        )
