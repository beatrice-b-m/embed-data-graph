"""Mutable image landmarks and immutable breast-coordinate facts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from embed_data_graph.core.anatomy import ContinuousAnatomicalPosition, DepthThird
from embed_data_graph.core.primitives import Laterality, ViewPosition


class LandmarkType(Enum):
    """Named image landmarks used by geometry consumers.

    Members
    -------
    NIPPLE='nipple', POSTERIOR_NIPPLE_LINE_START='posterior_nipple_line_start',
    POSTERIOR_NIPPLE_LINE_END='posterior_nipple_line_end', OTHER='other'.
    """

    NIPPLE = "nipple"
    POSTERIOR_NIPPLE_LINE_START = "posterior_nipple_line_start"
    POSTERIOR_NIPPLE_LINE_END = "posterior_nipple_line_end"
    OTHER = "other"


@dataclass(frozen=True)
class ImageLandmark:
    """One named point in an image's pixel frame.

    Coordinates and confidence are kept as supplied; their plausibility is a
    validation concern, so values outside the image or outside 0-1 remain
    representable. A landmark belongs to the image that stores it and does not
    repeat the image identifier. Use ``dataclasses.replace`` to change one.

    Attributes
    ----------
    y, x : float
        Vertical and horizontal pixel coordinates, converted to float.
    landmark_type : LandmarkType, optional
        Named point role. Default: LandmarkType.OTHER.
    confidence : float or None, optional
        Optional confidence; validate checks the finite 0-1 range. Default None.
    source : str or None, optional
        Optional label for where the point came from, such as an annotator or
        model. Default None.
    """

    y: float
    """Vertical pixel coordinate."""
    x: float
    """Horizontal pixel coordinate."""
    landmark_type: LandmarkType = LandmarkType.OTHER
    """Named point role."""
    confidence: Optional[float] = None
    """Optional confidence; validate checks the finite 0-1 range."""
    source: Optional[str] = None
    """Optional label for where the point came from."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "y", float(self.y))
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "landmark_type", LandmarkType(self.landmark_type))
        if self.confidence is not None:
            object.__setattr__(self, "confidence", float(self.confidence))

    @property
    def point(self) -> Tuple[float, float]:
        """Return ``(y, x)`` in pixels."""

        return self.y, self.x


@dataclass(frozen=True)
class BreastGeometry:
    """Coordinate-frame facts available for one breast image.

    This object stores observable geometry only. Matching and localization
    workflows consume these facts elsewhere.

    Attributes
    ----------
    image_id : str
        Explicit non-empty model image identifier, independent of source SOP
        identity.
    laterality : Laterality
        Breast side. Coercible values are normalized; unknown values become
        UNKNOWN where coercion is supported.
    view_position : ViewPosition
        Mammography projection; UNKNOWN when unavailable or unrecognized.
        Default: ViewPosition.UNKNOWN.
    image_shape : Optional[Tuple[int, int]]
        Optional (height, width) in pixels; supplying any other arity raises
        ValueError. Default: None.
    coordinate_frame_id : Optional[str]
        Caller-defined coordinate frame label; None means unspecified. Default:
        None.
    nipple : Optional[ImageLandmark]
        Optional nipple landmark in the declared pixel frame. Default: None.
    posterior_nipple_line : Optional[Tuple[ImageLandmark, ImageLandmark]]
        Optional pair of line endpoints in the same pixel frame. Default: None.
    """

    image_id: str
    """Explicit non-empty model image identifier, independent of source SOP identity."""
    laterality: Laterality
    """Breast side. Coercible values are normalized; unknown values become UNKNOWN
    where coercion is supported.
    """
    view_position: ViewPosition = ViewPosition.UNKNOWN
    """Mammography projection; UNKNOWN when unavailable or unrecognized. Default:
    ViewPosition.UNKNOWN.
    """
    image_shape: Optional[Tuple[int, int]] = None
    """Optional (height, width) in pixels; supplying any other arity raises
    ValueError. Default: None.
    """
    coordinate_frame_id: Optional[str] = None
    """Caller-defined coordinate frame label; None means unspecified. Default: None."""
    nipple: Optional[ImageLandmark] = None
    """Optional nipple landmark in the declared pixel frame."""
    posterior_nipple_line: Optional[Tuple[ImageLandmark, ImageLandmark]] = None
    """Optional pair of line endpoints in the same pixel frame."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "laterality", Laterality.coerce(self.laterality))
        object.__setattr__(
            self,
            "view_position",
            ViewPosition.coerce(self.view_position),
        )
        if self.image_shape is not None:
            shape = tuple(self.image_shape)
            if len(shape) != 2:
                raise ValueError("image_shape must contain height and width")
            object.__setattr__(self, "image_shape", shape)

    @property
    def has_nipple(self) -> bool:
        """True when a nipple landmark was supplied."""

        return self.nipple is not None

    @property
    def has_posterior_nipple_line(self) -> bool:
        """True when the two line endpoints were supplied; does not validate length."""

        return self.posterior_nipple_line is not None

    @property
    def frame_id(self) -> str:
        """Explicit coordinate_frame_id, or image_id when the explicit label is missing/empty."""

        return self.coordinate_frame_id or self.image_id

    @property
    def posterior_reference(self) -> Optional[ImageLandmark]:
        """Return the endpoint farthest from the nipple."""

        if self.posterior_nipple_line is None or self.nipple is None:
            return None
        start, end = self.posterior_nipple_line
        nipple = self.nipple
        return max(
            (start, end),
            key=lambda landmark: _distance(nipple.point, landmark.point),
        )

    @property
    def depth_vector(self) -> Optional[Tuple[float, float]]:
        """Return the nipple-to-posterior vector as ``(dy, dx)``."""

        if self.nipple is None:
            return None
        posterior = self.posterior_reference
        if posterior is None:
            return None
        dy = posterior.y - self.nipple.y
        dx = posterior.x - self.nipple.x
        if dy == 0.0 and dx == 0.0:
            return None
        return dy, dx

    @property
    def posterior_distance(self) -> Optional[float]:
        """Return distance from nipple to the posterior reference."""

        vector = self.depth_vector
        if vector is None:
            return None
        return math.hypot(vector[0], vector[1])

    def depth_value_for_point(self, point: Tuple[float, float]) -> Optional[float]:
        """Project point=(y, x) in pixels onto nipple-to-posterior depth.

        Returns a dimensionless float: 0 at the nipple and 2 at the posterior
        reference. Values are not clipped and can fall outside 0–2. Returns None
        when nipple/line geometry is absent or the depth vector has zero length.
        """

        if self.nipple is None:
            return None
        vector = self.depth_vector
        if vector is None:
            return None
        dy, dx = vector
        squared_length = dy * dy + dx * dx
        if squared_length == 0.0:
            return None
        point_dy = float(point[0]) - self.nipple.y
        point_dx = float(point[1]) - self.nipple.x
        fraction_to_posterior = (point_dy * dy + point_dx * dx) / squared_length
        return fraction_to_posterior * 2.0

    def depth_third_for_point(self, point: Tuple[float, float]) -> DepthThird:
        """Return anterior, middle, or posterior depth for a point."""

        depth_value = self.depth_value_for_point(point)
        if depth_value is None:
            return DepthThird.UNKNOWN
        if depth_value < 2 / 3:
            return DepthThird.ANTERIOR
        if depth_value < 4 / 3:
            return DepthThird.MIDDLE
        return DepthThird.POSTERIOR

    def continuous_position_for_point(
        self,
        point: Tuple[float, float],
    ) -> ContinuousAnatomicalPosition:
        """Project point=(y, x) in pixels into observable anatomical axes.

        Returns ContinuousAnatomicalPosition with depth on the unbounded nominal
        0–2 scale. The signed perpendicular displacement divided by posterior
        distance supplies ml for CC/XCCL or si for MLO/ML/LM. Other axes are None;
        missing/degenerate geometry leaves values None. Does not transform pixels
        or validate clinical orientation. coordinate_frame_id uses frame_id.
        """

        depth_value = self.depth_value_for_point(point)
        transverse_value = self._transverse_value_for_point(point)
        ml_value: Optional[float] = None
        si_value: Optional[float] = None

        if self.view_position in {ViewPosition.CC, ViewPosition.XCCL}:
            ml_value = transverse_value
        elif self.view_position in {ViewPosition.MLO, ViewPosition.ML, ViewPosition.LM}:
            si_value = transverse_value

        return ContinuousAnatomicalPosition(
            laterality=self.laterality,
            ml_value=ml_value,
            si_value=si_value,
            depth_value=depth_value,
            coordinate_frame_id=self.frame_id,
        )

    def _transverse_value_for_point(
        self,
        point: Tuple[float, float],
    ) -> Optional[float]:
        if self.nipple is None:
            return None
        vector = self.depth_vector
        distance = self.posterior_distance
        if vector is None or distance is None or distance == 0.0:
            return None
        dy, dx = vector
        point_dy = float(point[0]) - self.nipple.y
        point_dx = float(point[1]) - self.nipple.x
        signed_distance = (point_dy * -dx + point_dx * dy) / distance
        return signed_distance / distance


def _distance(
    first: Tuple[float, float],
    second: Tuple[float, float],
) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])
