"""Runtime settings: optional API keys and preferences, read from the environment and ``.env``.

No key is required. Each one only upgrades a capability:

====================================  ===============================================
``GOOGLE_PLACES_API_KEY``             live discovery via Google Places API (New)
``PAGESPEED_API_KEY``                 official Lighthouse scores (PageSpeed Insights)
``META_AD_LIBRARY_ACCESS_TOKEN``      verify active ads in the Meta Ad Library
``GEMINI_API_KEY`` / ``ANTHROPIC_API_KEY`` / ``OPENROUTER_API_KEY`` / ``OPENAI_API_KEY``
                                      LLM insights (tone of voice, toxicity, ideas)
====================================  ===============================================
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from coldlead.config import coldlead_home
from coldlead.locales import locale_for_country

USER_AGENT = "ColdLeadStudio/1.0 (+https://github.com/Gabbo-bruh/coldlead-studio)"
# Never ask servers for a specific language: a multilingual site must be audited as it presents
# itself to anyone, otherwise the M_reach variable would misjudge it as single-language.
HTTP_HEADERS: dict[str, str] = {"User-Agent": USER_AGENT, "Accept-Language": "*"}
DEFAULT_LANGUAGE = "en"


def language_for_country(country: str | None) -> str:
    """Outreach language of the locale pack serving ``country``; English when there is none."""
    pack = locale_for_country(country)
    return pack.language if pack else DEFAULT_LANGUAGE


def load_dotenv(*paths: Path) -> None:
    """Minimal ``.env`` loader. Never overrides variables already set in the environment."""
    for path in paths:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.removeprefix("export ").strip()
            value = value.strip().strip("'\"")
            if key and value and key not in os.environ:
                os.environ[key] = value


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    if not value or value.startswith("your_"):
        return None
    return value


@dataclass
class Settings:
    google_places_api_key: str | None = None
    pagespeed_api_key: str | None = None
    meta_ads_token: str | None = None
    llm_provider: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    country: str | None = None  # ISO code; None = no geographic bias
    language: str = DEFAULT_LANGUAGE
    http_timeout: float = 10.0
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_provider and (self.llm_api_key or self.llm_provider == "ollama"))


LLM_DEFAULTS: dict[str, tuple[str, str | None, str]] = {
    # provider: (api key env var, base url, default model). Auto-detection follows this order.
    "gemini": ("GEMINI_API_KEY", None, "gemini-2.5-flash"),
    "anthropic": ("ANTHROPIC_API_KEY", None, "claude-sonnet-5"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "deepseek/deepseek-chat"),
    "openai": ("OPENAI_API_KEY", "https://api.openai.com/v1", "gpt-4o-mini"),
    "ollama": ("", "http://localhost:11434/v1", "llama3.1"),
}


def get_settings(load_env_files: bool = True) -> Settings:
    if load_env_files:
        load_dotenv(Path.cwd() / ".env", coldlead_home() / ".env")

    provider = (_env("COLDLEAD_LLM_PROVIDER") or "").lower() or None
    if provider in (None, "auto"):
        provider = next((p for p, (var, _, _) in LLM_DEFAULTS.items() if _env(var)), None)
    elif provider == "none":
        provider = None
    api_key = base_url = model = None
    if provider in LLM_DEFAULTS:
        var, base_url, model = LLM_DEFAULTS[provider]
        api_key = _env(var) if var else None
        if provider in ("openai", "openrouter", "ollama"):
            base_url = _env("COLDLEAD_LLM_BASE_URL") or _env("OPENAI_BASE_URL") or base_url
    elif provider:
        provider = None  # unknown provider name: stay offline rather than fail later
    model = _env("COLDLEAD_LLM_MODEL") or model

    # COLDLEAD_LANG wins; otherwise ("auto" or unset) the language follows COLDLEAD_COUNTRY.
    country = (_env("COLDLEAD_COUNTRY") or "").upper() or None
    language = (_env("COLDLEAD_LANG") or "auto").lower()
    if language == "auto":
        language = language_for_country(country)

    return Settings(
        google_places_api_key=_env("GOOGLE_PLACES_API_KEY"),
        pagespeed_api_key=_env("PAGESPEED_API_KEY"),
        meta_ads_token=_env("META_AD_LIBRARY_ACCESS_TOKEN"),
        llm_provider=provider,
        llm_api_key=api_key,
        llm_model=model,
        llm_base_url=base_url,
        country=country,
        language=language,
        http_timeout=float(_env("COLDLEAD_HTTP_TIMEOUT") or 10),
    )
