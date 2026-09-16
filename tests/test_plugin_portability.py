"""Portability guards for every Codex plugin instruction asset."""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins/v8ch"

# Codex performs no substitution in SKILL.md. Instruction assets must resolve
# script paths from the installed SKILL.md location instead of naming a checkout,
# cache, home directory, other absolute installation path, or sibling skill.
HARDCODED_SKILL_SCRIPT_PATH_RE = re.compile(
    r"plugins/[^\s/`'\"]+/skills/[^\s/`'\"]+/scripts/"
    r"|(?:~|/)[^\s`'\"]*/skills/[^\s/`'\"]+/scripts/"
    r"|[^\s`'\"]*cache/[^\s`'\"]*/skills/[^\s/`'\"]+/scripts/"
    r"|(?:\.\./)+[A-Za-z0-9][A-Za-z0-9_-]*/scripts/"
)
UNEXPANDED_CODEX_PLACEHOLDER_RE = re.compile(
    r"\$\{[^}\n]+\}|<[A-Za-z0-9][A-Za-z0-9_-]*-skill-dir>"
)


def instruction_assets() -> list[Path]:
    """Return every plugin instruction asset that must stay path-portable."""
    return sorted((PLUGIN_ROOT / "skills").rglob("*.md"))


@pytest.mark.parametrize("asset", instruction_assets(), ids=lambda path: path.name)
def test_instruction_assets_use_portable_skill_script_paths(asset: Path) -> None:
    text = asset.read_text(encoding="utf-8")
    hardcoded_path = HARDCODED_SKILL_SCRIPT_PATH_RE.search(text)
    path_hit = hardcoded_path.group(0) if hardcoded_path else ""
    assert hardcoded_path is None, (
        f"{asset.relative_to(REPO_ROOT)} hardcodes '{path_hit}'. "
        "Resolve scripts/<name>.py against the installed SKILL.md instead."
    )

    placeholder = UNEXPANDED_CODEX_PLACEHOLDER_RE.search(text)
    placeholder_hit = placeholder.group(0) if placeholder else ""
    assert placeholder is None, (
        f"{asset.relative_to(REPO_ROOT)} contains the unexpanded Codex "
        f"placeholder '{placeholder_hit}'. Resolve installed skill paths from "
        "the available-skills catalog instead."
    )


@pytest.mark.parametrize(
    "hardcoded_path",
    [
        "plugins/v8ch/skills/remember/scripts/validate_memory.py",
        "/opt/codex/plugins/v8ch/skills/remember/scripts/validate_memory.py",
        "/var/cache/codex/v8ch/2.0.1/skills/remember/scripts/validate_memory.py",
        "~/.codex/skills/remember/scripts/validate_memory.py",
        "/Users/alice/.codex/plugins/cache/v8ch/v8ch/2.0.1/skills/remember/"
        "scripts/validate_memory.py",
        "../remember/scripts/validate_memory.py",
    ],
)
def test_path_regex_catches_hardcoded_skill_script_locations(
    hardcoded_path: str,
) -> None:
    assert HARDCODED_SKILL_SCRIPT_PATH_RE.search(f'python "{hardcoded_path}"')


def test_path_regex_allows_current_skill_script_references() -> None:
    assert HARDCODED_SKILL_SCRIPT_PATH_RE.search("scripts/validate_memory.py") is None


@pytest.mark.parametrize(
    "placeholder",
    [
        "<remember-skill-dir>",
        "<consensus-review-skill-dir>",
        "<future_skill-skill-dir>",
        "${PLUGIN_ROOT}",
        "${HOME}",
    ],
)
def test_placeholder_regex_catches_unexpanded_codex_values(
    placeholder: str,
) -> None:
    assert UNEXPANDED_CODEX_PLACEHOLDER_RE.search(placeholder)


@pytest.mark.parametrize("metavariable", ["<channel>", "<name>", "<YYYY-MM-DD>"])
def test_placeholder_regex_allows_generic_instruction_metavariables(
    metavariable: str,
) -> None:
    assert UNEXPANDED_CODEX_PLACEHOLDER_RE.search(metavariable) is None
