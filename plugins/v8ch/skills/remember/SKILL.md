---
name: remember
description: "Load existing project memory, set up memory storage, record structured memories, or capture session notes across four lanes: daily journal, curated memory, local context, and procedural memory. Trigger when: user says 'remember [type] [content]' or 'remember that [content]'; user invokes $remember with or without args; user invokes $remember setup, $remember session, $remember procedure, $remember workflow, $remember standard, or $remember review; user says 'setup remember', 'remember in this project', or 'initialize memory here'. For /recommend commands use the recommend skill."
---

# Remember Skill

Manages five memory lanes for the current working directory:

1. **Daily Journal** — episodic session notes in `.remember/memory/YYYY-MM-DD.md`
2. **Curated Memory** — durable structured entries in `.remember/MEMORY.md`
3. **Local Context** — current working state in `.remember/local/context.md`,
   gitignored so it never reaches another checkout
4. **Procedural Memory** — behavior-changing guidance in approved agent-facing targets
5. **Lifecycle Journal** — independently opt-in, immutable `version: 3` Stop
   and SessionEnd records in the shared, flat store `.remember/turns/`, used to
   preserve work across `/clear` and terminal session shutdown. Both Claude and
   Codex write into this one store; each record carries its own `platform`.

`.remember/MEMORY.md` travels through Git, so every checkout reads what any
checkout wrote. Context is state as of a moment on one machine, which makes it
the one type that must not travel: it lives in `.remember/local/context.md`
alone.

See `references/types.md` for curated memory type templates and examples.
See `references/agents-md-directive.md` for the legacy generated directive block
that setup may remove from `AGENTS.md` only by exact match.
See `references/journal-format.md` for journal entry format and dedupe marker spec.
See `references/procedural-targets.md` for the approved procedural target allowlist.
Use `scripts/validate_memory.py` for deterministic memory validation, JSON
reporting, and setup-aware Memory Fast-Track steering checks.

---

## Trigger patterns

**Manual load — any of:**
- `$remember` (no args)

**Setup — any of:**
- `$remember setup`
- Natural language: "setup remember", "remember in this project", "initialize memory here"

**Validation:**
- `$remember validate`
- `$remember validate --json`
- Natural language: "validate remember", "validate memory"

**Journal write:**
- `$remember session`
- Natural language: "capture this session", "write to journal"

**Lifecycle capture:**
- `$remember hook enable stop-capture`
- `$remember hook disable stop-capture`
- `$remember hook status stop-capture`
- `$remember hook enable session-end-capture`
- `$remember hook disable session-end-capture`
- `$remember hook status session-end-capture`
- `$remember clean [--apply]`

**Recommend:** use the `recommend` skill (`/recommend session`, `/recommend curated`, `/recommend procedural`).

**Review — slash command or natural language:**
- `$remember review`
- "review memory", "audit memories", "clean up remember"

**Procedural write:**
- `$remember procedure <text>`
- `$remember workflow <text>`
- `$remember standard <text>`

**Record — slash command:**
- `$remember entity <identifier>`
- `$remember decision <text>`
- `$remember error <text>`
- `$remember context <text>`
- `$remember preference <text>`
- `$remember todo <text>`

**Record — natural language (auto-invoke):**
- "Remember the entity `<identifier>`"
- "Remember the decision `<text>`"
- "Remember the error `<text>`"
- "Remember the context `<text>`"
- "Remember the preference `<text>`"
- "Remember the todo `<text>`"
- "Remember that `<text>`" — type inferred from content

---

## Workflow A: Manual Load / Status

Triggered by `$remember` with no args.

1. Check whether `.remember/MEMORY.md` and `.remember/memory/` exist in cwd.
   - If either is missing: perform a concise project-context inspection: read a
     root `README.md` and `AGENTS.md` when present, list top-level files, and
     report the tracked-file inventory (`git ls-files` when available). Then
     say memory is not initialized and tell the user to run `$remember setup`.
     Do not create files.
2. Read `.remember/MEMORY.md`.
3. Read `.remember/local/context.md` when present, and compute its age in days
   from the `Updated` field against today's date.
4. Find the most recent dated file matching `.remember/memory/YYYY-MM-DD.md`.
   Read it regardless of age; do not limit the lookup to today or yesterday.
5. If no dated journal exists, report that explicitly.
6. Respond with a concise status report:
   - durable memory loaded from `.remember/MEMORY.md`
   - local context loaded from `.remember/local/context.md`, reported as local,
     non-shared state, with its `Updated` date and age in days; or no local
     context exists. When the entry is more than 3 days old, say it is
     possibly stale and should be checked against the working tree before it is
     relied on.
   - most recent daily journal loaded or absent
   - optional procedural targets present or missing:
     `CODING_STANDARDS.md`, `ARCHITECTURE_STANDARDS.md`,
     `WORKFLOW_STANDARDS.md`

## Workflow B: Setup

Triggered by `$remember setup` or natural language setup phrases.

### Core memory setup

1. Create `.remember/` in cwd if it is missing.
2. Create `.remember/memory/` for the journal lane if it is missing.
3. Create `.remember/local/` for the local context lane if it is missing.
4. Ensure `.remember/local/` is git-ignored; run
   `git check-ignore -q .remember/local` to check. If it is not ignored and a
   `.gitignore` exists, append the rule `.remember/local/`. If no `.gitignore`
   exists, ask before creating one. An unignored local lane defeats the point of
   the lane, so do not migrate context into it until the path is ignored.
5. If `.remember/MEMORY.md` is missing, write this stub:

```
# Memory

<!-- This file is read by Codex at the start of every session.         -->
<!-- Use $remember to record entries, or edit directly.                  -->
<!-- Types: entity | decision | error | preference | todo                -->
<!-- Context is local-only; it lives in .remember/local/context.md.      -->

## entity

## decision

## error

## preference

## todo
```

6. If `.remember/MEMORY.md` holds a `<!-- context -->` entry, report it and offer
   to move it verbatim into `.remember/local/context.md`, then remove the entry
   and its `## context` heading from `.remember/MEMORY.md`. Move it only after
   user approval. If `.remember/local/context.md` already holds an entry, show
   both and ask which to keep; never merge them silently.
7. If `AGENTS.md` exists, compare its `## Memory` section to
   `references/agents-md-directive.md`.
   - If the section exactly matches the reference content, remove that generated
     section from `AGENTS.md`.
   - If a `## Memory` section exists but differs from the reference content,
     leave it unchanged and report that manual review is needed.
   - If no `## Memory` section exists, leave `AGENTS.md` unchanged.
8. Do not create `AGENTS.md` and do not inject a memory-load directive.
9. Confirm to the user with a summary of files created, existing files reused,
   directive cleanup performed, context migrated, and any manual review needed.
10. Run validation and steering detection from the repository root:
   `python plugins/v8ch/skills/remember/scripts/validate_memory.py --root . --toolchain codex --check-steering`.
   Report the validation status and issues. Validation must not mutate files.
11. If `AGENTS.md` is missing a `## Memory Fast-Track Workflow` section, report
   the gap and ask whether to append generated Codex-appropriate guidance.
   Apply it only after user approval with:
   `python plugins/v8ch/skills/remember/scripts/validate_memory.py --root . --toolchain codex --apply-fast-track`.
   If `AGENTS.md` has related but non-matching fast-track guidance, avoid
   destructive edits and ask for manual review or explicit approval.

### Status report

After core memory is confirmed present, inspect and report:

- **Journal lane**: is `.remember/memory/` present? List today's journal file if it exists.
- **Local context lane**: is `.remember/local/` present and git-ignored? Does
  `.remember/local/context.md` exist? Report whether a context migration was
  performed, offered and declined, or not needed.
- **Procedural targets**: for each of `CODING_STANDARDS.md`, `ARCHITECTURE_STANDARDS.md`, `WORKFLOW_STANDARDS.md` — present or missing? Report as optional managed targets. Do not create them automatically; offer stubs only on request.
- **Validation**: summarize pass/fail counts and actionable issues from
  `scripts/validate_memory.py`.
- **Memory Fast-Track steering**: report present, missing, added after approval,
  skipped, or manual-review-needed.

---

## Workflow C: Record (typed)

Triggered by `$remember <type> <content>` or natural language equivalent.

1. **Guard**: check `.remember/MEMORY.md` and `.remember/memory/` exist. If
   either is missing, tell the user to run `$remember setup` first and stop.
2. **Resolve type**: from explicit arg or inferred from natural language phrasing.
3. **Gather content**:
   - `entity`: search the codebase for `<identifier>` (grep/glob for class, function, or file). Fill template fields from what is found. Confirm with user before writing.
   - `decision`: use provided text. If no date is given, use today's date. Ask for `Rationale` if not supplied.
   - `error`, `context`, `preference`: use provided text. Fill template fields. Ask for missing required fields if content is too sparse.
   - `todo`: use provided text. If no date is given, use today's date. Ask for `Next action` if not supplied. Set `Status: open` by default.
4. **Route by target**: `context` is written to `.remember/local/context.md` and
   never to `.remember/MEMORY.md`. Every other type is written to
   `.remember/MEMORY.md`.
5. **Duplicate check**: for `context`, replace whatever
   `.remember/local/context.md` already holds — that file carries at most one
   entry. For every other type, search `.remember/MEMORY.md` for an existing
   entry with the same name or subject; if found, offer to update in place
   rather than append.
6. Write the entry using the template from `references/types.md`. In
   `.remember/MEMORY.md`, append or update under the correct `## <type>`
   section. For `context`, write `.remember/local/context.md` whole, first
   creating `.remember/local/` and its ignore rule if setup has not.
7. Confirm to user: type recorded, subject, target file, and whether it was added or updated.

---

## Workflow D: Inferred type

Triggered by "Remember that `<text>`" with no explicit type keyword.

1. Read `<text>` and classify as one of: `entity`, `decision`, `error`, `context`, `preference`, `todo`.
2. Tell the user: "I'll record this as a `<type>`. Does that look right?"
3. On confirmation: continue as Workflow C from step 3.
4. On rejection: ask the user to specify the type, then continue as Workflow C from step 3.

---

## Workflow E: Session Synthesis (`$remember session`)

Triggered by `$remember session` or natural language journal phrases.

Resolve `<remember-skill-dir>` to the directory containing this `SKILL.md`
before running a bundled helper.

**Goal:** Append one concise, deduplicated daily journal entry from valid,
unsummarized lifecycle records.

**Inputs:** every valid `version: 3` lifecycle segment in `.remember/turns/`
from any `platform`, and the available current context when no segments exist.

**Boundaries:** Preserve chronological order and ground the summary in selected
records or an available SessionEnd transcript. Keep curated and procedural
memory unchanged.

**Result:** Report the daily journal path, source segment count, and whether the write
was new or deduplicated.

1. **Guard**: check `.remember/MEMORY.md` and `.remember/memory/` exist. If
   either is missing, tell the user to run `$remember setup` first and stop.
2. List unsummarized segments with
   `python "<remember-skill-dir>/scripts/turn_journal.py" unsummarized --root .`,
   which returns every valid v3 record from both platforms ascending by
   `captured_at`. This makes work from a prior context survive `/clear`. Legacy
   or malformed files in the store are skipped, never repaired. If no segments
   exist, fall back to the available current context.
3. For each `session-end` segment, read its `transcript_path` only when the file is
   still available. Treat the transcript format as unstable input and extract
   only terminal context not already present in selected Stop segments. Use Stop
   as the response-text source when the transcript overlaps it. If the
   transcript is unavailable, retain the SessionEnd metadata without inventing
   missing content.
4. Synthesize a concise journal entry from the selected records, ordered
   chronologically. Include available work, context, decisions, blockers, next
   steps, and references.
5. Write **one** daily journal entry covering every selected segment, using the
   combined segment keys across all platforms as a single `session_hash`. Never
   write one entry per platform. Before writing, scan every dated daily journal
   for that hash and reuse a matching entry.
6. Only after the daily journal write succeeds, mark each source segment with
   `summarized_at` and `summary_path`:
   `python "<remember-skill-dir>/scripts/turn_journal.py" mark-summarized --root . --summary-path .remember/memory/YYYY-MM-DD.md`.
   Keep source records unchanged when synthesis or its journal write fails; no
   segment is modified until the journal write succeeds.
7. Confirm the summary path and the source segment count per platform. Leave
   segment cleanup to `$remember clean`.

## Workflow F: Lifecycle Capture and Cleanup

**Goal:** Manage independent, opt-in `Stop` and `SessionEnd` capture and
preview-first cleanup.

**Context:** The packaged hooks remain inert until their project-local channel
is enabled. Stop records a completed main-agent response as a `kind: stop`
record. SessionEnd records the terminal event and transcript path as a
`kind: session-end` record with empty `text`, leaving response text to Stop.
Both land in the shared `.remember/turns/` store with `platform: codex`.

**Boundaries:** Keep hook execution quiet and fail-open. Preserve the other
channel on every state change. Capture complete main-agent payloads only, write
immutable project-local segments, and leave recommendations and memory steering
outside hook execution.

**Result:** Report the targeted channel state and segment counts for hook
commands. For cleanup, report the exact preview or applied deletion set.

Codex requires the user to trust plugin hooks. Ask the user to verify the
current definitions with `/hooks` before enabling either channel.

### `$remember hook enable <channel>`

1. Require initialized memory; direct the user to `$remember setup` when absent.
2. Require exactly one channel: `stop-capture` or `session-end-capture`.
3. Explain that channel's scope and ask the user to confirm hook trust if it has
   not already been confirmed.
4. Run `python "<remember-skill-dir>/scripts/turn_journal.py" enable <channel> --root .`.
5. Report the enabled channel and its immutable project-local segment behavior.

### `$remember hook disable <channel>` and `$remember hook status <channel>`

Require one supported channel, then run the corresponding helper command with
the channel and `--root .`, using the resolved helper path above. Status reports
that channel's enabled state plus store-wide totals: summarized and
unsummarized counts and their per-platform breakdown, and the unsummarized
records themselves. Report hook trust only when the user's `/hooks` evidence
confirms it.

### `$remember clean [--apply]`

Run `python "<remember-skill-dir>/scripts/turn_journal.py" clean --root .` first
and show the exact older, valid summarized segments eligible for removal. Apply
deletion only by rerunning it with `--apply` after explicit approval.
Retain the newest completed summary checkpoint with all its records, plus every
unsummarized or malformed segment. Retention applies uniformly to every valid
v3 segment regardless of `platform`.

---

## Workflow G: Recommend Curated

Invoked by the `recommend` skill (`/recommend curated`).

1. **Guard**: check `.remember/MEMORY.md` and `.remember/memory/` exist. If
   either is missing, tell the user to run `$remember setup` first.
2. Review current session context.
3. Identify durable curated candidates:
   - `decision`: explicit technical or workflow choices and their rationale.
   - `error`: failure modes, fixes, gotchas, or validation issues discovered.
   - `context`: current project state, active work, blockers, or next steps. Written to `.remember/local/context.md`, never to `.remember/MEMORY.md`.
   - `preference`: repeated or explicit user working preferences.
   - `entity`: important codebase objects discussed in enough detail to locate and describe.
4. Exclude ephemeral information: one-off commands, transient status, vague observations, unconfirmed guesses, or facts already covered.
5. Compare candidates against `.remember/MEMORY.md`, and any `context` candidate against `.remember/local/context.md`. Mark each as `add`, `update`, or `skip`. Prefer updating the existing local `context` entry over adding a second one.
6. Present recommendations only; do not write automatically.
7. For each recommendation include: action, type, subject, reason it is durable, proposed entry text using the template from `references/types.md`.
8. Ask which to apply. On approval, continue through Workflow C from duplicate check.
9. Before writing approved entries, run validation:
   `python plugins/v8ch/skills/remember/scripts/validate_memory.py --root . --toolchain codex`.
   If validation fails, report the issues and do not write unless the user
   explicitly confirms proceeding despite the malformed memory state.

---

## Workflow H: Recommend Session

Invoked by the `recommend` skill (`/recommend session`).

1. **Guard**: check `.remember/MEMORY.md` and `.remember/memory/` exist. If
   either is missing, tell the user to run `$remember setup` first.
2. Run journal write logic (Workflow E steps 2–6) as a prerequisite. If already captured (dedupe), skip silently and continue.
3. Review the captured journal entry and full session context.
4. Identify curated candidates (entity, decision, error, context, preference) and procedural candidates (workflow lessons, coding/arch standards, skill/tool routines).
5. Resolve each procedural candidate to an approved target from `references/procedural-targets.md`. If no target fits, mark as unsupported.
6. Dedupe curated candidates against `.remember/MEMORY.md`; dedupe procedural candidates against their respective target files.
7. Present recommendations grouped by target and action: `add`, `update`, `skip`. List unsupported procedural candidates separately with a note.
8. Apply only approved changes. For curated approvals, continue through Workflow C. For procedural approvals, continue through Workflow I.
9. Before applying approved curated or procedural changes, run validation:
   `python plugins/v8ch/skills/remember/scripts/validate_memory.py --root . --toolchain codex`.
   If validation fails, report the issues and do not write unless the user
   explicitly confirms proceeding despite the malformed memory state.

---

## Workflow I: Recommend Procedural

Invoked by the `recommend` skill (`/recommend procedural`).

1. **Guard**: check `.remember/MEMORY.md` and `.remember/memory/` exist. If
   either is missing, tell the user to run `$remember setup` first.
2. Review current session context and today's journal file if present.
3. Identify procedural candidates only: workflow lessons, coding/arch standards, skill/tool routines.
4. Resolve each to an approved target from `references/procedural-targets.md`. If no target fits, mark as unsupported; do not write elsewhere.
5. Read existing guidance in each resolved target file.
6. Classify candidates as `add`, `update`, or `skip` against the file's current content.
7. Propose a concise patch per target. Present for user review.
8. Apply only approved changes (Workflow I).
9. Before applying approved procedural changes, run validation:
   `python plugins/v8ch/skills/remember/scripts/validate_memory.py --root . --toolchain codex`.
   If validation fails, report the issues and do not write unless the user
   explicitly confirms proceeding despite the malformed memory state.

---

## Workflow J: Procedural Write (`$remember procedure/workflow/standard <text>`)

Triggered by `$remember procedure <text>`, `$remember workflow <text>`, or `$remember standard <text>`.

1. **Guard**: check `.remember/MEMORY.md` and `.remember/memory/` exist. If
   either is missing, tell the user to run `$remember setup` first and stop.
2. Parse `<text>` and resolve to an approved target file using `references/procedural-targets.md`.
   - If text maps clearly to one target: proceed.
   - If ambiguous: present candidates and ask the user to choose.
   - If no target fits: surface as unsupported; ask for explicit user direction. Do not write elsewhere.
3. Read existing guidance in the resolved target file. Check for duplication.
4. Propose the addition or update as a patch and present it to the user.
5. On approval: write the change. Prefer updating existing guidance over appending duplicate rules.
6. If the target file does not exist: offer to create it with a stub before writing. Create only on approval.

---

## Workflow K: Review (`$remember review`)

Triggered by `$remember review`, "review memory", "audit memories", or "clean up remember".

1. **Guard**: check `.remember/MEMORY.md` and `.remember/memory/` exist. If
   either is missing, tell the user to run `$remember setup` first.
2. Read `.remember/MEMORY.md` and collect all entries across every type section, then read `.remember/local/context.md` when present.
3. For each entry, classify as one of:
   - `retain`: still accurate and useful.
   - `remove`: stale, duplicated, obsolete, superseded, or no longer actionable.
   - `act`: requires follow-up.
4. Apply type-specific review criteria:
   - `entity`: retain if the code object still exists and remains important; remove if deleted, renamed without update, duplicated, or too trivial; act if documentation or dependencies need updating.
   - `decision`: retain if the rationale is still valid; remove if superseded or contradicted by a newer decision; act if implementation or documentation appears incomplete.
   - `error`: retain if the failure mode may recur; remove if obsolete (resolved and unlikely to recur); act if status is `watch` and there is an unresolved mitigation.
   - `context`: read from `.remember/local/context.md`. Retain only if it still matches the working tree; remove or update if stale. The file holds at most one entry; collapse any extras. A `<!-- context -->` entry still sitting in `.remember/MEMORY.md` is a migration item, not a review item — move it.
   - `preference`: retain unless contradicted by a newer preference; remove duplicates or overly narrow one-off preferences.
   - `todo`: retain if still valid; remove if `done`, `obsolete`, or duplicated; act if `open` or `blocked` and specific enough to become a work item.
5. For `todo` entries classified as `act`, propose new work items (title, description, suggested tracking mechanism). Do not create automatically.
6. Respond with a concise summary: total entries reviewed, counts per classification, memories to remove, memories to act upon, proposed work items.
7. Ask which removals and actions to apply. On approval: remove entries, create work items if requested, update `todo` entries with the `Work item` field.

---

## Workflow L: Validate (`$remember validate`)

Triggered by `$remember validate`, `$remember validate --json`, "validate
remember", or "validate memory".

1. Run `scripts/validate_memory.py` from the repository root:
   - Human-readable: `python plugins/v8ch/skills/remember/scripts/validate_memory.py --root . --toolchain codex --check-steering`
   - JSON: `python plugins/v8ch/skills/remember/scripts/validate_memory.py --root . --toolchain codex --check-steering --json`
2. Validation checks `.remember/MEMORY.md` for required type sections, known
   entry markers, and required fields. A `<!-- context -->` entry there is an
   error (`context_entry_in_memory_file`); a leftover `## context` heading is a
   warning (`legacy_context_section`).
3. Validation checks `.remember/local/context.md` for a single well-formed
   `context` entry, and reports `local_context_not_ignored` when
   `.remember/local/` exists in a Git repository without being ignored.
4. Validation checks `.remember/memory/YYYY-MM-DD.md` journal filenames and
   `remember-journal` metadata blocks, plus `version: 3` lifecycle segment
   records in `.remember/turns/`.
5. With `--check-steering`, validation also inspects an existing
   `## Memory Fast-Track Workflow` section and reports
   `fast_track_steering_drift` when the allowlist has lost a required path or
   the conflict step still references a single active `context` entry. It never
   rewrites an existing section.
6. Validation reports issues without mutating files by default. Only append
   generated Memory Fast-Track steering after explicit user approval with
   `--apply-fast-track`.
7. JSON output includes overall `status`, `counts`, and `issues` containing
   `severity`, `code`, `path`, `message`, and optional `suggested_fix`.
8. Respond with the helper output and a concise next action for any failures.

---

## Edge cases

- **Unknown type in args**: "Remember the widget `<text>`" — treat as Workflow D, infer type from content.
- **Empty subject on record command**: `$remember entity` with no identifier — ask the user to provide the subject.
- **`AGENTS.md` absent**: do not create it during setup.
- **No durable curated recommendations**: say no memory-worthy updates were found; do not modify files.
- **Procedural candidate with no approved target**: surface as unsupported; present to the user as a manual decision rather than writing elsewhere.
- **Stop payload lacks a session ID, turn ID, or final message**: skip capture
  quietly. Do not infer missing values or write a partial record.
- **SessionEnd payload lacks a session ID, transcript path, or reason**: skip
  capture quietly. Do not register a substitute event or write a partial record.
- **Legacy Stop state**: preserve `.remember/stop-capture.json` as the Stop
  channel preference. Treat a missing `.remember/session-end-capture.json` as
  disabled.

---

$ARGUMENTS
