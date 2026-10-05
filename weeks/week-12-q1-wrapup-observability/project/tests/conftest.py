import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))            # `app`, `main`
sys.path.insert(0, str(ROOT / "scripts"))  # `verify_traces`
