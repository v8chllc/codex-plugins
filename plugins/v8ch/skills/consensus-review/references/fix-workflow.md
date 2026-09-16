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
directory, the absolute skill directory, and a scratch directory for the fix log.

The raw score is the only threshold input. There are no fix modes and no
score-gap targeting: every current finding gets a disposition.

### 2. Read the fix log

The fixer returns a path and one terminal word. It emits no signal: this
workflow returns an outcome and the skill emits the run's single terminal signal.

- `COMPLETE` — every finding carries a disposition, every applied repair carries
  a confirmed mutation check, and the quality commands passed. Continue.
- `MUTATION_UNPROVEN` — an applied repair (`fixed`, or `partial` where code
  changed) has an unconfirmed mutation check. Commit nothing and return
  `BLOCKERS_REMAIN` naming those findings: the commit body carries fix evidence,
  so an unproven repair would record a claim nothing tested.
- `QUALITY_FAILURES` — commit nothing and return `QUALITY_FAILURES` with the
  failing commands.

  Leave the fixer's edits in the working tree. They are most of a repair, and
  discarding them loses work with no record. State in the final report that the
  tree holds uncommitted changes and name them: a PR/MR re-run reviews the
  platform diff, so those edits are **not** in the next cycle's scope. Commit or
  discard them before re-running.
- No files changed — nothing is committed or pushed, so `PUSH_COMPLETE`, which
  reports pushed commits, never applies. Return `NO_CHANGE` with an empty SHA
  list.

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
- one mutation check per fix;
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

Return the outcome, the commit SHAs (or an empty list), the work-item records,
and the disposition counts. The orchestrator routes on the first match, so two
identical runs cannot end on different signals:

1. A finding with no disposition, or outcome `MUTATION_UNPROVEN` —
   `BLOCKERS_REMAIN`, whatever the budget allows.
2. Outcome `QUALITY_FAILURES` — `QUALITY_FAILURES`.
3. Budget remaining — start the next review cycle.
4. Budget exhausted with `partial` or `work-item-required` findings —
   `BLOCKERS_REMAIN`.
5. Budget exhausted with pushed commits — `PUSH_COMPLETE`.
6. Budget exhausted with nothing committed — `MAX_REVIEWS_REACHED`.

## Constraints and authority

Edit only tracked files inside the findings under repair and the tests that
prove them. Run the repository's documented quality commands and `git` directly.
Never merge, deploy, force-push, rewrite history, create a tracking item, or
post a comment from this workflow.

## Output and stop rule

This workflow writes no comment. It returns to the orchestrator with:

- the commit SHAs, or `[]` when nothing was committed;
- the work-item records, or `[]`;
- the terminal condition: `COMPLETE`, `BLOCKERS_REMAIN`, or `QUALITY_FAILURES`.

The orchestrator emits the run's single terminal signal.
