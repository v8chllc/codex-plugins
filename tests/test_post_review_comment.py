"""Tests for the consensus-review comment renderer and publisher."""

import json
import subprocess
from pathlib import Path
from typing import Any

import post_review_comment as prc
import pytest

from tests.consensus_review_support import FIXTURES_DIR

REPORT = (FIXTURES_DIR / "sample-report.md").read_text(encoding="utf-8").strip()
SUMMARY_LINES = [
    line
    for line in (FIXTURES_DIR / "summary.md").read_text(encoding="utf-8").splitlines()
    if line.strip()
]

BASE_METADATA: dict[str, Any] = {
    "cycle": 1,
    "status": "passing",
    "score": 88,
    "delegation_mode": "parallel-subagents",
    "plan_source": "none",
    "reviewed_sha": "abc1234",
    "scope_basis": "full-diff",
    "files_touched": 2,
    "findings_opened": 2,
    "findings_closed": 0,
}


def metadata(**overrides: Any) -> dict[str, object]:
    values = {**BASE_METADATA, **overrides}
    return prc.build_metadata(**values)


# --- platform detection ----------------------------------------------------


def test_read_platform_defaults_to_github(tmp_path: Path) -> None:
    assert prc.read_platform_from_env(tmp_path) == "github"


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("DEV_SEC_OPS_PLATFORM=gitlab\n", "gitlab"),
        ('DEV_SEC_OPS_PLATFORM="gitlab"\n', "gitlab"),
        ("DEV_SEC_OPS_PLATFORM=GitLab\n", "gitlab"),
        ("DEV_SEC_OPS_PLATFORM=github\n", "github"),
        ("OTHER=1\n", "github"),
    ],
)
def test_read_platform_from_env(tmp_path: Path, line: str, expected: str) -> None:
    (tmp_path / ".env").write_text(line, encoding="utf-8")
    assert prc.read_platform_from_env(tmp_path) == expected


# --- metadata validation (contract C-5) ------------------------------------


def test_metadata_has_exactly_the_contract_key_set() -> None:
    assert set(metadata()) == {
        "cycle",
        "delegation_mode",
        "files_touched",
        "findings_closed",
        "findings_opened",
        "plan_source",
        "reviewed_sha",
        "schema_version",
        "scope_basis",
        "score",
        "status",
        "type",
    }


def test_metadata_block_is_sorted_and_compact() -> None:
    block = prc.build_metadata_block(metadata())
    assert block.startswith("<!-- consensus-review\n")
    assert block.endswith("\n-->")
    encoded = block.split("\n")[1]
    assert " " not in encoded
    assert list(json.loads(encoded)) == sorted(json.loads(encoded))
    assert json.loads(encoded)["schema_version"] == 2


def test_metadata_rejects_an_extra_key() -> None:
    payload = dict(metadata())
    payload["extra"] = 1
    with pytest.raises(prc.ContractError, match="key set mismatch"):
        prc.validate_metadata(payload)


def test_metadata_rejects_a_missing_key() -> None:
    payload = dict(metadata())
    del payload["scope_basis"]
    with pytest.raises(prc.ContractError, match="key set mismatch"):
        prc.validate_metadata(payload)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"cycle": 0}, "cycle must be an integer"),
        ({"score": 0}, "score must be an integer"),
        ({"score": 101}, "score must be an integer"),
        ({"status": "unknown"}, "status must be one of"),
        ({"delegation_mode": "solo"}, "delegation_mode must be one of"),
        ({"plan_source": "   "}, "plan_source must be a non-empty"),
        ({"reviewed_sha": "ABC1234"}, "reviewed_sha must be"),
        ({"reviewed_sha": "abc"}, "reviewed_sha must be"),
        ({"scope_basis": "delta"}, "scope_basis must be"),
        ({"files_touched": -1}, "files_touched must be"),
        ({"findings_opened": -1}, "findings_opened must be"),
        ({"findings_closed": -1}, "findings_closed must be"),
    ],
)
def test_metadata_value_types_are_enforced(
    override: dict[str, Any], message: str
) -> None:
    with pytest.raises(prc.ContractError, match=message):
        metadata(**override)


def test_metadata_accepts_a_supplied_plan_source_and_delta_scope() -> None:
    payload = metadata(
        plan_source="supplied: .plan/feature.md", scope_basis="delta-since:abc1234"
    )
    assert payload["plan_source"] == "supplied: .plan/feature.md"
    assert payload["scope_basis"] == "delta-since:abc1234"


# --- summary shape ---------------------------------------------------------


@pytest.mark.parametrize("count", [1, 2, 3])
def test_summary_accepts_one_to_three_bullets(tmp_path: Path, count: int) -> None:
    path = tmp_path / "summary.md"
    path.write_text("\n".join(f"- bullet {i}" for i in range(count)), encoding="utf-8")
    assert len(prc.build_summary_lines(path)) == count


@pytest.mark.parametrize("count", [0, 4])
def test_summary_rejects_any_other_count(tmp_path: Path, count: int) -> None:
    path = tmp_path / "summary.md"
    path.write_text("\n".join(f"- bullet {i}" for i in range(count)), encoding="utf-8")
    with pytest.raises(prc.ContractError):
        prc.build_summary_lines(path)


def test_missing_summary_file_is_a_contract_error(tmp_path: Path) -> None:
    with pytest.raises(prc.ContractError, match="Failed to read summary"):
        prc.build_summary_lines(tmp_path / "absent.md")


# --- body rendering --------------------------------------------------------


def test_body_starts_with_metadata_then_renders_the_template() -> None:
    body = prc.build_review_comment_body(
        REPORT, summary_lines=SUMMARY_LINES, metadata=metadata()
    )
    assert body.startswith("<!-- consensus-review\n")
    assert "### 🟡 Consensus Review — Cycle 01" in body
    assert "*Score: 88/100 — Passing*" in body
    assert (
        "Delegation: parallel-subagents. Plan: none. "
        "Scope: full-diff. Reviewed: abc1234." in body
    )
    assert "<summary>Evidence and full findings</summary>" in body
    assert REPORT in body


@pytest.mark.parametrize(
    ("status", "icon"),
    [("clean", "✅"), ("passing", "🟡"), ("failing", "❌")],
)
def test_status_icon_follows_the_status(status: str, icon: str) -> None:
    score = {"clean": 96, "passing": 88, "failing": 70}[status]
    body = prc.build_review_comment_body(
        REPORT,
        summary_lines=SUMMARY_LINES,
        metadata=metadata(status=status, score=score),
    )
    assert f"### {icon} Consensus Review" in body


def test_body_requires_a_quality_score_heading() -> None:
    with pytest.raises(prc.ContractError, match="Quality Score"):
        prc.build_review_comment_body(
            "### Evidence\n\n- **Files examined:** a\n- **Commands run:** none",
            summary_lines=SUMMARY_LINES,
            metadata=metadata(),
        )


def test_body_requires_a_non_empty_evidence_section() -> None:
    report = REPORT.replace(
        "- **Files examined:** AGENTS.md, CODING_STANDARDS.md, "
        "src/api/handler.py, tests/test_handler.py\n"
        "- **Commands run:** uv run ruff check ., uv run mypy ., uv run pytest",
        "",
    )
    with pytest.raises(prc.ContractError, match="Evidence"):
        prc.build_review_comment_body(
            report, summary_lines=SUMMARY_LINES, metadata=metadata()
        )


def test_body_rejects_a_nested_details_block() -> None:
    report = REPORT + "\n\n<details>\n<summary>extra</summary>\nhidden\n</details>"
    with pytest.raises(prc.ContractError, match="nested <details>"):
        prc.build_review_comment_body(
            report, summary_lines=SUMMARY_LINES, metadata=metadata()
        )


def test_extract_evidence_returns_the_merged_section() -> None:
    evidence = prc.extract_evidence(REPORT)
    assert "Files examined" in evidence
    assert "Commands run" in evidence
    assert "Must Fix" not in evidence


# --- transport -------------------------------------------------------------


def test_post_comment_github_invokes_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(command: list[str], **kwargs: Any) -> None:
        calls.append({"command": command, "kwargs": kwargs})

    monkeypatch.setattr(prc, "GH", "/usr/bin/gh")
    monkeypatch.setattr(prc.subprocess, "run", fake_run)
    prc.post_comment(7, "body text", platform="github", repo_dir="/repo")

    assert calls[0]["command"] == [
        "/usr/bin/gh",
        "pr",
        "comment",
        "7",
        "--body",
        "body text",
    ]
    assert calls[0]["kwargs"]["cwd"] == "/repo"
    assert calls[0]["kwargs"]["check"] is True


def test_post_comment_gitlab_invokes_glab(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> None:
        calls.append(command)

    monkeypatch.setattr(prc, "GLAB", "/usr/bin/glab")
    monkeypatch.setattr(prc.subprocess, "run", fake_run)
    prc.post_comment(7, "body text", platform="gitlab", repo_dir="/repo")

    assert calls[0] == [
        "/usr/bin/glab",
        "mr",
        "note",
        "7",
        "--message",
        "body text",
    ]


def test_post_comment_requires_the_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prc, "GH", None)
    with pytest.raises(FileNotFoundError, match="gh executable"):
        prc.post_comment(7, "body", platform="github")
    monkeypatch.setattr(prc, "GLAB", None)
    with pytest.raises(FileNotFoundError, match="glab executable"):
        prc.post_comment(7, "body", platform="gitlab")


# --- CLI -------------------------------------------------------------------


def cli_args(tmp_path: Path, **overrides: str) -> list[str]:
    review = tmp_path / "review.md"
    review.write_text(REPORT, encoding="utf-8")
    summary = tmp_path / "summary.md"
    summary.write_text("\n".join(SUMMARY_LINES), encoding="utf-8")
    args = {
        "--pr-number": "7",
        "--review-file": str(review),
        "--summary-file": str(summary),
        "--repo-dir": str(tmp_path),
        "--cycle": "1",
        "--status": "passing",
        "--delegation-mode": "parallel-subagents",
        "--plan-source": "none",
        "--reviewed-sha": "abc1234",
        "--scope-basis": "full-diff",
        "--files-touched": "2",
        "--findings-opened": "2",
        "--findings-closed": "0",
    }
    args.update(overrides)
    return [item for pair in args.items() for item in pair]


def test_cli_posts_the_rendered_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    posted: list[tuple[int, str, str]] = []

    def fake_post(number: int, body: str, *, platform: str, repo_dir: Any) -> None:
        posted.append((number, body, platform))

    monkeypatch.setattr(prc, "post_comment", fake_post)
    assert prc.main(cli_args(tmp_path)) == 0
    assert posted[0][0] == 7
    assert posted[0][2] == "github"
    assert '"schema_version":2' in posted[0][1]


def test_cli_uses_the_env_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("DEV_SEC_OPS_PLATFORM=gitlab\n", encoding="utf-8")
    seen: list[str] = []

    def fake_post(number: int, body: str, *, platform: str, repo_dir: Any) -> None:
        seen.append(platform)

    monkeypatch.setattr(prc, "post_comment", fake_post)
    assert prc.main(cli_args(tmp_path)) == 0
    assert seen == ["gitlab"]


def test_cli_reports_a_contract_failure_without_posting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_post(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("must not post")

    monkeypatch.setattr(prc, "post_comment", fail_post)
    assert prc.main(cli_args(tmp_path, **{"--cycle": "0"})) == 1
    assert "cycle must be an integer" in capsys.readouterr().err


def test_cli_reports_a_transport_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_post(*args: Any, **kwargs: Any) -> None:
        raise subprocess.CalledProcessError(1, ["gh"])

    monkeypatch.setattr(prc, "post_comment", fake_post)
    assert prc.main(cli_args(tmp_path)) == 1
    assert "Failed to post comment" in capsys.readouterr().err
