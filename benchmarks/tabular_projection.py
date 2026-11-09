"""Synthetic load and projection measurements; pandas is optional until tables()."""
from __future__ import annotations

import argparse
import json
from time import perf_counter
import tracemalloc

from benchmarks.graph_loading import fixture
from embed_data_graph import load_embed


def measure(patients: int) -> dict[str, object]:
    """Measure one run, excluding input construction and pandas import costs."""
    import pandas  # noqa: F401

    inputs = fixture(patients)
    tracemalloc.start()
    started = perf_counter()
    graph = load_embed(**inputs).graph
    load_seconds = perf_counter() - started
    load_bytes = tracemalloc.get_traced_memory()[0]
    started = perf_counter()
    exams = graph.records("exams")
    records_seconds = perf_counter() - started
    assert len(exams) == patients
    started = perf_counter()
    tables = graph.tables()
    tables_seconds = perf_counter() - started
    retained, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return dict(patients=patients, input_rows=6 * patients, load_seconds=load_seconds,
                exam_records_seconds=records_seconds, all_tables_seconds=tables_seconds,
                load_bytes=load_bytes, retained_bytes=retained, peak_bytes=peak,
                output_rows=sum(len(frame) for frame in tables.values()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[100, 200, 400])
    args = parser.parse_args()
    print(json.dumps([measure(size) for size in args.sizes], indent=2))
