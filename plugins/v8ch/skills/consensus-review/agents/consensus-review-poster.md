# consensus-review-poster

## Goal

Publish the synthesized report as one `review` comment on the PR/MR, and report
the comment URL.

## Inputs

You receive the synthesized report; the PR/MR number; the cycle number; the
status, delegation mode, plan source, reviewed SHA, and scope basis; the
`files_touched`, `findings_opened`, and `findings_closed` counts; the repository
directory; and the absolute path of the consensus-review skill directory.

## Success criteria

1. **Stop without posting if the report has no `### Quality Score:` heading.**
   Report that and stop; do not compose a substitute.
2. **Inspect the exact report before writing the summary:** write the report
   verbatim to its scratch file, then run:

   ```bash
   uv run python <skill-dir>/scripts/review_contract.py advisory \
     --report-file <report-path> --score <score> --status <status>
   ```

   Stop without posting and pass through the command error when it exits
   nonzero. Preserve its exact JSON result for the caller.
3. **Write the summary yourself:** one to three bullets drawn from the report's
   Summary section, naming the highest-severity finding and the status. Add the
   sentence that the caller will disposition the advisory findings only when
   the command in step 2 returned a JSON list. Put that sentence inside one of
   the one to three summary bullets, never on a separate line. Do not
   independently infer the advisory condition from report prose, promise an
   automatic fix cycle, or claim no fixes are needed. Nothing else in the
   comment is yours to write.
4. **Do not alter the findings, the score, or the status.** They are decided by
   the synthesizer and travel through you unchanged.
5. **Take `--plan-source` and `--delegation-mode` from the report's
   `### Run Provenance` line.** Copy those values exactly into the posting
   command, rather than using the plan source or delegation mode supplied in
   your prompt. Write the summary scratch file outside the repository, then post
   with:

   ```bash
   uv run <skill-dir>/scripts/post_review_comment.py \
     --pr-number <number> \
     --review-file <report-path> \
     --summary-file <summary-path> \
     --repo-dir <repo-dir> \
     --cycle <cycle> \
     --status <status> \
     --delegation-mode <mode> \
     --plan-source "<plan-source>" \
     --reviewed-sha <sha> \
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

On success, report the comment URL and the exact advisory JSON result from step
2, then stop.

On failure, report the exact error from the script and stop. Do not retry with
different inputs.
