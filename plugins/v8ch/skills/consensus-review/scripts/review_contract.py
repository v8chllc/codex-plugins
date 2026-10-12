"""Executable consensus-review v2 contract for the Codex CLI plugin.

Holds the scoring rules (C-1) and the audit-metadata schema (C-5) that
``post_review_comment.py`` and ``recover_context.py`` share. Keeping both in one
module is what makes a rendered comment recoverable by the sibling toolchain:
the Claude copy in ``v8chllc/claude-plugins`` is byte-identical to this file apart
from this docstring, which ``parity-manifest.json`` enforces in both
repositories.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 2
COMMENT_MARKER = "consensus-review"
COMMENT_TYPE = "review"
EVIDENCE_HEADING = "### Evidence"

SEVERITIES: tuple[str, ...] = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
SEVERITY_DEDUCTIONS: dict[str, int] = {
    "CRITICAL": 20,
    "HIGH": 10,
    "MEDIUM": 5,
    "LOW": 2,
}

MUST_FIX = "must-fix"
SHOULD_FIX = "should-fix"
LATENT = "latent"
PLAN_NOTE = "plan-note"
SECTIONS: tuple[str, ...] = (MUST_FIX, SHOULD_FIX, LATENT, PLAN_NOTE)
BLOCKING_SECTIONS: frozenset[str] = frozenset({MUST_FIX, SHOULD_FIX})

SCORE_MAX = 100
SCORE_FLOOR = 1
CLEAN_MIN_SCORE = 95
PASSING_MIN_SCORE = 85

STATUS_CLEAN = "clean"
STATUS_PASSING = "passing"
STATUS_FAILING = "failing"
STATUSES: tuple[str, ...] = (STATUS_CLEAN, STATUS_PASSING, STATUS_FAILING)

STATUS_LABELS: dict[str, str] = {
    STATUS_CLEAN: "Fully Clean",
    STATUS_PASSING: "Passing",
    STATUS_FAILING: "Failing",
}

DELEGATION_MODES: tuple[str, ...] = ("parallel-subagents", "sequential-fallback")

NO_PLAN_SOURCE = "none"
SUPPLIED_PLAN_PREFIX = "supplied: "

FULL_DIFF = "full-diff"
DELTA_SINCE_PREFIX = "delta-since:"

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
COUNT_KEYS: tuple[str, ...] = ("files_touched", "findings_opened", "findings_closed")

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")

SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
QUALITY_SCORE_RE = re.compile(
    r"^### Quality Score:\s*(\d+)/100 — (Fully Clean|Passing|Failing)$"
)
FINDING_HEADING_RE = re.compile(
    r"^#### \[(F-\d+)\] \[(CRITICAL|HIGH|MEDIUM|LOW)\] (.+)$"
)
FINDING_SECTIONS = {
    "### Must Fix": MUST_FIX,
    "### Should Fix": SHOULD_FIX,
    "### Latent Findings": LATENT,
}
METADATA_BLOCK_RE = re.compile(
    rf"<!--\s*{COMMENT_MARKER}\s*(.*?)\s*-->",
    re.DOTALL,
)


class ContractError(ValueError):
    """Raised when a value violates the consensus-review v2 contract."""


@dataclass(frozen=True)
class Finding:
    """One emitted finding, as the synthesizer classified it.

    ``severity`` is required everywhere except Plan Notes, which carry no
    severity tag and never deduct.
    """

    identifier: str
    section: str
    severity: str | None = None

    def __post_init__(self) -> None:
        if self.section not in SECTIONS:
            raise ContractError(
                f"Unknown section '{self.section}'; expected one of "
                f"{', '.join(SECTIONS)}."
            )
        if self.section == PLAN_NOTE:
            if self.severity is not None:
                raise ContractError(
                    f"Plan note '{self.identifier}' must not carry a severity."
                )
            return
        if self.severity not in SEVERITIES:
            raise ContractError(
                f"Finding '{self.identifier}' has severity {self.severity!r}; "
                f"expected one of {', '.join(SEVERITIES)}."
            )


@dataclass(frozen=True)
class ReportContract:
    """Authoritative score, routing, and summary contract for one report."""

    score: int
    status: str
    open_findings: tuple[dict[str, str], ...]
    advisory_completion: bool
    summary_directive: str


def deduction(finding: Finding) -> int:
    """Return the points a single finding deducts.

    A latent finding deducts at the severity of its would-be failure, so it is
    scored like any other defect. Plan Notes deduct nothing. Reviewer count is
    not an input: a finding raised once deducts exactly what the same finding
    raised three times deducts.
    """
    if finding.section == PLAN_NOTE:
        return 0
    return SEVERITY_DEDUCTIONS[str(finding.severity)]


def score_findings(findings: Iterable[Finding]) -> int:
    """Score a report: start at 100, deduct once per emitted defect, floor at 1."""
    total = SCORE_MAX - sum(deduction(finding) for finding in findings)
    return max(total, SCORE_FLOOR)


def review_status(score: int, findings: Iterable[Finding]) -> str:
    """Return the single status for a score and its findings.

    The three statuses are mutually exclusive: ``clean`` needs both a score of
    95 or more and no open Must Fix or Should Fix finding, so a high score with
    an open blocker is ``passing`` rather than ``clean``.
    """
    if score < PASSING_MIN_SCORE:
        return STATUS_FAILING
    has_blocker = any(finding.section in BLOCKING_SECTIONS for finding in findings)
    if score >= CLEAN_MIN_SCORE and not has_blocker:
        return STATUS_CLEAN
    return STATUS_PASSING


def status_label(status: str) -> str:
    """Return the report heading label for a status."""
    try:
        return STATUS_LABELS[status]
    except KeyError:
        raise ContractError(f"Unknown status '{status}'.") from None


def _top_level_lines(report_text: str, *, prefix: str | None = None) -> list[str]:
    """Return lines outside fenced code blocks, optionally filtered by prefix."""
    lines: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    for line in report_text.splitlines():
        fence_match = re.match(r"^(`{3,}|~{3,})", line)
        if fence_character is not None:
            if (
                fence_match
                and fence_match.group(1)[0] == fence_character
                and len(fence_match.group(1)) >= fence_length
            ):
                fence_character = None
                fence_length = 0
            continue
        if fence_match:
            fence_character = fence_match.group(1)[0]
            fence_length = len(fence_match.group(1))
            continue
        if prefix is None or line.startswith(prefix):
            lines.append(line)
    if fence_character is not None:
        raise ContractError("The report contains an unclosed fenced code block.")
    return lines


def open_findings(report_text: str) -> list[dict[str, str]]:
    """Read and validate top-level findings in report order."""
    section: str | None = None
    findings: list[dict[str, str]] = []
    seen_sections: list[str] = []
    for line in _top_level_lines(report_text):
        if line.startswith("### "):
            section = FINDING_SECTIONS.get(line.strip())
            if section is not None:
                if section in seen_sections:
                    raise ContractError(
                        f"Finding section {line.strip()!r} is duplicated."
                    )
                seen_sections.append(section)
            continue
        if not line.startswith("#### "):
            continue
        match = FINDING_HEADING_RE.match(line)
        looks_like_finding = line.startswith("#### [F")
        if section is None:
            if looks_like_finding:
                raise ContractError(
                    f"Finding heading {line!r} is outside a finding section."
                )
            continue
        if not match:
            raise ContractError(f"Malformed finding heading in {section}: {line!r}.")
        identifier, severity, title = match.groups()
        findings.append(
            {
                "id": identifier,
                "severity": severity,
                "section": section,
                "title": title,
            }
        )

    expected_sections = list(FINDING_SECTIONS.values())
    if seen_sections != expected_sections:
        raise ContractError(
            "Finding sections must appear exactly once in this order: "
            + ", ".join(FINDING_SECTIONS)
            + "."
        )
    identifiers = [finding["id"] for finding in findings]
    expected = [f"F-{number}" for number in range(1, len(findings) + 1)]
    if identifiers != expected:
        raise ContractError(
            "Finding IDs must be unique and sequential in report order; expected "
            f"{expected}, got {identifiers}."
        )
    return findings


def parse_report_contract(report_text: str) -> ReportContract:
    """Validate a report and return its authoritative completion contract."""
    lowered = report_text.lower()
    if "<details>" in lowered or "</details>" in lowered:
        raise ContractError(
            "The report contains a <details> or </details> tag. The comment wraps "
            "the report in one <details> element, and recovery cuts at the first "
            "closing tag, so either one truncates the recovered report."
        )
    top_level_lines = _top_level_lines(report_text)
    if EVIDENCE_HEADING not in top_level_lines:
        raise ContractError(
            "The report is missing its merged '### Evidence' section; the "
            "synthesizer did not complete."
        )
    quality_headings = [
        line for line in top_level_lines if line.startswith("### Quality Score:")
    ]
    if len(quality_headings) != 1:
        raise ContractError(
            "The report must contain exactly one Quality Score heading."
        )
    quality_match = QUALITY_SCORE_RE.fullmatch(quality_headings[0])
    if not quality_match:
        raise ContractError(
            "The Quality Score heading must be '### Quality Score: N/100 — "
            "<Fully Clean | Passing | Failing>'."
        )

    findings = open_findings(report_text)
    scored_findings = [
        Finding(item["id"], item["section"], item["severity"]) for item in findings
    ]
    score = score_findings(scored_findings)
    status = review_status(score, scored_findings)
    heading_score = int(quality_match.group(1))
    heading_status = {label: candidate for candidate, label in STATUS_LABELS.items()}[
        quality_match.group(2)
    ]
    if heading_score != score:
        raise ContractError(
            f"The report score {heading_score} contradicts the computed score {score}."
        )
    if heading_status != status:
        raise ContractError(
            f"The report status {heading_status!r} contradicts the computed status "
            f"{status!r}."
        )

    sections = [finding["section"] for finding in findings]
    advisory = (
        score >= CLEAN_MIN_SCORE
        and status == STATUS_PASSING
        and MUST_FIX not in sections
        and SHOULD_FIX in sections
    )
    if advisory:
        summary_directive = "Say the caller will disposition the open findings."
    elif status == STATUS_CLEAN:
        summary_directive = "Say the review is fully clean."
    else:
        summary_directive = "State the status and highest-severity finding."
    return ReportContract(
        score=score,
        status=status,
        open_findings=tuple(findings),
        advisory_completion=advisory,
        summary_directive=summary_directive,
    )


def _require_int(value: object, *, key: str, minimum: int, maximum: int | None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"Metadata '{key}' must be an integer, got {value!r}.")
    if value < minimum:
        raise ContractError(f"Metadata '{key}' must be >= {minimum}, got {value}.")
    if maximum is not None and value > maximum:
        raise ContractError(f"Metadata '{key}' must be <= {maximum}, got {value}.")
    return value


def _require_sha(value: object, *, key: str) -> str:
    if not isinstance(value, str) or not SHA_RE.match(value):
        raise ContractError(
            f"Metadata '{key}' must be 7-40 lowercase hex characters, got {value!r}."
        )
    return value


def validate_plan_source(value: object) -> str:
    """Validate the plan-source value shared by the report and the metadata.

    The value is published twice, in the Run Provenance line and in the metadata
    block, and read by people with no checkout of the machine that produced it.
    A path that resolves only there is refused for the same reason findings may
    not cite one.
    """
    if not isinstance(value, str) or not value:
        raise ContractError("Metadata 'plan_source' must be a non-empty string.")
    if value == NO_PLAN_SOURCE:
        return value
    if value.startswith(SUPPLIED_PLAN_PREFIX) and value[len(SUPPLIED_PLAN_PREFIX) :]:
        suffix = value[len(SUPPLIED_PLAN_PREFIX) :].strip()
        if suffix.startswith(("/", "~")) or _WINDOWS_DRIVE_RE.match(suffix):
            raise ContractError(
                "Metadata 'plan_source' must not publish an absolute or "
                f"home-directory path, got {suffix!r}. Cite the plan by its "
                "repository-relative path or by a short description."
            )
        return value
    raise ContractError(
        "Metadata 'plan_source' must be 'none' or "
        f"'{SUPPLIED_PLAN_PREFIX}<path or short description>', got {value!r}."
    )


def validate_scope_basis(value: object) -> str:
    """Validate a scope basis of ``full-diff`` or ``delta-since:<sha>``."""
    if not isinstance(value, str):
        raise ContractError(f"Metadata 'scope_basis' must be a string, got {value!r}.")
    if value == FULL_DIFF:
        return value
    if value.startswith(DELTA_SINCE_PREFIX):
        _require_sha(value[len(DELTA_SINCE_PREFIX) :], key="scope_basis")
        return value
    raise ContractError(
        f"Metadata 'scope_basis' must be '{FULL_DIFF}' or "
        f"'{DELTA_SINCE_PREFIX}<sha>', got {value!r}."
    )


def validate_metadata(payload: object) -> dict[str, Any]:
    """Return the payload when it is a valid schema-v2 review block.

    Raises ``ContractError`` otherwise. Callers that recover history treat any
    error as "ignore this comment"; callers that publish treat it as a failure.
    """
    if not isinstance(payload, dict):
        raise ContractError("Metadata must be a JSON object.")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(
            f"Metadata 'schema_version' must be {SCHEMA_VERSION}, got "
            f"{payload.get('schema_version')!r}."
        )
    keys = set(payload)
    missing = sorted(METADATA_KEYS - keys)
    unexpected = sorted(keys - METADATA_KEYS)
    if missing or unexpected:
        raise ContractError(
            "Metadata key set mismatch"
            + (f"; missing: {', '.join(missing)}" if missing else "")
            + (f"; unexpected: {', '.join(unexpected)}" if unexpected else "")
            + "."
        )
    if payload["type"] != COMMENT_TYPE:
        raise ContractError(
            f"Metadata 'type' must be '{COMMENT_TYPE}', got {payload['type']!r}."
        )
    _require_int(payload["cycle"], key="cycle", minimum=1, maximum=None)
    _require_int(payload["score"], key="score", minimum=SCORE_FLOOR, maximum=SCORE_MAX)
    if payload["status"] not in STATUSES:
        raise ContractError(
            f"Metadata 'status' must be one of {', '.join(STATUSES)}, got "
            f"{payload['status']!r}."
        )
    if payload["delegation_mode"] not in DELEGATION_MODES:
        raise ContractError(
            "Metadata 'delegation_mode' must be one of "
            f"{', '.join(DELEGATION_MODES)}, got {payload['delegation_mode']!r}."
        )
    validate_status_band(payload["status"], payload["score"])
    validate_plan_source(payload["plan_source"])
    _require_sha(payload["reviewed_sha"], key="reviewed_sha")
    validate_scope_basis(payload["scope_basis"])
    for key in COUNT_KEYS:
        _require_int(payload[key], key=key, minimum=0, maximum=None)
    return payload


def validate_status_band(status: str, score: int) -> None:
    """Reject a status the score cannot support.

    ``review_status`` also consults the finding set, which metadata does not
    carry, so only the score bands are checkable here: below the passing
    threshold the status is always ``failing``, at or above it never is, and
    ``clean`` additionally needs the clean threshold. Without this, a caller can
    publish ``clean`` over a report headed 60/100 — the comment would show one
    verdict, the metadata another, and recovery would route on the metadata.
    """
    if score < PASSING_MIN_SCORE and status != STATUS_FAILING:
        raise ContractError(
            f"A score below {PASSING_MIN_SCORE} is '{STATUS_FAILING}', got "
            f"status {status!r} with score {score}."
        )
    if score >= PASSING_MIN_SCORE and status == STATUS_FAILING:
        raise ContractError(
            f"Status '{STATUS_FAILING}' contradicts a score of {score}."
        )
    if status == STATUS_CLEAN and score < CLEAN_MIN_SCORE:
        raise ContractError(
            f"Status '{STATUS_CLEAN}' needs a score of at least "
            f"{CLEAN_MIN_SCORE}, got {score}."
        )


def build_metadata(
    *,
    cycle: int,
    status: str,
    score: int,
    delegation_mode: str,
    plan_source: str,
    reviewed_sha: str,
    scope_basis: str,
    files_touched: int,
    findings_opened: int,
    findings_closed: int,
) -> dict[str, Any]:
    """Build and validate the schema-v2 metadata payload for a review comment."""
    payload: dict[str, Any] = {
        "cycle": cycle,
        "delegation_mode": delegation_mode,
        "files_touched": files_touched,
        "findings_closed": findings_closed,
        "findings_opened": findings_opened,
        "plan_source": plan_source,
        "reviewed_sha": reviewed_sha,
        "schema_version": SCHEMA_VERSION,
        "scope_basis": scope_basis,
        "score": score,
        "status": status,
        "type": COMMENT_TYPE,
    }
    return validate_metadata(payload)


def render_metadata_block(payload: dict[str, Any]) -> str:
    """Render the hidden metadata block that opens every review comment."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"<!-- {COMMENT_MARKER}\n{encoded}\n-->"


def parse_metadata_block(body: str) -> dict[str, Any] | None:
    """Return the decoded metadata object from a comment body, if it has one.

    Returns the raw object without schema checks so callers can tell a legacy
    v1 comment from a malformed one.
    """
    match = METADATA_BLOCK_RE.search(body)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def is_legacy_review(payload: dict[str, Any]) -> bool:
    """Return True for a schema-v1 review comment kept as legacy history."""
    return payload.get("schema_version") == 1 and payload.get("type") == COMMENT_TYPE


def strip_metadata_block(body: str) -> str:
    """Remove the hidden metadata block from a comment body."""
    return METADATA_BLOCK_RE.sub("", body, count=1).strip()
