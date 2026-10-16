"""Cross-curve geometric algorithms.

This module collects algorithms that operate on curves regardless of degree:
de Casteljau subdivision, tight bounding boxes, extrema, adaptive flattening,
and closest-point search.

Mathematical Reference:
- Pomax, "A Primer on Bézier Curves": https://pomax.github.io/bezierinfo/
  Sections on de Casteljau's algorithm, bounding boxes, and curve extrema.

Implementation notes:
- Cubic curves are represented by the canonical dict from
  :func:`lissara_equations.cubic.make_cubic`.
- Extrema of a cubic are the roots of the quadratic B'(t)=0 within [0, 1],
  solved with the stable quadratic formula.
"""

from __future__ import annotations
from typing import Tuple, List, Dict
import math

from .points import (
    Point,
    lerp,
    distance,
    distance_squared,
)
from . import cubic as _cubic


def _quadratic_roots(a: float, b: float, c: float, tol: float = 1e-12) -> List[float]:
    """Robust real roots of a*t^2 + b*t + c = 0.

    Handles the degenerate linear case and uses the numerically stable form
    q = -(b + sign(b)*sqrt(disc))/2 to avoid catastrophic cancellation.

    Args:
        a, b, c: Polynomial coefficients.
        tol: Threshold below which ``a`` is treated as zero.

    Returns:
        List of real roots (in arbitrary order).
    """
    if abs(a) < tol:
        if abs(b) < tol:
            return []
        return [-c / b]

    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        # Clamp tiny negative discriminants (rounding) to zero.
        if disc > -tol:
            disc = 0.0
        else:
            return []

    sqrt_disc = math.sqrt(disc)
    # Stable quadratic formula.
    if b >= 0.0:
        q = -0.5 * (b + sqrt_disc)
    else:
        q = -0.5 * (b - sqrt_disc)

    roots = []
    if q != 0.0:
        roots.append(q / a)
        roots.append(c / q)
    else:
        # b == 0 and disc == 0  => root is 0
        roots.append(0.0)
    return roots


def split_cubic(curve: Dict, t: float) -> Tuple[Dict, Dict]:
    """Split a cubic Bézier at parameter t via de Casteljau.

    de Casteljau for cubic:
        Q0 = lerp(P0, P1, t)
        Q1 = lerp(P1, P2, t)
        Q2 = lerp(P2, P3, t)
        R0 = lerp(Q0, Q1, t)
        R1 = lerp(Q1, Q2, t)
        S0 = lerp(R0, R1, t)   # point on curve at t
    Left curve:  P0, Q0, R0, S0
    Right curve: S0, R1, Q2, P3

    Args:
        curve: Cubic Bézier record.
        t: Split parameter in (0, 1).

    Returns:
        (left_curve, right_curve).

    Raises:
        ValueError: If t not strictly inside (0, 1).
    """
    if not 0.0 < t < 1.0:
        raise ValueError(f"Split parameter t must be in (0, 1), got {t}")

    p0, p1, p2, p3 = curve["control_points"]
    q0 = lerp(p0, p1, t)
    q1 = lerp(p1, p2, t)
    q2 = lerp(p2, p3, t)
    r0 = lerp(q0, q1, t)
    r1 = lerp(q1, q2, t)
    s0 = lerp(r0, r1, t)

    left = _cubic.make_cubic(p0, q0, r0, s0)
    right = _cubic.make_cubic(s0, r1, q2, p3)
    return left, right


def split_cubic_many(curve: Dict, ts: List[float]) -> List[Dict]:
    """Split a cubic at multiple parameters, returning ordered sub-curves.

    Args:
        curve: Cubic Bézier record.
        ts: Sorted split parameters strictly inside (0, 1).

    Returns:
        List of len(ts)+1 sub-curves covering the original [0, 1] interval.
    """
    ordered = sorted(t for t in ts if 0.0 < t < 1.0)
    segments = []
    remaining = curve
    consumed = 0.0
    for t in ordered:
        # Re-map t into the current remaining sub-curve's local parameter.
        local = (t - consumed) / (1.0 - consumed) if consumed < 1.0 else t
        left, remaining = split_cubic(remaining, local)
        segments.append(left)
        consumed = t
    segments.append(remaining)
    return segments


def cubic_derivative_roots(curve: Dict, axis: str = "x") -> List[float]:
    """Return parameters where the cubic derivative is zero on one axis.

    B'(t) = 3 a3 t^2 + 2 a2 t + a1 = 0. Only roots within [0, 1] are kept.

    Args:
        curve: Cubic Bézier record.
        axis: "x" or "y".

    Returns:
        Sorted list of parameter values in [0, 1].
    """
    if axis == "x":
        c = curve["x_coeffs"]
        a, b, cc = 3.0 * c["a3"], 2.0 * c["a2"], c["a1"]
    elif axis == "y":
        c = curve["y_coeffs"]
        a, b, cc = 3.0 * c["b3"], 2.0 * c["b2"], c["b1"]
    else:
        raise ValueError("axis must be 'x' or 'y'")

    roots = []
    for r in _quadratic_roots(a, b, cc):
        if 0.0 <= r <= 1.0:
            roots.append(r)
    return sorted(roots)


def cubic_extrema(curve: Dict) -> List[Tuple[float, Point]]:
    """Find the extrema (derivative-zero points) of a cubic Bézier.

    Returns:
        List of (t, point) for every t in [0, 1] where B'(t) = 0 on x or y,
        de-duplicated, sorted by t.
    """
    ts = set(cubic_derivative_roots(curve, "x"))
    ts.update(cubic_derivative_roots(curve, "y"))
    result = []
    for t in sorted(ts):
        result.append((t, _cubic.evaluate(t, curve)))
    return result


def cubic_bounding_box(curve: Dict) -> Tuple[Point, Point]:
    """Compute the tight axis-aligned bounding box of a cubic Bézier.

    The box is determined by the endpoints plus any interior extrema. This is
    tighter than the control-point hull and is exact for the curve, not an
    approximation.

    Args:
        curve: Cubic Bézier record.

    Returns:
        ((min_x, min_y), (max_x, max_y))
    """
    candidates = [
        curve["control_points"][0],
        curve["control_points"][3],
    ]
    for _t, pt in cubic_extrema(curve):
        candidates.append(pt)

    min_x = min(p[0] for p in candidates)
    max_x = max(p[0] for p in candidates)
    min_y = min(p[1] for p in candidates)
    max_y = max(p[1] for p in candidates)
    return ((min_x, min_y), (max_x, max_y))


def cubic_bounding_box_fast(curve: Dict) -> Tuple[Point, Point]:
    """Bounding box of the control-point convex hull (never tighter, always safe).

    Useful when a cheap over-approximation is sufficient (e.g., broad-phase).
    """
    cps = curve["control_points"]
    min_x = min(p[0] for p in cps)
    max_x = max(p[0] for p in cps)
    min_y = min(p[1] for p in cps)
    max_y = max(p[1] for p in cps)
    return ((min_x, min_y), (max_x, max_y))


def flatten_cubic(curve: Dict, n_samples: int = 16) -> List[Point]:
    """Uniformly sample a cubic Bézier into a polyline.

    This is an approximation (piecewise-linear). Sample count trades accuracy
    for speed.

    Args:
        curve: Cubic Bézier record.
        n_samples: Number of segments (produces n_samples+1 points).

    Returns:
        List of points from t=0 to t=1 inclusive.
    """
    if n_samples < 1:
        raise ValueError("n_samples must be >= 1")
    return [_cubic.evaluate(i / n_samples, curve) for i in range(n_samples + 1)]


def flatten_cubic_adaptive(
    curve: Dict,
    flatness: float = 0.25,
    max_depth: int = 16,
) -> List[Point]:
    """Adaptively flatten a cubic using recursive de Casteljau subdivision.

    A sub-curve is accepted when the control points are nearly collinear and
    the middle control points are close to the chord (within ``flatness`` px).

    Args:
        curve: Cubic Bézier record.
        flatness: Maximum deviation of control points from the chord.
        max_depth: Recursion cap.

    Returns:
        Polyline points approximating the curve.
    """
    points: List[Point] = [curve["control_points"][0]]

    def recurse(c: Dict, depth: int) -> None:
        p0, p1, p2, p3 = c["control_points"]

        # Flatness test: distance of p1, p2 from the p0-p3 chord.
        ux, uy = p3[0] - p0[0], p3[1] - p0[1]
        chord_len_sq = ux * ux + uy * uy

        if chord_len_sq <= 1e-12:
            d1 = distance(p0, p1)
            d2 = distance(p0, p2)
            flat = max(d1, d2) <= flatness
        else:
            # Perpendicular distances via cross products.
            c1 = abs(ux * (p1[1] - p0[1]) - uy * (p1[0] - p0[0]))
            c2 = abs(ux * (p2[1] - p0[1]) - uy * (p2[0] - p0[0]))
            scale = math.sqrt(chord_len_sq)
            flat = max(c1, c2) / scale <= flatness

        if flat or depth >= max_depth:
            points.append(p3)
            return

        left, right = split_cubic(c, 0.5)
        recurse(left, depth + 1)
        recurse(right, depth + 1)

    recurse(curve, 0)
    return points


def closest_point_on_cubic(
    curve: Dict,
    point: Point,
    n_samples: int = 32,
    refine_iterations: int = 4,
) -> Tuple[Point, float, float]:
    """Find the closest point on a cubic to a target point.

    Strategy: coarse sampling followed by a few iterations of golden-section
    / local ternary refinement around the best sample. This is a bounded
    approximation; exact closest-point requires solving a degree-5 polynomial.

    Args:
        curve: Cubic Bézier record.
        point: Target point.
        n_samples: Coarse sample count.
        refine_iterations: Number of ternary-search refinement rounds.

    Returns:
        Tuple of (closest_point, t, distance).
    """
    best_t = 0.0
    best_pt = curve["control_points"][0]
    best_d = distance_squared(point, best_pt)

    # Coarse scan (includes both endpoints t=0 and t=1).
    for i in range(n_samples + 1):
        t = i / n_samples
        pt = _cubic.evaluate(t, curve)
        d = distance_squared(point, pt)
        if d < best_d:
            best_d = d
            best_t = t
            best_pt = pt

    # Refine by ternary search within the bracketing interval. The refined
    # candidate only replaces the incumbent when it is genuinely closer, so a
    # true boundary minimum (e.g. t=0 or t=1) is never discarded.
    lo = max(0.0, best_t - 1.0 / n_samples)
    hi = min(1.0, best_t + 1.0 / n_samples)
    for _ in range(refine_iterations):
        m1 = lo + (hi - lo) / 3.0
        m2 = hi - (hi - lo) / 3.0
        d1 = distance_squared(point, _cubic.evaluate(m1, curve))
        d2 = distance_squared(point, _cubic.evaluate(m2, curve))
        if d1 < d2:
            hi = m2
        else:
            lo = m1
    t_ref = 0.5 * (lo + hi)
    pt_ref = _cubic.evaluate(t_ref, curve)
    d_ref = distance_squared(point, pt_ref)
    if d_ref < best_d:
        best_d = d_ref
        best_t = t_ref
        best_pt = pt_ref

    return best_pt, best_t, math.sqrt(best_d)


def curve_length(points: List[Point]) -> float:
    """Polyline length of a point list."""
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += distance(a, b)
    return total


def reverse_cubic(curve: Dict) -> Dict:
    """Return the cubic Bézier traversed in the opposite direction.

    Reversing swaps P0<->P3 and P1<->P2, which preserves the geometric locus
    and negates the tangent direction.
    """
    p0, p1, p2, p3 = curve["control_points"]
    return _cubic.make_cubic(p3, p2, p1, p0)