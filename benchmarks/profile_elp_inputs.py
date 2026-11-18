"""Measure the initial load inside an installed embed-label-pipeline environment.

Run `python profile_elp_inputs.py paths.yaml [--override study.yaml]`.
Use a fresh process for each comparison. Peak resident memory is the process
high-water mark in MiB, including imports and all preceding stages. It can stay
flat as memory is freed. For a second run, add `--profile graph` or
`--profile views` for function statistics on stderr. Profiling adds overhead.
"""

from __future__ import annotations

import argparse
import cProfile
import json
import platform
import pstats
import sys
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import pandas as pd
import yaml

import embed_label_pipeline as elp
import embed_label_pipeline.inputs as io
from embed_data_graph import DatasetGraph
from embed_label_pipeline.run import peak_memory_mb


def measure(paths: Path, defs: elp.Definitions, profile_stage: str | None) -> dict:
    seconds = Counter()
    file_seconds = []
    view_seconds = Counter()
    peak_mib = {}
    profiler = cProfile.Profile() if profile_stage else None

    def timed(func, stage):
        def call(*args, **kwargs):
            start = perf_counter()
            if profiler is not None and stage == profile_stage:
                result = profiler.runcall(func, *args, **kwargs)
            else:
                result = func(*args, **kwargs)
            elapsed = perf_counter() - start
            seconds[stage] += elapsed
            peak_mib[stage] = peak_memory_mb()
            if stage == "read":
                file_seconds.append(elapsed)
            elif stage == "views":
                view_seconds[args[1]] += elapsed
            return result
        return call

    # ELP imports load_embed into its inputs module. Wrap that binding so the
    # real call receives the same tables, sentinel values and column overrides.
    with ExitStack() as stack:
        for target, attr, stage in [(io, "read_table", "read"), (io, "load_embed", "graph"),
                                    (DatasetGraph, "table", "views"), (io, "summarize_views", "summary")]:
            stack.enter_context(patch.object(target, attr, timed(getattr(target, attr), stage)))
        start = perf_counter()
        inputs = elp.load_inputs(paths, defs, progress=False)
        total = perf_counter() - start
        peak_mib["total"] = peak_memory_mb()

    # ELP reads files in paths.yaml order; its source summary uses definition
    # order. Label each file duration with its role without printing paths.
    roles = yaml.safe_load(paths.read_text(encoding="utf-8"))
    assert len(roles) == len(file_seconds)
    shapes = {row.role: [int(row.rows), int(row.columns)] for row in inputs.sources.itertuples()
              if row.status == "loaded"}
    rows = {view: len(frame) for view, frame in inputs.tables.items()}
    assert dict(zip(inputs.summary["view"], inputs.summary["rows"])) == rows
    assert set(view_seconds) == set(rows)
    if profiler is not None and profiler.getstats():
        pstats.Stats(profiler, stream=sys.stderr).strip_dirs().sort_stats("cumulative").print_stats(35)
    return {
        "python": platform.python_version(), "pandas": pd.__version__, "profiled_stage": profile_stage,
        "shape": shapes, "rows": rows, "graph_issues": len(inputs.report.issues),
        "read_s": seconds["read"], "file_s": dict(zip(roles, file_seconds)), "graph_s": seconds["graph"],
        "views_s": seconds["views"], "view_s": view_seconds, "summary_s": seconds["summary"],
        "total_s": total, "other_s": total - sum(seconds.values()), "peak_rss_mib_after": peak_mib,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", type=Path, help="ELP paths YAML mapping input roles to source files")
    parser.add_argument("--override", action="append", type=Path, help="repeat in definition application order")
    parser.add_argument("--profile", choices=("graph", "views"), help="collect cProfile statistics on stderr")
    args = parser.parse_args()
    defs = elp.load_definitions(overrides=args.override)
    print(json.dumps(measure(args.paths, defs, args.profile), indent=2))


if __name__ == "__main__":
    main()
