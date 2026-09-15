#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

"""
Render and post the consensus-review PR/MR comment.

One comment type exists: ``review``. The script validates the audit metadata
(schema_version 2, contract C-5), renders the comment from a template, and posts
it with ``gh`` or ``glab``. Status and score are decided by the synthesizer; this
script only refuses to publish a report that fails the contract.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from string import Template

from review_contract import (
    DELEGATION_MODES,
    METADATA_KEYS,
    SCHEMA_VERSION,
    STATUS_LABELS,
    STATUSES,
    extract_quality_score,
    is_non_negative_int,
    is_valid_scope_basis,
    is_valid_score,
    is_valid_sha,
)

# Resolve absolute paths for external tools at module load (prevents PATH hijacking)
GH = shutil.which("gh")
GLAB = shutil.which("glab")

STATUS_EMOJI: dict[str, str] = {
    "clean": "✅",
    "passing": "🟡",
    "failing": "❌",
}

TEMPLATE_FILENAME = "review-comment.md.tmpl"

_EVIDENCE_RE = re.compile(
    r"^###\s+Evidence\s*$\n(?P<body>.*?)(?=^###\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
_NESTED_DETAILS_RE = re.compile(r"<details\b", re.IGNORECASE)

MAX_SUMMARY_BULLETS = 3


class ContractError(ValueError):
    """Raised when an input violates the consensus-review publishing contract."""


def read_platform_from_env(repo_dir: str | Path = ".") -> str:
    """Read DEV_SEC_OPS_PLATFORM from the repo-local .env file."""
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


def read_required_text(path: str | Path, *, label: str) -> str:
    """Read a required text file and fail if it is missing or empty."""
    try:
        content = Path(path).read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ContractError(f"Failed to read {label} '{path}': {error}") from error
    if not content:
        raise ContractError(f"{label.capitalize()} file is empty.")
    return content


def build_summary_lines(summary_file: str | Path) -> list[str]:
    """Read the 1-3 bullet summary and reject any other shape."""
    content = read_required_text(summary_file, label="summary")
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not 1 <= len(lines) <= MAX_SUMMARY_BULLETS:
        raise ContractError(
            f"Summary must hold 1-{MAX_SUMMARY_BULLETS} bullets, got {len(lines)}."
        )
    return lines


def template_dir() -> Path:
    """Return the template directory located beside the skill scripts."""
    return Path(__file__).resolve().parent.parent / "templates"


def load_template() -> Template:
    """Load the review comment template."""
    template_path = template_dir() / TEMPLATE_FILENAME
    try:
        content = template_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ContractError(
            f"Failed to read template '{template_path}': {error}"
        ) from error
    return Template(content)


def extract_evidence(review_text: str) -> str:
    """Return the merged Evidence section body from a synthesized report."""
    match = _EVIDENCE_RE.search(review_text)
    if not match:
        return ""
    return match.group("body").strip()


def build_metadata(
    *,
    cycle: int,
    status: str,
    score: int,
    delegation_mode: str,
    plan_source: str,
    reviewed_sha: str,
    scope_basis: str,
    files_touched: int,
    findings_opened: int,
    findings_closed: int,
) -> dict[str, object]:
    """Build and validate the schema_version 2 audit metadata (contract C-5)."""
    metadata: dict[str, object] = {
        "cycle": cycle,
        "delegation_mode": delegation_mode,
        "files_touched": files_touched,
        "findings_closed": findings_closed,
        "findings_opened": findings_opened,
        "plan_source": plan_source,
        "reviewed_sha": reviewed_sha,
        "schema_version": SCHEMA_VERSION,
        "scope_basis": scope_basis,
        "score": score,
        "status": status,
        "type": "review",
    }
    validate_metadata(metadata)
    return metadata


def validate_metadata(metadata: dict[str, object]) -> None:
    """Raise ContractError unless every C-5 key and value type is satisfied."""
    if set(metadata) != METADATA_KEYS:
        missing = sorted(METADATA_KEYS - set(metadata))
        extra = sorted(set(metadata) - METADATA_KEYS)
        raise ContractError(
            f"Metadata key set mismatch (missing={missing}, unexpected={extra})."
        )
    if metadata["schema_version"] != SCHEMA_VERSION:
        raise ContractError(f"schema_version must be {SCHEMA_VERSION}.")
    if metadata["type"] != "review":
        raise ContractError("type must be 'review'.")
    cycle = metadata["cycle"]
    if not isinstance(cycle, int) or isinstance(cycle, bool) or cycle < 1:
        raise ContractError("cycle must be an integer >= 1.")
    if not is_valid_score(metadata["score"]):
        raise ContractError("score must be an integer between 1 and 100.")
    if metadata["status"] not in STATUSES:
        raise ContractError(f"status must be one of {', '.join(STATUSES)}.")
    if metadata["delegation_mode"] not in DELEGATION_MODES:
        raise ContractError(
            f"delegation_mode must be one of {', '.join(DELEGATION_MODES)}."
        )
    plan_source = metadata["plan_source"]
    if not isinstance(plan_source, str) or not plan_source.strip():
        raise ContractError("plan_source must be a non-empty string.")
    if not is_valid_sha(metadata["reviewed_sha"]):
        raise ContractError("reviewed_sha must be 7-40 lowercase hex characters.")
    if not is_valid_scope_basis(metadata["scope_basis"]):
        raise ContractError("scope_basis must be 'full-diff' or 'delta-since:<sha>'.")
    for key in ("files_touched", "findings_opened", "findings_closed"):
        if not is_non_negative_int(metadata[key]):
            raise ContractError(f"{key} must be a non-negative integer.")


def build_metadata_block(metadata: dict[str, object]) -> str:
    """Render the hidden metadata block used for PR/MR audit recovery."""
    encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
    return f"<!-- consensus-review\n{encoded}\n-->"


def build_provenance_line(
    *,
    delegation_mode: str,
    plan_source: str,
    scope_basis: str,
    reviewed_sha: str,
) -> str:
    """Render the single provenance line shown above the summary."""
    return (
        f"Delegation: {delegation_mode}. Plan: {plan_source}. "
        f"Scope: {scope_basis}. Reviewed: {reviewed_sha}."
    )


def build_review_comment_body(
    review_text: str,
    *,
    summary_lines: list[str],
    metadata: dict[str, object],
) -> str:
    """Render the full review comment, metadata block first."""
    validate_metadata(metadata)

    status = str(metadata["status"])
    score = int(str(metadata["score"]))
    cycle = int(str(metadata["cycle"]))

    if extract_quality_score(review_text) is None:
        raise ContractError(
            "Review report is missing a '### Quality Score: N/100' heading."
        )
    if not extract_evidence(review_text):
        raise ContractError(
            "Review report is missing a non-empty '### Evidence' section."
        )

    # recover_context.py reads the first <details> block as the full report, so a
    # nested block inside the report body would truncate recovery.
    if _NESTED_DETAILS_RE.search(review_text):
        raise ContractError("Review report must not contain a nested <details> block.")

    body = load_template().substitute(
        {
            "icon": STATUS_EMOJI[status],
            "cycle_suffix": f"{cycle:02d}",
            "score": str(score),
            "status_label": STATUS_LABELS[status],
            "provenance_line": build_provenance_line(
                delegation_mode=str(metadata["delegation_mode"]),
                plan_source=str(metadata["plan_source"]),
                scope_basis=str(metadata["scope_basis"]),
                reviewed_sha=str(metadata["reviewed_sha"]),
            ),
            "summary_text": "\n".join(summary_lines),
            "details_text": review_text,
        }
    )
    return f"{build_metadata_block(metadata)}\n\n{body}"


def post_comment_github(pr_number: int, body: str, repo_dir: str | Path = ".") -> None:
    """Post a comment to a GitHub PR."""
    if not GH:
        raise FileNotFoundError("gh executable not found in PATH")
    subprocess.run(
        [GH, "pr", "comment", str(pr_number), "--body", body],
        cwd=repo_dir,
        check=True,
    )


def post_comment_gitlab(pr_number: int, body: str, repo_dir: str | Path = ".") -> None:
    """Post a note to a GitLab MR."""
    if not GLAB:
        raise FileNotFoundError("glab executable not found in PATH")
    subprocess.run(
        [GLAB, "mr", "note", str(pr_number), "--message", body],
        cwd=repo_dir,
        check=True,
    )


def post_comment(
    pr_number: int, body: str, *, platform: str, repo_dir: str | Path = "."
) -> None:
    """Post the rendered comment to the selected platform."""
    if platform == "gitlab":
        post_comment_gitlab(pr_number, body, repo_dir=repo_dir)
    else:
        post_comment_github(pr_number, body, repo_dir=repo_dir)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Post the consensus-review comment to a GitHub PR or GitLab MR.",
    )
    parser.add_argument(
        "--pr-number", type=int, required=True, help="PR/MR number to comment on"
    )
    parser.add_argument(
        "--review-file",
        required=True,
        help="Path to the synthesized review report",
    )
    parser.add_argument(
        "--summary-file",
        required=True,
        help="Path to the file holding the 1-3 bullet summary",
    )
    parser.add_argument(
        "--repo-dir",
        default=".",
        help="Git repository directory where gh/glab commands run (default: .)",
    )
    parser.add_argument("--cycle", type=int, required=True, help="Review cycle number")
    parser.add_argument(
        "--status", required=True, choices=list(STATUSES), help="Review status"
    )
    parser.add_argument(
        "--delegation-mode",
        required=True,
        choices=list(DELEGATION_MODES),
        help="How the reviewer roles were run",
    )
    parser.add_argument(
        "--plan-source",
        required=True,
        help="'none', or 'supplied: <path or short description>'",
    )
    parser.add_argument(
        "--reviewed-sha", required=True, help="Reviewed HEAD SHA (7-40 lowercase hex)"
    )
    parser.add_argument(
        "--scope-basis",
        required=True,
        help="'full-diff' or 'delta-since:<sha>'",
    )
    parser.add_argument(
        "--files-touched", type=int, required=True, help="Files in the reviewed scope"
    )
    parser.add_argument(
        "--findings-opened", type=int, required=True, help="Findings opened this cycle"
    )
    parser.add_argument(
        "--findings-closed", type=int, required=True, help="Findings closed this cycle"
    )
    parser.add_argument(
        "--score",
        type=int,
        default=None,
        help="Raw score; read from the review report heading when omitted",
    )
    parser.add_argument(
        "--platform",
        default=None,
        choices=["github", "gitlab"],
        help="Override platform detection (default: DEV_SEC_OPS_PLATFORM, else github)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate inputs, render the review comment, and post it."""
    args = build_parser().parse_args(argv)

    platform = args.platform or read_platform_from_env(args.repo_dir)

    try:
        review_text = read_required_text(args.review_file, label="review")
        summary_lines = build_summary_lines(args.summary_file)
        score = args.score
        if score is None:
            score = extract_quality_score(review_text)
        if score is None:
            raise ContractError(
                "Review comments require a Quality Score heading or --score."
            )
        metadata = build_metadata(
            cycle=args.cycle,
            status=args.status,
            score=score,
            delegation_mode=args.delegation_mode,
            plan_source=args.plan_source,
            reviewed_sha=args.reviewed_sha,
            scope_basis=args.scope_basis,
            files_touched=args.files_touched,
            findings_opened=args.findings_opened,
            findings_closed=args.findings_closed,
        )
        body = build_review_comment_body(
            review_text, summary_lines=summary_lines, metadata=metadata
        )
    except ContractError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    try:
        post_comment(args.pr_number, body, platform=platform, repo_dir=args.repo_dir)
    except FileNotFoundError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(
            f"Error: Failed to post comment (exit code {error.returncode}): {error}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
