"""Cross-repository parity guard for the shared consensus-review surface.

The Claude and Codex copies of this skill must post and recover identical
comments, so their scripts, templates, and fixtures are byte-identical apart from
each script's module docstring. The manifest pins a hash per path and is itself
byte-identical in both repositories, so drift fails here rather than at review
time on a PR.

Regenerate after an intended change:

    uv run --with pytest python -m tests.test_parity_manifest --write
"""

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

from tests.consensus_review_support import CONSENSUS_REVIEW_DIR, FIXTURES_DIR, REPO_ROOT

MANIFEST_PATH = FIXTURES_DIR / "parity-manifest.json"
MANIFEST_VERSION = 1


def covered_paths() -> list[Path]:
    """Return the shared-surface files, sorted by repository-relative path."""
    paths = [
        *(CONSENSUS_REVIEW_DIR / "scripts").glob("*.py"),
        *(CONSENSUS_REVIEW_DIR / "templates").glob("*.tmpl"),
        *(path for path in FIXTURES_DIR.glob("*") if path != MANIFEST_PATH),
    ]
    return sorted(paths, key=manifest_key)


def strip_module_docstring(source: str) -> str:
    """Return Python source with its module docstring removed.

    The two copies describe themselves differently; everything below the
    docstring must match byte for byte.
    """
    module = ast.parse(source)
    body = module.body
    if not body:
        return source
    first = body[0]
    if not (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return source
    lines = source.splitlines(keepends=True)
    assert first.end_lineno is not None
    del lines[first.lineno - 1 : first.end_lineno]
    return "".join(lines)


def normalized_bytes(path: Path) -> bytes:
    """Return the comparable content of a covered file."""
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        raw = strip_module_docstring(raw)
    return raw.encode("utf-8")


def manifest_key(path: Path) -> str:
    """Return the repository-relative key a path takes in the manifest."""
    return path.relative_to(REPO_ROOT).as_posix()


def manifest_hash(path: Path) -> str:
    """Return the sha256 of a covered file's comparable content."""
    return hashlib.sha256(normalized_bytes(path)).hexdigest()


def compute_manifest() -> dict[str, object]:
    """Build the manifest from the working tree."""
    return {
        "version": MANIFEST_VERSION,
        "files": {manifest_key(path): manifest_hash(path) for path in covered_paths()},
    }


def load_manifest() -> dict[str, object]:
    manifest: dict[str, object] = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return manifest


def write_manifest() -> None:
    MANIFEST_PATH.write_text(
        json.dumps(compute_manifest(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_manifest_exists_and_is_current() -> None:
    assert MANIFEST_PATH.exists(), (
        "parity manifest is missing; regenerate with "
        "`uv run --with pytest python -m tests.test_parity_manifest --write`"
    )
    assert load_manifest() == compute_manifest(), (
        "shared consensus-review surface drifted from the parity manifest; "
        "apply the same change to the sibling repository, then regenerate with "
        "`uv run --with pytest python -m tests.test_parity_manifest --write`"
    )


def test_manifest_covers_every_shared_file() -> None:
    manifest = load_manifest()
    files = manifest["files"]
    assert isinstance(files, dict)
    expected = {manifest_key(path) for path in covered_paths()}
    assert set(files) == expected
    for name in ("post_review_comment.py", "recover_context.py", "review_contract.py"):
        assert any(path.endswith(name) for path in files)
    assert any(path.endswith("review-comment.md.tmpl") for path in files)


def test_manifest_paths_are_identical_in_both_repositories() -> None:
    manifest = load_manifest()
    files = manifest["files"]
    assert isinstance(files, dict)
    for path in files:
        assert not path.startswith("/")
        assert "claude" not in path and "codex" not in path


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('"""Doc."""\nimport os\n', "import os\n"),
        ('"""Line one.\n\nLine two.\n"""\nimport os\n', "import os\n"),
        ("import os\n", "import os\n"),
        ("", ""),
    ],
)
def test_strip_module_docstring(source: str, expected: str) -> None:
    assert strip_module_docstring(source) == expected


def test_normalization_ignores_only_the_module_docstring() -> None:
    script = CONSENSUS_REVIEW_DIR / "scripts/review_contract.py"
    stripped = strip_module_docstring(script.read_text(encoding="utf-8"))
    assert "Executable consensus-review scoring contract" not in stripped
    assert "DEDUCTIONS: dict[str, int]" in stripped


if __name__ == "__main__":
    if "--write" in sys.argv:
        write_manifest()
        print(f"wrote {MANIFEST_PATH.relative_to(REPO_ROOT)}")
    else:
        print(__doc__)
