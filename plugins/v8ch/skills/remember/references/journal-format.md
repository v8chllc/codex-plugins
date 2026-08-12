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
JSON records into one shared, flat store:

```
.remember/turns/<platform>-<kind>-<key>.json
```

The store is non-recursive and holds no subdirectories. Both toolchains write
into it and read all of it, so a single synthesis run covers everything captured
in the workspace regardless of which toolchain recorded it.

### Record format

Every record is a UTF-8 JSON object with exactly these twelve keys. Nullable
keys are always present with an explicit `null`; a record carrying an unknown
key or a missing key is invalid.

```json
{
  "version": 3,
  "platform": "codex",
  "kind": "stop",
  "key": "<opaque deterministic key>",
  "project_root": "/absolute/path/to/workspace",
  "session_id": "<session ID>",
  "captured_at": "2026-08-12T14:50:28.391649Z",
  "text": "<assistant response text>",
  "reason": null,
  "transcript_path": null,
  "summarized_at": null,
  "summary_path": null
}
```

- `version`: always `3`. There is no v1 or v2 reader; legacy files are skipped
  as malformed and are never stamped or deleted.
- `platform`: `claude` or `codex`. Codex writes `codex` and reads both.
- `kind`: `stop` or `session-end`.
- `key`: idempotency key, unique per `(platform, kind)`. Stop hashes
  `session_id + Stop + turn_id`; SessionEnd hashes
  `session_id + SessionEnd + reason`.
- `project_root`: absolute workspace root. A record for another root is out of
  scope.
- `text`: the assistant response text. A `session-end` record legitimately
  carries `""`; it is never `null`.
- `reason`: non-null only for `session-end`.
- `transcript_path`: absolute path when present. It is carried through and
  never followed by the helper scripts.
- `summarized_at` / `summary_path`: the summary checkpoint.

### Timestamp encoding

`captured_at` and `summarized_at` use exactly `YYYY-MM-DDTHH:MM:SS.ffffffZ` -
six-digit microseconds, literal `Z`, no offset form. The width is fixed, so
lexicographic order equals chronological order and enumeration is ascending by
`captured_at`.

### Summary checkpoint

`summarized_at` and `summary_path` are written and cleared together. Both
non-null or both `null`; any other combination is invalid and the record is
rejected rather than repaired. `summary_path` is relative to the workspace root
and must resolve inside `.remember/memory/`.

`/clear` may replace model context while leaving earlier segment files intact,
so `$remember session` selects unsummarized segments rather than trusting only
the current session ID. During synthesis, read a `transcript_path` only if it
still exists; Codex documents the transcript format as unstable, so do not
depend on a fixed JSONL schema. `$remember clean` previews removal of older
valid summarized checkpoints and requires `--apply`; it never removes
unsummarized or malformed files.
