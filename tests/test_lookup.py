import pytest

from sheaf_db import lookup


def test_lookup_exact_match(populated_sheaf):
    _, path, _ = populated_sheaf
    result = lookup("inflammation", db_path=path)
    assert len(result.concepts) == 1
    assert result.concepts[0].canonical_label == "inflammation"


def test_lookup_case_insensitive(populated_sheaf):
    _, path, _ = populated_sheaf
    # "Inflammation" exists as its own raw concept; "INFLAMMATION" should still find
    # case-insensitive matches
    result = lookup("INFLAMMATION", db_path=path)
    assert len(result.concepts) >= 1
    labels = {c.canonical_label.lower() for c in result.concepts}
    assert "inflammation" in labels


def test_lookup_substring_fallback(populated_sheaf):
    _, path, _ = populated_sheaf
    result = lookup("neuro", db_path=path)
    assert any("neuroinflammation" in c.canonical_label for c in result.concepts)


def test_lookup_no_match_returns_empty(populated_sheaf):
    _, path, _ = populated_sheaf
    result = lookup("quantum_flux_capacitor", db_path=path)
    assert result.concepts == []
    assert result.books == []


def test_lookup_occurrences(populated_sheaf):
    _, path, _ = populated_sheaf
    result = lookup("inflammation", db_path=path)
    occ = result.concepts[0].occurrences
    books = {o.book_key for o in occ}
    assert books == {"book_a", "book_b"}
    pages_a = next(o.pages for o in occ if o.book_key == "book_a")
    assert "10" in pages_a


def test_lookup_outgoing_relations(populated_sheaf):
    _, path, _ = populated_sheaf
    result = lookup("inflammation", db_path=path)
    outgoing = [r for r in result.concepts[0].relations if r.direction == "to"]
    related = {r.related_term for r in outgoing}
    assert "Inflammation" in related
    assert "neuroinflammation" in related


def test_lookup_incoming_relations(populated_sheaf):
    _, path, _ = populated_sheaf
    result = lookup("neuroinflammation", db_path=path)
    incoming = [r for r in result.concepts[0].relations if r.direction == "from"]
    assert any(r.related_term == "inflammation" for r in incoming)


def test_lookup_relation_scores(populated_sheaf):
    _, path, _ = populated_sheaf
    result = lookup("inflammation", db_path=path)
    outgoing = [r for r in result.concepts[0].relations if r.direction == "to"]
    case_rel = next(r for r in outgoing if r.match_type == "case")
    assert case_rel.score == pytest.approx(1.0)
    containment_rel = next(r for r in outgoing if r.match_type == "containment")
    assert containment_rel.score == pytest.approx(0.6)


def test_lookup_books_property(populated_sheaf):
    _, path, _ = populated_sheaf
    result = lookup("inflammation", db_path=path)
    assert set(result.books) == {"book_a", "book_b"}


def test_lookup_skips_deprecated(populated_sheaf):
    sheaf_con, path, term_to_concept = populated_sheaf
    # Deprecate the "cytokine" concept
    concept_id = term_to_concept[4]
    sheaf_con.execute("UPDATE concepts SET status='deprecated' WHERE id=?", (concept_id,))
    sheaf_con.commit()
    result = lookup("cytokine", db_path=path)
    assert result.concepts == []
