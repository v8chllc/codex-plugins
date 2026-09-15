"""Tests for consensus-review PR/MR context recovery."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import recover_context as rc

from tests.consensus_review_support import FIXTURES_DIR

GITHUB_V2 = FIXTURES_DIR / "comments-github-v2.json"
GITLAB_V2 = FIXTURES_DIR / "comments-gitlab-v2.json"
LEGACY_V1 = FIXTURES_DIR / "comments-legacy-v1.json"


def load(path: Path) -> list[dict[str, Any]]:
    return rc.load_comments_json(path)


# --- platform detection ----------------------------------------------------


def test_platform_override_wins(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("DEV_SEC_OPS_PLATFORM=github\n", encoding="utf-8")
    assert rc.read_platform("GitLab", tmp_path) == "gitlab"


def test_platform_falls_back_to_env_then_github(tmp_path: Path) -> None:
    assert rc.read_platform(None, tmp_path) == "github"
    (tmp_path / ".env").write_text('DEV_SEC_OPS_PLATFORM="gitlab"\n', encoding="utf-8")
    assert rc.read_platform(None, tmp_path) == "gitlab"


# --- paginated payload decoding --------------------------------------------


def test_decode_json_stream_handles_concatenated_pages() -> None:
    payload = '[{"body": "a"}]\n[{"body": "b"}]\n'
    assert rc.flatten_comment_pages(payload) == [{"body": "a"}, {"body": "b"}]


def test_decode_json_stream_handles_a_single_page() -> None:
    assert rc.flatten_comment_pages('[{"body": "a"}]') == [{"body": "a"}]


def test_flatten_skips_non_dict_entries() -> None:
    assert rc.flatten_comment_pages('[{"body": "a"}, 3, null]') == [{"body": "a"}]


# --- v2 metadata validation (contract C-5) ---------------------------------


def valid_metadata(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "cycle": 1,
        "delegation_mode": "parallel-subagents",
        "files_touched": 2,
        "findings_closed": 0,
        "findings_opened": 2,
        "plan_source": "none",
        "reviewed_sha": "abc1234",
        "schema_version": 2,
        "scope_basis": "full-diff",
        "score": 88,
        "status": "passing",
        "type": "review",
    }
    payload.update(overrides)
    return payload


def test_valid_v2_metadata_is_accepted() -> None:
    assert rc.validate_v2_metadata(valid_metadata()) is True


@pytest.mark.parametrize(
    "override",
    [
        {"cycle": 0},
        {"cycle": "1"},
        {"score": 0},
        {"score": 101},
        {"status": "unknown"},
        {"delegation_mode": "solo"},
        {"plan_source": ""},
        {"reviewed_sha": "ABC1234"},
        {"scope_basis": "delta"},
        {"files_touched": -1},
        {"findings_opened": -1},
        {"findings_closed": -1},
        {"type": "acceptance"},
    ],
)
def test_invalid_v2_metadata_is_rejected(override: dict[str, Any]) -> None:
    assert rc.validate_v2_metadata(valid_metadata(**override)) is False


def test_v2_metadata_rejects_an_extra_or_missing_key() -> None:
    extra = valid_metadata()
    extra["unexpected"] = 1
    assert rc.validate_v2_metadata(extra) is False
    missing = valid_metadata()
    del missing["scope_basis"]
    assert rc.validate_v2_metadata(missing) is False


def test_a_comment_failing_validation_is_ignored() -> None:
    comments = rc.parse_audit_comments(load(LEGACY_V1))
    assert all(comment.schema_version == 1 for comment in comments)
    assert not any(comment.is_v2_review for comment in comments)


def test_v1_non_review_types_are_ignored() -> None:
    comments = rc.parse_audit_comments(load(LEGACY_V1))
    assert [comment.comment_type for comment in comments] == ["review"]


def test_a_comment_without_metadata_is_ignored() -> None:
    comments = rc.parse_audit_comments(load(GITHUB_V2))
    assert len(comments) == 2
    assert all(comment.is_v2_review for comment in comments)


# --- cycle and scope resolution --------------------------------------------


def test_next_cycle_follows_the_highest_prior_cycle() -> None:
    assert rc.next_cycle(rc.parse_audit_comments(load(GITHUB_V2))) == 3
    assert rc.next_cycle(rc.parse_audit_comments(load(LEGACY_V1))) == 2
    assert rc.next_cycle([]) == 1


def test_scope_basis_is_full_diff_without_a_prior_review() -> None:
    basis, reason = rc.resolve_scope_basis([], ancestor_check=False)
    assert basis == "full-diff"
    assert "no prior consensus-review comment" in reason


def test_scope_basis_is_full_diff_after_a_legacy_review() -> None:
    comments = rc.parse_audit_comments(load(LEGACY_V1))
    basis, reason = rc.resolve_scope_basis(comments, ancestor_check=False)
    assert basis == "full-diff"
    assert "schema_version 1 legacy history" in reason


def test_scope_basis_narrows_to_the_latest_v2_sha() -> None:
    comments = rc.parse_audit_comments(load(GITHUB_V2))
    basis, reason = rc.resolve_scope_basis(comments, ancestor_check=False)
    assert basis == "delta-since:def5678"
    assert "cycle 02" in reason


def test_scope_basis_falls_back_when_the_sha_is_not_an_ancestor(
    tmp_path: Path,
) -> None:
    comments = rc.parse_audit_comments(load(GITHUB_V2))
    basis, reason = rc.resolve_scope_basis(comments, repo_dir=tmp_path)
    assert basis == "full-diff"
    assert "not an ancestor of HEAD" in reason


def test_ancestor_check_reads_real_git_history(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    (tmp_path / "file.txt").write_text("one\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "first")
    first = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (tmp_path / "file.txt").write_text("two\n", encoding="utf-8")
    git("commit", "-qam", "second")

    assert rc.is_ancestor(first[:7], tmp_path) is True
    assert rc.is_ancestor("0" * 40, tmp_path) is False


def test_latest_v2_review_picks_the_highest_cycle() -> None:
    comments = rc.parse_audit_comments(load(GITHUB_V2))
    latest = rc.latest_v2_review(comments)
    assert latest is not None
    assert latest.cycle == 2
    assert latest.metadata["reviewed_sha"] == "def5678"


# --- output ----------------------------------------------------------------


def build_output(path: Path, platform: str = "github") -> str:
    comments = rc.parse_audit_comments(load(path))
    basis, reason = rc.resolve_scope_basis(comments, ancestor_check=False)
    return rc.build_context_output(
        number=9,
        platform=platform,
        audit_comments=comments,
        scope_basis=basis,
        scope_reason=reason,
    )


def test_output_header_carries_the_recovery_facts() -> None:
    output = build_output(GITHUB_V2)
    assert output.startswith("# RECOVERED_CONTEXT")
    assert "**Platform:** github" in output
    assert "**PR:** 9" in output
    assert "**Next cycle:** 03" in output
    assert "**Score source:** raw review score" in output
    assert "**Scope basis:** delta-since:def5678" in output
    assert "**Scope basis reason:** cycle 02 reviewed def5678" in output


def test_output_uses_the_mr_label_for_gitlab() -> None:
    assert "**MR:** 9" in build_output(GITLAB_V2, platform="gitlab")


def test_output_lists_prior_reviews_with_provenance() -> None:
    output = build_output(GITHUB_V2)
    assert "## Prior Reviews" in output
    assert "| Cycle | Score | Status | Delegation | Plan | Scope |" in output
    assert "| 01 | 88 | passing | parallel-subagents | none | full-diff |" in output


def test_output_includes_the_full_surviving_body() -> None:
    output = build_output(GITHUB_V2)
    assert "**Full report:**" in output
    assert "#### [F-1] [HIGH] Retry path drops the correlation id" in output
    assert "### Score Breakdown" in output


def test_output_extracts_the_summary_section() -> None:
    output = build_output(GITHUB_V2)
    assert "- One HIGH finding: the payload builder drops a required field" in output


def test_output_reports_no_prior_comments() -> None:
    output = rc.build_context_output(
        number=9,
        platform="github",
        audit_comments=[],
        scope_basis="full-diff",
        scope_reason="no prior consensus-review comment exists",
    )
    assert "This is the first cycle." in output
    assert "## Prior Reviews" not in output


def test_output_separates_legacy_history() -> None:
    output = build_output(LEGACY_V1)
    assert "## Legacy History (schema_version 1)" in output
    assert "never supplies a narrowing" in output
    assert "## Prior Reviews" not in output


# --- fetching --------------------------------------------------------------


def test_github_fetch_uses_the_issue_comments_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, '[{"body": "x"}]', "")

    monkeypatch.setattr(rc, "GH", "/usr/bin/gh")
    monkeypatch.setattr(rc.subprocess, "run", fake_run)
    assert rc.fetch_github_comments(9, "/repo") == [{"body": "x"}]
    assert seen[0] == [
        "/usr/bin/gh",
        "api",
        "repos/{owner}/{repo}/issues/9/comments",
        "--paginate",
    ]


def test_gitlab_fetch_uses_the_notes_api(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, '[{"note": "x"}]', "")

    monkeypatch.setattr(rc, "GLAB", "/usr/bin/glab")
    monkeypatch.setattr(rc.subprocess, "run", fake_run)
    assert rc.fetch_gitlab_comments(9, "/repo") == [{"note": "x"}]
    assert seen[0] == [
        "/usr/bin/glab",
        "api",
        "projects/:id/merge_requests/9/notes",
        "--paginate",
    ]


def test_fetch_requires_the_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rc, "GH", None)
    with pytest.raises(FileNotFoundError, match="gh executable"):
        rc.fetch_github_comments(9)
    monkeypatch.setattr(rc, "GLAB", None)
    with pytest.raises(FileNotFoundError, match="glab executable"):
        rc.fetch_gitlab_comments(9)


def test_fetch_raises_on_a_client_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "not authenticated")

    monkeypatch.setattr(rc, "GH", "/usr/bin/gh")
    monkeypatch.setattr(rc.subprocess, "run", fake_run)
    with pytest.raises(subprocess.CalledProcessError):
        rc.fetch_github_comments(9)


def test_gitlab_notes_are_normalized_like_github_comments() -> None:
    comments = rc.parse_audit_comments(load(GITLAB_V2))
    assert len(comments) == 1
    assert comments[0].author == "reviewer"
    assert comments[0].url.endswith("#note_1")


def test_load_comments_json_accepts_both_shapes(tmp_path: Path) -> None:
    listed = tmp_path / "list.json"
    listed.write_text(json.dumps([{"body": "a"}]), encoding="utf-8")
    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text(json.dumps({"comments": [{"body": "a"}]}), encoding="utf-8")
    assert rc.load_comments_json(listed) == rc.load_comments_json(wrapped)


def test_load_comments_json_rejects_another_shape(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"comments": 3}), encoding="utf-8")
    with pytest.raises(ValueError, match="must be a list"):
        rc.load_comments_json(path)


# --- CLI -------------------------------------------------------------------


def test_cli_prints_the_recovered_context(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = rc.main(
        ["9", "--repo-dir", str(tmp_path), "--comments-json", str(GITHUB_V2)]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert output.startswith("# RECOVERED_CONTEXT")
    assert "**Next cycle:** 03" in output
    # tmp_path is not a git repo, so the recorded SHA cannot be an ancestor.
    assert "**Scope basis:** full-diff" in output


def test_cli_reports_a_fetch_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_fetch(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        raise subprocess.CalledProcessError(1, ["gh"], "", "not authenticated")

    monkeypatch.setattr(rc, "fetch_platform_comments", fake_fetch)
    assert rc.main(["9", "--repo-dir", str(tmp_path)]) == 1
    assert "failed to recover PR/MR comments" in capsys.readouterr().err
