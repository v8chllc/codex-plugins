"""Pin required PR/MR scope and its early unsupported-scope abort."""

from pathlib import Path

SKILL = (
    Path(__file__).resolve().parents[1]
    / "plugins/v8ch/skills/consensus-review/SKILL.md"
)


def test_pr_mr_reference_is_required_and_missing_input_aborts() -> None:
    text = SKILL.read_text(encoding="utf-8")
    inputs = text.split("## Inputs\n")[1].split("## Plan handling\n")[0]
    normalized = " ".join(inputs.split())
    assert "**PR/MR reference** (required)" in inputs
    assert "Without one, emit `ABORT`" in normalized
    assert "`reason` `unsupported_scope` before workflow step 1" in normalized
    assert "PR/MR number or URL is required" in normalized
    assert "Do not infer scope from a commit, branch, or paths" in normalized


def test_scope_still_uses_platform_diff_and_checks_head() -> None:
    text = SKILL.read_text(encoding="utf-8")
    inputs = text.split("## Inputs\n")[1].split("## Plan handling\n")[0]
    normalized = " ".join(inputs.split())
    assert "gh pr diff <number>" in inputs
    assert "glab mr diff <number>" in inputs
    assert "local `HEAD` equals the PR/MR head SHA first" in normalized
    assert "head_mismatch" in inputs
    assert "NO_DIFF" in inputs
    signals = text.split("## Output and stop rule\n")[1]
    assert "local only:" not in signals
    assert "`details.scope`" not in signals
    post = text.split("### 9. Post or return\n")[1].split("### 10. Branch on status\n")[
        0
    ]
    assert "**No PR/MR:**" not in post
    assert "consensus-review-poster" in post
