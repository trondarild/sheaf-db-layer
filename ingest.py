"""
Intake functor: textbook-db outputs → sheaf-db concept graph.

Mapping:
  Term        → ConceptCandidate  (concepts, status='raw')
  Occurrence  → IndexEvidence     (index_entries)
  Candidate   → RelationCandidate (concept_relations, relation_type='candidate_restriction')
  Chapter     → Context           (contexts, context_type='textbook_section')
  Reference   → EvidenceSpan      (evidence_spans, span_type='reference')
"""

import json
import sqlite3
from pathlib import Path

from config import TEXTBOOK_SQLITE, CANDIDATES_JSON, SHEAF_DB_PATH

SCHEMA = Path(__file__).parent / "schema.sql"


def init_sheaf_db(sheaf: sqlite3.Connection) -> None:
    sheaf.executescript(SCHEMA.read_text())
    sheaf.commit()


def ingest_terms(upstream: sqlite3.Connection, sheaf: sqlite3.Connection) -> dict[int, int]:
    """terms → concepts (status='raw').  Returns upstream term_id → sheaf concept_id."""
    rows = upstream.execute("SELECT id, term FROM terms ORDER BY id").fetchall()
    term_to_concept: dict[int, int] = {}
    for term_id, term in rows:
        cur = sheaf.execute(
            "INSERT INTO concepts (canonical_label, source_term, status) VALUES (?, ?, 'raw')",
            (term, term),
        )
        term_to_concept[term_id] = cur.lastrowid
    sheaf.commit()
    return term_to_concept


def ingest_occurrences(
    upstream: sqlite3.Connection,
    sheaf: sqlite3.Connection,
    term_to_concept: dict[int, int],
) -> None:
    """occurrences → index_entries."""
    rows = upstream.execute(
        "SELECT id, term_id, book_key, pages FROM occurrences ORDER BY id"
    ).fetchall()
    sheaf.executemany(
        """INSERT INTO index_entries
               (upstream_occ_id, book_key, raw_label, concept_id, pages)
           VALUES (?, ?, ?, ?, ?)""",
        [
            (
                occ_id,
                book_key,
                upstream.execute(
                    "SELECT term FROM terms WHERE id = ?", (term_id,)
                ).fetchone()[0],
                term_to_concept.get(term_id),
                pages,
            )
            for occ_id, term_id, book_key, pages in rows
        ],
    )
    sheaf.commit()


def ingest_chapters(upstream: sqlite3.Connection, sheaf: sqlite3.Connection) -> dict[int, int]:
    """chapters → contexts (context_type='textbook_section').
    Returns upstream chapter_id → sheaf context_id."""
    rows = upstream.execute(
        "SELECT id, book_key, title, start_book_page, end_book_page FROM chapters ORDER BY id"
    ).fetchall()
    chapter_to_context: dict[int, int] = {}
    for ch_id, book_key, title, start_page, end_page in rows:
        cur = sheaf.execute(
            """INSERT INTO contexts
                   (label, context_type, book_key, upstream_chapter_id)
               VALUES (?, 'textbook_section', ?, ?)""",
            (title, book_key, ch_id),
        )
        chapter_to_context[ch_id] = cur.lastrowid
    sheaf.commit()
    return chapter_to_context


def ingest_references(
    upstream: sqlite3.Connection,
    sheaf: sqlite3.Connection,
    chapter_to_context: dict[int, int],
) -> None:
    """references → evidence_spans (span_type='reference')."""
    rows = upstream.execute(
        "SELECT id, chapter_id, raw FROM 'references' ORDER BY id"
    ).fetchall()
    sheaf.executemany(
        """INSERT INTO evidence_spans
               (upstream_ref_id, book_key, span_type, passage_text)
           VALUES (?, ?, 'reference', ?)""",
        [
            (
                ref_id,
                upstream.execute(
                    "SELECT book_key FROM chapters WHERE id = ?", (ch_id,)
                ).fetchone()[0],
                raw,
            )
            for ref_id, ch_id, raw in rows
        ],
    )
    sheaf.commit()


def ingest_candidates(
    sheaf: sqlite3.Connection,
    term_to_concept: dict[int, int],
    candidates: list[dict] | None = None,
    term_id_map: dict[str, int] | None = None,
) -> None:
    """candidates.json pairs → concept_relations (relation_type='candidate_restriction').

    These are candidate restriction morphisms: fuzzy-matched terms that may denote
    the same concept across different books / contexts.

    candidates and term_id_map are loaded from disk when not provided (normal run path).
    Pass them explicitly in tests to avoid filesystem access.
    """
    if candidates is None:
        candidates = json.loads(CANDIDATES_JSON.read_text())
    if term_id_map is None:
        upstream = sqlite3.connect(f"file:{TEXTBOOK_SQLITE}?mode=ro", uri=True)
        term_id_map = {
            term: tid
            for tid, term in upstream.execute("SELECT id, term FROM terms").fetchall()
        }
        upstream.close()

    rows = []
    for c in candidates:
        src_id = term_id_map.get(c["term1"])
        tgt_id = term_id_map.get(c["term2"])
        if src_id is None or tgt_id is None:
            continue
        src_concept = term_to_concept.get(src_id)
        tgt_concept = term_to_concept.get(tgt_id)
        if src_concept is None or tgt_concept is None:
            continue
        rows.append((src_concept, tgt_concept, c["match_type"], c["score"]))

    sheaf.executemany(
        """INSERT INTO concept_relations
               (source_concept_id, target_concept_id,
                relation_type, match_type, score, confidence)
           VALUES (?, ?, 'candidate_restriction', ?, ?, ?)""",
        [(s, t, mt, sc, sc) for s, t, mt, sc in rows],
    )
    sheaf.commit()


def run(force: bool = False) -> None:
    if SHEAF_DB_PATH.exists() and not force:
        print(f"{SHEAF_DB_PATH} already exists — pass force=True to re-ingest")
        return

    if SHEAF_DB_PATH.exists():
        SHEAF_DB_PATH.unlink()

    print(f"Opening upstream (read-only): {TEXTBOOK_SQLITE}")
    upstream = sqlite3.connect(f"file:{TEXTBOOK_SQLITE}?mode=ro", uri=True)

    print(f"Creating sheaf db: {SHEAF_DB_PATH}")
    sheaf = sqlite3.connect(SHEAF_DB_PATH)
    sheaf.execute("PRAGMA foreign_keys = ON")

    init_sheaf_db(sheaf)

    print("Ingesting terms → concepts …")
    term_to_concept = ingest_terms(upstream, sheaf)
    print(f"  {len(term_to_concept)} concepts created")

    print("Ingesting occurrences → index_entries …")
    ingest_occurrences(upstream, sheaf, term_to_concept)

    print("Ingesting chapters → contexts …")
    chapter_to_context = ingest_chapters(upstream, sheaf)
    print(f"  {len(chapter_to_context)} contexts created")

    print("Ingesting references → evidence_spans …")
    ingest_references(upstream, sheaf, chapter_to_context)

    print("Ingesting candidates → concept_relations …")
    ingest_candidates(sheaf, term_to_concept)

    upstream.close()
    sheaf.close()
    print("Done.")


if __name__ == "__main__":
    import sys
    run(force="--force" in sys.argv)
