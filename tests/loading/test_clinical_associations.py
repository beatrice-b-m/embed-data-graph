"""Clinical adapter contracts using synthetic, explicitly mapped registry data."""

from itertools import permutations

import pytest

from embed_data_graph.clinical.exams import Exam
from embed_data_graph.clinical.findings import Finding
from embed_data_graph.clinical.patients import Patient
from embed_data_graph.core.graph import DatasetGraph
from embed_data_graph import load_embed
from embed_data_graph.sources.embed.columns import resolve_columns


def test_out_of_range_severity_is_kept_raw_for_validation():
    graph = DatasetGraph()
    load(graph, pathology=[clinical_row(path_severity=99)])
    (pathology,) = graph.pathology
    assert (pathology.severity, pathology.raw_severity) == (None, 99)
    assert pathology.descriptors[0].descriptor.meaning == "Atypical ductal hyperplasia"


def load(graph, *, mode="refresh", columns=None, **tables):
    return list(load_embed(into=graph, mode=mode, columns=columns, **tables).issues)


def row(**fields):
    return dict(empi_anon="P", acc_anon="A", numfind="1", **fields)


@pytest.mark.parametrize("order", list(permutations(("exam", "assignment", "entry"))))
def test_registry_arrival_orders(order):
    graph = DatasetGraph()
    for step in order:
        if step == "exam":
            if graph.exam("A") is None:
                graph.register(Exam("A"))
        elif step == "assignment":
            load(graph, magview=[row(cancer_outcome_registry_id="7")] * 3)
            assert graph.exam("A").registry_references == {("P", "7")}
        else:
            load(graph, registry=[{"empi_anon": "P", "cancer_outcome_registry_id": "7"}])
    assert graph.exam("A").registry_entries == (
        graph.registry_entry("P", "7"),
    )


def test_registry_patient_scope_sharing_and_source_disagreement():
    graph = DatasetGraph()
    load(
        graph, registry=[{"empi_anon": p, "cancer_outcome_registry_id": 7} for p in ("P", "Q")]
    )
    load(
        graph,
        magview=[
            row(cancer_outcome_registry_id=7),
            {"empi_anon": "P", "acc_anon": "B", "cancer_outcome_registry_id": 7},
            {"empi_anon": "Q", "acc_anon": "A", "cancer_outcome_registry_id": 7},
        ],
    )
    assert len(graph.registry_entries) == 2
    assert graph.exam("A").patient_id is None
    assert graph.exam("A").asserted_patient_ids == {"P", "Q"}
    assert len(graph.exam("A").registry_entries) == 2
    assert graph.exam("B").registry_entries == (
        graph.registry_entry("P", "7"),
    )


def test_collection_refresh_absence_null_and_merge():
    graph = DatasetGraph()
    load(graph, magview=[row(cancer_outcome_registry_id="7", linkedaccession_anon="B")])
    assert graph.unresolved_references
    load(graph, magview=[row()])
    assert graph.exam("A").registry_references == {("P", "7")}
    assert graph.exam("A").linked_accessions == {"B"}
    load(
        graph,
        mode="merge",
        magview=[row(cancer_outcome_registry_id="8", linkedaccession_anon="C")],
    )
    assert graph.exam("A").registry_references == {("P", "7"), ("P", "8")}
    assert graph.exam("A").linked_accessions == {"B", "C"}
    load(
        graph, magview=[row(cancer_outcome_registry_id=None, linkedaccession_anon=None)]
    )
    assert not graph.exam("A").registry_references
    assert not graph.exam("A").linked_accessions


def clinical_row(**fields):
    result = row(
        procdate_anon="2020-01-01",
        type="biopsy",
        bside="L",
        pdate_anon="2020-01-02",
        path1="ADH",
        path2="ADH",
    )
    result.update(fields)
    return result


def test_repeated_narrow_wide_rows_share_descendants_and_preserve_parent():
    graph = DatasetGraph()
    graph.register(Patient("P"))
    graph.register(Exam("A", description="preserve"))
    graph.register(Finding("A", "L", "1"))
    graph.register(Finding("A", "L", "2"))
    first, second = clinical_row(), clinical_row(numfind="2")
    for rows in ([first, second], [second, first]):
        load(graph, magview=rows, procedures=rows, pathology=rows)
        assert len(graph.procedures) == len(graph.pathology) == 1
        assert graph.exam("A").description == "preserve"
        assert len(graph.patient("P").procedures) == 1
        assert len(graph.patient("P").pathology) == 1
        assert (
            graph.finding("A", "1").procedures[0]
            is graph.finding("A", "2").procedures[0]
        )
        assert [d.descriptor.code for d in graph.pathology[0].descriptors] == ["ADH", "ADH"]


def test_fallback_descriptor_conflict_unresolved_and_refresh_bounded():
    graph = DatasetGraph()
    rows = [clinical_row(), clinical_row(path1="DCIS")]
    for incoming in (rows, list(reversed(rows)), rows):
        issues = load(graph, pathology=incoming)
        assert "ambiguous_pathology_identity" in {i.code for i in issues}
        assert not graph.pathology
        assert sum(len(v) for v in graph.unresolved_records.values()) == 2
    load(graph, pathology=[clinical_row()])
    assert len(graph.pathology) == 1
    assert not graph.unresolved_records


def test_explicit_pathology_id_is_patient_scoped_and_preserves_reference():
    graph = DatasetGraph()
    columns = resolve_columns(None)
    columns["pathology"]["record_id"] = "report_id"
    load(
        graph,
        columns=columns,
        pathology=[
            clinical_row(report_id="R"),
            clinical_row(report_id="R", empi_anon="Q"),
        ],
    )
    assert len(graph.pathology) == 2
    obj = graph.get("pathology", ("P", "R"))
    load(graph, columns=columns, pathology=[clinical_row(report_id="R", path1="NEW")])
    assert graph.get("pathology", ("P", "R")) is obj
    assert obj.descriptors[0].descriptor.code == "NEW" and obj.descriptors[0].descriptor.meaning is None


def test_insufficient_identity_preserves_useful_snapshot():
    graph = DatasetGraph()
    issues = load(graph, procedures=[row(type="biopsy")], pathology=[row(path1="ADH")])
    assert {i.code for i in issues} >= {
        "incomplete_procedure_identity",
        "incomplete_pathology_identity",
    }
    assert not graph.procedures and not graph.pathology
    assert any(
        v[0]["payload"].get("path1") == "ADH" for v in graph.unresolved_records.values()
    )


def test_registry_payload_is_explicit_and_refreshes_only_bound_fields():
    graph = DatasetGraph()
    load(
        graph,
        registry=[{"empi_anon": "P", "cancer_outcome_registry_id": "7", "secret": "unused"}],
    )
    obj = graph.registry_entry("P", "7")
    assert dict(obj.payload) == {}
    columns = resolve_columns(None)
    columns["registry"]["diagnosis"] = "dx"
    load(
        graph,
        columns=columns,
        registry=[{"empi_anon": "P", "cancer_outcome_registry_id": "7", "dx": "supplied"}],
    )
    assert graph.registry_entry("P", "7") is obj
    assert obj.payload["diagnosis"] == "supplied"
    load(
        graph, columns=columns, registry=[{"empi_anon": "P", "cancer_outcome_registry_id": "7"}]
    )
    assert obj.payload["diagnosis"] == "supplied"
    load(
        graph,
        columns=columns,
        registry=[{"empi_anon": "P", "cancer_outcome_registry_id": "7", "dx": None}],
    )
    assert obj.payload["diagnosis"] is None


def test_unbound_collections_preserve_and_mapped_columns_are_used():
    graph = DatasetGraph()
    columns = resolve_columns(None)
    columns["magview"]["registry_assignment"] = "assignment"
    columns["magview"]["linked_accession"] = "link"
    load(graph, columns=columns, magview=[row(assignment="7", link="B")])
    columns["magview"]["registry_assignment"] = None
    columns["magview"]["linked_accession"] = None
    load(graph, columns=columns, magview=[row(assignment=None, link=None)])
    assert graph.exam("A").registry_references == {("P", "7")}
    assert graph.exam("A").linked_accessions == {"B"}


def test_conflicting_refresh_removes_prior_resolved_fallback():
    graph = DatasetGraph()
    load(graph, pathology=[clinical_row()])
    assert len(graph.pathology) == 1
    load(graph, pathology=[clinical_row(), clinical_row(path2="different")])
    assert not graph.pathology
    assert graph.unresolved_records


def test_scalar_conflict_is_unknown_and_unbound_pathology_fields_survive():
    graph = DatasetGraph()
    bound = resolve_columns({"pathology": {"diagnosis": "pathology_diagnosis"}})
    load(graph, columns=bound, pathology=[clinical_row(pathology_diagnosis="first")])
    obj = graph.pathology[0]
    load(graph, pathology=[clinical_row()])
    assert obj.diagnosis == "first"
    issues = load(
        graph,
        columns=bound,
        pathology=[
            clinical_row(pathology_diagnosis="a"),
            clinical_row(pathology_diagnosis="b"),
        ],
    )
    assert obj.diagnosis is None
    assert "conflicting_clinical_values" in {i.code for i in issues}


def test_registry_assignment_resolves_when_the_entry_arrives_later():
    graph = DatasetGraph()
    exam = graph.register(Exam("A"))
    graph.set_registry_assignments(exam, [("P", "7")])
    assert graph.unresolved_references
    load(graph, registry=[{"empi_anon": "P", "cancer_outcome_registry_id": "7"}])
    assert exam.registry_entries == (graph.registry_entry("P", "7"),)
    assert not graph.unresolved_references


def test_procedure_before_finding_resolves_and_exam_fallback_is_supported():
    graph = DatasetGraph()
    load(graph, procedures=[clinical_row()])
    assert len(graph.procedures) == 1
    graph.register(Finding("A", "L", "1"))
    assert graph.finding("A", "1").procedures[0] is graph.procedures[0]
    load(graph, procedures=[clinical_row(numfind=None, procdate_anon="2021-01-01")])
    assert len(graph.exam("A").procedures) == 2


def registry_row(registry_id=None, **fields):
    return {"empi_anon": "P", "cancer_outcome_registry_id": registry_id, **fields}


def test_registry_identity_defaults_to_the_magview_pointer_column():
    graph = DatasetGraph()
    load(graph, magview=[row(cancer_outcome_registry_id="7")], registry=[registry_row("7")])

    assert graph.exam("A").registry_entries == (graph.registry_entry("P", "7"),)


def test_patient_registry_entries_include_entries_no_exam_is_assigned_to():
    graph = DatasetGraph()
    load(graph, magview=[row(cancer_outcome_registry_id="7")], registry=[registry_row("7"), registry_row("8")])

    patient = graph.patient("P")

    assert patient.registry_entries == (graph.registry_entry("P", "7"), graph.registry_entry("P", "8"))
    assert graph.registry_entry("P", "8").exams == ()
    assert Patient("P").registry_entries == ()


def test_patient_registry_entries_follow_rekey_and_removal():
    graph = DatasetGraph()
    graph.register(Patient("P"))
    load(graph, registry=[registry_row("7")])
    entry = graph.registry_entry("P", "7")
    assert graph.patient("P").registry_entries == (entry,)

    entry.rekey(patient_id="Q")
    assert graph.patient("P").registry_entries == ()
    assert graph.register(Patient("Q")).registry_entries == (entry,)

    graph.remove(entry)
    assert graph.patient("Q").registry_entries == ()


def test_registry_rows_without_an_id_load_as_unkeyed_patient_records():
    graph = DatasetGraph()
    columns = {"registry": {"diagnosis": "dx"}}

    issues = load(graph, columns=columns, registry=[registry_row(dx="first"), registry_row(dx="second"), registry_row("7")])

    patient = graph.patient("P")
    assert [entry.payload for entry in patient.unkeyed_registry_entries] == [{"diagnosis": "first"}, {"diagnosis": "second"}]
    assert patient.registry_entries == (graph.registry_entry("P", "7"),)
    assert len(graph.registry_entries) == 1
    assert "incomplete_registry_identity" not in {issue.code for issue in issues}
    (info,) = [issue for issue in issues if issue.code == "unkeyed_registry_entries"]
    assert info.context["rows"] == 2


def test_registry_rows_create_the_patient_that_owns_unkeyed_records():
    graph = DatasetGraph()

    load(graph, registry=[registry_row()])

    assert len(graph.patient("P").unkeyed_registry_entries) == 1


def test_registry_rows_without_a_patient_are_still_rejected():
    graph = DatasetGraph()

    issues = load(graph, registry=[{"empi_anon": None, "cancer_outcome_registry_id": None}])

    assert graph.patients == () and graph.registry_entries == ()
    assert "incomplete_registry_identity" in {issue.code for issue in issues}


def test_refresh_replaces_each_addressed_patients_unkeyed_snapshot():
    graph = DatasetGraph()
    columns = {"registry": {"diagnosis": "dx"}}
    load(graph, columns=columns, registry=[registry_row(dx="old"), {"empi_anon": "Q", "cancer_outcome_registry_id": None}])

    load(graph, columns=columns, registry=[registry_row(dx="new")])
    assert [entry.payload["diagnosis"] for entry in graph.patient("P").unkeyed_registry_entries] == ["new"]
    assert len(graph.patient("Q").unkeyed_registry_entries) == 1

    # Once a patient's rows all carry IDs, the stale unkeyed records go.
    load(graph, columns=columns, registry=[registry_row("7", dx="new")])
    assert graph.patient("P").unkeyed_registry_entries == ()


def test_merge_preserves_unkeyed_records_and_reports_the_rows():
    graph = DatasetGraph()
    load(graph, registry=[registry_row()])
    stored = graph.patient("P").unkeyed_registry_entries

    issues = load(graph, mode="merge", registry=[registry_row(), registry_row("7")])

    assert graph.patient("P").unkeyed_registry_entries == stored
    assert graph.registry_entry("P", "7") is not None
    (warning,) = [issue for issue in issues if issue.code == "registry_merge_requires_registry_id"]
    assert warning.context == {"patient_id": "P", "rows": 1}


def test_unkeyed_registry_records_travel_with_patient_partitions_and_export():
    graph = DatasetGraph()
    load(graph, registry=[registry_row()])

    part = graph.partition(level="patient", key=lambda patient: patient.patient_id)["P"]

    copied = part.patient("P").unkeyed_registry_entries
    assert len(copied) == 1 and copied[0] is not graph.patient("P").unkeyed_registry_entries[0]
    assert part.to_dict()["patient"][0]["unkeyed_registry_entries"] == [{"payload": {}, "source": None}]


def full_registry_row(registry_id="7", **fields):
    return {
        "empi_anon": "P", "cancer_outcome_registry_id": registry_id, "DATE_OF_DIAGNOSIS_ANON": "2020-01-02",
        "LATERALITY": 2, "HISTOLOGY_ICDO3": 8500.0, "BEHAVIOR_ICDO3": 3, "PRIMARY_SITE": "C504",
        "T_Stage": "1c", "N_Stage": "0", "M_Stage": "0", "STAGE_GRP": "1A", "ESTROGEN_RECEPTOR": 1,
        "PROGESTERONE_RECEPTOR": 0, "HER2": 0, "VITAL_STATUS": 1, **fields,
    }


def test_registry_payload_loads_with_typed_views_by_default():
    graph = DatasetGraph()
    load(graph, registry=[full_registry_row()])

    entry = graph.registry_entry("P", "7")
    assert entry.diagnosis_date == "2020-01-02"
    assert (entry.laterality.value, entry.source_laterality) == ("L", "2")
    assert (entry.histology, entry.behavior, entry.icdo3, entry.primary_site) == ("8500", "3", "8500/3", "C504")
    assert (entry.t_stage, entry.n_stage, entry.m_stage, entry.stage_group) == ("1c", "0", "0", "1A")
    assert [code.code for code in (entry.estrogen_receptor, entry.progesterone_receptor, entry.her2)] == ["1", "0", "0"]
    assert entry.her2.meaning is None and entry.vital_status == "1"


@pytest.mark.parametrize("code", [3, 5, 9, 0, None])
def test_unspecified_registry_sides_load_as_unknown_and_are_kept(code):
    graph = DatasetGraph()
    load(graph, registry=[full_registry_row(LATERALITY=code), full_registry_row(None, LATERALITY=code)])

    patient = graph.patient("P")
    (keyed,) = patient.registry_entries
    (unkeyed,) = patient.unkeyed_registry_entries
    assert keyed.laterality.value == unkeyed.laterality.value == "UNKNOWN"
    assert keyed.icdo3 == unkeyed.icdo3 == "8500/3"


def test_registry_dates_from_timestamps_read_as_iso_days():
    from datetime import datetime

    graph = DatasetGraph()
    load(graph, registry=[full_registry_row(DATE_OF_DIAGNOSIS_ANON=datetime(2021, 5, 6, 0, 0))])

    assert graph.registry_entry("P", "7").diagnosis_date == "2021-05-06"


def test_conflicting_registry_rows_make_the_field_unknown():
    graph = DatasetGraph()
    issues = load(graph, registry=[full_registry_row(), full_registry_row(LATERALITY=1)])

    entry = graph.registry_entry("P", "7")
    assert entry.laterality.value == "UNKNOWN" and entry.source_laterality is None
    assert entry.histology == "8500"
    assert "conflicting_clinical_values" in {issue.code for issue in issues}


def test_procedure_keyed_severity_conflict_keeps_each_report_unresolved():
    graph = DatasetGraph()
    invasive, benign = clinical_row(path_severity=4), clinical_row(path_severity=5)
    for rows in ([invasive, benign], [benign, invasive]):
        issues = load(graph, pathology=rows)
        assert "ambiguous_pathology_identity" in {i.code for i in issues}
        assert not graph.pathology
        records = [e["record"] for v in graph.unresolved_records.values() for e in v]
        assert sorted(r.raw_severity for r in records if r.kind == "pathology") == [4, 5]
    load(graph, pathology=[invasive, clinical_row(path_severity=4.0)])  # Same code, no conflict.
    assert graph.pathology[0].raw_severity == 4
    assert not graph.unresolved_records
