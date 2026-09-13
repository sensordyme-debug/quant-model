"""Venues: explicit capability declarations over the execution adapters, and the fit question.

    base.py       Capability, Venue, StrategyProfile, Unsupported - the protocol
    propfirm.py   PropFirmRules, PropFirmObjective, Scoring - a firm as rules plus an objective
    registry.py   the concrete venues (simulated, ibkr, projectx), the registry, best_fit

The design rule in one line: a venue does what it DECLARES, a strategy gets what it
REQUIRES, and the gap between the two is a refusal with a reason - never an emulation.
"""
from quant_brain.venues.base import (
    Account,
    Capability,
    Reconciliation,
    StrategyProfile,
    Unsupported,
    Venue,
    hooks,
)
from quant_brain.venues.propfirm import (
    ObjectiveResult,
    ProfileObjective,
    ProfileRules,
    PropFirmObjective,
    PropFirmRules,
    Scoring,
    TopstepRules,
    TwinObjective,
)
from quant_brain.venues.registry import (
    DOCUMENTED_ABSENCES,
    CannotRank,
    ContradictsDocumentation,
    Fit,
    IBKRVenue,
    NoEligibleVenue,
    ProjectXVenue,
    SimulatedVenue,
    VenueRegistry,
    Verdict,
    default_registry,
)

__all__ = [
    "DOCUMENTED_ABSENCES", "Account", "CannotRank", "Capability", "ContradictsDocumentation",
    "Fit", "IBKRVenue", "NoEligibleVenue", "ObjectiveResult", "ProfileObjective",
    "ProfileRules", "ProjectXVenue", "PropFirmObjective", "PropFirmRules", "Reconciliation",
    "Scoring", "SimulatedVenue", "StrategyProfile", "TopstepRules", "TwinObjective",
    "Unsupported", "Venue", "VenueRegistry", "Verdict", "default_registry", "hooks",
]
