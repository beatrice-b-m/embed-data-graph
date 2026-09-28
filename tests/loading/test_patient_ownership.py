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


MAGVIEW = [{"empi_anon": "P1", "acc_anon": "A1", "numfind": 1, "side": "L"}]
IMAGE_ON_P2_PATH = [{"acc_anon": "A1", "anon_dicom_path": "cohort1/P2/S/SE/U1.dcm"}]


def claims(graph):
    exam = graph.exam("A1")
    return exam.asserted_patient_ids, exam.patient_id


def test_claims_from_different_tables_do_not_depend_on_load_order():
    one_call = load_embed(magview=MAGVIEW, images=IMAGE_ON_P2_PATH).graph
    magview_first = load_embed(magview=MAGVIEW).graph
    load_embed(images=IMAGE_ON_P2_PATH, into=magview_first)
    images_first = load_embed(images=IMAGE_ON_P2_PATH).graph
    load_embed(magview=MAGVIEW, into=images_first)

    assert claims(one_call) == claims(magview_first) == claims(images_first) == ({"P1", "P2"}, None)


def test_refreshing_one_table_replaces_only_the_claims_that_table_supplied():
    graph = load_embed(magview=MAGVIEW).graph
    load_embed(images=IMAGE_ON_P2_PATH, into=graph)
    load_embed(images=[{"acc_anon": "A1", "anon_dicom_path": "cohort1/P1/S/SE/U1.dcm"}], into=graph)

    assert claims(graph) == ({"P1"}, "P1")


def test_a_later_clinical_table_cannot_silently_resolve_a_conflict():
    graph = load_embed(exams=[{"acc_anon": "A1", "empi_anon": "P1"}, {"acc_anon": "A1", "empi_anon": "P2"}]).graph
    load_embed(
        procedures=[{"empi_anon": "P1", "acc_anon": "A1", "procdate_anon": "2020-01-01", "type": "B", "bside": "L"}],
        into=graph,
    )

    assert claims(graph) == ({"P1", "P2"}, None)


def test_an_explicit_owner_keeps_claims_from_other_tables():
    graph = load_embed(magview=MAGVIEW).graph
    graph.assign_patient(graph.exam("A1"), "P1")
    load_embed(images=IMAGE_ON_P2_PATH, into=graph)

    assert claims(graph) == ({"P1", "P2"}, "P1")


def test_claims_added_outside_the_loader_survive_a_refresh():
    graph = load_embed(exams=[{"acc_anon": "A1", "empi_anon": "P1"}]).graph
    graph.claim_patient(graph.exam("A1"), ["P3"])
    load_embed(exams=[{"acc_anon": "A1", "empi_anon": "P2"}], into=graph)

    assert graph.exam("A1").asserted_patient_ids == {"P2", "P3"}


def test_patient_column_that_disagrees_with_the_path_is_reported():
    report = load_embed(images=[{"empi_anon": "P1", "acc_anon": "A1", "anon_dicom_path": "cohort1/P2/S/SE/U1.dcm"}])

    assert "source_patient_path_mismatch" in {issue.code for issue in report.issues}
    assert claims(report.graph) == ({"P1"}, "P1")
