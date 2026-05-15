import json
import sqlite3

import pytest

from ingest import (
    init_sheaf_db,
    ingest_terms,
    ingest_occurrences,
    ingest_chapters,
    ingest_references,
    ingest_candidates,
)


EXPECTED_TABLES = {
    "level", "concepts", "index_entries", "evidence_spans",
    "concept_relations", "contexts", "context_concepts", "claims",
    "context_maps", "context_overlaps", "concept_maps", "claim_compatibility",
}


def test_init_creates_all_tables(sheaf_db):
    con, _ = sheaf_db
    tables = {
        r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert EXPECTED_TABLES <= tables


def test_init_seeds_levels(sheaf_db):
    con, _ = sheaf_db
    levels = con.execute("SELECT rank, label FROM level ORDER BY rank").fetchall()
    assert len(levels) == 6
    assert (levels[0]["rank"], levels[0]["label"]) == (1, "molecular")
    assert (levels[-1]["rank"], levels[-1]["label"]) == (6, "social-cultural")


def test_ingest_terms_creates_concepts(upstream_db, sheaf_db):
    con, _ = sheaf_db
    mapping = ingest_terms(upstream_db, con)
    assert len(mapping) == 4
    concepts = con.execute("SELECT canonical_label, status FROM concepts").fetchall()
    labels = {r[0] for r in concepts}
    assert "inflammation" in labels
    assert "cytokine" in labels
    assert all(r[1] == "raw" for r in concepts)


def test_ingest_terms_returns_correct_mapping(upstream_db, sheaf_db):
    con, _ = sheaf_db
    mapping = ingest_terms(upstream_db, con)
    # upstream term id 1 ("inflammation") must map to a valid sheaf concept id
    assert mapping[1] is not None
    row = con.execute("SELECT canonical_label FROM concepts WHERE id = ?", (mapping[1],)).fetchone()
    assert row[0] == "inflammation"


def test_ingest_occurrences(upstream_db, sheaf_db):
    con, _ = sheaf_db
    mapping = ingest_terms(upstream_db, con)
    ingest_occurrences(upstream_db, con, mapping)
    entries = con.execute("SELECT book_key, pages FROM index_entries WHERE concept_id = ?",
                          (mapping[1],)).fetchall()
    books = {r[0] for r in entries}
    assert books == {"book_a", "book_b"}
    pages_a = next(json.loads(r[1]) for r in entries if r[0] == "book_a")
    assert "10" in pages_a


def test_ingest_chapters_creates_contexts(upstream_db, sheaf_db):
    con, _ = sheaf_db
    mapping = ingest_chapters(upstream_db, con)
    assert len(mapping) == 1
    ctx = con.execute("SELECT label, context_type, book_key FROM contexts").fetchone()
    assert ctx[0] == "Immune Signaling"
    assert ctx[1] == "textbook_section"
    assert ctx[2] == "book_a"


def test_ingest_candidates_creates_relations(upstream_db, sheaf_db):
    con, _ = sheaf_db
    term_to_concept = ingest_terms(upstream_db, con)
    candidates = [
        {"term1": "inflammation", "term2": "Inflammation",
         "match_type": "case", "score": 1.0},
        {"term1": "inflammation", "term2": "neuroinflammation",
         "match_type": "containment", "score": 0.6},
    ]
    term_id_map = {t: i for i, t in upstream_db.execute("SELECT id, term FROM terms")}
    ingest_candidates(con, term_to_concept, candidates=candidates, term_id_map=term_id_map)

    relations = con.execute(
        "SELECT relation_type, match_type, score FROM concept_relations"
    ).fetchall()
    assert len(relations) == 2
    assert all(r[0] == "candidate_restriction" for r in relations)
    match_types = {r[1] for r in relations}
    assert match_types == {"case", "containment"}


def test_ingest_candidates_skips_unknown_terms(upstream_db, sheaf_db):
    con, _ = sheaf_db
    term_to_concept = ingest_terms(upstream_db, con)
    candidates = [
        {"term1": "inflammation", "term2": "NONEXISTENT",
         "match_type": "fuzzy", "score": 0.5},
    ]
    term_id_map = {t: i for i, t in upstream_db.execute("SELECT id, term FROM terms")}
    ingest_candidates(con, term_to_concept, candidates=candidates, term_id_map=term_id_map)
    count = con.execute("SELECT count(*) FROM concept_relations").fetchone()[0]
    assert count == 0
