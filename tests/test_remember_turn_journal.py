from __future__ import annotations

import importlib.util
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parents[1]
SCRIPT = (
    REPO_ROOT
    / "plugins"
    / "v8ch"
    / "skills"
    / "remember"
    / "scripts"
    / "turn_journal.py"
)
HOOKS_PATH = REPO_ROOT / "plugins" / "v8ch" / "hooks" / "hooks.json"
PLUGIN_ROOT = REPO_ROOT / "plugins" / "v8ch"
SPEC = importlib.util.spec_from_file_location("turn_journal", SCRIPT)
assert SPEC and SPEC.loader
turn_journal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(turn_journal)

CONTRACT_KEYS = {
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
}


def memory_root(tmp_path: Path) -> None:
    (tmp_path / ".remember" / "memory").mkdir(parents=True)
    (tmp_path / ".remember" / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")


def store(tmp_path: Path) -> Path:
    return tmp_path / ".remember" / "turns"


def stop_payload(
    turn_id: str = "turn-1", session_id: str = "session-1"
) -> dict[str, str]:
    return {
        "hook_event_name": "Stop",
        "session_id": session_id,
        "turn_id": turn_id,
        "last_assistant_message": "Implemented the requested change.",
    }


def session_end_payload(session_id: str = "session-1") -> dict[str, str]:
    return {
        "hook_event_name": "SessionEnd",
        "session_id": session_id,
        "transcript_path": f"/tmp/{session_id}.jsonl",
        "reason": "other",
    }


def write_claude_segment(
    tmp_path: Path,
    key: str = "claude-key-1",
    captured_at: str = "2026-08-12T09:00:00.000001Z",
    **overrides: Any,
) -> Path:
    """Write a contract-conformant segment as if the other toolchain wrote it."""
    record: dict[str, Any] = {
        "version": 3,
        "platform": "claude",
        "kind": "stop",
        "key": key,
        "project_root": str(tmp_path.resolve()),
        "session_id": "claude-session-1",
        "captured_at": captured_at,
        "text": "claude stop text",
        "reason": None,
        "transcript_path": None,
        "summarized_at": None,
        "summary_path": None,
    }
    record.update(overrides)
    directory = store(tmp_path)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record['platform']}-{record['kind']}-{record['key']}.json"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def enable_all(tmp_path: Path) -> None:
    turn_journal.enable(tmp_path, turn_journal.STOP_CAPTURE)
    turn_journal.enable(tmp_path, turn_journal.SESSION_END_CAPTURE)


def test_capture_channels_are_independent(tmp_path: Path) -> None:
    memory_root(tmp_path)
    legacy_config = tmp_path / ".remember" / "stop-capture.json"
    legacy_config.write_text('{"version": 1, "enabled": true}\n', encoding="utf-8")

    assert turn_journal.status(tmp_path, turn_journal.STOP_CAPTURE)["enabled"] is True
    assert (
        turn_journal.status(tmp_path, turn_journal.SESSION_END_CAPTURE)["enabled"]
        is False
    )

    assert turn_journal.enable(tmp_path, turn_journal.SESSION_END_CAPTURE) == {
        "enabled": True,
        "channel": turn_journal.SESSION_END_CAPTURE,
    }
    assert turn_journal.disable(tmp_path, turn_journal.STOP_CAPTURE) == {
        "enabled": False,
        "channel": turn_journal.STOP_CAPTURE,
    }
    assert (
        turn_journal.status(tmp_path, turn_journal.SESSION_END_CAPTURE)["enabled"]
        is True
    )


def test_capture_round_trips_v3_records_into_the_flat_shared_store(
    tmp_path: Path,
) -> None:
    memory_root(tmp_path)
    enable_all(tmp_path)

    stopped = turn_journal.capture(tmp_path, stop_payload())
    ended = turn_journal.capture(tmp_path, session_end_payload())

    assert stopped["captured"] is True
    assert ended["captured"] is True
    assert not [path for path in store(tmp_path).iterdir() if path.is_dir()]
    paths = sorted(store(tmp_path).glob("*.json"))
    assert [path.name for path in paths] == [
        f"codex-session-end-{ended['segment_key']}.json",
        f"codex-stop-{stopped['segment_key']}.json",
    ]

    records = {record["kind"]: record for _, record in turn_journal.segments(tmp_path)}
    for record in records.values():
        assert set(record) == CONTRACT_KEYS
        assert record["version"] == 3
        assert record["platform"] == "codex"
        assert record["project_root"] == str(tmp_path.resolve())
        assert record["session_id"] == "session-1"
        assert turn_journal.TIMESTAMP_RE.match(record["captured_at"])
        assert record["summarized_at"] is None
        assert record["summary_path"] is None
    assert records["stop"]["text"] == "Implemented the requested change."
    assert records["stop"]["reason"] is None
    assert records["session-end"]["text"] == ""
    assert records["session-end"]["reason"] == "other"
    assert records["session-end"]["transcript_path"] == "/tmp/session-1.jsonl"


def test_session_end_capture_accepts_missing_transcript_and_empty_text(
    tmp_path: Path,
) -> None:
    memory_root(tmp_path)
    enable_all(tmp_path)

    result = turn_journal.capture(
        tmp_path,
        {"hook_event_name": "SessionEnd", "session_id": "session-1", "reason": "clear"},
    )

    assert result["captured"] is True
    ((_, record),) = turn_journal.segments(tmp_path)
    assert record["text"] == ""
    assert record["transcript_path"] is None
    assert record["reason"] == "clear"


def test_capture_is_idempotent_through_link_based_duplicate_detection(
    tmp_path: Path,
) -> None:
    memory_root(tmp_path)
    enable_all(tmp_path)
    stopped = turn_journal.capture(tmp_path, stop_payload())
    ended = turn_journal.capture(tmp_path, session_end_payload())

    assert turn_journal.capture(tmp_path, stop_payload()) == {
        "captured": False,
        "reason": "duplicate",
        "segment_key": stopped["segment_key"],
    }
    assert turn_journal.capture(tmp_path, session_end_payload()) == {
        "captured": False,
        "reason": "duplicate",
        "segment_key": ended["segment_key"],
    }
    assert len(list(store(tmp_path).glob("*.json"))) == 2
    assert not list(store(tmp_path).glob(".*.tmp"))


def test_capture_rejects_malformed_or_unrelated_payloads(tmp_path: Path) -> None:
    memory_root(tmp_path)
    enable_all(tmp_path)

    assert turn_journal.capture(tmp_path, {})["reason"] == "unsupported_event"
    assert (
        turn_journal.capture(tmp_path, {"hook_event_name": "Stop"})["reason"]
        == "missing_session_id"
    )
    assert (
        turn_journal.capture(
            tmp_path,
            {"hook_event_name": "Stop", "session_id": "session-1"},
        )["reason"]
        == "missing_stop_fields"
    )
    assert (
        turn_journal.capture(
            tmp_path,
            {"hook_event_name": "SessionEnd", "session_id": "session-1"},
        )["reason"]
        == "missing_session_end_fields"
    )
    assert (
        turn_journal.capture(
            tmp_path,
            {
                "hook_event_name": "Stop",
                "session_id": "session-1",
                "turn_id": "turn-1",
                "last_assistant_message": "Subagent response",
                "agent_id": "agent-1",
            },
        )["reason"]
        == "subagent_event"
    )
    assert not (tmp_path / ".remember" / "turns").exists()


def test_discovery_spans_platforms_and_orders_by_captured_at(tmp_path: Path) -> None:
    memory_root(tmp_path)
    enable_all(tmp_path)
    turn_journal.capture(tmp_path, stop_payload())
    write_claude_segment(tmp_path)

    records = turn_journal.unsummarized_records(tmp_path)

    assert [record["platform"] for record in records] == ["claude", "codex"]
    stamps = [record["captured_at"] for record in records]
    assert stamps == sorted(stamps)

    reported = turn_journal.status(tmp_path)
    assert reported["segments"] == records
    assert reported["counts"]["unsummarized"] == 2
    assert reported["counts"]["by_platform"] == {"claude": 1, "codex": 1}


def test_mark_summarized_stamps_every_platform_only_after_target_exists(
    tmp_path: Path,
) -> None:
    memory_root(tmp_path)
    enable_all(tmp_path)
    turn_journal.capture(tmp_path, stop_payload())
    turn_journal.capture(tmp_path, session_end_payload())
    write_claude_segment(tmp_path)
    summary_path = ".remember/memory/2026-08-12.md"

    assert turn_journal.mark_summarized(tmp_path, summary_path) == {
        "error": "summary_path_missing"
    }
    assert len(turn_journal.unsummarized(tmp_path)) == 3
    (tmp_path / summary_path).write_text("## Session\n", encoding="utf-8")

    result = turn_journal.mark_summarized(tmp_path, summary_path)

    assert result["marked"] == 3
    assert result["by_platform"] == {"claude": 1, "codex": 2}
    assert not turn_journal.unsummarized(tmp_path)
    for _, record in turn_journal.segments(tmp_path):
        assert record["summary_path"] == summary_path
        assert turn_journal.TIMESTAMP_RE.match(record["summarized_at"])

    # A record already carrying a checkpoint is skipped, not re-stamped.
    stamps = {record["summarized_at"] for _, record in turn_journal.segments(tmp_path)}
    assert turn_journal.mark_summarized(tmp_path, summary_path)["marked"] == 0
    assert {
        record["summarized_at"] for _, record in turn_journal.segments(tmp_path)
    } == stamps


def test_mark_summarized_rejects_paths_outside_memory(tmp_path: Path) -> None:
    memory_root(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("not a journal\n", encoding="utf-8")

    assert turn_journal.mark_summarized(tmp_path, "outside.md") == {
        "error": "summary_path_missing"
    }
    assert turn_journal.mark_summarized(tmp_path, str(outside)) == {
        "error": "summary_path_missing"
    }


def test_legacy_v1_and_v2_files_are_skipped_and_never_touched(tmp_path: Path) -> None:
    memory_root(tmp_path)
    enable_all(tmp_path)
    store(tmp_path).mkdir(parents=True, exist_ok=True)
    v1 = store(tmp_path) / "stop-deadbeef.json"
    v1.write_text(
        json.dumps(
            {
                "version": 1,
                "kind": "stop",
                "idempotency_key": "deadbeef",
                "project_root": str(tmp_path.resolve()),
                "session_id": "legacy",
                "captured_at": "2026-08-12T14:39:31+00:00",
                "last_assistant_message": "legacy v1",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    v2 = store(tmp_path) / "legacy-v2.md"
    v2.write_text(
        "<!-- remember-turn\nversion: 2\nplatform: codex\nchannel: stop-capture\n"
        "event: Stop\nsession_id: legacy\nturn_id: t\nsegment_key: k\n"
        "captured_at: 2026-08-12T14:39:31Z\n-->\n\nlegacy v2\n",
        encoding="utf-8",
    )
    before = (v1.read_bytes(), v2.read_bytes())
    turn_journal.capture(tmp_path, stop_payload())
    summary_path = ".remember/memory/2026-08-12.md"
    (tmp_path / summary_path).write_text("## Session\n", encoding="utf-8")

    records = turn_journal.unsummarized_records(tmp_path)
    assert [record["key"] for record in records] != ["deadbeef"]
    assert len(records) == 1

    assert turn_journal.mark_summarized(tmp_path, summary_path)["marked"] == 1
    turn_journal.clean(tmp_path, apply=True)

    assert v1.exists() and v2.exists()
    assert (v1.read_bytes(), v2.read_bytes()) == before


def test_half_written_summary_checkpoint_is_rejected(tmp_path: Path) -> None:
    memory_root(tmp_path)
    (tmp_path / ".remember" / "memory" / "2026-08-12.md").write_text(
        "## Session\n", encoding="utf-8"
    )
    stamped_only = write_claude_segment(
        tmp_path,
        key="half-stamp",
        summarized_at="2026-08-12T14:39:31.123456Z",
    )
    path_only = write_claude_segment(
        tmp_path,
        key="half-path",
        captured_at="2026-08-12T09:00:00.000002Z",
        summary_path=".remember/memory/2026-08-12.md",
    )
    good = write_claude_segment(
        tmp_path, key="good", captured_at="2026-08-12T09:00:00.000003Z"
    )

    records = turn_journal.unsummarized_records(tmp_path)

    assert [record["key"] for record in records] == ["good"]
    before = (stamped_only.read_bytes(), path_only.read_bytes())
    turn_journal.mark_summarized(tmp_path, ".remember/memory/2026-08-12.md")
    assert (stamped_only.read_bytes(), path_only.read_bytes()) == before
    assert good.exists()


def test_clean_previews_and_removes_only_older_summarized_segments(
    tmp_path: Path,
) -> None:
    memory_root(tmp_path)
    enable_all(tmp_path)
    turn_journal.capture(tmp_path, stop_payload("older", "old-session"))
    write_claude_segment(tmp_path, key="older-claude")
    old_summary = ".remember/memory/2026-08-11.md"
    (tmp_path / old_summary).write_text("old", encoding="utf-8")
    turn_journal.mark_summarized(tmp_path, old_summary)
    turn_journal.capture(tmp_path, stop_payload("newer", "new-session"))
    turn_journal.capture(tmp_path, session_end_payload("new-session"))
    new_summary = ".remember/memory/2026-08-12.md"
    (tmp_path / new_summary).write_text("new", encoding="utf-8")
    turn_journal.mark_summarized(tmp_path, new_summary)
    malformed = store(tmp_path) / "codex-stop-malformed.json"
    malformed.write_text('{"version": 3}\n', encoding="utf-8")

    preview = turn_journal.clean(tmp_path, apply=False)
    applied = turn_journal.clean(tmp_path, apply=True)

    # Both older segments retire together regardless of platform.
    assert len(preview["segments"]) == 2
    assert preview["segments"] == applied["segments"]
    assert malformed.exists()
    assert len(list(store(tmp_path).glob("*.json"))) == 3


def test_hook_main_is_silent_and_always_succeeds(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    memory_root(tmp_path)
    turn_journal.enable(tmp_path, turn_journal.STOP_CAPTURE)
    monkeypatch.setattr(
        turn_journal.sys,
        "stdin",
        __import__("io").StringIO(json.dumps({**stop_payload(), "cwd": str(tmp_path)})),
    )

    assert turn_journal.hook_main() == 0
    assert capsys.readouterr().out == ""
    assert len(list(store(tmp_path).glob("*.json"))) == 1

    monkeypatch.setattr(turn_journal.sys, "stdin", __import__("io").StringIO("{"))
    assert turn_journal.hook_main() == 0
    assert capsys.readouterr().out == ""


def test_hook_main_fails_open_when_the_store_is_unwritable(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    memory_root(tmp_path)
    turn_journal.enable(tmp_path, turn_journal.STOP_CAPTURE)

    def explode(*args: object, **kwargs: object) -> None:
        raise OSError("read-only store")

    monkeypatch.setattr(turn_journal, "_write_segment", explode)
    monkeypatch.setattr(
        turn_journal.sys,
        "stdin",
        __import__("io").StringIO(json.dumps({**stop_payload(), "cwd": str(tmp_path)})),
    )

    assert turn_journal.hook_main() == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_cli_unsummarized_emits_a_json_list_of_segments(tmp_path: Path) -> None:
    memory_root(tmp_path)
    enable_all(tmp_path)
    turn_journal.capture(tmp_path, stop_payload())
    write_claude_segment(tmp_path)

    result = subprocess.run(
        ["python3", str(SCRIPT), "unsummarized", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert [record["platform"] for record in payload] == ["claude", "codex"]
    assert all(set(record) == CONTRACT_KEYS for record in payload)


def test_packaged_commands_resolve_plugin_root_and_exit_zero(tmp_path: Path) -> None:
    memory_root(tmp_path)
    enable_all(tmp_path)
    hooks = json.loads(HOOKS_PATH.read_text(encoding="utf-8"))["hooks"]
    payloads = {
        "Stop": {**stop_payload(), "cwd": str(tmp_path)},
        "SessionEnd": {**session_end_payload(), "cwd": str(tmp_path)},
    }

    for event_name, payload_data in payloads.items():
        handler = hooks[event_name][0]["hooks"][0]
        assert "${PLUGIN_ROOT}" in handler["command"]
        command = handler["command"].replace("${PLUGIN_ROOT}", str(PLUGIN_ROOT))
        result = subprocess.run(
            shlex.split(command),
            input=json.dumps(payload_data),
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert result.stdout == ""
        assert result.stderr == ""

    assert len(list(store(tmp_path).glob("*.json"))) == 2
