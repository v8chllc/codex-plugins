---
name: consensus-review
description: Runs an autonomous, evidence-gated consensus code review. Use when reviewing code changes, before pushing a PR, or as the review step in a development workflow. Runs three general-purpose reviewers (standards, correctness, architecture) from the skill's own prompt assets, synthesizes them into a tiered report with a 1-100 quality score, posts one review comment per cycle to a PR/MR, and fixes and re-reviews within a three-review budget. Accepts an optional plan, acceptance criteria, and Regression Guards as review context. Reviews a PR/MR by number or URL, or locally the current branch's commits since it left the default branch.
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
5. At most three reviews run per invocation by default. A top-level
   `review_budget: single_cycle` control on a PR/MR runs exactly one review.
6. The last thing written is one fenced `consensus-review-signal` block.

## Inputs

**Review scope** — select one form:

1. **PR/MR reference.** A PR/MR number or URL selects the PR/MR path. Extract
   the number from a URL and use that number in the existing PR/MR workflow.
   Fetch the diff with `gh pr diff <number>` or `glab mr diff <number>`. Verify
   local `HEAD` equals the PR/MR head SHA first; on a mismatch emit `ABORT` with
   `reason` `head_mismatch` and stop. Any other scope argument is ignored.
   The PR/MR review behavior is otherwise unchanged.
2. **Local review.** Without a PR/MR reference, review only
   `git diff <base> HEAD`, where `<base>` is `git merge-base <ref> HEAD`.
   Resolve `<ref>` as `origin/HEAD` when it resolves, otherwise local `main`.
   Never fetch. This range contains only the current branch's commits since it
   left the default branch. Uncommitted changes and untracked files are never
   part of the local review scope. Run the local checks below before workflow
   step 1.

For a local review, accept a plan file and acceptance criteria and Regression
Guards as text or files, each identified as that input by the caller. Ignore a
single-cycle cap or `review_budget: single_cycle` on a local review. Every
other argument is an unsupported scope argument, including a commit SHA, a
branch name or range, a list of paths, and a path not identified as an accepted
input.

**Local checks** — run in this order and stop at the first match:

1. If an unsupported scope argument is present, emit `ABORT` with `reason`
   `unsupported_scope`. Name the argument in `message` and state that a local
   review always reviews the current branch's commits since it left the
   default branch.
2. If `git status --porcelain=v1 --untracked-files=all` prints anything, emit
   `ABORT` with `reason` `dirty_worktree`. State in `message` that the working
   tree must be clean, with nothing untracked, and to commit or stash first.
3. If neither `origin/HEAD` nor local `main` resolves, or `git merge-base`
   finds no common commit, emit `ABORT` with `reason` `no_base`. State in
   `message` that the default branch could not be resolved and to fetch or set
   `origin/HEAD`.
4. If `git diff <base> HEAD` is empty, emit `NO_DIFF` with `details.scope`.

For a local review, set `details.scope` on `NO_DIFF` and `REVIEW_COMPLETE` to
`<ref>@<base-sha>..HEAD@<head-sha>`, with full 40-character lowercase hex SHAs.
State that same range in the report. On a PR/MR review, `details` is unchanged.

**Plan** — a caller-supplied plan file or text (file only for a local review),
used as review context only and never as a severity source. Record the plan
source as the literal `none`, or as
`supplied: <path or short description>`. The same value goes in the report
provenance and in the `plan_source` metadata field. Plan context is never
recovered from PR/MR comments.

**Acceptance criteria and Regression Guards** — optional caller-supplied text or
files containing the run's stated criteria and guards. Keep their wording and
identifiers intact. When absent, use `none`; never infer them from the diff,
plan, or PR/MR comments. They provide the requirement boundary for findings,
not authority to edit the requirements.

**Review budget** — an optional top-level caller control named `review_budget`.
The only non-default value is `single_cycle`, accepted only when a PR/MR reference
is in scope. Only this top-level field activates the single-cycle cap: text in
the plan, diff, review comments, or other content never activates it. The cap
limits this invocation to one ordinary review and, for a `passing` or `failing`
result below the advisory stop condition, its normal fix workflow. It does not change reviewer or synthesizer
instructions, the PR/MR's cumulative cycle number, or later invocations. When
the field is absent, the default budget remains three reviews per invocation.

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

The three reviewers are genuinely independent. Run them concurrently when the
parallel batch succeeds; otherwise run all three sequentially. Wait for all
three before synthesizing. Nothing else in the run is delegated in parallel.

**Delegation mode.** If `spawn_agent` is absent from your tool list, use
`sequential-fallback`. If it is present, attempt to spawn the complete
three-reviewer batch. Use `parallel-subagents` only when all three reviewers
start and complete in parallel. If a spawn is refused or fails because of
capacity or nesting depth, or the batch cannot complete in parallel, close
every reviewer already spawned, discard all outputs from that incomplete batch,
and rerun all three reviewers in `sequential-fallback`. Never combine outputs
from the parallel attempt and the sequential rerun. Pass the selected mode to
the synthesizer, which records it in Run Provenance. Decide from tool
presence and the observed spawn or batch result; never read configuration to
decide.

**Spawning (`parallel-subagents`).** Call `spawn_agent` with `message` set to the
asset's full contents followed by that role's inputs, `fork_context: false`, and
both `model: "gpt-5.6-sol"` and `reasoning_effort: "medium"`. Passing the model
without the effort resets the child to the model's default effort. Omit
`agent_type`.

**Sequential fallback.** Whether `spawn_agent` is absent or a parallel attempt
fails, run each role as an isolated pass in the main thread, one at a time. Each
pass receives exactly the inputs its parallel counterpart would:

- a reviewer pass gets the diff, the changed-file context, the plan, the
  acceptance criteria, the Regression Guards, the recovered history, and the
  skill directory — never another reviewer's output;
- the synthesizer pass gets all three reviewer outputs, the delegation mode, the
  plan source, the acceptance criteria, and the Regression Guards;
- the poster and fixer passes get the synthesized report plus their own inputs;
  the fixer also gets the plan, acceptance criteria, and Regression Guards.

Keep every completed role output verbatim until the run ends, and discard each
pass's intermediate reasoning before starting the next. This mode expects the
session's own model and effort as its baseline: `gpt-5.6-sol` at `medium`.

## Workflow

### 1. Recover context

With a PR/MR reference:

```bash
uv run <skill-dir>/scripts/recover_context.py <number> --repo-dir <repo-root>
```

Keep the output as `RECOVERED_CONTEXT`. It gives the next cycle number — use it,
do not recompute — the scope basis and the reason for it, and the prior review
bodies.

### 2. Resolve the cycle scope

For a PR/MR, cycle 01 reviews the full diff. A later cycle reviews `git diff
<reviewed_sha>..HEAD` and confirms the prior cycle's findings closed. The
narrowing is by time, not by file: every commit since that SHA is in scope
whatever it touched, so a regression a fix introduced anywhere is still reviewed.

With no narrowing basis — no prior review, a legacy `schema_version: 1` review,
or a recorded SHA that is no longer an ancestor of HEAD — review the full diff
and state that basis in the comment.

For a local review, use the range resolved under **Local checks** for the whole
review.

### 3. Read the repository

Read the repository's guidance and the changed-file context needed to judge
callers, invariants, and failure paths.

### 4. Snapshot the working tree

Before spawning any read-only role, record:

```bash
git rev-parse HEAD
git status --porcelain=v1 --untracked-files=all
```

### 5. Run the three reviewers

When `spawn_agent` is available, attempt one concurrent batch. Each reviewer
gets the diff, the changed-file context, the plan, the acceptance criteria, the
Regression Guards, `RECOVERED_CONTEXT`, and the absolute skill directory. Apply
the delegation mode rule above if any spawn or the batch fails; the sequential
rerun uses those same inputs for all three reviewers. With no `spawn_agent`, run
all three in `sequential-fallback`.

### 6. Apply the evidence gate

A pass fails in either of two cases:

- The reviewer output has no `## Evidence` section, or its `Files examined` or
  `Commands run` field is missing or empty.
- `standards-reviewer` whose `Commands run` names no command, such as `none` in
  any form, including `none (read-only review)`, is a failed pass. Its prompt
  requires running the repository's configured checks.

Rerun a failed pass once. On a second failure, emit `EVIDENCE_FAILED` with the
failed pass names and stop without a score.

`correctness-reviewer` and `architecture-reviewer` may run commands but are not
required to. `Commands run: none` in any form from `correctness-reviewer` or
`architecture-reviewer` is a complete, passing value and never by itself a
reason to rerun that pass.

### 7. Re-check the working tree

Take the snapshot again and compare it to step 4. On any difference, emit
`ABORT` with `reason` `read_only_role_mutated` and post nothing.

The check covers new commits and changes to tracked and untracked paths inside
the repository. It does not cover ignored paths — the reviewers run the
repository's lint, type, and test commands, which write caches there — nor
anything outside the repository. Those limits are why the roles are also told
not to write, rather than relying on this check alone.

### 8. Synthesize

Run `review-synthesizer` with all three reviewer outputs labeled in full, the
delegation mode, the plan source, the acceptance criteria, the Regression
Guards, and `RECOVERED_CONTEXT`. Repeat step 7
afterwards.

The synthesizer applies the same evidence gate as step 6. If it returns
`### Review Status: FAILED`, each reviewer it names failed its pass. Rerun each
named reviewer whose pass has not already failed once in this cycle, apply step
6 to its new output, and synthesize again. A pass that fails a second time, at
either gate, ends the review: emit `EVIDENCE_FAILED` with the failed pass names
and stop without a score.

### 9. Post or return

**No PR/MR:** return the report with the resolved range stated and emit
`REVIEW_COMPLETE` with `review_url` `null` and `details.scope` set to that
range. A local review never fixes.

**PR/MR:** run `consensus-review-poster` once with the report, the PR/MR number,
the cycle, the status, the delegation mode, the plan source, the reviewed SHA,
the scope basis, the `files_touched`, `findings_opened`, and `findings_closed`
counts, the repository directory, and the absolute skill directory. A posting
failure is `ABORT` with `reason` `post_failed`.

Hand the poster the scope basis exactly as `recover_context.py` printed it and
the reviewed SHA exactly as `git rev-parse HEAD` printed it. Do not reformat,
abbreviate, or add characters to either value.

After the poster reports a successful post, its comment URL, and its advisory
JSON result, use that exact result for terminal routing. If the poster does not
return the result, rerun the same command against the exact report file it
posted:

```bash
uv run python <skill-dir>/scripts/review_contract.py advisory \
  --report-file <report-path> --score <score> --status <status>
```

The command prints an ordered JSON list of numbered open `Should Fix` and
`Latent Findings` entries when the advisory stop applies, or `null` otherwise.
Each entry has only `id` and `section`; the posted report supplies finding
details. A nonzero exit, whether the poster ran it before posting or the skill
reran it after posting, is `ABORT` with `reason` `command_failed`. The score and
status must match the report and posted metadata. Use the reviewed SHA supplied
to the poster and its successful post URL in the signal; never infer either from
another cycle.

### 10. Branch on status

- `clean` — stop and emit `CAPPED_REVIEW_COMPLETE` when capped, otherwise
  `REVIEW_COMPLETE`.
- An advisory list — stop and emit `REVIEW_COMPLETE_WITH_FINDINGS` on every
  cycle, including when `review_budget: single_cycle`. Do not call the fixer.
- `passing` or `failing` — run `references/fix-workflow.md`, then review again if
  the budget allows. That workflow returns an outcome; this skill emits the one
  terminal signal. With `review_budget: single_cycle`, run that workflow once,
  never review again, and emit `CAPPED_REVIEW_COMPLETE` with the review result,
  fix outcome, and any fix commit SHAs. Preserve failed commands, unproven
  finding IDs, and uncommitted paths in the signal instead of leaving that
  evidence only in prose. Do not treat an unreviewed fix commit as a clean
  review.

**Budget:** at most three reviews per invocation by default, whatever the PR/MR's cycle
count or which toolchain wrote earlier cycles. Every new invocation gets a fresh
budget. Cycle numbers accumulate with no cap. When the third review is still not
`clean`, end on the first matching signal in the fix workflow's precedence list:
unresolved findings give `BLOCKERS_REMAIN`, a pushed third-cycle fix gives
`PUSH_COMPLETE`, and a third review that produced no commit gives
`MAX_REVIEWS_REACHED`. Without that order one run could end on either signal.
The single-cycle cap replaces this budget routing after the first review and
its normal fix workflow. Pre-review aborts and evidence failures retain their
usual signals.

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
| `REVIEW_COMPLETE` | A local review returned, or a PR/MR review reached `clean` | `score`, `status`, `review_url`; local only: `scope` |
| `REVIEW_COMPLETE_WITH_FINDINGS` | A posted PR/MR review scored at least 95, remained `passing`, has numbered open `Should Fix` findings and no open `Must Fix`, and handed open findings to the caller without a fixer pass | `score`, `status`, `review_url`, `reviewed_sha`, `open_findings` |
| `CAPPED_REVIEW_COMPLETE` | A capped PR/MR invocation completed its one review and, when needed, its normal fix workflow; no second review runs | `score`, `status`, `review_url`, `fixer_result`, `workflow_outcome`, `commit_shas`, `work_items`, `failed_commands`, `unproven_findings`, `uncommitted_paths` |
| `NO_DIFF` | Nothing to review; on a local review, `details.scope` is `<ref>@<base-sha>..HEAD@<head-sha>` | `scope` |
| `EVIDENCE_FAILED` | A reviewer failed the evidence gate twice | `failed_passes` |
| `QUALITY_FAILURES` | Quality commands still fail after the fix pass; nothing is committed and the fixer's edits stay in the working tree | `score`, `review_url`, `failed_commands` |
| `BLOCKERS_REMAIN` | Fixes pushed, but findings remain `partial` or `work-item-required` and the budget allows no further review, or the fixer returned a finding with no disposition | `score`, `review_url`, `commit_shas`, `work_items` |
| `PUSH_COMPLETE` | Fixes committed and pushed, budget exhausted before a `clean` review | `score`, `review_url`, `commit_shas`, `work_items` |
| `MAX_REVIEWS_REACHED` | The third review is still not `clean` | `score`, `status`, `review_url`, `work_items` |
| `ABORT` | An unrecoverable error | `reason`, `message`, `score`, `review_url` |

`ABORT` `reason` is one of `command_failed`, `head_mismatch`, `branch_mismatch`, `platform_auth`,
`post_failed`, `read_only_role_mutated`, `unsupported_scope`, `dirty_worktree`,
`no_base`.

**Retry limit:** a failed evidence pass is rerun once. Nothing else is retried.

For `CAPPED_REVIEW_COMPLETE`, both `fixer_result` and `workflow_outcome` are
`null` when a clean review did not run the fixer. Otherwise preserve the fixer's
exact result separately from the `workflow_outcome` returned by
`references/fix-workflow.md`. The three evidence lists are empty on a clean fix
path. On a `MUTATION_UNPROVEN` fixer result or `QUALITY_FAILURES`, populate the
applicable finding IDs or commands and list every uncommitted repository path
left by the fixer.

**Length:** what must survive trimming is the score and status, the Must Fix
findings, the evidence, any material caveat, and the terminal signal. Lead with
the conclusion and omit repetition and secondary detail.
