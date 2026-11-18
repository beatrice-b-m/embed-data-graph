# Where the label pipeline spends its loading time

**On 96,000 synthetic MagView rows and 1,600 registry rows, the actual ELP loader spent 12.60 s building the graph and 13.34 s converting it to 17 DataFrames.** File reads took 0.41 s. Two experimental changes inside the graph library brought the full load from **26.35 s to 16.01 s**, a **39% reduction**. Median peak memory increased from **1,666 to 1,857 MiB**. The existing ELP code produced identical output on both runs.

The clinical run record establishes the priority. Loading took **1,342.69 s** (22 min 23 s), or 85.4% of the reported loading and step time. Label steps took 230.44 s. `elp.run()` records one interval around `load_inputs`, which reads files, calls `load_embed` once, calls `graph.table(name)` for each view, then summarizes the results. Its 29,288.7 MiB peak (28.60 GiB) is the process high-water mark through the label steps. Attribution within that interval requires separate stage measurements. The timings below use synthetic inputs. [ELP run timing](https://github.com/beatrice-b-m/embed-label-pipeline/blob/eb4f8a1a00145bcc305d8529999987640b0816e4/src/embed_label_pipeline/run.py#L152-L181) · [ELP input loader](https://github.com/beatrice-b-m/embed-label-pipeline/blob/eb4f8a1a00145bcc305d8529999987640b0816e4/src/embed_label_pipeline/inputs.py#L100-L188)

## Cold graph and view construction

The following comparisons use the real `elp.load_inputs` entry point with prewritten local CSVs. Each result is the median of three fresh processes per variant. The 96,000-row baseline and patched trials alternated their order across repetitions. Times are wall seconds with function profiling off. OS file caches were warm. The 6,000-row case also has 100 registry rows. Totals include reads, summaries, and ELP bookkeeping.

| MagView rows | Library variant | Build graph (s) | Create 17 views (s) | Full ELP load (s) |
|---:|---|---:|---:|---:|
| 6,000 | Downstream pin | 0.775 | 0.849 | 1.658 |
| 6,000 | Graph construction patch | 0.608 | 0.848 | 1.490 |
| 6,000 | View projection patch | 0.766 | 0.346 | 1.143 |
| 6,000 | Both patches | 0.601 | 0.348 | 0.980 |
| 96,000 | Downstream pin | 12.598 | 13.342 | 26.352 |
| 96,000 | Both patches | 10.073 | 5.490 | 16.011 |

On the 96,000-row baseline, median process peaks were 418 MiB after reading, 1,480 MiB after graph construction, and 1,666 MiB after the views. With both patches those peaks were 418, 1,443 and 1,857 MiB. Final peaks ranged from 1,612–1,831 MiB on baseline and 1,781–1,873 MiB with the patches. Each high-water mark includes allocations from earlier stages. Budget for both wall time and peak RSS on the clinical host, especially given its 28.60 GiB run-record peak.

### Repeated projection and serialization

At 96,000 rows, `issues` took **5.05 s**, `unresolved` **2.61 s**, and `unresolved_values` **2.64 s**. Together these consumed **77% of all projection time**. There were 9,600 unresolved records, 91,200 unresolved-value rows and 19,200 projected issue rows.

Each of these three calls walks unresolved records. It flattens their fields, serializes the address and contents to make occurrence keys, constructs both unresolved output tables, and serializes records again to match diagnostic addresses. Unresolved clinical records carry their full source-row payload. The `issues` call also normalizes and temporarily retains rows for every entity grain to discover date diagnostics. Earlier grain requests have already performed much of that normalization. [Projection implementation at the pin](https://github.com/beatrice-b-m/embed-data-graph/blob/125b5c437851c5ddabb4f8879986abd862c83dd5/src/embed_data_graph/core/tabular.py#L324-L463)

In a separate 6,000-row function profile, 17 calls to `project` used 2.94 s of the 2.99 s profiled projection. Canonical key encoding consumed 1.49 s cumulatively. There were 900 calls to `UnresolvedClinicalRecord.to_dict` for 300 unresolved pathology records. The final pandas conversion used 0.052 s. These cumulative measurements overlap and profiler instrumentation increases wall time.

The projection patch builds only the requested rows, inspects date fields for diagnostics, and serializes an unresolved source payload only when an issue at that address needs matching. That reduced projection time **59%** in both ELP comparisons. It keeps the public keys, ordering, dtypes, issue associations and existing ELP calls. [Projection experiment](experiments/requested-views.patch)

### Building the graph from wide DataFrames

Graph construction spreads its time across several passes over the same rows. The loader converts DataFrames to record dictionaries, makes read-only row snapshots, copies mappings again, projects MagView into patient, exam and finding groups, reconciles their fields, and applies procedures, pathology, registry links and patient claims. Patient-context sorting even formats the full source rows through `repr` while ordering contexts. [Table normalization](https://github.com/beatrice-b-m/embed-data-graph/blob/125b5c437851c5ddabb4f8879986abd862c83dd5/src/embed_data_graph/core/tables.py#L145-L319) · [Loader orchestration](https://github.com/beatrice-b-m/embed-data-graph/blob/125b5c437851c5ddabb4f8879986abd862c83dd5/src/embed_data_graph/sources/embed/loader.py#L319-L421)

| Operation in the 6,000-row graph profile | Cumulative seconds |
|---|---:|
| Entire profiled `load_embed` | 2.573 |
| Finding loading | 0.632 |
| Clinical adapter including associations | 0.599 |
| Exam loading | 0.393 |
| Input materialization | 0.349 |
| Patient loading | 0.325 |

Field reconciliation (`_combine_fields`) was called 11,700 times across the grain loaders and used 0.596 s. Identifiers were normalized 171,501 times. DataFrame `to_dict` used 0.309 s inside materialization. Fresh entity registration accounted for 0.082 s. This points first to row and field processing.

The graph patch reuses the normalized row mapping across adapters, skips physical-key bookkeeping for the default unkeyed input, sorts patient context keys directly, combines column-presence checking with extraction, and gives ordinary strings and nulls a shorter normalization path. An intermediate experiment with row reuse and patient-context changes alone brought graph time from 0.775 to 0.696 s. The full graph patch reached **0.608 s**, a **21%** reduction. These changes retain the distinction between absent columns and supplied nulls, source-key failure handling, and support for pandas and NumPy scalars. [Graph construction experiment](experiments/graph-build.patch)

## Which properties of the data matter?

The default synthetic shape has three exams per patient, two MagView rows per exam, sparse procedure and registry evidence, and one unkeyed assessment plus one incomplete pathology record every ten exams. The wide CSV includes the default mapped clinical columns, with unpopulated columns supplied as null, and pads to 152 physical columns with unused fields. The narrow CSV includes only the 23 generated fields. These are workload choices. The clinical distributions, storage speed, input format, and memory pressure are unknown.

| Baseline workload | MagView rows | Unresolved records | Read (s) | Graph (s) | 17 views (s) |
|---|---:|---:|---:|---:|---:|
| Wide, 250 patients | 1,500 | 150 | 0.007 | 0.187 | 0.233 |
| Wide, 1,000 patients | 6,000 | 600 | 0.023 | 0.771 | 0.848 |
| Wide, 4,000 patients | 24,000 | 2,400 | 0.090 | 3.132 | 3.377 |
| Narrow, 1,000 patients | 6,000 | 600 | 0.005 | 0.472 | 0.622 |
| Wide, complete identities | 6,000 | 0 | 0.023 | 0.752 | 0.353 |
| Wide, incomplete evidence every second exam | 6,000 | 3,000 | 0.024 | 0.809 | 2.850 |

These are three-process medians from the graph benchmark using ELP's read settings and 17 separate view calls. At fixed shape, graph and view time grew roughly in proportion to cohort size. At fixed row count, changing completeness moved projection time by a factor of eight. The narrow case changes both physical width and which null-valued columns are present. Dropping columns can alter refresh semantics and the payload retained on unresolved records.

**Sentinel accessions can multiply memory use.** Starting with the wide, fully keyed 6,000-row fixture, we changed `acc_anon` to `"999"` on both rows of every twentieth exam (300 input rows). On the pinned library this produced 600 unresolved records and 26,100 `unresolved_values` rows. That one DataFrame occupied **128.2 MiB** by pandas `memory_usage(deep=True)`. Its Arrow-backed `record_key` column alone accounted for **126.3 MiB** and averaged **5,068 characters per leaf row**. The key encodes the address and semantic contents of the record, and each leaf repeats it. The fully keyed control had an empty `unresolved_values` frame. The process peak in these single diagnostic runs was 543 MiB versus 211 MiB. Compare the clinical `unresolved_values` row count and memory footprint before considering a compact representation. Changing the public key encoding requires a schema compatibility decision. [Unresolved record contract](../docs/tabular.md)

**Long patient histories expose a different graph bottleneck.** Holding 3,000 exams and 6,000 fully keyed MagView rows fixed, graph time was **0.74, 0.87, 1.50 and 2.34 s** at 3, 30, 150 and 300 exams per patient respectively. The patient and registry counts decrease as visits concentrate. At 300 visits, 21,000 insertions or replacements scanned existing observations and called the observation context accessor **44.1 million times**. Those insertions used 3.32 s of the 5.83 s profiled load. For clinical data with a long tail of visits per patient, the next graph optimization to test is a context-to-position index during grouped patient loading. It must preserve insertion order and replace existing observations at the original position. [Patient observation implementation](https://github.com/beatrice-b-m/embed-data-graph/blob/125b5c437851c5ddabb4f8879986abd862c83dd5/src/embed_data_graph/clinical/patients.py#L308-L330)

## What to change first

1. **Reuse loaded inputs for interactive label work.** Keep the `Inputs` object in the notebook kernel across calls to `run_steps`. A label-only definition change can use new definitions with the same inputs. Reload when the source data, input bindings, requested views, sentinel policy or graph implementation changes. On the shipped ELP walkthrough, two runs over one snapshot produced 34 equal step tables and preserved all 17 input frames. This avoids the entire recorded loading interval on each repeat. [ELP notebook interface](https://github.com/beatrice-b-m/embed-label-pipeline/blob/eb4f8a1a00145bcc305d8529999987640b0816e4/src/embed_label_pipeline/__init__.py#L1-L16)

   ```python
   import embed_label_pipeline as elp

   defs = elp.load_definitions()
   inputs = elp.load_inputs("paths.yaml", defs)
   results = elp.run_steps(inputs, defs)

   # After editing label rules in study.yaml
   revised = elp.load_definitions(overrides="study.yaml")
   results = elp.run_steps(inputs, revised)
   ```

2. **For fresh loads, qualify the projection and graph patches against the clinical snapshot.** Projection provides the larger single gain on this fixture, especially with incomplete records. The two changes are independent and work through ELP's existing calls. Measure each separately on the real shape and compare all configured frames, dtypes, row order and diagnostics before changing the downstream graph pin.
3. **Consider a supported selected-table call for ELP.** As a separate experiment on the original graph revision, projecting the same 17 names together reduced view time from 0.840 to 0.374 s (6,000 rows, fresh-process medians), and from 13.22 to 6.03 s (96,000 rows, one run each). All 17 frames matched. The benchmark uses a private helper to test this design. The existing public `graph.tables()` also constructs the large supplementary `values` table. A selected-table API could avoid that cost. Its gains overlap the projection patch. With both patches already applied, batching took 0.281 s for the 6,000-row views.

For repeated runs in **new processes**, a downstream cache of the prepared inputs is a further option. Key it by input file contents, resolved input configuration, and graph and projection revisions. Verify a round trip against the complete `Inputs` contract, including dtypes, report diagnostics and any graph access needed by the consumer. This option has no measured speedup here.

## Reproduce and diagnose a clinical run

Environment for the wall-time measurements was macOS 26.6, Apple M5 with 24 GB RAM, Python 3.12.15, pandas 3.1.1 and PyArrow 26.0.1. The graph revision was `125b5c437851c5ddabb4f8879986abd862c83dd5`, the exact ELP pin at `eb4f8a1a00145bcc305d8529999987640b0816e4`. The performance fixtures use fabricated data. ELP's own 48-row synthetic walkthrough was also run through the actual loader. It produces zero unresolved records. The older repository benchmark mixes images, ROIs and clinical rows, starts with narrow dictionaries, and measures its full-load column under allocation tracing. [Downstream pin](https://github.com/beatrice-b-m/embed-label-pipeline/blob/eb4f8a1a00145bcc305d8529999987640b0816e4/pyproject.toml) · [Configured views](https://github.com/beatrice-b-m/embed-label-pipeline/blob/eb4f8a1a00145bcc305d8529999987640b0816e4/src/embed_label_pipeline/definitions/inputs.yaml) · [Earlier benchmarks](README.md)

**For the clinical machine**, run the following in the existing ELP environment. Pass the same paths file and any original definition overrides, in order. The script runs only the input phase. JSON includes file times by role, table shapes and counts, graph time, per-view times, and process peak RSS after each stage. After timing, it also reports unresolved counts by kind and reason, and the deep pandas sizes of the unresolved-value table and its key column. Output contains aggregate measurements. Use a fresh process for each measurement. Start without function profiling. If graph construction dominates, repeat with `--profile graph`. If the views dominate, use `--profile views`. Label steps and output writing are excluded. [Actual ELP profiler](profile_elp_inputs.py)

```bash
python /path/to/embed-data-graph/benchmarks/profile_elp_inputs.py paths.yaml > load-timing.json
```

For the synthetic comparison, run from the graph repository in an editable graph installation with pandas available. Fixture generation and imports precede the stage timers. By default, the RSS includes fixture generation. Use prewritten CSVs with `--magview` and `--registry` to isolate process peaks, as in the 96,000-row comparison. `--compare-views` retains both view results from the same graph revision for equality checking. Use separate processes with and without `--batch-only` for timing or memory comparisons. [Synthetic benchmark](label_pipeline_loading.py)

```bash
python -m benchmarks.label_pipeline_loading --patients 1000 --compare-views
python -m benchmarks.label_pipeline_loading --patients 1000 --profile graph
python -m benchmarks.label_pipeline_loading --patients 1000 --profile views
python -m benchmarks.label_pipeline_loading --patients 1000 --incomplete-every 0
python -m benchmarks.label_pipeline_loading --patients 10 --visits 300 --incomplete-every 0
```

To reproduce the headline comparison, run the commands below from the graph checkout in a Python environment with ELP and its pinned graph distribution installed. The fixture writer and profiler run in separate processes. The paths file has one entry per input role, the format accepted by `elp.run()`. Repeat the last command in fresh processes before and after applying the patches.

```bash
fixture_dir=$(mktemp -d)
PYTHONPATH=src python - "$fixture_dir" <<'PY'
import sys
from pathlib import Path
from benchmarks.label_pipeline_loading import write_fixture

folder = Path(sys.argv[1])
write_fixture(folder, patients=16000, visits=3, incomplete_every=10, wide=True)
(folder / "paths.yaml").write_text("magview: magview.csv\nregistry: registry.csv\n")
PY
PYTHONPATH=src python benchmarks/profile_elp_inputs.py "$fixture_dir/paths.yaml"
```

To reproduce the experimental variants, use a disposable checkout of this profiling branch. Run the baseline, apply one or both patches there, and rerun the same command with that checkout's `src` on the Python path. The patches target the downstream graph pin. Each candidate matched all 17 ELP DataFrames and ordered load-report diagnostics on the downstream walkthrough and on a wide 25-patient subset containing unresolved records.

We captured the baseline and patched ELP outputs in separate processes and compared one pair of frames at a time with `assert_frame_equal(check_exact=True)`. With both patches applied, the full 96,000-row comparison matched **all 396,800 projected rows**, including column order, row order, exact values and pandas dtypes. All 9,600 ordered load-report diagnostics matched. The combined patches passed the graph library's 585 tests, including wheel and source distribution checks, plus Ruff and mypy.

```bash
git apply --check benchmarks/experiments/graph-build.patch benchmarks/experiments/requested-views.patch
git apply benchmarks/experiments/graph-build.patch benchmarks/experiments/requested-views.patch
PYTHONPATH=src python -m benchmarks.label_pipeline_loading --patients 1000 --compare-views
```
