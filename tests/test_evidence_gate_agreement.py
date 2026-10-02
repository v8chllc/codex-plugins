"""The consensus-review evidence gate exists twice: in the skill's step 6 and in
the review synthesizer's step 1. When the copies disagree on one report, the
review has no defined outcome, so each role's outcome is pinned in both."""

import re

import pytest

from tests.consensus_review_support import CONSENSUS_REVIEW_DIR

SKILL = CONSENSUS_REVIEW_DIR / "SKILL.md"
SYNTHESIZER = CONSENSUS_REVIEW_DIR / "agents" / "review-synthesizer.md"

# Each clause states one role's `Commands run` outcome. Both gates must carry
# every clause verbatim once whitespace is normalized.
OUTCOME_CLAUSES = [
    "`standards-reviewer` whose `Commands run` names no command, such as `none` "
    "in any form, including `none (read-only review)`, is a failed pass",
    "`Commands run: none` in any form from `correctness-reviewer` or "
    "`architecture-reviewer` is a complete, passing value",
]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def skill_gate() -> str:
    text = SKILL.read_text(encoding="utf-8")
    return normalize(section(text, "### 6. Apply the evidence gate", "\n### 7."))


def synthesizer_gate() -> str:
    text = SYNTHESIZER.read_text(encoding="utf-8")
    return normalize(section(text, "### 1. Apply the evidence gate", "\n### 2."))


@pytest.mark.parametrize("clause", OUTCOME_CLAUSES)
def test_both_gates_state_the_same_outcome(clause: str) -> None:
    assert clause in skill_gate(), f"SKILL.md step 6 no longer states: {clause}"
    assert clause in synthesizer_gate(), (
        f"review-synthesizer.md step 1 no longer states: {clause}"
    )


def test_the_synthesize_step_handles_a_failed_status() -> None:
    text = normalize(
        section(SKILL.read_text(encoding="utf-8"), "### 8. Synthesize", "\n### 9.")
    )
    assert "`### Review Status: FAILED`" in text
    assert "A pass that fails a second time, at either gate" in text
    assert "`EVIDENCE_FAILED`" in text
