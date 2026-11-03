"""Dated body measurements, intake attributes and exam location."""

from datetime import date

import pytest

from embed_data_graph import load_embed


def measure_row(**fields):
    return {"empi_anon": "P1", "collection_date_anon": "2020-01-02", "height_inches": 64, "weight_pounds": 150.5, "bmi": 25.8, **fields}


def test_body_measurements_are_dated_attribute_observations_with_units():
    report = load_embed(body_measurements=[measure_row(), measure_row(collection_date_anon="2021-03-04", height_inches=None, bmi=None, weight_pounds=160)])
    patient = report.graph.patient("P1")

    assert [(item.value, item.context_date) for item in patient.attribute_history("weight_pounds")] == [
        (150.5, date(2020, 1, 2)), (160, date(2021, 3, 4)),
    ]
    assert [item.accession_number for item in patient.attribute_observations] == [None] * 4
    assert patient.attribute_as_of("height_inches", date(2022, 1, 1)) == 64
    assert patient.attribute_as_of("bmi", date(2019, 1, 1)) is None
    assert not report.issues


def test_same_day_disagreeing_measurements_become_unknown():
    report = load_embed(body_measurements=[measure_row(), measure_row(weight_pounds=151)])

    (weight,) = report.graph.patient("P1").attribute_history("weight_pounds")
    assert weight.value is None
    assert "conflicting_body_measurement" in {issue.code for issue in report.issues}


def test_non_numeric_measurements_are_dropped_and_reported():
    report = load_embed(body_measurements=[measure_row(bmi="n/a")])

    assert report.graph.patient("P1").attribute_history("bmi") == ()
    assert "body_measurement_numeric_parse" in {issue.code for issue in report.issues}


def test_refresh_replaces_the_series_and_merge_adds_dates():
    graph = load_embed(body_measurements=[measure_row(), measure_row(collection_date_anon="2021-01-01", weight_pounds=155)]).graph

    load_embed(body_measurements=[measure_row(collection_date_anon="2022-01-01", weight_pounds=170)], into=graph)
    assert [item.value for item in graph.patient("P1").attribute_history("weight_pounds")] == [170]

    report = load_embed(
        body_measurements=[measure_row(collection_date_anon="2023-01-01", weight_pounds=180), measure_row(collection_date_anon="2022-01-01", weight_pounds=171)],
        into=graph,
        mode="merge",
    )
    assert [item.value for item in graph.patient("P1").attribute_history("weight_pounds")] == [None, 180]
    assert "conflicting_body_measurement" in {issue.code for issue in report.issues}


def test_an_unsupplied_measure_is_left_unchanged():
    graph = load_embed(body_measurements=[measure_row()]).graph

    load_embed(body_measurements=[{"empi_anon": "P1", "collection_date_anon": "2021-01-01", "weight_pounds": 155}], into=graph)

    patient = graph.patient("P1")
    assert [item.value for item in patient.attribute_history("height_inches")] == [64]
    assert [item.value for item in patient.attribute_history("weight_pounds")] == [155]


def test_the_collection_date_is_required():
    with pytest.raises(ValueError):
        load_embed(body_measurements=[measure_row()], columns={"body_measurements": {"measured_date": None}})


def magview_row(**fields):
    return {"empi_anon": "P1", "acc_anon": "A1", "numfind": 1, "studydate_anon": "2020-01-02", **fields}


def test_intake_answers_are_attribute_observations_per_exam_context():
    graph = load_embed(
        magview=[
            magview_row(menarcheage_anon=12, menopauseage_anon=None, livebirths=0),
            magview_row(acc_anon="A2", studydate_anon="2021-01-02", menarcheage_anon=13, livebirths=2),
        ]
    ).graph
    patient = graph.patient("P1")

    assert patient.attribute_as_of("menarche_age", date(2020, 6, 1)) == 12
    assert patient.attribute_as_of("live_births", date(2020, 6, 1)) == 0  # an explicit no, not missing
    assert patient.attribute_as_of("live_births", date(2022, 1, 1)) == 2
    assert patient.attribute_as_of("menopause_age", date(2022, 1, 1)) is None
    assert not hasattr(patient, "menarche_age")


def test_magview_height_and_weight_are_not_loaded():
    patient = load_embed(magview=[magview_row(height=60, weight=120)]).graph.patient("P1")

    assert {item.attribute for item in patient.attribute_observations}.isdisjoint({"height", "weight"})


def test_exam_location_is_an_opaque_identifier():
    exam = load_embed(magview=[magview_row(loc_num_anon=7.0)]).graph.exam("A1")

    assert exam.location_id == "7"
    assert exam.to_dict()["location_id"] == "7"
