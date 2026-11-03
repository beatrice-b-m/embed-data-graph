"""Mutable mammography image domain objects."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping, Optional, Set, Tuple, TYPE_CHECKING

from embed_data_graph.core.entity import MutableEntity, Reference
from embed_data_graph.core.graph import ensure_graph
from embed_data_graph.core.primitives import (
    DbtForm,
    ImageModality,
    Laterality,
    PatientOrientation,
    ViewModification,
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
    manufacturer : Optional[str], optional
        Acquisition device manufacturer as recorded; None means absent.
        Default: None.
    series_description : Optional[str], optional
        Free-text series description written by the modality; not a
        controlled vocabulary. Default: None.
    dicom_image_type : Optional[str], optional
        Serialized source DICOM ImageType value, kept as recorded. Default:
        None.
    view_modifier : Optional[str], optional
        Source view-modifier code meaning, such as a spot or magnification
        modifier; None means none is represented. Default: None.
    spot_magnification : Optional[bool], optional
        Derived spot-compression or magnification flag. Only True is a
        determination; None is not a negative one. Default: None.
    source_view_position : Optional[str], optional
        The view-position text as supplied, trimmed and uppercased, before
        coercion to ``view_position``; None when no view tag was supplied.
        Default: None.

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
    manufacturer: Optional[str]
    """Acquisition device manufacturer as recorded; None means absent."""
    series_description: Optional[str]
    """Free-text series description written by the modality."""
    dicom_image_type: Optional[str]
    """Serialized source DICOM ImageType value, as recorded."""
    view_modifier: Optional[str]
    """Source view-modifier code meaning; None means none is represented."""
    spot_magnification: Optional[bool]
    """Derived spot or magnification flag; None is not a negative determination."""
    source_view_position: Optional[str]
    """View-position text as supplied, trimmed and uppercased; None when absent."""

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
        manufacturer: Optional[str] = None,
        series_description: Optional[str] = None,
        dicom_image_type: Optional[str] = None,
        view_modifier: Optional[str] = None,
        spot_magnification: Optional[bool] = None,
        source_view_position: Optional[str] = None,
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
        self.manufacturer = manufacturer
        self.series_description = series_description
        self.dicom_image_type = dicom_image_type
        self.view_modifier = view_modifier
        self.spot_magnification = spot_magnification
        self.source_view_position = source_view_position

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
        elif name == "spot_magnification" and value is not None and not isinstance(value, bool):
            raise TypeError("spot_magnification must be a bool or None")
        elif name == "source_view_position" and value is not None:
            return str(value).strip().upper() or None
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

    @property
    def dbt_form(self) -> Optional[DbtForm]:
        """Projection or reconstruction for a DBT image; None for other images.

        Read from words in ``series_description`` (PROJ, PROJECTION; RECON,
        RECONSTRUCTION, RECONSTRUCTED, SLICES, VOLUME) and in the tokens of
        ``dicom_image_type`` (such as TOMO_PROJ). Wording differs by
        manufacturer, so the form is UNKNOWN when neither source names one,
        when one names both, or when the two disagree.

        Examples
        --------
        >>> MammogramImage("I", modality="3D", series_description="L CC Tomosynthesis Projection").dbt_form
        <DbtForm.PROJECTION: 'PROJECTION'>
        """

        if not self.is_dbt:
            return None
        forms = {form for form in (_dbt_form(self.series_description), _dbt_form(self.dicom_image_type))}
        forms.discard(DbtForm.UNKNOWN)
        return forms.pop() if len(forms) == 1 else DbtForm.UNKNOWN

    @property
    def view_modification(self) -> ViewModification:
        """Whether this image's view is a standard or a modified acquisition.

        MODIFIED when ``spot_magnification`` is True, a ``view_modifier`` is
        represented, or ``source_view_position`` carries words besides the base
        view and side (such as ``SPOT CC``). Otherwise UNKNOWN when the view is
        unknown and STANDARD when it is known. STANDARD means no modification is
        represented; the spot flag records only affirmative determinations.
        A modified view is never standard CC or MLO coverage.
        """

        modifier = (self.view_modifier or "").strip()
        if self.spot_magnification is True or modifier:
            return ViewModification.MODIFIED
        extra = [
            word
            for word in _words(self.source_view_position)
            if word not in _VIEW_WORDS and word not in _SIDE_WORDS and not _SIDE_VIEW.fullmatch(word)
        ]
        if extra:
            return ViewModification.MODIFIED
        if self.view_position is ViewPosition.UNKNOWN:
            return ViewModification.UNKNOWN
        return ViewModification.STANDARD

    @property
    def recovered_laterality(self) -> Laterality:
        """``laterality``, or when it is UNKNOWN the side parsed from ``series_description``.

        A value parsed from the series description is recovered, not recorded:
        it is used only when the laterality tag gave none, and a description
        naming no side, or both sides, leaves it UNKNOWN. ``laterality`` itself
        is never changed.
        """

        if self.laterality is not Laterality.UNKNOWN:
            return self.laterality
        return _series_side_and_view(self.series_description)[0]

    @property
    def recovered_view_position(self) -> ViewPosition:
        """``view_position``, or when no view tag was supplied the view parsed from ``series_description``.

        A populated view tag is never overridden, even when it did not coerce to
        a known view; a description naming no view, or several, leaves it
        UNKNOWN. ``view_position`` itself is never changed.
        """

        if self.view_position is not ViewPosition.UNKNOWN or self.source_view_position is not None:
            return self.view_position
        return _series_side_and_view(self.series_description)[1]

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
            "manufacturer": self.manufacturer,
            "series_description": self.series_description,
            "dicom_image_type": self.dicom_image_type,
            "view_modifier": self.view_modifier,
            "spot_magnification": self.spot_magnification,
            "source_view_position": self.source_view_position,
            "metadata": self.metadata,
        }


_VIEW_WORDS = frozenset(member.value for member in ViewPosition if member is not ViewPosition.UNKNOWN)
_SIDE_WORDS = {"L": Laterality.LEFT, "LT": Laterality.LEFT, "LEFT": Laterality.LEFT,
               "R": Laterality.RIGHT, "RT": Laterality.RIGHT, "RIGHT": Laterality.RIGHT}
_PROJECTION_WORDS = frozenset({"PROJ", "PROJECTION", "PROJECTIONS"})
_RECONSTRUCTION_WORDS = frozenset({"RECON", "RECONSTRUCTION", "RECONSTRUCTIONS", "RECONSTRUCTED", "SLICE", "SLICES", "VOLUME"})
_SIDE_VIEW = re.compile(r"(L|R)(XCCL|MLO|CC|ML|LM)")


def _words(text: Optional[str]) -> Tuple[str, ...]:
    return tuple(re.findall(r"[A-Z0-9]+", (text or "").upper()))


def _dbt_form(text: Optional[str]) -> DbtForm:
    words = set(_words(text))
    projection, reconstruction = bool(words & _PROJECTION_WORDS), bool(words & _RECONSTRUCTION_WORDS)
    if projection and not reconstruction:
        return DbtForm.PROJECTION
    if reconstruction and not projection:
        return DbtForm.RECONSTRUCTION
    return DbtForm.UNKNOWN


def _series_side_and_view(text: Optional[str]) -> Tuple[Laterality, ViewPosition]:
    """Best-effort side and view named by a series description; UNKNOWN unless exactly one."""

    sides: Set[Laterality] = set()
    views: Set[ViewPosition] = set()
    for word in _words(text):
        joined = _SIDE_VIEW.fullmatch(word)
        if word in _SIDE_WORDS:
            sides.add(_SIDE_WORDS[word])
        elif word in _VIEW_WORDS:
            views.add(ViewPosition(word))
        elif joined:
            sides.add(_SIDE_WORDS[joined.group(1)])
            views.add(ViewPosition(joined.group(2)))
    side = sides.pop() if len(sides) == 1 else Laterality.UNKNOWN
    view = views.pop() if len(views) == 1 else ViewPosition.UNKNOWN
    return side, view


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
