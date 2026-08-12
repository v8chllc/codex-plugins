from __future__ import annotations

import importlib.util
import json
import shlex
import subprocess
from pathlib import Path

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


def memory_root(tmp_path: Path) -> None:
    (tmp_path / ".remember" / "memory").mkdir(parents=True)
    (tmp_path / ".remember" / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")


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


def test_capture_channels_are_independent_and_migrate_existing_stop_state(
    tmp_path: Path,
) -> None:
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


def test_stop_and_session_end_capture_are_opt_in_distinct_and_idempotent(
    tmp_path: Path,
) -> None:
    memory_root(tmp_path)
    assert turn_journal.capture(tmp_path, stop_payload())["reason"] == (
        "disabled_or_uninitialized"
    )
    assert turn_journal.capture(tmp_path, session_end_payload())["reason"] == (
        "disabled_or_uninitialized"
    )

    turn_journal.enable(tmp_path, turn_journal.STOP_CAPTURE)
    turn_journal.enable(tmp_path, turn_journal.SESSION_END_CAPTURE)
    stopped = turn_journal.capture(tmp_path, stop_payload())
    ended = turn_journal.capture(tmp_path, session_end_payload())
    duplicate_stop = turn_journal.capture(tmp_path, stop_payload())
    duplicate_end = turn_journal.capture(tmp_path, session_end_payload())

    assert stopped["captured"] is True
    assert ended["captured"] is True
    assert stopped["segment_key"] != ended["segment_key"]
    assert duplicate_stop == {
        "captured": False,
        "reason": "duplicate",
        "segment_key": stopped["segment_key"],
    }
    assert duplicate_end == {
        "captured": False,
        "reason": "duplicate",
        "segment_key": ended["segment_key"],
    }

    segments = list((tmp_path / ".remember" / "turns" / "codex").glob("*.md"))
    assert len(segments) == 2
    text = "\n".join(path.read_text(encoding="utf-8") for path in segments)
    assert "event: Stop" in text
    assert "event: SessionEnd" in text
    assert "channel: stop-capture" in text
    assert "channel: session-end-capture" in text
    assert "Transcript: `/tmp/session-1.jsonl`" in text


def test_capture_rejects_malformed_or_unrelated_payloads(tmp_path: Path) -> None:
    memory_root(tmp_path)
    turn_journal.enable(tmp_path, turn_journal.STOP_CAPTURE)
    turn_journal.enable(tmp_path, turn_journal.SESSION_END_CAPTURE)

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


def test_mark_summarized_supports_both_channels_only_after_target_exists(
    tmp_path: Path,
) -> None:
    memory_root(tmp_path)
    turn_journal.enable(tmp_path, turn_journal.STOP_CAPTURE)
    turn_journal.enable(tmp_path, turn_journal.SESSION_END_CAPTURE)
    turn_journal.capture(tmp_path, stop_payload())
    turn_journal.capture(tmp_path, session_end_payload())
    summary_path = ".remember/memory/2026-08-12.md"
    assert turn_journal.mark_summarized(tmp_path, summary_path) == {
        "error": "summary_path_missing"
    }
    assert len(turn_journal.unsummarized(tmp_path)) == 2
    (tmp_path / summary_path).write_text("## Session\n", encoding="utf-8")

    result = turn_journal.mark_summarized(tmp_path, summary_path)

    assert result["marked"] == 2
    assert not turn_journal.unsummarized(tmp_path)
    for path in (tmp_path / ".remember" / "turns" / "codex").glob("*.md"):
        assert "summary_path: .remember/memory/2026-08-12.md" in path.read_text(
            encoding="utf-8"
        )


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


def test_clean_previews_and_removes_only_older_valid_summarized_segments(
    tmp_path: Path,
) -> None:
    memory_root(tmp_path)
    turn_journal.enable(tmp_path, turn_journal.STOP_CAPTURE)
    turn_journal.enable(tmp_path, turn_journal.SESSION_END_CAPTURE)
    turn_journal.capture(tmp_path, stop_payload("older", "old-session"))
    turn_journal.capture(tmp_path, session_end_payload("old-session"))
    old_summary = ".remember/memory/2026-08-11.md"
    (tmp_path / old_summary).write_text("old", encoding="utf-8")
    turn_journal.mark_summarized(tmp_path, old_summary)
    turn_journal.capture(tmp_path, stop_payload("newer", "new-session"))
    turn_journal.capture(tmp_path, session_end_payload("new-session"))
    new_summary = ".remember/memory/2026-08-12.md"
    (tmp_path / new_summary).write_text("new", encoding="utf-8")
    turn_journal.mark_summarized(tmp_path, new_summary)
    malformed = tmp_path / ".remember" / "turns" / "codex" / "malformed.md"
    malformed.write_text("<!-- remember-turn\nversion: 2\n-->\n", encoding="utf-8")

    preview = turn_journal.clean(tmp_path, apply=False)
    applied = turn_journal.clean(tmp_path, apply=True)

    assert len(preview["segments"]) == 2
    assert preview["segments"] == applied["segments"]
    assert malformed.exists()
    assert len(list((tmp_path / ".remember" / "turns" / "codex").glob("*.md"))) == 3


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

    monkeypatch.setattr(turn_journal.sys, "stdin", __import__("io").StringIO("{"))
    assert turn_journal.hook_main() == 0
    assert capsys.readouterr().out == ""


def test_packaged_commands_resolve_plugin_root_and_exit_zero(tmp_path: Path) -> None:
    memory_root(tmp_path)
    turn_journal.enable(tmp_path, turn_journal.STOP_CAPTURE)
    turn_journal.enable(tmp_path, turn_journal.SESSION_END_CAPTURE)
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
