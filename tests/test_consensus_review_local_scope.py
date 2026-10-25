"""Document tests for the narrowed consensus-review local scope."""

from tests.consensus_review_support import CONSENSUS_REVIEW_DIR


def skill_text() -> str:
    """Read the installed skill source used by these document tests."""
    return (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")


def test_pr_reference_and_local_diff_scope() -> None:
    skill = skill_text()
    assert "A PR/MR number or URL selects the PR/MR path" in skill
    assert "Extract\n   the number from a URL" in skill
    assert "Any other scope argument is ignored" in skill
    assert "git diff <base> HEAD" in skill
    assert "git merge-base <ref> HEAD" in skill
    assert "`origin/HEAD` when it resolves, otherwise local `main`" in skill
    assert "Never fetch" in skill
    assert "Uncommitted changes and untracked files are never" in skill
    assert "part of the local review scope" in skill


def test_local_inputs_and_ordered_preflight() -> None:
    skill = skill_text()
    inputs = skill.split("**Review scope**", 1)[1].split("**Local checks**", 1)[0]
    checks = skill.split("**Local checks**", 1)[1].split("**Plan**", 1)[0]
    assert "plan file and acceptance criteria and Regression" in inputs
    assert "Guards as text or files, each identified as that input" in inputs
    assert "Ignore a\nsingle-cycle cap or `review_budget: single_cycle`" in inputs
    for phrase in (
        "commit SHA",
        "branch name or range",
        "list of paths",
        "path not identified as an accepted",
    ):
        assert phrase in inputs
    assert checks.index("unsupported_scope") < checks.index("dirty_worktree")
    assert checks.index("dirty_worktree") < checks.index("no_base")
    assert checks.index("no_base") < checks.index("NO_DIFF")
    assert "Name the argument in `message`" in checks
    assert "current branch's commits since it left the" in checks
    assert "git status --porcelain=v1 --untracked-files=all" in checks
    assert "working\n   tree must be clean, with nothing untracked" in checks
    assert "commit or stash first" in checks
    assert "default branch could not be resolved" in checks
    assert "fetch or set" in checks
    assert "git merge-base" in checks


def test_local_signal_range_and_abort_reasons() -> None:
    skill = skill_text()
    assert "<ref>@<base-sha>..HEAD@<head-sha>" in skill
    assert "full 40-character lowercase hex SHAs" in skill
    assert "State that same range in the report" in skill
    complete_row = skill.split("| `REVIEW_COMPLETE` |", 1)[1].splitlines()[0]
    no_diff_row = skill.split("| `NO_DIFF` |", 1)[1].splitlines()[0]
    assert "local only: `scope`" in complete_row
    assert "`details.scope`" in no_diff_row
    reasons = skill.split("`ABORT` `reason` is one of", 1)[1].split(
        "**Retry limit:**", 1
    )[0]
    for reason in ("unsupported_scope", "dirty_worktree", "no_base"):
        assert f"`{reason}`" in reasons


def test_removed_local_scope_vocabulary() -> None:
    skill = skill_text().lower()
    for phrase in (
        "base commit",
        "branch diff",
        "file list",
        "all local changes",
        "ls-files --others",
        "levels 2 and 5",
    ):
        assert phrase not in skill
