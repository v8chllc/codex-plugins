"""Pin the Codex deferred input routing contract."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "plugins/v8ch/skills/consensus-review"


def test_skill_accepts_deferred_and_routes_it_only_to_synthesizer() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    inputs = skill.split("## Inputs\n", 1)[1].split("## Plan handling\n", 1)[0]
    for phrase in (
        "caller-supplied `deferred` JSON text or a file path",
        "A local review accepts a\n`deferred` file only",
        "never recovered from PR/MR comments",
        "Only the\nsynthesizer consumes this input",
        "a file identified as the `deferred`",
    ):
        assert phrase in inputs
    handling = skill.split("## Plan handling\n", 1)[1].split(
        "## Roles and delegation\n", 1
    )[0]
    assert "when the input is absent or an empty array" in handling
    assert "`supplied: <path or short description>`" in handling
    assert "only the synthesizer receives the input itself" in handling
    synthesis = skill.split("### 8. Synthesize\n", 1)[1].split(
        "### 9. Post or return\n", 1
    )[0]
    assert "the `deferred` input and its source" in synthesis
    assert "reviewed repository" in synthesis


def test_synthesizer_routes_deferred_findings_and_malformed_input() -> None:
    text = (ROOT / "agents/review-synthesizer.md").read_text(encoding="utf-8")
    for phrase in (
        "Parse `deferred` as a JSON array in its supplied order",
        "An omitted or null repository is run-wide",
        "do no cross-repository matching",
        "exactly one Plan Note titled",
        "`Unparseable deferred input` with a 0 deduction",
        "by judgment, not string matching",
        "Matches deferred entry <n>",
        "no `[F-N]` number, a 0 deduction",
        "is not sent to the fixer",
        "new instance of a deferred defect",
        "an unsure match remains a finding at its own",
        "Deferred: <none | supplied: source>.",
    ):
        assert phrase in text


def test_poster_hands_deferred_source_to_schema_3_script() -> None:
    text = (ROOT / "agents/consensus-review-poster.md").read_text(encoding="utf-8")
    assert "copy `Deferred:` into `--deferred-source`" in text
    assert "--deferred-source '<none | supplied: source>'" in text
    assert "`schema_version: 3`" in text


def test_reviewers_and_fixer_do_not_receive_deferred() -> None:
    for name in (
        "architecture-reviewer.md",
        "correctness-reviewer.md",
        "standards-reviewer.md",
        "consensus-review-fixer.md",
    ):
        assert (
            "deferred"
            not in (ROOT / "agents" / name).read_text(encoding="utf-8").lower()
        )
