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
