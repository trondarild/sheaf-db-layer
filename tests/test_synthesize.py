import pytest

from sheaf_db import synthesize, SynthesisResult

CAND = ("candidate_restriction",)


def test_synthesize_no_match_returns_empty(populated_sheaf):
    _, path, _ = populated_sheaf
    result = synthesize("quantum_flux_capacitor", db_path=path, relation_types=CAND)
    assert result.seed_concepts == []
    assert result.neighborhood == []
    assert result.by_book == {}
    assert result.cross_field_overlaps == []
    assert result.global_concepts == []


def test_synthesize_seed_populated(populated_sheaf):
    _, path, _ = populated_sheaf
    result = synthesize("inflammation", db_path=path, relation_types=CAND)
    assert len(result.seed_concepts) == 1
    assert result.seed_concepts[0].canonical_label == "inflammation"


def test_synthesize_neighborhood_populated(populated_sheaf):
    _, path, _ = populated_sheaf
    result = synthesize("inflammation", db_path=path, relation_types=CAND)
    labels = {n.canonical_label for n in result.neighborhood}
    assert "Inflammation" in labels
    assert "neuroinflammation" in labels


def test_synthesize_max_depth_zero_has_no_neighborhood(populated_sheaf):
    _, path, _ = populated_sheaf
    result = synthesize("inflammation", db_path=path, relation_types=CAND, max_depth=0)
    assert result.neighborhood == []


def test_synthesize_n_neighborhood_property(populated_sheaf):
    _, path, _ = populated_sheaf
    result = synthesize("inflammation", db_path=path, relation_types=CAND)
    assert result.n_neighborhood == len(result.neighborhood)


def test_synthesize_by_book_groups_correctly(populated_sheaf):
    _, path, _ = populated_sheaf
    result = synthesize("inflammation", db_path=path, relation_types=CAND)
    # inflammation appears in both books; Inflammation and neuroinflammation in one each
    assert "book_a" in result.by_book
    assert "book_b" in result.by_book
    assert "inflammation" in result.by_book["book_a"]
    assert "inflammation" in result.by_book["book_b"]
    assert "Inflammation" in result.by_book["book_b"]
    assert "neuroinflammation" in result.by_book["book_a"]


def test_synthesize_books_property(populated_sheaf):
    _, path, _ = populated_sheaf
    result = synthesize("inflammation", db_path=path, relation_types=CAND)
    assert set(result.books) == {"book_a", "book_b"}


def test_synthesize_global_concepts_span_multiple_books(populated_sheaf):
    _, path, _ = populated_sheaf
    # "inflammation" appears in book_a and book_b → global candidate
    result = synthesize("inflammation", db_path=path, relation_types=CAND,
                        min_books_for_global=2)
    global_labels = {label for label, _ in result.global_concepts}
    assert "inflammation" in global_labels


def test_synthesize_global_concepts_min_books_respected(populated_sheaf):
    _, path, _ = populated_sheaf
    result = synthesize("inflammation", db_path=path, relation_types=CAND,
                        min_books_for_global=3)
    # Nothing in the fixture spans 3+ books
    assert result.global_concepts == []


def test_synthesize_global_concept_book_count(populated_sheaf):
    _, path, _ = populated_sheaf
    result = synthesize("inflammation", db_path=path, relation_types=CAND,
                        min_books_for_global=2)
    infl_entry = next(
        (label, n) for label, n in result.global_concepts if label == "inflammation"
    )
    assert infl_entry[1] == 2


def test_synthesize_cross_field_overlaps_found(populated_sheaf):
    _, path, _ = populated_sheaf
    result = synthesize("inflammation", db_path=path, relation_types=CAND)
    # inflammation (book_a,book_b) → Inflammation (book_b): book_a ≠ book_b → overlap
    # inflammation (book_a,book_b) → neuroinflammation (book_a): book_b ≠ book_a → overlap
    assert len(result.cross_field_overlaps) == 2


def test_synthesize_cross_field_overlap_source_target_labels(populated_sheaf):
    _, path, _ = populated_sheaf
    result = synthesize("inflammation", db_path=path, relation_types=CAND)
    pairs = {(o.source_label, o.target_label) for o in result.cross_field_overlaps}
    assert ("inflammation", "Inflammation") in pairs
    assert ("inflammation", "neuroinflammation") in pairs


def test_synthesize_cross_field_overlap_books_differ(populated_sheaf):
    _, path, _ = populated_sheaf
    result = synthesize("inflammation", db_path=path, relation_types=CAND)
    for o in result.cross_field_overlaps:
        src_only, tgt_only = o.bridged_books
        # At least one book must be unique to one side
        assert src_only or tgt_only


def test_synthesize_no_cross_field_when_single_book(populated_sheaf):
    _, path, _ = populated_sheaf
    # cytokine appears only in book_a and has no relations in the fixture
    result = synthesize("cytokine", db_path=path, relation_types=CAND)
    assert result.cross_field_overlaps == []


def test_synthesize_cross_field_sorted_by_score_desc(populated_sheaf):
    _, path, _ = populated_sheaf
    result = synthesize("inflammation", db_path=path, relation_types=CAND)
    scores = [o.score for o in result.cross_field_overlaps if o.score is not None]
    assert scores == sorted(scores, reverse=True)


def test_synthesize_claims_empty_initially(populated_sheaf):
    _, path, _ = populated_sheaf
    result = synthesize("inflammation", db_path=path, relation_types=CAND)
    assert result.claims == []


def test_synthesize_result_type(populated_sheaf):
    _, path, _ = populated_sheaf
    result = synthesize("inflammation", db_path=path, relation_types=CAND)
    assert isinstance(result, SynthesisResult)
