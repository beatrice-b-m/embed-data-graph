# Downstream integration guide

Use this guide to integrate EMBED Data Graph into a research application.
The distribution is `embed-data-graph`, the Python namespace is `embed_data_graph`,
and the Python project lives at the repository root.

## Install and pin the dependency

For local development, install an editable checkout:

```bash
python -m pip install -e /path/to/embed-data-graph
```

For a reproducible source dependency, use the release tag or a qualified commit SHA:

```bash
python -m pip install \
  "git+https://github.com/beatrice-b-m/embed-data-graph.git@v0.3.0"
```

If the consumer uses `uv`, configure the repository URL and exact revision as its
source dependency, then lock it. Record the resolved commit and package version in
the consumer's environment specification and qualification notes.

## Choose public imports

The root facade is the preferred import boundary for common types:
`DatasetGraph`, `Patient`, `Exam`, `Finding`, `Procedure`, `ProcedureIdentity`,
`Pathology`, `CancerRegistryEntry`, `MammogramImage`, `RegionOfInterest`, `Box`,
`Laterality`, `ImageModality`, `ViewPosition`, `load_embed`, `validate`,
`ValidationResult`, `Issue`, `SourceRef`, and `LoadReport`.

Use specialist modules for mappings and types outside the root exports:

```python
from embed_data_graph import DatasetGraph, load_embed, validate
from embed_data_graph.clinical.findings import Finding
from embed_data_graph.sources.embed.columns import DEFAULT_COLUMNS

assert DEFAULT_COLUMNS["patients"]["patient_id"] == "empi_anon"
```

Use the same imports in application code, tests, examples, and notebooks. The
package has no mandatory runtime dependencies; install pandas in the consumer's
environment if its own workflow uses DataFrames.

## Configure table and DataFrame mappings

`load_embed` accepts mappings, iterables of mappings, one-shot generators, and
pandas-like DataFrames. The semantic identity is independent of the physical
DataFrame index. A reset index, duplicated index, or a slice with a different
index must produce the same patient, exam, finding, image, or ROI identity when
the mapped source fields are the same.

The `columns` argument maps semantic names to physical names:

```text
columns["patients"]["patient_id"] = "research_patient_id"
columns["findings"]["finding_number"] = "finding_no"
```

Use `None` to unbind an optional semantic field from an adapter. Required
identity fields cannot be unbound. The mapping is partial: unspecified fields
keep their defaults. The complete current default map is available from
`embed_data_graph.sources.embed.columns.DEFAULT_COLUMNS` and is summarized in
the [user guide](user-guide.md).

This complete example uses a renamed DataFrame schema and demonstrates the
expected result:

```python
import pandas as pd

from embed_data_graph import load_embed


patients = pd.DataFrame(
    {"research_patient_id": [101], "sex_at_birth": ["F"]},
    index=["row-from-source"],
)
report = load_embed(
    patients=patients,
    columns={
        "patients": {
            "patient_id": "research_patient_id",
            "sex": "sex_at_birth",
        }
    },
)

assert report.graph.patient("101").sex == "F"
assert report.graph.patient("row-from-source") is None
```

`source_keys` is available when a source row key is useful for diagnostics:
`source_keys={"patients": "source_row_id"}` or a callback. A bad or missing
diagnostic key produces an issue, while a valid semantic ID still admits the
row. It is not an alternate identity field.

## Preserve the policy boundary

The package owns source translation, mutable domain objects, explicit
containment, supplied associations, optional validation, and independent graph
movement. Downstream code owns study policy. Keep these decisions in the
consumer repository:

- cohort definitions, inclusion/exclusion rules, and outcome windows;
- pixel reading, preprocessing, alignment, and image-derived measurements;
- finding localization, finding-to-ROI matching, and cross-image
  correspondence;
- ROI transfer, patch extraction, visualization, and model-specific metadata;
- clinical/scientific interpretation and diagnosis inference.

The core does not infer a finding-to-image relationship because an exam or side
is shared. It does not turn a registry reference into a diagnosis. A registry
assignment supplied by the source remains a supplied relationship, and a
patient/exam conflict remains inspectable until a consumer explicitly chooses
ownership with `graph.assign_patient(...)`. `validate(...)` is an explicit
read-only quality report; loading representable but implausible facts is not an
automatic rejection policy.

Keep each workflow in the repository that owns its inputs and analysis policy,
and store the package revision used by that workflow.

## Avoid refresh and merge traps

Treat each call to `load_embed` as one complete grouped snapshot for every
semantic grain that it addresses.

`mode="refresh"` is the default. For bound adapter-managed scalar fields it
replaces the values whose columns the incoming rows supply, including explicit
nulls; a column absent from the rows leaves its field unchanged. It
updates the existing object in place, keeps consumer attributes/metadata and
subclasses, and leaves unbound fields and unspecified child grains alone.

`mode="merge"` applies supplied non-null scalar values. Complementary rows
combine; a populated value that conflicts with another supplied value or with
the value already in the graph becomes unknown and adds an issue. It does not infer whether two unkeyed history rows or two revised ROI
collections represent the same event.

These rules make the following results intentional:

```python
from embed_data_graph import load_embed


graph = load_embed(exams=[{"acc_anon": "A-001", "desc": "screening"}]).graph
exam = graph.exam("A-001")
exam.consumer_note = "preserve"

load_embed(exams=[{"acc_anon": "A-001", "desc": "reviewed"}], into=graph)
assert graph.exam("A-001") is exam
assert exam.description == "reviewed"
assert exam.consumer_note == "preserve"

load_embed(exams=[{"acc_anon": "A-001", "desc": None}], mode="merge", into=graph)
assert exam.description == "reviewed"

load_embed(exams=[{"acc_anon": "A-001", "desc": None}], into=graph)
assert exam.description is None

report = load_embed(
    exams=[
        {"acc_anon": "A-001", "desc": "one"},
        {"acc_anon": "A-001", "desc": "two"},
    ],
    mode="merge",
    into=graph,
)
assert exam.description is None
assert any("conflicting_exam" in issue.code for issue in report.issues)
```

Do not split one repeated MagView object across separate refresh calls when the
calls are meant to complement one another. Materialize and group streamed
chunks first. A child-only load, such as `findings=...` or `rois=...`, ensures a
missing parent shell but does not refresh parent scalar fields.

Collections have their own replacement rules:

- An explicit `rois` collection replaces the addressed image collection in
  either mode. Missing or null coordinates preserve the collection; `[]`
  clears it; malformed or conflicting replacements preserve the previous
  collection and add an issue. Save manual ROIs before a valid replacement if
  they must survive.
- A supplied linked-accession or registry-assignment collection replaces that
  collection on refresh. Absent or unbound preserves it; null clears it;
  `merge` unions supplied values.
- Identified history rows use their record ID for in-place refresh. Unkeyed
  history refresh replaces that history kind for the patient. Unkeyed history
  merge cannot establish event equality, so existing facts remain and the
  report explains that explicit IDs are required.

## Confirm expected graph results

Use a synthetic repeated-row fixture to check that source-row multiplicity
does not become object multiplicity:

```python
from embed_data_graph import load_embed


rows = [
    {
        "empi_anon": "P-001",
        "acc_anon": "A-001",
        "numfind": 1,
        "side": "L",
        "bside": "L",
        "type": "B",
        "procdate_anon": "2024-01-10",
        "pdate_anon": "2024-01-11",
        "path1": "ADH",
    },
    {
        "empi_anon": "P-001",
        "acc_anon": "A-001",
        "numfind": 1,
        "side": "L",
        "bside": "L",
        "type": "B",
        "procdate_anon": "2024-02-10",
        "pdate_anon": "2024-02-11",
        "path1": "ADH",
    },
]
graph = load_embed(magview=rows).graph

assert len(graph.patients) == 1
assert len(graph.exams) == 1
assert len(graph.findings) == 1
assert len(graph.procedures) == 2
assert len(graph.pathology) == 2
finding = graph.finding("A-001", "1")
assert finding is not None
assert len(finding.procedures) == 2
assert len(finding.pathology) == 2
```

The expected cardinalities are one patient, one exam, one finding, two
complete procedures, and two pathology bundles. Reversing `rows` should keep
the same cardinalities and the same canonical object identities. An incomplete
procedure or ambiguous pathology key should remain visible in
`graph.unresolved_records` instead of being promoted using a row ordinal.

## Integration checklist

Before accepting a consumer integration:

1. Use `embed_data_graph` for runtime and test imports.
2. Run package development commands from the repository root, as documented in
   [CONTRIBUTING.md](../CONTRIBUTING.md).
3. Compare custom `columns` maps with `DEFAULT_COLUMNS`; verify semantic and
   physical directions.
4. Test one complete refresh snapshot and one explicit merge. Include absent,
   null, unbound, and conflicting fields where the consumer depends on them.
5. Test image/ROI collection replacement separately from scalar image metadata.
6. Keep downstream matching, transfer, pixel, and cohort policy in the
   consumer code.
7. Pin the exact source revision and record expected graph cardinalities and
   package version in the consumer's qualification notes.

Run the package's [researcher journey](../examples/researcher_journeys.py) and
the full root checks before accepting the integration. Synthetic library tests verify
object behavior; they do not qualify private EMBED data, real pixels, or the
consumer's scientific conclusions.
