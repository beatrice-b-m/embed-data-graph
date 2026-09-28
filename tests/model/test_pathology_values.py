"""Pathology descriptor slots."""

import pytest

from embed_data_graph.clinical.pathology import PathologyObservation


def test_descriptor_occurrences_keep_their_slot_and_repeated_values():
    first = PathologyObservation("ADH", "path1", 1)
    second = PathologyObservation("ADH", "path2", 2)

    assert first.descriptor == second.descriptor
    assert first.identity != second.identity


def test_descriptor_slot_ordinal_is_one_based():
    with pytest.raises(ValueError):
        PathologyObservation("ADH", "path0", 0)
