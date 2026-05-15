-- sheaf-db schema  (sheaf_db.sqlite — never textbook_db.sqlite)
-- Layers 2-4: concept graph, categorical/sheaf layer, query+synthesis

PRAGMA foreign_keys = ON;

-- ── Level of explanation ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS level (
    id    INTEGER PRIMARY KEY,
    label TEXT    NOT NULL UNIQUE,
    rank  INTEGER NOT NULL UNIQUE
);

INSERT OR IGNORE INTO level (id, label, rank) VALUES
    (1, 'molecular',       1),
    (2, 'cellular',        2),
    (3, 'organ-system',    3),
    (4, 'organismic',      4),
    (5, 'interpersonal',   5),
    (6, 'social-cultural', 6);

-- ── Concepts ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS concepts (
    id              INTEGER PRIMARY KEY,
    canonical_label TEXT    NOT NULL,
    description     TEXT,
    field           TEXT,
    level_id        INTEGER REFERENCES level(id),
    status          TEXT    NOT NULL DEFAULT 'raw'
                    CHECK(status IN ('raw','curated','merged','deprecated')),
    source_term     TEXT,   -- raw term from textbook-db that seeded this node
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_concept_label  ON concepts(canonical_label);
CREATE INDEX IF NOT EXISTS idx_concept_status ON concepts(status);

-- ── Index entries (occurrences anchored to concept nodes) ─────────────────────

CREATE TABLE IF NOT EXISTS index_entries (
    id               INTEGER PRIMARY KEY,
    book_key         TEXT    NOT NULL,
    raw_label        TEXT    NOT NULL,
    normalized_label TEXT,
    concept_id       INTEGER REFERENCES concepts(id),
    pages            TEXT    NOT NULL DEFAULT '[]',  -- JSON array
    upstream_occ_id  INTEGER,                        -- occurrences.id in textbook_db
    confidence       REAL    NOT NULL DEFAULT 1.0
);

CREATE INDEX IF NOT EXISTS idx_ie_concept ON index_entries(concept_id);
CREATE INDEX IF NOT EXISTS idx_ie_book    ON index_entries(book_key);

-- ── Evidence spans ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS evidence_spans (
    id           INTEGER PRIMARY KEY,
    book_key     TEXT    NOT NULL,
    upstream_ref_id INTEGER,        -- references.id in textbook_db
    page_start   INTEGER,
    page_end     INTEGER,
    passage_text TEXT,
    span_type    TEXT    CHECK(span_type IN ('index','reference','passage','claim'))
);

-- ── Concept relations ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS concept_relations (
    id                INTEGER PRIMARY KEY,
    source_concept_id INTEGER NOT NULL REFERENCES concepts(id),
    target_concept_id INTEGER NOT NULL REFERENCES concepts(id),
    relation_type     TEXT    NOT NULL
                      CHECK(relation_type IN (
                          'is_a','part_of','causes','modulates','realizes',
                          'correlates_with','measures','models','explains',
                          'predicts','inhibits','enables','analogous_to',
                          'operationalized_as','candidate_restriction'
                      )),
    field             TEXT,
    level_id          INTEGER REFERENCES level(id),
    confidence        REAL    NOT NULL DEFAULT 1.0,
    evidence_span_id  INTEGER REFERENCES evidence_spans(id),
    match_type        TEXT,   -- from candidates.json: case/containment/abbreviation/fuzzy
    score             REAL,   -- similarity score from candidates.json
    CHECK(source_concept_id != target_concept_id)
);

CREATE INDEX IF NOT EXISTS idx_cr_source ON concept_relations(source_concept_id);
CREATE INDEX IF NOT EXISTS idx_cr_target ON concept_relations(target_concept_id);
CREATE INDEX IF NOT EXISTS idx_cr_type   ON concept_relations(relation_type);

-- ── Contexts (conceptual regions: fields, sections, mechanisms) ───────────────

CREATE TABLE IF NOT EXISTS contexts (
    id           INTEGER PRIMARY KEY,
    label        TEXT    NOT NULL,
    context_type TEXT    NOT NULL
                 CHECK(context_type IN (
                     'textbook_section','field','level','mechanism','scale','theory'
                 )),
    parent_id    INTEGER REFERENCES contexts(id),
    book_key     TEXT,
    upstream_chapter_id INTEGER,    -- chapters.id in textbook_db
    level_id     INTEGER REFERENCES level(id)
);

CREATE INDEX IF NOT EXISTS idx_ctx_type ON contexts(context_type);
CREATE INDEX IF NOT EXISTS idx_ctx_book ON contexts(book_key);

-- ── Context–concept membership ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS context_concepts (
    context_id INTEGER NOT NULL REFERENCES contexts(id),
    concept_id INTEGER NOT NULL REFERENCES concepts(id),
    role       TEXT    CHECK(role IN ('central','peripheral','methodological','disputed')),
    PRIMARY KEY (context_id, concept_id)
);

-- ── Claims ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS claims (
    id                 INTEGER PRIMARY KEY,
    context_id         INTEGER REFERENCES contexts(id),
    claim_text         TEXT    NOT NULL,
    claim_type         TEXT
                       CHECK(claim_type IN (
                           'definition','causal','mechanistic','taxonomic',
                           'measurement','analogy'
                       )),
    subject_concept_id INTEGER REFERENCES concepts(id),
    predicate          TEXT,
    object_concept_id  INTEGER REFERENCES concepts(id),
    evidence_span_id   INTEGER REFERENCES evidence_spans(id),
    level_id           INTEGER REFERENCES level(id),
    confidence         REAL    NOT NULL DEFAULT 1.0
);

-- ── Context maps and overlaps ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS context_maps (
    id                INTEGER PRIMARY KEY,
    source_context_id INTEGER NOT NULL REFERENCES contexts(id),
    target_context_id INTEGER NOT NULL REFERENCES contexts(id),
    map_type          TEXT    NOT NULL
                      CHECK(map_type IN (
                          'abstraction','refinement','translation',
                          'mechanistic_decomposition'
                      )),
    confidence        REAL    NOT NULL DEFAULT 1.0,
    CHECK(source_context_id != target_context_id)
);

CREATE TABLE IF NOT EXISTS context_overlaps (
    context_a_id       INTEGER NOT NULL REFERENCES contexts(id),
    context_b_id       INTEGER NOT NULL REFERENCES contexts(id),
    overlap_context_id INTEGER REFERENCES contexts(id),
    overlap_type       TEXT
                       CHECK(overlap_type IN (
                           'shared_concepts','shared_mechanism',
                           'shared_measurement','analogy'
                       )),
    PRIMARY KEY (context_a_id, context_b_id)
);

-- ── Concept maps (cross-context concept-level mappings) ───────────────────────

CREATE TABLE IF NOT EXISTS concept_maps (
    id                INTEGER PRIMARY KEY,
    source_concept_id INTEGER NOT NULL REFERENCES concepts(id),
    target_concept_id INTEGER NOT NULL REFERENCES concepts(id),
    context_map_id    INTEGER REFERENCES context_maps(id),
    map_type          TEXT    NOT NULL
                      CHECK(map_type IN (
                          'equivalent_to','narrower_than','broader_than','analogous_to'
                      )),
    confidence        REAL    NOT NULL DEFAULT 1.0,
    CHECK(source_concept_id != target_concept_id)
);

-- ── Claim compatibility (synthesis layer) ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS claim_compatibility (
    claim_a_id         INTEGER NOT NULL REFERENCES claims(id),
    claim_b_id         INTEGER NOT NULL REFERENCES claims(id),
    compatibility_type TEXT    NOT NULL
                       CHECK(compatibility_type IN (
                           'consistent','conflicting','narrower','broader',
                           'orthogonal','unknown'
                       )),
    basis              TEXT
                       CHECK(basis IN (
                           'shared_concept','shared_reference',
                           'LLM_judgment','ontology_rule'
                       )),
    confidence         REAL    NOT NULL DEFAULT 1.0,
    PRIMARY KEY (claim_a_id, claim_b_id),
    CHECK(claim_a_id != claim_b_id)
);
