# Journal Format

Daily journal entries live in `.remember/memory/YYYY-MM-DD.md`. Each file is
date-scoped and append-oriented. Entries are untyped prose.

---

## File path

```
.remember/memory/YYYY-MM-DD.md
```

Use the local date when the session summary is written, not UTC, unless the user specifies otherwise.

---

## Entry structure

Each session journal entry consists of two parts:

1. A metadata comment marker (for dedupe)
2. A prose section with the session narrative

### Metadata marker

```md
<!-- remember-journal
source: lifecycle-synthesis
kind: session
session_hash: <hash of source segment keys>
captured_at: <ISO-8601>
window_start: <ISO-8601>
window_end: <ISO-8601>
-->
```

Place the marker immediately before the session prose. The marker is an HTML
comment and will not render in most Markdown viewers.

Fields:
- `source`: `lifecycle-synthesis` when lifecycle segments are selected; `manual`
  when `$remember session` falls back to current context
- `kind`: always `session` for session captures
- `session_hash`: best-effort hash of the session window (see Dedupe below)
- `captured_at`: ISO-8601 timestamp when the entry was written
- `window_start`, `window_end`: approximate session boundaries (ISO-8601)

### Prose section

A heading followed by narrative content covering:

```md
## <HH:MM> Session

### What happened
<summary of work done, decisions made, tools used>

### Key context
<important background or state that informed the work>

### Decisions considered
<options weighed, trade-offs discussed, approaches rejected>

### Blockers
<anything that slowed progress or remains unresolved>

### Next steps
<specific follow-ups for the next session>

### References
<links, file paths, issue numbers, or other useful pointers>
```

Omit sections that have nothing to say. Keep prose concise.

---

## Dedupe

Goal: avoid duplicate entries when the same session is captured more than once
with `$remember session`.

### Session hash

Compute a deterministic `session_hash` from the sorted, selected lifecycle
segment keys.
This is stable across a retry after `/clear`, and avoids relying on the current
context window.

The hash does not need to be cryptographically strong — it only needs to be
stable across two captures of the same session window.

### Dedupe check

Before appending:
1. Read every dated daily journal file.
2. Scan for `<!-- remember-journal` blocks.
3. Extract the `session_hash` from each block.
4. If the computed hash matches an existing block: skip the write. Notify the
   user that this session was already captured.
5. After successful write, set `summarized_at` and `summary_path` on every
   source lifecycle segment. Never set those fields before the journal exists.

### Constraints

- Dedupe is deterministic for an identical set of source lifecycle segments.
- Do not use semantic similarity for dedupe.
- Do not introduce an external state store or database.
- Keep metadata in HTML comments so the journal remains readable as plain Markdown.

---

## Lifecycle segments

When explicitly enabled, the Codex `Stop` and `SessionEnd` hooks write immutable
Markdown files under:

```
.remember/turns/codex/<segment-key>.md
```

Each file starts with this marker:

```md
<!-- remember-turn
version: 2
platform: codex
channel: <stop-capture | session-end-capture>
event: <Stop | SessionEnd>
session_id: <Codex session ID>
segment_key: <opaque deterministic key>
captured_at: <ISO-8601>
summarized_at: <ISO-8601, absent until summary succeeds>
summary_path: <daily journal path, absent until summary succeeds>
-->
```

New segments use `version: 2`. Version 1 Stop segments remain valid for
migration and use `turn_id` plus `turn_key` instead of the version 2 event,
channel, and segment-key fields.

### Stop fields

Stop segments additionally contain:

```md
turn_id: <Codex turn ID>
```

The segment key hashes `session_id + Stop + turn_id`. Its prose body contains
the final assistant message for that completed main-agent turn.

### SessionEnd fields

SessionEnd segments additionally contain:

```md
transcript_path: <Codex transcript path>
reason: other
```

The segment key hashes `session_id + SessionEnd + reason`. The segment records
the transcript reference rather than copying the final assistant message, so
concurrent Stop and SessionEnd delivery does not duplicate response content.
During synthesis, read the transcript only if it still exists. Codex documents
the transcript format as unstable, so do not depend on a fixed JSONL schema.

`/clear` may replace model context while leaving earlier segment files intact,
so `$remember session` selects unsummarized segments rather than trusting only
the current session ID. `$remember clean` previews removal of older valid
summarized checkpoints and requires `--apply`; it never removes unsummarized or
malformed files.
