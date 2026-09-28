"""Refresh and merge semantics across separate load_embed calls."""

import pandas as pd

from embed_data_graph import DatasetGraph, load_embed


def test_partial_magview_load_keeps_patient_and_exam_fields_it_does_not_supply():
    graph = DatasetGraph()
    load_embed(
        patients=[{"empi_anon": "P1", "GENDER_DESC": "F"}],
        exams=[{"acc_anon": "A1", "empi_anon": "P1", "desc": "screen", "studydate_anon": "2020-01-01"}],
        into=graph,
    )
    load_embed(
        magview=[{"empi_anon": "P1", "acc_anon": "A1", "numfind": 1, "side": "L", "asses": "N"}],
        into=graph,
    )

    exam = graph.exam("A1")
    assert (exam.exam_date, exam.description) == ("2020-01-01", "screen")
    assert graph.patient("P1").sex == "F"
    assert graph.finding("A1", "1").interpretation.assessment.meaning == "Negative"


def test_refresh_clears_a_field_whose_column_is_supplied_as_null():
    graph = load_embed(exams=[{"acc_anon": "A1", "desc": "screen"}]).graph
    load_embed(exams=[{"acc_anon": "A1", "desc": None}], into=graph)

    assert graph.exam("A1").description is None


def test_dataframe_nan_counts_as_a_supplied_null():
    graph = load_embed(exams=[{"acc_anon": "A1", "desc": "screen", "studydate_anon": "2020-01-01"}]).graph
    frame = pd.DataFrame([{"acc_anon": "A1", "desc": float("nan"), "studydate_anon": "2021-02-03"}])
    load_embed(exams=frame, into=graph)

    exam = graph.exam("A1")
    assert exam.description is None
    assert exam.exam_date == "2021-02-03"


def test_partial_image_row_keeps_metadata_it_does_not_supply():
    path = "cohort1/P1/S1/SE1/U1.dcm"
    graph = load_embed(
        images=[{"anon_dicom_path": path, "acc_anon": "A1", "ViewPosition": "CC", "Rows": 100, "Columns": 80}]
    ).graph
    load_embed(images=[{"anon_dicom_path": path, "ImageLateralityFinal": "R"}], into=graph)

    (image,) = graph.images
    assert image.view_position.value == "CC"
    assert (image.height, image.width) == (100, 80)
    assert image.laterality.value == "R"


def test_merge_reports_a_value_that_contradicts_the_graph_and_makes_it_unknown():
    graph = load_embed(exams=[{"acc_anon": "A1", "desc": "screen"}]).graph
    report = load_embed(exams=[{"acc_anon": "A1", "desc": "diagnostic"}], into=graph, mode="merge")

    assert graph.exam("A1").description is None
    assert "conflicting_exam_description" in {issue.code for issue in report.issues}


def test_merge_fills_gaps_and_accepts_an_agreeing_value_silently():
    graph = load_embed(exams=[{"acc_anon": "A1", "desc": "screen"}]).graph
    report = load_embed(
        exams=[{"acc_anon": "A1", "desc": "screen", "studydate_anon": "2020-01-01"}],
        into=graph,
        mode="merge",
    )

    exam = graph.exam("A1")
    assert (exam.description, exam.exam_date) == ("screen", "2020-01-01")
    assert not report.issues


def test_merge_conflict_on_an_enum_field_becomes_its_unknown_member():
    from embed_data_graph import Laterality

    graph = load_embed(findings=[{"acc_anon": "A1", "numfind": 1, "side": "L", "asses": "B"}]).graph
    report = load_embed(
        findings=[{"acc_anon": "A1", "numfind": 1, "side": "R", "asses": "S"}], into=graph, mode="merge"
    )

    finding = graph.finding("A1", "1")
    assert finding.laterality is Laterality.UNKNOWN
    assert finding.interpretation.assessment is None
    codes = {issue.code for issue in report.issues}
    assert {"conflicting_finding_laterality", "conflicting_finding_assessment"} <= codes


def test_merge_conflict_in_image_metadata_is_reported():
    path = "cohort1/P1/S1/SE1/U1.dcm"
    graph = load_embed(images=[{"anon_dicom_path": path, "ViewPosition": "CC"}]).graph
    report = load_embed(images=[{"anon_dicom_path": path, "ViewPosition": "MLO"}], into=graph, mode="merge")

    assert graph.images[0].view_position.value == "UNKNOWN"
    assert "conflicting_image_view_position" in {issue.code for issue in report.issues}


def test_patient_attribute_that_changes_between_exams_is_kept_per_exam():
    from datetime import date

    rows = [
        {"empi_anon": "P1", "acc_anon": "A1", "numfind": 1, "studydate_anon": "2020-01-01", "GENDER_DESC": "F"},
        {"empi_anon": "P1", "acc_anon": "A2", "numfind": 1, "studydate_anon": "2022-01-01", "GENDER_DESC": "U"},
    ]
    report = load_embed(magview=rows)
    patient = report.graph.patient("P1")

    assert patient.sex is None
    assert patient.attribute_as_of("sex", date(2021, 1, 1)) == "F"
    assert patient.attribute_as_of("sex", date(2022, 1, 1)) == "U"
    assert not [issue for issue in report.issues if issue.code.startswith("conflicting_patient")]


def test_patient_attribute_that_agrees_across_exams_is_a_scalar():
    rows = [
        {"empi_anon": "P1", "acc_anon": "A1", "numfind": 1, "studydate_anon": "2020-01-01", "GENDER_DESC": "F"},
        {"empi_anon": "P1", "acc_anon": "A2", "numfind": 1, "studydate_anon": "2022-01-01", "GENDER_DESC": "F"},
    ]
    patient = load_embed(magview=rows).graph.patient("P1")

    assert patient.sex == "F"
    assert len(patient.attribute_history("sex")) == 2


def test_conflicting_patient_values_within_one_exam_are_reported():
    rows = [
        {"empi_anon": "P1", "acc_anon": "A1", "numfind": 1, "GENDER_DESC": "F"},
        {"empi_anon": "P1", "acc_anon": "A1", "numfind": 2, "GENDER_DESC": "M"},
    ]
    report = load_embed(magview=rows)

    assert report.graph.patient("P1").sex is None
    assert "conflicting_patient_sex" in {issue.code for issue in report.issues}
