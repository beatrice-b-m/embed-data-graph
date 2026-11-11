"""Registry groups retain individual tumors and fan out source exam pointers."""

from itertools import permutations

import pytest

from embed_data_graph import CancerRegistryEntry, DatasetGraph, Exam, Laterality, load_embed


ROWS = [
    {"empi_anon": "P", "cancer_outcome_registry_id": "R", "TUMOR_RECORD_NUMBER": 1,
     "DATE_OF_DIAGNOSIS_ANON": "2020-02-01", "LATERALITY": 2,
     "HISTOLOGY_ICDO3": 8500, "BEHAVIOR_ICDO3": 3, "PRIMARY_SITE": "C504"},
    {"empi_anon": "P", "cancer_outcome_registry_id": "R", "TUMOR_RECORD_NUMBER": 2,
     "DATE_OF_DIAGNOSIS_ANON": "2020-02-01", "LATERALITY": 1,
     "HISTOLOGY_ICDO3": 8500, "BEHAVIOR_ICDO3": 2, "PRIMARY_SITE": "C501"},
]
POINTER = {"empi_anon": "P", "acc_anon": "A", "cancer_outcome_registry_id": "R"}


@pytest.mark.parametrize("order", ["together", "registry_first", "pointer_first"])
def test_tumors_keep_distinct_facts_and_exam_links_independent_of_load_order(order):
    for rows in permutations(ROWS):
        graph = DatasetGraph()
        if order == "together":
            report = load_embed(registry=rows, magview=[POINTER], into=graph)
        else:
            first, second = ({"registry": rows}, {"magview": [POINTER]})
            if order == "pointer_first":
                first, second = second, first
            load_embed(**first, into=graph)
            report = load_embed(**second, into=graph)
        assert not any(issue.code == "conflicting_clinical_values" for issue in report.issues)
        left = graph.registry_entry("P", "R", "1")
        right = graph.registry_entry("P", "R", "2")
        assert left.identity == ("P", "R", "1") and right.identity == ("P", "R", "2")
        assert (left.laterality, left.icdo3, left.primary_site) == (Laterality.LEFT, "8500/3", "C504")
        assert (right.laterality, right.icdo3, right.primary_site) == (Laterality.RIGHT, "8500/2", "C501")
        assert graph.registry_entry("P", "R") is None
        assert set(graph.exam("A").registry_entries) == {left, right}
        assert left.exams == right.exams == (graph.exam("A"),)
        assert len(graph.records("exam_registry")) == 2
        assert not [ref for ref in graph.unresolved_references if ref.target_kind == "registry"]


@pytest.mark.parametrize("mode", ["refresh", "merge"])
def test_partial_refresh_preserves_other_tumor_and_conflicts_stay_within_identity(mode):
    graph = load_embed(registry=ROWS, magview=[POINTER]).graph
    first = graph.registry_entry("P", "R", "1")
    second = graph.registry_entry("P", "R", "2")
    first.metadata["consumer"] = "keep"
    report = load_embed(registry=[ROWS[0], {**ROWS[0], "PRIMARY_SITE": "C500"}], into=graph, mode=mode)
    assert graph.registry_entry("P", "R", "1") is first
    assert first.primary_site is None and first.metadata == {"consumer": "keep"}
    assert graph.registry_entry("P", "R", "2") is second and second.primary_site == "C501"
    conflict = next(issue for issue in report.issues if issue.code == "conflicting_clinical_values")
    assert conflict.context["identity"] == ("P", "R", "1")
    assert len(graph.exam("A").registry_entries) == 2


@pytest.mark.parametrize("missing", ["absent", "null", "unbound"])
def test_missing_tumor_id_keeps_legacy_grouping_and_conflict_issues(missing):
    rows = [{key: value for key, value in row.items() if key != "TUMOR_RECORD_NUMBER"} for row in ROWS]
    if missing == "null":
        rows = [{**row, "TUMOR_RECORD_NUMBER": None} for row in rows]
    options = {"columns": {"registry": {"record_id": None}}} if missing == "unbound" else {}
    report = load_embed(registry=ROWS if missing == "unbound" else rows, **options)
    (entry,) = report.graph.registry_entries
    assert entry.identity == ("P", "R") and entry.record_id is None
    assert entry.laterality is Laterality.UNKNOWN
    assert entry.behavior is None and entry.primary_site is None
    assert any(issue.code == "conflicting_clinical_values" for issue in report.issues)


def test_explicit_sequence_number_mapping_and_patient_scope():
    rows = [{**{key: value for key, value in row.items() if key != "TUMOR_RECORD_NUMBER"},
             "SEQUENCE_NUMBER": row["TUMOR_RECORD_NUMBER"]} for row in ROWS]
    assert len(load_embed(registry=rows).graph.registry_entries) == 1
    rows.append({**rows[0], "empi_anon": "Q"})
    graph = load_embed(registry=rows, magview=[POINTER], columns={"registry": {"record_id": "SEQUENCE_NUMBER"}}).graph
    assert len(graph.registry_entries) == 3
    assert len(graph.exam("A").registry_entries) == 2
    assert graph.registry_entry("Q", "R", "1").exams == ()
    unkeyed = load_embed(registry=[{**ROWS[0], "cancer_outcome_registry_id": None}]).graph
    (record,) = unkeyed.records("unresolved")
    assert record["record_id"] == "1"
    assert not unkeyed.registry_entries


def test_group_pointer_reaches_later_tumors_and_refresh_can_clear_it():
    graph = load_embed(magview=[POINTER]).graph
    assert len(graph.records("exam_registry")) == 1  # Retained missing group reference.
    load_embed(registry=[ROWS[0]], into=graph)
    load_embed(registry=[ROWS[1]], into=graph)
    assert len(graph.exam("A").registry_entries) == 2
    load_embed(magview=[{**POINTER, "cancer_outcome_registry_id": None}], into=graph)
    assert graph.exam("A").registry_entries == ()
    assert len(graph.registry_entries) == 2


def test_exact_references_rekey_and_group_detachment():
    graph = load_embed(registry=ROWS, magview=[POINTER]).graph
    one, two = (graph.registry_entry("P", "R", str(number)) for number in (1, 2))
    exact = graph.register(Exam("EXACT", registry_references=[one.identity]))
    graph.rekey(one, record_id="3")
    assert exact.registry_references == {("P", "R", "3")}
    assert graph.registry_entry("P", "R", "1") is None
    assert set(graph.exam("A").registry_entries) == {one, two}
    graph.detach(graph.exam("A"), one)
    assert graph.exam("A").registry_entries == (two,)
    assert one.exams == (exact,)
    graph.remove(two)
    assert graph.exam("A").registry_entries == ()


def test_group_pointer_survives_adding_tumor_identity_to_legacy_entry():
    graph = DatasetGraph()
    exam = graph.register(Exam("A", registry_references=[("P", "R")]))
    entry = graph.register(CancerRegistryEntry("P", "R"))
    entry.record_id = "1"
    graph.register(CancerRegistryEntry("P", "R", record_id="2"))
    assert exam.registry_references == {("P", "R")}
    assert len(exam.registry_entries) == 2
    with pytest.raises(ValueError):
        entry.record_id = "2"
    assert entry.record_id == "1" and len(exam.registry_entries) == 2


def test_registry_projection_copies_selections_and_graph_transfer_keep_tumors():
    graph = load_embed(registry=ROWS, magview=[POINTER]).graph
    assert {item["record_id"] for item in graph.records("registry")} == {"1", "2"}
    assert {item["record_id"] for item in graph.to_dict()["registry"]} == {"1", "2"}
    selected = graph.select(level="exam", predicate=lambda exam: True)
    assert len(selected.records("exam_registry")) == 2
    part = graph.partition(level="exam", key=lambda exam: exam.accession_number)["A"]
    assert len(part.exam("A").registry_entries) == 2
    assert len(part.records("exam_registry")) == 2
    for entry in part.registry_entries:
        assert entry is not graph.registry_entry(*entry.identity)
        assert entry.exams == (part.exam("A"),)
    destination = DatasetGraph()
    destination.register(graph.exam("A"))
    assert len(destination.registry_entries) == 2 and not graph.registry_entries


def test_mixed_missing_and_populated_tumor_ids_remain_separate():
    graph = load_embed(registry=[*ROWS, {**ROWS[0], "TUMOR_RECORD_NUMBER": None}], magview=[POINTER]).graph
    assert len(graph.registry_entries) == 3
    assert graph.registry_entry("P", "R") is not None
    assert len(graph.exam("A").registry_entries) == 3



def test_detaching_from_mixed_group_requires_identifying_legacy_entry_first():
    graph = load_embed(registry=[*ROWS, {**ROWS[0], "TUMOR_RECORD_NUMBER": None}], magview=[POINTER]).graph
    exam = graph.exam("A")
    one = graph.registry_entry("P", "R", "1")
    with pytest.raises(ValueError):
        graph.detach(exam, one)
    assert len(exam.registry_entries) == 3
    graph.registry_entry("P", "R").record_id = "3"
    graph.detach(exam, one)
    assert {entry.record_id for entry in exam.registry_entries} == {"2", "3"}


def test_rekeying_legacy_member_does_not_move_group_pointer_away_from_siblings():
    graph = load_embed(registry=[*ROWS, {**ROWS[0], "TUMOR_RECORD_NUMBER": None}], magview=[POINTER]).graph
    legacy = graph.registry_entry("P", "R")
    graph.rekey(legacy, registry_id="OTHER")
    assert graph.exam("A").registry_references == {("P", "R")}
    assert len(graph.exam("A").registry_entries) == 2
    assert legacy.exams == ()
