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

The fixer returns a path and one terminal word.

- `QUALITY_FAILURES` — emit the `QUALITY_FAILURES` signal with the failing
  commands and commit nothing. The run ends here.
- `COMPLETE` — continue.

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

On a mismatch, emit `ABORT` with `reason` `branch_mismatch` and do not push.
Otherwise `git push`, then record the pushed commit SHAs.

### 6. Hand back to the review budget

Return the commit SHAs, the work-item records, and the disposition counts to the
orchestrator. It decides whether another review fits in the three-review budget.

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
