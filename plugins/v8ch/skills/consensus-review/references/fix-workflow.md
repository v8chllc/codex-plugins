# Fix Workflow

## Goal

Repair the findings from the current review cycle, prove each repair, and land
them on the PR/MR head branch as one commit whose body is the fix evidence.

No fix-validation comment is posted. The commit body is the record.

## Prerequisite

This workflow is PR/MR-only. A local review never fixes. The current review is
the synthesized report from the cycle that just posted; the PR/MR thread is the
durable history, recovered with:

```bash
uv run <skill-dir>/scripts/recover_context.py <number> --repo-dir <repo-root>
```

## Success criteria

### 1. Run the fixer

Run `consensus-review-fixer` with the synthesized report and its `[F-N]`
numbering, the raw score and cycle, the PR/MR number and URL, the repository
directory, the absolute skill directory, the optional plan, acceptance criteria
and Regression Guards (`none` when absent), and a scratch directory for the fix
log. Pass only numbered findings for disposition; the report's one `Noted` list
needs no individual disposition and is not fixed unless the sponsor asks.

The raw score is the only threshold input. There are no fix modes and no
score-gap targeting: every current finding gets a disposition.

### 2. Read the fix log

The fixer returns a path and one terminal word. It emits no signal: this
workflow returns an outcome and the skill emits the run's single terminal signal.

- `COMPLETE` — every finding carries a disposition, every applied code or
  configuration repair has a confirmed mutation check, every applied text-only
  repair has a recorded author verification, and the quality commands passed.
  A cycle with only author-verified text-only repairs commits and continues.
- `MUTATION_UNPROVEN` — an applied code or configuration repair (`fixed`, or
  `partial` where code or configuration changed) has an unconfirmed mutation
  check. Commit nothing and map this fixer result to workflow outcome
  `BLOCKERS_REMAIN`, naming those findings: the commit body carries fix
  evidence, so an unproven repair would record a claim nothing tested.
- `QUALITY_FAILURES` — commit nothing and map this fixer result to workflow
  outcome `QUALITY_FAILURES` with the failing commands.

  Leave the fixer's edits in the working tree. They are most of a repair, and
  discarding them loses work with no record. State in the final report that the
  tree holds uncommitted changes and name them: a PR/MR re-run reviews the
  platform diff, so those edits are **not** in the next cycle's scope. Commit or
  discard them before re-running.
- No files changed — nothing is committed or pushed, so `PUSH_COMPLETE`, which
  reports pushed commits, never applies. Set workflow outcome `NO_CHANGE` with
  an empty SHA list.

### 3. Verify the dispositions

Every current finding is `fixed`, `declined`, `partial`, or
`work-item-required`. The finding under repair must have closed. If the log
shows a finding with no disposition, treat the pass as incomplete and emit
`BLOCKERS_REMAIN` after committing whatever did land.

### 4. Commit

Guard: run only when `git status --porcelain` is non-empty.

Stage the fixer's changes and create one conventional commit directly with
`git`. Do not invoke another skill for this.

The commit body records, in order:

- the raw score and the cycle;
- every disposition;
- the quality commands and their results;
- one mutation check per code or configuration repair;
- the author verifications for text-only repairs, in a separate section;
- the work-item records.

### 5. Push

Verify the current branch equals the PR/MR head ref:

- `github`: `gh pr view <number> --json headRefName -q .headRefName`
- `gitlab`: `glab mr view <number> -F json | jq -r .source_branch`

On a mismatch, `ABORT` with `reason` `branch_mismatch` and do not push. A failed
query is `ABORT` with `reason` `command_failed`, also without pushing: an
unanswered query is not a matching branch.

Push to an explicit remote and ref rather than the branch's upstream, which may
point at a fork or a stale remote:

```bash
git push origin HEAD:<head-ref>
```

A non-zero commit or push is `ABORT` with `reason` `command_failed`. The commit
exists locally after a failed push, so name its SHA in `message`. On success,
record the pushed commit SHAs.

### 6. Hand back to the review budget

Keep two result fields with distinct, exhaustive vocabularies. Evaluate the
rows from top to bottom; the first matching row wins:

| Fixer result | Workflow condition | Workflow outcome |
| --- | --- | --- |
| `MUTATION_UNPROVEN` | any | `BLOCKERS_REMAIN` |
| `QUALITY_FAILURES` | any | `QUALITY_FAILURES` |
| `COMPLETE` | a finding has no disposition | `BLOCKERS_REMAIN` |
| `COMPLETE` | a finding is `partial` or `work-item-required` | `BLOCKERS_REMAIN` |
| `COMPLETE` | no unresolved dispositions; changes committed and pushed | `COMPLETE` |
| `COMPLETE` | no unresolved dispositions; no files changed | `NO_CHANGE` |

Return `fixer_result` using only `COMPLETE`, `MUTATION_UNPROVEN`, or
`QUALITY_FAILURES`. Return `workflow_outcome` using only `COMPLETE`,
`NO_CHANGE`, `BLOCKERS_REMAIN`, or `QUALITY_FAILURES`, according to the table.
Also return the commit SHAs (or an empty list), work-item records, disposition
counts, failed commands, unproven finding IDs, and uncommitted paths.

For top-level `review_budget: single_cycle`, hand back after this one fix pass.
The orchestrator emits `CAPPED_REVIEW_COMPLETE` with the review URL, score,
status, exact `fixer_result`, exact `workflow_outcome`, fix commit SHAs, work
items, `failed_commands`, `unproven_findings`, and `uncommitted_paths`; it never
starts a second review. Empty evidence lists are returned for a clean fix path.
For the default budget, the orchestrator routes on the first match, so two
identical runs cannot end on different signals:

1. A finding with no disposition, or fixer result `MUTATION_UNPROVEN` — workflow
   outcome `BLOCKERS_REMAIN`, whatever the budget allows.
2. Workflow outcome `QUALITY_FAILURES` — `QUALITY_FAILURES`.
3. Budget remaining — start the next review cycle.
4. Budget exhausted with `partial` or `work-item-required` findings —
   `BLOCKERS_REMAIN`, matching their precedence in the mapping above.
5. Budget exhausted with pushed commits — `PUSH_COMPLETE`.
6. Budget exhausted with nothing committed — `MAX_REVIEWS_REACHED`.

## Constraints and authority

Edit only tracked files inside the findings under repair and the tests that
prove them. Run the repository's documented quality commands and `git` directly.
Do not change a criterion, Regression Guard, or plan decision, and do not add
scope. A required plan-level change goes to the sponsor as an issue edit and
`sponsor-decision` marker, never into a fixer commit.
Never merge, deploy, force-push, rewrite history, create a tracking item, or
post a comment from this workflow.

## Output and stop rule

This workflow writes no comment. It returns to the orchestrator with:

- the `fixer_result` and mapped `workflow_outcome`;
- the commit SHAs, or `[]` when nothing was committed;
- the work-item records, or `[]`;
- the supporting failure evidence and disposition counts.

The orchestrator emits the run's single terminal signal.
