from __future__ import annotations

import pytest

from embed_data_graph.core.anatomy import (
    ClockFacePosition,
    ContinuousAnatomicalPosition,
    DepthThird,
    MedialLateralAxis,
    Quadrant,
    SuperiorInferiorAxis,
)
from embed_data_graph.core.primitives import Laterality


@pytest.mark.parametrize(
    ("value", "hour"),
    [
        (1, 1),
        ("1", 1),
        ("C10", 10),
        ("12:00", 12),
    ],
)
def test_clock_face_position_coerce(value: object, hour: int) -> None:
    assert ClockFacePosition.coerce(value) == ClockFacePosition(hour)


@pytest.mark.parametrize("value", ["clock", ""])
def test_clock_face_position_rejects_invalid_values(value: object) -> None:
    with pytest.raises(ValueError):
        ClockFacePosition.coerce(value)


@pytest.mark.parametrize(
    ("hour", "left_ml", "right_ml", "si"),
    [
        (12, MedialLateralAxis.CENTRAL, MedialLateralAxis.CENTRAL, SuperiorInferiorAxis.SUPERIOR),
        (3, MedialLateralAxis.LATERAL, MedialLateralAxis.MEDIAL, SuperiorInferiorAxis.CENTRAL),
        (6, MedialLateralAxis.CENTRAL, MedialLateralAxis.CENTRAL, SuperiorInferiorAxis.INFERIOR),
        (9, MedialLateralAxis.MEDIAL, MedialLateralAxis.LATERAL, SuperiorInferiorAxis.CENTRAL),
    ],
)
def test_clock_face_mapping_mirrors_by_laterality(
    hour: int,
    left_ml: MedialLateralAxis,
    right_ml: MedialLateralAxis,
    si: SuperiorInferiorAxis,
) -> None:
    clock = ClockFacePosition(hour)

    left = clock.to_quadrant(Laterality.LEFT)
    right = clock.to_quadrant(Laterality.RIGHT)

    assert left.ml is left_ml
    assert right.ml is right_ml
    assert left.si is si
    assert right.si is si


def test_clock_face_mapping_requires_unilateral_side() -> None:
    with pytest.raises(ValueError):
        ClockFacePosition(3).to_quadrant(Laterality.BILATERAL)


def test_quadrant_merge_fills_only_unknown_axes() -> None:
    base = Quadrant(
        laterality=Laterality.LEFT,
        ml=MedialLateralAxis.LATERAL,
        depth=DepthThird.UNKNOWN,
    )
    supplement = Quadrant(
        laterality=Laterality.LEFT,
        ml=MedialLateralAxis.MEDIAL,
        si=SuperiorInferiorAxis.SUPERIOR,
        depth=DepthThird.POSTERIOR,
    )

    merged = base.merge_missing(supplement)

    assert merged.ml is MedialLateralAxis.LATERAL
    assert merged.si is SuperiorInferiorAxis.SUPERIOR
    assert merged.depth is DepthThird.POSTERIOR


def test_quadrant_merge_rejects_side_mismatch() -> None:
    with pytest.raises(ValueError):
        Quadrant(Laterality.LEFT).merge_missing(Quadrant(Laterality.RIGHT))


def test_continuous_position_reports_observable_axes() -> None:
    position = ContinuousAnatomicalPosition(
        laterality=Laterality.RIGHT,
        ml_value=0.2,
        depth_value=1.7,
        coordinate_frame_id="image-1",
    )

    assert position.observable_axes == ("ml", "depth")


@pytest.mark.parametrize(
    ("ml_value", "si_value", "depth_value", "expected"),
    [
        (-0.6, -0.6, 0.1, (MedialLateralAxis.MEDIAL, SuperiorInferiorAxis.INFERIOR, DepthThird.ANTERIOR)),
        (0.0, 0.0, 1.0, (MedialLateralAxis.CENTRAL, SuperiorInferiorAxis.CENTRAL, DepthThird.MIDDLE)),
        (0.6, 0.6, 1.8, (MedialLateralAxis.LATERAL, SuperiorInferiorAxis.SUPERIOR, DepthThird.POSTERIOR)),
        (None, None, None, (MedialLateralAxis.UNKNOWN, SuperiorInferiorAxis.UNKNOWN, DepthThird.UNKNOWN)),
    ],
)
def test_continuous_position_quantizes_to_discrete_quadrant(
    ml_value: float,
    si_value: float,
    depth_value: float,
    expected: tuple[MedialLateralAxis, SuperiorInferiorAxis, DepthThird],
) -> None:
    quadrant = ContinuousAnatomicalPosition(
        laterality=Laterality.LEFT,
        ml_value=ml_value,
        si_value=si_value,
        depth_value=depth_value,
    ).to_quadrant()

    assert (quadrant.ml, quadrant.si, quadrant.depth) == expected


def test_out_of_range_clock_hour_is_preserved_for_optional_validation():
    from embed_data_graph.core.validation import validate
    clock = ClockFacePosition(13)
    assert clock.hour == 13
    assert clock.to_quadrant(Laterality.LEFT).ml is MedialLateralAxis.UNKNOWN
    assert not validate(clock).valid
