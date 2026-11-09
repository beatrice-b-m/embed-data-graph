"""Pathology from MagView rows attaches to its procedure."""

from embed_data_graph import load_embed


def procedure_row(**fields):
    row = {
        "empi_anon": "P1",
        "acc_anon": "A1",
        "numfind": 1,
        "side": "L",
        "bside": "L",
        "type": "B",
        "procdate_anon": "2020-01-02",
        "path1": "IDC",
        "path_severity": 0,
    }
    row.update(fields)
    return row


def test_pathology_without_a_report_date_attaches_to_its_procedure():
    report = load_embed(magview=[procedure_row()])
    graph = report.graph

    (procedure,) = graph.procedures
    (pathology,) = graph.pathology
    assert procedure.pathology == (pathology,)
    assert [d.descriptor.code for d in pathology.descriptors] == ["IDC"]
    assert pathology.report_documented_date is None
    assert not graph.unresolved_records
    assert graph.finding("A1", "1").pathology == (pathology,)


def test_report_date_is_an_attribute_not_part_of_pathology_identity():
    graph = load_embed(magview=[procedure_row(pdate_anon="2020-01-05")]).graph
    (pathology,) = graph.pathology

    load_embed(magview=[procedure_row(pdate_anon="2020-01-06")], into=graph)

    assert graph.pathology == (pathology,)
    assert pathology.report_documented_date == "2020-01-06"


def test_one_procedure_on_several_findings_has_one_pathology_bundle():
    graph = load_embed(magview=[procedure_row(), procedure_row(numfind=2)]).graph

    (procedure,) = graph.procedures
    (pathology,) = graph.pathology
    assert {f.finding_number for f in graph.findings if pathology in f.pathology} == {"1", "2"}


def test_pathology_without_a_complete_procedure_stays_unresolved():
    report = load_embed(magview=[procedure_row(bside=None, pdate_anon="2020-01-05")])

    assert not report.graph.pathology
    assert report.graph.unresolved_records
    assert "incomplete_pathology_identity" in {issue.code for issue in report.issues}


def test_cancer_on_a_procedure_without_a_side_is_reachable_from_the_patient():
    report = load_embed(magview=[procedure_row(bside=None)])
    graph = report.graph

    records = graph.patient("P1").unresolved_clinical_records
    (pathology,) = [record for record in records if record.kind == "pathology"]
    assert graph.procedures == () and graph.pathology == ()
    assert pathology.severity.name == "INVASIVE_BREAST_CANCER"
    assert [d.descriptor.code for d in pathology.descriptors] == ["IDC"]
    assert pathology.performed_date == "2020-01-02" and pathology.procedure_type.code == "B"
    assert pathology.patient_id == "P1"
    issues = [issue for issue in report.issues if issue.code == "incomplete_pathology_identity"]
    assert issues and issues[0].context["patient_id"] == "P1"


def test_an_unreported_procedure_side_is_never_taken_from_the_finding():
    graph = load_embed(magview=[procedure_row(bside=None, side="R")]).graph

    sides = {record.kind: record.laterality.value for record in graph.patient("P1").unresolved_clinical_records}
    assert sides == {"procedure": "UNKNOWN", "pathology": "UNKNOWN"}


def test_procedures_missing_date_or_type_keep_what_they_report():
    graph = load_embed(
        procedures=[
            {"empi_anon": "P1", "procdate_anon": None, "type": "B", "bside": "L"},
            {"empi_anon": "P1", "procdate_anon": "2020-01-02", "type": None, "bside": "R"},
        ]
    ).graph

    records = graph.patient("P1").unresolved_clinical_records
    assert [(r.performed_date, r.procedure_type and r.procedure_type.code, r.laterality.value) for r in records] == [
        (None, "B", "L"),
        ("2020-01-02", None, "R"),
    ]
    assert {r.reason for r in records} == {"incomplete_procedure_identity"}


def test_accessionless_unresolved_rows_are_kept_per_patient_and_refresh_per_patient():
    graph = load_embed(
        procedures=[
            {"empi_anon": "P1", "procdate_anon": None, "type": "B", "bside": "L"},
            {"empi_anon": "P2", "procdate_anon": None, "type": "B", "bside": "L"},
        ]
    ).graph

    load_embed(procedures=[{"empi_anon": "P1", "procdate_anon": "2020-01-02", "type": "B", "bside": "L"}], into=graph)

    assert graph.patient("P1").unresolved_clinical_records == ()
    assert len(graph.patient("P2").unresolved_clinical_records) == 1
    assert len(graph.patient("P1").procedures) == 1


def test_unresolved_records_travel_with_patient_partitions():
    graph = load_embed(
        magview=[procedure_row(bside=None)],
        procedures=[{"empi_anon": "P1", "procdate_anon": None, "type": "B", "bside": "L"}],
    ).graph

    part = graph.partition(level="patient", key=lambda patient: patient.patient_id)["P1"]

    assert len(part.patient("P1").unresolved_clinical_records) == 3
    assert part.patient("P1").unresolved_clinical_records[0] is not graph.patient("P1").unresolved_clinical_records[0]


def test_patient_reaches_procedures_and_pathology_not_attached_to_an_exam():
    graph = load_embed(
        procedures=[{"empi_anon": "P1", "procdate_anon": "2020-01-02", "type": "B", "bside": "L"}],
        pathology=[{"empi_anon": "P1", "procdate_anon": "2020-01-02", "type": "B", "bside": "L", "path_severity": 4}],
    ).graph

    patient = graph.patient("P1")
    assert patient.exams == ()
    assert patient.procedures == graph.procedures and len(patient.procedures) == 1
    assert patient.pathology == graph.pathology and len(patient.pathology) == 1


def test_patient_view_matches_graph_records_and_follows_refresh():
    graph = load_embed(pathology=[procedure_row(bside=None)]).graph
    patient = graph.patient("P1")

    (entry,) = graph.unresolved_records[("clinical", "pathology", ("finding", ("A1", "1")))]
    assert patient.unresolved_clinical_records == (entry["record"],)

    load_embed(pathology=[procedure_row()], into=graph)
    assert patient.unresolved_clinical_records == ()
    assert len(patient.pathology) == 1
