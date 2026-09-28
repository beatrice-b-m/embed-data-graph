from __future__ import annotations

from embed_data_graph.sources.embed.magview import normalize_magview_location
from embed_data_graph.core.anatomy import (
    AnatomicalLocationCategory,
    DepthThird,
    MedialLateralAxis,
    SuperiorInferiorAxis,
)
from embed_data_graph.core.primitives import Laterality


def warning_codes(result: object) -> set[str]:
    return {warning.code for warning in result.warnings}


def test_clock_mapping_is_laterality_aware() -> None:
    left = normalize_magview_location(laterality=Laterality.LEFT, clock_code="3")
    right = normalize_magview_location(laterality=Laterality.RIGHT, clock_code="3")

    assert left.position.clock_position.hour == 3
    assert left.position.quadrant.ml is MedialLateralAxis.LATERAL
    assert right.position.quadrant.ml is MedialLateralAxis.MEDIAL
    assert left.position.quadrant.si is SuperiorInferiorAxis.CENTRAL
    assert right.position.quadrant.si is SuperiorInferiorAxis.CENTRAL


def test_location_column_clock_code_uses_clock_mapping() -> None:
    result = normalize_magview_location(laterality="L", location_code="10")

    assert result.position.clock_position.hour == 10
    assert result.position.quadrant.ml is MedialLateralAxis.MEDIAL
    assert result.position.quadrant.si is SuperiorInferiorAxis.SUPERIOR
    assert any(
        item.field == "location_code" and item.normalized_kind == "clock"
        for item in result.evidence
    )


def test_explicit_depth_takes_precedence_over_location_default() -> None:
    result = normalize_magview_location(
        laterality="R",
        location_code="S",
        depth_code="P",
    )

    assert result.position.location_category is AnatomicalLocationCategory.SUBAREOLAR
    assert result.position.quadrant.ml is MedialLateralAxis.CENTRAL
    assert result.position.quadrant.si is SuperiorInferiorAxis.CENTRAL
    assert result.position.quadrant.depth is DepthThird.POSTERIOR
    assert "conflicting_depth" in warning_codes(result)


def test_named_retroareolar_location_is_preserved() -> None:
    result = normalize_magview_location(laterality="L", location_code="retroareolar")

    assert result.position.location_category is AnatomicalLocationCategory.RETROAREOLAR
    assert result.position.quadrant.ml is MedialLateralAxis.CENTRAL
    assert result.position.quadrant.si is SuperiorInferiorAxis.CENTRAL
    assert result.position.quadrant.depth is DepthThird.ANTERIOR


def test_named_central_location_is_preserved() -> None:
    result = normalize_magview_location(laterality="R", location_code="C")

    assert result.position.location_category is AnatomicalLocationCategory.CENTRAL
    assert result.position.quadrant.ml is MedialLateralAxis.CENTRAL
    assert result.position.quadrant.si is SuperiorInferiorAxis.CENTRAL


def test_named_axillary_tail_location_is_preserved() -> None:
    result = normalize_magview_location(laterality="L", location_code="T")

    assert result.position.location_category is AnatomicalLocationCategory.AXILLARY_TAIL
    assert result.position.quadrant.si is SuperiorInferiorAxis.SUPERIOR
    assert result.position.quadrant.depth is DepthThird.POSTERIOR


def test_unknown_codes_are_reported_without_failing() -> None:
    result = normalize_magview_location(
        laterality="L",
        location_code="??",
        depth_code="deep",
        clock_code="13",
    )

    assert result.position.laterality is Laterality.LEFT
    assert result.position.quadrant.ml is MedialLateralAxis.UNKNOWN
    assert result.position.quadrant.depth is DepthThird.UNKNOWN
    assert {
        "unknown_location_code",
        "unknown_depth_code",
        "unknown_clock_code",
    }.issubset(warning_codes(result))


def test_clock_quadrant_conflict_warns_and_prefers_clock_axes() -> None:
    result = normalize_magview_location(
        laterality="L",
        clock_code="3",
        location_code="IN",
    )

    assert result.position.clock_position.hour == 3
    assert result.position.quadrant.ml is MedialLateralAxis.LATERAL
    assert result.position.quadrant.si is SuperiorInferiorAxis.CENTRAL
    assert "conflicting_clock_quadrant" in warning_codes(result)
