"""Time the graph and DataFrame stages used by embed-label-pipeline's default inputs."""

from __future__ import annotations

import argparse
import cProfile
import json
import platform
import pstats
import sys
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Optional

import pandas as pd

from embed_data_graph import load_embed
from embed_data_graph.sources.embed.columns import DEFAULT_COLUMNS

# inputs.parameters.views in embed-label-pipeline at eb4f8a1
VIEWS = (
    "patients", "exams", "findings", "procedures", "pathology", "registry",
    "exam_registry", "exam_patients", "exam_links", "procedure_findings", "procedure_exams",
    "pathology_procedures", "pathology_findings", "pathology_exams",
    "unresolved", "unresolved_values", "issues",
)


def write_fixture(directory: Path, patients: int, visits: int, incomplete_every: int,
                  wide: bool) -> dict[str, Path]:
    """Write fabricated CSVs. Missing columns and supplied nulls have distinct semantics."""
    magview, registry = [], []
    for p in range(patients):
        for visit in range(visits):
            n = p * visits + visit
            day = (date(2015, 1, 1) + timedelta(days=visit)).isoformat()
            base = dict(empi_anon=f"P{p}", acc_anon=f"A{n}", studydate_anon=day,
                        GENDER_DESC="Female", race="R", ethnicity="E", cohort_num="1",
                        age_at_study_anon="50", mg_exam_type="screening", desc="MG Screening Bilateral",
                        modality_desc="MG", tissueden="3", side="L", asses="B",
                        linkedaccession_anon=f"A{n - 1}" if visit else None)
            if visit == 0 and p % 10 == 0:
                registry.append(dict(empi_anon=f"P{p}", cancer_outcome_registry_id="1",
                                     TUMOR_RECORD_NUMBER="1", DATE_OF_DIAGNOSIS_ANON=day,
                                     LATERALITY="1", HISTOLOGY_ICDO3="8500", BEHAVIOR_ICDO3="3"))
                base["cancer_outcome_registry_id"] = "1"
            for f in range(2):
                row = dict(base, numfind=str(f + 1))
                if f == 1 and n % 5 == 0:
                    row.update(procdate_anon=day, type="B", bside="L", path1="1",
                               path_severity="2", pdate_anon=day)
                if f == 0 and incomplete_every and n % incomplete_every == 0:
                    # An assessment and a reported pathology without their full identities.
                    row.update(numfind=None, path_severity="2")
                magview.append(row)
    frame = pd.DataFrame(magview)
    if wide:
        physical = {column for table in ("patients", "exams", "findings", "procedures", "pathology", "magview")
                    for column in DEFAULT_COLUMNS[table].values() if column}
        columns = sorted(physical | set(frame.columns))
        columns.extend(f"unused_{i}" for i in range(152 - len(columns)))
        frame = frame.reindex(columns=columns)
    paths = {name: directory / (name + ".csv") for name in ("magview", "registry")}
    frame.to_csv(paths["magview"], index=False)
    pd.DataFrame(registry).to_csv(paths["registry"], index=False)
    return paths


def read_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".pq", ".parquet"}:
        return pd.read_parquet(path)
    return pd.read_csv(path, dtype=str, low_memory=False)


def peak_rss_mib() -> Optional[float]:
    """Process lifetime high water, including imports, inputs and retained views."""
    if sys.platform != "darwin" and not sys.platform.startswith("linux"):
        return None
    import resource

    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(raw / (1024 ** 2 if sys.platform == "darwin" else 1024), 1)


def batch_views(graph):
    """Test one traversal over exactly the views ELP requests."""
    from embed_data_graph.core.tabular import dataframe, project, table_schema

    records = project(graph, VIEWS)
    return {name: dataframe(records.pop(name), table_schema(name)) for name in VIEWS}


def measure(paths: dict[str, Path], profile_stage: Optional[str], compare_views: bool,
            batch_only: bool) -> dict:
    profile = cProfile.Profile()
    started = perf_counter()
    frames = {table: read_frame(path) for table, path in paths.items()}
    read_end = perf_counter()
    if profile_stage == "graph":
        profile.enable()
    report = load_embed(**frames, invalid_accessions=("999",))
    if profile_stage == "graph":
        profile.disable()
    graph_end = perf_counter()
    rss_graph = peak_rss_mib()
    tables, view_times = {}, {}
    if profile_stage == "views":
        profile.enable()
    views_start = perf_counter()
    if batch_only:
        tables = batch_views(report.graph)
    else:
        for name in VIEWS:
            view_start = perf_counter()
            tables[name] = report.graph.table(name)
            view_times[name] = perf_counter() - view_start
    views_seconds = perf_counter() - views_start
    if profile_stage == "views":
        profile.disable()
    rss_views = peak_rss_mib()
    result = dict(
        python=platform.python_version(), pandas=pd.__version__, platform=platform.platform(),
        shape={name: list(frame.shape) for name, frame in frames.items()},
        graph_issues=len(report.issues), rows={name: len(frame) for name, frame in tables.items()},
        read_s=read_end - started, graph_s=graph_end - read_end,
        views_s=views_seconds, view_s=view_times, projection="batch" if batch_only else "separate",
        peak_rss_mib_after_graph=rss_graph, peak_rss_mib_after_views=rss_views,
    )
    if profile_stage:
        pstats.Stats(profile, stream=sys.stderr).strip_dirs().sort_stats("cumulative").print_stats(35)
        pstats.Stats(profile, stream=sys.stderr).strip_dirs().sort_stats("tottime").print_stats(20)
    if compare_views:
        # Prototype for a public selected-table batch operation. It must return
        # identical detached snapshots including diagnostic IDs and nullable dtypes.
        start = perf_counter()
        batched = batch_views(report.graph)
        result["batched_views_s"] = perf_counter() - start
        for name in VIEWS:
            pd.testing.assert_frame_equal(tables[name], batched[name])
    return result


def positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patients", type=positive_int, default=250)
    parser.add_argument("--visits", type=positive_int, default=3, help="exams per synthetic patient")
    parser.add_argument("--incomplete-every", type=int, default=10,
                        help="include incomplete evidence every N exams, or 0 for complete keys")
    parser.add_argument("--narrow", action="store_true", help="only include generated source fields")
    parser.add_argument("--magview", type=Path, help="measure an existing CSV or Parquet input")
    parser.add_argument("--registry", type=Path, help="optional existing registry input with --magview")
    parser.add_argument("--profile", choices=["graph", "views"], help="print cProfile statistics to stderr")
    projection = parser.add_mutually_exclusive_group()
    projection.add_argument("--compare-views", action="store_true", help="also time and verify a batched projection")
    projection.add_argument("--batch-only", action="store_true", help="measure batched views in isolation")
    args = parser.parse_args()
    if args.registry and not args.magview:
        parser.error("--registry requires --magview")
    if args.incomplete_every < 0:
        parser.error("--incomplete-every cannot be negative")
    with TemporaryDirectory() as directory:
        if args.magview:
            paths = {"magview": args.magview}
            if args.registry:
                paths["registry"] = args.registry
        else:
            paths = write_fixture(Path(directory), args.patients, args.visits, args.incomplete_every,
                                  not args.narrow)
        result = measure(paths, args.profile, args.compare_views, args.batch_only)
        if not args.magview:
            exams = args.patients * args.visits
            unkeyed = len(range(0, exams, args.incomplete_every)) if args.incomplete_every else 0
            assert result["rows"]["patients"] == args.patients
            assert result["rows"]["exams"] == exams
            assert result["rows"]["findings"] == exams * 2 - unkeyed
            assert result["rows"]["unresolved"] == 2 * unkeyed
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
