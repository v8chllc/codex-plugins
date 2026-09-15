"""Hygiene checks for the consensus-review skill's prose assets.

Codex performs no variable substitution in `SKILL.md` or in a prompt asset, so an
`${...}` placeholder reaches the model literally. Script paths must stay relative
to the skill directory for the same reason: a hardcoded marketplace path is wrong
in every installed cache.
"""

import re
from pathlib import Path

import pytest

from tests.consensus_review_support import CONSENSUS_REVIEW_DIR

UNDEFINED_VARIABLE_RE = re.compile(r"\$\{[^}]*\}")
HARDCODED_SCRIPT_PATH_RE = re.compile(r"plugins/v8ch/skills/[^\s`)]*/scripts/")

ROLE_NAMES = (
    "standards-reviewer",
    "correctness-reviewer",
    "architecture-reviewer",
    "review-synthesizer",
    "consensus-review-poster",
    "consensus-review-fixer",
)

PROSE_ASSETS = sorted(
    [
        CONSENSUS_REVIEW_DIR / "SKILL.md",
        *(CONSENSUS_REVIEW_DIR / "references").glob("*.md"),
        *(CONSENSUS_REVIEW_DIR / "agents").glob("*.md"),
    ]
)


def asset_id(path: Path) -> str:
    return str(path.relative_to(CONSENSUS_REVIEW_DIR))


@pytest.mark.parametrize("path", PROSE_ASSETS, ids=asset_id)
def test_no_undefined_template_variables(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    found = UNDEFINED_VARIABLE_RE.findall(text)
    assert not found, f"{asset_id(path)} contains undefined variables: {found}"


@pytest.mark.parametrize("path", PROSE_ASSETS, ids=asset_id)
def test_no_hardcoded_marketplace_script_paths(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    found = HARDCODED_SCRIPT_PATH_RE.findall(text)
    assert not found, f"{asset_id(path)} hardcodes a script path: {found}"


def test_every_role_ships_a_prompt_asset() -> None:
    agents = CONSENSUS_REVIEW_DIR / "agents"
    assert {path.stem for path in agents.glob("*.md")} == set(ROLE_NAMES)


@pytest.mark.parametrize("name", ROLE_NAMES)
def test_role_assets_use_the_gpt_document_shape(name: str) -> None:
    text = (CONSENSUS_REVIEW_DIR / "agents" / f"{name}.md").read_text(encoding="utf-8")
    assert "## Goal" in text
    assert "## Constraints and authority" in text
    assert "## Output and stop rule" in text


@pytest.mark.parametrize(
    "name", ("standards-reviewer", "correctness-reviewer", "architecture-reviewer")
)
def test_reviewer_assets_require_evidence_and_forbid_mutation(name: str) -> None:
    text = (CONSENSUS_REVIEW_DIR / "agents" / f"{name}.md").read_text(encoding="utf-8")
    assert "## Evidence" in text
    assert "**Files examined:**" in text
    assert "**Commands run:**" in text
    assert "inspect and report; do not implement changes" in text.lower()


def test_synthesizer_is_read_only_and_owns_status() -> None:
    text = (CONSENSUS_REVIEW_DIR / "agents" / "review-synthesizer.md").read_text(
        encoding="utf-8"
    )
    assert "inspect and report; do not implement changes" in text.lower()
    assert "You are the only place status is decided." in text
    for status in ("clean", "passing", "failing"):
        assert f"`{status}`" in text


def test_skill_is_standalone_and_always_autonomous() -> None:
    text = (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "This skill invokes no other skill" in text
    assert "It never prompts the operator." in text
    for removed in ("AUTONOMOUS=", "MAX_AUTONOMOUS_CYCLES", "on_quality_failure"):
        assert removed not in text
    for removed_skill in ("code-quality", "git-ops", "meta-consensus-review-agents"):
        assert removed_skill not in text


def test_skill_spawns_with_both_model_and_effort() -> None:
    text = (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert '`model: "gpt-5.6-sol"`' in text
    assert '`reasoning_effort: "medium"`' in text
    assert "gpt-5.5" not in text
    assert "`fork_context: false`" in text


def test_skill_documents_every_terminal_signal() -> None:
    text = (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")
    for signal in (
        "REVIEW_COMPLETE",
        "NO_DIFF",
        "EVIDENCE_FAILED",
        "QUALITY_FAILURES",
        "BLOCKERS_REMAIN",
        "PUSH_COMPLETE",
        "MAX_REVIEWS_REACHED",
        "ABORT",
    ):
        assert signal in text
    for reason in (
        "head_mismatch",
        "branch_mismatch",
        "platform_auth",
        "post_failed",
        "read_only_role_mutated",
    ):
        assert reason in text
    assert "MAX_CYCLES_REACHED" not in text


def test_fix_workflow_posts_no_comment_and_invokes_no_skill() -> None:
    text = (CONSENSUS_REVIEW_DIR / "references/fix-workflow.md").read_text(
        encoding="utf-8"
    )
    assert "No fix-validation comment is posted." in text
    for removed in ("code-quality", "git-ops", "recommended-only", "threshold` mode"):
        assert removed not in text
    for disposition in ("fixed", "declined", "partial", "work-item-required"):
        assert f"`{disposition}`" in text


def test_removed_comment_types_are_gone_from_the_skill_tree() -> None:
    templates = CONSENSUS_REVIEW_DIR / "templates"
    assert [path.name for path in sorted(templates.glob("*"))] == [
        "review-comment.md.tmpl"
    ]
    assert not (CONSENSUS_REVIEW_DIR / "skip-files.md").exists()
