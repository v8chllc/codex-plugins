"""Shared test configuration.

The consensus-review scripts are a flat module directory rather than a package,
matching how Codex runs them: ``uv run <skill-dir>/scripts/<name>.py`` puts that
directory on ``sys.path``. Reproduce that here, before any test module imports
them, so the tests exercise the same import graph the skill does.
"""

import sys

from tests.consensus_review_support import SCRIPTS_DIR

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
