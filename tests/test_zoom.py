import pytest

from sheaf_db import zoom, ZoomResult


CAND = ("candidate_restriction",)


def test_zoom_no_match_returns_empty(populated_sheaf):
    _, path, _ = populated_sheaf
    result = zoom("quantum_flux_capacitor", db_path=path, relation_types=CAND)
    assert result.root is None
    assert result.nodes == []


def test_zoom_root_set(populated_sheaf):
    _, path, _ = populated_sheaf
    result = zoom("inflammation", direction="out", relation_types=CAND, db_path=path)
    assert result.root is not None
    assert result.root.canonical_label == "inflammation"
    assert result.root.depth == 0
    assert result.root.relation_type is None


def test_zoom_out_finds_targets(populated_sheaf):
    _, path, _ = populated_sheaf
    result = zoom("inflammation", direction="out", relation_types=CAND, db_path=path)
    labels = {n.canonical_label for n in result.nodes}
    assert "Inflammation" in labels
    assert "neuroinflammation" in labels


def test_zoom_out_depth_is_one(populated_sheaf):
    _, path, _ = populated_sheaf
    result = zoom("inflammation", direction="out", relation_types=CAND, db_path=path)
    assert all(n.depth == 1 for n in result.nodes)


def test_zoom_in_finds_sources(populated_sheaf):
    _, path, _ = populated_sheaf
    result = zoom("Inflammation", direction="in", relation_types=CAND, db_path=path)
    labels = {n.canonical_label for n in result.nodes}
    assert "inflammation" in labels


def test_zoom_in_neuroinflammation(populated_sheaf):
    _, path, _ = populated_sheaf
    result = zoom("neuroinflammation", direction="in", relation_types=CAND, db_path=path)
    labels = {n.canonical_label for n in result.nodes}
    assert "inflammation" in labels


def test_zoom_both_combines_directions(populated_sheaf):
    _, path, _ = populated_sheaf
    # "Inflammation" has one incoming edge (from inflammation) and no outgoing in fixture
    out_result = zoom("Inflammation", direction="out", relation_types=CAND, db_path=path)
    in_result  = zoom("Inflammation", direction="in",  relation_types=CAND, db_path=path)
    both_result = zoom("Inflammation", direction="both", relation_types=CAND, db_path=path)
    both_labels = {n.canonical_label for n in both_result.nodes}
    for n in in_result.nodes:
        assert n.canonical_label in both_labels


def test_zoom_max_depth_zero_returns_no_nodes(populated_sheaf):
    _, path, _ = populated_sheaf
    result = zoom("inflammation", direction="out", relation_types=CAND, max_depth=0, db_path=path)
    assert result.root is not None
    assert result.nodes == []


def test_zoom_max_depth_limits_traversal(populated_sheaf):
    sheaf_con, path, term_to_concept = populated_sheaf
    # Add a depth-2 chain: neuroinflammation → cytokine
    neuro_id = term_to_concept[3]   # neuroinflammation
    cyto_id  = term_to_concept[4]   # cytokine
    sheaf_con.execute(
        "INSERT INTO concept_relations (source_concept_id, target_concept_id, "
        "relation_type, match_type, score, confidence) VALUES (?,?,'candidate_restriction','containment',0.5,0.5)",
        (neuro_id, cyto_id),
    )
    sheaf_con.commit()

    result_d1 = zoom("inflammation", direction="out", relation_types=CAND, max_depth=1, db_path=path)
    result_d2 = zoom("inflammation", direction="out", relation_types=CAND, max_depth=2, db_path=path)

    labels_d1 = {n.canonical_label for n in result_d1.nodes}
    labels_d2 = {n.canonical_label for n in result_d2.nodes}

    assert "cytokine" not in labels_d1
    assert "cytokine" in labels_d2


def test_zoom_cycle_detection(populated_sheaf):
    sheaf_con, path, term_to_concept = populated_sheaf
    # Create a cycle: Inflammation → inflammation (back-edge)
    infl_id  = term_to_concept[1]   # inflammation
    Infl_id  = term_to_concept[2]   # Inflammation
    sheaf_con.execute(
        "INSERT INTO concept_relations (source_concept_id, target_concept_id, "
        "relation_type, match_type, score, confidence) VALUES (?,?,'candidate_restriction','case',1.0,1.0)",
        (Infl_id, infl_id),
    )
    sheaf_con.commit()

    # Should terminate and not visit inflammation twice
    result = zoom("inflammation", direction="out", relation_types=CAND, max_depth=5, db_path=path)
    visited = [n.canonical_label for n in result.nodes]
    assert visited.count("inflammation") == 0   # seed not re-visited
    assert visited.count("Inflammation") == 1   # appears exactly once


def test_zoom_at_depth(populated_sheaf):
    _, path, _ = populated_sheaf
    result = zoom("inflammation", direction="out", relation_types=CAND, db_path=path)
    assert result.at_depth(1) == result.nodes
    assert result.at_depth(2) == []


def test_zoom_node_path_from_root(populated_sheaf):
    _, path, _ = populated_sheaf
    result = zoom("inflammation", direction="out", relation_types=CAND, db_path=path)
    for node in result.nodes:
        assert node.path[0] == "inflammation"
        assert node.path[-1] == node.canonical_label


def test_zoom_node_carries_relation_metadata(populated_sheaf):
    _, path, _ = populated_sheaf
    result = zoom("inflammation", direction="out", relation_types=CAND, db_path=path)
    case_node = next(n for n in result.nodes if n.canonical_label == "Inflammation")
    assert case_node.match_type == "case"
    assert case_node.score == pytest.approx(1.0)
    assert case_node.relation_type == "candidate_restriction"


def test_zoom_semantic_types_return_nothing_without_typed_relations(populated_sheaf):
    # Fixture only has candidate_restriction; ZOOM_RELATION_TYPES default returns empty
    _, path, _ = populated_sheaf
    from sheaf_db import ZOOM_RELATION_TYPES
    result = zoom("inflammation", direction="out", relation_types=ZOOM_RELATION_TYPES, db_path=path)
    assert result.root is not None
    assert result.nodes == []


def test_zoom_invalid_direction_raises(populated_sheaf):
    _, path, _ = populated_sheaf
    with pytest.raises(ValueError):
        zoom("inflammation", direction="sideways", db_path=path)
