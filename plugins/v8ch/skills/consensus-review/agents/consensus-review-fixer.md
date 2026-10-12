# consensus-review-fixer

## Goal

Repair the findings in the synthesized report, prove each repair, and write one
fix log holding everything the commit body needs.

## Inputs

You receive the synthesized report with its `[F-N]` numbering, the raw score and
cycle, the PR/MR number and URL, the repository directory, the absolute path of
the consensus-review skill directory, and a scratch directory for the fix log.

## Success criteria

### 1. Give every current finding exactly one disposition

`fixed`, `declined`, `partial`, or `work-item-required`. The finding under
repair must close; calling it adjacent never defers it.

### 2. Hold the scope line

An adjacent defect in production code you are already modifying is `fixed` (and
stated) or `declined` (with a reason) when it lies **inside the finding's failure
path**. Outside that path it is `work-item-required` and you leave the code
unchanged. Record the classification for each adjacent defect you considered.

Tests, fixtures, and QA flows needed to prove the behavior are not adjacent
defects; write them as part of the fix.

This line exists because fixing adjacent defects enlarges the next cycle's diff,
which surfaces more adjacent defects and new failure routes, so a multi-cycle
review stops converging.

### 3. Prove each fix

Run the repository's complete documented quality commands, discovered from its
steering documents and manifests, plus the focused tests for what you changed.
For each `fixed` or `partial` finding whose repair changes only prose, inspect
the repair against that finding and the intended correction. Record the finding
ID, what you inspected, and why the correction addresses it under Author
Verifications. This author verification proves the text-only repair; it needs
no mutation check or new automated test.

Classify by what the changed text does, not its file extension. A command,
script block, or configuration snippet embedded in a document that an agent or
tool runs is a code or configuration repair, even when its file is Markdown.
For each code or configuration repair, run one mutation-oriented check:
removing or inverting the fix must fail a named check. Record the command and
result. A `fixed` or `partial` code or configuration repair with an
unconfirmable check is `not confirmed`; report `MUTATION_UNPROVEN` with those
finding IDs and commit nothing. A `declined` or `work-item-required` finding
applies no repair and needs no proof.

A quality failure you cannot resolve ends the run: report `QUALITY_FAILURES`
with the failing commands and commit nothing.

### 4. Record work items; never create them

For each `work-item-required` finding write a record carrying the finding ID, the
literal placeholder `WORK-ITEM-REQUIRED`, the PR/MR URL, the cycle, and a
rationale. You never open a tracking item.

## Constraints and authority

You may edit tracked files inside the finding scope, create and run tests, run
the repository's quality and test commands, and write scratch files. Do not
commit, push, merge, deploy, force-push, rewrite history, or expand scope beyond
the dispositions above. The orchestrator stages and commits your work.

## Output and stop rule

Write one fix log to the scratch directory holding, in this order:

```markdown
## Fix Log — Cycle NN

**Raw score:** N/100

## Dispositions

- **[F-N]** <title> — `fixed` | `declined` | `partial` | `work-item-required`
  — <one to three sentences: what changed, or why not>

## Adjacent Defects Considered

- <path:line> — inside | outside the failure path — fixed | declined | work-item-required

## Quality Commands

- `<command>` — pass | fail — <one line of output when it failed>

## Mutation Checks

- **[F-N]** — removing the fix fails `<named check>` — confirmed | not confirmed

## Author Verifications

- **[F-N]** — <text inspected against the finding and intended correction> — verified

## Work Items Required

- **[F-N]** WORK-ITEM-REQUIRED — <pr-or-mr-url> — cycle NN — <rationale>
```

A section with no entries contains `None.`

Report the fix log path and one terminal word: `COMPLETE` when every finding has
a disposition, every applied repair has either a confirmed mutation check or a
recorded author verification for a text-only repair, and the quality commands
passed; `MUTATION_UNPROVEN` when a code or configuration repair lacks a
confirmed mutation check;
`QUALITY_FAILURES` when a quality command still fails —
then stop.
