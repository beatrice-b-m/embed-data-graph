"""Source-SOP image normalization and image-local ROI snapshot replacement."""
from __future__ import annotations

import ast
from collections import defaultdict
from numbers import Real
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Optional

from embed_data_model.clinical.exams import Exam
from embed_data_model.clinical.patients import Patient
from embed_data_model.core.primitives import ImageModality, Laterality, ViewPosition
from embed_data_model.core.source import Issue
from embed_data_model.imaging.images import MammogramImage
from embed_data_model.imaging.rois import RegionOfInterest
from embed_data_model.sources.embed._values import (
    cell, identifier, is_missing, outside_graph_issue, reconcile_merge, whole_number)


def load_imaging(*, images: list[Mapping[str, Any]], rois: Optional[list[Mapping[str, Any]]],
                 graph: Any, columns: Mapping[str, Mapping[str, Optional[str]]],
                 mode: str, issues: list[Issue], claims: dict[str, set[str]],
                 create_images: bool = True) -> None:
    """Each ROI-bearing row supplies a complete collection, never a row identity.

    Automatic metadata collections are overridden only for images addressed by
    explicit rois rows. Missing/null input preserves; [] clears; malformed or
    conflicting replacements preserve the previous collection, including in merge.
    Without ``create_images``, ROI rows whose image is absent are skipped and
    counted instead of registering a bare image.
    """
    image_columns, roi_columns = columns["images"], columns["rois"]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in images:
        observation = _observation(row, image_columns, issues)
        if observation is not None:
            groups[observation["group"]].append(observation)
    for key, observations in groups.items():
        first = observations[0]
        derivative = first["derived_from"] is not None
        image = graph.image(first["image_id"]) if derivative else (
            graph.source_image(first["source_sop_instance_uid"]) if first["source_sop_instance_uid"] else graph.image(first["image_id"]))
        fields: dict[str, Any] = {}
        managed = set().union(*(item["managed"] for item in observations))
        for field in sorted(managed):
            values = _distinct(item["fields"].get(field) for item in observations)
            if len(values) > 1:
                _issue(issues, "conflicting_image_values", "Conflicting populated image values become unknown", identity=key, field=field)
                fields[field] = _unknown(field)
            elif values:
                fields[field] = values[0]
            elif mode == "refresh":
                fields[field] = _unknown(field)
        # Parent identity is an association; absent/null rows do not erase it.
        accession_values = _distinct(item["accession"] for item in observations)
        patient_values = _distinct(item["patient"] for item in observations)
        accession = accession_values[0] if len(accession_values) == 1 else None
        patient = patient_values[0] if len(patient_values) == 1 else None
        aliases = set().union(*(item["source_paths"] for item in observations))
        if image is None:
            try:
                image = graph.register(MammogramImage(first["image_id"], source_sop_instance_uid=first["source_sop_instance_uid"],
                    source_paths=aliases, derived_from=first["derived_from"], accession_number=accession, patient_id=patient, **fields))
            except (ValueError, TypeError) as exc:
                _issue(issues, "image_registration_failed", str(exc), image_id=first["image_id"])
                continue
        else:
            if mode == "merge":
                reconcile_merge({name: getattr(image, name, None) for name in fields}, fields, grain="image", key=key, issues=issues)
            graph.update(image, **fields)
            graph.update(image, source_paths=set(image.source_paths) | aliases)
            if accession is not None and image.accession_number != accession:
                graph.update(image, accession_number=accession)
            if patient is not None:
                graph.update(image, patient_id=patient)
        if accession:
            if graph.exam(accession) is None:
                graph.register(Exam(accession))
            for claim in patient_values:
                if graph.patient(claim) is None:
                    graph.register(Patient(claim))
            claims.setdefault(accession, set()).update(patient_values)

    automatic: dict[str, list[tuple[Mapping[str, Any], MammogramImage]]] = defaultdict(list)
    explicit: dict[str, list[tuple[Mapping[str, Any], MammogramImage]]] = defaultdict(list)
    metadata_roi_columns = dict(roi_columns)
    for field in ("image_id", "source_path"):
        if image_columns.get(field) is not None:
            metadata_roi_columns[field] = image_columns[field]
    outside: dict[str, list[Mapping[str, Any]]] = {"images": [], "rois": []}
    for table, rows, target_groups, cmap in (("images", images, automatic, metadata_roi_columns),
                                             ("rois", rois or [], explicit, roi_columns)):
        for row in rows:
            image = _roi_image(row, cmap, image_columns, graph, issues, None if create_images else outside[table])
            if image is not None:
                target_groups[image.image_id].append((row, image))
    if outside["rois"]:
        # Image rows were scoped by the loader; only explicit ROI rows are new here.
        issues.append(outside_graph_issue("rois", len(outside["rois"])))
    automatic.update(explicit)
    for image_id, roi_rows in automatic.items():
        image = roi_rows[0][1]
        collections: list[tuple[RegionOfInterest, ...]] = []
        invalid = False
        for row, _ in roi_rows:
            raw = _mapped(row, roi_columns, "coordinates")
            if is_missing(raw):
                continue
            try:
                collection = _collection(row, roi_columns, image)
            except (ValueError, TypeError, SyntaxError) as exc:
                _issue(issues, "invalid_roi_collection", str(exc), image_id=image_id)
                invalid = True
                continue
            signature = _signature(collection)
            if not any(_signature(existing) == signature for existing in collections):
                collections.append(collection)
        if len(collections) > 1:
            _issue(issues, "conflicting_roi_collections", "Different complete collections require an explicit resolution", image_id=image_id)
            invalid = True
        if collections and not invalid:
            graph.replace_rois(image, collections[0])


def _observation(row: Mapping[str, Any], columns: Mapping[str, Optional[str]], issues: list[Issue]) -> Optional[dict[str, Any]]:
    path = identifier(_mapped(row, columns, "source_path"))
    parsed = _parse_embed_path(path)
    explicit_uid = identifier(_mapped(row, columns, "source_sop_instance_uid"))
    if explicit_uid and parsed and explicit_uid != parsed["source_sop_instance_uid"]:
        _issue(issues, "source_sop_path_mismatch", "Explicit SOP wins over path-derived SOP", explicit_uid=explicit_uid, path_uid=parsed["source_sop_instance_uid"], path=path)
    if path and parsed is None:
        _issue(issues, "unparseable_image_path", "Path does not match cohort/patient/study/series/SOP.dcm", path=path)
    uid = explicit_uid or (parsed["source_sop_instance_uid"] if parsed else None)
    explicit_id = identifier(_mapped(row, columns, "image_id"))
    derived = _mapped(row, columns, "derived_from")
    if is_missing(derived):
        derived = None
    if derived is not None and explicit_id is None:
        _issue(issues, "derivative_requires_image_id", "A derivative requires an explicit toolkit ID")
        return None
    image_id = explicit_id or uid
    if not image_id:
        _issue(issues, "unresolved_image_identity", "Image needs explicit identity or a valid source path")
        return None
    fields: dict[str, Any] = {}
    scalar_map = {"laterality": "laterality", "view_position": "view_position", "height": "height", "width": "width",
                  "frame_count": "frame_count", "study_instance_uid": "study_instance_uid", "series_instance_uid": "series_instance_uid",
                  "coordinate_frame_id": "coordinate_frame_id", "derived_image_type": "derived_image_type"}
    for semantic, field in scalar_map.items():
        if _supplied(row, columns, semantic):
            raw = _mapped(row, columns, semantic)
            if not is_missing(raw):
                if semantic == "laterality":
                    raw = Laterality.coerce(raw)
                elif semantic == "view_position":
                    raw = ViewPosition.coerce(raw)
                elif semantic in {"height", "width", "frame_count"}:
                    count = whole_number(raw)
                    if count is None:
                        _issue(issues, "image_numeric_parse", "Image dimension/frame fact is not a whole number", field=semantic, value=raw)
                    raw = count
                fields[field] = raw
            else:
                fields[field] = None
    if _supplied(row, columns, "modality") or _supplied(row, columns, "derived_image_type"):
        raw_modality = _mapped(row, columns, "modality")
        raw_type = _mapped(row, columns, "derived_image_type")
        inferred = ImageModality.coerce(raw_type)
        fields["modality"] = inferred if inferred is not ImageModality.UNKNOWN else ImageModality.coerce(raw_modality)
        if _supplied(row, columns, "modality"):
            fields["source_modality"] = identifier(raw_modality)
        if is_missing(raw_modality) and is_missing(raw_type):
            fields["modality"] = None
    if "frame_count" in fields and fields.get("modality") is not ImageModality.DBT:
        # ImagesInAcquisition is a frame count only for DBT images; on other
        # image types it must not be interpreted as frames.
        fields["frame_count"] = None
    if parsed:
        for field in ("study_instance_uid", "series_instance_uid"):
            if fields.get(field) is None:
                fields[field] = parsed[field]
    return {"group": image_id if derived is not None else uid or image_id, "image_id": image_id,
            "source_sop_instance_uid": uid, "source_paths": {path} if path else set(), "derived_from": derived,
            "patient": identifier(_mapped(row, columns, "patient_id")) or (parsed["patient_id"] if parsed else None),
            "accession": identifier(_mapped(row, columns, "accession")), "managed": set(fields), "fields": fields}


def _roi_image(row: Mapping[str, Any], columns: Mapping[str, Optional[str]], image_columns: Mapping[str, Optional[str]], graph: Any,
               issues: list[Issue], outside: Optional[list[Mapping[str, Any]]] = None) -> Any:
    """Return the image an ROI row addresses, registering it when absent.

    When ``outside`` is a list, a row that would register a new image is
    appended to it and None is returned instead.
    """
    path = identifier(_mapped(row, columns, "source_path"))
    explicit_id = identifier(_mapped(row, columns, "image_id"))
    uid = identifier(_mapped(row, image_columns, "source_sop_instance_uid"))
    if explicit_id:
        image = graph.image(explicit_id)
        if image is not None:
            return image
    if path:
        image = graph.image_at_path(path)
        if image is not None:
            return image
    parsed = _parse_embed_path(path)
    uid = uid or (parsed["source_sop_instance_uid"] if parsed else None)
    image = graph.source_image(uid) if uid else None
    if image is not None:
        if path:
            graph.update(image, source_paths=set(image.source_paths) | {path})
        return image
    if is_missing(_mapped(row, columns, "coordinates")):
        return None
    if outside is not None:
        outside.append(row)
        return None
    image_id = explicit_id or uid
    if not image_id:
        _issue(issues, "unresolved_roi_identity", "ROI collection lacks a usable source image identity")
        return None
    try:
        return graph.register(MammogramImage(image_id, source_sop_instance_uid=uid, source_paths={path} if path else ()))
    except ValueError as exc:
        _issue(issues, "roi_image_collision", str(exc))
        return None


def _collection(row: Mapping[str, Any], columns: Mapping[str, Optional[str]], image: MammogramImage) -> tuple[RegionOfInterest, ...]:
    value = _literal(_mapped(row, columns, "coordinates"))
    if not isinstance(value, (list, tuple)):
        raise ValueError("ROI collection must be a sequence")
    if len(value) == 4 and all(isinstance(item, Real) and not isinstance(item, bool) for item in value):
        value = [value]
    frames = _literal(_mapped(row, columns, "frame_indices"))
    depth_derived = _mapped(row, columns, "depth_derived")
    if isinstance(depth_derived, str) and depth_derived.strip().startswith(("[", "(")):
        depth_derived = _literal(depth_derived)
    flags = depth_derived if isinstance(depth_derived, (list, tuple)) else [depth_derived] * len(value)
    if len(flags) != len(value):
        raise ValueError("Depth flags must align with ROI collection slots")
    confidence = _mapped(row, columns, "confidence")
    if not is_missing(confidence):
        confidence = float(confidence)
    else:
        confidence = None
    source_path = identifier(_mapped(row, columns, "source_path"))
    result = []
    for position, box in enumerate(value):
        flag = flags[position]
        if is_missing(flag):
            derived = False
        elif str(flag).strip().lower() in {"1", "1.0", "true", "yes"}:
            derived = True
        elif str(flag).strip().lower() in {"0", "0.0", "false", "no"}:
            derived = False
        else:
            raise ValueError("Depth flags must be boolean values")
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            raise ValueError("Each ROI needs exactly four numeric coordinates")
        coords = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
        indices: tuple[int, ...] = ()
        if frames is not None:
            if not isinstance(frames, (list, tuple)):
                raise ValueError("ROI frame facts must be a sequence")
            supplied = frames if len(value) == 1 and all(isinstance(item, Real) for item in frames) else frames[position] if len(frames) == len(value) else None
            if supplied is None or not isinstance(supplied, (list, tuple)):
                raise ValueError("Frame facts must align with ROI collection slots")
            if any(isinstance(frame, bool) or float(frame) != int(frame) for frame in supplied):
                raise ValueError("Frame indices must be integral")
            indices = tuple(int(frame) for frame in supplied)
        result.append(RegionOfInterest((coords[0], coords[1], coords[2] + 1, coords[3] + 1), image.image_id, str(position),
            source_path=source_path, collection_position=position, source_coordinates=coords,
            source_coordinate_convention="inclusive_maxima", source_frame_indices=indices,
            frame_provenance="source_derived" if derived else "source_supplied" if indices else None,
            frame_derivation_method="ROI_depth_derived" if derived else None,
            annotation_source=identifier(_mapped(row, columns, "annotation_source")), confidence=confidence,
            coordinate_frame_id=identifier(_mapped(row, columns, "coordinate_frame_id"))))
    return tuple(result)


def _signature(collection: tuple[RegionOfInterest, ...]) -> Any:
    return tuple((roi.coordinates, roi.source_frame_indices, roi.frame_provenance, roi.frame_derivation_method, roi.confidence, roi.annotation_source, roi.coordinate_frame_id) for roi in collection)


def _supplied(row: Mapping[str, Any], columns: Mapping[str, Optional[str]], semantic: str) -> bool:
    """Return whether the row carries the bound column, including an explicit null."""

    physical = columns.get(semantic)
    return physical is not None and physical in row


def _mapped(row: Mapping[str, Any], columns: Mapping[str, Optional[str]], semantic: str) -> Any:
    """Return the row's value for a semantic field, or None when unbound or missing."""

    return cell(row, columns.get(semantic))


def _distinct(values: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if not is_missing(value) and value not in result:
            result.append(value)
    return result


def _unknown(field: str) -> Any:
    return {"laterality": Laterality.UNKNOWN, "view_position": ViewPosition.UNKNOWN, "modality": ImageModality.UNKNOWN}.get(field)


def _literal(value: Any) -> Any:
    return ast.literal_eval(value) if isinstance(value, str) else None if is_missing(value) else value


def _parse_embed_path(path: Optional[str]) -> Optional[dict[str, str]]:
    if path is None:
        return None
    parts = PurePosixPath(path.replace("\\", "/")).parts
    if len(parts) < 5:
        return None
    cohort, patient, study, series, filename = parts[-5:]
    if not cohort.startswith("cohort") or not cohort[6:].isdigit() or not all((patient, study, series)) or not filename.lower().endswith(".dcm") or not filename[:-4]:
        return None
    return dict(patient_id=patient, study_instance_uid=study, series_instance_uid=series, source_sop_instance_uid=filename[:-4])


def _issue(issues: list[Issue], code: str, message: str, **context: Any) -> None:
    issues.append(Issue(code, message, context=context))
