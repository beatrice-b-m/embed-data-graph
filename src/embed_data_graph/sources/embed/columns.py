"""Small, table-local column maps for the EMBED source loader.

The maps bind only source facts that are established at this adapter boundary.
Every bound default names a column that exists in the internal EMBED MagView
or V1c image-metadata tables; semantic fields without such a column default to
None and can be bound explicitly through ``columns``.
In particular, registry payload fields and future image identity fields remain
explicitly configurable instead of being guessed from similarly named columns.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping, Optional


ColumnMap = Mapping[str, Optional[str]]


DEFAULT_COLUMNS: Mapping[str, ColumnMap] = MappingProxyType(
    {
        "patients": MappingProxyType(
            {
                "patient_id": "empi_anon",
                "accession": "acc_anon",
                "context_date": "studydate_anon",
                "sex": "GENDER_DESC",
                "race": "race",
                "ethnicity": "ethnicity",
                "birth_year": None,
            }
        ),
        "exams": MappingProxyType(
            {
                "accession": "acc_anon",
                "patient_id": "empi_anon",
                "exam_date": "studydate_anon",
                "exam_description": "desc",
                "density": "tissueden",
                "exam_type": "mg_exam_type",
                "visit_type": "vtype",
                "modality": "modality_desc",
                "patient_age": "age_at_study_anon",
            }
        ),
        "findings": MappingProxyType(
            {
                "accession": "acc_anon",
                "finding_number": "numfind",
                "patient_id": "empi_anon",
                "laterality": "side",
                "finding_type": None,
                "assessment": "asses",
                "recommendation": "recc",
                "location": "location",
                "depth": "depth",
                "distance": "distance",
                "record_type": None,
                "mass": "mass",
                "asymmetry": "asymmetry",
                "architectural_distortion": "arch_distortion",
                "calcification": "calc",
                "mass_shape": "massshape",
                "mass_margin": "massmargin",
                "mass_density": "massdens",
                "calcification_morphology": "calcfind",
                "calcification_distribution": "calcdistri",
                "calcification_number": "calcnumber",
                "other_finding": "otherfind",
                "implant_finding": "implanfind",
            }
        ),
        "images": MappingProxyType(
            {
                "image_id": None,
                "source_path": "anon_dicom_path",
                "source_sop_instance_uid": None,
                "derived_from": None,
                "patient_id": "empi_anon",
                "accession": "acc_anon",
                "laterality": "ImageLateralityFinal",
                "view_position": "ViewPosition",
                "modality": "Modality",
                "derived_image_type": "FinalImageType",
                "height": "Rows",
                "width": "Columns",
                "frame_count": "ImagesInAcquisition",
                "study_instance_uid": None,
                "series_instance_uid": None,
                "coordinate_frame_id": None,
            }
        ),
        "rois": MappingProxyType(
            {
                "image_id": None,
                "source_path": "anon_dicom_path",
                "roi_key": None,
                "coordinates": "ROI_coords",
                "frame_indices": "ROI_frames",
                "depth_derived": "ROI_depth_derived",
                "annotation_source": None,
                "confidence": None,
                "coordinate_frame_id": None,
            }
        ),
        "hormone_history": MappingProxyType(
            {
                "patient_id": "empi_anon",
                "record_id": None,
                "accession": "acc_anon",
                "category": "type",
                "medication": "code",
                "continuous": "continuous",
                "current": "current",
                "duration": "duration",
                "start_age": "first_age",
                "start_month": "mfirst",
                "start_year": "yfirst",
                "stop_age": "last_age",
                "stop_month": "mlast",
                "stop_year": "ylast",
                "comment": "comment",
            }
        ),
        "procedure_history": MappingProxyType(
            {
                "patient_id": "empi_anon",
                "record_id": None,
                "accession": "acc_anon",
                "category": "type",
                "procedure": "pcode",
                "laterality": "side",
                "result": "result",
            }
        ),
        "procedures": MappingProxyType(
            {
                "patient_id": "empi_anon",
                "record_id": None,
                "performed_date": "procdate_anon",
                "procedure_type": "type",
                "laterality": "bside",
                "accession": "acc_anon",
                "finding_number": "numfind",
            }
        ),
        "pathology": MappingProxyType(
            {
                "patient_id": "empi_anon",
                "record_id": None,
                "accession": "acc_anon",
                "finding_number": "numfind",
                "laterality": "bside",
                "procedure_date": "procdate_anon",
                "procedure_type": "type",
                "diagnosis": None,
                "result_category": None,
                "malignant": None,
                "severity": "path_severity",
                "report_documented_date": "pdate_anon",
                **{f"descriptor_{index}": f"path{index}" for index in range(1, 11)},
            }
        ),
        "registry": MappingProxyType(
            {
                "patient_id": "empi_anon",
                "registry_id": "cancer_registry_id",
                "record_id": None,
                "diagnosis": None,
                "result_category": None,
                "malignant": None,
                "severity": None,
                "report_documented_date": None,
                **{f"descriptor_{index}": None for index in range(1, 11)},
            }
        ),
        "magview": MappingProxyType(
            {
                "patient_id": "empi_anon",
                "accession": "acc_anon",
                "finding_number": "numfind",
                "registry_assignment": "cancer_outcome_registry_id",
                "linked_accession": "linkedaccession_anon",
            }
        ),
    }
)


_REQUIRED = {
    "patients": frozenset({"patient_id"}),
    "exams": frozenset({"accession"}),
    "findings": frozenset({"accession", "finding_number"}),
    # Image identity can be supplied by toolkit ID, source path, or source
    # SOP UID.  The imaging adapter reports when none of those are bound.
    "images": frozenset(),
    "rois": frozenset({"coordinates"}),
    "hormone_history": frozenset({"patient_id", "category", "medication"}),
    "procedure_history": frozenset({"patient_id", "category", "procedure"}),
    "procedures": frozenset(
        {"patient_id", "performed_date", "procedure_type", "laterality"}
    ),
    "pathology": frozenset(),
    "registry": frozenset({"patient_id", "registry_id"}),
    "magview": frozenset(),
}


def resolve_columns(
    overrides: Optional[Mapping[str, Mapping[str, Optional[str]]]],
) -> dict[str, dict[str, Optional[str]]]:
    """Return mutable per-table column maps merged with EMBED defaults.

    Parameters
    ----------
    overrides : mapping or None
        Table name to partial semantic-field-to-physical-column mapping. None
        copies all defaults. None field bindings disable optional fields only;
        supported names are the keys of DEFAULT_COLUMNS. No input is mutated.

    Returns
    -------
    dict of str to dict
        Independent table maps. DEFAULT_COLUMNS stays read-only and unchanged.

    Raises
    ------
    TypeError
        overrides or a field map is not a mapping.
    ValueError
        Unknown table/semantic field, blank column, or unbound required field.
    """

    resolved = {table: dict(fields) for table, fields in DEFAULT_COLUMNS.items()}
    if overrides is None:
        return resolved
    if not isinstance(overrides, Mapping):
        raise TypeError("columns must be a mapping of table names to field maps")

    unknown_tables = set(overrides).difference(DEFAULT_COLUMNS)
    if unknown_tables:
        names = ", ".join(sorted(str(name) for name in unknown_tables))
        raise ValueError(f"Unknown columns table(s): {names}")

    for table, field_overrides in overrides.items():
        if not isinstance(field_overrides, Mapping):
            raise TypeError(f"columns[{table!r}] must be a mapping")
        unknown_fields = set(field_overrides).difference(DEFAULT_COLUMNS[table])
        if unknown_fields:
            names = ", ".join(sorted(str(name) for name in unknown_fields))
            raise ValueError(f"Unknown {table} semantic column(s): {names}")
        for semantic, physical in field_overrides.items():
            if physical is not None and (
                not isinstance(physical, str) or not physical.strip()
            ):
                raise ValueError(
                    f"columns[{table!r}][{semantic!r}] must be a "
                    "non-empty string or None"
                )
            if semantic in _REQUIRED[table] and physical is None:
                raise ValueError(
                    f"Required {table} semantic column {semantic!r} cannot be unbound"
                )
            resolved[table][semantic] = physical
    return resolved


__all__ = ["ColumnMap", "DEFAULT_COLUMNS", "resolve_columns"]
