"""Keep the four reused role assets identical to their consensus originals."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "plugins/v8ch/skills"
ROLES = (
    "standards-reviewer",
    "correctness-reviewer",
    "architecture-reviewer",
    "review-synthesizer",
)


@pytest.mark.parametrize("role", ROLES)
def test_reused_role_is_byte_identical(role: str) -> None:
    original = ROOT / "consensus-review/agents" / f"{role}.md"
    reused = ROOT / "post-merge-review/agents" / f"{role}.md"
    assert reused.read_bytes() == original.read_bytes()


def test_only_four_roles_ship_and_wiring_resolves_installed_assets() -> None:
    skill = ROOT / "post-merge-review"
    assert {path.stem for path in (skill / "agents").glob("*.md")} == set(ROLES)
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert "available-skills catalog" in text
    assert "absolute path before use" in text
    assert "full prompt contents followed by its inputs" in text
    for role in ROLES:
        assert f"agents/{role}.md" in text


def test_every_fresh_role_receives_post_merge_authority_context() -> None:
    text = " ".join((ROOT / "post-merge-review/SKILL.md").read_text().split())
    reviewers = text.split("3. **Delegate independent reviews.**")[1].split(
        "4. **Apply the evidence gate unchanged.**"
    )[0]
    for restriction in (
        "Append the following invocation-specific context after each unchanged prompt",
        "every initial, fallback and retry invocation",
        "actual prepared repository root, merge SHA, absolute reserved run directory",
        "caller-prepared compatible dependencies and safe selected-check environment",
        "explicit workspace/database-reuse authorization and its limits",
        "generic role directions to install dependencies or write external scratch "
        "are narrowed",
        "do not install tools/dependencies",
        "Do not let a check bootstrap missing dependencies",
        "Leave unprepared or unsafe checks unrun",
        "Existing evidence-gate requirements still apply",
        "only in the supplied external run directory",
        "role-prefixed names",
        "`check --run-dir <run-dir> <absolute-output-path>`",
        "create the file exclusively",
        "No outside scratch writes",
        "private-backup changes",
    ):
        assert restriction in reviewers
    synthesizer = text.split("5. **Synthesize once evidence passes.**")[1].split(
        "6. **Format, validate and return.**"
    )[0]
    assert "Append the complete invocation-specific context from step 3" in synthesizer
    assert "every synthesis retry" in synthesizer
    assert "fresh context must receive these limits explicitly" in synthesizer
    assert "The synthesizer alone decides score and status" in synthesizer
