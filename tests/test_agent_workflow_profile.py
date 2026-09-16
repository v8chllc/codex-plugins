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
SETUP_COMMANDS = {"npm ci", "uv sync"}
DOCUMENTED_COMMAND_BLOCKS = [
    (
        "README.md",
        "## Development",
        (
            "Install the locked Python and Node development dependencies:",
            "Run the repository quality commands:",
        ),
    ),
    (
        "CODING_STANDARDS.md",
        "## Quality Checks",
        (
            "Install the locked development dependencies, then run the same checks "
            "used by\nCI before pushing:",
        ),
    ),
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


def markdown_section(text: str, heading: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(heading)}\n(?P<section>.*?)(?=^## |\Z)", text)
    assert match is not None, f"documented section is missing: {heading}"
    return match.group("section")


def command_block_after(section: str, label: str) -> str:
    matches = list(
        re.finditer(
            rf"^{re.escape(label)}\n\n```(?:sh|bash)\n(?P<commands>.*?)\n```",
            section,
            flags=re.DOTALL | re.MULTILINE,
        )
    )
    assert len(matches) == 1, f"expected one command block after: {label}"
    return matches[0].group("commands")


def assert_documented_commands(
    text: str, section_heading: str, block_labels: tuple[str, ...], expected: set[str]
) -> None:
    section = markdown_section(text, section_heading)
    actual = {
        line.strip()
        for label in block_labels
        for line in command_block_after(section, label).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if actual != expected:
        raise AssertionError(
            f"documented commands differ; missing: {missing}; unexpected: {unexpected}"
        )


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


@pytest.mark.parametrize(
    ("document", "section_heading", "block_labels"), DOCUMENTED_COMMAND_BLOCKS
)
def test_documented_quality_commands_match_profile(
    document: str, section_heading: str, block_labels: tuple[str, ...]
) -> None:
    text = (REPO_ROOT / document).read_text(encoding="utf-8")
    profile = load_profile((REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8"))
    expected = SETUP_COMMANDS | set(profile["quality_commands"])

    assert_documented_commands(text, section_heading, block_labels, expected)


@pytest.mark.parametrize(
    ("document", "section_heading", "block_labels"), DOCUMENTED_COMMAND_BLOCKS
)
def test_documented_command_check_rejects_suffixed_governed_command(
    document: str, section_heading: str, block_labels: tuple[str, ...]
) -> None:
    text = (REPO_ROOT / document).read_text(encoding="utf-8")
    expected = SETUP_COMMANDS | set(QUALITY_COMMANDS)
    text = text.replace(
        "uv run pytest\n```",
        "uv run pytest --ignore=tests/test_agent_workflow_profile.py\n```",
        1,
    )

    with pytest.raises(AssertionError, match=r"unexpected: .*--ignore"):
        assert_documented_commands(text, section_heading, block_labels, expected)


@pytest.mark.parametrize(
    ("document", "section_heading", "block_labels"), DOCUMENTED_COMMAND_BLOCKS
)
def test_documented_command_check_rejects_extra_governed_command(
    document: str, section_heading: str, block_labels: tuple[str, ...]
) -> None:
    text = (REPO_ROOT / document).read_text(encoding="utf-8")
    expected = SETUP_COMMANDS | set(QUALITY_COMMANDS)
    text = text.replace("uv run pytest\n```", "uv run pytest\nuv run pylint\n```", 1)

    with pytest.raises(AssertionError, match=r"unexpected: \['uv run pylint'\]"):
        assert_documented_commands(text, section_heading, block_labels, expected)


@pytest.mark.parametrize(
    ("document", "section_heading", "block_labels"), DOCUMENTED_COMMAND_BLOCKS
)
def test_documented_command_check_ignores_unrelated_examples(
    document: str, section_heading: str, block_labels: tuple[str, ...]
) -> None:
    text = (REPO_ROOT / document).read_text(encoding="utf-8")
    expected = SETUP_COMMANDS | set(QUALITY_COMMANDS)
    nested_example = "\n### Unrelated Example\n\n```sh\npytest --fixtures\n```\n"
    outside_example = "\n## Unrelated Section\n\n```sh\nruff check example.py\n```\n"
    text = text.replace(section_heading, section_heading + nested_example, 1)
    text += outside_example

    assert_documented_commands(text, section_heading, block_labels, expected)
