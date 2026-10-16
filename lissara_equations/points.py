"""Two-dimensional point primitives and operations.

This module provides the fundamental point type and operations used throughout
the equation library. All functions operate on plain Python tuples (x, y) for
interoperability and zero-dependency operation.

Mathematical Reference:
- Points are represented as ordered pairs (x, y) in Cartesian coordinates.
- Operations are defined in the standard Euclidean plane.
"""

from __future__ import annotations
from typing import Tuple, Sequence
import math


# Type alias for a 2D point
Point = Tuple[float, float]


def validate_point(point: Point, name: str = "point") -> Point:
    """Validate and normalize a 2D point.

    Args:
        point: A sequence of two numeric values (x, y).
        name: Optional name for error messages.

    Returns:
        A tuple of two floats (x, y).

    Raises:
        TypeError: If point is not a sequence of length 2.
        ValueError: If coordinates cannot be converted to float.
    """
    if point is None:
        raise TypeError(f"{name} cannot be None")
    try:
        x, y = point
    except (TypeError, ValueError):
        raise TypeError(f"{name} must be a sequence of two numeric values, got {type(point).__name__}")
    try:
        return (float(x), float(y))
    except (TypeError, ValueError) as e:
        raise ValueError(f"{name} coordinates must be numeric: {e}")


def is_finite(point: Point) -> bool:
    """Check if a point has finite coordinates.

    Args:
        point: A 2D point (x, y).

    Returns:
        True if both coordinates are finite, False otherwise.
    """
    x, y = point
    return math.isfinite(x) and math.isfinite(y)


def point_equal(p1: Point, p2: Point, tol: float = 1e-12) -> bool:
    """Check if two points are equal within tolerance.

    Args:
        p1: First point.
        p2: Second point.
        tol: Absolute tolerance for coordinate comparison.

    Returns:
        True if |p1.x - p2.x| <= tol and |p1.y - p2.y| <= tol.
    """
    return abs(p1[0] - p2[0]) <= tol and abs(p1[1] - p2[1]) <= tol


def distance(p1: Point, p2: Point) -> float:
    """Euclidean distance between two points.

    Args:
        p1: First point (x1, y1).
        p2: Second point (x2, y2).

    Returns:
        sqrt((x2-x1)^2 + (y2-y1)^2)
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return math.hypot(dx, dy)


def distance_squared(p1: Point, p2: Point) -> float:
    """Squared Euclidean distance between two points.

    Avoids the sqrt operation; useful for comparisons.

    Args:
        p1: First point (x1, y1).
        p2: Second point (x2, y2).

    Returns:
        (x2-x1)^2 + (y2-y1)^2
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return dx * dx + dy * dy


def midpoint(p1: Point, p2: Point) -> Point:
    """Midpoint of the line segment between two points.

    Args:
        p1: First point.
        p2: Second point.

    Returns:
        ((x1+x2)/2, (y1+y2)/2)
    """
    return ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)


def lerp(p0: Point, p1: Point, t: float) -> Point:
    """Linear interpolation between two points.

    Computes (1-t)*p0 + t*p1.

    Args:
        p0: Start point (t=0).
        p1: End point (t=1).
        t: Interpolation parameter. Clamped to [0, 1] if outside range.

    Returns:
        Interpolated point.
    """
    # Clamp t to [0, 1] for robustness
    if t <= 0.0:
        return p0
    if t >= 1.0:
        return p1
    u = 1.0 - t
    return (u * p0[0] + t * p1[0], u * p0[1] + t * p1[1])


def lerp_unclamped(p0: Point, p1: Point, t: float) -> Point:
    """Linear interpolation without clamping t.

    Useful for extrapolation or when t is guaranteed to be in [0, 1].

    Args:
        p0: Start point.
        p1: End point.
        t: Interpolation parameter (can be outside [0, 1]).

    Returns:
        Interpolated point.
    """
    u = 1.0 - t
    return (u * p0[0] + t * p1[0], u * p0[1] + t * p1[1])


def point_add(p1: Point, p2: Point) -> Point:
    """Vector addition of two points."""
    return (p1[0] + p2[0], p1[1] + p2[1])


def point_sub(p1: Point, p2: Point) -> Point:
    """Vector subtraction: p1 - p2."""
    return (p1[0] - p2[0], p1[1] - p2[1])


def point_scale(p: Point, s: float) -> Point:
    """Scalar multiplication: p * s."""
    return (p[0] * s, p[1] * s)


def point_neg(p: Point) -> Point:
    """Negation: -p."""
    return (-p[0], -p[1])


def dot(p1: Point, p2: Point) -> float:
    """Dot product of two points treated as vectors."""
    return p1[0] * p2[0] + p1[1] * p2[1]


def cross(p1: Point, p2: Point) -> float:
    """2D cross product (scalar): p1.x * p2.y - p1.y * p2.x."""
    return p1[0] * p2[1] - p1[1] * p2[0]


def length(p: Point) -> float:
    """Length (magnitude) of a point treated as a vector."""
    return math.hypot(p[0], p[1])


def length_squared(p: Point) -> float:
    """Squared length of a point treated as a vector."""
    return p[0] * p[0] + p[1] * p[1]


def normalize(p: Point) -> Point:
    """Normalize a point to unit length.

    Args:
        p: Input point.

    Returns:
        Unit vector in the same direction, or (0, 0) if input is zero.
    """
    l = length(p)
    if l == 0.0:
        return (0.0, 0.0)
    return (p[0] / l, p[1] / l)


def perpendicular(p: Point) -> Point:
    """Perpendicular vector (rotated 90 degrees CCW): (-y, x)."""
    return (-p[1], p[0])


def perpendicular_cw(p: Point) -> Point:
    """Perpendicular vector (rotated 90 degrees CW): (y, -x)."""
    return (p[1], -p[0])


def project(p: Point, onto: Point) -> Point:
    """Project point p onto the line spanned by 'onto'.

    Args:
        p: Vector to project.
        onto: Non-zero vector defining the line direction.

    Returns:
        Projection of p onto 'onto'.
    """
    onto_len_sq = length_squared(onto)
    if onto_len_sq == 0.0:
        return (0.0, 0.0)
    t = dot(p, onto) / onto_len_sq
    return point_scale(onto, t)


def angle_between(p1: Point, p2: Point) -> float:
    """Signed angle from p1 to p2 in radians, in [-pi, pi].

    Args:
        p1: First vector.
        p2: Second vector.

    Returns:
        Angle in radians. Positive means p2 is CCW from p1.
    """
    return math.atan2(cross(p1, p2), dot(p1, p2))


def polar(r: float, theta: float) -> Point:
    """Convert polar coordinates to Cartesian point.

    Args:
        r: Radius (non-negative).
        theta: Angle in radians.

    Returns:
        (r*cos(theta), r*sin(theta))
    """
    return (r * math.cos(theta), r * math.sin(theta))


def bounding_box(points: Sequence[Point]) -> Tuple[Point, Point]:
    """Compute axis-aligned bounding box of a point set.

    Args:
        points: Sequence of points.

    Returns:
        ((min_x, min_y), (max_x, max_y))

    Raises:
        ValueError: If points sequence is empty.
    """
    if not points:
        raise ValueError("Cannot compute bounding box of empty point sequence")
    it = iter(points)
    first = next(it)
    min_x = max_x = first[0]
    min_y = max_y = first[1]
    for x, y in it:
        if x < min_x:
            min_x = x
        elif x > max_x:
            max_x = x
        if y < min_y:
            min_y = y
        elif y > max_y:
            max_y = y
    return ((min_x, min_y), (max_x, max_y))


def centroid(points: Sequence[Point]) -> Point:
    """Compute centroid (arithmetic mean) of a point set.

    Args:
        points: Sequence of points.

    Returns:
        (mean_x, mean_y)

    Raises:
        ValueError: If points sequence is empty.
    """
    if not points:
        raise ValueError("Cannot compute centroid of empty point sequence")
    n = len(points)
    sum_x = sum(p[0] for p in points)
    sum_y = sum(p[1] for p in points)
    return (sum_x / n, sum_y / n)