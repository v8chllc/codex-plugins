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
- Plugin-scoped Codex agent definitions live in `plugins/<plugin>/agents/` as
  TOML files.

## Validation

Run the checks relevant to the files you changed. For broad changes, use the
full quality suite documented in `CODING_STANDARDS.md`.
