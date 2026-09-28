"""Mutable mammography image domain objects."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Set, Tuple, TYPE_CHECKING

from embed_data_graph.core.entity import MutableEntity, Reference
from embed_data_graph.core.graph import ensure_graph
from embed_data_graph.core.primitives import (
    ImageModality,
    Laterality,
    PatientOrientation,
    ViewPosition,
)
from embed_data_graph.imaging.landmarks import BreastGeometry, ImageLandmark

if TYPE_CHECKING:
    from embed_data_graph.imaging.rois import RegionOfInterest


class MammogramImage(MutableEntity):
    """Mutable metadata for one mammography image.

    ``image_id`` is the toolkit identity.  Original source identity and
    source locations are optional aliases, and derivative identity is explicit
    through ``derived_from``.  No source path parsing occurs in this class.

    Parameters
    ----------
    image_id : str
        Explicit non-empty model image identifier, independent of source SOP
        identity.
    laterality : Laterality, optional
        Breast side. Coercible values are normalized; unknown values become
        UNKNOWN where coercion is supported. Default: Laterality.UNKNOWN.
    view_position : ViewPosition, optional
        Mammography projection; UNKNOWN when unavailable or unrecognized.
        Default: ViewPosition.UNKNOWN.
    source_paths : Optional[Iterable[str]], optional
        Location aliases, copied into a set. No files are opened; ordering is
        not meaningful. Default: None.
    modality : ImageModality, optional
        Acquisition/derived image modality; UNKNOWN when unavailable or
        unrecognized. Default: ImageModality.UNKNOWN.
    source_sop_instance_uid : Optional[str], optional
        Original DICOM SOP identity; independent of model image_id. None means
        unknown. Default: None.
    derived_from : Optional[Any], optional
        Explicit original-image reference for a derivative; None denotes an
        original. Default: None.
    source_modality : Optional[str], optional
        Unnormalized source modality label; None means absent. Default: None.
    derived_image_type : Optional[str], optional
        Source description of derived image type; None means absent. Default:
        None.
    height : Optional[int], optional
        Image height in pixels; None means unknown. No pixel buffer is
        allocated. Default: None.
    width : Optional[int], optional
        Image width in pixels; None means unknown. No pixel buffer is allocated.
        Default: None.
    frame_count : Optional[int], optional
        Reported number of frames, normally for DBT; None means unknown.
        Default: None.
    accession_number : Optional[str], optional
        Non-empty exam accession identifying the clinical examination. Default:
        None.
    patient_id : Optional[str], optional
        Patient identifier. Non-empty text; source patient claims and assigned
        exam ownership are separate facts. Default: None.
    study_instance_uid : Optional[str], optional
        DICOM study identifier; None means absent. Default: None.
    series_instance_uid : Optional[str], optional
        DICOM series identifier; None means absent. Default: None.
    patient_orientation : Optional[PatientOrientation], optional
        DICOM row/column orientation; None means absent. Default: None.
    coordinate_frame_id : Optional[str], optional
        Caller-defined coordinate frame label; None means unspecified. Default:
        None.
    landmarks : Iterable[ImageLandmark], optional
        Initial landmarks in this image's pixel frame. Default: ().
    metadata : Optional[Mapping[str, Any]], optional
        Consumer metadata, shallow-copied into a mutable dict. Nested values
        remain shared. Default: None.

    Notes
    -----
    ``rois`` are resolved by the owning graph from the ROIs' ``image_id``; an
    image without a graph has none. Only original images (``derived_from`` is
    None) are indexed by source SOP UID and path. No pixels are loaded.

    Raises
    ------
    ValueError
        Blank image_id, incompatible ROI identity or invalid orientation arity.
    TypeError
        A supplied landmark has an unsupported type."""

    image_id: str
    """Explicit non-empty model image identifier, independent of source SOP identity."""
    laterality: Laterality
    """Breast side. Coercible values are normalized; unknown values become UNKNOWN
    where coercion is supported. Default: Laterality.UNKNOWN.
    """
    view_position: ViewPosition
    """Mammography projection; UNKNOWN when unavailable or unrecognized. Default:
    ViewPosition.UNKNOWN.
    """
    source_paths: Set[str]
    """Location aliases, copied into a set. No files are opened; ordering is not
    meaningful. Default: None.
    """
    modality: ImageModality
    """Acquisition/derived image modality; UNKNOWN when unavailable or
    unrecognized. Default: ImageModality.UNKNOWN.
    """
    source_sop_instance_uid: Optional[str]
    """Original DICOM SOP identity; independent of model image_id. None means
    unknown. Default: None.
    """
    derived_from: Optional[Any]
    """Explicit original-image reference for a derivative; None denotes an
    original. Default: None.
    """
    source_modality: Optional[str]
    """Unnormalized source modality label; None means absent. Default: None."""
    derived_image_type: Optional[str]
    """Source description of derived image type; None means absent. Default: None."""
    height: Optional[int]
    """Image height in pixels; None means unknown. No pixel buffer is allocated. Default: None."""
    width: Optional[int]
    """Image width in pixels; None means unknown. No pixel buffer is allocated. Default: None."""
    frame_count: Optional[int]
    """Reported number of frames, normally for DBT; None means unknown. Default: None."""
    accession_number: Optional[str]
    """Non-empty exam accession identifying the clinical examination. Default: None."""
    patient_id: Optional[str]
    """Patient identifier. Non-empty text; source patient claims and assigned exam
    ownership are separate facts. Default: None.
    """
    study_instance_uid: Optional[str]
    """DICOM study identifier; None means absent. Default: None."""
    series_instance_uid: Optional[str]
    """DICOM series identifier; None means absent. Default: None."""
    patient_orientation: Optional[PatientOrientation]
    """DICOM row/column orientation; None means absent. Default: None."""
    coordinate_frame_id: Optional[str]
    """Caller-defined coordinate frame label; None means unspecified. Default: None."""
    landmarks: Tuple[ImageLandmark, ...]
    """Named points in this image's pixel frame."""
    metadata: Dict[str, Any]
    """Consumer metadata, shallow-copied into a mutable dict. Nested values remain
    shared. Default: None.
    """

    kind = "image"
    __key_fields__ = ("image_id",)
    _references = (Reference("accession_number", "exam"),)
    _alias_fields = frozenset({"source_sop_instance_uid", "source_paths", "derived_from"})

    def __init__(
        self,
        image_id: str,
        laterality: Laterality = Laterality.UNKNOWN,
        view_position: ViewPosition = ViewPosition.UNKNOWN,
        source_paths: Optional[Iterable[str]] = None,
        *,
        modality: ImageModality = ImageModality.UNKNOWN,
        source_sop_instance_uid: Optional[str] = None,
        derived_from: Optional[Any] = None,
        source_modality: Optional[str] = None,
        derived_image_type: Optional[str] = None,
        height: Optional[int] = None,
        width: Optional[int] = None,
        frame_count: Optional[int] = None,
        accession_number: Optional[str] = None,
        patient_id: Optional[str] = None,
        study_instance_uid: Optional[str] = None,
        series_instance_uid: Optional[str] = None,
        patient_orientation: Optional[PatientOrientation] = None,
        coordinate_frame_id: Optional[str] = None,
        landmarks: Iterable[ImageLandmark] = (),
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__()
        self.image_id = image_id
        self.laterality = laterality
        self.view_position = view_position
        self.modality = modality
        self.source_sop_instance_uid = source_sop_instance_uid
        self.source_paths = _source_path_set(source_paths)
        self.derived_from = derived_from
        self.source_modality = source_modality
        self.derived_image_type = derived_image_type
        self.height = height
        self.width = width
        self.frame_count = frame_count
        self.accession_number = accession_number
        self.patient_id = patient_id
        self.study_instance_uid = study_instance_uid
        self.series_instance_uid = series_instance_uid
        self.patient_orientation = patient_orientation
        self.coordinate_frame_id = coordinate_frame_id
        self.landmarks = tuple(landmarks)
        self.metadata = dict(metadata or {})

    def _coerce(self, name: str, value: Any) -> Any:
        if name == "image_id":
            _require_image_id(value)
        elif name == "laterality":
            return Laterality.coerce(value)
        elif name == "view_position":
            return ViewPosition.coerce(value)
        elif name == "modality":
            return ImageModality.coerce(value)
        elif name == "patient_orientation" and value is not None:
            return PatientOrientation.coerce(value)
        elif name == "source_paths":
            return _source_path_set(value)
        elif name == "landmarks":
            landmarks = tuple(value or ())
            if any(not isinstance(item, ImageLandmark) for item in landmarks):
                raise TypeError("landmarks must be ImageLandmark values")
            return landmarks
        elif name == "metadata":
            return dict(value or {})
        return value

    def _source_aliases(self, overrides: Mapping[str, Any]) -> Iterable[Tuple[str, Any, bool]]:
        """Yield ``(index, alias, unique)`` lookups for an original image."""

        def value(name: str) -> Any:
            return overrides.get(name, getattr(self, name))

        if value("derived_from") is not None:
            return
        uid = value("source_sop_instance_uid")
        if uid:
            yield "sop", uid, True
        for path in value("source_paths"):
            yield "path", path, False

    @property
    def identity(self) -> str:
        """Return ``image_id``."""

        return self.image_id

    @property
    def source_path(self) -> Optional[str]:
        """The lexicographically first source path, or None."""

        return min(self.source_paths) if self.source_paths else None

    @property
    def exam(self) -> Optional[Any]:
        """The exam with this accession if registered, else None."""

        graph = self.graph
        return graph.exam(self.accession_number) if graph is not None and self.accession_number else None

    @property
    def rois(self) -> Tuple["RegionOfInterest", ...]:
        """Regions of interest on this image."""

        graph = self.graph
        return graph.children(self, "roi") if graph is not None else ()

    def add_landmark(self, landmark: ImageLandmark) -> ImageLandmark:
        """Append a landmark in this image's pixel frame and return it."""

        self.landmarks = (*self.landmarks, landmark)
        return landmark

    def add_roi(self, roi: "RegionOfInterest") -> "RegionOfInterest":
        """Attach an ROI with this image's ``image_id`` and return it.

        Raises
        ------
        ValueError
            The ROI names another image, or its key is already taken.
        """

        return ensure_graph(self).attach(self, roi)

    @property
    def image_shape(self) -> Optional[Tuple[int, int]]:
        """(height, width) in pixels, or None unless both dimensions are supplied."""

        if self.height is None or self.width is None:
            return None
        return self.height, self.width

    @property
    def is_dbt(self) -> bool:
        """True exactly when modality is ImageModality.DBT; no inference from frame count."""

        return self.modality is ImageModality.DBT

    def breast_geometry(
        self,
        *,
        nipple: Optional[ImageLandmark] = None,
        posterior_nipple_line: Optional[Tuple[ImageLandmark, ImageLandmark]] = None,
    ) -> BreastGeometry:
        """Build breast-coordinate facts from explicitly supplied landmarks.

        Parameters
        ----------
        nipple : ImageLandmark or None, optional
            Nipple point in this image's pixel frame; None means unavailable.
        posterior_nipple_line : tuple of two ImageLandmark or None, optional
            Line endpoints in this pixel frame; None means unavailable. The endpoint
            farthest from nipple supplies the posterior reference.

        Returns
        -------
        BreastGeometry
            Frozen geometry container holding the supplied landmarks. Does not
            search self.landmarks or infer missing geometry.
        """

        return BreastGeometry(
            image_id=self.image_id,
            laterality=self.laterality,
            view_position=self.view_position,
            image_shape=self.image_shape,
            coordinate_frame_id=self.coordinate_frame_id,
            nipple=nipple,
            posterior_nipple_line=posterior_nipple_line,
        )

    def _to_dict_data(self) -> Dict[str, Any]:
        return {
            "image_id": self.image_id,
            "accession_number": self.accession_number,
            "patient_id": self.patient_id,
            "source_sop_instance_uid": self.source_sop_instance_uid,
            "source_paths": self.source_paths,
            "derived_from": self.derived_from,
            "laterality": self.laterality,
            "view_position": self.view_position,
            "modality": self.modality,
            "source_modality": self.source_modality,
            "derived_image_type": self.derived_image_type,
            "height": self.height,
            "width": self.width,
            "frame_count": self.frame_count,
            "study_instance_uid": self.study_instance_uid,
            "series_instance_uid": self.series_instance_uid,
            "patient_orientation": (
                list(self.patient_orientation.as_tuple()) if self.patient_orientation is not None else None
            ),
            "coordinate_frame_id": self.coordinate_frame_id,
            "landmarks": self.landmarks,
            "metadata": self.metadata,
        }


def _require_image_id(image_id: str) -> None:
    if not isinstance(image_id, str) or not image_id.strip():
        raise ValueError("image_id must be a non-empty string")


def _source_path_set(paths: Optional[Iterable[str]]) -> Set[str]:
    if paths is None:
        return set()
    if isinstance(paths, str):
        return {paths}
    result = set(paths)
    if any(not isinstance(path, str) for path in result):
        raise TypeError("source_paths must contain strings")
    return result
