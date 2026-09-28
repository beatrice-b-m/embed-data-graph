# Changelog

## 0.3.0 — 2026-09-28

Source release `v0.3.0`. This release renames the project to EMBED Data Graph.
It is breaking only in name: the distribution, the import namespace and the
repository change, and the public API, loading behavior, Python 3.9–3.13
support and the absence of mandatory runtime dependencies are unchanged. The
Changed section gives the migration steps.

### Changed

- The project is renamed from EMBED Data Model to EMBED Data Graph. The
  distribution is now `embed-data-graph` and the Python namespace is now
  `embed_data_graph`. The source repository moves to
  `beatrice-b-m/embed-data-graph`. The old name suggested a common data model
  such as OMOP. The library builds a graph of the objects that EMBED rows
  describe and does not map them into a target schema. The API is otherwise
  unchanged.

  This is a breaking change with no compatibility shim: `embed_data_model` can
  no longer be imported. To migrate:

  1. Replace the `embed-data-model` dependency with `embed-data-graph`, pinned
     to the new tag or commit from
     `https://github.com/beatrice-b-m/embed-data-graph.git`.
  2. Replace every `embed_data_model` import with `embed_data_graph`, including
     submodules such as `embed_data_graph.sources.embed.columns`.
  3. Reinstall into existing environments. An editable install of the old
     distribution does not provide the new namespace.

## 0.2.1 — 2026-09-28

Source release `v0.2.1`. This patch release fixes incremental loading and
partitioning: later tables and partial extracts no longer overwrite patient
claims, anatomy or dated attributes loaded earlier, and partitions keep the
records and links that belong to their patients. It adds an opt-in
`parents="existing"` mode to `load_embed`; the default behavior of documented
APIs is unchanged apart from the fixes below. Python 3.9–3.13 support and the
absence of mandatory runtime dependencies are unchanged.

### Added

- `load_embed(..., parents="existing")` loads whole tables into a subset graph
  without adding patients or exams. A row loads only when every patient and exam
  it addresses is already in the target graph; skipped rows are counted in one
  INFO issue per table (`rows_outside_graph`). The default, `parents="create"`,
  keeps the previous behavior, which registers the patients and exams rows
  address. Previously, loading a full image table into a partition re-grew it
  with placeholder exams unless the rows were filtered first.

### Fixed

- Loading images, procedures or pathology after MagView no longer replaces the
  exam's patient claims. Claims are kept per source table, and refresh replaces
  only the claims of the table being reloaded. Previously the last table loaded
  won: an image path naming another patient could re-parent an exam or hide a
  conflict, and the result depended on load order. `set_patient_claims` still
  replaces every claim. An image row whose patient column disagrees with its
  path is reported as `source_patient_path_mismatch`.
- Partial finding extracts keep the anatomy they do not supply. A row with only
  distance or location no longer resets the finding's side and depth to
  unknown, and a side-only correction now moves the anatomical position to the
  new side instead of leaving it on the old one. MagView side and a narrow
  location table give the same position in either load order.
- A patient-attribute correction without the exam-date column replaces the
  observation for its accession's dated context. Previously it added a second,
  undated observation and the scalar attribute became unknown.
- `is_context` no longer reports a newly added object as context when it
  reuses the Python id of a removed one. Removing or moving an entity ends its
  context mark; later loads leave the mark unchanged.
- Patient partitions, `pop` and `register` of a patient now carry registry
  entries not assigned to an exam and procedures or pathology without an
  accession. Previously these were dropped from the copy or left behind.
- A partition keeps a link that only an exam outside it records, as an
  unresolved reference on the copied exam. Previously the link disappeared.
- Partitioning no longer scans every unresolved record once per group, which
  made per-exam partitions quadratic in the number of unresolved records.

## 0.2.0 — 2026-09-23

Source release `v0.2.0`. This release aligns the model with the EMBED
clinical-semantic catalog and simplifies the public API. It contains breaking
changes: coded fields load as `Code` values, several unused types and aliases
are removed, and relationships are resolved through the graph. The Removed and
Changed sections list each change and how to migrate. Python 3.9–3.13 support
and the absence of mandatory runtime dependencies are unchanged.

### Added

- `Code`, a source code together with its human-readable meaning. Assessment,
  recommendation, exam density/type/visit type/modality, finding descriptors,
  procedure type, pathology descriptor slots and patient-history category,
  code and result load as `Code` values decoded
  with EMBED vocabulary tables (`sources.embed.vocabulary`), generated from the
  EMBED catalog by `tools/generate_embed_vocabulary.py`. These fields no longer
  equal plain strings; compare `.code` or `.meaning`.
- Exam fields `density` (`tissueden`), `exam_type` (`mg_exam_type`),
  `visit_type` (`vtype`), `modality` (`modality_desc`) and `patient_age`
  (`age_at_study_anon`), loaded by default. `validate` flags a patient age
  outside 1-89 (EMBED top-codes ages at 89; zero is a data-quality error).
- Patient `race` and `ethnicity`, recorded per exam context like `sex`.
- Finding descriptors from the MagView mass, asymmetry, architectural
  distortion, calcification, other-finding and implant columns, stored in
  `finding.descriptors` as `Code` values under semantic names. Each descriptor
  follows refresh and merge on its own. Comma-separated codes are kept whole,
  with the meaning of each part.
  The unbound free-form `descriptors` binding is removed.

### Removed

- `core.birads` and its lexicon normalizers. They were never used by the loader
  and accept only English BI-RADS terms such as "oval", while EMBED stores
  source codes such as "O" in columns that mix finding kinds. EMBED finding
  descriptors are now loaded as their source codes (see Added).
- Graph internals exposed as API: `reference`, `remove_reference`,
  `clear_references`, `operation_counts`, `issues`, `identity_namespace`, and
  the `core.selection.select`/`partition` functions (use the graph methods).
- Aliases and duplicate methods: `pathologies`, `registry_pathology`,
  `finding_index`, `finding_id`, `extend_findings`, `set_linked_exam`,
  `set_registry_entry`, `add_linked_accession`, `add_registry_reference`,
  `Finding.merge_observation`, `Selection.owning`.
- `ExamAttributeObservation` and `Exam.attribute_observations`: exam fields are
  invariant across rows and were never loaded as observations.
- `PathologyDiagnosis`, an intermediate object the adapter copied field by
  field into `Pathology`. `normalize_pathology` returns a dictionary of
  supplied `Pathology` fields plus the descriptor slots.
- `docs/qualification.md`, a dated record of one local test run whose counts
  and commit hashes went stale with the next change. CI records test results.
- `load_embed` parameters `retain_raw` (validated but never used),
  `registry_rows` (an alias of `registry`) and `identity_namespace` (a label
  that changed nothing).
- The `core.provenance` module (`SourceLocator`, `BuildIssue`,
  `SourceOccurrence`, `ResolutionState`, `AvailabilityState`,
  `SourceScopeKind` and a duplicate `IssueSeverity`). The loader only ever
  produced `SourceRef`, which is now the single source-row type; each class
  validates it through `core.source.optional_source`.
  `ImagingInterpretation` drops its availability fields and its separate
  `source` constructor argument; pass `sources`.
- Unused association and attribution types that the library never produced:
  the `clinical.associations` module (`AttributionStatus`,
  `ClinicalObjectReference`, `FindingProcedureLink`, `AssociationLink`),
  `PathologyReference`, `PathologyAttributionLink`, `PathologyRecordKind` and
  `UnresolvedProcedureOccurrence`. Relationships are represented by the graph
  and unresolved records keep their source payload.

### Changed

- Relationships are stored as keys on the entities and resolved by
  `DatasetGraph` indexes. A finding stores its exam's accession, a procedure the
  keys of its findings and exams (`finding_references`, `exam_references`),
  pathology the keys of its procedures, findings and exams, and an exam its
  owner, links and registry assignments. Relationships form in any arrival
  order, collections are resolved on access, and a changed key is propagated to
  every entity that stored it.
- Adding a child to an entity without a graph registers both in a new graph.
  The standalone-tree rekey is gone; rekeying always goes through a graph.
- `graph.pop(entity)` returns the entity inside a new graph that holds what it
  contains, instead of a graph-less tree. `register` and `pop` no longer take a
  `boundary` argument.
- Assigning a key or reference field of a registered entity goes through the
  graph instead of raising `AttributeError`.
- `Exam.breast_sides` is computed on access, so it always matches finding and
  image laterality. `BreastSide` is a frozen view and `Exam.ensure_side` is
  removed.
- Partition context is reported by `graph.is_context(entity)` instead of a
  `context` attribute on copies. Copies keep the keys they stored, so
  relationships to entities outside a group stay unresolved references.
- `to_dict()` exports one entity's fields, with related entities as keys,
  instead of nesting its descendants.
- Constructors no longer accept child collections (`Patient(exams=...)`,
  `Exam(findings=..., images=..., procedures=..., pathology=...,
  registry_pathology=..., breast_sides=...)`, `Finding(procedures=...)`,
  `Procedure(pathologies=...)`, `MammogramImage(rois=...)`); use the `add_*`
  methods.
- `PathologyObservation` is a frozen value `(descriptor, source_slot,
  source_ordinal, source)`.
- `ImagingInterpretation(assessment=None, recommendation=None, sources=())` is
  a mutable value stored on its finding; it no longer takes or repeats
  `accession_number` and `finding_number`.
- Patient history observations and `HistoryTimeEstimate` are values stored
  on their `Patient` and no longer carry `patient_id`; construct them without
  it. Observations stay mutable through `update`, which re-checks fields.
  `HistoryTimeEstimate` is frozen. The history normalizers no longer take a
  `patient_id` argument.
- `MedicationHistoryObservation.category`/`medication` and
  `ProcedureHistoryObservation.category`/`procedure`/`reported_result` are
  `Code` values with EMBED meanings, replacing library-invented labels such as
  `"hormone"` or `"core_biopsy"`. A history code is decoded in its category's
  table. Category and code are now the first, required constructor fields;
  `source` and `record_id` follow the other fields. The coarse
  `ProcedureHistoryObservation.detail` grouping is removed.
- `ImageLandmark` is a frozen value `(y, x, landmark_type, confidence,
  source)` that no longer repeats its image's ID. Change one with
  `dataclasses.replace`. `ImageLandmark.owned_by`, the `image_id` and
  `provenance` fields, and `MammogramImage.with_landmark` (a shallow copy that
  shared mutable state) are removed.
- `PathologySeverity` members carry their EMBED meanings
  (`INVASIVE_BREAST_CANCER`=0 through `NON_BREAST_CANCER`=5) instead of
  `SEVERITY_0`–`SEVERITY_5`. The docstring records the inverse ordering and
  that code 5 is non-breast cancer.
- Patient attributes are recorded per exam context as
  `PatientAttributeObservation(attribute, value, accession_number,
  context_date)`. `Patient.attribute_as_of` and `Patient.attribute_history`
  choose values explicitly. `patient.sex` keeps a value only when all
  observations agree. Values that differ between exams are no longer reported
  as conflicts or discarded. `Patient.context_date` and the unused
  `select_patient_attribute_as_of` selection types are removed.
- `Pathology(...)` requires an explicit `identity` or both `patient_id` and
  `record_id`. The undocumented `**identity_parts` attachment/report-date
  fallback, which could not be reached through the constructor, is removed.
- Refresh replaces only fields whose columns the rows supply. An explicit null
  still clears a field, but a column absent from every row now leaves it
  unchanged. Previously a findings-only MagView load cleared the exam date,
  exam description and patient sex loaded earlier.
- Default column bindings now name only columns that exist in the internal
  EMBED tables. `patients.birth_year`, `images.series_instance_uid` and
  pathology `diagnosis`, `result_category` and `malignant` are unbound by
  default; bind them through `columns` if a source provides them.

### Fixed

- A prior-procedure history result of `NONE` loads as a `Code` meaning "No
  reported result" instead of None, so it stays distinct from a blank result. `NONE` means no
  result was reported; it is not a negative result.
- Pathology on MagView procedure rows is keyed by its procedure and attaches to
  it. It was keyed on the provisional pathology report date (`pdate_anon`), so
  pathology without that date became an unresolved record even when its
  procedure was fully identified. The report date is now only an attribute.
- A refresh that supplies a corrected patient ID for an exam now replaces its
  source claims. Previously claims only accumulated, so a corrected row left
  the exam permanently unowned. Merge still adds claims.
  `DatasetGraph.set_patient_claims` replaces an exam's claims directly.
- `mode="merge"` now detects values that contradict a populated value already
  in the graph. The field becomes unknown and the load reports
  `conflicting_<grain>_<field>`. Previously a later merge silently overwrote
  the earlier value, and only conflicts within one call were detected.
- A supplied null finding `side` now loads as bilateral and projects to both
  breast sides, matching the EMBED MagView convention. It previously loaded as
  unknown and the finding appeared on neither side.
- Coded values (assessment, recommendation, procedure type, pathology
  descriptors) are trimmed and uppercased before comparison, so formatting
  variants of one code no longer register as conflicting values. Procedure
  identities and descriptors now carry the normalized code.
- A negative finding `distance` (EMBED uses values such as -2 and -99 as
  undocumented exceptional codes) is no longer stored as a distance from the
  nipple. The raw code stays in `source_distance_codes` and the load reports
  `exceptional_finding_distance`. `validate` flags a negative or non-finite
  distance supplied directly.
- `ImagesInAcquisition` is loaded as `frame_count` only for DBT images; on other
  image types it is not a frame count. `validate` no longer rejects every DBT
  image with a frame count (it compared against the wrong modality value), and
  multiple frames on a non-DBT image is now a warning instead of an error.
- Image `height`, `width` and `frame_count` load as integers, matching their
  documented type; a fractional value is reported instead of stored.
- Unknown or conflicting location and depth codes are reported as finding
  `normalization_warnings` and load issues whether or not `source_keys` are
  supplied. Previously they were silently dropped without source keys.
  `FindingNormalizationEvidence` and `FindingNormalizationWarning` accept
  `source=None`.

## 0.1.0 — 2026-09-09

First tagged source release, `v0.1.0`, under the MIT license, with Python
3.9–3.13 qualification and no mandatory runtime dependencies.

### Data model

- Provide mutable patient, exam, finding, procedure, pathology, image, and ROI
  objects, with indexed graph membership and source lookups.
- Load optional EMBED tables using semantic identities, in-place refresh,
  explicit merge, and inspectable unresolved records and relationships.
- Support consumer extensions, explicit validation, live selections,
  independent partitions, and subtree movement.

### Packaging

- Distribute `embed-data-model` with the Python namespace `embed_data_model`.
- Include typed source, MIT license text, and wheel installation checks.
- Provide a Python project at the repository root with a locked development
  environment and tests for each supported Python minor version.

### Documentation

- Provide installation instructions, runnable researcher examples, and
  downstream integration guidance.
- Specify object and API contracts, development checks, and compatibility policy.
- Record local test qualification and synthetic loading measurements.
