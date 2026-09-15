"""ColdLead Studio — scientific B2B lead scouting for VibeCoding studios.

The public API is intentionally small and pure:

>>> from coldlead import demo_leads, score_leads, resolve_config
>>> leads = demo_leads("Yacht charter", "Miami", limit=5)
>>> ranked = score_leads(leads, resolve_config(preset="high_ticket_luxury"))
>>> ranked[0].evaluation.final_score  # doctest: +SKIP
"""

from __future__ import annotations

__version__ = "1.1.0"
SCHEMA_VERSION = "1.0.0"

from coldlead.config import ScoringConfig, list_presets, resolve_config  # noqa: E402
from coldlead.models import (  # noqa: E402
    ActionKit,
    Company,
    Lead,
    LeadDossier,
    POSEvaluation,
    RawSignals,
    RedFlag,
    Session,
)
from coldlead.providers.demo import demo_leads  # noqa: E402
from coldlead.scoring import ScoredLead, score_lead, score_leads  # noqa: E402

__all__ = [
    "SCHEMA_VERSION",
    "ActionKit",
    "Company",
    "Lead",
    "LeadDossier",
    "POSEvaluation",
    "RawSignals",
    "RedFlag",
    "ScoredLead",
    "ScoringConfig",
    "Session",
    "__version__",
    "demo_leads",
    "list_presets",
    "resolve_config",
    "score_lead",
    "score_leads",
]
