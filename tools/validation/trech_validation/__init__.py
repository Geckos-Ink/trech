"""TRECH validation suite — physics-consistency checks vs reference data."""

from .cases import (
    ALL_CASES,
    CaseResult,
    OperatorReferencePairCase,
    OperatorReferencePairSpec,
    OperatorTrustRequirements,
    PairRunAliases,
    ValidationCase,
)
from .runner import RunContext, run_all
from .report import write_report

__all__ = [
    "ALL_CASES",
    "ValidationCase",
    "CaseResult",
    "OperatorReferencePairCase",
    "OperatorReferencePairSpec",
    "OperatorTrustRequirements",
    "PairRunAliases",
    "RunContext",
    "run_all",
    "write_report",
]
