from __future__ import annotations

import sys
from pathlib import Path

# Allow running the unit tests from the repository root without an editable
# install (CI still installs the server package).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
