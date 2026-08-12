#!/usr/bin/env python3
"""Maintain opt-in, project-local Codex lifecycle journal segments.

The hook path is deliberately deterministic: it persists immutable Stop and
SessionEnd records but never calls a model, emits recommendations, or blocks
Codex. The Remember skill performs the human-readable synthesis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

STOP_CAPTURE = "stop-capture"
SESSION_END_CAPTURE = "session-end-capture"
CAPTURE_CHANNELS = (STOP_CAPTURE, SESSION_END_CAPTURE)
CONFIG_NAMES = {
    STOP_CAPTURE: "stop-capture.json",
    SESSION_END_CAPTURE: "session-end-capture.json",
}
EVENT_CHANNELS = {"Stop": STOP_CAPTURE, "SessionEnd": SESSION_END_CAPTURE}
SEGMENT_DIR = Path(".remember") / "turns" / "codex"
TURN_MARKER = "remember-turn"
MARKER_RE = re.compile(r"<!--\s*remember-turn(?P<body>.*?)-->", re.DOTALL)


def now() -> str:
    return (
        datetime.now(timezone.utc)  # noqa: UP017 - packaged python3 may be 3.9
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def root_path(value: Optional[str]) -> Path:  # noqa: UP045 - support Python 3.9
    return Path(value or os.getcwd()).resolve()


def memory_ready(root: Path) -> bool:
    return (root / ".remember" / "MEMORY.md").is_file() and (
        root / ".remember" / "memory"
    ).is_dir()


def config_path(root: Path, channel: str = STOP_CAPTURE) -> Path:
    return root / ".remember" / CONFIG_NAMES[channel]


def load_config(root: Path, channel: str = STOP_CAPTURE) -> dict[str, Any]:
    path = config_path(root, channel)
    if not path.is_file():
        return {"enabled": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": False}
    return data if isinstance(data, dict) else {"enabled": False}


def atomic_write(path: Path, content: str) -> None:
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def summary_target(root: Path, value: str) -> Optional[Path]:  # noqa: UP045
    path = Path(value)
    if path.is_absolute():
        return None
    target = (root / path).resolve()
    memory = (root / ".remember" / "memory").resolve()
    if target.parent != memory or not target.is_file():
        return None
    return target


def segment_key(session_id: str, event_name: str, event_id: str) -> str:
    value = f"{session_id}\0{event_name}\0{event_id}"
    return hashlib.sha256(value.encode()).hexdigest()[:24]


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


def segment_channel(
    fields: dict[str, str],
) -> Optional[str]:  # noqa: UP045 - support Python 3.9
    channel = fields.get("channel")
    if channel in CAPTURE_CHANNELS:
        return channel
    if fields.get("version") == "1" and fields.get("turn_key"):
        return STOP_CAPTURE
    return None


def valid_segment_fields(fields: dict[str, str]) -> bool:
    common = ("version", "platform", "session_id", "captured_at")
    if not all(fields.get(field) for field in common):
        return False
    if fields.get("platform") != "codex":
        return False
    if fields.get("version") == "1":
        return all(fields.get(field) for field in ("turn_id", "turn_key"))
    event_name = fields.get("event")
    channel = segment_channel(fields)
    if event_name not in EVENT_CHANNELS or channel != EVENT_CHANNELS[event_name]:
        return False
    if not fields.get("segment_key"):
        return False
    if event_name == "Stop":
        return bool(fields.get("turn_id"))
    return bool(fields.get("transcript_path") and fields.get("reason"))


def _capture_stop(
    root: Path, payload: dict[str, Any], session_id: str
) -> dict[str, Any]:
    turn_id = str(payload.get("turn_id") or "").strip()
    message = str(payload.get("last_assistant_message") or "").strip()
    if not turn_id or not message:
        return {"captured": False, "reason": "missing_stop_fields"}
    key = segment_key(session_id, "Stop", turn_id)
    marker = f"session_id: {session_id}\nturn_id: {turn_id}\nsegment_key: {key}\n"
    body = f"## Stopped turn {turn_id}\n\n{message}\n"
    return _write_segment(root, STOP_CAPTURE, "Stop", key, marker, body)


def _capture_session_end(
    root: Path, payload: dict[str, Any], session_id: str
) -> dict[str, Any]:
    transcript_path = str(payload.get("transcript_path") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    if not transcript_path or not reason:
        return {"captured": False, "reason": "missing_session_end_fields"}
    key = segment_key(session_id, "SessionEnd", reason)
    marker = (
        f"session_id: {session_id}\n"
        f"transcript_path: {transcript_path}\n"
        f"reason: {reason}\n"
        f"segment_key: {key}\n"
    )
    body = (
        f"## Ended session {session_id}\n\n"
        f"Reason: {reason}\n\n"
        f"Transcript: `{transcript_path}`\n"
    )
    return _write_segment(root, SESSION_END_CAPTURE, "SessionEnd", key, marker, body)


def _write_segment(
    root: Path,
    channel: str,
    event_name: str,
    key: str,
    marker: str,
    body: str,
) -> dict[str, Any]:
    directory = root / SEGMENT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{key}.md"
    content = (
        f"<!-- {TURN_MARKER}\n"
        "version: 2\n"
        "platform: codex\n"
        f"channel: {channel}\n"
        f"event: {event_name}\n"
        f"{marker}"
        f"captured_at: {now()}\n"
        "-->\n\n"
        f"{body}"
    )
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=directory,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError:
        return {"captured": False, "reason": "duplicate", "segment_key": key}
    finally:
        temporary.unlink(missing_ok=True)
    return {"captured": True, "segment_key": key, "channel": channel}


def capture(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("agent_id"):
        return {"captured": False, "reason": "subagent_event"}
    event_name = str(payload.get("hook_event_name") or "").strip()
    channel = EVENT_CHANNELS.get(event_name)
    if not channel:
        return {"captured": False, "reason": "unsupported_event"}
    if not memory_ready(root) or not load_config(root, channel).get("enabled"):
        return {
            "captured": False,
            "reason": "disabled_or_uninitialized",
            "channel": channel,
        }
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return {"captured": False, "reason": "missing_session_id"}
    if event_name == "Stop":
        return _capture_stop(root, payload, session_id)
    return _capture_session_end(root, payload, session_id)


def set_enabled(root: Path, channel: str, enabled: bool) -> dict[str, Any]:
    if not memory_ready(root):
        return {"enabled": False, "channel": channel, "error": "memory_not_initialized"}
    atomic_write(
        config_path(root, channel),
        json.dumps({"version": 1, "enabled": enabled}, indent=2) + "\n",
    )
    return {"enabled": enabled, "channel": channel}


def enable(root: Path, channel: str = STOP_CAPTURE) -> dict[str, Any]:
    return set_enabled(root, channel, True)


def disable(root: Path, channel: str = STOP_CAPTURE) -> dict[str, Any]:
    return set_enabled(root, channel, False)


def status(root: Path, channel: str = STOP_CAPTURE) -> dict[str, Any]:
    segments = []
    summarized = 0
    for path in segment_paths(root):
        fields = marker_fields(path.read_text(encoding="utf-8"))
        if valid_segment_fields(fields) and segment_channel(fields) == channel:
            segments.append(path)
            if fields.get("summarized_at"):
                summarized += 1
    return {
        "memory_initialized": memory_ready(root),
        "channel": channel,
        "enabled": bool(load_config(root, channel).get("enabled")),
        "segments": len(segments),
        "unsummarized_segments": len(segments) - summarized,
    }


def unsummarized(root: Path) -> list[tuple[Path, dict[str, str]]]:
    found: list[tuple[Path, dict[str, str]]] = []
    for path in segment_paths(root):
        fields = marker_fields(path.read_text(encoding="utf-8"))
        if valid_segment_fields(fields) and not fields.get("summarized_at"):
            found.append((path, fields))
    return sorted(
        found, key=lambda item: (item[1].get("captured_at", ""), item[0].name)
    )


def mark_summarized(root: Path, summary_path: str) -> dict[str, Any]:
    if not memory_ready(root):
        return {"error": "memory_not_initialized"}
    if summary_target(root, summary_path) is None:
        return {"error": "summary_path_missing"}
    items = unsummarized(root)
    stamp = now()
    for path, _ in items:
        text = path.read_text(encoding="utf-8")
        replacement = text.replace(
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
            valid_segment_fields(fields)
            and fields.get("summarized_at")
            and summary_path
            and summary_target(root, summary_path) is not None
        ):
            candidates.append((path, fields))
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
        "segments": [str(path) for path in removable],
    }


def hook_main() -> int:
    try:
        payload = json.load(sys.stdin)
        if isinstance(payload, dict):
            capture(root_path(str(payload.get("cwd") or "")), payload)
    except Exception:
        pass  # Lifecycle capture must never interfere with Codex.
    return 0


def cli_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("enable", "disable", "status", "mark-summarized", "clean", "capture"),
    )
    parser.add_argument("channel", nargs="?", choices=CAPTURE_CHANNELS)
    parser.add_argument("--root")
    parser.add_argument("--summary-path")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = root_path(args.root)
    if args.command == "capture":
        return hook_main()
    channel = args.channel or STOP_CAPTURE
    if args.command == "enable":
        result = enable(root, channel)
    elif args.command == "disable":
        result = disable(root, channel)
    elif args.command == "status":
        result = status(root, channel)
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
