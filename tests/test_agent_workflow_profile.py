import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILE_HEADING = "## Agent workflow profile"
QUALITY_COMMANDS = [
    "npm run lint:md",
    "uv run black --check .",
    "uv run ruff check .",
    "uv run ruff format --check .",
    "uv run mypy",
    "uv run pytest",
]
EXPECTED_PROFILE = {
    "tracking": "required",
    "merge_method": "rebase",
    "quality_commands": QUALITY_COMMANDS,
    "release_steps": [
        "whenever a file under plugins/<name>/ changes, bump the version in "
        "plugins/<name>/.codex-plugin/plugin.json and the literal version in "
        "tests/test_codex_marketplace.py in the same pull request"
    ],
    "prohibited_actions": [
        "never move private vault content into this public repository",
        "never merge; the sponsor merges",
    ],
    "synchronized_with": "v8chllc/claude-plugins",
}


def load_profile(text: str) -> dict[str, Any]:
    assert text.count(PROFILE_HEADING) == 1
    match = re.search(
        rf"(?ms)^{re.escape(PROFILE_HEADING)}\n\n```yaml\n(.*?)^```$", text
    )
    assert match is not None, "agent workflow profile must be a fenced YAML block"
    profile = yaml.safe_load(match.group(1))
    assert isinstance(profile, dict)
    return profile


def workflow_commands(text: str) -> set[str]:
    workflow = yaml.safe_load(text)
    steps = workflow["jobs"]["quality"]["steps"]
    return {
        command
        for step in steps
        if "run" in step
        for command in step["run"].splitlines()
        if command
    }


def assert_quality_commands_in_ci(
    profile_commands: list[str], ci_commands: set[str]
) -> None:
    missing = [command for command in profile_commands if command not in ci_commands]
    assert not missing, f"CI workflow is missing profile quality commands: {missing}"


def test_agent_workflow_profile_matches_pinned_contract() -> None:
    agents_text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    profile = load_profile(agents_text)

    assert list(profile) == list(EXPECTED_PROFILE)
    assert profile == EXPECTED_PROFILE


def test_profile_quality_commands_match_ci() -> None:
    profile = load_profile((REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8"))
    workflow_text = (REPO_ROOT / ".github/workflows/code-quality.yml").read_text(
        encoding="utf-8"
    )

    assert "pip install" not in workflow_text
    commands = workflow_commands(workflow_text)
    assert_quality_commands_in_ci(profile["quality_commands"], commands)
    python_checks = {
        command
        for command in commands
        if any(tool in command.split() for tool in ("black", "ruff", "mypy", "pytest"))
    }
    assert all(command.startswith("uv run ") for command in python_checks)


def test_missing_ci_command_diagnostic_names_full_command() -> None:
    missing_command = "uv run pytest"

    with pytest.raises(AssertionError, match=re.escape(missing_command)):
        assert_quality_commands_in_ci(QUALITY_COMMANDS, {"npm run lint:md"})


@pytest.mark.parametrize("document", ["README.md", "CODING_STANDARDS.md"])
def test_documented_quality_commands_match_profile(document: str) -> None:
    text = (REPO_ROOT / document).read_text(encoding="utf-8")

    for command in ["uv sync", "npm ci", *QUALITY_COMMANDS]:
        assert command in text
    for bare_command in [
        "black --check .",
        "ruff check .",
        "ruff format --check .",
        "mypy",
        "pytest",
    ]:
        assert f"\n{bare_command}\n" not in text
