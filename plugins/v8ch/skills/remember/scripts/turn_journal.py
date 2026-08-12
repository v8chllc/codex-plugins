#!/usr/bin/env python3
"""Maintain opt-in, project-local Codex Stop-hook journal segments.

The hook path is deliberately deterministic: it persists the final assistant
message for a stopped turn but never calls a model, emits recommendations, or
blocks Codex.  The Remember skill performs the human-readable synthesis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONFIG_NAME = "stop-capture.json"
SEGMENT_DIR = Path(".remember") / "turns" / "codex"
TURN_MARKER = "remember-turn"
MARKER_RE = re.compile(r"<!--\s*remember-turn(?P<body>.*?)-->", re.DOTALL)


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def root_path(value: str | None) -> Path:
    return Path(value or os.getcwd()).resolve()


def memory_ready(root: Path) -> bool:
    return (root / ".remember" / "MEMORY.md").is_file() and (
        root / ".remember" / "memory"
    ).is_dir()


def config_path(root: Path) -> Path:
    return root / ".remember" / CONFIG_NAME


def load_config(root: Path) -> dict[str, Any]:
    path = config_path(root)
    if not path.is_file():
        return {"enabled": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": False}
    return data if isinstance(data, dict) else {"enabled": False}


def atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def segment_key(session_id: str, turn_id: str) -> str:
    return hashlib.sha256(f"{session_id}\0{turn_id}".encode()).hexdigest()[:24]


def marker_fields(text: str) -> dict[str, str]:
    match = MARKER_RE.search(text)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group("body").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


def segment_paths(root: Path) -> list[Path]:
    directory = root / SEGMENT_DIR
    return sorted(directory.glob("*.md")) if directory.is_dir() else []


def capture(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if not memory_ready(root) or not load_config(root).get("enabled"):
        return {"captured": False, "reason": "disabled_or_uninitialized"}
    session_id = str(payload.get("session_id") or "").strip()
    turn_id = str(payload.get("turn_id") or "").strip()
    message = str(payload.get("last_assistant_message") or "").strip()
    if not session_id or not turn_id or not message:
        return {"captured": False, "reason": "missing_stop_fields"}
    key = segment_key(session_id, turn_id)
    directory = root / SEGMENT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{key}.md"
    captured_at = now()
    content = (
        f"<!-- {TURN_MARKER}\n"
        "version: 1\n"
        "platform: codex\n"
        f"session_id: {session_id}\n"
        f"turn_id: {turn_id}\n"
        f"turn_key: {key}\n"
        f"captured_at: {captured_at}\n"
        "-->\n\n"
        f"## Stopped turn {turn_id}\n\n{message}\n"
    )
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError:
        return {"captured": False, "reason": "duplicate", "turn_key": key}
    return {"captured": True, "turn_key": key}


def enable(root: Path) -> dict[str, Any]:
    if not memory_ready(root):
        return {"enabled": False, "error": "memory_not_initialized"}
    atomic_write(
        config_path(root), json.dumps({"version": 1, "enabled": True}, indent=2) + "\n"
    )
    return {"enabled": True}


def disable(root: Path) -> dict[str, Any]:
    if not memory_ready(root):
        return {"enabled": False, "error": "memory_not_initialized"}
    atomic_write(
        config_path(root), json.dumps({"version": 1, "enabled": False}, indent=2) + "\n"
    )
    return {"enabled": False}


def status(root: Path) -> dict[str, Any]:
    segments = segment_paths(root)
    summarized = 0
    for path in segments:
        if marker_fields(path.read_text(encoding="utf-8")).get("summarized_at"):
            summarized += 1
    return {
        "memory_initialized": memory_ready(root),
        "enabled": bool(load_config(root).get("enabled")),
        "segments": len(segments),
        "unsummarized_segments": len(segments) - summarized,
    }


def unsummarized(root: Path) -> list[tuple[Path, dict[str, str]]]:
    found: list[tuple[Path, dict[str, str]]] = []
    for path in segment_paths(root):
        fields = marker_fields(path.read_text(encoding="utf-8"))
        if fields and not fields.get("summarized_at"):
            found.append((path, fields))
    return sorted(
        found, key=lambda item: (item[1].get("captured_at", ""), item[0].name)
    )


def mark_summarized(root: Path, summary_path: str) -> dict[str, Any]:
    if not memory_ready(root):
        return {"error": "memory_not_initialized"}
    if not (root / summary_path).is_file():
        return {"error": "summary_path_missing"}
    items = unsummarized(root)
    stamp = now()
    for path, _ in items:
        text = path.read_text(encoding="utf-8")
        replacement = f"<!-- {TURN_MARKER}" + text.split(f"<!-- {TURN_MARKER}", 1)[1]
        replacement = replacement.replace(
            "-->\n", f"summarized_at: {stamp}\nsummary_path: {summary_path}\n-->\n", 1
        )
        atomic_write(path, replacement)
    return {"marked": len(items), "summarized_at": stamp, "summary_path": summary_path}


def clean(root: Path, apply: bool) -> dict[str, Any]:
    candidates = []
    for path in segment_paths(root):
        fields = marker_fields(path.read_text(encoding="utf-8"))
        summary_path = fields.get("summary_path")
        if (
            fields.get("summarized_at")
            and summary_path
            and (root / summary_path).is_file()
        ):
            candidates.append((path, fields))
    # Keep all segments associated with the newest completed summary checkpoint.
    newest_checkpoint = max(
        (
            (fields.get("summarized_at", ""), fields.get("summary_path", ""))
            for _, fields in candidates
        ),
        default=("", ""),
    )
    removable = [
        path
        for path, fields in candidates
        if (fields.get("summarized_at", ""), fields.get("summary_path", ""))
        != newest_checkpoint
    ]
    if apply:
        for path in removable:
            path.unlink()
    return {
        "apply": apply,
        "kept_checkpoint": newest_checkpoint[0] or None,
        "segments": [str(p) for p in removable],
    }


def hook_main() -> int:
    try:
        payload = json.load(sys.stdin)
        result = capture(root_path(str(payload.get("cwd") or "")), payload)
    except Exception:  # Hooks must never prevent Codex from stopping.
        result = {"captured": False, "reason": "capture_error"}
    print(json.dumps({"continue": True, "suppressOutput": True, "remember": result}))
    return 0


def cli_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("enable", "disable", "status", "mark-summarized", "clean", "capture"),
    )
    parser.add_argument("--root")
    parser.add_argument("--summary-path")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = root_path(args.root)
    if args.command == "capture":
        return hook_main()
    if args.command == "enable":
        result = enable(root)
    elif args.command == "disable":
        result = disable(root)
    elif args.command == "status":
        result = status(root)
    elif args.command == "mark-summarized":
        if not args.summary_path:
            parser.error("mark-summarized requires --summary-path")
        result = mark_summarized(root, args.summary_path)
    else:
        result = clean(root, args.apply)
    print(json.dumps(result, indent=2))
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
