from datetime import datetime
import json
import os
import subprocess
import sys

import pandas as pd
import pytest

from embed_data_graph import load_embed


def sample():
    return load_embed(
        magview=[{"empi_anon": "P", "acc_anon": "A", "numfind": 1, "side": "L", "asses": "A",
                  "studydate_anon": "2020-01-02", "recc": "B,U", "massshape": "R",
                  "type": "B", "procdate_anon": "2020-01-03", "bside": "L", "path_severity": 0,
                  "path1": "1", "cancer_outcome_registry_id": "R"},
                 {"empi_anon": "Q", "acc_anon": "B", "numfind": 1, "asses": "N", "studydate_anon": "bad"}],
        images=[{"empi_anon": "P", "acc_anon": "A", "anon_dicom_path": "I.dcm", "ROI_coords": [[0, 0, 10, 10]]}],
        registry=[{"empi_anon": "P", "cancer_outcome_registry_id": "R", "DATE_OF_DIAGNOSIS_ANON": "2020-01-04"}],
    ).graph


def test_each_entity_has_one_flat_row_and_stable_empty_schema():
    graph = sample()
    tables = graph.tables()
    for table in ("patients", "exams", "findings", "procedures", "pathology", "registry", "images", "rois"):
        kind = {"patients": "patient", "exams": "exam", "findings": "finding", "procedures": "procedure", "images": "image", "rois": "roi"}.get(table, table)
        expected = graph.select(level=kind, predicate=lambda obj: True)
        rows = graph.records(table)
        assert len(rows) == len(expected)
        assert len({row["entity_key"] for row in rows}) == len(rows)
        assert list(tables[table].columns) == list(graph.table_schema(table).columns)
        assert all(value is None or isinstance(value, (str, int, float, bool, datetime)) for row in rows for value in row.values())
    assert tables["findings"].loc[tables["findings"].assessment == "A", "accession_number"].tolist() == ["A"]
    assert tables["procedures"].patient_id.tolist() == ["P"]
    assert tables["pathology"].patient_id.tolist() == ["P"]
    assert tables["pathology"].performed_date.iloc[0] == pd.Timestamp("2020-01-03")
    assert len(tables["procedure_findings"]) == len(tables["exam_registry"]) == 1
    assert pd.api.types.is_datetime64_ns_dtype(tables["exams"].exam_date)
    assert pd.isna(tables["exams"].loc[tables["exams"].accession_number == "B", "exam_date"].iloc[0])
    issue = tables["issues"].query("code == 'invalid_date'").iloc[0]
    assert issue.entity_key == tables["exams"].query("accession_number == 'B'").iloc[0].entity_key
    empty = load_embed().graph.tables()
    assert empty["exams"].dtypes.equals(tables["exams"].dtypes)


def test_physical_mapping_and_dataframe_index_do_not_change_projections():
    rows = [{"empi_anon": "P", "acc_anon": "B", "numfind": 2, "asses": "N"},
            {"empi_anon": "P", "acc_anon": "A", "numfind": 1, "asses": "A"}]
    graph = load_embed(magview=rows).graph
    frame = pd.DataFrame(rows[::-1], index=[7, 7])
    other = load_embed(magview=frame).graph
    for name in graph.tables():
        assert graph.records(name) == other.records(name)
    renamed = [{"person": row["empi_anon"], "exam": row["acc_anon"], "finding": row["numfind"], "result": row["asses"]} for row in rows]
    columns = {table: {"patient_id": "person", "accession": "exam"} for table in ("patients", "exams", "findings", "magview", "procedures", "pathology")}
    for table in ("findings", "magview", "procedures", "pathology"):
        columns[table]["finding_number"] = "finding"
    columns["findings"]["assessment"] = "result"
    other = load_embed(magview=renamed, columns=columns).graph
    for name in graph.tables():
        assert graph.records(name) == other.records(name)


def test_partition_and_selection_match_and_do_not_copy_consumer_state():
    graph = sample()
    selected = graph.select(level="patient", predicate=lambda p: p.patient_id == "P")
    part = graph.partition(level="patient", key=lambda p: p.patient_id)["P"]
    for name in graph.tables():
        assert selected.records(name) == part.records(name)
        if name not in {"issues"}:
            assert all(row in graph.records(name) for row in part.records(name))
    graph.patient("P").metadata["private"] = object()
    graph.patient("P").consumer = "private"
    assert "private" not in str(selected.records("values"))
    rows = selected.records("patients")
    rows[0]["patient_id"] = "changed"
    assert graph.patient("P").patient_id == "P"


def test_unresolved_assessments_pathology_and_invalid_accessions_are_visible():
    graph = load_embed(magview=[{"empi_anon": "P", "acc_anon": "A", "numfind": None, "asses": "A"},
                               {"empi_anon": "Q", "acc_anon": 999, "asses": "N"}],
                       pathology=[{"empi_anon": "P", "acc_anon": "A", "type": "B", "path_severity": 0}]).graph
    rows = graph.records("unresolved")
    assert any(r["patient_id"] == "P" and r["assessment"] == "A" and r["incomplete"] for r in rows)
    assert any(r["patient_id"] == "P" and r["kind"] == "pathology" and r["severity"] == 0 for r in rows)
    assert any(r["patient_id"] == "Q" and r["reason"] == "invalid_accession" for r in rows)
    assert len({r["record_key"] for r in rows}) == len(rows)


def test_records_do_not_import_pandas_and_are_hash_seed_independent():
    script = '''
import sys, json
sys.modules['pandas'] = None
from embed_data_graph import load_embed
rows = [{'empi_anon': 'P', 'acc_anon': a, 'numfind': 1, 'asses': 'A'} for a in {'A', 'B'}]
graph = load_embed(magview=rows).graph
print(json.dumps({name: graph.records(name) for name in ('patients', 'exams', 'findings', 'issues')}, default=str, sort_keys=True))
assert sys.modules['pandas'] is None
'''
    outputs = [subprocess.check_output([sys.executable, "-c", script], env={**os.environ, "PYTHONHASHSEED": str(seed)}, text=True) for seed in (1, 9)]
    assert json.loads(outputs[0]) == json.loads(outputs[1])


def test_unknown_schema_rejected_and_schemas_cannot_be_mutated():
    graph = sample()
    with pytest.raises(ValueError):
        graph.records("not-a-table")
    with pytest.raises(TypeError):
        graph.table_schema("exams").columns["new"] = "string"


@pytest.mark.parametrize("value, expected", [
    ("2020-01-02T03:00:00+03:00", datetime(2020, 1, 2)),
    ("01/02/2020", datetime(2020, 1, 2)),
    ("2020-01-02garbage", None),
    ("1500-01-01", None),
    (None, None),
])
def test_date_contract_is_shared_by_records_and_frames(value, expected):
    graph = load_embed(registry=[{"empi_anon": "P", "cancer_outcome_registry_id": "R", "DATE_OF_DIAGNOSIS_ANON": value}]).graph
    row, = graph.records("registry")
    assert row["diagnosis_date"] == expected
    frame_value = graph.table("registry").diagnosis_date.iloc[0]
    assert pd.isna(frame_value) if expected is None else frame_value == pd.Timestamp(expected)
    diagnostics = graph.records("issues")
    assert any(r["entity_key"] == row["entity_key"] and r["field"] == "diagnosis_date" for r in diagnostics) == (expected is None)


def test_issue_history_is_deduplicated_and_subset_addressed():
    graph = load_embed(exams=[{"acc_anon": "A", "studydate_anon": "first"}, {"acc_anon": "A", "studydate_anon": "second"}]).graph
    first = graph.records("issues")
    conflicts = [r for r in first if r["code"] == "conflicting_exam_exam_date"]
    assert len(conflicts) == 1 and conflicts[0]["entity_key"] == graph.records("exams")[0]["entity_key"]
    before = graph.load_issues
    load_embed(exams=[{"acc_anon": "A", "studydate_anon": "first"}, {"acc_anon": "A", "studydate_anon": "second"}], into=graph)
    assert graph.load_issues == before
    part = graph.partition(level="exam", key=lambda e: e.accession_number)["A"]
    assert conflicts[0] in part.records("issues")
    load_embed(exams=[{"acc_anon": "A", "studydate_anon": "2020-01-01"}], into=graph)
    assert graph.load_issues == before
    assert not any(r["code"] == "missing_date" for r in graph.records("issues"))


def test_roi_projection_preserves_exclusive_stops_and_source_convention():
    graph = sample()
    row, = graph.records("rois")
    assert (row["y_min"], row["x_min"], row["y_stop"], row["x_stop"]) == (0, 0, 11, 11)
    assert (row["source_y_max"], row["source_x_max"]) == (10, 10)
    assert row["source_coordinate_convention"] == "inclusive_maxima"


def test_unkeyed_registry_projection_is_independent_of_input_order():
    rows = [
        {"empi_anon": "P", "DATE_OF_DIAGNOSIS_ANON": "2020-01-01", "HISTOLOGY_ICDO3": "8500"},
        {"empi_anon": "P", "DATE_OF_DIAGNOSIS_ANON": "2021-01-01", "HISTOLOGY_ICDO3": "8520"},
    ]
    first = load_embed(registry=rows + rows[:1]).graph
    reordered = load_embed(registry=list(reversed(rows + rows[:1]))).graph
    for name in ("unresolved", "unresolved_values", "issues"):
        assert first.records(name) == reordered.records(name)
    assert len(first.records("unresolved")) == 3
    assert len({row["record_key"] for row in first.records("unresolved")}) == 3


def test_invalid_accession_diagnostics_follow_the_patient_into_subsets():
    graph = load_embed(magview=[{"empi_anon": p, "acc_anon": 999, "asses": "A"}
                               for p in ("P", "Q")]).graph
    selected = graph.select(level="patient", predicate=lambda p: p.patient_id == "P")
    part = graph.partition(level="patient", key=lambda p: p.patient_id)["P"]
    patient_key = selected.records("patients")[0]["entity_key"]
    for subset in (selected, part):
        issues = [row for row in subset.records("issues") if row["code"] == "invalid_accession"]
        assert len(issues) == 1
        assert issues[0]["kind"] == "patient" and issues[0]["entity_key"] == patient_key
        assert issues[0] in graph.records("issues")
    unowned = load_embed(exams=[{"acc_anon": 999}]).graph
    issue = next(row for row in unowned.records("issues") if row["code"] == "invalid_accession")
    assert issue["entity_key"] is None
