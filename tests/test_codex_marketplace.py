import json
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE_PATH = REPO_ROOT / ".agents/plugins/marketplace.json"


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    assert manifest["version"] == "1.0.2"
    assert manifest["description"]


def test_plugin_manifest_component_paths_exist() -> None:
    manifest_path = REPO_ROOT / "plugins/v8ch/.codex-plugin/plugin.json"
    manifest = load_json(manifest_path)
    plugin_root = manifest_path.parent.parent

    for component in ("skills", "agents"):
        value = manifest[component]
        assert isinstance(value, str)
        assert value.startswith("./")
        component_path = (plugin_root / value).resolve()
        assert component_path.is_relative_to(plugin_root.resolve())
        assert component_path.is_dir()


def test_all_plugin_skills_have_metadata() -> None:
    skill_root = REPO_ROOT / "plugins/v8ch/skills"
    skill_files = sorted(skill_root.glob("*/SKILL.md"))
    assert {path.parent.name for path in skill_files} == {
        "consensus-review",
        "meta-consensus-review-agents",
        "recommend",
        "remember",
    }

    for skill_file in skill_files:
        text = skill_file.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        header = text.split("---", 2)[1]
        assert "\nname:" in f"\n{header}"
        assert "\ndescription:" in f"\n{header}"


def test_plugin_agents_are_valid_codex_toml() -> None:
    agent_root = REPO_ROOT / "plugins/v8ch/agents"
    agent_files = sorted(agent_root.glob("*.toml"))
    assert {path.stem for path in agent_files} == {
        "acceptance-recommender",
        "consensus-review-fixer",
        "consensus-review-poster",
        "opt-in-recommender",
        "review-synthesizer",
    }
    assert not list(agent_root.glob("*.md"))

    for agent_file in agent_files:
        data = tomllib.loads(agent_file.read_text(encoding="utf-8"))
        assert data["name"] == agent_file.stem
        assert data["description"]
        assert data["model"]
        assert data["model_reasoning_effort"] in {"low", "medium", "high"}
        assert data["sandbox_mode"] in {"read-only", "workspace-write"}
        assert data["developer_instructions"]


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
