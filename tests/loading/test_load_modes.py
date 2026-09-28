"""Refresh and merge semantics across separate load_embed calls."""

from datetime import date

import pandas as pd
import pytest

from embed_data_graph import DatasetGraph, Laterality, load_embed
from embed_data_graph.core.anatomy import DepthThird, MedialLateralAxis


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


LOCATED = {"empi_anon": "P1", "acc_anon": "A1", "numfind": 1, "side": "L", "location": "10", "depth": "P", "distance": 3}


def located_finding(extract, mode="refresh"):
    graph = load_embed(magview=[LOCATED]).graph
    report = load_embed(findings=[{"acc_anon": "A1", "numfind": 1, **extract}], into=graph, mode=mode)
    return graph.finding("A1", "1"), report


def test_partial_finding_extract_keeps_the_anatomy_it_does_not_supply():
    finding, report = located_finding({"distance": 4})
    position = finding.anatomical_position

    assert finding.laterality is Laterality.LEFT
    assert (position.laterality, position.clock_position.hour) == (Laterality.LEFT, 10)
    assert position.quadrant.depth is DepthThird.POSTERIOR
    assert position.distance_from_nipple_cm == 4.0
    assert not report.issues


def test_location_only_extract_keeps_side_and_depth():
    finding, _ = located_finding({"location": "2"})
    position = finding.anatomical_position

    assert (position.laterality, position.clock_position.hour) == (Laterality.LEFT, 2)
    assert position.quadrant.depth is DepthThird.POSTERIOR
    assert position.distance_from_nipple_cm == 3.0


def test_side_correction_re_derives_the_position_on_the_new_side():
    finding, _ = located_finding({"side": "R"})
    position = finding.anatomical_position

    assert finding.laterality is Laterality.RIGHT
    assert position.laterality is Laterality.RIGHT
    assert position.quadrant.ml is MedialLateralAxis.LATERAL
    assert position.distance_from_nipple_cm == 3.0


def test_explicit_null_still_clears_an_anatomy_component_in_refresh():
    finding, _ = located_finding({"distance": None})

    assert finding.anatomical_position.distance_from_nipple_cm is None
    assert finding.anatomical_position.clock_position.hour == 10


@pytest.mark.parametrize("mode", ["refresh", "merge"])
def test_side_and_location_from_separate_tables_combine_in_either_order(mode):
    side = [{"empi_anon": "P1", "acc_anon": "A1", "numfind": 1, "side": "L", "asses": "N"}]
    location = [{"acc_anon": "A1", "numfind": 1, "location": "10", "depth": "P"}]
    together = load_embed(magview=side, findings=location).graph
    side_first = load_embed(magview=side).graph
    load_embed(findings=location, into=side_first, mode=mode)
    location_first = load_embed(findings=location).graph
    load_embed(magview=side, into=location_first, mode=mode)

    positions = [graph.finding("A1", "1").anatomical_position for graph in (together, side_first, location_first)]
    assert {(item.laterality, item.clock_position.hour) for item in positions} == {(Laterality.LEFT, 10)}


def test_undated_attribute_correction_replaces_the_dated_observation():
    graph = load_embed(patients=[{"empi_anon": "P1", "acc_anon": "A1", "studydate_anon": "2020-01-01", "GENDER_DESC": "F"}]).graph
    load_embed(patients=[{"empi_anon": "P1", "acc_anon": "A1", "GENDER_DESC": "M"}], into=graph)

    patient = graph.patient("P1")
    assert patient.sex == "M"
    assert [(item.accession_number, item.value) for item in patient.attribute_observations] == [("A1", "M")]


def test_undated_row_joins_a_dated_row_for_the_same_accession_in_one_call():
    patient = load_embed(
        patients=[
            {"empi_anon": "P1", "acc_anon": "A1", "GENDER_DESC": "F"},
            {"empi_anon": "P1", "acc_anon": "A1", "studydate_anon": "2020-01-01", "race": "W"},
        ]
    ).graph.patient("P1")

    assert {item.context_date for item in patient.attribute_observations} == {date(2020, 1, 1)}
    assert patient.sex == "F"
