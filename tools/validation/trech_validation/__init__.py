"""TRECH validation suite — physics-consistency checks vs reference data."""

from .cases import ALL_CASES, ValidationCase, CaseResult
from .runner import RunContext, run_all
from .report import write_report

__all__ = [
    "ALL_CASES",
    "ValidationCase",
    "CaseResult",
    "RunContext",
    "run_all",
    "write_report",
]
