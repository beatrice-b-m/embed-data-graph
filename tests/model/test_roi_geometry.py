import math
import pytest
from embed_data_graph import MammogramImage, RegionOfInterest, ImageModality


def roi(coordinates, *, image_id="img-1", source_value="0", **fields):
    return RegionOfInterest(coordinates, image_id, source_value, **fields)


def test_roi_uses_canonical_half_open_yxyx_geometry() -> None:
    observed = roi((10, 20, 30, 50))

    assert observed.y_min == 10
    assert observed.x_min == 20
    assert observed.y_max == 30
    assert observed.x_max == 50
    assert observed.height == 20
    assert observed.width == 30
    assert observed.area == 600
    assert observed.centroid == (20, 35)


def test_roi_iou_and_containment_ratio() -> None:
    observed = roi((0, 0, 10, 10), source_value="observed")
    overlapping = roi((5, 5, 15, 15), source_value="overlap")
    container = roi((-5, -5, 20, 20), source_value="container")

    assert observed.intersection_area(overlapping) == 25
    assert observed.iou(overlapping) == pytest.approx(25 / 175)
    assert observed.containment_ratio(overlapping) == pytest.approx(0.25)
    assert observed.containment_ratio(container) == 1.0
    assert overlapping.containment_ratio(observed) == pytest.approx(0.25)


def test_roi_center_distance() -> None:
    observed = roi((0, 0, 10, 10), source_value="observed")
    other = roi((6, 8, 16, 18), source_value="other")

    assert observed.center_distance(other) == pytest.approx(10.0)
    assert observed.center_distance(observed) == 0.0
    assert math.isclose(
        other.center_distance(observed), observed.center_distance(other)
    )


def test_embed_roi_factory_preserves_inclusive_source_geometry():
    observed = RegionOfInterest.from_embed_coordinates((100,200,150,250), image_id="I", roi_key="0")
    assert observed.coordinates == (100,200,151,251)
    assert observed.area == 2601
    assert observed.source_coordinates == (100,200,150,250)
    pixel = RegionOfInterest.from_embed_coordinates((5,7,5,7), image_id="I", roi_key="1")
    assert pixel.area == 1


def test_resize_and_realign_preserve_original_geometry_and_frame_facts():
    original = roi((10,20,30,50), source_frame_indices=(17,), annotation_source="embed")
    resized = original.resize(scale_y=0.5, scale_x=2)
    aligned = resized.realign(offset_y=4, offset_x=-10, coordinate_frame_id="aligned")
    assert resized.coordinates == (5,40,15,100)
    assert aligned.coordinates == (9,30,19,90)
    assert original.coordinates == (10,20,30,50)
    assert aligned.frame_indices == (17,)


def test_image_identity_and_supplied_dbt_dimensions():
    image = MammogramImage("I", modality="dbt", height=2048, width=1536, frame_count=72, source_sop_instance_uid="SOP")
    assert image.modality is ImageModality.DBT
    assert image.identity == "I" and image.image_shape == (2048,1536)
    assert image.frame_count == 72
