from embed_data_graph import Laterality, load_embed


def test_missing_finding_number_keeps_assessment_and_refreshes_snapshot():
    row = {"empi_anon": "P", "acc_anon": "A", "numfind": None, "asses": "A", "side": "L", "massshape": "R"}
    report = load_embed(magview=[row, row])
    graph = report.graph
    exam = graph.exam("A")
    assert graph.findings == ()
    assert len(exam.unkeyed_findings) == 2
    record = exam.unkeyed_findings[0]
    assert record.finding_number is None and record.laterality is Laterality.UNKNOWN
    assert record.interpretation.assessment.code == "A"
    assert record.descriptors["mass_shape"].code == "R"
    assert any(i.code == "missing_finding_identity" for i in report.issues)
    load_embed(magview=[row], into=graph)
    assert len(exam.unkeyed_findings) == 1
    part = graph.partition(level="patient", key=lambda p: p.patient_id)["P"]
    assert len(part.exam("A").unkeyed_findings) == 1
    load_embed(magview=[{**row, "numfind": 1}], into=graph)
    assert exam.unkeyed_findings == ()


def test_contested_exams_reachable_and_copy_with_each_claimant():
    graph = load_embed(magview=[{"empi_anon": p, "acc_anon": "A", "numfind": 1} for p in ("P", "Q")]).graph
    exam = graph.exam("A")
    assert exam.patient_id is None and exam.contested
    for p in graph.patients:
        assert p.exams == ()
        assert p.claimed_exams == (exam,)
    parts = graph.partition(level="patient", key=lambda p: p.patient_id)
    assert all(part.exam("A").contested and len(part.findings) == 1 for part in parts.values())
    graph.set_patient_claims(exam, {"P"})
    assert graph.patient("Q").claimed_exams == ()
    assert not exam.contested


def test_invalid_accessions_never_merge_patients_and_can_be_configured():
    rows = [{"empi_anon": p, "acc_anon": 999, "asses": "A"} for p in ("P", "Q")]
    report = load_embed(magview=rows)
    graph = report.graph
    assert graph.exams == ()
    assert len(report.issues) == 2
    for patient in graph.patients:
        record, = patient.invalid_accession_records
        assert record.patient_id == patient.patient_id
        assert record.values["findings.assessment"] == "A"
    part = graph.partition(level="patient", key=lambda p: p.patient_id)["P"]
    assert len(part.unresolved_records) == 1
    load_embed(magview=rows, into=graph)
    assert len(graph.patient("P").invalid_accession_records) == 1
    assert load_embed(magview=rows, invalid_accessions=()).graph.exam("999") is not None


def test_exam_and_cohort_bindings_refresh_and_conflicts():
    row = {"empi_anon": "P", "acc_anon": "A", "accession_type": "non_magview", "total_L_find": 2, "total_R_find": 0, "cohort_num": 3}
    graph = load_embed(magview=[row]).graph
    exam = graph.exam("A")
    assert (exam.accession_type, exam.total_left_findings, exam.total_right_findings) == ("non_magview", 2, 0)
    assert graph.patient("P").cohort_number == "3"
    load_embed(exams=[{**row, "total_L_find": None}], into=graph)
    assert exam.total_left_findings is None


def test_merge_retains_every_unkeyed_row_without_claiming_deduplication():
    rows = [{"empi_anon": "P", "acc_anon": "A", "numfind": None, "asses": "A"},
            {"empi_anon": "P", "acc_anon": 999, "asses": "S"}]
    graph = load_embed(magview=rows, mode="merge").graph
    assert len(graph.exam("A").unkeyed_findings) == 1
    assert len(graph.patient("P").invalid_accession_records) == 1
    report = load_embed(magview=rows, into=graph, mode="merge")
    assert len(graph.exam("A").unkeyed_findings) == 2
    assert len(graph.patient("P").invalid_accession_records) == 2
    assert sum(i.code == "unkeyed_merge_requires_identity" for i in report.issues) == 2
    assert len(graph.records("unresolved")) == 4
    load_embed(magview=rows, into=graph)
    assert len(graph.records("unresolved")) == 2


def test_invalid_accession_clinical_facts_are_typed_patient_scoped_and_projected():
    from datetime import datetime
    from embed_data_graph.clinical.pathology import PathologySeverity

    row = {"empi_anon": "P", "acc_anon": 999, "numfind": 1, "path_severity": 0.0,
           "bside": "L", "procdate_anon": "2018-06-10", "type": "BX", "pdate_anon": "2018-06-12", "path1": "1"}
    for table in ("magview", "pathology", "procedures"):
        graph = load_embed(**{table: [row]}).graph
        patient = graph.patient("P")
        assert graph.exams == graph.procedures == graph.pathology == ()
        assert len(patient.invalid_accession_records) == 1
        records = patient.unresolved_clinical_records
        assert {r.kind for r in records} == ({"procedure"} if table == "procedures" else {"procedure", "pathology"})
        assert all(r.accession_number == "999" and r.finding_number == "1" and r.laterality is Laterality.LEFT for r in records)
        if table != "procedures":
            pathology = next(r for r in records if r.kind == "pathology")
            assert pathology.severity is PathologySeverity.INVASIVE_BREAST_CANCER
            assert pathology.descriptors
        projected = graph.records("unresolved")
        for record in records:
            # The retained raw wrapper may itself have kind 'pathology' or 'procedures'.
            typed = next(r for r in projected if r["kind"] == record.kind and r["procedure_type"] == "BX")
            assert typed["performed_date"] == datetime(2018, 6, 10)
            assert typed["patient_id"] == "P" and typed["incomplete"]
            if record.kind == "pathology":
                assert typed["severity"] == 0 and typed["report_documented_date"] == datetime(2018, 6, 12)
        for subset in (graph.select(level="patient", predicate=lambda p: True), graph.partition(level="patient", key=lambda p: p.patient_id)["P"]):
            assert subset.records("unresolved") == projected


def test_invalid_clinical_snapshots_refresh_merge_and_clear_together():
    row = {"empi_anon": "P", "acc_anon": 999, "path_severity": 0, "bside": "L", "type": "BX", "procdate_anon": "2018-06-10"}
    graph = load_embed(magview=[row]).graph
    load_embed(magview=[row], into=graph)
    assert len(graph.patient("P").unresolved_clinical_records) == 2
    load_embed(magview=[row], into=graph, mode="merge")
    assert len(graph.patient("P").unresolved_clinical_records) == 4
    assert len(graph.records("unresolved")) == 6
    load_embed(magview=[{"empi_anon": "P", "acc_anon": 999, "asses": "A"}], into=graph)
    assert graph.patient("P").unresolved_clinical_records == ()
    assert len(graph.records("unresolved")) == 1
    load_embed(magview=[row], into=graph)
    load_embed(magview=[{"empi_anon": "P", "acc_anon": "A"}], into=graph)
    assert graph.patient("P").unresolved_clinical_records == ()
    assert graph.records("unresolved") == []


def test_invalid_clinical_records_obey_maps_subset_admission_and_missing_values():
    row = {"p": "P", "a": "invalid", "s": 0, "d": "bad", "t": "BX", "b": None}
    columns = {"pathology": {"patient_id": "p", "accession": "a", "severity": "s", "procedure_date": "d", "procedure_type": "t", "laterality": "b"}}
    graph = load_embed(patients=[{"empi_anon": "P"}]).graph
    report = load_embed(pathology=[row, {**row, "p": "Q"}], columns=columns, invalid_accessions={"invalid"}, into=graph, parents="existing")
    assert graph.patient("Q") is None and graph.exams == ()
    assert any(i.code == "rows_outside_graph" for i in report.issues)
    assert len(graph.patient("P").unresolved_clinical_records) == 2
    typed = [r for r in graph.records("unresolved") if r["procedure_type"] == "BX"]
    assert len(typed) == 2 and all(r["performed_date"] is None and r["laterality"] == "UNKNOWN" for r in typed)
    for r in typed:
        assert any(i["code"] == "invalid_date" and i["entity_key"] == r["record_key"] for i in graph.records("issues"))
    anonymous = load_embed(pathology=[{k: v for k, v in row.items() if k != "p"}], columns=columns, invalid_accessions={"invalid"}).graph
    assert anonymous.patients == () and len(anonymous.records("unresolved")) == 3


def test_unkeyed_and_keyed_finding_sides_share_null_absent_and_unrecognized_rules():
    import pandas as pd

    for fields, expected in [({}, "UNKNOWN"), ({"side": None}, "B"), ({"side": float("nan")}, "B"),
                             ({"side": pd.NA}, "B"), ({"side": ""}, "B"), ({"side": "?"}, "UNKNOWN"), ({"side": "R"}, "R")]:
        row = {"empi_anon": "P", "acc_anon": "A", "asses": "A", **fields}
        for table in ("magview", "findings"):
            keyed = load_embed(**{table: [{**row, "numfind": 1}]}).graph.findings[0]
            graph = load_embed(**{table: [{**row, "numfind": None}]}).graph
            unkeyed = graph.exam("A").unkeyed_findings[0]
            assert keyed.laterality.value == unkeyed.reported_laterality.value == expected
            assert unkeyed.laterality is Laterality.UNKNOWN
            assert graph.records("unresolved")[0]["reported_laterality"] == expected
    for mapping, fields, expected in [({"laterality": "side_fact"}, {"side_fact": None}, "B"),
                                       ({"laterality": None}, {"side": None}, "UNKNOWN")]:
        graph = load_embed(findings=[{"empi_anon": "P", "acc_anon": "A", "numfind": None, **fields}], columns={"findings": mapping}).graph
        assert graph.exam("A").unkeyed_findings[0].reported_laterality.value == expected
