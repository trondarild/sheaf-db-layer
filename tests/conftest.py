"""Shared fixtures for sheaf-db tests."""

import json
import sqlite3
from pathlib import Path

import pytest

from ingest import init_sheaf_db, ingest_terms, ingest_occurrences, ingest_candidates


UPSTREAM_SCHEMA = """
CREATE TABLE books (
    key TEXT PRIMARY KEY, title TEXT NOT NULL,
    author TEXT NOT NULL, year INTEGER NOT NULL
);
CREATE TABLE terms (
    id INTEGER PRIMARY KEY, term TEXT NOT NULL UNIQUE, n_books INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE occurrences (
    id INTEGER PRIMARY KEY,
    term_id INTEGER NOT NULL REFERENCES terms(id),
    book_key TEXT NOT NULL REFERENCES books(key),
    pages TEXT NOT NULL DEFAULT '[]',
    UNIQUE(term_id, book_key)
);
CREATE TABLE candidates (
    id INTEGER PRIMARY KEY,
    term1_id INTEGER NOT NULL REFERENCES terms(id),
    term2_id INTEGER NOT NULL REFERENCES terms(id),
    match_type TEXT NOT NULL, score REAL NOT NULL
);
CREATE TABLE chapters (
    id INTEGER PRIMARY KEY, book_key TEXT NOT NULL REFERENCES books(key),
    title TEXT NOT NULL, start_book_page INTEGER, end_book_page INTEGER, ref_line INTEGER
);
CREATE TABLE "references" (
    id INTEGER PRIMARY KEY, chapter_id INTEGER NOT NULL REFERENCES chapters(id),
    authors TEXT, year INTEGER, title TEXT, venue TEXT, raw TEXT NOT NULL
);
"""


@pytest.fixture
def upstream_db():
    """Minimal in-memory textbook-db with two books, four terms, and candidates."""
    con = sqlite3.connect(":memory:")
    con.executescript(UPSTREAM_SCHEMA)
    con.executemany("INSERT INTO books VALUES (?,?,?,?)", [
        ("book_a", "Book A", "Author A", 2020),
        ("book_b", "Book B", "Author B", 2021),
    ])
    con.executemany("INSERT INTO terms (id, term) VALUES (?,?)", [
        (1, "inflammation"),
        (2, "Inflammation"),
        (3, "neuroinflammation"),
        (4, "cytokine"),
    ])
    con.executemany("INSERT INTO occurrences (term_id, book_key, pages) VALUES (?,?,?)", [
        (1, "book_a", '["10", "11"]'),
        (1, "book_b", '["55"]'),
        (2, "book_b", '["12"]'),
        (3, "book_a", '["20", "21"]'),
        (4, "book_a", '["30"]'),
    ])
    con.executemany(
        "INSERT INTO chapters (id, book_key, title, start_book_page, end_book_page) VALUES (?,?,?,?,?)",
        [(1, "book_a", "Immune Signaling", 1, 50)],
    )
    yield con
    con.close()


@pytest.fixture
def sheaf_db(tmp_path):
    """Initialised sheaf_db.sqlite in a temp directory."""
    path = tmp_path / "sheaf_db.sqlite"
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_sheaf_db(con)
    yield con, path
    con.close()


@pytest.fixture
def populated_sheaf(upstream_db, sheaf_db):
    """sheaf_db pre-loaded with the minimal upstream fixture."""
    sheaf_con, sheaf_path = sheaf_db
    term_to_concept = ingest_terms(upstream_db, sheaf_con)

    ingest_occurrences(upstream_db, sheaf_con, term_to_concept)

    # Provide candidates data directly (no filesystem access)
    candidates = [
        {"term1": "inflammation", "term2": "Inflammation", "match_type": "case",  "score": 1.0},
        {"term1": "inflammation", "term2": "neuroinflammation", "match_type": "containment", "score": 0.6},
    ]
    term_id_map = {term: tid for tid, term in upstream_db.execute("SELECT id, term FROM terms")}
    ingest_candidates(sheaf_con, term_to_concept, candidates=candidates, term_id_map=term_id_map)

    return sheaf_con, sheaf_path, term_to_concept
