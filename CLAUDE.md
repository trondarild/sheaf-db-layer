# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

Build a categorical/sheaf knowledge layer over the textbook-db corpus. sheaf-db is a
**separate project** that composes with textbook-db by consuming its outputs — it does
not modify textbook-db's schema, pipeline, or files.

## Interface with textbook-db

Default textbook-db root: `~/code/textbook-db-project/` (make configurable via config file or env var).

Reads from (read-only, file-based):

| File | Contents |
|------|----------|
| `textbook_db.sqlite` | terms, occurrences, books, candidates |
| `lookup.json` | unified term → books → pages index |
| `candidates.json` | fuzzy-matched term pairs (candidate restriction morphisms) |
| `references/<key>.json` | per-book structured bibliography |
| `chapters/<key>.json` | chapter boundaries and page ranges |

The intake functor maps: Term → ConceptCandidate, Candidate → RelationCandidate,
Occurrence → IndexEvidence, Reference → EvidenceSpan. The file list above is the
working interface until the formal functor spec is formalised on the textbook-db side.

## Architecture: Four Layers

```
1. Textbook extraction      lives in textbook-db-project (upstream, read-only here)
2. Concept/reference graph  index entries → concept nodes + typed relations + evidence spans
3. Categorical/sheaf layer  presheaf over conceptual contexts; restriction + gluing maps
4. Query + synthesis        lookup(term), zoom(concept, direction), synthesize(query)
```

The SQL store for layers 2–4 lives in this project. textbook-db's outputs are ingested
once and referenced; they are never written back to.

### Core entities

```
Book → Section → IndexEntry → Concept → Context → Claim
                      ↓                    ↓
               Reference → EvidenceSpan → ConceptRelation / ConceptMap
```

Every concept, claim, relation, and context carries a `level` field:
`molecular=1, cellular=2, organ-system=3, organismic=4, interpersonal=5, social-cultural=6`

### Relation types

`is_a, part_of, causes, modulates, realizes, correlates_with, measures, models,
explains, predicts, inhibits, enables, analogous_to, operationalized_as`

### Three core operations

- `lookup(term)` — index entries, sections, concepts, references
- `zoom(concept, direction="in|out")` — recursive traversal via `part_of`, `is_a`, `realizes`, `mechanism_of`
- `synthesize(query)` — retrieve concepts + contexts + claims, cluster by field/level, identify overlaps, produce cross-level summary with citations

### Key design decisions

- **LLM is narrator, not knowledge store.** Use LLM as parser, mapper, and synthesis narrator over structured data only.
- **Embeddings are candidate generators, not the knowledge model.** Use for "may concern similar things"; graph traversal + typed claim comparison handle validity.
- **Level of explanation is explicit everywhere.** Real zooming, not metaphorical.
- **Gluing failures are data.** Obstruction (failed gluing) signals contradictions, gaps, or granularity mismatches between fields.

## Implementation Phases

See `todo.md` for the full task list. In brief:

1. **Phase 1** — Concept graph schema + ingestion + `lookup()`
2. **Phase 2** — `zoom()` with recursive graph traversal; cross-field restriction morphisms
3. **Phase 3** — `synthesize()`, `claim_compatibility` table, LLM synthesis narrator
4. **Phase 4** — Phenomenology interface (typed coordinate system over lived experience; see `design/phenomenology-interface.md`)

## Corpus Synthesis Axes

- Subjectivity / phenomenology — Stanghellini 2019
- Society / sociology — Franks 2013
- Core science — Kandel 2021, Yudofsky 2018, Buzaki 2011, Baars 2013, Gazzaniga 2014, Cacioppo 2007, Kusnecov 2014, Faure 2013

Default synthesis target when all three axes are covered: subjectivity × society × science.

## Related Projects

- `~/code/textbook-db-project` — upstream data source; stable pipeline, do not modify
- `~/code/OrganismCat` — categorical modeling of organismic processes; overlapping goals;
  textbook-db could enrich OrganismCat with grounded refs
