# Codex Plugins Coding Standards

Codex Plugins is a plugin marketplace for Codex CLI. Keep repository content,
examples, package metadata, and documentation aligned with that purpose.

## Python

Use Python 3.11-compatible syntax. Format with Black at the repository default
line length of 88 characters, and keep Ruff lint and format checks clean. Python
modules and files should use `snake_case.py`; plugin directories should use
lowercase hyphenated names such as `consensus-review`.

Prefer standard-library modules unless a dependency is needed for the plugin or
skill to work. Keep scripts focused on one task. Move shared behavior into a
local helper module rather than duplicating logic across scripts.

## Markdown

Use concise headings, direct prose, and fenced code blocks for commands or
examples. Run `npm run lint:md` before opening a pull request.

## Codex Plugin Metadata

Marketplace metadata lives in `.agents/plugins/marketplace.json`. Use the
marketplace `name` `v8ch`, set `interface.displayName`, and include
`policy.installation`, `policy.authentication`, and `category` on every plugin
entry. Plugin `source.path` values must be relative to the repository root,
start with `./`, and stay inside the repository.

Each plugin must include `plugins/<plugin>/.codex-plugin/plugin.json` with
`name`, `version`, and `description`. Component paths such as `skills` and
`agents` must be relative paths that start with `./`.

## Testing

Place tests in `tests/` or in a plugin-local `tests/` directory when that keeps
fixtures close to the implementation. Name Python tests `test_<behavior>.py`.
For script-style utilities, cover argument parsing, expected output, and failure
paths. Avoid relying on local machine state; use fixtures or temporary
directories for file-system behavior.

## Quality Checks

Run the same checks used by CI before pushing:

```sh
npm run lint:md
black --check .
ruff check .
ruff format --check .
mypy
pytest
```
