# EMBED Data Graph loading measurements

Measured 2026-09-23 against `b180feb` on branch `refactor/catalog-alignment`.
Python 3.13.11, macOS-26.5.1-arm64-arm-64bit-Mach-O.

```bash
uv run --frozen python -m benchmarks.graph_loading --base 100 --repeats 3
```

Each patient contributes six input rows: four repeated finding/procedure MagView
rows, one image row containing two equal ROI slots, and one registry entry.
Expected objects per patient: one patient, one exam, two findings, two procedures,
two pathology bundles, one image, two ROIs, and one registry entry (12 total).
Edges count actual parent associations once, including exam/registry edges, plus
each reciprocal linked-exam pair once. The last exam has no linked successor.

| Patients | Rows | Objects | Edges | Full load (s) | Peak bytes | Retained bytes |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 600 | 1200 | 1399 | 0.1417 | 2,911,270 | 1,799,046 |
| 200 | 1200 | 2400 | 2799 | 0.2830 | 5,671,470 | 3,368,498 |
| 400 | 2400 | 4800 | 5599 | 0.5725 | 11,298,958 | 6,506,690 |

| Patients | Fixed-patient update (µs) | One-patient subset (ms) | Batched load (s) | Late registry resolution (ms) |
|---:|---:|---:|---:|---:|
| 100 | 17.26 | 0.426 | 0.0283 | 0.502 |
| 200 | 17.29 | 0.439 | 0.0578 | 1.051 |
| 400 | 17.63 | 0.476 | 0.1175 | 2.021 |

All values are medians of three repetitions. Full loads use `tracemalloc`; input
fixture construction is excluded from both time and memory. Retained memory is
measured after loading; peak includes transient load allocations. Other operations
are timed without tracing, so their absolute timings are not directly comparable
to the traced full-load column. Fixed updates average 50 same-patient refreshes per
repetition; subset setup uses prebuilt slices. Deferred resolution excludes graph
construction and times only the later registry input.

Full-load time and memory grew linearly (doubling ratios 2.00× and 2.02×).
Fixed-patient update time stayed near 17 µs as unrelated data quadrupled, because
updates touch only the indexes of the changed entity. Compared with the 0.1.0
graph at `664b4e2`, full loads are about 20% faster and retain about 35% less
memory for the same objects and edges. Timing is diagnostic, not a CI threshold.

Batches contain 25 complete patient groups. A refresh invocation is one snapshot:
callers must assemble all rows for a repeated semantic grain before applying it.
Arbitrarily splitting one object across refresh calls changes the snapshot and is
not a streaming merge. Full and batched cardinalities are checked at every size.

These are synthetic scale results, not qualification on the full private EMBED
dataset, real pixels, or every source schema. Representative private-data testing
requires data supplied through an authorized path. Registry measurements cover
the default patient/registry-ID mapping; optional payload mappings were not measured.
