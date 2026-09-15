"""Shared paths for the consensus-review test modules."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONSENSUS_REVIEW_DIR = REPO_ROOT / "plugins/v8ch/skills/consensus-review"
SCRIPTS_DIR = CONSENSUS_REVIEW_DIR / "scripts"
FIXTURES_DIR = REPO_ROOT / "tests/fixtures/consensus-review"
