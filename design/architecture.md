Think of the system in four layers:

1. **Textbook extraction layer**
2. **Concept/reference graph layer**
3. **Categorical/sheaf layer**
4. **Query + synthesis layer**

Your SQL database can remain the storage backend. The key is not to make SQL “do category theory”, but to store enough typed relational structure that category-theoretic operations can be computed over it.

A practical architecture:

```text
Textbooks
  ↓
Sections / index entries / references / glossary terms
  ↓
Concept nodes + relations + evidence passages
  ↓
Typed graph / hypergraph
  ↓
Presheaf / sheaf-like consistency machinery
  ↓
Zoom, synthesis, contradiction finding, cross-field mappings
```

The first move is to stop treating extracted index entries merely as strings. Turn them into **candidate concept nodes**.

For example:

```sql
concept
--------
id
canonical_label
description
field              -- e.g. social neuroscience, PNI, neurogastroenterology
level              -- molecular, cellular, organ, organismic, social, cultural
status             -- raw, curated, merged, deprecated
```

Then index entries become observations of concepts, not concepts themselves:

```sql
index_entry
-----------
id
book_id
raw_label
normalized_label
concept_id nullable
page_start
page_end
section_id
confidence
```

References likewise should become structured evidential objects:

```sql
reference
---------
id
book_id
raw_citation
doi
authors
year
title
venue

concept_reference
-----------------
concept_id
reference_id
relation_type  -- supports, reviews, criticizes, historically_related, etc.
section_id
evidence_span_id
```

The crucial layer is the **concept-relation layer**. You need explicit relation types:

```sql
concept_relation
----------------
source_concept_id
target_concept_id
relation_type
field
level
confidence
evidence_span_id
```

Relation types could include:

```text
is_a
part_of
causes
modulates
realizes
correlates_with
measures
models
explains
predicts
inhibits
enables
analogous_to
operationalized_as
```

This gives you a typed graph. The sheaf-like machinery then sits on top of this graph.

A good practical interpretation of a sheaf here is:

> To each local region of knowledge, assign a structured description; where regions overlap, require or measure compatibility between descriptions.

So your “base space” can be a graph of conceptual regions:

```text
immune inflammation
  overlaps with sickness behavior
  overlaps with interoception
  overlaps with vagal signaling
  overlaps with social withdrawal
```

Each local region has associated data:

```text
definitions
mechanisms
canonical references
levels of explanation
models
measurement paradigms
neighboring concepts
```

Formally-ish:

```text
Base category B:
  objects = conceptual contexts / regions / textbook sections / field-level frames
  morphisms = inclusion, abstraction, refinement, analogy, translation

Presheaf F:
  F(context) = structured claims available in that context

Restriction maps:
  F(broad context) → F(narrow context)
  or
  F(field A frame) → F(shared overlap frame)
```

In SQL, this can be approximated with:

```sql
context
-------
id
label
context_type   -- textbook_section, field, level, mechanism, scale, theory
parent_id nullable

context_concept
---------------
context_id
concept_id
role           -- central, peripheral, methodological, disputed

context_claim
-------------
id
context_id
claim_text
claim_type     -- definition, causal, mechanistic, taxonomic, measurement, analogy
subject_concept_id
predicate
object_concept_id nullable
evidence_span_id
confidence
```

Then overlaps:

```sql
context_overlap
---------------
context_a_id
context_b_id
overlap_context_id
overlap_type      -- shared_concepts, shared_mechanism, shared_measurement, analogy
```

And mappings:

```sql
context_map
-----------
source_context_id
target_context_id
map_type          -- abstraction, refinement, translation, mechanistic_decomposition
confidence

concept_map
-----------
source_concept_id
target_concept_id
context_map_id
map_type          -- equivalent_to, narrower_than, broader_than, analogous_to
confidence
```

Now the “zoom in/out” operation becomes concrete.

Zoom out:

```text
concept → parent concepts → mechanisms → field-level contexts → general theory
```

Example:

```text
IL-6
→ inflammatory cytokines
→ immune-to-brain signaling
→ sickness behavior
→ interoceptive regulation
→ organismic coordination
```

Zoom in:

```text
sickness behavior
→ cytokine signaling
→ vagal afferents
→ hypothalamic modulation
→ behavioral withdrawal
→ measurement paradigms
```

In SQL, this is recursive graph traversal. PostgreSQL recursive CTEs can do this; if the graph becomes central, mirror it into Neo4j, Kuzu, DuckDB extensions, or a custom Python graph layer.

The sheaf-inspired synthesis step is then a compatibility problem.

For a query like:

```text
How do immune signals influence social behavior?
```

You retrieve local contexts:

```text
psychoneuroimmunology: cytokines → sickness behavior
social neuroscience: social withdrawal, threat processing, affiliation
neurogastroenterology: gut inflammation → vagal/interoceptive pathways
affective neuroscience: motivational state, energy regulation
```

Then compare their overlaps:

```text
Do they share concepts?
Do they share mechanisms?
Do they describe the same phenomenon at different scales?
Do their causal arrows align?
Do terms conflict?
Are there missing restriction maps?
```

A simple compatibility table:

```sql
claim_compatibility
-------------------
claim_a_id
claim_b_id
compatibility_type  -- consistent, conflicting, narrower, broader, orthogonal, unknown
basis               -- shared_concept, shared_reference, LLM_judgment, ontology_rule
confidence
```

This lets you distinguish:

```text
synthesis: claims agree under abstraction
tension: claims conflict
gap: contexts overlap but no mapping exists
translation: same structure, different vocabulary
```

The implementation path I would use:

First, keep SQL as canonical storage.

Second, add normalized entities:

```text
Book
Section
IndexEntry
Reference
EvidenceSpan
Concept
Context
Claim
Relation
Mapping
```

Third, build a Python service layer that does the actual operations:

```text
ingest_textbook()
extract_index()
normalize_index_terms()
link_terms_to_concepts()
extract_claims()
build_context_graph()
compute_overlaps()
query_candidates()
synthesize_answer()
```

Fourth, use embeddings only as a candidate generator, not as the knowledge model. Embeddings are useful for saying:

```text
these passages may concern similar things
```

They are not sufficient for:

```text
this is a valid cross-level explanatory mapping
```

So the pipeline should be:

```text
keyword/index search
+ embedding search
+ graph traversal
+ reference lookup
+ typed claim comparison
+ LLM-assisted synthesis with citations
```

The LLM should not be the database. It should act as a parser, mapper, and synthesis narrator over structured data.

A minimal first prototype could use these tables only:

```text
books
sections
index_entries
references
evidence_spans
concepts
concept_relations
contexts
context_concepts
claims
concept_maps
```

Then implement three operations:

```text
1. lookup(term)
   → index entries, sections, concepts, references

2. zoom(concept, direction="in/out")
   → traverse relation types such as part_of, is_a, realizes, mechanism_of

3. synthesize(query)
   → retrieve concepts + contexts + claims
   → cluster by field and level
   → identify overlaps
   → produce cross-level summary with citations
```

The most valuable design decision is to make **level of explanation** explicit everywhere.

For example:

```sql
level
-----
id
label
rank

-- molecular = 1
-- cellular = 2
-- organ-system = 3
-- organismic = 4
-- interpersonal = 5
-- social-cultural = 6
```

Then every concept, claim, relation, and context can optionally have a level:

```text
claim: IL-6 modulates vagal signaling
level: molecular → organ-system

claim: inflammation increases social withdrawal
level: organismic → social
```

This gives you real zooming, not metaphorical zooming.

The categorical version becomes more credible once you can say:

```text
A context is an object.
A refinement/abstraction/translation is a morphism.
A concept assignment is a presheaf over contexts.
A synthesis is a gluing operation over compatible local sections.
A contradiction is failed gluing.
A research gap is a missing or weak morphism between overlapping contexts.
```

My concrete recommendation: do not begin by implementing a full categorical sheaf library. Begin with a typed relational/graph representation that can later be interpreted categorically.

The first milestone should be:

```text
Given a concept, show:
- definitions across textbooks
- index locations
- references
- neighboring concepts
- levels of explanation
- field-specific contexts
- possible broader/narrower mappings
- compatible and conflicting claims
```

Once that works, the sheaf language becomes operational rather than decorative.
