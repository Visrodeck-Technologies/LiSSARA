"""Quadratic Bézier curve representation and operations.

A quadratic Bézier curve is defined by three control points P0, P1, P2:
B(t) = (1-t)^2 * P0 + 2(1-t)t * P1 + t^2 * P2,  for t in [0, 1]

This can be expanded to polynomial form:
B(t) = a2*t^2 + a1*t + a0
where:
  a0 = P0
  a1 = 2(P1 - P0)
  a2 = P0 - 2P1 + P2

Mathematical Reference:
- Pomax, "A Primer on Bézier Curves": https://pomax.github.io/bezierinfo/
- Quadratic curves are a subset of cubic curves (degree elevation).
- They can exactly represent parabolic arcs and line segments.
"""

from __future__ import annotations
from typing import Tuple, Dict
import math

from .points import Point, validate_point, lerp


# Type aliases
QuadraticControlPoints = Tuple[Point, Point, Point]
QuadraticCoeffs = Dict[str, Dict[str, float]]


def validate_quadratic_control_points(
    p0: Point, p1: Point, p2: Point
) -> QuadraticControlPoints:
    """Validate three control points for a quadratic Bézier."""
    return (
        validate_point(p0, "p0"),
        validate_point(p1, "p1"),
        validate_point(p2, "p2"),
    )


def quadratic_coefficients(
    p0: Point, p1: Point, p2: Point
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Compute polynomial coefficients for a quadratic Bézier.

    Returns (x_coeffs, y_coeffs) where each is a dict with keys:
    - "a2": coefficient of t^2
    - "a1": coefficient of t^1
    - "a0": coefficient of t^0 (constant term)

    Mathematical derivation:
    B(t) = (1-t)^2 P0 + 2(1-t)t P1 + t^2 P2
         = (P0 - 2P1 + P2) t^2 + 2(P1 - P0) t + P0

    Args:
        p0, p1, p2: Control points.

    Returns:
        (x_coeffs, y_coeffs) dictionaries.
    """
    p0, p1, p2 = validate_quadratic_control_points(p0, p1, p2)

    a2x = p0[0] - 2.0 * p1[0] + p2[0]
    a1x = 2.0 * (p1[0] - p0[0])
    a0x = p0[0]

    a2y = p0[1] - 2.0 * p1[1] + p2[1]
    a1y = 2.0 * (p1[1] - p0[1])
    a0y = p0[1]

    return (
        {"a2": a2x, "a1": a1x, "a0": a0x},
        {"a2": a2y, "a1": a1y, "a0": a0y},
    )


def make_quadratic(p0: Point, p1: Point, p2: Point) -> Dict:
    """Create a quadratic Bézier curve object.

    Args:
        p0, p1, p2: Control points.

    Returns:
        Dictionary with:
        - "control_points": [(x0,y0), (x1,y1), (x2,y2)]
        - "x_coeffs": {"a2": ..., "a1": ..., "a0": ...}
        - "y_coeffs": {"a2": ..., "a1": ..., "a0": ...}
        - "degree": 2
    """
    p0, p1, p2 = validate_quadratic_control_points(p0, p1, p2)
    x_coeffs, y_coeffs = quadratic_coefficients(p0, p1, p2)

    return {
        "control_points": [p0, p1, p2],
        "x_coeffs": x_coeffs,
        "y_coeffs": y_coeffs,
        "degree": 2,
    }


def evaluate_quadratic(t: float, curve: Dict) -> Point:
    """Evaluate a quadratic Bézier curve at parameter t.

    Args:
        t: Parameter in [0, 1]. Values outside are extrapolated.
        curve: Dictionary from make_quadratic().

    Returns:
        Point (x, y) on the curve.
    """
    xc = curve["x_coeffs"]
    yc = curve["y_coeffs"]

    t2 = t * t
    x = xc["a2"] * t2 + xc["a1"] * t + xc["a0"]
    y = yc["a2"] * t2 + yc["a1"] * t + yc["a0"]

    return (float(x), float(y))


def evaluate_quadratic_coeffs(t: float, x_coeffs: Dict, y_coeffs: Dict) -> Point:
    """Evaluate using coefficient dicts directly (for performance)."""
    t2 = t * t
    x = x_coeffs["a2"] * t2 + x_coeffs["a1"] * t + x_coeffs["a0"]
    y = y_coeffs["a2"] * t2 + y_coeffs["a1"] * t + y_coeffs["a0"]
    return (float(x), float(y))


def quadratic_derivative(t: float, curve: Dict) -> Point:
    """First derivative (tangent vector) of quadratic Bézier at t.

    B'(t) = 2*(1-t)*(P1-P0) + 2*t*(P2-P1)
          = 2*a2*t + a1  (in polynomial form)

    Args:
        t: Parameter in [0, 1].
        curve: Dictionary from make_quadratic().

    Returns:
        Tangent vector (dx/dt, dy/dt) at t.
    """
    xc = curve["x_coeffs"]
    yc = curve["y_coeffs"]

    dx = 2.0 * xc["a2"] * t + xc["a1"]
    dy = 2.0 * yc["a2"] * t + yc["a1"]

    return (float(dx), float(dy))


def quadratic_second_derivative(curve: Dict) -> Point:
    """Second derivative (constant for quadratic Bézier).

    B''(t) = 2*a2

    Returns:
        Constant second derivative vector.
    """
    xc = curve["x_coeffs"]
    yc = curve["y_coeffs"]
    return (2.0 * xc["a2"], 2.0 * yc["a2"])


def quadratic_tangent_angle(t: float, curve: Dict) -> float:
    """Angle of the tangent vector at parameter t.

    Args:
        t: Parameter in [0, 1].
        curve: Quadratic Bézier curve.

    Returns:
        Angle in radians [-pi, pi].
    """
    dx, dy = quadratic_derivative(t, curve)
    return math.atan2(dy, dx)


def quadratic_curvature(t: float, curve: Dict) -> float:
    """Signed curvature of quadratic Bézier at parameter t.

    For a parametric curve (x(t), y(t)):
    k = (x'y'' - y'x'') / (x'^2 + y'^2)^(3/2)

    For quadratic Bézier, x'' and y'' are constant.

    Args:
        t: Parameter in [0, 1].
        curve: Quadratic Bézier curve.

    Returns:
        Signed curvature. Zero for straight lines.
    """
    dx, dy = quadratic_derivative(t, curve)
    ddx, ddy = quadratic_second_derivative(curve)

    cross_prod = dx * ddy - dy * ddx
    speed_sq = dx * dx + dy * dy

    if speed_sq == 0.0:
        return 0.0

    return cross_prod / (speed_sq ** 1.5)


def quadratic_arc_length(curve: Dict, n_samples: int = 32) -> float:
    """Approximate arc length using adaptive sampling.

    Args:
        curve: Quadratic Bézier curve.
        n_samples: Number of segments for numerical integration.

    Returns:
        Approximate arc length.
    """
    total = 0.0
    prev = evaluate_quadratic(0.0, curve)
    for i in range(1, n_samples + 1):
        t = i / n_samples
        curr = evaluate_quadratic(t, curve)
        total += math.hypot(curr[0] - prev[0], curr[1] - prev[1])
        prev = curr
    return total


def split_quadratic(curve: Dict, t: float) -> Tuple[Dict, Dict]:
    """Split a quadratic Bézier at parameter t using de Casteljau's algorithm.

    de Casteljau for quadratic:
    Q0 = lerp(P0, P1, t)
    Q1 = lerp(P1, P2, t)
    R0 = lerp(Q0, Q1, t)  # This is the point on the curve at t

    Left sub-curve:  P0, Q0, R0
    Right sub-curve: R0, Q1, P2

    Args:
        curve: Quadratic Bézier curve.
        t: Split parameter in (0, 1).

    Returns:
        Tuple of (left_curve, right_curve).

    Raises:
        ValueError: If t not in (0, 1).
    """
    if not 0.0 < t < 1.0:
        raise ValueError(f"Split parameter t must be in (0, 1), got {t}")

    p0, p1, p2 = curve["control_points"]

    q0 = lerp(p0, p1, t)
    q1 = lerp(p1, p2, t)
    r0 = lerp(q0, q1, t)

    left = make_quadratic(p0, q0, r0)
    right = make_quadratic(r0, q1, p2)

    return left, right


def quadratic_bounding_box(curve: Dict) -> Tuple[Point, Point]:
    """Compute tight axis-aligned bounding box of a quadratic Bézier.

    The extrema occur at t=0, t=1, and any critical points where
    the derivative is zero (if in [0, 1]).

    For quadratic B(t) = a2*t^2 + a1*t + a0:
    B'(t) = 2*a2*t + a1 = 0  =>  t = -a1 / (2*a2)  (if a2 != 0)

    Args:
        curve: Quadratic Bézier curve.

    Returns:
        ((min_x, min_y), (max_x, max_y))
    """
    xc = curve["x_coeffs"]
    yc = curve["y_coeffs"]

    # Endpoints
    candidates = [(xc["a0"], yc["a0"])]
    t1_x = xc["a2"] * 1.0 + xc["a1"] * 1.0 + xc["a0"]
    t1_y = yc["a2"] * 1.0 + yc["a1"] * 1.0 + yc["a0"]
    candidates.append((t1_x, t1_y))

    # Critical points where derivative is zero
    # x'(t) = 2*a2*t + a1 = 0
    if xc["a2"] != 0.0:
        tx = -xc["a1"] / (2.0 * xc["a2"])
        if 0.0 < tx < 1.0:
            x = xc["a2"] * tx * tx + xc["a1"] * tx + xc["a0"]
            y = yc["a2"] * tx * tx + yc["a1"] * tx + yc["a0"]
            candidates.append((x, y))

    if yc["a2"] != 0.0:
        ty = -yc["a1"] / (2.0 * yc["a2"])
        if 0.0 < ty < 1.0:
            x = xc["a2"] * ty * ty + xc["a1"] * ty + xc["a0"]
            y = yc["a2"] * ty * ty + yc["a1"] * ty + yc["a0"]
            candidates.append((x, y))

    min_x = min(p[0] for p in candidates)
    max_x = max(p[0] for p in candidates)
    min_y = min(p[1] for p in candidates)
    max_y = max(p[1] for p in candidates)

    return ((min_x, min_y), (max_x, max_y))


def quadratic_to_cubic(curve: Dict) -> Dict:
    """Degree elevation: convert quadratic to cubic Bézier.

    A quadratic B(t) = (1-t)^2 P0 + 2(1-t)t P1 + t^2 P2
    is exactly equivalent to a cubic with control points:
    Q0 = P0
    Q1 = (1/3)P0 + (2/3)P1
    Q2 = (2/3)P1 + (1/3)P2
    Q3 = P2

    Args:
        curve: Quadratic Bézier curve.

    Returns:
        Equivalent cubic Bézier curve dictionary.
    """
    p0, p1, p2 = curve["control_points"]

    q0 = p0
    q1 = (p0[0] * (1/3) + p1[0] * (2/3), p0[1] * (1/3) + p1[1] * (2/3))
    q2 = (p1[0] * (2/3) + p2[0] * (1/3), p1[1] * (2/3) + p2[1] * (1/3))
    q3 = p2

    # Import here to avoid circular import
    from .cubic import make_cubic
    return make_cubic(q0, q1, q2, q3)


def quadratic_from_three_points(p_start: Point, p_mid: Point, p_end: Point, t_mid: float = 0.5) -> Dict:
    """Construct a quadratic Bézier passing through three points.

    Given start, middle, and end points, and the parameter value t_mid
    at which the curve should pass through p_mid, compute the control point P1.

    B(t_mid) = (1-t_mid)^2 P0 + 2(1-t_mid)t_mid P1 + t_mid^2 P2 = p_mid

    Solving for P1:
    P1 = (p_mid - (1-t_mid)^2 P0 - t_mid^2 P2) / (2(1-t_mid)t_mid)

    Args:
        p_start: Start point (P0).
        p_mid: Point on curve at t=t_mid.
        p_end: End point (P2).
        t_mid: Parameter value for p_mid (default 0.5).

    Returns:
        Quadratic Bézier curve.

    Raises:
        ValueError: If t_mid is 0 or 1.
    """
    if t_mid <= 0.0 or t_mid >= 1.0:
        raise ValueError(f"t_mid must be in (0, 1), got {t_mid}")

    p0, p2 = p_start, p_end
    denom = 2.0 * (1.0 - t_mid) * t_mid

    p1x = (p_mid[0] - (1.0 - t_mid)**2 * p0[0] - t_mid**2 * p2[0]) / denom
    p1y = (p_mid[1] - (1.0 - t_mid)**2 * p0[1] - t_mid**2 * p2[1]) / denom

    return make_quadratic(p0, (p1x, p1y), p2)