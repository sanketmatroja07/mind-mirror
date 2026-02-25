import os
import sys
from pathlib import Path

root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, root)

os.environ.setdefault("DB_PATH", "/tmp/ai_journal.db")

from app import app
