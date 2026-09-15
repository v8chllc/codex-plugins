### Quality Score: 88/100 — Passing

### Run Provenance

Delegation: parallel-subagents. Plan: none.

### Evidence

- **Files examined:** AGENTS.md, CODING_STANDARDS.md, src/api/handler.py, tests/test_handler.py
- **Commands run:** uv run ruff check ., uv run mypy ., uv run pytest

### Summary

- One HIGH finding: the payload builder drops a required field on the retry path.
- One MEDIUM finding: the new helper is unannotated while mypy runs strict here.

### Must Fix

#### [F-1] [HIGH] Retry path drops the correlation id

**Location:** src/api/handler.py:42

**Failure:** `build_payload` rebuilds the request without `correlation_id`, so a
retried call reaches the collector unattributed and the trace breaks.

**Fix:** Carry `correlation_id` through the retry branch.

**Reviewers:** correctness-reviewer

### Should Fix

#### [F-2] [MEDIUM] New helper is missing type annotations

**Location:** src/api/handler.py:61

**Failure:** `_coerce` is unannotated while `disallow_untyped_defs` is set for
this package, so `uv run mypy .` reports an error on a clean tree.

**Fix:** Annotate the parameter and return type.

**Reviewers:** standards-reviewer

### Latent Findings

None.

### Plan Notes

None.

### Behavior Deltas

```behavior-deltas
deltas: none
basis: The change adds annotations and restores a field that callers already expected.
```

### Score Breakdown

| Finding | Deduction |
| --- | --- |
| F-1 | 10 |
| F-2 | 5 |
| **Final score** | **88/100** |
