"""Puts `function/` (the exact directory `gcloud run deploy --source` packages, see
scripts/deploy_function.sh) on sys.path, so tests import `main` and `app.*` the same
way the deployed function does -- no divergence between what's tested and what ships.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "function"))
