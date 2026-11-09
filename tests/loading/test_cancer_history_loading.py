"""Reported cancer history (CancerHist) about the patient or a relative."""

from datetime import date

from embed_data_graph import load_embed
from embed_data_graph.clinical.histories import CancerHistoryObservation


def cancer_row(**fields):
    return {"empi_anon": "P1", "acc_anon": "A1", "patient": 1, "type": "B", "cancercode": "idc", **fields}


def test_cancer_history_loads_with_subject_decoded_and_codes_kept_raw():
    report = load_embed(
        cancer_history=[cancer_row(), cancer_row(patient=0.0, rel="m", diag_age="45", brca1="2", side="L")]
    )
    own, relative = report.graph.patient("P1").cancer_history

    assert isinstance(own, CancerHistoryObservation)
    assert (own.about_relative, own.category.code, own.cancer_code.code) == (False, "B", "IDC")
    assert own.cancer_code.meaning is None and own.category.meaning is None
    assert own.context_accession == "A1"
    assert (relative.about_relative, relative.relationship.code, relative.relationship.meaning) == (True, "M", None)
    assert (relative.diagnosis_age, relative.brca1, relative.side) == ("45", "2", "L")
    assert not report.issues


def test_an_unrecognized_subject_is_unknown_and_reported():
    report = load_embed(cancer_history=[cancer_row(patient="X")])

    (entry,) = report.graph.patient("P1").cancer_history
    assert entry.about_relative is None
    assert "unknown_cancer_history_subject" in {issue.code for issue in report.issues}


def test_cancer_history_refreshes_as_a_patient_snapshot_and_keeps_other_history():
    graph = load_embed(
        cancer_history=[cancer_row(), cancer_row(cancercode="dcis")],
        hormone_history=[{"empi_anon": "P1", "acc_anon": "A1", "type": "H", "code": "TAMOX"}],
    ).graph

    load_embed(cancer_history=[cancer_row(cancercode="lcis")], into=graph)

    patient = graph.patient("P1")
    assert [entry.cancer_code.code for entry in patient.cancer_history] == ["LCIS"]
    assert len(patient.medication_history) == 1


def test_cancer_history_is_dated_by_its_context_exam():
    graph = load_embed(
        exams=[{"acc_anon": "A1", "empi_anon": "P1", "studydate_anon": "2019-02-03"}],
        cancer_history=[cancer_row(patient=0, rel="S")],
    ).graph

    patient = graph.patient("P1")
    assert patient.history_as_of(date(2019, 2, 2), kind="cancer") == ()
    assert patient.history_as_of(date(2019, 2, 3), kind="cancer") == patient.cancer_history
