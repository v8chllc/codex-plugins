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
    assert "against it into an absolute path" in text
    assert "unchanged full prompt and" in text
    for role in ROLES:
        assert f"agents/{role}.md" in text


def test_every_fresh_role_receives_post_merge_authority_context() -> None:
    text = " ".join((ROOT / "post-merge-review/SKILL.md").read_text().split())
    reviewers = text.split("3. **Delegate independent reviews.**")[1].split(
        "4. **Apply the evidence gate.**"
    )[0]
    for restriction in (
        "Append this invocation context to every role and synthesizer prompt, "
        "including retries",
        "Actual repository root, merge SHA, external run directory",
        "caller-prepared dependencies/check environment with any reuse limits",
        "No installation, dependency bootstrapping, fetching, ref switching",
        "checkout repair, database reset or backup restoration",
        "Leave unprepared or unsafe checks unrun and name gaps without claiming a pass",
        "Temporary files only in that directory with role-prefixed names",
        "no source, environment, ignore-rule, input-report or private-backup changes",
    ):
        assert restriction in reviewers
    synthesizer = text.split("5. **Synthesize.**")[1].split(
        "6. **Format, validate and return.**"
    )[0]
    assert "invocation context from step 3" in synthesizer
    assert "retry within step 4's limit" in synthesizer
    assert "The synthesizer alone decides score/status" in synthesizer
