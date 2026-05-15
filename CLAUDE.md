# CLAUDE.md

## Project Purpose

Build a categorical/sheaf knowledge layer over the textbook-db corpus. sheaf-db is a
**separate project** that composes with textbook-db by consuming its outputs — it does
not modify textbook-db's schema, pipeline, or files.

## Interface with textbook-db

Reads from (read-only, file-based):

| File | Contents |
|------|----------|
| `textbook_db.sqlite` | terms, occurrences, books, candidates |
| `lookup.json` | unified term → books → pages index |
| `candidates.json` | fuzzy-matched term pairs (candidate restriction morphisms) |
| `references/<key>.json` | per-book structured bibliography |
| `chapters/<key>.json` | chapter boundaries and page ranges |

Default textbook-db root: `~/code/textbook-db-project/` (make configurable via config file or env var).

## Architecture: Four Layers

```
1. Textbook extraction      lives in textbook-db-project (upstream, read-only here)
2. Concept/reference graph  index entries → concept nodes + typed relations + evidence spans
3. Categorical/sheaf layer  presheaf over conceptual contexts; restriction + gluing maps
4. Query + synthesis        lookup(term), zoom(concept, direction), synthesize(query)
```

The SQL store for layers 2–4 lives in this project. textbook-db's outputs are ingested
once and referenced; they are never written back to.

See `design/architecture.md` for the full schema sketch and implementation path.

## Related Projects

- `~/code/textbook-db-project` — upstream data source; stable pipeline, do not modify
- `~/code/OrganismCat` — categorical modeling of organismic processes; overlapping goals
  but less explicit CatLab.jl; textbook-db could enrich OrganismCat with grounded refs
