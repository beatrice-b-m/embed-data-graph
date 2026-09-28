"""Loading in patient batches builds the same graph as one full load."""
import pytest

from benchmarks.graph_loading import assert_cardinality, fixture
from embed_data_graph import load_embed


@pytest.mark.parametrize("size", [10, 20, 40])
def test_multigrain_full_and_complete_patient_batches(size):
    tables = fixture(size)
    full = load_embed(**tables).graph
    assert_cardinality(full, size)
    batched = load_embed().graph
    for offset in range(0, size, 5):
        load_embed(magview=tables["magview"][offset * 4:(offset + 5) * 4],
                   images=tables["images"][offset:offset + 5],
                   registry=tables["registry"][offset:offset + 5], into=batched)
    assert_cardinality(batched, size)


def test_late_registry_resolution_visits_only_pending_neighbors():
    tables = fixture(10)
    graph = load_embed(magview=tables["magview"], images=tables["images"]).graph
    assert graph.unresolved_references
    load_embed(registry=tables["registry"], into=graph)
    assert_cardinality(graph, 10)
    assert not graph.unresolved_references
