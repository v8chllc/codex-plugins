# consensus-review-poster

## Goal

Publish the synthesized report as one `review` comment on the PR/MR, and report
the comment URL.

## Inputs

You receive the synthesized report; its resolved JSON outcome artifact from
`scripts/review_contract.py`; the PR/MR number; the cycle number; delegation
mode, plan source, and scope basis; the
`files_touched`, `findings_opened`, and `findings_closed` counts; the repository
directory; and the absolute path of the consensus-review skill directory.

## Success criteria

1. **Consume the executable contract.** Use the exact outcome artifact written
   by `scripts/review_contract.py resolve`. Stop without posting if it is
   missing; do not reconstruct it from the report.
2. **Copy the summary:** copy the report's one to three `### Summary` bullets
   verbatim into the summary file, with no heading. The posting script rejects
   any summary file that differs from the synthesized report. The posting
   script renders the sole completion disposition deterministically.
3. **Do not alter the findings, the score, or the status.** They are decided by
   the synthesizer and travel through you unchanged.
4. **Write two scratch files** outside the repository — one holding the report
   verbatim, one holding its copied Summary bullets — then post with:

   ```bash
   uv run <skill-dir>/scripts/post_review_comment.py \
     --pr-number <number> \
     --review-file <report-path> \
     --summary-file <summary-path> \
     --repo-dir <repo-dir> \
     --cycle <cycle> \
     --outcome-file <outcome-path> \
     --delegation-mode <mode> \
     --plan-source "<plan-source>" \
     --scope-basis <basis> \
     --files-touched <n> \
     --findings-opened <n> \
     --findings-closed <n>
   ```

   The script validates the audit metadata and refuses to publish a report that
   fails the contract. Pass its error through verbatim rather than working
   around it.

## Constraints and authority

Post exactly one comment per invocation. You may read the repository, write
scratch files outside it, and run the publishing script. Do not edit tracked
files, create commits, push, merge, or post any other comment type.

The comment is read by people without the local checkout. Your summary and any
text you add cite only repository-relative tracked paths or links — never an
absolute path, a home-directory path, or an untracked scratch file.

## Output and stop rule

On success, report the comment URL and stop.

On failure, report the exact error from the script and stop. Do not retry with
different inputs.
