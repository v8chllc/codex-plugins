# Agent Instructions

## Scope

This file is for automation agents working in the Codex Plugins repository, a
plugin marketplace for Codex CLI. For project overview and everyday commands,
read `README.md`. For formatting, linting, typing, and testing expectations,
read `CODING_STANDARDS.md`.

## Working Rules

- Inspect the current repository layout before changing plugin or skill
  structure.
- Prefer minimal, targeted edits that match the existing plugin organization.
- Preserve user-created local files and unrelated worktree changes unless the
  user explicitly asks you to remove or revert them.
- Do not commit generated files such as `.DS_Store`, `__pycache__/`, `*.pyc`,
  `node_modules/`, or tool caches.
- If a plugin introduces its own package metadata or test runner, update the
  relevant documentation alongside the code change.
- Keep documentation and metadata aligned with the Codex Plugins name and Codex
  CLI plugin marketplace purpose.
- Keep repo marketplace metadata in `.agents/plugins/marketplace.json`.
- Keep each plugin manifest at `plugins/<plugin>/.codex-plugin/plugin.json`.
- Codex plugins cannot ship agents: the manifest parser drops an `agents` key,
  and custom agents load only from `~/.codex/agents/` or `.codex/agents/`. A
  plugin that needs named roles ships them as skill-bundled prompt assets under
  `plugins/<plugin>/skills/<skill>/agents/` and passes their contents to
  `spawn_agent`.
- Whenever any file under `plugins/<name>/` changes, bump the version in
  `plugins/<name>/.codex-plugin/plugin.json` in the same pull request. A merged
  change with no version bump ships a version already present in installed
  caches, so clients have nothing to refetch and keep running the old code.
- `tests/test_codex_marketplace.py` pins the expected version literally, so it
  moves in the same commit as the bump.

## Validation

Run the checks relevant to the files you changed. For broad changes, use the
full quality suite documented in `CODING_STANDARDS.md`.

## Agent workflow profile

```yaml
tracking: required
merge_method: rebase
quality_commands:
  - npm run lint:md
  - uv run black --check .
  - uv run ruff check .
  - uv run ruff format --check .
  - uv run mypy
  - uv run pytest
release_steps:
  - whenever a file under plugins/<name>/ changes, bump the version in
    plugins/<name>/.codex-plugin/plugin.json and the literal version in
    tests/test_codex_marketplace.py in the same pull request
prohibited_actions:
  - never move private vault content into this public repository
  - never merge; the sponsor merges
synchronized_with: v8chllc/claude-plugins
```
