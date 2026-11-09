"""Reported patient history tables."""

import pytest

from embed_data_graph import Code, load_embed


def load_procedure_history(**row):
    report = load_embed(procedure_history=[{"empi_anon": "P1", "acc_anon": "A1", **row}])
    return report.graph.patient("P1").procedure_history, {issue.code for issue in report.issues}


def reported_result(result):
    (history,), issues = load_procedure_history(type="B", pcode="1", result=result)
    return history.reported_result, issues


def test_medication_code_is_read_in_its_category_table():
    rows = [{"empi_anon": "P", "acc_anon": "A1", "type": category, "code": "O"} for category in ("H", "T", "O")]
    report = load_embed(hormone_history=rows)
    history = report.graph.patient("P").medication_history

    assert [str(item.category) for item in history] == ["Hormone", "Therapy", "Contraceptive"]
    assert [str(item.medication) for item in history] == ["Other hormone", "Other therapy", "Other contraceptive"]
    assert all(item.medication.code == "O" for item in history)
    assert not report.issues


def test_procedure_history_decodes_category_and_procedure():
    (history,), issues = load_procedure_history(type="g", pcode="hyst", side="L")

    assert (history.category.code, history.category.meaning) == ("G", "Gynecological procedure")
    assert (history.procedure.code, history.procedure.meaning) == ("HYST", "Hysterectomy")
    assert not issues


def test_unknown_category_and_code_keep_their_source_codes_with_warnings():
    (history,), issues = load_procedure_history(type="X", pcode="1")

    assert history.category == Code("X") and not history.category.is_known
    assert history.procedure == Code("1") and history.procedure.meaning is None
    assert {"unknown_procedure_history_category", "unknown_procedure_history_code"} <= issues


def test_code_valid_in_another_category_is_unknown():
    report = load_embed(hormone_history=[{"empi_anon": "P", "acc_anon": "A1", "type": "O", "code": "TAMOX"}])
    (history,) = report.graph.patient("P").medication_history

    assert history.medication.meaning is None
    assert {issue.code for issue in report.issues} == {"unknown_medication_history_code"}


def test_none_means_no_reported_result_and_is_kept_distinct_from_blank():
    none_result, _ = reported_result("NONE")
    blank_result, _ = reported_result("")

    assert none_result == Code("NONE") and none_result.meaning == "No reported result"
    assert blank_result is None


@pytest.mark.parametrize("code, meaning", [("BEN", "Benign"), ("id", "Invasive ductal carcinoma")])
def test_known_result_codes_are_decoded(code, meaning):
    result, issues = reported_result(code)

    assert result == Code(code.upper()) and result.meaning == meaning
    assert not issues


def test_combined_result_token_is_kept_whole_and_reported():
    result, issues = reported_result("FA,SF")

    assert result.code == "FA,SF" and result.meaning is None
    assert "unknown_procedure_history_result" in issues


def test_unkeyed_history_refresh_and_merge_require_explicit_event_identity():
    rows = [{"empi_anon":"P", "type":"H", "code":"ESTRO", "first_age":-5}]
    graph = load_embed(hormone_history=rows * 2).graph
    patient = graph.patient("P")
    assert len(patient.medication_history) == 2
    assert patient.medication_history[0].started.age == -5
    old = patient.medication_history
    report = load_embed(hormone_history=rows, into=graph, mode="merge")
    assert patient.medication_history == old
    assert any(i.code == "history_merge_requires_record_id" for i in report.issues)
    load_embed(hormone_history=rows, into=graph)
    assert len(patient.medication_history) == 1
    patient.replace_history("medication", [])
    assert not patient.medication_history


def test_explicit_history_key_refresh_preserves_reference_and_custom_values():
    columns = {"hormone_history":{"record_id":"record"}}
    rows = [{"empi_anon":"P", "type":"H", "code":"ESTRO", "record":"1", "comment":"old"}]
    graph = load_embed(hormone_history=rows, columns=columns).graph
    history = graph.patient("P").medication_history[0]
    history.project = {"keep":True}
    rows[0]["comment"] = "new"
    load_embed(hormone_history=rows, columns=columns, into=graph)
    assert graph.patient("P").medication_history == (history,)
    assert history.comment == "new" and history.project == {"keep":True}


def history_graph(**exam):
    exams = [{"acc_anon": "A1", "empi_anon": "P", "studydate_anon": "2020-03-04", **exam}]
    return load_embed(
        exams=exams,
        hormone_history=[{"empi_anon": "P", "acc_anon": "A1", "type": "H", "code": "TAMOX"}],
        procedure_history=[{"empi_anon": "P", "acc_anon": "A1", "type": "B", "pcode": "1"}],
    )


def test_reported_history_is_known_on_its_context_exam_date():
    from datetime import date

    patient = history_graph().graph.patient("P")

    assert {patient.history_known_on(item) for item in patient.history_observations} == {date(2020, 3, 4)}
    assert patient.history_as_of(date(2020, 3, 3)) == ()
    assert patient.history_as_of(date(2020, 3, 4)) == patient.history_observations
    assert patient.history_as_of(date(2021, 1, 1), kind="medication") == patient.medication_history


def test_history_known_on_resolves_once_the_exam_arrives_later():
    from datetime import date

    report = load_embed(hormone_history=[{"empi_anon": "P", "acc_anon": "A1", "type": "H", "code": "TAMOX"}])
    graph = report.graph
    (item,) = graph.patient("P").medication_history
    assert graph.patient("P").history_known_on(item) is None
    assert "history_known_on_unresolved" not in {issue.code for issue in report.issues}

    load_embed(exams=[{"acc_anon": "A1", "empi_anon": "P", "studydate_anon": "2019-05-06"}], into=graph)
    assert graph.patient("P").history_known_on(item) == date(2019, 5, 6)


def test_history_without_an_accession_or_exam_date_is_reported_and_left_out():
    from datetime import date

    report = load_embed(
        exams=[{"acc_anon": "A1", "empi_anon": "P", "studydate_anon": None}],
        hormone_history=[
            {"empi_anon": "P", "acc_anon": "A1", "type": "H", "code": "TAMOX"},
            {"empi_anon": "P", "acc_anon": None, "type": "H", "code": "TAMOX"},
        ],
    )

    (issue,) = [issue for issue in report.issues if issue.code == "history_known_on_unresolved"]
    assert issue.context["reasons"] == {"context_exam_without_date": 1, "missing_context_accession": 1}
    assert report.graph.patient("P").history_as_of(date(2100, 1, 1)) == ()


def test_history_from_another_patients_exam_has_no_known_on_date():
    from datetime import date

    report = load_embed(
        exams=[{"acc_anon": "A1", "empi_anon": "Q", "studydate_anon": "2020-03-04"}],
        hormone_history=[{"empi_anon": "P", "acc_anon": "A1", "type": "H", "code": "TAMOX"}],
    )

    patient = report.graph.patient("P")
    assert patient.history_as_of(date(2100, 1, 1)) == ()
    (issue,) = [issue for issue in report.issues if issue.code == "history_known_on_unresolved"]
    assert issue.context["reasons"] == {"context_exam_ownership_ambiguous": 1}
