# EMBED Data Model API reference

This reference specifies the behavior defined by the [contract](contract.md).
See the [user guide](user-guide.md) for runnable examples.

Public classes, properties and entry points carry inline usage contracts for
editor hovers and `help()`. For example, inspect `help(load_embed)`,
`help(DatasetGraph.partition)`, or `help(RegionOfInterest.from_embed_coordinates)`
after importing them from the package root. Field descriptions appear in class
help and alongside annotated fields. The distribution includes `py.typed`;
there is no separate stub package.

Graph lookups return a typed entity or `None`; collection properties contain
live entities. Selection overloads use the eight supported literal level names
to retain the type of iterated objects and callback parameters. Dynamic level
variables should be annotated with the corresponding `Literal` choices.
Mutation `**fields` intentionally remains open for consumer attributes; consult
the entity constructor for ordinary fields and their types. ROI factory overloads
expose base constructor options and preserve arbitrary subclass forwarding.
These annotations do not introduce runtime validation or new root exports.

## Identity, relationships, and mutation

The graph holds eight entity kinds, each keyed by its source identity:
patient (`patient_id`), exam (`accession_number`), finding
(`(accession_number, finding_number)`), procedure (`ProcedureIdentity`),
pathology (`identity`), registry entry (`(patient_id, registry_id)`), image
(`image_id`) and ROI (`(image_id, roi_key)`).

Entities store the *keys* of related entities, never object pointers: a
finding stores its exam's accession, an ROI its image's ID, a procedure the
keys of its findings and exams (`finding_references`, `exam_references`),
pathology the keys of its procedures, findings and exams, and an exam its
owner (`patient_id`), linked accessions and registry assignments. The graph
resolves these keys through indexes, so entities can be registered in any order
and a relationship appears once both ends are present. `unresolved_references`
lists stored keys whose target is absent. Collections such as `exam.findings`,
`finding.procedures` or `patient.exams` are resolved on access; an entity
without a graph has none. Adding a child to an entity without a graph first
registers it in a new graph.

One accession has one `Exam`; its `asserted_patient_ids` retains all source
claims. Conflicting claims leave `patient_id` unset until
`graph.assign_patient(exam, patient_id)` chooses ownership explicitly. That choice
persists on reload; source identities are unchanged.

Each entity has `graph` (zero or one owner), `update(**fields)`, and
`rekey(**key_fields)`. Changing a key, reference or source-alias field of a
registered entity, by `update`, `rekey` or plain assignment, goes through the
graph. A key change is propagated: every entity that stored the old key stores
the new one, and entities whose own key includes it (findings of a rekeyed exam,
ROIs of a rekeyed image) are rekeyed too. The whole change is checked for key
and source-SOP collisions before anything is modified. A patient rekey keeps its
exams (their owner becomes explicit) and leaves source claims, image patient
claims and procedure or registry identities unchanged.

Graph methods: `register(entity)`, `attach(parent, child)`, `detach(parent,
child)`, `update(entity, **fields)`, `rekey(entity, **fields)`, `pop(entity)`,
`remove(entity)` and `replace_rois(image, rois)`. `detach` removes an optional or
many-valued containment and refuses one that is part of the child's key.
`children`, `parents`, `descendants` and `ancestors` expose the structure.

`pop(entity)` moves the entity and everything it contains into a new graph and
returns it (`entity.graph` is the new graph). Contained entities keep their Python
identity. A contained entity that something staying behind also contains, such
as a procedure attached to findings of two exams, stays and is deep-copied into
the new graph. `register` moves an entity from another graph the same way, after
checking every key first. Keys pointing across the boundary remain unresolved
references until their targets are registered in the same graph.

Linked exams are associations, never containment, and read symmetrically:
`exam.linked_exams` includes exams this one lists and exams that list it.

`select(level=..., predicate=...)` returns a non-owning view. `partition(level=...,
key=...)` returns independent graphs holding deep copies of the grouped entities,
everything they contain, and their ancestors, for which `graph.is_context(entity)`
is True. A grouped patient also brings the registry entries, procedures and
pathology that name it. Copies keep the keys they stored, so relationships to
entities outside a group stay unresolved; a link recorded only on an exam outside
the group is added to the copied exam's `linked_accessions` for the same reason.
The context mark is fixed when the partition is made and ends when the entity is
removed or moved. Copy failures raise an informative error; consumer
`__deepcopy__` hooks are supported.

## Semantic loading

`load_embed(..., into=None, mode="refresh", columns=None)` returns a compact
report containing the graph and issues. Inputs are optional. One invocation is
one complete grouped snapshot; callers must assemble complete groups across
streaming chunks before invoking refresh. Separate calls are separate snapshots.

Refresh replaces bound adapter-managed scalar fields whose columns are supplied,
including explicit nulls, and applies the combined snapshot. Columns absent from
every row leave their fields unchanged. Unbound fields, consumer metadata/attributes,
subclass types, Python references, and unspecified descendant grains survive.
Merge applies supplied non-null fields. Complementary rows combine; a value that
conflicts with another supplied value or with a populated value already in the
graph becomes unknown with a diagnostic. Wide and narrow projections
share one grouping stage. Child rows ensure parents without refreshing them.

`parents="existing"` (default `"create"`) requires `into` and loads a row only
when every patient and exam it addresses is already in the graph when the call
starts. A whole table loaded into a partition or popped graph then attaches to
that subset without adding patients or exams; existing exams still gain new
findings, images, procedures and pathology. Patient, history and registry rows
are checked by patient only. Image rows use the patient named by the EMBED path
when the patient column is absent. ROI rows attach only to images already
present or loaded by admitted image rows. A row that addresses no patient or
exam is not loaded. Skipped rows are counted in one INFO issue per table with
code `rows_outside_graph` and context `{"table": ..., "rows": ...}`.

Managed fields by grain (bound mapped fields only): patient sex/birth_year, recorded
per exam context as attribute observations (a row without the date column
addresses its accession's one dated context);
exam exam_date/description; finding laterality/finding_type/interpretation/anatomy,
source anatomy codes/descriptors/record_type; image laterality/view/modality,
source modality/derived type, dimensions/frame_count, study/series IDs and coordinate
frame; procedure non-key adapter payload; pathology diagnosis/result_category,
malignant/severity/raw_severity/report_documented_date and ordered descriptors;
registry explicitly mapped payload fields. Source aliases and source identity,
source patient claims, keys, children and assignment sets have separate rules.
History snapshots replace each addressed patient's supplied history kind when no
explicit event ID is bound; merge of unkeyed history collections requires explicit
record IDs rather than guessing event equality.

## Coded values

Coded source fields hold `Code(code, meaning, tokens, unknown)` values. `code` is
the trimmed source code (alphabetic codes uppercased, exam types kept as
supplied); `meaning` comes from the EMBED vocabulary tables in
`sources.embed.vocabulary`, or is None for a code without a documented meaning.
Codes compare and hash by code (by token set for comma-separated codes) and
never equal plain strings. Constructors accept text for these fields and store a
`Code` without meaning.

Patient-history codes are scoped by category: a hormone-history `code` is
decoded in the hormone, therapy or contraceptive table its `type` selects, and
a procedure-history `pcode` in the breast or gynecological table. An unknown
category or code keeps its source code without a meaning and adds a warning. A
procedure-history result of `NONE` means no result was reported; it is not a
negative result.

## Pathology and reported facts

A pathology bundle is keyed by a supplied patient-scoped record ID,
`(patient_id, record_id)`, or, for MagView procedure rows without one, by the
procedure it was reported for, `("procedure", ProcedureIdentity)`. The
provisional report date (`pdate_anon`) is an attribute, never part of the key,
and is not a diagnosis or event date. Descriptor slots belong to the bundle;
duplicate values and order are preserved. Pathology without a complete
procedure or record ID is kept as an unresolved record with its payload and the
attachment the adapter could establish, never keyed by a row position. When rows
of one procedure disagree on a descriptor slot, the bundle is unresolved because
only a record ID could tell the reports apart. Within an addressed attachment's
refresh, unresolved snapshots replace earlier ones; no replay ledger accumulates.

`path_severity` loads as `PathologySeverity`, an inverse scale on which 0 is
invasive breast cancer and 5 non-breast cancer; code 6 is invalid and kept only
as `raw_severity`. A missing severity means no pathology is attached, not a
benign result.

History observations with an explicit record ID are updated in place on reload.
Without one they are snapshots of reported facts: never performed procedures and
never inferred distinct events. Patient attribute observations record one value
per exam context; choose among them with `Patient.attribute_as_of`.

The eight graph entities are Patient, Exam, Finding, Procedure, Pathology,
CancerRegistryEntry, MammogramImage and RegionOfInterest. Interpretations and
history observations are mutable values stored on their entity. BreastSide,
ProcedureIdentity, PatientAttributeObservation, PathologyObservation,
ImageLandmark, Box, anatomy values, enums, SourceRef and Issue are frozen values.

## Imaging and supplied association collections

`image_id` is model identity; `source_sop_instance_uid` is original identity;
`source_paths` stores location aliases. The adapter parses trailing
`cohortN/patient/study/series/SOP.dcm` path components. Explicit UID wins over disagreement and the
conflicting path UID is not a SOP alias; the supplied path remains a location alias
for the explicit UID. Derivatives require explicit model IDs and
`derived_from`; source reload follows the original even after model rekey.
An update or rekey that would give two original images the same source SOP raises
ValueError before changing fields or source indexes. The check uses the proposed
UID and derivation state together, including a derivative becoming an original.

Image metadata automatically projects ROI collections. Missing/null ROI input
preserves; explicit `[]` clears; malformed/conflicting input preserves with an issue.
Explicit `rois` input overrides automatic projection for addressed images. Both
refresh and merge replace the complete addressed image collection, including manual
ROIs. Save/pop manual annotations before replacement to retain them. Ordinals start
at zero, including singletons; equal boxes remain separate. Individual `roi.update`
preserves its reference, while collection replacement need not. Supplied depth flags
may be scalar or position-aligned lists; malformed/misaligned flags preserve the
previous collection with an issue. Derivative ROIs cannot replace the original
source collection or its source-address lookups.

Registry assignments group by accession, source patient and registry ID, independent
of findings. They remain confirmed when endpoints are missing. Refresh replaces
supplied assignment/link sets; explicit null clears; absent/unbound columns preserve;
merge unions. Refresh must contain all desired assignments for an addressed exam.
Targets are never deleted by clearing associations. Registry keys remain
(patient_id, registry_id), even when exam ownership differs.

Registry identity maps `patient_id` to `empi_anon` and `registry_id` to
`cancer_registry_id`. Payload fields are unbound by default and can be configured
through `columns`. Caller-supplied registry inputs do not require a physical table
name. MagView assignment IDs use `cancer_outcome_registry_id`.

## Validation

Numeric parsing, coordinate arity, and key/relationship representation checks are
part of construction. Bounds, ordered geometry, confidence, clinical age/date,
severity, and modality/frame plausibility are checked by explicit validation.
Warnings do not invalidate by default; error issues do. Missing optional tables
alone are valid. Validation is read-only and never called implicitly by loading.

## Current limitations

Inputs are materialized in memory,
loading is synchronous, and arbitrary multi-field updates are not transactions.
`validate(graph)` does not traverse graph registries; validate individual roots
or use `partition_by_validation` at the desired level.

For direct `Pathology` construction, use an explicit hashable `identity` or
`patient_id` plus `record_id`; anything else raises `TypeError`.

ROI `resize`/`realign` return graph-less **shallow**
copies. They retain shared mutable metadata and other referenced values; use
graph partitions when independent owning copies are needed. ROI `to_dict()`
copies metadata without recursively encoding arbitrary consumer objects, so
its output is JSON-ready only when those metadata values already are.

MagView normalization recognizes its source codes, such as `W` for upper outer,
`OU` for outer and `IN` for inner. The earlier quickstart's `UOQ` was unrecognized;
examples now use `W` and assert that finding normalization emits no warnings.
