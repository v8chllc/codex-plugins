# Shared Memory Operations

This plugin-root directory owns the contracts used directly by both Remember
and Recommend. Neither skill delegates to the other or resolves assets through
its sibling's directory.

| Resource | Shared operation |
| --- | --- |
| `references/types.md` | Curated types, entry templates, and evidence rules |
| `references/procedural-targets.md` | Procedural target allowlist and routing |
| `references/journal-format.md` | Daily journal marker, format, and retry dedupe |
| `references/recording.md` | Curated add/update, procedural patch, and journal append rules |
| `scripts/validate_memory.py` | Validation preflight and CLI report schema |

An installed Codex skill resolves this directory from its own catalog-listed
`SKILL.md`: ascend twice from the skill directory to the plugin root, then
open `memory/<resource>`. Remember alone owns lifecycle hooks, segment details,
setup, direct record, and review. Recommend owns candidate selection, approval,
preflight, and application for every `/recommend` route. Its approved curated or
procedural writes use the shared recording contract only after preflight.
