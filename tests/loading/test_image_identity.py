"""Source SOP identity of image and ROI rows, independent of the storage layout."""

import pytest

from embed_data_graph import load_embed

ANON_PATH = "/mnt/data/anon/1.2.3.dcm"
COHORT_PATH = "/data/cohort2/P1/S1/SE1/1.2.3.dcm"


def codes(report):
    return [issue.code for issue in report.issues]


@pytest.mark.parametrize(
    ("row", "columns"),
    [
        ({"anon_dicom_path": ANON_PATH, "empi_anon": "P1", "acc_anon": "A1"}, None),
        (
            {"original_path": r"D:\originals\2019\exam 7\1.2.3.DCM", "empi": "P1", "acc": "A1"},
            {"images": {"source_path": "original_path", "patient_id": "empi", "accession": "acc"}},
        ),
    ],
    ids=["anonymized", "original"],
)
def test_filename_names_the_source_sop_outside_the_cohort_layout(row, columns):
    report = load_embed(images=[row], columns=columns)

    (image,) = report.graph.images
    assert image.source_sop_instance_uid == "1.2.3"
    assert report.graph.source_image("1.2.3") is image
    assert image.patient_id == "P1" and image.accession_number == "A1"
    assert codes(report) == []


def test_explicit_sop_column_loads_without_a_layout_issue():
    report = load_embed(
        images=[{"anon_dicom_path": "/scratch/export", "SOPInstanceUID": "1.2.3"}],
        columns={"images": {"source_sop_instance_uid": "SOPInstanceUID"}},
    )

    image = report.graph.source_image("1.2.3")
    assert image is not None and "/scratch/export" in image.source_paths
    assert codes(report) == []


def test_explicit_sop_wins_over_a_different_filename():
    report = load_embed(
        images=[{"anon_dicom_path": ANON_PATH, "SOPInstanceUID": "9.9.9"}],
        columns={"images": {"source_sop_instance_uid": "SOPInstanceUID"}},
    )

    assert report.graph.source_image("9.9.9") is not None
    assert report.graph.source_image("1.2.3") is None
    assert codes(report) == ["source_sop_path_mismatch"]


def test_explicit_sop_equal_to_the_filename_is_not_a_mismatch():
    report = load_embed(
        images=[{"anon_dicom_path": ANON_PATH, "SOPInstanceUID": "1.2.3"}],
        columns={"images": {"source_sop_instance_uid": "SOPInstanceUID"}},
    )

    assert report.graph.source_image("1.2.3") is not None
    assert codes(report) == []


def test_cohort_layout_still_supplies_patient_study_and_series():
    report = load_embed(images=[{"anon_dicom_path": COHORT_PATH}])

    image = report.graph.source_image("1.2.3")
    assert (image.patient_id, image.study_instance_uid, image.series_instance_uid) == ("P1", "S1", "SE1")
    assert codes(report) == []


def test_cohort_layout_still_reports_a_disagreeing_patient_column():
    report = load_embed(images=[{"anon_dicom_path": COHORT_PATH, "empi_anon": "P2"}])

    assert report.graph.source_image("1.2.3").patient_id == "P2"
    assert codes(report) == ["source_patient_path_mismatch"]


def test_roi_row_attaches_to_the_image_loaded_from_the_same_path():
    graph = load_embed(images=[{"anon_dicom_path": ANON_PATH}]).graph

    report = load_embed(rois=[{"anon_dicom_path": ANON_PATH, "ROI_coords": "[(1, 2, 3, 4)]"}], into=graph)

    (image,) = graph.images
    assert len(image.rois) == 1
    assert codes(report) == []


def test_roi_row_at_another_location_attaches_by_filename_sop():
    graph = load_embed(images=[{"anon_dicom_path": ANON_PATH}]).graph
    relocated = "/archive/rois/1.2.3.dcm"

    load_embed(rois=[{"anon_dicom_path": relocated, "ROI_coords": "[(1, 2, 3, 4)]"}], into=graph)

    (image,) = graph.images
    assert len(image.rois) == 1
    assert relocated in image.source_paths and ANON_PATH in image.source_paths


def test_image_row_attaches_to_the_shell_an_roi_row_registered():
    graph = load_embed(rois=[{"anon_dicom_path": "/archive/rois/1.2.3.dcm", "ROI_coords": "[(1, 2, 3, 4)]"}]).graph

    load_embed(images=[{"anon_dicom_path": ANON_PATH, "Rows": 64}], into=graph)

    (image,) = graph.images
    assert image.source_sop_instance_uid == "1.2.3"
    assert image.height == 64 and len(image.rois) == 1


@pytest.mark.parametrize("path", ["/mnt/data/anon/1.2.3", "/mnt/data/anon/1.2.3.png", "/mnt/data/anon/.dcm"])
def test_path_that_names_no_sop_leaves_the_image_unresolved(path):
    report = load_embed(images=[{"anon_dicom_path": path}])

    assert report.graph.images == ()
    assert codes(report) == ["unresolved_image_identity"]


def test_path_that_names_no_sop_loads_under_an_explicit_image_id():
    report = load_embed(
        images=[{"anon_dicom_path": "/mnt/data/anon/1.2.3", "toolkit": "img-1"}],
        columns={"images": {"image_id": "toolkit"}},
    )

    assert report.graph.image("img-1") is not None
    assert codes(report) == []
