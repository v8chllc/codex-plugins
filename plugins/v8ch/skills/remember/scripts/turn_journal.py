#!/usr/bin/env python3
"""Maintain opt-in, project-local lifecycle journal segments.

Segments live in one shared, non-recursive store at `.remember/turns/` and use
the `version: 3` JSON record format. Every toolchain writes its own `platform`
value and reads all of them, so a single synthesis run covers everything
captured in the workspace.

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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STOP_CAPTURE = "stop-capture"
SESSION_END_CAPTURE = "session-end-capture"
CAPTURE_CHANNELS = (STOP_CAPTURE, SESSION_END_CAPTURE)
CONFIG_NAMES = {
    STOP_CAPTURE: "stop-capture.json",
    SESSION_END_CAPTURE: "session-end-capture.json",
}
EVENT_CHANNELS = {"Stop": STOP_CAPTURE, "SessionEnd": SESSION_END_CAPTURE}

SEGMENT_DIR = Path(".remember") / "turns"
SEGMENT_VERSION = 3
PLATFORM = "codex"
PLATFORMS = ("claude", "codex")
KIND_STOP = "stop"
KIND_SESSION_END = "session-end"
KINDS = (KIND_STOP, KIND_SESSION_END)

SEGMENT_FIELDS = (
    "version",
    "platform",
    "kind",
    "key",
    "project_root",
    "session_id",
    "captured_at",
    "text",
    "reason",
    "transcript_path",
    "summarized_at",
    "summary_path",
)
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def root_path(value: str | None) -> Path:
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


def summary_target(root: Path, value: str) -> Path | None:
    path = Path(value)
    if path.is_absolute():
        return None
    target = (root / path).resolve()
    memory = (root / ".remember" / "memory").resolve()
    if target.parent != memory or not target.is_file():
        return None
    return target


def summary_path_in_memory(root: Path, value: str) -> bool:
    """Contract check: relative and resolving inside `.remember/memory/`."""
    path = Path(value)
    if path.is_absolute():
        return False
    target = (root / path).resolve()
    memory = (root / ".remember" / "memory").resolve()
    return target.parent == memory


def segment_key(session_id: str, event_name: str, event_id: str) -> str:
    value = f"{session_id}\0{event_name}\0{event_id}"
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def segment_name(platform: str, kind: str, key: str) -> str:
    return f"{platform}-{kind}-{key}.json"


def segment_paths(root: Path) -> list[Path]:
    directory = root / SEGMENT_DIR
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.json") if path.is_file())


def valid_segment(root: Path, path: Path, record: Any) -> bool:
    """Return True when `record` satisfies the v3 contract for this store.

    Anything else - including v1 JSON and v2 Markdown leftovers - is malformed
    and must be skipped rather than repaired, stamped, or deleted.
    """
    if not isinstance(record, dict) or set(record) != set(SEGMENT_FIELDS):
        return False
    if record["version"] != SEGMENT_VERSION or isinstance(record["version"], bool):
        return False
    platform, kind, key = record["platform"], record["kind"], record["key"]
    if platform not in PLATFORMS or kind not in KINDS:
        return False
    if not isinstance(key, str) or not key:
        return False
    if path.name != segment_name(platform, kind, key):
        return False
    if not isinstance(record["project_root"], str) or not record["project_root"]:
        return False
    if Path(record["project_root"]).resolve() != root.resolve():
        return False
    session_id = record["session_id"]
    if not isinstance(session_id, str) or not session_id:
        return False
    captured_at = record["captured_at"]
    if not isinstance(captured_at, str) or not TIMESTAMP_RE.match(captured_at):
        return False
    if not isinstance(record["text"], str):
        return False
    reason = record["reason"]
    if kind == KIND_STOP:
        if reason is not None:
            return False
    elif not isinstance(reason, str) or not reason:
        return False
    transcript_path = record["transcript_path"]
    if transcript_path is not None and not isinstance(transcript_path, str):
        return False
    stamped, summary = record["summarized_at"], record["summary_path"]
    if stamped is None and summary is None:
        return True
    if not isinstance(stamped, str) or not stamped:
        return False
    if not isinstance(summary, str) or not summary:
        return False
    if not TIMESTAMP_RE.match(stamped):
        return False
    return summary_path_in_memory(root, summary)


def read_segment(root: Path, path: Path) -> dict[str, Any] | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not valid_segment(root, path, record):
        return None
    return dict(record)


def segments(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Every valid v3 segment in the shared store, ascending by captured_at."""
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in segment_paths(root):
        record = read_segment(root, path)
        if record is not None:
            found.append((path, record))
    return sorted(found, key=lambda item: (item[1]["captured_at"], item[0].name))


def unsummarized(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return [item for item in segments(root) if item[1]["summarized_at"] is None]


def unsummarized_records(root: Path) -> list[dict[str, Any]]:
    return [record for _, record in unsummarized(root)]


def platform_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = dict.fromkeys(PLATFORMS, 0)
    for record in records:
        counts[record["platform"]] = counts.get(record["platform"], 0) + 1
    return counts


def _write_segment(
    root: Path,
    kind: str,
    key: str,
    session_id: str,
    text: str,
    reason: str | None,
    transcript_path: str | None,
) -> dict[str, Any]:
    directory = root / SEGMENT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / segment_name(PLATFORM, kind, key)
    record = {
        "version": SEGMENT_VERSION,
        "platform": PLATFORM,
        "kind": kind,
        "key": key,
        "project_root": str(root.resolve()),
        "session_id": session_id,
        "captured_at": now(),
        "text": text,
        "reason": reason,
        "transcript_path": transcript_path,
        "summarized_at": None,
        "summary_path": None,
    }
    content = json.dumps(record, indent=2) + "\n"
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
    return {"captured": True, "segment_key": key, "channel": kind_channel(kind)}


def kind_channel(kind: str) -> str:
    return STOP_CAPTURE if kind == KIND_STOP else SESSION_END_CAPTURE


def _capture_stop(
    root: Path, payload: dict[str, Any], session_id: str
) -> dict[str, Any]:
    turn_id = str(payload.get("turn_id") or "").strip()
    message = str(payload.get("last_assistant_message") or "").strip()
    if not turn_id or not message:
        return {"captured": False, "reason": "missing_stop_fields"}
    transcript_path = str(payload.get("transcript_path") or "").strip() or None
    return _write_segment(
        root,
        KIND_STOP,
        segment_key(session_id, "Stop", turn_id),
        session_id,
        message,
        None,
        transcript_path,
    )


def _capture_session_end(
    root: Path, payload: dict[str, Any], session_id: str
) -> dict[str, Any]:
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        return {"captured": False, "reason": "missing_session_end_fields"}
    transcript_path = str(payload.get("transcript_path") or "").strip() or None
    return _write_segment(
        root,
        KIND_SESSION_END,
        segment_key(session_id, "SessionEnd", reason),
        session_id,
        "",
        reason,
        transcript_path,
    )


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
    known = segments(root)
    pending = [record for _, record in known if record["summarized_at"] is None]
    return {
        "memory_initialized": memory_ready(root),
        "channel": channel,
        "enabled": bool(load_config(root, channel).get("enabled")),
        "counts": {
            "total": len(known),
            "summarized": len(known) - len(pending),
            "unsummarized": len(pending),
            "by_platform": platform_counts([record for _, record in known]),
            "unsummarized_by_platform": platform_counts(pending),
        },
        "segments": pending,
    }


def mark_summarized(root: Path, summary_path: str) -> dict[str, Any]:
    if not memory_ready(root):
        return {"error": "memory_not_initialized"}
    if summary_target(root, summary_path) is None:
        return {"error": "summary_path_missing"}
    items = unsummarized(root)
    stamp = now()
    for path, record in items:
        record["summarized_at"] = stamp
        record["summary_path"] = summary_path
        atomic_write(path, json.dumps(record, indent=2) + "\n")
    return {
        "marked": len(items),
        "summarized_at": stamp,
        "summary_path": summary_path,
        "by_platform": platform_counts([record for _, record in items]),
    }


def clean(root: Path, apply: bool) -> dict[str, Any]:
    candidates = [
        (path, record)
        for path, record in segments(root)
        if record["summarized_at"]
        and record["summary_path"]
        and summary_target(root, record["summary_path"]) is not None
    ]
    newest_checkpoint = max(
        ((record["summarized_at"], record["summary_path"]) for _, record in candidates),
        default=("", ""),
    )
    removable = [
        path
        for path, record in candidates
        if (record["summarized_at"], record["summary_path"]) != newest_checkpoint
    ]
    if apply:
        for path in removable:
            path.unlink()
    return {
        "apply": apply,
        "kept_checkpoint": newest_checkpoint[0] or None,
        "segments": [str(path) for path in removable],
    }


def hook_main(root: Path | None = None) -> int:
    try:
        payload = json.load(sys.stdin)
        if isinstance(payload, dict):
            target = (
                root if root is not None else root_path(str(payload.get("cwd") or ""))
            )
            capture(target, payload)
    except Exception:
        pass  # Lifecycle capture must never interfere with Codex.
    return 0


def cli_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "enable",
            "disable",
            "status",
            "unsummarized",
            "mark-summarized",
            "clean",
            "capture",
        ),
    )
    parser.add_argument("channel", nargs="?", choices=CAPTURE_CHANNELS)
    parser.add_argument("--root")
    parser.add_argument("--summary-path")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = root_path(args.root)
    if args.command == "capture":
        return hook_main(root if args.root else None)
    channel = args.channel or STOP_CAPTURE
    result: Any
    if args.command == "enable":
        result = enable(root, channel)
    elif args.command == "disable":
        result = disable(root, channel)
    elif args.command == "status":
        result = status(root, channel)
    elif args.command == "unsummarized":
        result = unsummarized_records(root)
    elif args.command == "mark-summarized":
        if not args.summary_path:
            parser.error("mark-summarized requires --summary-path")
        result = mark_summarized(root, args.summary_path)
    else:
        result = clean(root, args.apply)
    print(json.dumps(result, indent=2))
    return 1 if isinstance(result, dict) and result.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
