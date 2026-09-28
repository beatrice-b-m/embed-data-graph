# EMBED Data Model contract

This document defines the library's scope and behavior. The [API reference](api.md)
specifies method, identity, and loading semantics; the [user guide](user-guide.md)
provides runnable examples.

## Scope and clinical structure

EMBED Data Model represents clinical and mammography data as mutable objects.
It supports FFDM, DBT, and synthetic 2D, with optional EMBED table adapters.
Ultrasound and MRI are outside the supported imaging scope.

The clinical containment path is patient → exam → finding → procedure → pathology.
Exams also expose images and supplied registry associations; images contain ROIs.
Objects support direct child and descendant traversal. Patients are independent
clinical roots, grouped by `DatasetGraph` for membership and lookup. Construction
and updates use patient and semantic indexes to avoid scanning unrelated objects.

Linked exams and registry assignments preserve source-supplied relationships.
A registry entry is patient-scoped and may be assigned to multiple exams. Missing
endpoints remain inspectable references and resolve when their objects arrive.
The adapter preserves assignments without rerunning matching or inferring diagnoses.

Findings and images can share exam and breast-side context without a direct
finding-to-image or finding-to-ROI association. Cohort selection, localization,
matching, cross-image correspondence, ROI transfer, pixel processing, patch
extraction, visualization, and scientific interpretation belong to consumers.

## Semantic identity and ownership

Clinical identity comes from mapped source identifiers, never DataFrame indexes
or row order. One accession identifies one exam. Conflicting source patient claims
remain in `asserted_patient_ids`; ownership stays unset until explicitly assigned
with `graph.assign_patient`. Explicit ownership persists across reloads. Claims
are kept per source table: refresh replaces the claims a table supplied before
with the claims it supplies now, so reloading a corrected table corrects its
claim, while claims from other tables and claims added outside the loader
remain. Merge adds claims. The claims an exam asserts therefore do not depend
on the order in which tables are loaded. An image row whose patient column
disagrees with its EMBED path claims the column's patient and is reported.

A finding's side is an attribute, not part of its identity. In EMBED a supplied
null finding side means bilateral (code `B`) and projects to both breast sides;
a side column absent from every row leaves the side unknown.

Procedure identity requires patient, performed date, procedure type, and laterality.
Pathology uses an explicit patient-scoped record ID or, for MagView rows, the
identity of the procedure it belongs to. The provisional pathology report date is
an attribute, never identity. Pathology without a complete procedure or record ID,
and procedure pathology whose descriptor slots disagree across rows, remain
unresolved records.
Unkeyed histories are patient-scoped reported facts, without inferred event identity.

An image's mutable `image_id` is separate from its source SOP UID and path aliases.
The adapter can recover source identity from the EMBED path convention
`cohortN/patient/study/series/SOP.dcm`. Explicit SOP UIDs take precedence over
conflicting path-derived UIDs. Derivatives have explicit IDs and `derived_from`.

An ROI has an image-local collection key. Source annotation positions are zero-based
addresses within the loaded collection, not durable lesion identities. Equal boxes
remain separate annotations. Collection replacement can change what a position denotes.

## Loading and refresh

Every supported table input is optional. One `load_embed` invocation groups rows
into a complete snapshot per addressed semantic grain and returns its graph and
issues. Callers assemble complete groups before applying streamed refreshes.

Default refresh updates existing objects in place and replaces bound
adapter-managed scalar fields whose columns the rows supply, including explicitly
null values. A column absent from every row of a grain leaves its field
unchanged, so partial tables and extracts can be loaded progressively. It preserves Python
references, subclasses, consumer attributes and metadata, unbound fields, and
unsupplied child grains. Child-only loads ensure parent objects without resetting
their scalar fields. Explicit merge applies non-null values. Complementary rows
combine; a populated value that conflicts with another supplied value or with the
populated value already in the graph becomes unknown with a diagnostic.

Image metadata projects ROI collections by default. Valid supplied ROI collections
replace the addressed image collection in either load mode, including manual ROIs.
Missing or null input preserves the collection; an empty collection clears it;
malformed or conflicting input preserves it with an issue. Explicit ROI input takes
precedence over automatic projection. Individual ROI updates preserve the object.

Rows create the patients and exams they address by default. With
`parents="existing"` a load never adds a patient or exam: rows addressing one
absent from the target graph at the start of the call are counted and skipped,
so later tables integrate into a subset without growing it.

Supplied linked-accession and registry-assignment sets replace on refresh and union
on merge. Absent or unbound columns preserve the sets; explicit null clears them.
Clearing an association does not delete its target object.

## Mutation and graph membership

Entities are mutable and can be constructed independently of a graph. Each stores
the keys of related entities rather than object pointers, and a graph resolves
those keys through its indexes; a relationship exists whenever both ends are
registered, in any arrival order. `update` changes fields and `rekey` changes
keys; a key change is propagated to every entity that stored the old key, after
a collision check covering the whole change. Collections are resolved views.
Source claims remain source facts.

An entity belongs to at most one graph. Registration rejects distinct objects at
occupied keys. Popping an entity moves it and what it contains into a new graph.
Exclusive descendants retain Python identity; descendants also contained by
something that stays are deep-copied at the boundary. Linked exams are
associations, not containment; keys crossing the boundary stay unresolved until
their targets are present.

Selections are live, non-owning views. Partitions are independent graphs of deep
copies: the selected entities, what they contain, and their ancestors as context.
Consumer metadata is copied; unsupported copy operations raise an error.

## Validation and evidence

Ingestion performs the parsing and representation checks needed to construct
objects and relationships. Clinical plausibility and geometric quality checks are
explicit, read-only validation operations. Loading does not invoke validation or
promise transaction rollback. Optional source diagnostics do not govern identity.

`validate` returns a `ValidationResult`. Errors make it invalid; warnings remain
valid unless `warnings_invalid=True`. Missing optional tables alone are valid.
Consumers can inspect results, partition by validation, or select with independent
predicates without imposing a study-specific rejection policy on the library.

Synthetic tests establish software behavior. Private-data, real-pixel, and downstream
scientific qualification require their own evidence. See
[loading measurements](../benchmarks/README.md) for synthetic scale results.
