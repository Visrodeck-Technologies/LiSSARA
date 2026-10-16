"""Line segment primitives and geometric queries.

This module provides operations on line segments defined by two endpoints.
All functions work with plain Point tuples (x, y).

Mathematical Reference:
- A line segment is the convex hull of two points: S(t) = (1-t)*p0 + t*p1 for t in [0, 1].
- The closest point on a segment to an external point is found by clamping the
  projection parameter to [0, 1].
"""

from __future__ import annotations
from typing import Tuple, Optional
import math

from .points import (
    Point,
    validate_point,
    lerp,
    distance,
    distance_squared,
    dot,
    cross,
    length_squared,
)


# Type alias for a segment (two endpoints)
Segment = Tuple[Point, Point]


def validate_segment(seg: Segment, name: str = "segment") -> Segment:
    """Validate a line segment.

    Args:
        seg: A sequence of two points.
        name: Optional name for error messages.

    Returns:
        A tuple of two validated Points.

    Raises:
        TypeError: If seg is not a sequence of two points.
    """
    if seg is None:
        raise TypeError(f"{name} cannot be None")
    try:
        p0, p1 = seg
    except (TypeError, ValueError):
        raise TypeError(f"{name} must be a sequence of two points, got {type(seg).__name__}")
    return (validate_point(p0, f"{name}[0]"), validate_point(p1, f"{name}[1]"))


def segment_length(seg: Segment) -> float:
    """Length of a line segment."""
    p0, p1 = seg
    return distance(p0, p1)


def segment_length_squared(seg: Segment) -> float:
    """Squared length of a line segment."""
    p0, p1 = seg
    return distance_squared(p0, p1)


def evaluate_segment(seg: Segment, t: float) -> Point:
    """Evaluate point on segment at parameter t.

    Args:
        seg: Segment (p0, p1).
        t: Parameter in [0, 1] for interpolation.

    Returns:
        Point on the segment.
    """
    p0, p1 = seg
    return lerp(p0, p1, t)


def segment_midpoint(seg: Segment) -> Point:
    """Midpoint of a segment."""
    p0, p1 = seg
    return ((p0[0] + p1[0]) * 0.5, (p0[1] + p1[1]) * 0.5)


def closest_point_on_segment(seg: Segment, point: Point) -> Tuple[Point, float]:
    """Find the closest point on a segment to an external point.

    Args:
        seg: Segment (p0, p1).
        point: External point.

    Returns:
        Tuple of (closest_point, parameter_t) where parameter_t in [0, 1]
        indicates the position along the segment.
    """
    p0, p1 = seg
    v = (p1[0] - p0[0], p1[1] - p0[1])
    w = (point[0] - p0[0], point[1] - p0[1])

    seg_len_sq = length_squared(v)
    if seg_len_sq == 0.0:
        # Degenerate segment (point)
        return p0, 0.0

    t = dot(w, v) / seg_len_sq
    # Clamp to segment
    if t <= 0.0:
        return p0, 0.0
    if t >= 1.0:
        return p1, 1.0
    return (p0[0] + t * v[0], p0[1] + t * v[1]), t


def distance_point_to_segment(point: Point, seg: Segment) -> float:
    """Distance from a point to a line segment.

    Args:
        point: Query point.
        seg: Segment (p0, p1).

    Returns:
        Minimum Euclidean distance from point to any point on the segment.
    """
    closest, _ = closest_point_on_segment(seg, point)
    return distance(point, closest)


def distance_point_to_segment_squared(point: Point, seg: Segment) -> float:
    """Squared distance from a point to a line segment."""
    closest, _ = closest_point_on_segment(seg, point)
    return distance_squared(point, closest)


def segment_intersects_segment(
    seg1: Segment, seg2: Segment, tol: float = 1e-12
) -> Tuple[bool, Optional[Point], Optional[float], Optional[float]]:
    """Check if two segments intersect and find intersection point.

    Uses the standard line intersection formula with parameter clamping.

    Args:
        seg1: First segment (p0, p1).
        seg2: Second segment (q0, q1).
        tol: Tolerance for parallel check.

    Returns:
        Tuple of (intersects, intersection_point, t1, t2) where:
        - intersects: True if segments intersect (including endpoints)
        - intersection_point: The intersection point if intersects, else None
        - t1: Parameter on seg1 (in [0, 1] if intersects)
        - t2: Parameter on seg2 (in [0, 1] if intersects)
    """
    p0, p1 = seg1
    q0, q1 = seg2

    r = (p1[0] - p0[0], p1[1] - p0[1])
    s = (q1[0] - q0[0], q1[1] - q0[1])

    rxs = cross(r, s)
    q_p = (q0[0] - p0[0], q0[1] - p0[1])

    if abs(rxs) < tol:
        # Parallel or collinear
        q_pxr = cross(q_p, r)
        if abs(q_pxr) < tol:
            # Collinear - check for overlap
            # This is a simplified check; full collinear overlap detection
            # would require projecting endpoints
            return False, None, None, None
        # Parallel non-intersecting
        return False, None, None, None

    t = cross(q_p, s) / rxs
    u = cross(q_p, r) / rxs

    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        ix = p0[0] + t * r[0]
        iy = p0[1] + t * r[1]
        return True, (ix, iy), t, u

    return False, None, None, None


def point_to_line_distance(point: Point, line_p0: Point, line_p1: Point) -> float:
    """Perpendicular distance from a point to an infinite line.

    Args:
        point: Query point.
        line_p0: First point on the line.
        line_p1: Second point on the line.

    Returns:
        Perpendicular distance.
    """
    v = (line_p1[0] - line_p0[0], line_p1[1] - line_p0[1])
    w = (point[0] - line_p0[0], point[1] - line_p0[1])

    v_len = length_squared(v)
    if v_len == 0.0:
        return distance(point, line_p0)

    # Cross product magnitude / length of v
    return abs(cross(v, w)) / math.sqrt(v_len)


def project_point_onto_line(point: Point, line_p0: Point, line_p1: Point) -> Point:
    """Project a point onto an infinite line.

    Args:
        point: Query point.
        line_p0: First point on the line.
        line_p1: Second point on the line.

    Returns:
        Projected point on the line.
    """
    v = (line_p1[0] - line_p0[0], line_p1[1] - line_p0[1])
    w = (point[0] - line_p0[0], point[1] - line_p0[1])

    v_len_sq = length_squared(v)
    if v_len_sq == 0.0:
        return line_p0

    t = dot(w, v) / v_len_sq
    return (line_p0[0] + t * v[0], line_p0[1] + t * v[1])


def segment_angle(seg: Segment) -> float:
    """Angle of segment direction vector in radians [-pi, pi].

    Args:
        seg: Segment (p0, p1).

    Returns:
        Angle of the vector p1 - p0.
    """
    p0, p1 = seg
    return math.atan2(p1[1] - p0[1], p1[0] - p0[0])


def offset_segment(seg: Segment, distance: float) -> Segment:
    """Offset a segment perpendicularly by a given distance.

    Args:
        seg: Segment (p0, p1).
        distance: Offset distance (positive = left side, negative = right side).

    Returns:
        New segment offset by distance.
    """
    p0, p1 = seg
    v = (p1[0] - p0[0], p1[1] - p0[1])
    v_len = math.hypot(v[0], v[1])
    if v_len == 0.0:
        return seg
    # Perpendicular unit vector (left side)
    nx = -v[1] / v_len
    ny = v[0] / v_len
    return (
        (p0[0] + distance * nx, p0[1] + distance * ny),
        (p1[0] + distance * nx, p1[1] + distance * ny),
    )