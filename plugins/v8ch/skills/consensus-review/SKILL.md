---
name: consensus-review
description: Runs an autonomous, evidence-gated consensus code review. Use when reviewing code changes, before pushing a PR, or as the review step in a development workflow. Runs three general-purpose reviewers (standards, correctness, architecture) from the skill's own prompt assets, synthesizes them into a tiered report with a 1-100 quality score, posts one review comment per cycle to a PR/MR, and fixes and re-reviews within a three-review budget. Accepts an optional plan as review context. Scope defaults to all local changes (staged, unstaged, and untracked); also accepts a PR/MR number, a base commit SHA, a branch diff, or an explicit file list.
---

# Consensus Review

## Goal

Produce one evidence-backed review of a change, ranked by consequence, and —
when a PR/MR is in scope — repair what it found and review again until the
change is clean or the budget runs out.

The run is autonomous from start to finish. It never prompts the operator. It
ends with exactly one terminal signal.

## Success criteria

1. Three reviewers run independently, each from this skill's own prompt asset,
   and none sees another's output.
2. Every reviewer output carries a non-empty `## Evidence` section before it is
   scored.
3. The synthesizer alone decides the score and the status.
4. A PR/MR run posts exactly one `review` comment per cycle. Fix evidence lives
   in the fix commit, never in a second comment.
5. At most three reviews run per invocation.
6. The last thing written is one fenced `consensus-review-signal` block.

## Inputs

**Scope ladder** — check in order, use the first match:

1. **PR/MR number.** Fetch the diff with `gh pr diff <number>` or
   `glab mr diff <number>`. Verify local `HEAD` equals the PR/MR head SHA first;
   on a mismatch emit `ABORT` with `reason` `head_mismatch` and stop.
2. **Base commit SHA.** `git diff <sha>`, plus `git ls-files --others
   --exclude-standard`. Read each untracked file in full and label it as new.
3. **Branch diff.** The `git diff` range for that branch.
4. **Explicit file list.** `git diff -- <paths>`.
5. **Default.** `git diff HEAD`, plus `git ls-files --others --exclude-standard`,
   reading each untracked file in full. No changes here emits `NO_DIFF`.

**Plan** — a caller-supplied plan file or text, used as review context only and
never as a severity source. Record the plan source as the literal `none`, or as
`supplied: <path or short description>`. The same value goes in the report
provenance and in the `plan_source` metadata field. Plan context is never
recovered from PR/MR comments.

**Platform** — `DEV_SEC_OPS_PLATFORM` from `.env` at the repository root, or
`--platform github|gitlab`.

**Script paths** — this skill's scripts are referenced as `scripts/<name>.py`,
resolved against the directory holding this file into an absolute path before
running. Pass that absolute skill directory to every role.

## Roles and delegation

Six roles, each a prompt asset in `agents/` beside this file:

| Role | Asset |
| --- | --- |
| `standards-reviewer` | `agents/standards-reviewer.md` |
| `correctness-reviewer` | `agents/correctness-reviewer.md` |
| `architecture-reviewer` | `agents/architecture-reviewer.md` |
| `review-synthesizer` | `agents/review-synthesizer.md` |
| `consensus-review-poster` | `agents/consensus-review-poster.md` |
| `consensus-review-fixer` | `agents/consensus-review-fixer.md` |

The three reviewers are genuinely independent and run concurrently. Wait for all
three before synthesizing. Nothing else in the run is delegated in parallel.

**Delegation mode.** If `spawn_agent` is in your tool list, the mode is
`parallel-subagents`. If it is absent, the mode is `sequential-fallback`. Decide
by tool presence alone; never read configuration to decide.

**Spawning (`parallel-subagents`).** Call `spawn_agent` with `message` set to the
asset's full contents followed by that role's inputs, `fork_context: false`, and
both `model: "gpt-5.6-sol"` and `reasoning_effort: "medium"`. Passing the model
without the effort resets the child to the model's default effort. Omit
`agent_type`.

**Sequential fallback.** Run each role as an isolated pass in the main thread,
one at a time, each receiving exactly the inputs its parallel counterpart would:

- a reviewer pass gets the diff, the changed-file context, the plan, the
  recovered history, and the skill directory — never another reviewer's output;
- the synthesizer pass gets all three reviewer outputs, the delegation mode, and
  the plan source;
- the poster and fixer passes get the synthesized report plus their own inputs.

Keep every completed role output verbatim until the run ends, and discard each
pass's intermediate reasoning before starting the next. This mode expects the
session's own model and effort as its baseline: `gpt-5.6-sol` at `medium`.

## Workflow

### 1. Recover context

With a PR/MR number:

```bash
uv run <skill-dir>/scripts/recover_context.py <number> --repo-dir <repo-root>
```

Keep the output as `RECOVERED_CONTEXT`. It gives the next cycle number — use it,
do not recompute — the scope basis and the reason for it, and the prior review
bodies.

### 2. Resolve the cycle scope

Cycle 01 reviews the full diff. A later cycle reviews `git diff
<reviewed_sha>..HEAD` and confirms the prior cycle's findings closed. The
narrowing is by time, not by file: every commit since that SHA is in scope
whatever it touched, so a regression a fix introduced anywhere is still reviewed.

With no narrowing basis — no prior review, a legacy `schema_version: 1` review,
or a recorded SHA that is no longer an ancestor of HEAD — review the full diff
and state that basis in the comment.

### 3. Read the repository

Read the repository's guidance and the changed-file context needed to judge
callers, invariants, and failure paths.

### 4. Snapshot the working tree

Before spawning any read-only role, record:

```bash
git rev-parse HEAD
git status --porcelain=v1 --untracked-files=all --ignored
```

### 5. Run the three reviewers

One batch, concurrently. Each gets the diff, the changed-file context, the plan,
`RECOVERED_CONTEXT`, and the absolute skill directory.

### 6. Apply the evidence gate

A reviewer output without a non-empty `## Evidence` section carrying both
`Files examined` and `Commands run` is a failed pass. Rerun that pass once. On a
second failure, emit `EVIDENCE_FAILED` with the failed pass names and stop
without a score.

### 7. Re-check the working tree

Take the snapshot again and compare it to step 4. On any difference, emit
`ABORT` with `reason` `read_only_role_mutated` and post nothing.

The check detects new commits and changes to tracked, untracked, and ignored
paths inside the repository. It does not detect changes outside the repository
or content-only edits to already-ignored files.

### 8. Synthesize

Run `review-synthesizer` with all three reviewer outputs labeled in full, the
delegation mode, the plan source, and `RECOVERED_CONTEXT`. Repeat step 7
afterwards.

### 9. Post or return

**No PR/MR:** return the report unchanged and emit `REVIEW_COMPLETE` with
`review_url` `null`. A local review never fixes.

**PR/MR:** run `consensus-review-poster` once with the report, the PR/MR number,
the cycle, the status, the delegation mode, the plan source, the reviewed SHA,
the scope basis, the `files_touched`, `findings_opened`, and `findings_closed`
counts, the repository directory, and the absolute skill directory. A posting
failure is `ABORT` with `reason` `post_failed`.

### 10. Branch on status

- `clean` — stop and emit `REVIEW_COMPLETE`.
- `passing` or `failing` — run `references/fix-workflow.md`, then review again if
  the budget allows.

**Budget:** at most three reviews per invocation, whatever the PR/MR's cycle
count or which toolchain wrote earlier cycles. Every new invocation gets a fresh
budget. Cycle numbers accumulate with no cap. When the third review is still not
`clean`, emit `MAX_REVIEWS_REACHED`.

## Constraints and authority

**Safe without asking:** reading any file; running `git` read commands, the
repository's documented quality and test commands, and `gh`/`glab` read
commands; writing scratch files outside the repository; running the reviewers,
the synthesizer, and the poster; applying in-scope fixes through the fixer;
posting the one review comment; and committing and pushing those fixes to the
PR/MR head branch.

**Never:** merge, deploy, force-push, rewrite history, run a destructive
operation, expand scope beyond the findings under repair, create a tracking
item, prompt the operator, or post any comment other than the one `review`
comment per cycle.

This skill invokes no other skill and no agent outside `agents/`. Its external
requirements are `git`, `uv`, and `gh` or `glab`.

Published text cites only repository-relative tracked paths or links.

## Output and stop rule

Every run ends with exactly one fenced block as its last output:

```consensus-review-signal
{"signal": "<SIGNAL>", "cycle": 1, "details": {}}
```

`cycle` is the PR/MR cycle number, or `0` for a local review. `details` carries
exactly the keys listed for its signal, all required. A value that does not exist
at that point is `null`; an empty list is `[]`.

| Signal | When | `details` keys |
| --- | --- | --- |
| `REVIEW_COMPLETE` | A local review returned, or a PR/MR review reached `clean` | `score`, `status`, `review_url` |
| `NO_DIFF` | Nothing to review | `scope` |
| `EVIDENCE_FAILED` | A reviewer failed the evidence gate twice | `failed_passes` |
| `QUALITY_FAILURES` | Quality commands still fail after the fix pass; nothing committed | `score`, `review_url`, `failed_commands` |
| `BLOCKERS_REMAIN` | Fixes pushed, but findings remain `partial` or `work-item-required` and the budget allows no further review | `score`, `review_url`, `commit_shas`, `work_items` |
| `PUSH_COMPLETE` | Fixes committed and pushed, budget exhausted before a `clean` review | `score`, `review_url`, `commit_shas`, `work_items` |
| `MAX_REVIEWS_REACHED` | The third review is still not `clean` | `score`, `status`, `review_url`, `work_items` |
| `ABORT` | An unrecoverable error | `reason`, `message`, `score`, `review_url` |

`ABORT` `reason` is one of `head_mismatch`, `branch_mismatch`, `platform_auth`,
`post_failed`, `read_only_role_mutated`.

**Retry limit:** a failed evidence pass is rerun once. Nothing else is retried.

**Length:** what must survive trimming is the score and status, the Must Fix
findings, the evidence, any material caveat, and the terminal signal. Lead with
the conclusion and omit repetition and secondary detail.
