from __future__ import annotations

import pytest

from embed_data_graph.core.primitives import (
    FovHorizontalFlip,
    FovRotation,
    ImageModality,
    Laterality,
    OrientationDirection,
    PatientOrientation,
    ViewPosition,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("L", Laterality.LEFT),
        ("left", Laterality.LEFT),
        ("RT", Laterality.RIGHT),
        ("both", Laterality.BILATERAL),
        ("", Laterality.UNKNOWN),
        (None, Laterality.UNKNOWN),
    ],
)
def test_laterality_coerce(value: object, expected: Laterality) -> None:
    assert Laterality.coerce(value) is expected


def test_laterality_expands_bilateral_without_guessing_unknown() -> None:
    assert Laterality.BILATERAL.expand() == (Laterality.LEFT, Laterality.RIGHT)
    assert Laterality.LEFT.expand() == (Laterality.LEFT,)
    assert Laterality.UNKNOWN.expand() == ()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("CC", ViewPosition.CC),
        ("left mlo", ViewPosition.MLO),
        ("R-ML spot", ViewPosition.ML),
        ("xccL", ViewPosition.XCCL),
        ("nonsense", ViewPosition.UNKNOWN),
    ],
)
def test_view_position_coerce(value: object, expected: ViewPosition) -> None:
    assert ViewPosition.coerce(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2D", ImageModality.FFDM),
        ("ffdm", ImageModality.FFDM),
        ("3D", ImageModality.DBT),
        ("tomosynthesis", ImageModality.DBT),
        ("cview", ImageModality.S2D),
        ("synthetic 2d", ImageModality.S2D),
    ],
)
def test_image_modality_coerce(value: object, expected: ImageModality) -> None:
    assert ImageModality.coerce(value) is expected


def test_patient_orientation_coerces_string_tuple() -> None:
    orientation = PatientOrientation.coerce("('P', 'R')")

    assert orientation.row is OrientationDirection.P
    assert orientation.column is OrientationDirection.R
    assert orientation.exact
    assert orientation.as_tuple() == ("P", "R")


def test_patient_orientation_allows_unknown_components() -> None:
    orientation = PatientOrientation.coerce(("P", "bad"))

    assert orientation.row is OrientationDirection.P
    assert orientation.column is OrientationDirection.UNKNOWN
    assert not orientation.exact


@pytest.mark.parametrize("value", ["P", ("P",), ("P", "R", "L"), 3])
def test_patient_orientation_rejects_invalid_shapes(value: object) -> None:
    with pytest.raises(ValueError):
        PatientOrientation.coerce(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, FovRotation.NONE),
        ("0.0", FovRotation.NONE),
        (180, FovRotation.FULL),
        ("180.0", FovRotation.FULL),
        ("90", FovRotation.UNKNOWN),
    ],
)
def test_fov_rotation_coerce(value: object, expected: FovRotation) -> None:
    assert FovRotation.coerce(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("YES", FovHorizontalFlip.YES),
        ("y", FovHorizontalFlip.YES),
        (1, FovHorizontalFlip.YES),
        ("NO", FovHorizontalFlip.NO),
        ("false", FovHorizontalFlip.NO),
        ("maybe", FovHorizontalFlip.UNKNOWN),
    ],
)
def test_fov_horizontal_flip_coerce(
    value: object,
    expected: FovHorizontalFlip,
) -> None:
    assert FovHorizontalFlip.coerce(value) is expected
