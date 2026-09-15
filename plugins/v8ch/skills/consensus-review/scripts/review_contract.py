#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

"""
Executable consensus-review scoring contract (contract C-1).

The synthesizer decides status in prose; this module is the machine-checkable
statement of the same rules, so both toolchains score a finding set identically
and a drift in either prompt is caught by a fixture test rather than by a
disagreeing review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SCHEMA_VERSION = 2

SEVERITIES: tuple[str, ...] = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

#: Deduction applied once per emitted defect, by severity (contract C-1).
DEDUCTIONS: dict[str, int] = {
    "CRITICAL": 20,
    "HIGH": 10,
    "MEDIUM": 5,
    "LOW": 2,
}

#: Report sections a finding can land in. ``plan_note`` never deducts.
SECTIONS: tuple[str, ...] = ("must_fix", "should_fix", "latent", "plan_note")

#: Sections whose open findings block the ``clean`` status.
BLOCKING_SECTIONS: frozenset[str] = frozenset({"must_fix", "should_fix"})

STATUSES: tuple[str, ...] = ("clean", "passing", "failing")

STATUS_LABELS: dict[str, str] = {
    "clean": "Fully Clean",
    "passing": "Passing",
    "failing": "Failing",
}

DELEGATION_MODES: tuple[str, ...] = ("parallel-subagents", "sequential-fallback")

#: Exact key set of the schema_version 2 audit metadata block (contract C-5).
#: Declared once so the writer and the reader cannot drift apart.
METADATA_KEYS: frozenset[str] = frozenset(
    {
        "cycle",
        "delegation_mode",
        "files_touched",
        "findings_closed",
        "findings_opened",
        "plan_source",
        "reviewed_sha",
        "schema_version",
        "scope_basis",
        "score",
        "status",
        "type",
    }
)

MAX_SCORE = 100
MIN_SCORE = 1
CLEAN_THRESHOLD = 95
PASSING_THRESHOLD = 85

SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
SCOPE_BASIS_RE = re.compile(r"^(?:full-diff|delta-since:[0-9a-f]{7,40})$")
QUALITY_SCORE_RE = re.compile(
    r"^### Quality Score:\s+(\d+)/100(?:\s+—.*)?$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Finding:
    """One emitted finding, as the synthesizer would place it in the report."""

    id: str
    section: str
    severity: str | None = None
    demonstrated: bool = True

    def __post_init__(self) -> None:
        if self.section not in SECTIONS:
            raise ValueError(f"Unknown section: {self.section!r}")
        if self.section == "plan_note":
            if self.severity is not None:
                raise ValueError("Plan notes carry no severity.")
        elif self.severity not in SEVERITIES:
            raise ValueError(f"Unknown severity: {self.severity!r}")


def deduction(finding: Finding) -> int:
    """Return the points a single finding removes from the score.

    A latent finding takes the severity of its would-be failure, so it is scored
    from ``severity`` exactly like a Must Fix or Should Fix entry. Plan notes and
    undemonstrated findings deduct nothing.
    """
    if finding.section == "plan_note":
        return 0
    if not finding.demonstrated:
        return 0
    assert finding.severity is not None  # guaranteed by __post_init__
    return DEDUCTIONS[finding.severity]


def score_findings(findings: list[Finding]) -> int:
    """Score a finding set: start at 100, deduct once per defect, floor at 1."""
    total = MAX_SCORE - sum(deduction(finding) for finding in findings)
    return max(MIN_SCORE, min(MAX_SCORE, total))


def has_open_blockers(findings: list[Finding]) -> bool:
    """Return whether any Must Fix or Should Fix finding is present."""
    return any(finding.section in BLOCKING_SECTIONS for finding in findings)


def resolve_status(score: int, findings: list[Finding]) -> str:
    """Return the review status for a score and finding set (contract C-1)."""
    if score >= CLEAN_THRESHOLD and not has_open_blockers(findings):
        return "clean"
    if score >= PASSING_THRESHOLD:
        return "passing"
    return "failing"


def score_breakdown(findings: list[Finding]) -> list[tuple[str, int]]:
    """Return ``(finding id, deduction)`` rows in emission order."""
    return [(finding.id, deduction(finding)) for finding in findings]


def extract_quality_score(review_text: str) -> int | None:
    """Return the raw score from a synthesized report's Quality Score heading."""
    match = QUALITY_SCORE_RE.search(review_text)
    if not match:
        return None
    return int(match.group(1))


def is_valid_sha(value: object) -> bool:
    """Return whether a value is a 7-40 character lowercase hex SHA."""
    return isinstance(value, str) and bool(SHA_RE.match(value))


def is_valid_scope_basis(value: object) -> bool:
    """Return whether a value is ``full-diff`` or ``delta-since:<sha>``."""
    return isinstance(value, str) and bool(SCOPE_BASIS_RE.match(value))


def is_valid_score(value: object) -> bool:
    """Return whether a value is an integer score within the 1-100 range."""
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and MIN_SCORE <= value <= MAX_SCORE
    )


def is_non_negative_int(value: object) -> bool:
    """Return whether a value is a non-negative integer."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
