import sys
from pathlib import Path

MP5_ROOT = Path(__file__).resolve().parents[1]
if str(MP5_ROOT) not in sys.path:
    sys.path.insert(0, str(MP5_ROOT))
