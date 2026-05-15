# Todo

## Architecture principle

sheaf-db is a **separate project** that composes with textbook-db by consuming its
outputs. textbook-db's pipeline stays intact and unchanged; this project reads from it
and builds its own graph/presheaf representation independently. No changes to
textbook-db's schema or files.

**Reads from textbook-db (read-only):**
- `textbook_db.sqlite` — terms, occurrences, books, candidates
- `lookup.json` — unified term → books → pages index
- `candidates.json` — fuzzy-matched term pairs (candidate restriction morphisms)
- `references/<key>.json` — per-book structured bibliography
- `chapters/<key>.json` — chapter boundaries and page ranges

## Interface contract (categorical I/O)

- [ ] Define the intake functor from the textbook-db interface category into sheaf-db's
      concept-graph structures. Classical goal: this project should know as little as
      possible about textbook-db's internals — only what the shared interface category
      exposes. Counterpart task (defining that interface category) lives in
      textbook-db-project/todo.md and should be drafted in parallel.
      - The intake functor maps: Term → ConceptCandidate, Candidate → RelationCandidate,
        Occurrence → IndexEvidence, Reference → EvidenceSpan (tentative — revise once
        the interface category is formalised on the textbook-db side).
      - Until the formal contract exists, the current file-list above is the working
        interface; treat it as the object-level stand-in for the eventual functor spec.

## Design documents

- `design/architecture.md` — full SQL schema + layered architecture sketch
  (four layers, concept/context/claim tables, level-of-explanation field, relation types,
  zoom/synthesize operations, implementation path)
- `design/phenomenology-interface.md` — phenomenology as typed interface layer;
  functor faithfulness; case study on integrating Stanghellini with core science books

## Exploration

- [ ] Establish whether the corpus can be modelled as a sheaf in the categorical sense:
      each book is an "open set" over its domain (neuroscience, psychiatry, gastro, etc.);
      terms shared or fuzzy-matched across books are restriction maps between sections;
      a consistent assignment of meaning/pages across overlapping domains constitutes a
      global section — i.e. knowledge that holds across fields.
      - Why valuable: books crossing fields (neuro+psychology, neuro+gastro, neuropsychiatry)
        are natural gluing sites; sheaf structure makes explicit which claims are field-local
        vs. field-invariant, and where gluing fails (contradictions, gaps, granularity mismatches).
      - Concrete representation: terms as sections, books as opens, candidates.json pairs
        as candidate restriction morphisms; global section query = find the maximal consistent
        sub-sheaf containing a term.
      - Starting point: Spivak (2014) "Category Theory for the Sciences" ch. 7 (databases as
        functors); Curry (2014) thesis on sheaves and data fusion; check pysheaf library.

## Implementation

### Phase 1 — Concept graph (minimal prototype)

- [ ] Schema: `concepts`, `concept_relations`, `contexts`, `context_concepts`, `claims`,
      `concept_maps` (see design/architecture.md for full column specs)
- [ ] Ingestion: read textbook-db outputs → populate concept nodes from index terms;
      candidates.json pairs become candidate `concept_relations`
- [ ] Level-of-explanation field on every concept, claim, relation, context:
      molecular=1, cellular=2, organ-system=3, organismic=4, interpersonal=5, social-cultural=6
- [ ] Implement `lookup(term)` → index entries, sections, concepts, references

### Phase 2 — Zoom operations

- [ ] Implement `zoom(concept, direction="in|out")` traversing `part_of`, `is_a`,
      `realizes`, `mechanism_of` relation types via recursive graph traversal
- [ ] Cross-field traversal: follow restriction morphisms across book/domain boundaries

### Phase 3 — Synthesis

- [ ] Implement `synthesize(query)`:
      retrieve concepts + contexts + claims → cluster by field and level →
      identify overlaps → produce cross-level summary with citations
- [ ] `claim_compatibility` table: tag pairs as consistent / conflicting / narrower /
      broader / orthogonal / unknown
- [ ] LLM acts as parser, mapper, and synthesis narrator over structured data —
      not as the knowledge store

### Phase 4 — Phenomenology interface (see design/phenomenology-interface.md)

- [ ] Model phenomenology as typed coordinate system over lived experience, not as doctrine:
      `experience episode → intentional object → bodily orientation → affective tone →
       temporal structure → salience field → action-readiness → reportability constraints`
- [ ] Three layers: raw subjective report → phenomenological coding → cross-level anchoring
- [ ] Map Stanghellini 2019 index terms into phenomenological coding dimensions
- [ ] Link coded dimensions sparsely to candidate mechanisms from core-science books

## UI

### Terminal UI

- [ ] Interactive TUI (`tui.py`) using `Textual` or `curses`:
      - Search bar → calls `lookup(term)`, displays concept + occurrences by book
      - Zoom panel: navigate the concept graph in/out with arrow keys or j/k
      - Synthesis panel: cross-field overlap table for the selected concept
      - Status bar showing relation type filter, depth, active db path
- [ ] Pager-friendly plain-text output mode (already partially in place via CLI);
      pipe-friendly: `python3 sheaf_db.py synthesize "memory" | less`
- [ ] Symlink `bin/sheaf-db` (and any future piped commands) into `~/.local/bin`
      so they are available on PATH without modifying shell config:
      `ln -s $(pwd)/bin/sheaf-db ~/.local/bin/sheaf-db`
      Ensure `~/.local/bin` is in PATH (standard on most modern Linux/macOS setups).

### Web UI

- [ ] Minimal Flask/FastAPI backend exposing `lookup`, `zoom`, `synthesize` as JSON endpoints
- [ ] Frontend: concept graph visualisation (e.g. D3 force graph) with book-coloured nodes
- [ ] Cross-field overlap table with sortable score/match_type columns
- [ ] Global section candidates highlighted in the graph

### Claude skill (sheaf-db as a tool)

- [ ] Wrap `lookup`, `zoom`, `synthesize` as Claude tool-use functions
      so Claude can query sheaf-db during a conversation
- [ ] Skill prompt: instructs Claude to use structured results as evidence,
      not to confabulate — LLM as narrator over sheaf-db output
- [ ] Register as a skill in the FleetView/Claude Code harness

## Notes

Primary synthesis axes (from textbook-db corpus):
- Subjectivity / phenomenology — Stanghellini 2019
- Society / sociology — Franks 2013
- Core science — Kandel 2021, Yudofsky 2018, Buzaki 2011, Baars 2013, Gazzaniga 2014,
  Cacioppo 2007, Kusnecov 2014, Faure 2013
A three-way subjectivity × society × science synthesis is the default target when all
three axes are covered.
