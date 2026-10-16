"""Cubic Bézier curve representation and operations.

A cubic Bézier curve is defined by four control points P0, P1, P2, P3:
B(t) = (1-t)^3 P0 + 3(1-t)^2 t P1 + 3(1-t) t^2 P2 + t^3 P3,  for t in [0, 1]

Expanded to polynomial form:
B(t) = a3*t^3 + a2*t^2 + a1*t + a0
where:
  a0 = P0
  a1 = 3(P1 - P0)
  a2 = 3(P0 - 2P1 + P2)
  a3 = -P0 + 3P1 - 3P2 + P3

Mathematical Reference:
- Pomax, "A Primer on Bézier Curves": https://pomax.github.io/bezierinfo/
- The coefficient form matches the existing Lissara MathScene representation,
  ensuring backward compatibility with serialized scenes and the SVG exporter.

Implementation note:
- The dictionary returned by make_cubic()/bezier_control_points() uses keys
  "control_points", "x_coeffs" and "y_coeffs". This is the canonical Lissara
  curve record consumed by lissara_engine.PathRecord and persisted in
  MathScene JSON. Do not rename these keys without a migration.
"""

from __future__ import annotations
from typing import Tuple, Dict
import math

from .points import (
    Point,
    validate_point,
    lerp,
    distance_squared,
    cross,
)


# Type aliases
CubicControlPoints = Tuple[Point, Point, Point, Point]
CubicCoeffs = Dict[str, Dict[str, float]]
CubicCurve = Dict


def _to_float(val) -> float:
    """Convert a value to float, tolerating numpy scalars if present.

    Kept for backward compatibility with callers that previously used a local
    helper of the same name.
    """
    import numbers
    if isinstance(val, numbers.Number):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def validate_control_points(
    p0: Point, p1: Point, p2: Point, p3: Point
) -> CubicControlPoints:
    """Validate four control points for a cubic Bézier."""
    return (
        validate_point(p0, "p0"),
        validate_point(p1, "p1"),
        validate_point(p2, "p2"),
        validate_point(p3, "p3"),
    )


def cubic_coefficients(
    p0: Point, p1: Point, p2: Point, p3: Point
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Compute polynomial coefficients (x_coeffs, y_coeffs).

    Mathematical derivation of the power-basis coefficients:
      a0 = P0
      a1 = 3(P1 - P0)
      a2 = 3(P0 - 2P1 + P2)
      a3 = -P0 + 3P1 - 3P2 + P3

    The existing Lissara code stored these in the expanded Bernstein-to-power
    form directly; the identities are algebraically identical.

    Returns:
        (x_coeffs, y_coeffs). ``x_coeffs`` uses keys "a3", "a2", "a1", "a0";
        ``y_coeffs`` uses keys "b3", "b2", "b1", "b0". The asymmetric key
        names preserve the historical Lissara serialization format, which the
        SVG exporter and downstream consumers read directly.
    """
    p0, p1, p2, p3 = validate_control_points(p0, p1, p2, p3)

    a3x = -p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]
    a2x = 3.0 * p0[0] - 6.0 * p1[0] + 3.0 * p2[0]
    a1x = -3.0 * p0[0] + 3.0 * p1[0]
    a0x = p0[0]

    a3y = -p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]
    a2y = 3.0 * p0[1] - 6.0 * p1[1] + 3.0 * p2[1]
    a1y = -3.0 * p0[1] + 3.0 * p1[1]
    a0y = p0[1]

    x_coeffs = {"a3": _to_float(a3x), "a2": _to_float(a2x),
                "a1": _to_float(a1x), "a0": _to_float(a0x)}
    y_coeffs = {"b3": _to_float(a3y), "b2": _to_float(a2y),
                "b1": _to_float(a1y), "b0": _to_float(a0y)}
    return x_coeffs, y_coeffs


def make_cubic(p0: Point, p1: Point, p2: Point, p3: Point) -> CubicCurve:
    """Create a canonical cubic Bézier curve record.

    Returns a dictionary with the stable Lissara schema:
        {
            "control_points": [(x0,y0), (x1,y1), (x2,y2), (x3,y3)],
            "x_coeffs": {"a3": f, "a2": f, "a1": f, "a0": f},
            "y_coeffs": {"a3": f, "a2": f, "a1": f, "a0": f},
        }
    """
    p0, p1, p2, p3 = validate_control_points(p0, p1, p2, p3)
    x_coeffs, y_coeffs = cubic_coefficients(p0, p1, p2, p3)
    return {
        "control_points": [p0, p1, p2, p3],
        "x_coeffs": x_coeffs,
        "y_coeffs": y_coeffs,
    }


def bezier_control_points(p0, p1, p2, p3) -> CubicCurve:
    """Backward-compatible alias for make_cubic().

    Preserved because existing modules import ``bezier_control_points`` by name.
    """
    return make_cubic(p0, p1, p2, p3)


def evaluate(t: float, curve: CubicCurve) -> Point:
    """Evaluate a cubic Bézier curve at parameter t.

    B(t) = a3 t^3 + a2 t^2 + a1 t + a0

    This is a direct power-basis evaluation (Horner-friendly). For numerical
    stability far outside [0, 1] prefer de Casteljau evaluation.

    Args:
        t: Parameter (typically in [0, 1]).
        curve: Cubic Bézier record from make_cubic().

    Returns:
        (x, y) point on the curve.
    """
    xc = curve["x_coeffs"]
    yc = curve["y_coeffs"]
    t2 = t * t
    t3 = t2 * t
    x = xc["a3"] * t3 + xc["a2"] * t2 + xc["a1"] * t + xc["a0"]
    y = yc["b3"] * t3 + yc["b2"] * t2 + yc["b1"] * t + yc["b0"]
    return (float(x), float(y))


def evaluate_bezier(t: float, curve: CubicCurve) -> Point:
    """Backward-compatible alias for evaluate()."""
    return evaluate(t, curve)


def evaluate_de_casteljau(t: float, curve: CubicCurve) -> Point:
    """Evaluate using de Casteljau's algorithm (numerically stable).

    de Casteljau for cubic:
    Q0 = lerp(P0, P1, t)
    Q1 = lerp(P1, P2, t)
    Q2 = lerp(P2, P3, t)
    R0 = lerp(Q0, Q1, t)
    R1 = lerp(Q1, Q2, t)
    S0 = lerp(R0, R1, t)   # point on curve

    Args:
        t: Parameter.
        curve: Cubic Bézier record.

    Returns:
        Point on curve at t.
    """
    p0, p1, p2, p3 = curve["control_points"]
    q0 = lerp(p0, p1, t)
    q1 = lerp(p1, p2, t)
    q2 = lerp(p2, p3, t)
    r0 = lerp(q0, q1, t)
    r1 = lerp(q1, q2, t)
    return lerp(r0, r1, t)


def derivative(t: float, curve: CubicCurve) -> Point:
    """First derivative B'(t) of a cubic Bézier.

    Polynomial form: B'(t) = 3 a3 t^2 + 2 a2 t + a1

    Equivalent control-point form (the hodograph):
    B'(t) = 3(1-t)^2 (P1-P0) + 6(1-t)t (P2-P1) + 3t^2 (P3-P2)

    Args:
        t: Parameter.
        curve: Cubic Bézier record.

    Returns:
        Tangent vector (dx/dt, dy/dt).
    """
    xc = curve["x_coeffs"]
    yc = curve["y_coeffs"]
    t2 = t * t
    dx = 3.0 * xc["a3"] * t2 + 2.0 * xc["a2"] * t + xc["a1"]
    dy = 3.0 * yc["b3"] * t2 + 2.0 * yc["b2"] * t + yc["b1"]
    return (float(dx), float(dy))


def second_derivative(t: float, curve: CubicCurve) -> Point:
    """Second derivative B''(t).

    B''(t) = 6 a3 t + 2 a2

    Args:
        t: Parameter.
        curve: Cubic Bézier record.

    Returns:
        Second derivative vector.
    """
    xc = curve["x_coeffs"]
    yc = curve["y_coeffs"]
    ddx = 6.0 * xc["a3"] * t + 2.0 * xc["a2"]
    ddy = 6.0 * yc["b3"] * t + 2.0 * yc["b2"]
    return (float(ddx), float(ddy))


def tangent(t: float, curve: CubicCurve) -> Point:
    """Unit tangent vector at t.

    Returns (0, 0) at cusps/degenerate points where |B'(t)| == 0.
    """
    dx, dy = derivative(t, curve)
    l = math.hypot(dx, dy)
    if l == 0.0:
        return (0.0, 0.0)
    return (dx / l, dy / l)


def normal(t: float, curve: CubicCurve) -> Point:
    """Unit normal vector at t (tangent rotated 90 degrees CCW)."""
    tx, ty = tangent(t, curve)
    return (-ty, tx)


def tangent_angle(t: float, curve: CubicCurve) -> float:
    """Angle of the tangent in radians [-pi, pi]."""
    dx, dy = derivative(t, curve)
    return math.atan2(dy, dx)


def curvature(t: float, curve: CubicCurve) -> float:
    """Signed curvature at parameter t.

    k(t) = (x' y'' - y' x'') / (x'^2 + y'^2)^(3/2)

    Returns 0 where the speed is zero. Sign indicates turning direction
    (positive = left turn).

    Args:
        t: Parameter.
        curve: Cubic Bézier record.

    Returns:
        Signed curvature.
    """
    dx, dy = derivative(t, curve)
    ddx, ddy = second_derivative(t, curve)
    cross_prod = dx * ddy - dy * ddx
    speed_sq = dx * dx + dy * dy
    if speed_sq == 0.0:
        return 0.0
    return cross_prod / (speed_sq ** 1.5)


def is_degenerate(curve: CubicCurve, tol: float = 1e-12) -> Dict[str, bool]:
    """Detect degenerate configurations of a cubic Bézier.

    Returns a dict describing the degeneracies, useful for robust handling:
        - "point": all control points coincide
        - "line": curve degenerates to a straight line (zero curvature area)
        - "coincident_endpoints": P0 == P3
    """
    p0, p1, p2, p3 = curve["control_points"]

    all_same = (
        distance_squared(p0, p1) <= tol and
        distance_squared(p1, p2) <= tol and
        distance_squared(p2, p3) <= tol
    )

    # A cubic is a straight line when all control points are collinear.
    v1 = (p1[0] - p0[0], p1[1] - p0[1])
    v2 = (p2[0] - p0[0], p2[1] - p0[1])
    v3 = (p3[0] - p0[0], p3[1] - p0[1])
    collinear = (
        abs(cross(v1, v2)) <= tol and
        abs(cross(v1, v3)) <= tol and
        abs(cross(v2, v3)) <= tol
    )

    return {
        "point": all_same,
        "line": collinear,
        "coincident_endpoints": distance_squared(p0, p3) <= tol,
    }


def arc_length(curve: CubicCurve, n_samples: int = 64) -> float:
    """Approximate arc length by polyline sampling.

    This is a numerical approximation; for exact length one would integrate
    sqrt(x'(t)^2 + y'(t)^2) analytically or via adaptive quadrature.

    Args:
        curve: Cubic Bézier record.
        n_samples: Number of line segments.

    Returns:
        Approximate arc length.
    """
    if n_samples < 1:
        raise ValueError("n_samples must be >= 1")
    total = 0.0
    prev = evaluate(0.0, curve)
    for i in range(1, n_samples + 1):
        curr = evaluate(i / n_samples, curve)
        total += math.hypot(curr[0] - prev[0], curr[1] - prev[1])
        prev = curr
    return total


def bind_curve_to_coefficients(
    control_points: CubicControlPoints,
) -> CubicCurve:
    """Rebuild a canonical curve record from control points.

    Convenience for callers that mutate a control point tuple and need the
    coefficient cache regenerated (used by adaptive fitting for C0 repair).
    """
    return make_cubic(*control_points)