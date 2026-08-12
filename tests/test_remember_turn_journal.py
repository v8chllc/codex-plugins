from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = (
    Path(__file__).parents[1]
    / "plugins"
    / "v8ch"
    / "skills"
    / "remember"
    / "scripts"
    / "turn_journal.py"
)
SPEC = importlib.util.spec_from_file_location("turn_journal", SCRIPT)
assert SPEC and SPEC.loader
turn_journal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(turn_journal)


def memory_root(tmp_path: Path) -> None:
    (tmp_path / ".remember" / "memory").mkdir(parents=True)
    (tmp_path / ".remember" / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")


def payload(turn_id: str = "turn-1") -> dict[str, str]:
    return {
        "session_id": "session-before-clear",
        "turn_id": turn_id,
        "last_assistant_message": "Implemented the requested change.",
    }


def test_capture_is_opt_in_and_idempotent(tmp_path: Path) -> None:
    memory_root(tmp_path)
    assert (
        turn_journal.capture(tmp_path, payload())["reason"]
        == "disabled_or_uninitialized"
    )

    assert turn_journal.enable(tmp_path) == {"enabled": True}
    captured = turn_journal.capture(tmp_path, payload())
    duplicate = turn_journal.capture(tmp_path, payload())

    assert captured["captured"] is True
    assert duplicate == {
        "captured": False,
        "reason": "duplicate",
        "turn_key": captured["turn_key"],
    }
    segment = next((tmp_path / ".remember" / "turns" / "codex").glob("*.md"))
    assert "session_id: session-before-clear" in segment.read_text(encoding="utf-8")


def test_mark_summarized_marks_all_unsummarized_turns_only_after_target_exists(
    tmp_path: Path,
) -> None:
    memory_root(tmp_path)
    turn_journal.enable(tmp_path)
    turn_journal.capture(tmp_path, payload("turn-before-clear"))
    turn_journal.capture(tmp_path, payload("turn-after-clear"))
    summary_path = ".remember/memory/2026-08-11.md"
    assert turn_journal.mark_summarized(tmp_path, summary_path) == {
        "error": "summary_path_missing"
    }
    assert len(turn_journal.unsummarized(tmp_path)) == 2
    (tmp_path / summary_path).write_text("## Session\n", encoding="utf-8")

    result = turn_journal.mark_summarized(tmp_path, summary_path)

    assert result["marked"] == 2
    assert not turn_journal.unsummarized(tmp_path)
    for path in (tmp_path / ".remember" / "turns" / "codex").glob("*.md"):
        assert "summary_path: .remember/memory/2026-08-11.md" in path.read_text(
            encoding="utf-8"
        )


def test_clean_previews_then_keeps_newest_valid_checkpoint(tmp_path: Path) -> None:
    memory_root(tmp_path)
    turn_journal.enable(tmp_path)
    turn_journal.capture(tmp_path, payload("older"))
    old_summary = ".remember/memory/2026-08-10.md"
    (tmp_path / old_summary).write_text("old", encoding="utf-8")
    turn_journal.mark_summarized(tmp_path, old_summary)
    turn_journal.capture(tmp_path, payload("newer"))
    new_summary = ".remember/memory/2026-08-11.md"
    (tmp_path / new_summary).write_text("new", encoding="utf-8")
    turn_journal.mark_summarized(tmp_path, new_summary)

    preview = turn_journal.clean(tmp_path, apply=False)
    applied = turn_journal.clean(tmp_path, apply=True)

    assert len(preview["segments"]) == 1
    assert preview["segments"] == applied["segments"]
    assert len(list((tmp_path / ".remember" / "turns" / "codex").glob("*.md"))) == 1


def test_hook_main_is_quiet_and_always_continues(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    memory_root(tmp_path)
    turn_journal.enable(tmp_path)
    monkeypatch.setattr(
        turn_journal.sys,
        "stdin",
        __import__("io").StringIO(json.dumps({**payload(), "cwd": str(tmp_path)})),
    )

    assert turn_journal.hook_main() == 0

    response = json.loads(capsys.readouterr().out)
    assert response["continue"] is True
    assert response["suppressOutput"] is True
