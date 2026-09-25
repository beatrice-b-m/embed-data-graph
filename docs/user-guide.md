# EMBED Data Model user guide

This guide describes the mutable object model and the source-table adapter.
The Python project is at the repository root and is installed as
`embed-data-model`; import `embed_data_model`. Start with
the repository [README](../README.md), then use the
[documentation index](README.md) for contracts and integration guidance.

The examples below are standalone unless a block says otherwise. They use
synthetic rows and public imports, so they do not require access to private
EMBED files.

## Public surface

The root facade exports the common working types:

```python
from embed_data_model import (
    BreastSide,
    Box,
    CancerRegistryEntry,
    DatasetGraph,
    Exam,
    Finding,
    ImageModality,
    Issue,
    Laterality,
    LoadReport,
    MammogramImage,
    Pathology,
    Patient,
    Procedure,
    ProcedureIdentity,
    RegionOfInterest,
    SourceRef,
    ValidationResult,
    ViewPosition,
    load_embed,
    validate,
)
```

The source adapter's complete default table map is intentionally available in
its specialist module rather than on the root facade:

```python
from embed_data_model.sources.embed.columns import DEFAULT_COLUMNS

assert DEFAULT_COLUMNS["patients"]["patient_id"] == "empi_anon"
assert DEFAULT_COLUMNS["findings"]["finding_number"] == "numfind"
```

`DEFAULT_COLUMNS` is a read-only mapping of semantic names to physical source
columns. Pass partial overrides through `load_embed(columns=...)`; the map is
validated before rows are consumed. The full reference is summarized below.

## Construct and extend objects

Objects can be built without a graph. Each stores the keys of related objects
(a finding stores its exam's accession) and a `DatasetGraph` resolves those keys,
so relationships appear as soon as both ends are registered, in any order. Adding
a child to an object that has no graph yet creates one; registering the patient
into another graph moves the whole tree.

```python
from embed_data_model import DatasetGraph, Exam, Finding, Laterality, Patient


class ResearchExam(Exam):
    pass


patient = Patient("P-001")
exam = patient.add_exam(ResearchExam("A-001", description="screening"))
exam.metadata["review"] = {"complete": False}
finding = exam.add_finding(Finding("A-001", Laterality.LEFT, "1"))

graph = DatasetGraph()
graph.register(patient)
exam.update(description="reviewed")

assert graph.patient("P-001") is patient
assert graph.exam("A-001") is exam
assert graph.finding("A-001", "1") is finding
assert exam.metadata["review"] == {"complete": False}
```

`Patient -> Exam -> Finding` is the main clinical containment path. An exam
also contains images, procedures, pathology bundles, and patient-scoped
registry entries. An image contains its ROIs. Findings and images grouped under
the same exam or breast side are separate facts; the core does not infer a
finding-to-image or finding-to-ROI association from shared scope.

Collections such as `patient.exams`, `exam.findings`, `image.rois`, and
`exam.breast_sides` are computed on access from the graph's indexes. Use
`add_*`, `attach`, `detach`, `replace_rois`, or an update of the stored keys to
change them. Changing a key (with `rekey`, `update` or plain assignment) is
propagated to every object that stored the old key, after checking the whole
change for collisions. `metadata` and consumer-added attributes remain editable.

Repeated registration of the same instance is idempotent. A distinct object at
an occupied key raises `ValueError`. Every entity belongs to zero or one graph.
Registering an object owned by another graph moves it with everything it
contains; a contained object that something staying behind also contains is
copied instead.

## Load semantic snapshots

`load_embed` accepts any combination of these optional inputs: `patients`,
`exams`, `findings`, `images`, `rois`, `hormone_history`, `procedure_history`,
`procedures`, `pathology`, `magview`, and `registry`. It accepts iterables of mappings, one-shot
generators, and DataFrame-like values. It returns a `LoadReport` with:

- `report.graph`, the target `DatasetGraph`;
- `report.issues`, issues from this invocation; and
- `report.source_scope`, the source scope used for optional diagnostics.

This complete synthetic load creates one patient, one exam, and one finding:

```python
from embed_data_model import DatasetGraph, Laterality, load_embed


graph = DatasetGraph()
report = load_embed(
    magview=[
        {
            "empi_anon": "P-001",
            "acc_anon": "A-001",
            "numfind": 1,
            "side": "L",
            "desc": "screening",
            "asses": "S",
            "recc": "B",
            "location": "W",
            "depth": "P",
        }
    ],
    into=graph,
)

exam = graph.exam("A-001")
finding = graph.finding("A-001", "1")
assert exam is not None and finding is not None
assert graph.patient("P-001") is not None
assert finding.laterality is Laterality.LEFT
assert finding.interpretation.assessment.code == "S"
assert finding.interpretation.assessment.meaning == "Suspicious"
assert not finding.normalization_warnings
assert finding.interpretation.recommendation.meaning == "Biopsy"
assert not report.issues
```

The loader groups rows by semantic identity before updating an object. A
patient is keyed by `patient_id`, an exam by accession, and a finding by
`(accession, finding_number)`. Numeric identifiers normalize to stable strings;
blank identifiers do not manufacture shared objects. Coded values such as
assessment, recommendation, procedure type, and pathology descriptors are
trimmed and uppercased, so `"b"` and `" B"` are the same code; no meaning
is assigned to unexplained tokens. A `magview` row projects
supported patient, exam, and finding grains while its procedure, pathology,
registry, and linked-accession columns are handled by their corresponding
adapters.

## Coded values and their meanings

Coded MagView fields load as `Code` values that carry both the source code and
its human-readable meaning from the EMBED data dictionary, so analyses do not
need to look codes up. This covers assessment and recommendation, exam density,
type, visit type and modality, the finding descriptors, procedure type and the
pathology descriptor slots:

```python
from embed_data_model import load_embed

row = {"empi_anon": "P-1", "acc_anon": "A-1", "numfind": 1, "side": "L", "asses": "S",
       "recc": "B,U", "massshape": "O", "tissueden": 3}
graph = load_embed(magview=[row]).graph
finding = graph.finding("A-1", "1")

assert finding.interpretation.assessment.meaning == "Suspicious"
assert finding.interpretation.recommendation.meaning == "Biopsy; An ultrasound exam"
assert finding.descriptors["mass_shape"].code == "O"
assert str(finding.descriptors["mass_shape"]) == "Oval"
assert graph.exam("A-1").density.meaning == "Heterogeneously dense"
```

A `Code` compares by its code, never by meaning, and never equals a plain
string: compare `.code` or `.meaning`. Comma-separated codes list their parts in
`tokens` and compare regardless of order. A code the dictionary does not explain
keeps its `code` with `meaning` None, and `is_known` is False. The tables live in
`embed_data_model.sources.embed.vocabulary` and are generated from the EMBED
catalog by `tools/generate_embed_vocabulary.py`.

## Patient attributes over time

Patient attributes such as sex repeat on every exam row and can change over
time or disagree. The loader records one `PatientAttributeObservation` per
exam context (accession and exam date). `patient.sex` holds a value only when
every observation agrees; otherwise choose a value as of an explicit date so
later information does not leak into an earlier analysis:

```python
from datetime import date

from embed_data_model import load_embed

rows = [
    {"empi_anon": "P-9", "acc_anon": "A-1", "numfind": 1, "studydate_anon": "2020-01-01", "GENDER_DESC": "F"},
    {"empi_anon": "P-9", "acc_anon": "A-2", "numfind": 1, "studydate_anon": "2022-01-01", "GENDER_DESC": "U"},
]
patient = load_embed(magview=rows).graph.patient("P-9")
assert patient.sex is None
assert patient.attribute_as_of("sex", date(2021, 1, 1)) == "F"
assert [item.value for item in patient.attribute_history("sex")] == ["F", "U"]
```

## Refresh and merge

One invocation is one complete grouped snapshot for each grain it addresses.
The default `mode="refresh"` replaces bound adapter-managed scalar fields whose
columns the rows supply, including explicitly null values. A column absent from
every row leaves its field unchanged, so a findings-only extract does not erase
exam or patient fields loaded earlier. It keeps
the same Python object, subclass, consumer attributes and metadata, unbound
fields, and child grains that were not supplied. A child-only load ensures
missing parent shells but does not refresh the parent's fields.

`mode="merge"` applies supplied non-null scalar values. Complementary rows
combine. When supplied values conflict with each other, or with a populated
value already in the graph, the field becomes unknown and the load report
contains an issue. Merge does not
guess equality for unkeyed history facts or for revised ROI collections.

```python
from embed_data_model import load_embed


graph = load_embed(exams=[{"acc_anon": "A-001", "desc": "screening"}]).graph
exam = graph.exam("A-001")
exam.research_note = "keep this"

load_embed(exams=[{"acc_anon": "A-001", "desc": "reviewed"}], into=graph)
assert graph.exam("A-001") is exam
assert exam.description == "reviewed"
assert exam.research_note == "keep this"

load_embed(exams=[{"acc_anon": "A-001", "desc": None}], mode="merge", into=graph)
assert exam.description == "reviewed"

load_embed(exams=[{"acc_anon": "A-001", "desc": None}], into=graph)
assert exam.description is None
```

Assemble complete semantic groups before calling refresh on streamed chunks.
Two refresh calls for the same exam are two snapshots: the second replaces the
fields whose columns it supplies and leaves the others. A single generator is
consumed once. `source_scope` and `source_keys` add diagnostic source
references; they do not decide admission, identity, or replay. `report.issues`
holds the diagnostics of one invocation.

## DataFrames and column maps

The adapter accepts a pandas DataFrame or another object that supports
`to_dict(orient="records")`, `index`, and `columns`. DataFrame index values,
including a reset or duplicated index, are never used as semantic identity.
`source_keys` can name a physical diagnostic column or provide a callback. A
missing or duplicate diagnostic key produces an issue but does not prevent a
row with valid clinical identifiers from loading.

The semantic-to-physical direction is always
`columns[table][semantic] = "physical_column"`. Optional fields can be
explicitly unbound with `None`. Required identity fields cannot be unbound.

```python
import pandas as pd

from embed_data_model import load_embed


patients = pd.DataFrame(
    {"research_patient_id": [101], "sex_at_birth": ["F"]},
    index=["source-row-7"],
)
report = load_embed(
    patients=patients,
    columns={
        "patients": {
            "patient_id": "research_patient_id",
            "sex": "sex_at_birth",
        }
    },
    source_keys={"patients": "source-row-id"},
)

patient = report.graph.patient("101")
assert patient is not None and patient.sex == "F"
assert report.graph.patient("source-row-7") is None
```

The requested source key above is absent, so it may produce a diagnostic
warning. The row still loads because `research_patient_id` is its semantic
identity. A DataFrame index is not a substitute for a missing `patient_id`.

The supported default map is:

| Input | Identity and default bindings |
| --- | --- |
| `patients` | `patient_id <- empi_anon`; exam context `acc_anon`/`studydate_anon`; `sex <- GENDER_DESC`; `race <- race`; `ethnicity <- ethnicity`; `birth_year` unbound |
| `exams` | `accession <- acc_anon`; `patient_id <- empi_anon`; `exam_date <- studydate_anon`; `exam_description <- desc`; `density <- tissueden`; `exam_type <- mg_exam_type`; `visit_type <- vtype`; `modality <- modality_desc`; `patient_age <- age_at_study_anon` |
| `findings` | `(accession, finding_number) <- (acc_anon, numfind)`; `patient_id <- empi_anon`; `laterality <- side` (a supplied null side is bilateral, like `B`); `assessment <- asses`; `recommendation <- recc`; `location <- location`; `depth <- depth`; `distance <- distance` (negative values are exceptional codes, kept raw only); descriptors `mass`, `asymmetry`, `arch_distortion`, `calc`, `massshape`, `massmargin`, `massdens`, `calcfind`, `calcdistri`, `calcnumber`, `otherfind`, `implanfind` into `finding.descriptors` as source codes |
| `images` | source path `anon_dicom_path`; patient/accession `empi_anon`/`acc_anon`; laterality/view `ImageLateralityFinal`/`ViewPosition`; modality `Modality`; derived type `FinalImageType`; dimensions `Rows`/`Columns`; frames `ImagesInAcquisition` (DBT images only); study/series UIDs from the path |
| `rois` | source path `anon_dicom_path`; coordinates `ROI_coords`; frame facts `ROI_frames`; depth flag `ROI_depth_derived` |
| `procedures` | identity `(empi_anon, procdate_anon, type, bside)`; optional accession/finding `(acc_anon, numfind)` |
| `pathology` | optional record ID, otherwise the procedure `(empi_anon, procdate_anon, type, bside)`; attachment `(acc_anon, numfind)`; procedure date `procdate_anon`; report date `pdate_anon`; severity `path_severity`; descriptors `path1` through `path10`; `diagnosis`, `result_category` and `malignant` unbound |
| `hormone_history` | patient `empi_anon`; category/code `type`/`code`; accession `acc_anon`; timing `first_age`, `mfirst`, `yfirst`, `last_age`, `mlast`, `ylast` |
| `procedure_history` | patient `empi_anon`; category/procedure `type`/`pcode`; accession `acc_anon`; laterality `side`; result `result` |
| `registry` | required patient/entry identity `empi_anon`/`cancer_registry_id`; payload is unbound by default |
| `magview` | patient/accession/finding `empi_anon`/`acc_anon`/`numfind`; registry assignment `cancer_outcome_registry_id`; linked accession `linkedaccession_anon` |

`DEFAULT_COLUMNS` is the authoritative mapping object; the table above is a
quick reference. The registry identity binding is deliberately narrower than
the rest of its possible payload. Map additional registry payload fields only
when their source meanings are established.

## Clinical relationships

An accession identifies one exam. Source patient claims are retained in
`exam.asserted_patient_ids`. If claims disagree, accession-addressed findings,
procedures, pathology, and registry assignments can still attach while
`exam.patient_id` remains unset. Choose ownership explicitly with
`graph.assign_patient(exam, "P-001")`; this preserves the source claims and does
not rewrite source patient IDs on associated facts.

Linked accessions and registry assignments are supplied relationships. They
resolve in either arrival order and can remain pending when an endpoint has not
been loaded:

```python
from embed_data_model import load_embed


graph = load_embed(
    magview=[
        {
            "empi_anon": "P-001",
            "acc_anon": "A-001",
            "cancer_outcome_registry_id": 7,
            "linkedaccession_anon": "B-001",
        }
    ],
    registry=[{"empi_anon": "P-001", "cancer_registry_id": 7}],
).graph

exam = graph.exam("A-001")
entry = graph.registry_entry("P-001", "7")
assert exam is not None and entry is not None
assert exam.registry_entries == (entry,)
assert graph.unresolved_references

load_embed(exams=[{"acc_anon": "B-001"}], into=graph)
assert graph.exam("B-001") in exam.linked_exams
```

`graph.set_linked_accessions(exam, values)` and
`graph.set_registry_assignments(exam, keys)` replace the addressed collection;
pass `merge=True` to union it. In source-table refresh, an absent or unbound
association preserves the existing set, a null clears it, and a supplied set
replaces it. A registry entry is patient-scoped and can be assigned to several
exams. A registry ID by itself does not create a diagnosis.

Verified `procedures` use the complete identity `(patient_id, performed_date,
procedure_type, laterality)`. Incomplete records remain accessible through
`graph.unresolved_records` rather than becoming one procedure per physical row.
Pathology prefers a supplied patient-scoped record ID. Without one, the
documented attachment plus report-documentation-date fallback is used; an
ambiguous or insufficient key remains unresolved. Descriptor slots retain
order and duplicate values. A report date is not substituted for the procedure
date or a diagnosis event date.

`hormone_history` and `procedure_history` are patient-owned reported facts.
They are distinct from performed procedures. Their category, code and result
are `Code` values, and a code is decoded within its category, so `O` under
hormone `H` reads "Other hormone" but under contraceptive `O` reads "Other
contraceptive". Identified history rows refresh
their existing object in place. Without an event ID, refresh replaces that
history kind as a patient snapshot; merge requires explicit record IDs and
preserves existing unkeyed facts while reporting the limitation.

## Images and ROI collections

`MammogramImage.image_id` is the mutable model identity. The original
`source_sop_instance_uid` and `source_paths` are separate source facts. A path
matching the EMBED convention
`cohortN/patient/study/series/SOP.dcm` can supply source identity and study or
series context without opening pixels. An explicit SOP UID wins if it conflicts
with a path-derived UID, and the report carries an issue. Relocating a file
adds a path alias; rekeying the model image does not break source lookup.

Image metadata automatically projects its `ROI_coords` collection. A row in
the explicit `rois` input overrides the automatic collection for the image it
addresses. Each collection is complete for that image: missing or null
coordinates preserve the current collection, `[]` clears it, and malformed or
conflicting collections preserve the previous collection with an issue. A
valid replacement creates image-local ROI objects, so manual annotations and
old ROI references should be saved before replacement. This behavior applies
in both refresh and merge modes.

```python
from embed_data_model import load_embed


path = "/data/cohort1/P-001/study-1/series-1/SOP-001.dcm"
report = load_embed(
    images=[
        {
            "anon_dicom_path": path,
            "ROI_coords": "[(10, 20, 30, 50)]",
            "Rows": 100,
            "Columns": 120,
        }
    ]
)

graph = report.graph
image = graph.source_image("SOP-001")
assert image is not None and len(image.rois) == 1
roi = image.rois[0]
assert roi.identity == (image.image_id, "0")
assert roi.coordinates == (10.0, 20.0, 31.0, 51.0)

image.rekey(image_id="processed-SOP-001")
roi.update(confidence=0.75)
assert graph.roi("processed-SOP-001", "0") is roi
assert graph.roi_at_source(path, 0) is roi
```

ROI coordinates are stored as half-open `(y_min, x_min, y_stop, x_stop)`
geometry. EMBED inclusive maxima are converted once; `source_coordinates`
retains the original values. The collection position is zero-based and is part
of the source lookup address. Equal boxes in different positions are distinct
ROIs. `ROI_frames` remains a tuple of supplied frame facts, and
`ROI_depth_derived` records whether depth was source-supplied or derived; the
loader does not invent frame indices or clinical correspondence.

Derivatives require an explicit model `image_id` and `derived_from`. Their
metadata and ROIs do not replace the original source image or its source-path
lookups. Images with an accession can establish an exam shell and source patient
claim; an image row without clinical context remains image-local.

## Selection, validation, partitioning, and movement

`graph.select(level=..., predicate=...)` returns a live, non-owning selection.
Editing a selected object edits the source graph. `graph.partition(level=...,
key=...)` returns independent graphs of deep copies. A scalar key, including a
tuple, selects one output; a list or set key places the object in several
outputs. Each output holds the selected objects, everything they contain, and
their ancestors, for which `output.is_context(obj)` is True. Supported levels include patient, exam, finding, procedure,
pathology, image, ROI, and registry.

Validation is separate from loading and selection:

```python
from embed_data_model import load_embed


graph = load_embed(
    images=[
        {
            "anon_dicom_path": "/data/cohort1/P/study/series/SOP.dcm",
            "Rows": 100,
            "Columns": 100,
            "ROI_coords": "[(1, 2, 10, 20)]",
        }
    ]
).graph

selected = graph.select(level="image", predicate=lambda image: image.height == 100)
assert len(selected) == 1
valid, invalid = graph.partition_by_validation(level="image")
assert valid.image("SOP") is not None
assert invalid.images == ()
```

`validate` is read-only. It reports represented quality facts such as
contradictory patient claims, confidence and dimension ranges, ROI ordering and
bounds, frame consistency, date plausibility, and pathology severity. Errors
make `ValidationResult.valid` false; warnings remain valid unless
`warnings_invalid=True`. Missing optional tables are not errors. Custom
validators can inspect consumer fields.

### Load later tables into a subset

Tables can arrive after a subset has been chosen. By default a row creates the
patient and exam it addresses, so a whole image table loaded into a partition
would add every exam in that table. Pass `parents="existing"` to attach rows to
the subset only:

```python
from embed_data_model import load_embed


clinical = load_embed(
    magview=[
        {"empi_anon": "P1", "acc_anon": "A1", "numfind": 1, "side": "L", "desc": "screening"},
        {"empi_anon": "P2", "acc_anon": "A2", "numfind": 1, "side": "R", "desc": "diagnostic"},
    ]
).graph
screening = clinical.partition(level="exam", key=lambda exam: exam.description)["screening"]
exam = screening.exam("A1")

report = load_embed(
    images=[
        {"empi_anon": "P1", "acc_anon": "A1", "anon_dicom_path": "cohort1/P1/S/SE/I1.dcm"},
        {"empi_anon": "P2", "acc_anon": "A2", "anon_dicom_path": "cohort1/P2/S/SE/I2.dcm"},
    ],
    into=screening,
    parents="existing",
)

assert [item.accession_number for item in screening.exams] == ["A1"]
assert screening.exam("A1") is exam
assert [image.image_id for image in exam.images] == ["I1"]
(skipped,) = report.issues
assert (skipped.code, skipped.context["table"], skipped.context["rows"]) == ("rows_outside_graph", "images", 1)
```

Membership is read once, before the call loads anything, so rows of one call
cannot admit each other. Patient, history and registry rows are checked by
patient only; their accession is context rather than an exam they create.

`graph.pop(entity)` moves an entity and everything it contains into a new graph
and returns it. Exclusive descendants keep their Python identity; a descendant
that something staying behind also contains is copied. Keys pointing back into
the original graph, such as linked accessions, stay as unresolved references.
Register the popped entity in another graph to complete a move; `register`
applies the same rules to an entity owned by another graph.

## Serialization and diagnostics

`entity.to_dict()` returns one entity's fields as JSON-ready values, with
related entities as their stored keys; `graph.to_dict()` lists every registry. `Issue` and `SourceRef` preserve optional source scope,
table, and typed diagnostic key information. `graph.unresolved_references`
reports association endpoints that have not arrived; `graph.unresolved_records`
holds source records whose clinical identity is insufficient or ambiguous.

These diagnostics do not turn physical rows into clinical identities. A caller
that needs an audit ledger or a stricter rejection policy should build that
policy around the returned report and unresolved collections.

## Development

Run from the repository root:

```bash
uv sync --frozen
uv run --frozen pytest
uv run --frozen ruff check src/embed_data_model tests examples benchmarks tools
uv run --frozen mypy
uv run --frozen python -m examples.researcher_journeys
```

The package has no mandatory runtime dependencies. pandas is used by the
development and test environment; DataFrame-like support is duck-typed at the
table boundary. The full suite includes an installed-wheel journey outside the
checkout. Synthetic checks establish library behavior, not private EMBED-data,
real-pixel, or downstream scientific validity.

Matching, localization, transfer, patch extraction, and visualization are
consumer workflows. Keep them in the downstream repository that owns the
relevant image data and analysis policy. See the [contract](contract.md) and [API reference](api.md) for the
supported semantics.
