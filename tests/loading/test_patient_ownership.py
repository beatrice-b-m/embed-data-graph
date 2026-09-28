"""Source patient claims on exams across loads."""

from embed_data_graph import load_embed


def test_refresh_replaces_a_corrected_patient_claim():
    graph = load_embed(exams=[{"acc_anon": "A1", "empi_anon": "P1"}]).graph
    load_embed(exams=[{"acc_anon": "A1", "empi_anon": "P2"}], into=graph)

    exam = graph.exam("A1")
    assert exam.asserted_patient_ids == {"P2"}
    assert exam.patient_id == "P2"
    assert exam in graph.patient("P2").exams
    assert exam not in graph.patient("P1").exams


def test_merge_keeps_both_claims_and_leaves_the_exam_unowned():
    graph = load_embed(exams=[{"acc_anon": "A1", "empi_anon": "P1"}]).graph
    load_embed(exams=[{"acc_anon": "A1", "empi_anon": "P2"}], into=graph, mode="merge")

    exam = graph.exam("A1")
    assert exam.asserted_patient_ids == {"P1", "P2"}
    assert exam.patient_id is None


def test_conflicting_claims_within_one_snapshot_leave_the_exam_unowned():
    graph = load_embed(
        exams=[{"acc_anon": "A1", "empi_anon": "P1"}],
        images=[{"anon_dicom_path": "cohort1/P2/S/SE/U1.dcm", "acc_anon": "A1"}],
    ).graph

    exam = graph.exam("A1")
    assert exam.asserted_patient_ids == {"P1", "P2"}
    assert exam.patient_id is None


def test_explicit_owner_survives_a_later_refresh():
    graph = load_embed(exams=[{"acc_anon": "A1", "empi_anon": "P1"}, {"acc_anon": "A1", "empi_anon": "P2"}]).graph
    graph.assign_patient(graph.exam("A1"), "P2")
    load_embed(exams=[{"acc_anon": "A1", "empi_anon": "P1"}], into=graph)

    exam = graph.exam("A1")
    assert exam.patient_id == "P2"
    assert exam.asserted_patient_ids == {"P1"}


def test_load_without_a_patient_column_keeps_existing_claims():
    graph = load_embed(exams=[{"acc_anon": "A1", "empi_anon": "P1"}]).graph
    load_embed(exams=[{"acc_anon": "A1", "desc": "screen"}], into=graph)

    assert graph.exam("A1").patient_id == "P1"
