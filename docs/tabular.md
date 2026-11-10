# Tabular projection schema

`graph.records(name)` returns flat scalar dictionaries without pandas.
`graph.table(name)` returns one pandas DataFrame; `graph.tables()` returns all
20 tables from one snapshot. Selections expose the same methods. Install pandas
separately for DataFrames. `graph.table_schema(name)` returns an immutable
`TableSchema(name, columns, key)`; schemas do not depend on present data.

Each entity grain has exactly one row per registered entity, including ancestor
context in partitions. All rows are sorted by schema key; input indexes and
physical column names never define identity or output ordering. Output cells are
strings, integers, floats, booleans, naive UTC datetimes, or null. No dictionaries,
lists, Code objects or enums occur in grain cells. Consumer attributes, metadata
and physical source references are excluded.

## Keys and relationships

`entity_key` is a canonical JSON encoding of the semantic graph key with type
tags: text `A` becomes `["str","A"]`; compound keys use nested tagged values.
Code identities use their canonical token sets, not their meaning. Dataclasses
encode their type name and ordered fields; enums encode their type and value.
Use this opaque string for joins, not parsing or clinical interpretation. Custom
keys must be serializable scalars, dates, Code, enums, dataclasses, or nested
sequences/maps; unsupported objects raise TypeError rather than using unstable
repr/object addresses. Natural keys and scalar parent keys are also provided.
Procedure-linked pathology carries the procedure's identity fields; explicitly
keyed reports carry `patient_id` and `record_id` instead. Many-valued parents
remain in link tables, without selecting an arbitrary parent.

Link tables contain supplied relationships only, unique on `(source_key,
target_key)`. Target keys use the target grain's entity_key encoding and remain
present even when that entity is absent. `exam_links` preserves supplied link
direction; the graph's symmetric linked-exam accessor is a different view.
`exam_patients` contains claims, while `exams.patient_id` remains ownership.

| Link table | Source grain | Target grain |
|---|---|---|
| exam_registry | exams | registry |
| exam_links | exams | exams |
| exam_patients | exams | patients |
| procedure_findings | procedures | findings |
| procedure_exams | procedures | exams |
| pathology_procedures | pathology | procedures |
| pathology_findings | pathology | findings |
| pathology_exams | pathology | exams |

## Values and incomplete records

Nested records and collections also appear in `values`, one scalar leaf per
`(kind, entity_key, field)`. `field` is a JSON Pointer path: `/` and `~` inside
names are escaped; sequence positions are zero-based, and sets are sorted by
canonical value first. This includes anatomy evidence, pathology descriptors,
patient history/attribute observations, registry payload, image paths/landmarks,
and ROI frame indices. Codes have companion `_meaning` paths. Empty collections
contribute no leaves. The main grain columns expose common scalar facts;
`values` retains the remaining built-in data without inventing dynamic columns.

`unresolved` includes incomplete procedure/pathology records, unkeyed findings,
invalid-accession rows, and unkeyed registry entries. `incomplete=True` distinguishes
these from entity rows. Reported `accession_number` and `finding_number` are
explicit columns on incomplete clinical records, including when the referenced
finding is absent. Consumers do not need to parse opaque addresses.

Unkeyed findings retain UNKNOWN `laterality` and null `finding_number`; their
`reported_laterality` preserves the source side independently of identity. A
supplied null side is BILATERAL (`B`), consistent with keyed EMBED findings;
an absent/unbound column or unrecognized code stays UNKNOWN.
Unkeyed findings also carry the same typed descriptor columns as `findings`
(`mass` through `implant_finding`, each with a `_meaning` companion), with the
same code normalization. Unresolved pathology rows carry `raw_severity`, the
severity as supplied, beside the normalized `severity`, so an out-of-scale code
is distinguishable from a missing one. These columns are null on other kinds.
Unkeyed registry entries expose every typed registry fact in `unresolved`,
including parsed `diagnosis_date`, normalized histology/behavior and `icdo3`,
source and normalized laterality, stages, receptors and vital status. Their
`registry_id` is null; the `registry` entity table still contains keyed entities
only. Raw registry payload remains in `unresolved_values` for audit.

`record_key` encodes the address and semantic record
contents plus an occurrence number for identical rows. It identifies a snapshot
occurrence only, never a clinical identity or cross-load match. Duplicates stay
visible. `unresolved_values` exposes their remaining semantic leaves; raw physical
clinical-row payloads are excluded. Invalid-accession mapped values retain their
`grain.field` names. Invalid-accession procedure/pathology facts also appear as
typed `procedure`/`pathology` rows with reason `invalid_accession`, normalized
severity and codes, and parsed dates. These and the raw wrapper describe the
same source evidence; they are not distinct clinical events. Their reported
invalid accession never becomes an exam key. A missing patient is null, not
an inferred owner.

For entity rows, `incomplete` marks a missing resolved parent/owner, or pathology
with no procedure date/side in its identity. It does not certify clinical
completeness. A source claim is never promoted to ownership by projection.

## Dates, codes and diagnostics

Date columns accept ISO dates/timestamps (including UTC offsets) and US
`MM/DD/YYYY`, normalized to naive UTC. Supported range is 1678-01-01 inclusive
through 2262-01-01 exclusive, so records and nanosecond DataFrames agree.
Unparseable, out-of-range and missing dates become null and produce `invalid_date`
or `missing_date` rows in `issues`. For the shared `unresolved` schema, only
applicable fields are checked: registry diagnosis date; procedure performed
date; pathology performed and report-documented dates. Unkeyed findings and
raw invalid-accession wrappers have no applicable date columns. Their typed
clinical records use the ordinary procedure/pathology date checks. Other date columns
remain null without emitting diagnostics. Source date text is still retained in the
supplementary values table for audit. No ambiguous formats are guessed.

Coded fields become strings and companion `<field>_meaning` columns; absent
codes and unknown meanings are null. Multi-code strings use sorted unique tokens
joined with commas. Meanings retain the vocabulary's supplied text/order.
Enums become their values, including numeric pathology severity.

`issues` combines deduplicated historical `graph.load_issues` and current date
projection diagnostics. Entity-addressed issues carry `kind` and `entity_key`;
unresolved-date issues use the snapshot record_key. Unaddressed batch issues
have null keys. `context` is canonical JSON text. Corrections do not erase load
history; current projection diagnostics are recomputed without mutating the
graph. Subsets retain load diagnostics addressed to included entities; global
batch diagnostics remain on the full graph.

ROI `y_min`, `x_min`, `y_stop`, `x_stop` are pixel coordinates with exclusive
stops, matching Box. The separate source coordinates retain their recorded
convention; read `source_coordinate_convention` before interpreting them.

## Types, ownership and cost

All non-key columns are nullable. Logical string/integer/number/boolean types map
to pandas StringDtype/Int64/Float64/boolean; datetime is datetime64[ns], including
empty tables. `scalar` uses object dtype. Records use native Python values and
None. Returned data is detached: editing a record/frame never changes the graph.
Selections use current values of their snapshot membership plus descendants and
ancestor context, without copying consumer state. Partitions project their
independent copies normally.

Traversal and storage are linear in entities, links and scalar leaves, followed
by O(n log n) key sorting. There is no row limit. A single-grain records/table call
avoids constructing unrelated tables; tables() builds all tables once. Large
supplementary values tables may dominate memory; request one grain when possible.
Synthetic measurements are in benchmarks/README.md; private-data performance has
not been measured. No cohort selection, BI-RADS reduction or outcome policy is
performed.

## Column lists

The following schemas are the versioned public column lists. Keys are stated for
each table. Columns appear in this order even when the table is empty.

### patients

Key: `entity_key`

| Column | Logical type |
|---|---|
| `entity_key` | string |
| `incomplete` | boolean |
| `patient_id` | string |
| `sex` | string |
| `race` | string |
| `ethnicity` | string |
| `birth_year` | integer |
| `cohort_number` | string |

### exams

Key: `entity_key`

| Column | Logical type |
|---|---|
| `entity_key` | string |
| `incomplete` | boolean |
| `accession_number` | string |
| `patient_id` | string |
| `exam_date` | datetime |
| `description` | string |
| `patient_age` | number |
| `location_id` | string |
| `accession_type` | string |
| `total_left_findings` | number |
| `total_right_findings` | number |
| `contested` | boolean |
| `owner_explicit` | boolean |
| `imaged_laterality` | string |
| `density` | string |
| `density_meaning` | string |
| `exam_type` | string |
| `exam_type_meaning` | string |
| `visit_type` | string |
| `visit_type_meaning` | string |
| `modality` | string |
| `modality_meaning` | string |

### findings

Key: `entity_key`

| Column | Logical type |
|---|---|
| `entity_key` | string |
| `incomplete` | boolean |
| `accession_number` | string |
| `finding_number` | string |
| `patient_id` | string |
| `laterality` | string |
| `finding_type` | string |
| `record_type` | string |
| `quadrant_ml` | string |
| `quadrant_si` | string |
| `depth` | string |
| `clock_hour` | integer |
| `location_category` | string |
| `distance_from_nipple_cm` | number |
| `assessment` | string |
| `assessment_meaning` | string |
| `recommendation` | string |
| `recommendation_meaning` | string |
| `mass` | string |
| `mass_meaning` | string |
| `asymmetry` | string |
| `asymmetry_meaning` | string |
| `architectural_distortion` | string |
| `architectural_distortion_meaning` | string |
| `calcification` | string |
| `calcification_meaning` | string |
| `mass_shape` | string |
| `mass_shape_meaning` | string |
| `mass_margin` | string |
| `mass_margin_meaning` | string |
| `mass_density` | string |
| `mass_density_meaning` | string |
| `calcification_morphology` | string |
| `calcification_morphology_meaning` | string |
| `calcification_distribution` | string |
| `calcification_distribution_meaning` | string |
| `calcification_number` | string |
| `calcification_number_meaning` | string |
| `other_finding` | string |
| `other_finding_meaning` | string |
| `implant_finding` | string |
| `implant_finding_meaning` | string |

### procedures

Key: `entity_key`

| Column | Logical type |
|---|---|
| `entity_key` | string |
| `incomplete` | boolean |
| `patient_id` | string |
| `performed_date` | datetime |
| `laterality` | string |
| `procedure_type` | string |
| `procedure_type_meaning` | string |

### pathology

Key: `entity_key`

| Column | Logical type |
|---|---|
| `entity_key` | string |
| `incomplete` | boolean |
| `patient_id` | string |
| `record_id` | string |
| `performed_date` | datetime |
| `laterality` | string |
| `diagnosis` | string |
| `result_category` | string |
| `malignant` | boolean |
| `severity` | scalar |
| `raw_severity` | scalar |
| `report_documented_date` | datetime |
| `procedure_type` | string |
| `procedure_type_meaning` | string |
| `descriptor_1` | string |
| `descriptor_1_meaning` | string |
| `descriptor_2` | string |
| `descriptor_2_meaning` | string |
| `descriptor_3` | string |
| `descriptor_3_meaning` | string |
| `descriptor_4` | string |
| `descriptor_4_meaning` | string |
| `descriptor_5` | string |
| `descriptor_5_meaning` | string |
| `descriptor_6` | string |
| `descriptor_6_meaning` | string |
| `descriptor_7` | string |
| `descriptor_7_meaning` | string |
| `descriptor_8` | string |
| `descriptor_8_meaning` | string |
| `descriptor_9` | string |
| `descriptor_9_meaning` | string |
| `descriptor_10` | string |
| `descriptor_10_meaning` | string |

### registry

Key: `entity_key`

| Column | Logical type |
|---|---|
| `entity_key` | string |
| `incomplete` | boolean |
| `patient_id` | string |
| `registry_id` | string |
| `diagnosis_date` | datetime |
| `laterality` | string |
| `source_laterality` | string |
| `histology` | string |
| `behavior` | string |
| `icdo3` | string |
| `primary_site` | string |
| `t_stage` | string |
| `n_stage` | string |
| `m_stage` | string |
| `stage_group` | string |
| `vital_status` | string |
| `estrogen_receptor` | string |
| `estrogen_receptor_meaning` | string |
| `progesterone_receptor` | string |
| `progesterone_receptor_meaning` | string |
| `her2` | string |
| `her2_meaning` | string |

### images

Key: `entity_key`

| Column | Logical type |
|---|---|
| `entity_key` | string |
| `incomplete` | boolean |
| `image_id` | string |
| `accession_number` | string |
| `patient_id` | string |
| `source_sop_instance_uid` | string |
| `derived_from` | string |
| `laterality` | string |
| `view_position` | string |
| `modality` | string |
| `source_modality` | string |
| `derived_image_type` | string |
| `height` | integer |
| `width` | integer |
| `frame_count` | integer |
| `study_instance_uid` | string |
| `series_instance_uid` | string |
| `coordinate_frame_id` | string |
| `manufacturer` | string |
| `series_description` | string |
| `view_modifier` | string |
| `spot_magnification` | boolean |
| `source_view_position` | string |

### rois

Key: `entity_key`

| Column | Logical type |
|---|---|
| `entity_key` | string |
| `incomplete` | boolean |
| `image_id` | string |
| `roi_key` | string |
| `accession_number` | string |
| `patient_id` | string |
| `source_path` | string |
| `collection_position` | integer |
| `annotation_source` | string |
| `confidence` | number |
| `coordinate_frame_id` | string |
| `source_coordinate_convention` | string |
| `frame_provenance` | string |
| `frame_derivation_method` | string |
| `y_min` | number |
| `x_min` | number |
| `y_stop` | number |
| `x_stop` | number |
| `source_y_min` | number |
| `source_x_min` | number |
| `source_y_max` | number |
| `source_x_max` | number |

### exam_registry

Key: `source_key`, `target_key`

| Column | Logical type |
|---|---|
| `source_key` | string |
| `target_key` | string |

### exam_links

Key: `source_key`, `target_key`

| Column | Logical type |
|---|---|
| `source_key` | string |
| `target_key` | string |

### exam_patients

Key: `source_key`, `target_key`

| Column | Logical type |
|---|---|
| `source_key` | string |
| `target_key` | string |

### procedure_findings

Key: `source_key`, `target_key`

| Column | Logical type |
|---|---|
| `source_key` | string |
| `target_key` | string |

### procedure_exams

Key: `source_key`, `target_key`

| Column | Logical type |
|---|---|
| `source_key` | string |
| `target_key` | string |

### pathology_procedures

Key: `source_key`, `target_key`

| Column | Logical type |
|---|---|
| `source_key` | string |
| `target_key` | string |

### pathology_findings

Key: `source_key`, `target_key`

| Column | Logical type |
|---|---|
| `source_key` | string |
| `target_key` | string |

### pathology_exams

Key: `source_key`, `target_key`

| Column | Logical type |
|---|---|
| `source_key` | string |
| `target_key` | string |

### values

Key: `kind`, `entity_key`, `field`

| Column | Logical type |
|---|---|
| `kind` | string |
| `entity_key` | string |
| `field` | string |
| `value` | scalar |

### unresolved

Key: `record_key`

| Column | Logical type |
|---|---|
| `record_key` | string |
| `address` | string |
| `kind` | string |
| `reason` | string |
| `patient_id` | string |
| `accession_number` | string |
| `incomplete` | boolean |
| `assessment` | string |
| `assessment_meaning` | string |
| `recommendation` | string |
| `recommendation_meaning` | string |
| `performed_date` | datetime |
| `procedure_type` | string |
| `procedure_type_meaning` | string |
| `laterality` | string |
| `severity` | scalar |
| `report_documented_date` | datetime |
| `finding_number` | string |
| `reported_laterality` | string |
| `registry_id` | string |
| `diagnosis_date` | datetime |
| `source_laterality` | string |
| `histology` | string |
| `behavior` | string |
| `icdo3` | string |
| `primary_site` | string |
| `t_stage` | string |
| `n_stage` | string |
| `m_stage` | string |
| `stage_group` | string |
| `vital_status` | string |
| `estrogen_receptor` | string |
| `estrogen_receptor_meaning` | string |
| `progesterone_receptor` | string |
| `progesterone_receptor_meaning` | string |
| `her2` | string |
| `her2_meaning` | string |
| `raw_severity` | scalar |
| `mass` | string |
| `mass_meaning` | string |
| `asymmetry` | string |
| `asymmetry_meaning` | string |
| `architectural_distortion` | string |
| `architectural_distortion_meaning` | string |
| `calcification` | string |
| `calcification_meaning` | string |
| `mass_shape` | string |
| `mass_shape_meaning` | string |
| `mass_margin` | string |
| `mass_margin_meaning` | string |
| `mass_density` | string |
| `mass_density_meaning` | string |
| `calcification_morphology` | string |
| `calcification_morphology_meaning` | string |
| `calcification_distribution` | string |
| `calcification_distribution_meaning` | string |
| `calcification_number` | string |
| `calcification_number_meaning` | string |
| `other_finding` | string |
| `other_finding_meaning` | string |
| `implant_finding` | string |
| `implant_finding_meaning` | string |

### unresolved_values

Key: `record_key`, `field`

| Column | Logical type |
|---|---|
| `record_key` | string |
| `field` | string |
| `value` | scalar |

### issues

Key: `issue_key`

| Column | Logical type |
|---|---|
| `issue_key` | string |
| `kind` | string |
| `entity_key` | string |
| `field` | string |
| `code` | string |
| `message` | string |
| `severity` | string |
| `context` | string |
