"""
sheaf-db query operations.

lookup(term)                    → concepts, index entries by book, candidate relations
zoom(term, direction, ...)      → recursive graph traversal (part_of, is_a, realizes, …)
synthesize(query, ...)          → cross-field view: seed + neighborhood grouped by book,
                                  cross-field overlaps, global section candidates, claims
"""

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config import SHEAF_DB_PATH

# Relation types used for semantic zoom (hierarchy / mechanism).
# candidate_restriction is intentionally excluded from the default so that zoom
# traverses only asserted typed relations; pass it explicitly when exploring the
# raw candidate graph.
ZOOM_RELATION_TYPES: tuple[str, ...] = (
    "is_a", "part_of", "realizes", "mechanism_of",
    "causes", "modulates", "enables", "inhibits",
)


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or SHEAF_DB_PATH
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class Occurrence:
    book_key: str
    pages: list[str]


@dataclass
class Relation:
    related_term: str
    relation_type: str
    match_type: Optional[str]
    score: Optional[float]
    direction: str          # 'from' | 'to'


@dataclass
class Concept:
    id: int
    canonical_label: str
    status: str
    level: Optional[str]
    occurrences: list[Occurrence] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)


@dataclass
class LookupResult:
    query: str
    concepts: list[Concept] = field(default_factory=list)

    @property
    def books(self) -> list[str]:
        seen: set[str] = set()
        out = []
        for c in self.concepts:
            for occ in c.occurrences:
                if occ.book_key not in seen:
                    seen.add(occ.book_key)
                    out.append(occ.book_key)
        return out


# ── lookup ────────────────────────────────────────────────────────────────────

def lookup(term: str, db_path: Optional[Path] = None) -> LookupResult:
    """Return concepts, occurrences, and candidate relations matching term.

    Match priority: exact → case-insensitive exact → substring.
    All matching concepts are returned (a term may seed multiple raw nodes
    that will be merged during curation).
    """
    con = _connect(db_path)
    result = LookupResult(query=term)

    # Find matching concepts — exact first, then case-insensitive, then substring
    exact = con.execute(
        "SELECT * FROM concepts WHERE canonical_label = ? AND status != 'deprecated'",
        (term,),
    ).fetchall()
    if exact:
        rows = exact
    else:
        iexact = con.execute(
            "SELECT * FROM concepts WHERE canonical_label = ? COLLATE NOCASE"
            " AND status != 'deprecated'",
            (term,),
        ).fetchall()
        rows = iexact if iexact else con.execute(
            "SELECT * FROM concepts WHERE canonical_label LIKE ? AND status != 'deprecated'",
            (f"%{term}%",),
        ).fetchall()

    if not rows:
        return result

    level_map: dict[int, str] = {
        r["id"]: r["label"]
        for r in con.execute("SELECT id, label FROM level").fetchall()
    }

    for row in rows:
        concept = Concept(
            id=row["id"],
            canonical_label=row["canonical_label"],
            status=row["status"],
            level=level_map.get(row["level_id"]) if row["level_id"] else None,
        )

        # Occurrences by book
        occ_rows = con.execute(
            "SELECT book_key, pages FROM index_entries WHERE concept_id = ? ORDER BY book_key",
            (concept.id,),
        ).fetchall()
        for occ in occ_rows:
            concept.occurrences.append(
                Occurrence(book_key=occ["book_key"], pages=json.loads(occ["pages"]))
            )

        # Relations: outgoing (source) and incoming (target)
        out_rows = con.execute(
            """SELECT cr.relation_type, cr.match_type, cr.score, c2.canonical_label
               FROM concept_relations cr
               JOIN concepts c2 ON c2.id = cr.target_concept_id
               WHERE cr.source_concept_id = ?
               ORDER BY cr.score DESC""",
            (concept.id,),
        ).fetchall()
        for r in out_rows:
            concept.relations.append(
                Relation(
                    related_term=r["canonical_label"],
                    relation_type=r["relation_type"],
                    match_type=r["match_type"],
                    score=r["score"],
                    direction="to",
                )
            )

        in_rows = con.execute(
            """SELECT cr.relation_type, cr.match_type, cr.score, c1.canonical_label
               FROM concept_relations cr
               JOIN concepts c1 ON c1.id = cr.source_concept_id
               WHERE cr.target_concept_id = ?
               ORDER BY cr.score DESC""",
            (concept.id,),
        ).fetchall()
        for r in in_rows:
            concept.relations.append(
                Relation(
                    related_term=r["canonical_label"],
                    relation_type=r["relation_type"],
                    match_type=r["match_type"],
                    score=r["score"],
                    direction="from",
                )
            )

        result.concepts.append(concept)

    con.close()
    return result


# ── zoom ─────────────────────────────────────────────────────────────────────

@dataclass
class ZoomNode:
    concept_id: int
    canonical_label: str
    depth: int
    relation_type: Optional[str]    # None for the root node
    match_type: Optional[str]
    score: Optional[float]
    path: list[str]                 # labels from root to this node (inclusive)


@dataclass
class ZoomResult:
    query: str
    direction: str
    relation_types: tuple[str, ...]
    root: Optional[ZoomNode]
    nodes: list[ZoomNode] = field(default_factory=list)  # depth > 0, BFS order

    def at_depth(self, depth: int) -> list[ZoomNode]:
        return [n for n in self.nodes if n.depth == depth]

    @property
    def max_depth(self) -> int:
        return max((n.depth for n in self.nodes), default=0)


def zoom(
    term: str,
    direction: str = "out",
    relation_types: Optional[tuple[str, ...]] = None,
    max_depth: int = 5,
    db_path: Optional[Path] = None,
) -> ZoomResult:
    """Traverse the concept graph from a seed term.

    direction="out"  follows edges where the seed is the source
                     (e.g. X part_of Y  →  reaches Y and its ancestors).
    direction="in"   follows edges where the seed is the target
                     (e.g. Y part_of X  →  reaches parts/children of X).
    direction="both" combines both traversals.

    relation_types defaults to ZOOM_RELATION_TYPES (semantic typed relations).
    Pass ('candidate_restriction',) to explore the raw candidate graph.

    Uses a Python-level BFS so each node is visited at most once regardless of
    how many paths lead to it (the recursive-CTE approach caused path explosion
    on dense candidate graphs).
    """
    if direction not in ("in", "out", "both"):
        raise ValueError(f"direction must be 'in', 'out', or 'both'; got {direction!r}")

    rel_types = relation_types or ZOOM_RELATION_TYPES
    result = ZoomResult(query=term, direction=direction, relation_types=rel_types, root=None)

    con = _connect(db_path)

    # Resolve seed concept (exact → case-insensitive → substring, first match only)
    seed_row = (
        con.execute(
            "SELECT id, canonical_label FROM concepts WHERE canonical_label = ?"
            " AND status != 'deprecated'", (term,)
        ).fetchone()
        or con.execute(
            "SELECT id, canonical_label FROM concepts WHERE canonical_label = ? COLLATE NOCASE"
            " AND status != 'deprecated'", (term,)
        ).fetchone()
        or con.execute(
            "SELECT id, canonical_label FROM concepts WHERE canonical_label LIKE ?"
            " AND status != 'deprecated'", (f"%{term}%",)
        ).fetchone()
    )
    if seed_row is None:
        con.close()
        return result

    seed_id: int = seed_row["id"]
    seed_label: str = seed_row["canonical_label"]
    result.root = ZoomNode(
        concept_id=seed_id, canonical_label=seed_label,
        depth=0, relation_type=None, match_type=None, score=None,
        path=[seed_label],
    )

    rel_placeholders = ",".join("?" * len(rel_types))

    def _run_bfs(join_src: str, join_tgt: str, visited: set[int]) -> list[ZoomNode]:
        """BFS in one direction. visited is shared across directions for 'both'."""
        frontier: list[int] = [seed_id]
        path_map: dict[int, list[str]] = {seed_id: [seed_label]}
        nodes: list[ZoomNode] = []

        for depth in range(1, max_depth + 1):
            if not frontier:
                break
            fp = ",".join("?" * len(frontier))
            rows = con.execute(
                f"""SELECT cr.{join_src} AS parent_id,
                           cr.relation_type, cr.match_type, cr.score,
                           c.id AS concept_id, c.canonical_label
                    FROM concept_relations cr
                    JOIN concepts c ON c.id = cr.{join_tgt}
                    WHERE cr.{join_src} IN ({fp})
                      AND cr.relation_type IN ({rel_placeholders})
                      AND c.status != 'deprecated'
                    ORDER BY cr.score DESC, c.canonical_label""",
                (*frontier, *rel_types),
            ).fetchall()

            next_frontier: list[int] = []
            for row in rows:
                if row["concept_id"] in visited:
                    continue
                visited.add(row["concept_id"])
                next_frontier.append(row["concept_id"])
                parent_path = path_map.get(row["parent_id"], [seed_label])
                child_path = parent_path + [row["canonical_label"]]
                path_map[row["concept_id"]] = child_path
                nodes.append(ZoomNode(
                    concept_id=row["concept_id"],
                    canonical_label=row["canonical_label"],
                    depth=depth,
                    relation_type=row["relation_type"],
                    match_type=row["match_type"],
                    score=row["score"],
                    path=child_path,
                ))
            frontier = next_frontier

        return nodes

    seen_ids: set[int] = {seed_id}

    if direction in ("out", "both"):
        result.nodes.extend(_run_bfs("source_concept_id", "target_concept_id", seen_ids))

    if direction in ("in", "both"):
        result.nodes.extend(_run_bfs("target_concept_id", "source_concept_id", seen_ids))

    con.close()
    return result


# ── synthesize ───────────────────────────────────────────────────────────────

@dataclass
class CrossFieldOverlap:
    """A concept relation whose endpoints appear in at least one different book.

    These are candidate restriction morphisms across field boundaries —
    the primary gluing sites in the sheaf picture.
    """
    source_label: str
    target_label: str
    relation_type: str
    match_type: Optional[str]
    score: Optional[float]
    source_books: list[str]
    target_books: list[str]

    @property
    def bridged_books(self) -> tuple[list[str], list[str]]:
        """Books unique to source vs. unique to target."""
        src = set(self.source_books)
        tgt = set(self.target_books)
        return sorted(src - tgt), sorted(tgt - src)


@dataclass
class SynthesisResult:
    """Structured cross-field view of a query ready for LLM narration.

    by_book groups every concept (seed + neighborhood) by the books it
    appears in.  cross_field_overlaps highlight relations that bridge
    different books — the sheaf restriction morphisms.  global_concepts
    are concepts present in >= min_books books directly (candidate
    global sections).  claims is empty until Phase 3 curation adds typed
    assertions.
    """
    query: str
    seed_concepts: list[Concept]
    neighborhood: list[ZoomNode]                    # zoom-expanded related concepts
    by_book: dict[str, list[str]]                   # book_key → canonical labels
    cross_field_overlaps: list[CrossFieldOverlap]
    global_concepts: list[tuple[str, int]]          # (label, n_books), descending
    claims: list = field(default_factory=list)      # Phase 3+

    @property
    def books(self) -> list[str]:
        return sorted(self.by_book)

    @property
    def n_neighborhood(self) -> int:
        return len(self.neighborhood)


def synthesize(
    query: str,
    relation_types: Optional[tuple[str, ...]] = None,
    max_depth: int = 1,
    min_books_for_global: int = 2,
    db_path: Optional[Path] = None,
) -> SynthesisResult:
    """Build a cross-field structured view of query for synthesis / narration.

    Steps:
      1. lookup(query)   → seed concepts
      2. zoom(both)      → neighborhood (candidate_restriction or typed relations)
      3. group by book   → field sections
      4. cross-field     → relations whose endpoints appear in different books
      5. global          → concepts present in min_books+ books directly

    relation_types defaults to ('candidate_restriction',) so the operation is
    immediately useful with the current graph; switch to ZOOM_RELATION_TYPES
    once typed relations are populated.
    """
    rel_types = relation_types or ("candidate_restriction",)

    # ── 1. Seed ───────────────────────────────────────────────────────────────
    lookup_result = lookup(query, db_path=db_path)
    seed_concepts = lookup_result.concepts

    result = SynthesisResult(
        query=query,
        seed_concepts=seed_concepts,
        neighborhood=[],
        by_book={},
        cross_field_overlaps=[],
        global_concepts=[],
    )

    if not seed_concepts:
        return result

    # ── 2. Neighborhood via zoom ──────────────────────────────────────────────
    seen_concept_ids: set[int] = {c.id for c in seed_concepts}
    all_nodes: list[ZoomNode] = []

    for seed in seed_concepts:
        zoom_result = zoom(
            seed.canonical_label,
            direction="both",
            relation_types=rel_types,
            max_depth=max_depth,
            db_path=db_path,
        )
        for node in zoom_result.nodes:
            if node.concept_id not in seen_concept_ids:
                seen_concept_ids.add(node.concept_id)
                all_nodes.append(node)

    result.neighborhood = all_nodes

    # ── 3. Group by book ──────────────────────────────────────────────────────
    con = _connect(db_path)
    placeholders = ",".join("?" * len(seen_concept_ids))
    id_list = list(seen_concept_ids)

    book_rows = con.execute(
        f"""SELECT ie.book_key, c.canonical_label
            FROM index_entries ie
            JOIN concepts c ON c.id = ie.concept_id
            WHERE ie.concept_id IN ({placeholders})
            ORDER BY ie.book_key, c.canonical_label""",
        id_list,
    ).fetchall()

    by_book: dict[str, list[str]] = {}
    for row in book_rows:
        by_book.setdefault(row["book_key"], []).append(row["canonical_label"])
    result.by_book = by_book

    # ── 4. Cross-field overlaps ───────────────────────────────────────────────
    rel_placeholders = ",".join("?" * len(rel_types))
    overlap_rows = con.execute(
        f"""SELECT cr.relation_type, cr.match_type, cr.score,
                   c1.canonical_label AS src_label,
                   c2.canonical_label AS tgt_label,
                   ie1.book_key       AS src_book,
                   ie2.book_key       AS tgt_book
            FROM concept_relations cr
            JOIN concepts      c1  ON c1.id  = cr.source_concept_id
            JOIN concepts      c2  ON c2.id  = cr.target_concept_id
            JOIN index_entries ie1 ON ie1.concept_id = cr.source_concept_id
            JOIN index_entries ie2 ON ie2.concept_id = cr.target_concept_id
            WHERE cr.source_concept_id IN ({placeholders})
              AND cr.target_concept_id IN ({placeholders})
              AND cr.relation_type IN ({rel_placeholders})
              AND ie1.book_key != ie2.book_key""",
        (*id_list, *id_list, *rel_types),
    ).fetchall()

    # Aggregate per (source, target) pair
    overlap_map: dict[tuple[str, str], CrossFieldOverlap] = {}
    for row in overlap_rows:
        key = (row["src_label"], row["tgt_label"])
        if key not in overlap_map:
            overlap_map[key] = CrossFieldOverlap(
                source_label=row["src_label"],
                target_label=row["tgt_label"],
                relation_type=row["relation_type"],
                match_type=row["match_type"],
                score=row["score"],
                source_books=[],
                target_books=[],
            )
        o = overlap_map[key]
        if row["src_book"] not in o.source_books:
            o.source_books.append(row["src_book"])
        if row["tgt_book"] not in o.target_books:
            o.target_books.append(row["tgt_book"])

    result.cross_field_overlaps = sorted(
        overlap_map.values(),
        key=lambda o: (-(o.score or 0), o.source_label),
    )

    # ── 5. Global concepts ────────────────────────────────────────────────────
    global_rows = con.execute(
        f"""SELECT c.canonical_label, count(distinct ie.book_key) AS n_books
            FROM concepts c
            JOIN index_entries ie ON ie.concept_id = c.id
            WHERE c.id IN ({placeholders})
            GROUP BY c.id
            HAVING n_books >= ?
            ORDER BY n_books DESC, c.canonical_label""",
        (*id_list, min_books_for_global),
    ).fetchall()

    result.global_concepts = [
        (row["canonical_label"], row["n_books"]) for row in global_rows
    ]

    con.close()
    return result


# ── CLI pretty-print ──────────────────────────────────────────────────────────

def _print_result(r: LookupResult) -> None:
    if not r.concepts:
        print(f"No concepts found for '{r.query}'")
        return

    for c in r.concepts:
        level_tag = f"  [{c.level}]" if c.level else ""
        print(f"\n{c.canonical_label}{level_tag}  (id={c.id}, status={c.status})")

        if c.occurrences:
            print("  Occurrences:")
            for occ in c.occurrences:
                pages = ", ".join(str(p) for p in occ.pages[:8])
                ellipsis = " …" if len(occ.pages) > 8 else ""
                print(f"    {occ.book_key}: {pages}{ellipsis}")

        if c.relations:
            print("  Relations:")
            for rel in c.relations:
                arrow = "→" if rel.direction == "to" else "←"
                score = f"  score={rel.score:.2f}" if rel.score is not None else ""
                mt = f"  [{rel.match_type}]" if rel.match_type else ""
                print(f"    {arrow} {rel.related_term}{mt}{score}")


def _print_zoom(r: ZoomResult) -> None:
    if r.root is None:
        print(f"No concept found for '{r.query}'")
        return
    print(f"{r.root.canonical_label}  (seed, direction={r.direction})")
    for node in r.nodes:
        indent = "  " * node.depth
        score = f"  score={node.score:.2f}" if node.score is not None else ""
        mt = f"  [{node.match_type}]" if node.match_type else ""
        rtype = f"  {node.relation_type}" if node.relation_type else ""
        print(f"{indent}→ {node.canonical_label}{rtype}{mt}{score}")
    if not r.nodes:
        print("  (no typed relations found — run ingest or add curated relations)")


def _print_synthesis(r: SynthesisResult) -> None:
    if not r.seed_concepts:
        print(f"No concepts found for '{r.query}'")
        return

    print(f"=== Synthesis: {r.query} ===\n")

    print(f"Seed concepts ({len(r.seed_concepts)}):")
    for c in r.seed_concepts:
        books = ", ".join(o.book_key for o in c.occurrences)
        print(f"  {c.canonical_label}  [{books}]")

    if r.neighborhood:
        print(f"\nNeighborhood ({r.n_neighborhood} concepts via zoom):")
        for node in r.neighborhood[:12]:
            indent = "  " * node.depth
            score = f"  score={node.score:.2f}" if node.score is not None else ""
            print(f"  {indent}→ {node.canonical_label}{score}")
        if r.n_neighborhood > 12:
            print(f"  … and {r.n_neighborhood - 12} more")

    if r.by_book:
        print(f"\nBy book ({len(r.by_book)} books):")
        for book, labels in sorted(r.by_book.items()):
            print(f"  {book} ({len(labels)} concepts): {', '.join(labels[:5])}"
                  + (" …" if len(labels) > 5 else ""))

    if r.global_concepts:
        print(f"\nGlobal section candidates (≥{2} books):")
        for label, n in r.global_concepts:
            print(f"  {label}  ({n} books)")

    if r.cross_field_overlaps:
        print(f"\nCross-field overlaps ({len(r.cross_field_overlaps)}):")
        for o in r.cross_field_overlaps[:10]:
            src_only, tgt_only = o.bridged_books
            score = f"  score={o.score:.2f}" if o.score is not None else ""
            print(f"  {o.source_label} [{','.join(src_only)}]"
                  f"  ↔  {o.target_label} [{','.join(tgt_only)}]{score}")
        if len(r.cross_field_overlaps) > 10:
            print(f"  … and {len(r.cross_field_overlaps) - 10} more")

    if not r.claims:
        print("\n(No claims yet — populate via curation or LLM extraction)")


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if args and args[0] == "zoom":
        direction = args[1] if len(args) > 1 and args[1] in ("in", "out", "both") else "out"
        term = " ".join(args[2:]) if len(args) > 2 else args[-1] if args else "inflammation"
        rel_types = ("candidate_restriction",)
        _print_zoom(zoom(term, direction=direction, relation_types=rel_types))
    elif args and args[0] == "synthesize":
        term = " ".join(args[1:]) if len(args) > 1 else "EEG"
        _print_synthesis(synthesize(term))
    else:
        term = " ".join(args) if args else "EEG"
        _print_result(lookup(term))
