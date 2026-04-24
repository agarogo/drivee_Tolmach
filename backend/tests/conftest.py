import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os

os.environ.setdefault("DATABASE_URL", "postgresql://analytics.example.local:5432/drivee")
os.environ.setdefault("JWT_SECRET", "test-secret")
