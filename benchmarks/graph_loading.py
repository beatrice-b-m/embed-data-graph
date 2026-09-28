"""Multi-grain synthetic construction and fixed-patient update measurements."""
from __future__ import annotations

import argparse
import gc
import json
import platform
import statistics
import tracemalloc
from time import perf_counter
from typing import Any, Dict

from embed_data_graph import load_embed


def fixture(patient_count: int) -> Dict[str, list[dict[str, Any]]]:
    tables: Dict[str, list[dict[str, Any]]] = {name: [] for name in ("magview", "images", "registry")}
    for index in range(patient_count):
        patient, accession = "P" + str(index), "A" + str(index)
        for finding in (1, 2):
            for procedure in (1, 2):
                tables["magview"].append({
                    "empi_anon": patient, "acc_anon": accession,
                    "numfind": finding, "side": "L", "bside": "L",
                    "procdate_anon": "2020-01-0" + str(procedure), "type": "biopsy",
                    "pdate_anon": "2020-02-0" + str(procedure), "path1": "reported finding",
                    "cancer_outcome_registry_id": 1,
                    "linkedaccession_anon": "A" + str(index + 1) if index + 1 < patient_count else None,
                })
        tables["images"].append({
            "empi_anon": patient, "acc_anon": accession,
            "anon_dicom_path": f"/data/cohort1/{patient}/study/series/SOP{index}.dcm",
            "ImageLateralityFinal": "L", "ViewPosition": "CC", "Modality": "MG",
            "Rows": 1000, "Columns": 1000, "ROI_coords": "[(1, 2, 10, 20), (1, 2, 10, 20)]",
        })
        tables["registry"].append({"empi_anon": patient, "cancer_registry_id": 1})
    return tables


def assert_cardinality(graph: Any, size: int) -> Dict[str, int]:
    counts = {name: len(getattr(graph, name)) for name in (
        "patients", "exams", "findings", "procedures", "pathology", "images", "rois", "registry_entries")}
    expected = dict(patients=size, exams=size, findings=2 * size, procedures=2 * size,
                    pathology=2 * size, images=size, rois=2 * size, registry_entries=size)
    assert counts == expected, (counts, expected)
    assert len(graph.patient("P0").procedures) == 2
    assert len(graph.exam("A0").registry_entries) == 1
    return counts


def measure(size: int, repeats: int = 3) -> Dict[str, Any]:
    tables = fixture(size)  # Input setup excluded from timed work and memory.
    elapsed, peaks, retained, updates, subsets, batches, deferred = [], [], [], [], [], [], []
    counts: Dict[str, int] = {}
    for _ in range(repeats):
        gc.collect()
        tracemalloc.start()
        started = perf_counter()
        graph = load_embed(**tables).graph
        elapsed.append(perf_counter() - started)
        current, peak = tracemalloc.get_traced_memory()
        retained.append(current)
        peaks.append(peak)
        tracemalloc.stop()
        counts = assert_cardinality(graph, size)
        update_rows = [{"acc_anon": "A0", "desc": "reviewed"}]
        started = perf_counter()
        for _ in range(50):
            load_embed(exams=update_rows, into=graph)
        updates.append((perf_counter() - started) / 50)
        # Complete patient groups: each invocation is a distinct refresh snapshot.
        started = perf_counter()
        subset = load_embed(magview=tables["magview"][:4], images=tables["images"][:1], registry=tables["registry"][:1]).graph
        subsets.append(perf_counter() - started)
        assert_cardinality(subset, 1)
        batch_graph = load_embed().graph
        started = perf_counter()
        for offset in range(0, size, 25):
            load_embed(magview=tables["magview"][offset * 4:(offset + 25) * 4],
                       images=tables["images"][offset:offset + 25],
                       registry=tables["registry"][offset:offset + 25], into=batch_graph)
        batches.append(perf_counter() - started)
        assert_cardinality(batch_graph, size)
        late_graph = load_embed(magview=tables["magview"], images=tables["images"]).graph
        started = perf_counter()
        load_embed(registry=tables["registry"], into=late_graph)
        deferred.append(perf_counter() - started)
        assert_cardinality(late_graph, size)
    return {"patients": size, "rows": sum(map(len, tables.values())), "objects": counts,
            "edges": sum(len(graph.parents(item)) for kind in ("exam", "finding", "procedure", "pathology", "registry", "image", "roi")
                         for item in getattr(graph, {"registry": "registry_entries"}.get(kind, kind + "s" if kind != "pathology" else kind)))
                     + sum(len(exam.linked_exams) for exam in graph.exams) // 2, "repeats": repeats,
            "median_seconds": statistics.median(elapsed),
            "median_peak_bytes": statistics.median(peaks),
            "median_retained_bytes": statistics.median(retained),
            "fixed_patient_update_seconds": statistics.median(updates),
            "patient_subset_seconds": statistics.median(subsets),
            "batched_seconds": statistics.median(batches),
            "late_registry_seconds": statistics.median(deferred)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps({"environment": {"python": platform.python_version(), "platform": platform.platform()},
                      "measurements": [measure(args.base * factor, args.repeats) for factor in (1, 2, 4)]}, indent=2))
