# Codex Plugins

Codex Plugins is a plugin marketplace for Codex CLI. It packages reusable
skills and agents for Codex CLI workflows.

## Installation

Add the marketplace from GitHub:

```sh
codex plugin marketplace add v8chllc/codex-plugins
```

For local development, add the repository checkout instead:

```sh
codex plugin marketplace add ./codex-plugins
```

Then restart Codex, open `/plugins`, choose **Codex Plugins by V8CH**, and
install the `v8ch` plugin.

## Repository Layout

- `plugins/` contains Codex CLI plugin-owned assets, grouped by owner or
  organization.
- `plugins/<owner>/agents/` contains agent definitions and supporting prompts
  when a plugin includes agent-facing assets.
- `plugins/<owner>/.codex-plugin/plugin.json` contains the Codex plugin
  manifest.
- `.agents/plugins/marketplace.json` contains the Codex marketplace catalog.
- `plugins/<owner>/skills/<skill-name>/` contains reusable skill packages when a
  plugin includes skill-facing assets.
- `plugins/<owner>/skills/<skill-name>/scripts/` contains helper scripts used by
  skills.
- `tests/` contains Python tests for plugin and skill behavior.

## Development

Install Node dependencies before running Markdown checks:

```sh
npm ci
npm run lint:md
```

Python quality tools are configured in `pyproject.toml`:

```sh
black --check .
ruff check .
ruff format --check .
mypy
pytest
```

GitHub Actions runs these checks on each push. See `CODING_STANDARDS.md` for code style and testing expectations.
