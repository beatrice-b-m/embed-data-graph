"""Build the EMBED graph assembly page: one graph, loaded table by table.

Runs ``embed_data_graph`` on synthetic rows through four calls: MagView rows
only, an exam-level partition to the flagged workup, the whole image table and
then the registry, both with ``parents="existing"``. The graph is recorded after
each call and rendered as a self-contained, step-through HTML page in the Bea
style. Every node, edge, unresolved key, skip count and Python object id on the
page is read back from the library's objects; nothing is drawn by hand.

    python -m tools.visualization.graph_assembly
    python -m tools.visualization.graph_assembly --out figure.html --scale-patients 0
    python -m tools.visualization.graph_assembly --bea-dir <bea-style>/assets --vendor

The page loads Inter and JetBrains Mono from Google Fonts; everything else is
inlined. No EMBED data is read.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import shutil
import subprocess
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import embed_data_graph
from embed_data_graph import DatasetGraph, load_embed

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TEMPLATE = HERE / "graph_assembly.html"
VENDORED_BEA = HERE / "bea"
BEA_FILES = ("tokens.css", "bea.css", "bea.js")
DEFAULT_OUT = REPO / "build" / "visualization" / "graph-assembly.html"

KINDS = ("patient", "exam", "finding", "procedure", "pathology", "registry", "image", "roi")
COLLECTIONS = {
    "patient": "patients",
    "exam": "exams",
    "finding": "findings",
    "procedure": "procedures",
    "pathology": "pathology",
    "registry": "registry_entries",
    "image": "images",
    "roi": "rois",
}
FLAGGED = {"S", "M"}  # BI-RADS suspicious, highly suggestive of malignancy

# accession: (patient, exam date, description, findings as (number, side, assessment))
EXAMS: Dict[str, Tuple[str, str, str, List[Tuple[int, str, str]]]] = {
    "A101": ("P01", "2019-03-04", "screening", [(1, "L", "N")]),
    "A102": ("P01", "2019-03-18", "diagnostic", [(1, "L", "S"), (2, "R", "B")]),
    "A201": ("P02", "2020-01-10", "screening", [(1, "R", "B")]),
    "A301": ("P03", "2018-06-02", "screening", [(1, "L", "A")]),
    "A302": ("P03", "2018-06-02", "diagnostic", [(1, "L", "M")]),
    "A401": ("P04", "2021-09-14", "screening", [(1, "B", "N")]),
    "A501": ("P05", "2020-11-30", "diagnostic", [(1, "R", "S")]),
    "A502": ("P05", "2021-05-30", "screening", [(1, "R", "P")]),
    "A601": ("P06", "2022-02-02", "screening", [(1, "L", "N")]),
}
BIOPSY_DATES = {("A102", 1): "2019-03-25", ("A302", 1): "2018-06-20", ("A501", 1): "2020-12-08"}
LINKS = {"A302": "A301"}  # a same-day screening and diagnostic workup
REGISTRY = {"A102": ("P01", 11), "A302": ("P03", 31)}
UNASSIGNED_REGISTRY = ("P06", 61)  # a registry entry for a patient outside the subset
VIEWS = (("L", "CC"), ("L", "MLO"), ("R", "CC"), ("R", "MLO"))
ROI = "[(812, 1204, 1030, 1391)]"


# -- synthetic tables ----------------------------------------------------------


def story_tables() -> Dict[str, List[Dict[str, Any]]]:
    """Return the synthetic MagView, image and registry rows for the story.

    The image table covers all nine exams, so loading it into the subset shows
    which rows attach and which are skipped. Flagged findings get an ROI on the
    CC view of their side.
    """

    magview: List[Dict[str, Any]] = []
    images: List[Dict[str, Any]] = []
    for accession, (patient, exam_date, description, findings) in EXAMS.items():
        for number, side, assessment in findings:
            row: Dict[str, Any] = {
                "empi_anon": patient, "acc_anon": accession, "studydate_anon": exam_date,
                "desc": description, "numfind": number, "side": side, "asses": assessment,
            }
            biopsy = BIOPSY_DATES.get((accession, number))
            if biopsy is not None:
                row.update(procdate_anon=biopsy, type="B", bside=side, pdate_anon=biopsy, path1="reported")
            if accession in LINKS:
                row["linkedaccession_anon"] = LINKS[accession]
            if accession in REGISTRY:
                row["cancer_outcome_registry_id"] = REGISTRY[accession][1]
            magview.append(row)
        for side, view in VIEWS:
            sop = f"{accession}{side}{view}"
            image: Dict[str, Any] = {
                "empi_anon": patient, "acc_anon": accession,
                "anon_dicom_path": f"/embed/cohort1/{patient}/{accession}S/{accession}{side}/{sop}.dcm",
                "ImageLateralityFinal": side, "ViewPosition": view, "Modality": "MG",
                "FinalImageType": "2D", "Rows": 4096, "Columns": 3328,
            }
            if view == "CC" and any(f_side == side and code in FLAGGED for _, f_side, code in findings):
                image["ROI_coords"] = ROI
            images.append(image)
    registry = [{"empi_anon": patient, "cancer_registry_id": entry} for patient, entry in REGISTRY.values()]
    registry.append({"empi_anon": UNASSIGNED_REGISTRY[0], "cancer_registry_id": UNASSIGNED_REGISTRY[1]})
    return {"magview": magview, "images": images, "registry": registry}


def flagged(finding: Any) -> bool:
    """Whether a finding is BI-RADS suspicious or highly suggestive (S or M)."""

    interpretation = finding.interpretation
    assessment = interpretation.assessment if interpretation else None
    return assessment is not None and assessment.code in FLAGGED


def flag_workup(graph: DatasetGraph) -> None:
    """Mark exams with a flagged finding as ``"workup"``; the page shows this code."""

    for exam in graph.exams:
        hits = any(map(flagged, exam.findings))
        exam.review_flag = "workup" if hits else None


def workup_partition(graph: DatasetGraph) -> DatasetGraph:
    """Return the independent partition holding the flagged exams."""

    return graph.partition(level="exam", key=lambda exam: exam.review_flag or [])["workup"]


# -- snapshots -----------------------------------------------------------------


def short_key(kind: str, key: Any) -> str:
    """Return a readable, stable id for an entity key."""

    if kind in ("procedure", "pathology"):
        identity = key if kind == "procedure" else key[1]
        return f"{identity.patient_id}/{identity.performed_date}/{identity.laterality.value}"
    if isinstance(key, tuple):
        return "/".join(str(part) for part in key)
    return str(key)


def node_id(entity: Any) -> str:
    return f"{entity.kind}:{short_key(entity.kind, entity.key)}"


def target_id(kind: str, raw: str) -> str:
    """Node id for an ``UnresolvedReference`` target, whose key arrives as text."""

    import ast

    try:
        key = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        key = raw
    return f"{kind}:{short_key(kind, key)}"


def label(entity: Any) -> str:
    kind = entity.kind
    if kind == "finding":
        interpretation = entity.interpretation
        assessment = interpretation.assessment if interpretation is not None else None
        code = f" · {assessment.code}" if assessment is not None else ""
        return f"#{entity.finding_number} {entity.laterality.value}{code}"
    if kind == "image":
        return f"{entity.laterality.value} {entity.view_position.value}"
    if kind == "roi":
        return f"ROI {entity.roi_key}"
    if kind == "registry":
        return f"registry {entity.registry_id}"
    if kind == "patient":
        return entity.patient_id
    if kind == "exam":
        return entity.accession_number
    return kind


def node(graph: DatasetGraph, entity: Any) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "id": node_id(entity), "kind": entity.kind, "label": label(entity),
        "context": graph.is_context(entity), "py": hex(id(entity)),
    }
    if entity.kind == "exam":
        record.update(patient=entity.patient_id, description=entity.description, date=entity.exam_date)
    elif entity.kind in ("finding", "image"):
        record["exam"] = entity.accession_number
        if entity.kind == "finding":
            assessment = entity.interpretation.assessment if entity.interpretation is not None else None
            record["assessment"] = assessment.meaning if assessment is not None else None
    elif entity.kind == "procedure":
        record.update(date=entity.identity.performed_date, type=entity.identity.procedure_type.meaning)
    return record


def snapshot(graph: DatasetGraph, tracked: Iterable[Tuple[str, Any]] = ()) -> Dict[str, Any]:
    """Record the graph's entities, edges, unresolved keys and counts."""

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, str]] = []
    for kind in KINDS:
        for entity in getattr(graph, COLLECTIONS[kind]):
            nodes.append(node(graph, entity))
            for child in graph.children(entity):
                edges.append({"from": node_id(entity), "to": node_id(child), "type": "contains"})
            if kind == "exam":
                for other in graph.linked_exams(entity):
                    if node_id(entity) < node_id(other):
                        edges.append({"from": node_id(entity), "to": node_id(other), "type": "linked"})
    unresolved = [
        {"from": f"{item.source_kind}:{item.source_id}", "to": target_id(item.target_kind, item.target_id),
         "target_kind": item.target_kind}
        for item in graph.unresolved_references
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "unresolved": sorted(unresolved, key=lambda item: (item["from"], item["to"])),
        "counts": {kind: len(getattr(graph, COLLECTIONS[kind])) for kind in KINDS},
        "tracked": {name: hex(id(obj)) if obj is not None else None for name, obj in tracked},
    }


def issues(report: Any) -> List[Dict[str, Any]]:
    return [
        {"code": issue.code, "severity": issue.severity.value,
         "context": {key: value for key, value in issue.context.items() if key in ("table", "rows")}}
        for issue in report.issues
    ]


def trace_story() -> List[Dict[str, Any]]:
    """Run the four calls and return one snapshot per step.

    Raises
    ------
    AssertionError
        A later load replaced a tracked object or added an exam to the subset;
        the page would then misstate what the library does.
    """

    tables = story_tables()
    stages: List[Dict[str, Any]] = []

    report = load_embed(magview=tables["magview"])
    clinical = report.graph
    stages.append({"id": "clinical", "tables": ["magview"], "rows": {"magview": len(tables["magview"])},
                   "issues": issues(report), **snapshot(clinical)})

    flag_workup(clinical)
    source_exam = clinical.exam("A102")
    workup = workup_partition(clinical)
    objects = (workup.exam("A102"), workup.patient("P01"), workup.finding("A102", "1"))

    def tracked() -> Tuple[Tuple[str, Any], ...]:
        return (("exam A102", workup.exam("A102")), ("patient P01", workup.patient("P01")),
                ("finding A102 #1", workup.finding("A102", "1")))

    stages.append({"id": "subset", "tables": ["magview"], "rows": {}, "issues": [],
                   "source_exam_py": hex(id(source_exam)), **snapshot(workup, tracked())})
    exams = {exam.accession_number for exam in workup.exams}

    for table in ("images", "registry"):
        report = load_embed(**{table: tables[table]}, into=workup, parents="existing")
        loaded = stages[-1]["tables"] + [table]
        stages.append({"id": table, "tables": loaded, "rows": {table: len(tables[table])},
                       "issues": issues(report), **snapshot(workup, tracked())})
        current = (workup.exam("A102"), workup.patient("P01"), workup.finding("A102", "1"))
        assert all(now is then for now, then in zip(current, objects)), "a later load replaced a tracked object"
        assert {exam.accession_number for exam in workup.exams} == exams, "a later load added exams to the subset"
    return stages


def trace_scale(patients: int, seed: int = 7) -> Dict[str, Any]:
    """Load a larger synthetic cohort and time the same subset-then-images call."""

    rng = random.Random(seed)
    magview: List[Dict[str, Any]] = []
    images: List[Dict[str, Any]] = []
    for index in range(patients):
        patient = f"P{index:05d}"
        for exam_index in range(rng.randint(1, 4)):
            accession = f"{patient}E{exam_index}"
            for number in range(1, rng.randint(1, 3) + 1):
                magview.append({
                    "empi_anon": patient, "acc_anon": accession, "numfind": number, "side": rng.choice("LR"),
                    "asses": rng.choices("NBPASMK", weights=[50, 20, 10, 10, 6, 2, 2])[0],
                    "desc": rng.choice(["screening", "diagnostic"]),
                })
            for side, view in VIEWS:
                images.append({
                    "empi_anon": patient, "acc_anon": accession, "ImageLateralityFinal": side, "ViewPosition": view,
                    "anon_dicom_path": f"/embed/cohort1/{patient}/{accession}/S/{accession}{side}{view}.dcm",
                    "Rows": 4096, "Columns": 3328,
                })
    started = perf_counter()
    graph = load_embed(magview=magview).graph
    clinical_seconds = perf_counter() - started
    flag_workup(graph)
    subset = workup_partition(graph)
    before = {kind: len(getattr(subset, COLLECTIONS[kind])) for kind in ("patient", "exam", "finding")}
    started = perf_counter()
    report = load_embed(images=images, into=subset, parents="existing")
    image_seconds = perf_counter() - started
    after = {kind: len(getattr(subset, COLLECTIONS[kind])) for kind in ("patient", "exam", "finding", "image")}
    return {
        "patients": patients, "magview_rows": len(magview), "image_rows": len(images),
        "subset_before": before, "subset_after": after, "attached": after["image"],
        "skipped": sum(issue.context["rows"] for issue in report.issues if issue.code == "rows_outside_graph"),
        "seconds": {"clinical": round(clinical_seconds, 2), "images": round(image_seconds, 2)},
    }


def git_commit() -> Optional[str]:
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def build_trace(scale_patients: int = 5000) -> Dict[str, Any]:
    """Return the full page data: story stages, optional scale run, provenance."""

    return {
        "stages": trace_story(),
        "scale": trace_scale(scale_patients) if scale_patients > 0 else None,
        "provenance": {
            "library": embed_data_graph.__version__,
            "commit": git_commit(),
            "python": platform.python_version(),
        },
    }


# -- rendering -----------------------------------------------------------------


def bea_assets(bea_dir: Optional[Path] = None) -> Dict[str, str]:
    """Read the Bea web assets from ``bea_dir`` or the vendored copy."""

    source = bea_dir or VENDORED_BEA
    missing = [name for name in BEA_FILES if not (source / name).is_file()]
    if missing:
        raise FileNotFoundError(f"{source} lacks Bea assets: {', '.join(missing)}")
    return {name: (source / name).read_text(encoding="utf-8") for name in BEA_FILES}


def vendor_bea(bea_dir: Path) -> None:
    """Copy the Bea web assets from ``bea_dir`` over the vendored ones."""

    bea_assets(bea_dir)
    for name in BEA_FILES:
        shutil.copyfile(bea_dir / name, VENDORED_BEA / name)


def render(trace: Mapping[str, Any], assets: Mapping[str, str]) -> str:
    """Fill the page template with the trace and inlined Bea assets."""

    # A literal "</" inside the JSON would end the script element early.
    data = json.dumps(trace, separators=(",", ":"), default=str).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8")
    for marker, value in (
        ("/*__BEA_TOKENS__*/", assets["tokens.css"]),
        ("/*__BEA_CSS__*/", assets["bea.css"]),
        ("/*__BEA_JS__*/", assets["bea.js"]),
        ("__TRACE_JSON__", data),
    ):
        if page.count(marker) != 1:
            raise ValueError(f"Template must contain {marker} exactly once")
        page = page.replace(marker, value)
    return page


def main(argv: Optional[Sequence[str]] = None) -> Path:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"HTML file to write (default: {DEFAULT_OUT.relative_to(REPO)})")
    parser.add_argument("--scale-patients", type=int, default=5000,
                        help="synthetic patients for the at-scale section; 0 omits it (default: 5000)")
    parser.add_argument("--bea-dir", type=Path, help="read tokens.css, bea.css and bea.js from this directory")
    parser.add_argument("--vendor", action="store_true", help="with --bea-dir, also replace the vendored copies")
    parser.add_argument("--trace-json", type=Path, help="also write the recorded trace to this JSON file")
    args = parser.parse_args(argv)
    if args.vendor and args.bea_dir is None:
        parser.error("--vendor requires --bea-dir")
    if args.vendor:
        vendor_bea(args.bea_dir)
    trace = build_trace(args.scale_patients)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(trace, bea_assets(args.bea_dir)), encoding="utf-8")
    if args.trace_json is not None:
        args.trace_json.write_text(json.dumps(trace, indent=1, default=str), encoding="utf-8")
    print(f"wrote {args.out}")
    return args.out


if __name__ == "__main__":
    main()
