"""Hygiene checks for the consensus-review skill's prose assets.

Codex performs no variable substitution in `SKILL.md` or in a prompt asset, so an
`${...}` placeholder reaches the model literally. Script paths must stay relative
to the skill directory for the same reason: a hardcoded marketplace path is wrong
in every installed cache.
"""

import re
from pathlib import Path

import pytest

from tests.consensus_review_support import CONSENSUS_REVIEW_DIR, REPO_ROOT

UNDEFINED_VARIABLE_RE = re.compile(r"\$\{[^}]*\}")
HARDCODED_SCRIPT_PATH_RE = re.compile(r"plugins/v8ch/skills/[^\s`)]*/scripts/")

ROLE_NAMES = (
    "standards-reviewer",
    "correctness-reviewer",
    "architecture-reviewer",
    "review-synthesizer",
    "consensus-review-poster",
    "consensus-review-fixer",
)

PROSE_ASSETS = sorted(
    [
        CONSENSUS_REVIEW_DIR / "SKILL.md",
        *(CONSENSUS_REVIEW_DIR / "references").glob("*.md"),
        *(CONSENSUS_REVIEW_DIR / "agents").glob("*.md"),
    ]
)


def asset_id(path: Path) -> str:
    """Label a prose asset by its path within the consensus-review skill."""
    return str(path.relative_to(CONSENSUS_REVIEW_DIR))


def normalized(text: str) -> str:
    """Collapse Markdown line wrapping while preserving token order."""
    return " ".join(text.split())


def markdown_section(text: str, heading: str) -> str:
    """Return the text from a heading through the next level-two heading."""
    start = text.index(heading) + len(heading)
    remainder = text[start:]
    next_heading = re.search(r"\n## ", remainder)
    return remainder[: next_heading.start()] if next_heading else remainder


@pytest.mark.parametrize("path", PROSE_ASSETS, ids=asset_id)
def test_no_undefined_template_variables(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    found = UNDEFINED_VARIABLE_RE.findall(text)
    assert not found, f"{asset_id(path)} contains undefined variables: {found}"


@pytest.mark.parametrize("path", PROSE_ASSETS, ids=asset_id)
def test_no_hardcoded_marketplace_script_paths(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    found = HARDCODED_SCRIPT_PATH_RE.findall(text)
    assert not found, f"{asset_id(path)} hardcodes a script path: {found}"


def test_every_role_ships_a_prompt_asset() -> None:
    agents = CONSENSUS_REVIEW_DIR / "agents"
    assert {path.stem for path in agents.glob("*.md")} == set(ROLE_NAMES)


@pytest.mark.parametrize("name", ROLE_NAMES)
def test_role_assets_use_the_gpt_document_shape(name: str) -> None:
    text = (CONSENSUS_REVIEW_DIR / "agents" / f"{name}.md").read_text(encoding="utf-8")
    assert "## Goal" in text
    assert "## Constraints and authority" in text
    assert "## Output and stop rule" in text


@pytest.mark.parametrize(
    "name", ("standards-reviewer", "correctness-reviewer", "architecture-reviewer")
)
def test_reviewer_assets_require_evidence_and_forbid_mutation(name: str) -> None:
    text = (CONSENSUS_REVIEW_DIR / "agents" / f"{name}.md").read_text(encoding="utf-8")
    assert "## Evidence" in text
    assert "**Files examined:**" in text
    assert "**Commands run:**" in text
    assert "inspect and report; do not implement changes" in text.lower()


def test_synthesizer_is_read_only_and_owns_status() -> None:
    """Keep synthesis read-only and make it the owner of review status."""
    text = (CONSENSUS_REVIEW_DIR / "agents" / "review-synthesizer.md").read_text(
        encoding="utf-8"
    )
    assert "inspect and report; do not implement changes" in text.lower()
    assert "You are the only place status is decided." in text
    for status in ("clean", "passing", "failing"):
        assert f"`{status}`" in text


@pytest.mark.parametrize(
    "name", ("standards-reviewer", "correctness-reviewer", "architecture-reviewer")
)
def test_reviewers_bound_findings_and_return_other_observations(name: str) -> None:
    text = (CONSENSUS_REVIEW_DIR / "agents" / f"{name}.md").read_text(encoding="utf-8")
    assert "correctness, security, privacy or authorization" in normalized(text)
    assert "a stated acceptance criterion or Regression Guard" in normalized(text)
    assert "or the plan" in normalized(text)
    assert "## Noted" in text
    assert "Noted items have no" in text
    assert "fix request" in text
    assert "criteria and Regression Guards (each `none` when absent)" in normalized(
        text
    )


def test_architecture_prompt_patterns_obey_finding_boundary() -> None:
    text = (CONSENSUS_REVIEW_DIR / "agents" / "architecture-reviewer.md").read_text(
        encoding="utf-8"
    )
    criteria = normalized(markdown_section(text, "## Success criteria"))
    prompt_rule = criteria.split("3. **Judge a prompt asset", 1)[1].split("4.", 1)[0]
    assert "re-verify its own work" in prompt_rule
    assert "repeats one rule in several places" in prompt_rule
    assert "only when its demonstrated consequence meets the finding boundary" in (
        prompt_rule
    )
    assert "otherwise put the observation in `Noted`" in prompt_rule
    assert "apply the finding boundary before reporting it as a finding" in criteria


@pytest.mark.parametrize(
    "name", ("standards-reviewer", "correctness-reviewer", "architecture-reviewer")
)
def test_committed_build_output_observation_obeys_boundary(name: str) -> None:
    text = (CONSENSUS_REVIEW_DIR / "agents" / f"{name}.md").read_text(encoding="utf-8")
    rule = normalized(text).split("Vendored dependencies, build output", 1)[1]
    rule = rule.split("## Constraints and authority", 1)[0]
    assert "committed build output or dependencies" in rule
    assert (
        "Apply the finding boundary to decide whether it is a finding or `Noted`"
        in (rule)
    )


def test_synthesizer_has_one_unscored_noted_list() -> None:
    text = (CONSENSUS_REVIEW_DIR / "agents" / "review-synthesizer.md").read_text(
        encoding="utf-8"
    )
    classification = normalized(
        markdown_section(text, "### 3. Classify each surviving finding")
    )
    output = normalized(markdown_section(text, "## Output and stop rule"))
    assert "Only a gap affecting correctness, security, privacy or authorization" in (
        classification
    )
    assert "a stated acceptance criterion or Regression Guard" in classification
    assert "single `Noted` list, separate from findings" in classification
    assert "Do not send noted items to the fixer" in classification
    assert "`### Noted` — one list" in output
    assert "no severity, finding number, score deduction, or disposition" in output


def test_fixer_preserves_requirements_and_does_not_expand_scope() -> None:
    fixer = (CONSENSUS_REVIEW_DIR / "agents" / "consensus-review-fixer.md").read_text(
        encoding="utf-8"
    )
    workflow = (CONSENSUS_REVIEW_DIR / "references" / "fix-workflow.md").read_text(
        encoding="utf-8"
    )
    for text in (fixer, workflow):
        text = normalized(text)
        assert "do not add scope" in text.lower()
        assert "Regression Guard" in text
        assert "plan decision" in text
        assert "`sponsor-decision` marker" in text
        assert "Noted" in text
        assert "no individual disposition" in text or "do not disposition" in text


def test_skill_accepts_and_passes_optional_run_requirements() -> None:
    skill = (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")
    inputs = normalized(markdown_section(skill, "## Inputs"))
    delegation = normalized(markdown_section(skill, "## Roles and delegation"))
    workflow = normalized(markdown_section(skill, "## Workflow"))
    assert "Acceptance criteria and Regression Guards" in inputs
    assert "optional caller-supplied text or files" in inputs
    assert "When absent, use `none`" in inputs
    assert "acceptance criteria, the Regression Guards" in delegation
    assert "acceptance criteria, the Regression Guards" in workflow
    assert (
        "the fixer also gets the plan, acceptance criteria, and Regression Guards"
        in delegation
    )


def test_poster_places_advisory_disposition_inside_summary_bullet() -> None:
    """Reject the old instruction that left the disposition on its own line."""
    poster = (CONSENSUS_REVIEW_DIR / "agents" / "consensus-review-poster.md").read_text(
        encoding="utf-8"
    )
    step_three = normalized(
        poster.split("3. **Write the summary yourself:**", 1)[1].split(
            "4. **Do not alter", 1
        )[0]
    )

    def assert_bullet_placement(instruction: str) -> None:
        assert "sentence that the caller will disposition the advisory findings" in (
            instruction
        )
        assert (
            "only when the command in step 2 returned a JSON list. "
            "Put that sentence inside one of the one to three summary bullets, "
            "never on a separate line."
        ) in instruction

    old_instruction = (
        "one to three bullets drawn from the report's Summary section. "
        "Add the sentence that the caller will disposition the advisory findings "
        "only when the command in step 2 returned a JSON list."
    )
    with pytest.raises(AssertionError):
        assert_bullet_placement(old_instruction)
    assert_bullet_placement(step_three)


def test_synthesizer_routes_sponsor_decision_conflicts() -> None:
    """Pin decision parsing, conflict routing, and report references."""
    text = (CONSENSUS_REVIEW_DIR / "agents" / "review-synthesizer.md").read_text(
        encoding="utf-8"
    )
    classification_source = markdown_section(
        text, "### 3. Classify each surviving finding"
    )
    classification = normalized(classification_source)
    output = normalized(markdown_section(text, "## Output and stop rule"))

    assert "after deduplication" in classification
    assert "`### Sponsor decisions`" in classification
    assert "missing `### Sponsor decisions` heading means `None.`" in classification
    assert "exactly one such level-3 heading" in classification
    assert "`- **D-<n>:** <decision text>`" in classification
    assert "`  - Rejected: <alternative>`" in classification_source
    assert "`  - Source: <https://github.com/...>`" in classification_source
    assert "A decision entry with zero `Rejected:` lines is valid" in classification
    assert (
        "each alternative on a `Rejected:` line that is present must be non-empty"
        in classification
    )
    assert "`None.`" in classification
    assert "Unparseable sponsor decisions section" in classification
    assert "exactly one Plan Note" in classification
    assert "proposed fix and failure statement" in classification
    assert "implement a `Rejected:` alternative" in classification
    assert "reverse the decision text" in classification
    assert "CRITICAL or HIGH finding with a demonstrated failure" in classification
    assert "keep it in Must Fix" in classification
    assert "independent defect normally" in classification
    assert "classified exactly as before" in classification
    assert "`**Plan reference:**`" in classification
    assert "no `[F-N]` number, and no deduction" in classification
    assert "no severity tag" in classification
    assert "`**Plan reference:** D-<n>`" in output
    assert "not assign it an `[F-N]` number" in output
    assert (
        "MEDIUM or LOW sponsor-decision contradiction remains a Plan Note even when"
        in classification
    )
    assert "the contradictory part causes a defect" in classification
    assert (
        "Only a demonstrated CRITICAL or HIGH contradiction stays ranked"
        in classification
    )
    assert "Rank independent defects in partly contradictory findings" in classification


def test_skill_is_standalone_and_always_autonomous() -> None:
    """Prevent the skill from depending on removed workflow controls."""
    text = (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "This skill invokes no other skill" in text
    assert "It never prompts the operator." in text
    for removed in ("AUTONOMOUS=", "MAX_AUTONOMOUS_CYCLES", "on_quality_failure"):
        assert removed not in text
    for removed_skill in ("code-quality", "git-ops", "meta-consensus-review-agents"):
        assert removed_skill not in text


def test_skill_spawns_with_both_model_and_effort() -> None:
    text = (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert '`model: "gpt-5.6-sol"`' in text
    assert '`reasoning_effort: "medium"`' in text
    assert "gpt-5.5" not in text
    assert "`fork_context: false`" in text


def test_delegation_attempts_parallel_and_handles_absent_spawn() -> None:
    skill = (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")
    delegation = normalized(markdown_section(skill, "**Delegation mode.**"))
    workflow = normalized(markdown_section(skill, "### 5. Run the three reviewers"))
    assert (
        "If `spawn_agent` is absent from your tool list, use `sequential-fallback`"
        in delegation
    )
    assert "If it is present, attempt to spawn the complete three-reviewer batch" in (
        delegation
    )
    assert (
        "Use `parallel-subagents` only when all three reviewers start and complete"
        in delegation
    )
    assert "attempt one concurrent batch" in workflow


def test_failed_parallel_batch_reruns_all_reviewers_without_mixing() -> None:
    skill = (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")
    delegation = normalized(markdown_section(skill, "**Delegation mode.**"))
    fallback = normalized(markdown_section(skill, "**Sequential fallback.**"))
    workflow = normalized(markdown_section(skill, "### 5. Run the three reviewers"))
    assert (
        "spawn is refused or fails because of capacity or nesting depth" in delegation
    )
    assert "batch cannot complete in parallel" in delegation
    assert "close every reviewer already spawned" in delegation
    assert "discard all outputs from that incomplete batch" in delegation
    assert "rerun all three reviewers in `sequential-fallback`" in delegation
    assert (
        "Never combine outputs from the parallel attempt and the sequential rerun"
        in delegation
    )
    assert (
        "Pass the selected mode to the synthesizer, which records it in Run Provenance"
        in delegation
    )
    assert "failure reason" not in delegation
    assert "Each pass receives exactly the inputs its parallel counterpart would" in (
        fallback
    )
    assert "never another reviewer's output" in fallback
    assert (
        "Apply the delegation mode rule above if any spawn or the batch fails"
        in workflow
    )
    assert "sequential rerun uses those same inputs for all three reviewers" in workflow


def test_delegation_does_not_consult_configuration() -> None:
    skill = (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")
    delegation = normalized(markdown_section(skill, "**Delegation mode.**"))
    assert "Decide from tool presence and the observed spawn or batch result" in (
        delegation
    )
    assert "never read configuration to decide" in delegation


def test_installation_documents_parallel_capacity_and_fallback() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    installation = markdown_section(readme, "## Installation")
    assert "three open subagents per session by default" in installation
    assert "retained builder" in installation
    assert "review agent, and three reviewers" in installation
    assert "`~/.codex/config.toml`" in installation
    assert "[agents]\nmax_concurrent_threads_per_session = 6" in installation
    assert "all\nthree reviewers in `sequential-fallback`" in installation


def test_skill_documents_every_terminal_signal() -> None:
    text = (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")
    for signal in (
        "REVIEW_COMPLETE",
        "REVIEW_COMPLETE_WITH_FINDINGS",
        "CAPPED_REVIEW_COMPLETE",
        "NO_DIFF",
        "EVIDENCE_FAILED",
        "QUALITY_FAILURES",
        "BLOCKERS_REMAIN",
        "PUSH_COMPLETE",
        "MAX_REVIEWS_REACHED",
        "ABORT",
    ):
        assert signal in text
    for reason in (
        "head_mismatch",
        "branch_mismatch",
        "platform_auth",
        "post_failed",
        "command_failed",
        "read_only_role_mutated",
    ):
        assert reason in text
    assert "MAX_CYCLES_REACHED" not in text


def test_skill_routes_posting_and_advisory_results_in_order() -> None:
    skill = (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")
    post_or_return = markdown_section(skill, "### 9. Post or return")
    branch = markdown_section(skill, "### 10. Branch on status")

    assert post_or_return.index("consensus-review-poster") < post_or_return.index(
        "use that exact result for terminal routing"
    )
    post_or_return_normalized = normalized(post_or_return)
    assert (
        "A posting failure is `ABORT` with `reason` `post_failed`"
        in post_or_return_normalized
    )
    assert "A local review never fixes" in post_or_return
    assert "is `ABORT` with `reason` `command_failed`" in post_or_return
    branch_normalized = normalized(branch)
    assert "on every cycle" in branch_normalized
    assert "including when `review_budget: single_cycle`" in branch_normalized
    assert "Do not call the fixer" in branch_normalized


def test_advisory_terminal_signal_carries_required_fields() -> None:
    skill = (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")
    signal_row = skill.split("| `REVIEW_COMPLETE_WITH_FINDINGS` |", maxsplit=1)[
        1
    ].split("\n", maxsplit=1)[0]
    for key in (
        "`score`",
        "`status`",
        "`review_url`",
        "`reviewed_sha`",
        "`open_findings`",
    ):
        assert key in signal_row


def test_poster_uses_the_deterministic_advisory_result() -> None:
    poster = (CONSENSUS_REVIEW_DIR / "agents/consensus-review-poster.md").read_text(
        encoding="utf-8"
    )
    advisory_command = "review_contract.py advisory"
    assert advisory_command in poster
    assert poster.index(advisory_command) < poster.index("Write the summary yourself")
    poster_normalized = normalized(poster)
    assert "only when the command in step 2 returned a JSON list" in poster_normalized
    assert "Do not independently infer the advisory condition" in poster_normalized
    assert "the exact advisory JSON result from step" in poster_normalized


def test_text_only_repairs_have_distinct_author_proof() -> None:
    fixer = (CONSENSUS_REVIEW_DIR / "agents/consensus-review-fixer.md").read_text(
        encoding="utf-8"
    )
    workflow = (CONSENSUS_REVIEW_DIR / "references/fix-workflow.md").read_text(
        encoding="utf-8"
    )
    proof_contract = normalized(markdown_section(fixer, "### 3. Prove each fix"))
    assert "## Author Verifications" in fixer
    assert "finding ID" in proof_contract
    assert "intended correction" in proof_contract
    assert "no mutation check or new automated test" in proof_contract
    assert "command, script block, or configuration snippet" in proof_contract
    assert "For each code or configuration repair" in proof_contract
    assert "unconfirmable check" in proof_contract
    assert "only author-verified text-only repairs commits" in workflow
    assert "the author verifications for text-only repairs, in a separate section" in (
        workflow
    )


def test_single_cycle_budget_is_a_top_level_control() -> None:
    skill = (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")
    budget = normalized(markdown_section(skill, "**Review budget**"))
    assert "top-level caller control named `review_budget`" in budget
    assert "`single_cycle`" in budget
    assert "accepted only when a PR/MR reference is in scope" in budget
    assert "plan, diff, review comments, or other content never activates it" in budget
    assert "the default budget remains three reviews per invocation" in skill


def test_capped_review_runs_fix_once_and_serializes_results() -> None:
    skill = (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")
    workflow = (CONSENSUS_REVIEW_DIR / "references/fix-workflow.md").read_text(
        encoding="utf-8"
    )
    skill_normalized = normalized(skill)
    workflow_normalized = normalized(workflow)
    assert "run that workflow once, never review again" in skill_normalized
    assert "Do not treat an unreviewed fix commit as a clean review" in skill_normalized
    assert "it never starts a second review" in workflow_normalized
    signal_row = skill.split("| `CAPPED_REVIEW_COMPLETE` |", maxsplit=1)[1].split(
        "\n", maxsplit=1
    )[0]
    for key in (
        "`score`",
        "`status`",
        "`review_url`",
        "`fixer_result`",
        "`workflow_outcome`",
        "`commit_shas`",
        "`work_items`",
        "`failed_commands`",
        "`unproven_findings`",
        "`uncommitted_paths`",
    ):
        assert key in signal_row
    signal_contract = normalized(
        markdown_section(skill, "For `CAPPED_REVIEW_COMPLETE`")
    )
    assert "both `fixer_result` and `workflow_outcome` are `null`" in signal_contract
    assert "preserve the fixer's exact result separately" in signal_contract
    assert "Empty evidence lists are returned for a clean fix path" in workflow


def test_fix_workflow_maps_every_fixer_result_to_a_workflow_outcome() -> None:
    workflow = (CONSENSUS_REVIEW_DIR / "references/fix-workflow.md").read_text(
        encoding="utf-8"
    )
    handback = normalized(markdown_section(workflow, "### 6. Hand back"))
    for mapping in (
        "`COMPLETE` | a finding is `partial` or `work-item-required` | "
        "`BLOCKERS_REMAIN`",
        "`COMPLETE` | no unresolved dispositions; changes committed and pushed | "
        "`COMPLETE`",
        "`COMPLETE` | no unresolved dispositions; no files changed | `NO_CHANGE`",
        "`MUTATION_UNPROVEN` | any | `BLOCKERS_REMAIN`",
        "`QUALITY_FAILURES` | any | `QUALITY_FAILURES`",
        "`COMPLETE` | a finding has no disposition | `BLOCKERS_REMAIN`",
    ):
        assert mapping in handback
    assert "the first matching row wins" in handback
    assert (
        "Return `fixer_result` using only `COMPLETE`, `MUTATION_UNPROVEN`, or "
        "`QUALITY_FAILURES`"
    ) in handback
    assert (
        "Return `workflow_outcome` using only `COMPLETE`, `NO_CHANGE`, "
        "`BLOCKERS_REMAIN`, or `QUALITY_FAILURES`"
    ) in handback

    skill = (CONSENSUS_REVIEW_DIR / "SKILL.md").read_text(encoding="utf-8")
    signal_contract = normalized(
        markdown_section(skill, "For `CAPPED_REVIEW_COMPLETE`")
    )
    assert (
        "`workflow_outcome` returned by `references/fix-workflow.md`" in signal_contract
    )
    assert "missing dispositions precedence" not in signal_contract


def test_fix_workflow_posts_no_comment_and_invokes_no_skill() -> None:
    text = (CONSENSUS_REVIEW_DIR / "references/fix-workflow.md").read_text(
        encoding="utf-8"
    )
    assert "No fix-validation comment is posted." in text
    for removed in ("code-quality", "git-ops", "recommended-only", "threshold` mode"):
        assert removed not in text
    for disposition in ("fixed", "declined", "partial", "work-item-required"):
        assert f"`{disposition}`" in text


def test_removed_comment_types_are_gone_from_the_skill_tree() -> None:
    templates = CONSENSUS_REVIEW_DIR / "templates"
    assert [path.name for path in sorted(templates.glob("*"))] == [
        "review-comment.md.tmpl"
    ]
    assert not (CONSENSUS_REVIEW_DIR / "skip-files.md").exists()
