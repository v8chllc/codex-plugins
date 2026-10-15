# Lifecycle Segments


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
