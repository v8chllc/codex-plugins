"""Fixture tests for the executable scoring contract (contract C-1)."""

import json

import pytest
import review_contract

from tests.consensus_review_support import FIXTURES_DIR

CASES = json.loads((FIXTURES_DIR / "scoring-cases.json").read_text(encoding="utf-8"))[
    "cases"
]


def build_findings(raw: list[dict[str, object]]) -> list[review_contract.Finding]:
    return [
        review_contract.Finding(
            id=str(entry["id"]),
            section=str(entry["section"]),
            severity=(
                str(entry["severity"]) if entry.get("severity") is not None else None
            ),
            demonstrated=bool(entry.get("demonstrated", True)),
        )
        for entry in raw
    ]


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_scoring_cases(case: dict[str, object]) -> None:
    findings = build_findings(case["findings"])  # type: ignore[arg-type]
    score = review_contract.score_findings(findings)
    assert score == case["expected_score"]
    assert review_contract.resolve_status(score, findings) == case["expected_status"]


def test_deduction_table_matches_the_contract() -> None:
    assert review_contract.DEDUCTIONS == {
        "CRITICAL": 20,
        "HIGH": 10,
        "MEDIUM": 5,
        "LOW": 2,
    }


def test_latent_finding_deducts_at_its_would_be_severity() -> None:
    latent = review_contract.Finding(id="F-1", section="latent", severity="CRITICAL")
    must_fix = review_contract.Finding(
        id="F-1", section="must_fix", severity="CRITICAL"
    )
    assert review_contract.deduction(latent) == review_contract.deduction(must_fix)


def test_plan_note_rejects_a_severity() -> None:
    with pytest.raises(ValueError):
        review_contract.Finding(id="F-1", section="plan_note", severity="LOW")


def test_unknown_section_and_severity_are_rejected() -> None:
    with pytest.raises(ValueError):
        review_contract.Finding(id="F-1", section="nope", severity="LOW")
    with pytest.raises(ValueError):
        review_contract.Finding(id="F-1", section="must_fix", severity="SEVERE")


def test_clean_requires_both_the_score_and_an_empty_blocking_set() -> None:
    blocking = [review_contract.Finding(id="F-1", section="should_fix", severity="LOW")]
    assert review_contract.score_findings(blocking) == 98
    assert review_contract.resolve_status(98, blocking) == "passing"
    assert review_contract.resolve_status(98, []) == "clean"


def test_status_thresholds_are_mutually_exclusive() -> None:
    assert review_contract.resolve_status(95, []) == "clean"
    assert review_contract.resolve_status(94, []) == "passing"
    assert review_contract.resolve_status(85, []) == "passing"
    assert review_contract.resolve_status(84, []) == "failing"


def test_score_breakdown_preserves_emission_order() -> None:
    findings = build_findings(
        [
            {"id": "F-1", "section": "must_fix", "severity": "HIGH"},
            {"id": "F-2", "section": "plan_note"},
            {"id": "F-3", "section": "should_fix", "severity": "MEDIUM"},
        ]
    )
    assert review_contract.score_breakdown(findings) == [
        ("F-1", 10),
        ("F-2", 0),
        ("F-3", 5),
    ]


def test_extract_quality_score_reads_the_report_heading() -> None:
    report = (FIXTURES_DIR / "sample-report.md").read_text(encoding="utf-8")
    assert review_contract.extract_quality_score(report) == 88
    assert review_contract.extract_quality_score("no heading here") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("abc1234", True),
        ("a" * 40, True),
        ("abc123", False),
        ("a" * 41, False),
        ("ABC1234", False),
        ("xyz1234", False),
        (1234567, False),
    ],
)
def test_sha_validation(value: object, expected: bool) -> None:
    assert review_contract.is_valid_sha(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("full-diff", True),
        ("delta-since:abc1234", True),
        ("delta-since:xyz", False),
        ("delta", False),
    ],
)
def test_scope_basis_validation(value: object, expected: bool) -> None:
    assert review_contract.is_valid_scope_basis(value) is expected


def test_booleans_are_not_accepted_as_integers() -> None:
    assert review_contract.is_valid_score(True) is False
    assert review_contract.is_non_negative_int(False) is False
    assert review_contract.is_non_negative_int(0) is True
    assert review_contract.is_non_negative_int(-1) is False
