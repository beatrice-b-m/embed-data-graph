"""Image-local regions of interest and intrinsic ROI geometry."""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, Type, TypeVar, Union, overload

from embed_data_graph.core.entity import MutableEntity, Reference


CoordinateBox = Tuple[float, float, float, float]
_RoiT = TypeVar("_RoiT", bound="RegionOfInterest")


@dataclass(frozen=True)
class Box:
    """Immutable half-open image geometry.

    A box keeps four numeric coordinates in ``[y_min, x_min, y_stop,
    x_stop]`` order.  Bounds and ordering are inspected by optional
    validation; construction preserves those raw facts.

    Attributes
    ----------
    y_min : float
        Top coordinate in pixels.
    x_min : float
        Left coordinate in pixels.
    y_stop : float
        Exclusive vertical stop in pixels.
    x_stop : float
        Exclusive horizontal stop in pixels.
    """

    y_min: float
    """Top coordinate in pixels."""
    x_min: float
    """Left coordinate in pixels."""
    y_stop: float
    """Exclusive vertical stop in pixels."""
    x_stop: float
    """Exclusive horizontal stop in pixels."""

    def __post_init__(self) -> None:
        for attribute, value in zip(
            ("y_min", "x_min", "y_stop", "x_stop"),
            _numeric_box((self.y_min, self.x_min, self.y_stop, self.x_stop)),
        ):
            object.__setattr__(self, attribute, value)

    def as_tuple(self) -> CoordinateBox:
        """Return (y_min, x_min, y_stop, x_stop) in pixels with exclusive stops."""

        return self.y_min, self.x_min, self.y_stop, self.x_stop


class RegionOfInterest(MutableEntity):
    """One mutable, image-local ROI.

    ``(image_id, roi_key)`` is the toolkit identity.  Source location fields
    are optional lookup aliases and do not participate in identity.

    Parameters
    ----------
    coordinates : Union[CoordinateBox, Box]
        Four numeric pixel coordinates (y_min, x_min, y_stop, x_stop), with
        exclusive stops. Numeric arity is checked; bounds/order require
        validate.
    image_id : str
        Explicit non-empty model image identifier, independent of source SOP
        identity.
    roi_key : str
        Explicit non-empty ROI identifier scoped to image_id; equal boxes can
        have distinct keys.
    source_path : Optional[str], optional
        Optional physical source location alias. Does not identify the clinical
        object. Default: None.
    collection_position : Optional[int], optional
        Optional zero-based position in a supplied source ROI collection.
        Default: None.
    annotation_source : Optional[str], optional
        Origin of the annotation, such as manual or a model label; None means
        unknown. Default: None.
    confidence : Optional[float], optional
        Optional numeric confidence; converted to float. validate checks the
        finite 0–1 range. Default: None.
    coordinate_frame_id : Optional[str], optional
        Caller-defined coordinate frame label; None means unspecified. Default:
        None.
    source_coordinates : Optional[CoordinateBox], optional
        Optional original four-coordinate box, retained separately from
        canonical geometry. Default: None.
    source_coordinate_convention : Optional[str], optional
        Label describing source coordinates; inclusive_maxima is used by the
        EMBED conversion. Default: None.
    source_frame_indices : Tuple[int, ...], optional
        Supplied zero-based frame indices in original order. Empty means no
        frame facts, not all frames. Default: ().
    frame_provenance : Optional[str], optional
        Optional description of the source of frame assignments. Default: None.
    frame_derivation_method : Optional[str], optional
        Optional method used to derive frame assignments; no depth is inferred
        here. Default: None.
    metadata : Optional[Mapping[str, Any]], optional
        Consumer metadata, shallow-copied into a mutable dict. Nested values
        remain shared. Default: None.

    Notes
    -----
    Geometry is stored as supplied; ordering, bounds and confidence range are
    checked by ``validate``. Changing ``image_id`` or ``roi_key`` of a
    registered ROI goes through its graph.

    Raises
    ------
    ValueError
        Wrong coordinate arity, blank image_id/roi_key or unparseable confidence.
    TypeError
        Coordinates are not iterable/numeric or confidence cannot become float."""

    coordinates: CoordinateBox
    """Four numeric pixel coordinates (y_min, x_min, y_stop, x_stop), with
    exclusive stops. Numeric arity is checked; bounds/order require validate.
    """
    image_id: str
    """Explicit non-empty model image identifier, independent of source SOP identity."""
    roi_key: str
    """Explicit non-empty ROI identifier scoped to image_id; equal boxes can have
    distinct keys.
    """
    source_path: Optional[str]
    """Optional physical source location alias. Does not identify the clinical
    object. Default: None.
    """
    collection_position: Optional[int]
    """Optional zero-based position in a supplied source ROI collection. Default: None."""
    annotation_source: Optional[str]
    """Origin of the annotation, such as manual or a model label; None means
    unknown. Default: None.
    """
    confidence: Optional[float]
    """Optional numeric confidence; converted to float. validate checks the finite
    0–1 range. Default: None.
    """
    coordinate_frame_id: Optional[str]
    """Caller-defined coordinate frame label; None means unspecified. Default: None."""
    source_coordinates: Optional[CoordinateBox]
    """Optional original four-coordinate box, retained separately from canonical
    geometry. Default: None.
    """
    source_coordinate_convention: Optional[str]
    """Label describing source coordinates; inclusive_maxima is used by the EMBED
    conversion. Default: None.
    """
    source_frame_indices: Tuple[int, ...]
    """Supplied zero-based frame indices in original order. Empty means no frame
    facts, not all frames. Default: ().
    """
    frame_provenance: Optional[str]
    """Optional description of the source of frame assignments. Default: None."""
    frame_derivation_method: Optional[str]
    """Optional method used to derive frame assignments; no depth is inferred here.
    Default: None.
    """
    metadata: Dict[str, Any]
    """Consumer metadata, shallow-copied into a mutable dict. Nested values remain
    shared. Default: None.
    """

    kind = "roi"
    __key_fields__ = ("image_id", "roi_key")
    _references = (Reference("image_id", "image"),)
    _alias_fields = frozenset({"source_path", "collection_position"})

    def __init__(
        self,
        coordinates: Union[CoordinateBox, Box],
        image_id: str,
        roi_key: str,
        *,
        source_path: Optional[str] = None,
        collection_position: Optional[int] = None,
        annotation_source: Optional[str] = None,
        confidence: Optional[float] = None,
        coordinate_frame_id: Optional[str] = None,
        source_coordinates: Optional[CoordinateBox] = None,
        source_coordinate_convention: Optional[str] = None,
        source_frame_indices: Tuple[int, ...] = (),
        frame_provenance: Optional[str] = None,
        frame_derivation_method: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__()
        self.coordinates = _numeric_box(coordinates)
        self.image_id = image_id
        self.roi_key = roi_key
        self.source_path = source_path
        self.collection_position = collection_position
        self.annotation_source = annotation_source
        self.confidence = confidence
        self.coordinate_frame_id = coordinate_frame_id
        self.source_coordinates = source_coordinates
        self.source_coordinate_convention = source_coordinate_convention
        self.source_frame_indices = source_frame_indices
        self.frame_provenance = frame_provenance
        self.frame_derivation_method = frame_derivation_method
        self.metadata = dict(metadata or {})

    def _coerce(self, name: str, value: Any) -> Any:
        if name == "image_id":
            _require_image_id(value)
        elif name == "roi_key":
            _require_roi_key(value)
        elif name == "coordinates":
            return _numeric_box(value)
        elif name == "source_coordinates" and value is not None:
            return _numeric_box(value)
        elif name == "source_frame_indices":
            return tuple(value or ())
        elif name == "confidence" and value is not None:
            return float(value)
        elif name == "metadata":
            return dict(value or {})
        return value

    def _source_aliases(self, overrides: Mapping[str, Any]) -> Iterable[Tuple[str, Any, bool]]:
        """Yield the ``(source_path, collection_position)`` lookup when both are set."""

        path = overrides.get("source_path", self.source_path)
        position = overrides.get("collection_position", self.collection_position)
        if path is not None and position is not None:
            yield "roi_source", (path, position), False

    @property
    def image(self) -> Optional[Any]:
        """The image with this ``image_id`` if registered, else None."""

        graph = self.graph
        return graph.image(self.image_id) if graph is not None else None

    @classmethod
    @overload
    def from_embed_coordinates(
        cls: Type[_RoiT], coordinates: CoordinateBox, *, image_id: str, roi_key: str,
        source_path: Optional[str] = None, collection_position: Optional[int] = None,
        annotation_source: Optional[str] = None, confidence: Optional[float] = None,
        coordinate_frame_id: Optional[str] = None,
        source_frame_indices: Tuple[int, ...] = (),
        frame_provenance: Optional[str] = None,
        frame_derivation_method: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> _RoiT: ...

    @classmethod
    @overload
    def from_embed_coordinates(
        cls: Type[_RoiT], coordinates: CoordinateBox, **metadata: Any,
    ) -> _RoiT: ...

    @classmethod
    def from_embed_coordinates(
        cls: Type[_RoiT],
        coordinates: CoordinateBox,
        **metadata: Any,
    ) -> _RoiT:
        """Construct an ROI from EMBED inclusive pixel maxima.

        Parameters
        ----------
        coordinates : tuple of four numbers
            Source (y_min, x_min, y_max, x_max). Adds 1 to each maximum to produce
            canonical exclusive stops; retains the source coordinates unchanged.
        image_id, roi_key : str
            Required non-empty identity keywords forwarded to the constructor.
        source_path, collection_position, annotation_source, confidence, coordinate_frame_id
            Optional constructor keywords with the same defaults and meanings.
        source_frame_indices, frame_provenance, frame_derivation_method, metadata
            Optional constructor keywords with the same defaults and meanings.
        **metadata : Any
            Additional keywords forwarded to cls for subclass compatibility. Do not
            pass source_coordinates or source_coordinate_convention: this method
            supplies those values and duplicate keywords raise TypeError.

        Returns
        -------
        RegionOfInterest
            New standalone instance of cls, with convention "inclusive_maxima".

        Raises
        ------
        ValueError
            Wrong coordinate arity or blank identifiers.
        TypeError
            Non-numeric coordinates, missing required identity, duplicate generated
            keywords or constructor-rejected options.

        Examples
        --------
        >>> from embed_data_graph import RegionOfInterest
        >>> roi = RegionOfInterest.from_embed_coordinates(
        ...     (0, 0, 9, 19), image_id="I1", roi_key="0")
        >>> roi.coordinates
        (0.0, 0.0, 10.0, 20.0)
        >>> roi.area
        200.0
        """

        y_min, x_min, y_max, x_max = _numeric_box(coordinates)
        return cls(
            coordinates=(y_min, x_min, y_max + 1.0, x_max + 1.0),
            source_coordinates=(y_min, x_min, y_max, x_max),
            source_coordinate_convention="inclusive_maxima",
            **metadata,
        )

    @property
    def frame_indices(self) -> Tuple[int, ...]:
        """Return supplied frame facts without inferring depth."""

        return self.source_frame_indices

    @property
    def identity(self) -> Tuple[str, str]:
        """Semantic identity used for equality of addresses, independent of Python object identity."""

        return self.image_id, self.roi_key

    @property
    def y_min(self) -> float:
        """Top coordinate in pixels in the declared image frame."""

        return _numeric_box(self.coordinates)[0]

    @property
    def x_min(self) -> float:
        """Left coordinate in pixels in the declared image frame."""

        return _numeric_box(self.coordinates)[1]

    @property
    def y_max(self) -> float:
        """Exclusive vertical stop in pixels, despite the historical max name."""

        return _numeric_box(self.coordinates)[2]

    @property
    def x_max(self) -> float:
        """Exclusive horizontal stop in pixels, despite the historical max name."""

        return _numeric_box(self.coordinates)[3]

    @property
    def height(self) -> float:
        """Vertical extent y_max - y_min in pixels; invalid ordering can make it negative."""

        return self.y_max - self.y_min

    @property
    def width(self) -> float:
        """Horizontal extent x_max - x_min in pixels; invalid ordering can make it negative."""

        return self.x_max - self.x_min

    @property
    def area(self) -> float:
        """Height times width in square pixels; geometry is not validated by this property."""

        return self.height * self.width

    @property
    def centroid(self) -> Tuple[float, float]:
        """Box center as (y, x) in pixel coordinates."""

        return (self.y_min + self.y_max) / 2.0, (self.x_min + self.x_max) / 2.0

    def resize(
        self: _RoiT,
        *,
        scale_y: float,
        scale_x: float,
        image_id: Optional[str] = None,
        roi_key: Optional[str] = None,
        coordinate_frame_id: Optional[str] = None,
    ) -> _RoiT:
        """Return a standalone shallow copy with transformed pixel geometry.

        Parameters
        ----------
        scale_y, scale_x : float
            Multipliers applied to vertical/horizontal coordinates.
        image_id, roi_key, coordinate_frame_id : str or None, optional
            Replacement identity/frame values. None (default) preserves each value.

        Returns
        -------
        RegionOfInterest
            Same concrete type, graph=None, transformed coordinates. Metadata and
            other mutable attributes remain shared; source coordinates/frame facts
            are retained unchanged. No clipping or quality validation is performed.

        Raises
        ------
        ValueError
            A replacement identity is blank, or a scale/offset cannot become float.
        TypeError
            Non-numeric scale or offset.
        """

        return self._geometry_copy(
            coordinates=(
                self.y_min * float(scale_y),
                self.x_min * float(scale_x),
                self.y_max * float(scale_y),
                self.x_max * float(scale_x),
            ),
            image_id=image_id,
            roi_key=roi_key,
            coordinate_frame_id=coordinate_frame_id,
        )

    def realign(
        self: _RoiT,
        *,
        offset_y: float = 0.0,
        offset_x: float = 0.0,
        scale_y: float = 1.0,
        scale_x: float = 1.0,
        image_id: Optional[str] = None,
        roi_key: Optional[str] = None,
        coordinate_frame_id: Optional[str] = None,
    ) -> _RoiT:
        """Return a standalone shallow copy with transformed pixel geometry.

        Parameters
        ----------
        scale_y, scale_x : float
            Multipliers applied to vertical/horizontal coordinates. Defaults are 1.0.
        offset_y, offset_x : float, optional
            Translation in destination pixels, applied after scaling; defaults 0.0.
        image_id, roi_key, coordinate_frame_id : str or None, optional
            Replacement identity/frame values. None (default) preserves each value.

        Returns
        -------
        RegionOfInterest
            Same concrete type, graph=None, transformed coordinates. Metadata and
            other mutable attributes remain shared; source coordinates/frame facts
            are retained unchanged. No clipping or quality validation is performed.

        Raises
        ------
        ValueError
            A replacement identity is blank, or a scale/offset cannot become float.
        TypeError
            Non-numeric scale or offset.
        """

        return self._geometry_copy(
            coordinates=(
                self.y_min * float(scale_y) + float(offset_y),
                self.x_min * float(scale_x) + float(offset_x),
                self.y_max * float(scale_y) + float(offset_y),
                self.x_max * float(scale_x) + float(offset_x),
            ),
            image_id=image_id,
            roi_key=roi_key,
            coordinate_frame_id=coordinate_frame_id,
        )

    def _geometry_copy(
        self: _RoiT,
        *,
        coordinates: CoordinateBox,
        image_id: Optional[str],
        roi_key: Optional[str],
        coordinate_frame_id: Optional[str],
    ) -> _RoiT:
        clone = copy.copy(self)
        object.__setattr__(clone, "_graph", None)
        object.__setattr__(clone, "coordinates", _numeric_box(coordinates))
        if image_id is not None:
            _require_image_id(image_id)
            object.__setattr__(clone, "image_id", image_id)
        if roi_key is not None:
            _require_roi_key(roi_key)
            object.__setattr__(clone, "roi_key", roi_key)
        if coordinate_frame_id is not None:
            object.__setattr__(clone, "coordinate_frame_id", coordinate_frame_id)
        return clone

    def intersection_area(self, other: "RegionOfInterest") -> float:
        """Return overlap with other in square pixels, clamping each non-overlapping axis to zero.

        Both ROIs must already use the same coordinate frame. This method neither
        checks frame IDs nor validates bounds/order; use valid geometry for ratios.
        """

        y_overlap = max(0.0, min(self.y_max, other.y_max) - max(self.y_min, other.y_min))
        x_overlap = max(0.0, min(self.x_max, other.x_max) - max(self.x_min, other.x_min))
        return y_overlap * x_overlap

    def iou(self, other: "RegionOfInterest") -> float:
        """Return intersection/union with other, or 0.0 when union is zero.

        Both ROIs must already use the same coordinate frame. This method neither
        checks frame IDs nor validates bounds/order; use valid geometry for ratios.
        """

        intersection = self.intersection_area(other)
        union = self.area + other.area - intersection
        return 0.0 if union == 0.0 else intersection / union

    def containment_ratio(self, container: "RegionOfInterest") -> float:
        """Return the fraction of this ROI covered by container, or 0.0 when this ROI has zero area.

        Both ROIs must already use the same coordinate frame. This method neither
        checks frame IDs nor validates bounds/order; use valid geometry for ratios.
        """

        if self.area == 0.0:
            return 0.0
        return self.intersection_area(container) / self.area

    def center_distance(self, other: "RegionOfInterest") -> float:
        """Return Euclidean distance between this centroid and other's in pixels.

        Both ROIs must already use the same coordinate frame. This method neither
        checks frame IDs nor validates bounds/order; use valid geometry for ratios.
        """

        self_y, self_x = self.centroid
        other_y, other_x = other.centroid
        return math.hypot(self_y - other_y, self_x - other_x)

    def _to_dict_data(self) -> Dict[str, Any]:
        return {
            "roi_key": self.roi_key,
            "image_id": self.image_id,
            "source_path": self.source_path,
            "collection_position": self.collection_position,
            "coordinates": list(_numeric_box(self.coordinates)),
            "annotation_source": self.annotation_source,
            "confidence": self.confidence,
            "coordinate_frame_id": self.coordinate_frame_id,
            "source_coordinates": (
                list(_numeric_box(self.source_coordinates))
                if self.source_coordinates is not None
                else None
            ),
            "source_coordinate_convention": self.source_coordinate_convention,
            "frame_indices": list(self.frame_indices),
            "frame_provenance": self.frame_provenance,
            "frame_derivation_method": self.frame_derivation_method,
            "metadata": dict(self.metadata),
        }



def _numeric_box(value: Union[CoordinateBox, Box, Any]) -> CoordinateBox:
    if isinstance(value, Box):
        values = value.as_tuple()
    else:
        try:
            values = tuple(value)
        except TypeError as exc:
            raise TypeError("ROI coordinates must be an iterable of four numbers") from exc
    if len(values) != 4:
        raise ValueError("ROI coordinates must contain four values")
    try:
        return tuple(float(item) for item in values)  # type: ignore[return-value]
    except (TypeError, ValueError) as exc:
        raise TypeError("ROI coordinates must contain numeric values") from exc


def _require_image_id(image_id: str) -> None:
    if not isinstance(image_id, str) or not image_id.strip():
        raise ValueError("image_id must be a non-empty string")


def _require_roi_key(roi_key: str) -> None:
    if not isinstance(roi_key, str) or not roi_key.strip():
        raise ValueError("roi_key must be an explicit non-empty string")
