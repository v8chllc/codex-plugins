import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE_PATH = REPO_ROOT / ".agents/plugins/marketplace.json"


def load_json(path: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return data


def test_marketplace_points_to_valid_plugin_manifest() -> None:
    marketplace = load_json(MARKETPLACE_PATH)

    assert marketplace["name"] == "v8ch"
    assert marketplace["interface"] == {"displayName": "Codex Plugins by V8CH"}

    plugins = marketplace["plugins"]
    assert isinstance(plugins, list)
    assert len(plugins) == 1

    entry = plugins[0]
    assert entry["name"] == "v8ch"
    assert entry["category"] == "Developer Tools"
    assert entry["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }

    source = entry["source"]
    assert source == {"source": "local", "path": "./plugins/v8ch"}

    plugin_root = (REPO_ROOT / source["path"]).resolve()
    assert plugin_root.is_dir()
    assert plugin_root.is_relative_to(REPO_ROOT.resolve())

    manifest = load_json(plugin_root / ".codex-plugin/plugin.json")
    assert manifest["name"] == entry["name"]
    assert manifest["version"] == "2.0.1"
    assert manifest["description"]


def test_plugin_manifest_component_paths_exist() -> None:
    manifest_path = REPO_ROOT / "plugins/v8ch/.codex-plugin/plugin.json"
    manifest = load_json(manifest_path)
    plugin_root = manifest_path.parent.parent

    # Codex plugins cannot register agents: the manifest parser drops the key and
    # custom agents load only from ~/.codex/agents or .codex/agents. The roles are
    # skill-bundled prompt assets instead.
    assert "agents" not in manifest
    assert not (plugin_root / "agents").exists()

    value = manifest["skills"]
    assert isinstance(value, str)
    assert value.startswith("./")
    skills_path = (plugin_root / value).resolve()
    assert skills_path.is_relative_to(plugin_root.resolve())
    assert skills_path.is_dir()

    hooks_value = manifest["hooks"]
    assert isinstance(hooks_value, str)
    hooks_path = (plugin_root / hooks_value).resolve()
    assert hooks_path.is_relative_to(plugin_root.resolve())
    hooks: Any = load_json(hooks_path)
    assert set(hooks["hooks"]) == {"Stop", "SessionEnd"}
    for event_name in ("Stop", "SessionEnd"):
        command = hooks["hooks"][event_name][0]["hooks"][0]["command"]
        assert "${PLUGIN_ROOT}/skills/remember/scripts/turn_journal.py" in command
    assert hooks["hooks"]["SessionEnd"][0]["hooks"][0]["timeout"] == 3


def test_all_plugin_skills_have_metadata() -> None:
    skill_root = REPO_ROOT / "plugins/v8ch/skills"
    skill_files = sorted(skill_root.glob("*/SKILL.md"))
    assert {path.parent.name for path in skill_files} == {
        "consensus-review",
        "recommend",
        "remember",
    }

    for skill_file in skill_files:
        text = skill_file.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        header = text.split("---", 2)[1]
        assert "\nname:" in f"\n{header}"
        assert "\ndescription:" in f"\n{header}"


def test_consensus_review_roles_ship_as_skill_bundled_prompt_assets() -> None:
    agent_root = REPO_ROOT / "plugins/v8ch/skills/consensus-review/agents"
    assert {path.stem for path in agent_root.glob("*.md")} == {
        "architecture-reviewer",
        "consensus-review-fixer",
        "consensus-review-poster",
        "correctness-reviewer",
        "review-synthesizer",
        "standards-reviewer",
    }
    # TOML agent definitions are never registered by Codex; the roles must not
    # reappear in that form.
    assert not list(agent_root.glob("*.toml"))
    assert not list(REPO_ROOT.glob("plugins/*/agents/*.toml"))


def test_meta_consensus_review_agents_skill_is_removed() -> None:
    assert not (REPO_ROOT / "plugins/v8ch/skills/meta-consensus-review-agents").exists()


def test_remember_skill_uses_manual_load_and_explicit_setup() -> None:
    skill_dir = REPO_ROOT / "plugins" / "v8ch" / "skills" / "remember"
    skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")

    assert "Workflow A: Manual Load / Status" in skill_text
    assert "Workflow B: Setup" in skill_text
    assert "`$remember setup`" in skill_text
    assert "Do not create files." in skill_text
    assert "do not inject a memory-load directive" in skill_text
    assert "exactly matches the reference content" in skill_text
    assert "Inject `references/agents-md-directive.md`" not in skill_text
    assert "most recent dated file" in skill_text
    assert "$remember hook enable stop-capture" in skill_text
    assert "$remember hook enable session-end-capture" in skill_text
    assert "survive `/clear`" in skill_text
    assert "use this skill's path" in skill_text
    assert "available-skills" in skill_text
    assert "catalog to locate" in skill_text
    assert "resolved `scripts/turn_journal.py`" in skill_text
    assert "<remember-skill-dir>" not in skill_text


def test_recommend_resolves_the_remember_validator_from_the_skill_catalog() -> None:
    skill_path = REPO_ROOT / "plugins/v8ch/skills/recommend/SKILL.md"
    skill_text = skill_path.read_text(encoding="utf-8")

    assert "`v8ch:remember`" in skill_text
    assert "available-skills catalog" in skill_text
    assert "resolve `scripts/validate_memory.py` against the directory" in skill_text
    assert "resulting absolute path to Python" in skill_text
    assert "../remember/scripts/validate_memory.py" not in skill_text
