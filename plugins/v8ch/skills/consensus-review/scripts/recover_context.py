#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

"""
Recover consensus-review audit history from PR/MR comments.

The PR/MR thread is the durable audit trail. This script fetches its comments,
keeps the ones carrying a valid schema_version 2 ``consensus-review`` metadata
block, and prints the cycle number, scope basis, and prior review bodies the
orchestrator needs. A schema_version 1 comment is reported as legacy history and
never supplies a narrowing basis.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from review_contract import (
    DELEGATION_MODES,
    METADATA_KEYS,
    SCHEMA_VERSION,
    STATUSES,
    is_non_negative_int,
    is_valid_scope_basis,
    is_valid_score,
    is_valid_sha,
)

GH = shutil.which("gh")
GLAB = shutil.which("glab")
GIT = shutil.which("git")

_METADATA_RE = re.compile(r"<!--\s*consensus-review\s*(.*?)\s*-->", re.DOTALL)
_SUMMARY_RE = re.compile(
    r"^###\s+Summary\s*$\n(?P<summary>.*?)(?=^<details>|^###\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
# Audit comments wrap their full report in a single top-level <details> element.
# post_review_comment.py rejects nested blocks, so the first match is the report.
_DETAILS_RE = re.compile(
    r"<details>\s*<summary>.*?</summary>\s*(?P<details>.*?)\s*</details>",
    re.DOTALL | re.IGNORECASE,
)

SCORE_SOURCE = "raw review score"

PRIOR_REVIEW_COLUMNS: tuple[str, ...] = (
    "Cycle",
    "Score",
    "Status",
    "Delegation",
    "Plan",
    "Scope",
    "Reviewed SHA",
    "Comment",
)

LEGACY_REVIEW_COLUMNS: tuple[str, ...] = ("Cycle", "Score", "Comment")


def _table_row(cells: list[str] | tuple[str, ...]) -> str:
    """Render one markdown table row."""
    return "| " + " | ".join(cells) + " |"


@dataclass(frozen=True)
class AuditComment:
    """A PR/MR comment carrying a consensus-review metadata block."""

    metadata: dict[str, Any]
    body: str
    created_at: str
    url: str
    author: str

    @property
    def schema_version(self) -> int:
        raw = self.metadata.get("schema_version")
        return raw if isinstance(raw, int) and not isinstance(raw, bool) else 0

    @property
    def cycle(self) -> int:
        raw = self.metadata.get("cycle")
        try:
            return int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0

    @property
    def comment_type(self) -> str:
        raw = self.metadata.get("type")
        return str(raw) if raw is not None else "unknown"

    @property
    def is_v2_review(self) -> bool:
        return self.schema_version == SCHEMA_VERSION and self.comment_type == "review"


def read_platform(override: str | None, repo_dir: str | Path = ".") -> str:
    """Return the platform from --platform, else DEV_SEC_OPS_PLATFORM, else github."""
    if override:
        return override.strip().lower()
    env_path = Path(repo_dir) / ".env"
    if not env_path.exists():
        return "github"
    with open(env_path, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line.startswith("DEV_SEC_OPS_PLATFORM="):
                value = line[len("DEV_SEC_OPS_PLATFORM=") :]
                return value.strip().strip('"').strip("'").lower()
    return "github"


def decode_json_stream(payload: str) -> list[Any]:
    """Decode one or more concatenated JSON values.

    ``gh api --paginate`` and ``glab api --paginate`` emit one JSON array per
    page, concatenated. Decoding the stream handles both that shape and a single
    array from an unpaginated response.
    """
    decoder = json.JSONDecoder()
    values: list[Any] = []
    index = 0
    text = payload.strip()
    while index < len(text):
        value, offset = decoder.raw_decode(text, index)
        values.append(value)
        index = offset
        while index < len(text) and text[index] in " \t\r\n":
            index += 1
    return values


def flatten_comment_pages(payload: str) -> list[dict[str, Any]]:
    """Flatten paginated JSON array pages into one comment list."""
    comments: list[dict[str, Any]] = []
    for page in decode_json_stream(payload):
        if isinstance(page, list):
            comments.extend(item for item in page if isinstance(item, dict))
        elif isinstance(page, dict):
            comments.append(page)
    return comments


def _run(command: list[str], repo_dir: str | Path) -> str:
    """Run a command and return stdout, raising on a non-zero exit."""
    result = subprocess.run(command, cwd=repo_dir, capture_output=True, text=True)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, command, result.stdout, result.stderr
        )
    return result.stdout


def fetch_github_comments(
    number: int, repo_dir: str | Path = "."
) -> list[dict[str, Any]]:
    """Fetch GitHub PR issue-level comments through gh.

    Note: this retrieves issue-level (top-level) PR comments only, not inline
    review comments attached to diff lines.
    """
    if not GH:
        raise FileNotFoundError("gh executable not found in PATH")
    payload = _run(
        [
            GH,
            "api",
            f"repos/{{owner}}/{{repo}}/issues/{number}/comments",
            "--paginate",
        ],
        repo_dir,
    )
    return flatten_comment_pages(payload)


def fetch_gitlab_comments(
    number: int, repo_dir: str | Path = "."
) -> list[dict[str, Any]]:
    """Fetch GitLab MR notes through glab."""
    if not GLAB:
        raise FileNotFoundError("glab executable not found in PATH")
    payload = _run(
        [
            GLAB,
            "api",
            f"projects/:id/merge_requests/{number}/notes",
            "--paginate",
        ],
        repo_dir,
    )
    return flatten_comment_pages(payload)


def fetch_platform_comments(
    number: int, *, platform: str, repo_dir: str | Path = "."
) -> list[dict[str, Any]]:
    """Fetch PR/MR comments for the selected platform."""
    if platform == "gitlab":
        return fetch_gitlab_comments(number, repo_dir)
    return fetch_github_comments(number, repo_dir)


def load_comments_json(path: Path) -> list[dict[str, Any]]:
    """Load normalized or platform-style comments from a JSON file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    comments = payload.get("comments", []) if isinstance(payload, dict) else payload
    if not isinstance(comments, list):
        raise ValueError(
            "comments JSON must be a list or an object with a comments list"
        )
    return [comment for comment in comments if isinstance(comment, dict)]


def validate_v2_metadata(metadata: dict[str, Any]) -> bool:
    """Return whether metadata satisfies the schema_version 2 contract (C-5)."""
    if set(metadata) != METADATA_KEYS:
        return False
    if metadata["schema_version"] != SCHEMA_VERSION or metadata["type"] != "review":
        return False
    cycle = metadata["cycle"]
    if not isinstance(cycle, int) or isinstance(cycle, bool) or cycle < 1:
        return False
    if not is_valid_score(metadata["score"]):
        return False
    if metadata["status"] not in STATUSES:
        return False
    if metadata["delegation_mode"] not in DELEGATION_MODES:
        return False
    plan_source = metadata["plan_source"]
    if not isinstance(plan_source, str) or not plan_source.strip():
        return False
    if not is_valid_sha(metadata["reviewed_sha"]):
        return False
    if not is_valid_scope_basis(metadata["scope_basis"]):
        return False
    return all(
        is_non_negative_int(metadata[key])
        for key in ("files_touched", "findings_opened", "findings_closed")
    )


def extract_metadata(text: str) -> dict[str, Any] | None:
    """Return a usable consensus-review metadata block, or None.

    A valid v2 review block is returned as-is. A v1 review block is returned so
    it can be listed as legacy history. Anything else, including a v2 block that
    fails validation, is ignored.
    """
    match = _METADATA_RE.search(text)
    if not match:
        return None
    try:
        metadata = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(metadata, dict):
        return None

    version = metadata.get("schema_version")
    if version == SCHEMA_VERSION:
        return metadata if validate_v2_metadata(metadata) else None
    if version == 1 and metadata.get("type") == "review":
        return metadata
    return None


def normalise_comment(raw: dict[str, Any]) -> dict[str, str]:
    """Normalize GitHub/GitLab comment JSON into common fields."""
    author = raw.get("author") or raw.get("user") or {}
    if isinstance(author, dict):
        author_name = str(author.get("login") or author.get("username") or "")
    else:
        author_name = str(author)
    return {
        "body": str(raw["body"] if "body" in raw else raw.get("note", "")),
        "created_at": str(raw.get("createdAt") or raw.get("created_at") or ""),
        "url": str(raw.get("url") or raw.get("html_url") or raw.get("web_url") or ""),
        "author": author_name,
    }


def parse_audit_comments(raw_comments: list[dict[str, Any]]) -> list[AuditComment]:
    """Filter raw platform comments down to consensus-review audit comments."""
    audit_comments: list[AuditComment] = []
    for raw in raw_comments:
        normalized = normalise_comment(raw)
        metadata = extract_metadata(normalized["body"])
        if metadata is None:
            continue
        audit_comments.append(
            AuditComment(
                metadata=metadata,
                body=normalized["body"],
                created_at=normalized["created_at"],
                url=normalized["url"],
                author=normalized["author"],
            )
        )
    return sorted(audit_comments, key=lambda c: (c.cycle, c.created_at))


def is_ancestor(sha: str, repo_dir: str | Path = ".") -> bool:
    """Return whether a SHA is an ancestor of HEAD in the given repository."""
    if not GIT:
        return False
    result = subprocess.run(
        [GIT, "merge-base", "--is-ancestor", sha, "HEAD"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def latest_v2_review(audit_comments: list[AuditComment]) -> AuditComment | None:
    """Return the highest-cycle valid v2 review comment, if any."""
    reviews = [comment for comment in audit_comments if comment.is_v2_review]
    if not reviews:
        return None
    return max(reviews, key=lambda c: (c.cycle, c.created_at))


def resolve_scope_basis(
    audit_comments: list[AuditComment],
    *,
    repo_dir: str | Path = ".",
    ancestor_check: bool = True,
) -> tuple[str, str]:
    """Return the ``(scope_basis, reason)`` for the next cycle (contract C-5)."""
    latest = latest_v2_review(audit_comments)
    if latest is None:
        has_legacy = any(comment.schema_version == 1 for comment in audit_comments)
        reason = (
            "the only prior reviews are schema_version 1 legacy history"
            if has_legacy
            else "no prior consensus-review comment exists"
        )
        return "full-diff", reason
    sha = str(latest.metadata["reviewed_sha"])
    if ancestor_check and not is_ancestor(sha, repo_dir):
        return (
            "full-diff",
            f"the prior reviewed SHA {sha} is not an ancestor of HEAD",
        )
    return f"delta-since:{sha}", f"cycle {latest.cycle:02d} reviewed {sha}"


def next_cycle(audit_comments: list[AuditComment]) -> int:
    """Return the next cycle number, counting valid v2 and legacy v1 reviews."""
    cycles = [comment.cycle for comment in audit_comments]
    return max(cycles, default=0) + 1


def extract_summary(text: str) -> str:
    """Return the Summary section of a review comment body."""
    match = _SUMMARY_RE.search(text)
    if not match:
        return "*No summary section found.*"
    return match.group("summary").strip() or "*No summary section found.*"


def extract_report(text: str) -> str:
    """Return the full report body from a review comment's details block."""
    match = _DETAILS_RE.search(text)
    if not match:
        return ""
    return match.group("details").strip()


def build_context_output(
    *,
    number: int,
    platform: str,
    audit_comments: list[AuditComment],
    scope_basis: str,
    scope_reason: str,
) -> str:
    """Build the recovered-context block consumed by the orchestrating skill."""
    platform_label = "MR" if platform == "gitlab" else "PR"
    v2_reviews = [comment for comment in audit_comments if comment.is_v2_review]
    legacy_reviews = [
        comment for comment in audit_comments if comment.schema_version == 1
    ]

    lines: list[str] = [
        "# RECOVERED_CONTEXT",
        "",
        f"**Platform:** {platform}",
        f"**{platform_label}:** {number}",
        f"**Next cycle:** {next_cycle(audit_comments):02d}",
        f"**Score source:** {SCORE_SOURCE}",
        f"**Scope basis:** {scope_basis}",
        f"**Scope basis reason:** {scope_reason}",
        "",
    ]

    if not audit_comments:
        lines += [
            "No prior consensus-review comments found. This is the first cycle.",
            "",
        ]
        return "\n".join(lines)

    if v2_reviews:
        lines += ["## Prior Reviews", "", _table_row(PRIOR_REVIEW_COLUMNS)]
        lines.append(_table_row(["---"] * len(PRIOR_REVIEW_COLUMNS)))
        for comment in v2_reviews:
            metadata = comment.metadata
            lines.append(
                _table_row(
                    [
                        f"{comment.cycle:02d}",
                        str(metadata["score"]),
                        str(metadata["status"]),
                        str(metadata["delegation_mode"]),
                        str(metadata["plan_source"]),
                        str(metadata["scope_basis"]),
                        str(metadata["reviewed_sha"]),
                        comment.url or "n/a",
                    ]
                )
            )
        lines.append("")

        for comment in v2_reviews:
            lines += [
                f"### Review cycle {comment.cycle:02d}",
                "",
                f"*Score {comment.metadata['score']}/100 — "
                f"{comment.metadata['status']}. "
                f"Files touched {comment.metadata['files_touched']}, "
                f"opened {comment.metadata['findings_opened']}, "
                f"closed {comment.metadata['findings_closed']}.*",
                "",
                "**Summary:**",
                "",
                extract_summary(comment.body),
                "",
            ]
            report = extract_report(comment.body)
            if report:
                lines += ["**Full report:**", "", report, ""]

    if legacy_reviews:
        lines += [
            "## Legacy History (schema_version 1)",
            "",
            "> Listed for context only. A legacy review never supplies a narrowing",
            "> basis, so a cycle following one reviews the full diff.",
            "",
            _table_row(LEGACY_REVIEW_COLUMNS),
            _table_row(["---"] * len(LEGACY_REVIEW_COLUMNS)),
        ]
        for comment in legacy_reviews:
            score = comment.metadata.get("score", "n/a")
            lines.append(
                _table_row([f"{comment.cycle:02d}", str(score), comment.url or "n/a"])
            )
        lines.append("")
        for comment in legacy_reviews:
            lines += [
                f"**Legacy cycle {comment.cycle:02d} summary:**",
                "",
                extract_summary(comment.body),
                "",
            ]

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Recover consensus-review context from PR/MR comments.",
    )
    parser.add_argument("number", type=int, metavar="NUMBER", help="PR/MR number")
    parser.add_argument(
        "--platform",
        default=None,
        choices=["github", "gitlab"],
        help="Override platform detection (default: DEV_SEC_OPS_PLATFORM, else github)",
    )
    parser.add_argument(
        "--repo-dir",
        default=".",
        help="Git repository directory where gh/glab/git commands run (default: .)",
    )
    parser.add_argument(
        "--comments-json",
        default=None,
        help="Read comments from JSON instead of fetching from gh/glab",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Print the recovered context block for a PR/MR."""
    args = build_parser().parse_args(argv)
    platform = read_platform(args.platform, args.repo_dir)

    try:
        raw_comments = (
            load_comments_json(Path(args.comments_json))
            if args.comments_json
            else fetch_platform_comments(
                args.number, platform=platform, repo_dir=args.repo_dir
            )
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        detail = str(error)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            detail = f"{error}: {error.stderr.strip()}"
        print(f"Error: failed to recover PR/MR comments: {detail}", file=sys.stderr)
        return 1

    audit_comments = parse_audit_comments(raw_comments)
    scope_basis, scope_reason = resolve_scope_basis(
        audit_comments, repo_dir=args.repo_dir
    )
    print(
        build_context_output(
            number=args.number,
            platform=platform,
            audit_comments=audit_comments,
            scope_basis=scope_basis,
            scope_reason=scope_reason,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
