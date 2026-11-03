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
