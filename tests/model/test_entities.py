"""Entity fields on their own, without relationships."""

import json

import pytest

from embed_data_graph import Finding, Laterality, MammogramImage, RegionOfInterest, ViewPosition
from embed_data_graph.clinical.findings import FindingNormalizationWarning, FindingRecordType
from embed_data_graph.core.anatomy import AnatomicalPosition, ClockFacePosition, Quadrant
from embed_data_graph.imaging.rois import Box


def test_finding_key_is_accession_and_number_with_side_as_an_attribute():
    left = Finding("A", Laterality.LEFT, 1)
    right = Finding("A", Laterality.RIGHT, "1")

    assert left.key == right.key == ("A", "1")


def test_finding_number_alone_does_not_make_a_synthetic_record():
    assert Finding("A", Laterality.LEFT, "-9").record_type is FindingRecordType.FINDING


def test_finding_export_keeps_source_codes_anatomy_and_warnings():
    finding = Finding(
        "A",
        "left",
        9,
        anatomical_position=AnatomicalPosition(
            Laterality.LEFT, Quadrant(Laterality.LEFT), ClockFacePosition(2), distance_from_nipple_cm=4.5
        ),
        source_location_codes={"location": "C2"},
        descriptors={"mass": {"shape": "oval"}},
        normalization_warnings=[
            FindingNormalizationWarning(source=None, source_field="location", raw_value="X", code="unknown_location_code", message="Unknown")
        ],
    )

    exported = finding.to_dict()

    assert exported["laterality"] == "L"
    assert exported["source_location_codes"] == {"location": "C2"}
    assert exported["anatomical_position"]["clock_position"]["hour"] == 2
    assert exported["normalization_warnings"][0]["code"] == "unknown_location_code"
    json.dumps(exported)


def test_update_changes_fields_in_place_and_keeps_consumer_attributes():
    class ReviewedImage(MammogramImage):
        pass

    image = ReviewedImage("I")
    image.reviewer = "reader-1"

    assert image.update(laterality="L", view_position="MLO", reviewer="reader-2") is image
    assert (image.laterality, image.view_position, image.reviewer) == (Laterality.LEFT, ViewPosition.MLO, "reader-2")


def test_image_source_identity_is_separate_from_its_model_identity():
    image = MammogramImage("model-id", source_sop_instance_uid="SOP", source_paths="/a.dcm")

    assert image.key == "model-id" and image.source_sop_instance_uid == "SOP"
    assert image.source_paths == {"/a.dcm"}


def test_roi_keeps_raw_geometry_for_validation_to_judge():
    roi = RegionOfInterest(Box(10, 20, 5, 4), "I", "0", confidence=1.5, source_frame_indices=[-1])

    roi.update(coordinates=(11, 21, 6, 5), confidence=-0.25)

    assert roi.coordinates == (11.0, 21.0, 6.0, 5.0)
    assert (roi.height, roi.width, roi.confidence) == (-5.0, -16.0, -0.25)
    assert roi.frame_indices == (-1,)


def test_roi_coordinates_need_four_numbers():
    with pytest.raises(ValueError):
        RegionOfInterest((1, 2, 3), "I", "0")
    with pytest.raises(TypeError):
        RegionOfInterest(("a", 2, 3, 4), "I", "0")


def test_metadata_and_descriptors_are_editable_dicts():
    finding = Finding("A", Laterality.LEFT, "1", descriptors={"shape": "oval"}, metadata={"reader": "x"})
    finding.descriptors["margin"] = "circumscribed"
    finding.metadata["reviewed"] = True

    assert finding.descriptors == {"shape": "oval", "margin": "circumscribed"}
    assert finding.metadata == {"reader": "x", "reviewed": True}
