"""Loading whole tables into a subset graph with ``parents="existing"``."""

import pytest

from embed_data_model import DatasetGraph, load_embed


MAGVIEW = [
    {"empi_anon": "P1", "acc_anon": "A1", "numfind": 1, "side": "L", "desc": "screening"},
    {"empi_anon": "P1", "acc_anon": "A2", "numfind": 1, "side": "R", "desc": "diagnostic"},
    {"empi_anon": "P2", "acc_anon": "A3", "numfind": 1, "side": "L", "desc": "diagnostic"},
]


def image_row(patient, accession, sop, **extra):
    row = {"empi_anon": patient, "acc_anon": accession, "anon_dicom_path": f"cohort1/{patient}/S/SE/{sop}.dcm"}
    return {**row, **extra}


IMAGES = [
    image_row("P1", "A1", "I1", ROI_coords="[(1, 2, 5, 6)]"),
    image_row("P1", "A2", "I2"),
    image_row("P2", "A3", "I3"),
    image_row("P9", "A9", "I9"),
]


def screening_subset():
    source = load_embed(magview=MAGVIEW).graph
    return source, source.partition(level="exam", key=lambda exam: exam.description)["screening"]


def outside(report):
    return {issue.context["table"]: issue.context["rows"] for issue in report.issues if issue.code == "rows_outside_graph"}


def test_whole_image_table_attaches_to_a_subset_without_growing_it():
    source, subset = screening_subset()
    patient, exam, finding = subset.patient("P1"), subset.exam("A1"), subset.finding("A1", "1")
    exam.reviewer = "BM"

    report = load_embed(images=IMAGES, into=subset, parents="existing")

    assert [item.accession_number for item in subset.exams] == ["A1"]
    assert [item.patient_id for item in subset.patients] == ["P1"]
    assert (subset.patient("P1"), subset.exam("A1"), subset.finding("A1", "1")) == (patient, exam, finding)
    assert subset.exam("A1") is exam and exam.reviewer == "BM"
    assert [image.image_id for image in exam.images] == ["I1"]
    assert len(subset.image("I1").rois) == 1
    assert outside(report) == {"images": 3}
    assert {issue.severity.value for issue in report.issues} == {"info"}
    assert source.images == ()


def test_default_still_creates_the_patients_and_exams_rows_address():
    _, subset = screening_subset()

    load_embed(images=IMAGES, into=subset)

    assert {item.accession_number for item in subset.exams} == {"A1", "A2", "A3", "A9"}


def test_existing_exams_gain_new_children_but_new_exams_are_not_created():
    graph = load_embed(magview=MAGVIEW[:1]).graph

    report = load_embed(
        magview=[
            {"empi_anon": "P1", "acc_anon": "A1", "numfind": 2, "side": "R"},
            {"empi_anon": "P1", "acc_anon": "A2", "numfind": 1, "side": "R"},
        ],
        exams=[{"acc_anon": "A4", "empi_anon": "P1", "desc": "new"}],
        findings=[{"acc_anon": "A5", "numfind": 1}],
        into=graph,
        parents="existing",
    )

    assert [item.accession_number for item in graph.exams] == ["A1"]
    assert [item.finding_number for item in graph.exam("A1").findings] == ["1", "2"]
    assert outside(report) == {"magview": 1, "exams": 1, "findings": 1}


def test_a_row_claiming_an_absent_patient_for_a_present_exam_is_not_loaded():
    graph = load_embed(magview=MAGVIEW[:1]).graph

    load_embed(images=[image_row("P2", "A1", "I1")], into=graph, parents="existing")

    assert graph.images == ()
    assert set(graph.exam("A1").asserted_patient_ids) == {"P1"}
    assert graph.patient("P2") is None


def test_path_patient_counts_when_the_patient_column_is_absent():
    graph = load_embed(magview=MAGVIEW[:1]).graph
    rows = [{"acc_anon": "A1", "anon_dicom_path": "cohort1/P9/S/SE/I1.dcm"},
            {"acc_anon": "A1", "anon_dicom_path": "cohort1/P1/S/SE/I2.dcm"}]

    report = load_embed(images=rows, into=graph, parents="existing")

    assert [image.image_id for image in graph.images] == ["I2"]
    assert graph.patient("P9") is None
    assert outside(report) == {"images": 1}


def test_patient_scoped_tables_are_checked_by_patient_only():
    source = load_embed(magview=MAGVIEW).graph
    subset = source.partition(level="patient", key=lambda patient: patient.patient_id)["P1"]
    subset_exam = subset.exam("A1")

    report = load_embed(
        patients=[{"empi_anon": "P1", "GENDER_DESC": "F"}, {"empi_anon": "P2", "GENDER_DESC": "F"}],
        hormone_history=[
            {"empi_anon": "P1", "acc_anon": "A-not-loaded", "type": "O", "code": "TAMOX"},
            {"empi_anon": "P2", "type": "O", "code": "TAMOX"},
        ],
        registry=[{"empi_anon": "P1", "cancer_registry_id": 7}, {"empi_anon": "P2", "cancer_registry_id": 8}],
        into=subset,
        parents="existing",
    )

    assert [patient.patient_id for patient in subset.patients] == ["P1"]
    assert subset.patient("P1").sex == "F"
    assert len(subset.patient("P1").medication_history) == 1
    assert subset.exam("A-not-loaded") is None and subset.exam("A1") is subset_exam
    assert [entry.registry_id for entry in subset.registry_entries] == ["7"]
    assert outside(report) == {"patients": 1, "hormone_history": 1, "registry": 1}


def test_procedures_and_pathology_need_their_patient_and_exam():
    graph = load_embed(magview=MAGVIEW[:1]).graph
    row = {"empi_anon": "P1", "acc_anon": "A1", "numfind": 1, "procdate_anon": "2020-01-02",
           "type": "biopsy", "bside": "L", "path1": "reported"}
    elsewhere = {**row, "empi_anon": "P2", "acc_anon": "A3"}

    report = load_embed(procedures=[row, elsewhere], pathology=[row, elsewhere], into=graph, parents="existing")

    assert len(graph.procedures) == len(graph.pathology) == 1
    assert graph.finding("A1", "1").procedures == graph.procedures
    assert graph.patient("P2") is None and graph.exam("A3") is None
    assert outside(report) == {"procedures": 1, "pathology": 1}


def test_roi_rows_attach_only_to_images_present_or_loaded_in_the_same_call():
    graph = load_embed(magview=MAGVIEW[:1]).graph

    report = load_embed(
        images=[image_row("P1", "A1", "I1")],
        rois=[
            {"anon_dicom_path": "cohort1/P1/S/SE/I1.dcm", "ROI_coords": "[(3, 3, 4, 4)]"},
            {"anon_dicom_path": "cohort1/P9/S/SE/I9.dcm", "ROI_coords": "[(1, 1, 2, 2)]"},
        ],
        into=graph,
        parents="existing",
    )

    assert [image.image_id for image in graph.images] == ["I1"]
    assert [roi.coordinates for roi in graph.image("I1").rois] == [(3.0, 3.0, 5.0, 5.0)]
    assert outside(report) == {"rois": 1}


def test_membership_is_read_once_before_the_call_loads_anything():
    graph = load_embed(patients=[{"empi_anon": "P1"}]).graph

    report = load_embed(
        exams=[{"acc_anon": "A1"}],
        findings=[{"acc_anon": "A1", "numfind": 1}],
        into=graph,
        parents="existing",
    )

    assert graph.exams == () and graph.findings == ()
    assert outside(report) == {"exams": 1, "findings": 1}


def test_existing_requires_a_target_graph_and_a_known_value():
    with pytest.raises(ValueError):
        load_embed(images=IMAGES, parents="existing")
    with pytest.raises(ValueError):
        load_embed(images=IMAGES, into=DatasetGraph(), parents="subset")  # type: ignore[arg-type]
