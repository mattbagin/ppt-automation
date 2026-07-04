"""Make the deck_agent package importable when pytest is run from anywhere.

The package lives one level up from tests/ (next to run.py), so plain
`pytest` works without an editable install or a pyproject.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_DIR = str(Path(__file__).resolve().parent.parent)
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)
