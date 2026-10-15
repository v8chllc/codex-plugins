# Memory Recording Operations

Both Remember direct writes and Recommend approved writes use these operations.
The caller owns its own guard, user approval, and, for recommendations, the
validation preflight before any curated or procedural write.

## Curated entries

Use `references/types.md` for the entry shape. Before adding, search
`.remember/MEMORY.md` for an entry with the same name or subject. Update that
entry in place when found; otherwise append under the correct `## <type>`
section. For decision and error updates, retain existing `Evidence` only while
it supports the revised claim; replace or omit stale evidence. Never append a
duplicate entry.

## Procedural guidance

Use `references/procedural-targets.md` to resolve an approved target. Treat an
unmatched candidate as unsupported, and ask the user for direction. Read an
existing target before proposing a patch. Skip guidance already covered; update
its existing section when partially covered; add a concise rule when missing.
Show the patch and obtain approval. Create a missing standards target only with
user approval. Write only to the approved target.

## Daily journal

Use `references/journal-format.md` for the marker and prose shape. Compute a
stable `session_hash`, scan every dated journal file for that hash, and append
one entry only if absent. A retry with the same hash reuses the existing entry.
For lifecycle synthesis, checkpoint source records only after the journal write
succeeds; lifecycle record handling remains in Remember.
