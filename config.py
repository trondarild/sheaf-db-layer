import os
from pathlib import Path

TEXTBOOK_DB_ROOT = Path(
    os.environ.get("TEXTBOOK_DB_ROOT", Path.home() / "code" / "textbook-db-project")
)

SHEAF_DB_PATH = Path(
    os.environ.get("SHEAF_DB_PATH", Path(__file__).parent / "sheaf_db.sqlite")
)

TEXTBOOK_SQLITE  = TEXTBOOK_DB_ROOT / "textbook_db.sqlite"
CANDIDATES_JSON  = TEXTBOOK_DB_ROOT / "candidates.json"
LOOKUP_JSON      = TEXTBOOK_DB_ROOT / "lookup.json"
CHAPTERS_DIR     = TEXTBOOK_DB_ROOT / "chapters"
REFERENCES_DIR   = TEXTBOOK_DB_ROOT / "references"
