"""Cubic Bézier fitting utilities and continuity checks.

This module owns the reusable geometry of fitting a cubic Bézier to an ordered
point sequence, plus the continuity predicates used to validate chained curves.
It is independent of any image-processing concern; contour-specific adaptive
subdivision lives in :mod:`lissara_vectorization` but consumes these primitives.

Mathematical Reference:
- Pomax, "A Primer on Bézier Curves": curve fitting and curve splitting.
- Chord-length parameterization: assign each sample point a parameter
  proportional to accumulated chord length. This is a first-order
  approximation to arc-length parameterization and is cheap and robust.

Implementation decisions (distinguish from formulas):
- Interior control points are initialised by sampling the data at the
  parameters closest to u=1/3 and u=2/3. This is an *approximation* heuristic,
  not a least-squares optimum; it is deliberate for speed and stability in the
  pure-Python pipeline.
- Fitting error is measured as the maximum distance from each data point to
  the sampled polyline of the fitted curve. It therefore slightly
  *over-estimates* true geometric error and is safe as a subdivision trigger.
"""

from __future__ import annotations
from typing import List, Tuple, Optional, Dict
import math

from .points import (
    Point,
    distance,
    distance_squared,
)
from . import cubic as _cubic


def chord_length_parameterize(points: List[Point]) -> List[float]:
    """Assign normalized chord-length parameters to a point sequence.

    The first point gets 0.0 and the last gets 1.0. Interior points receive
    cumulative chord length divided by the total.

    Args:
        points: Ordered list of points (length >= 2).

    Returns:
        List of parameters ``u`` of the same length as ``points``.

    Raises:
        ValueError: If fewer than 2 points are supplied.
    """
    if len(points) < 2:
        raise ValueError("Need at least 2 points for chord-length parameterization")

    chords = [0.0]
    total = 0.0
    for i in range(1, len(points)):
        total += distance(points[i - 1], points[i])
        chords.append(total)

    if total == 0.0:
        # Degenerate: all points coincide. Distribute uniformly.
        n = len(points) - 1
        return [i / n for i in range(len(points))]

    return [c / total for c in chords]


def _sample_curve_points(curve: Dict, n: int) -> List[Point]:
    """Sample a cubic at n+1 uniformly spaced parameters."""
    return [_cubic.evaluate(i / n, curve) for i in range(n + 1)]


def cubic_fit_error(curve: Dict, points: List[Point], n_samples: int = 10) -> float:
    """Maximum distance from data points to a fitted cubic's polyline.

    This is an upper-bound-style approximation: each data point is compared to
    the nearest sampled curve point, so a larger ``n_samples`` gives a tighter
    (smaller) and more accurate value.

    Args:
        curve: Fitted cubic Bézier record.
        points: Data points the curve was fitted to.
        n_samples: Polyline resolution for the curve.

    Returns:
        Maximum Euclidean distance.
    """
    samples = _sample_curve_points(curve, n_samples)
    max_error = 0.0
    for pt in points:
        best = min(distance_squared(pt, s) for s in samples)
        max_error = max(max_error, math.sqrt(best))
    return max_error


def fit_cubic_segment(points: List[Point]) -> Tuple[Optional[Dict], float]:
    """Fit a single cubic Bézier to an ordered point sequence.

    Endpoints are interpolated exactly (P0 = first, P3 = last). Interior
    control points are chosen by sampling the data at parameters nearest
    u=1/3 (P1) and u=2/3 (P2) under chord-length parameterization.

    Degenerate handling:
        - len < 2  => (None, 0.0)
        - len == 2 => a straight "linear" cubic with P1 = P0, P2 = P3.

    Args:
        points: Ordered points (length >= 2).

    Returns:
        (coefficients_dict, max_error) or (None, 0.0) if unfit.
    """
    if len(points) < 2:
        return None, 0.0

    p0 = points[0]
    p3 = points[-1]

    if len(points) == 2:
        return _cubic.make_cubic(p0, p0, p3, p3), 0.0

    us = chord_length_parameterize(points)
    total = us[-1]

    if total == 0.0:
        return _cubic.make_cubic(p0, p0, p3, p3), 0.0

    u1, u2 = 1.0 / 3.0, 2.0 / 3.0
    # Index range excludes the endpoints.
    p1_idx = min(range(1, len(points) - 1), key=lambda i: abs(us[i] - u1))
    p2_idx = min(range(1, len(points) - 1), key=lambda i: abs(us[i] - u2))

    curve = _cubic.make_cubic(p0, points[p1_idx], points[p2_idx], p3)
    max_error = cubic_fit_error(curve, points)
    return curve, max_error


def fit_cubic_least_squares(
    points: List[Point], u_values: Optional[List[float]] = None
) -> Tuple[Optional[Dict], float]:
    """Least-squares fit of a cubic Bézier with fixed endpoints.

    Requires at least 4 points. Uses chord-length parameterization by default.
    The endpoints are allowed to move slightly in this variant only if
    ``fix_endpoints`` is False; here endpoints are fixed to the data endpoints
    for continuity with the adaptive fitter.

    This solver forms the normal equations for the two interior control points
    under the standard least-squares Bézier fit (Pomax, "Curve fitting"), using
    a plain Gaussian elimination for the 2x2 system per axis.

    Args:
        points: Ordered data points (length >= 4 recommended).
        u_values: Optional externally supplied parameters.

    Returns:
        (coefficients_dict, max_error) or (None, 0.0).
    """
    n = len(points)
    if n < 2:
        return None, 0.0
    if n == 2:
        return _cubic.make_cubic(points[0], points[0], points[-1], points[-1]), 0.0

    u = u_values if u_values is not None else chord_length_parameterize(points)
    p0 = points[0]
    p3 = points[-1]

    # Bernstein basis components (Pomax): for fixed endpoints, solve for P1,P2.
    # B(t) - P0 B0 - P3 B3 = P1 B1 + P2 B2
    # Build normal equations A * [P1, P2]^T = C for each axis.
    a11 = a12 = a22 = 0.0
    cx = cy = bx = by = 0.0

    for i in range(n):
        t = u[i]
        mt = 1.0 - t
        b0 = mt ** 3
        b1 = 3.0 * mt * mt * t
        b2 = 3.0 * mt * t * t
        b3 = t ** 3

        # Target after removing fixed endpoint contributions.
        tx = points[i][0] - p0[0] * b0 - p3[0] * b3
        ty = points[i][1] - p0[1] * b0 - p3[1] * b3

        a11 += b1 * b1
        a12 += b1 * b2
        a22 += b2 * b2
        bx += b1 * tx
        by += b1 * ty
        cx += b2 * tx
        cy += b2 * ty

    det = a11 * a22 - a12 * a12
    if abs(det) < 1e-12:
        # Singular: fall back to the heuristic sampler.
        return fit_cubic_segment(points)

    p1x = (bx * a22 - cx * a12) / det
    p1y = (by * a22 - cy * a12) / det
    p2x = (a11 * cx - a12 * bx) / det
    p2y = (a11 * cy - a12 * by) / det

    curve = _cubic.make_cubic(p0, (p1x, p1y), (p2x, p2y), p3)
    max_error = cubic_fit_error(curve, points)
    return curve, max_error


# ---------------------------------------------------------------------------
# Continuity checks
# ---------------------------------------------------------------------------

def is_c0_continuous(
    curve_a: Dict, curve_b: Dict, tol: float = 1e-9
) -> bool:
    """Check positional (C0) continuity between two chained curves.

    True when the end point of ``curve_a`` equals the start point of
    ``curve_b`` within ``tol``.
    """
    a_end = curve_a["control_points"][3]
    b_start = curve_b["control_points"][0]
    return distance(a_end, b_start) <= tol


def is_c1_continuous(
    curve_a: Dict, curve_b: Dict, tol: float = 1e-6
) -> bool:
    """Check tangent (C1) continuity between two chained curves.

    True when the outgoing tangent direction of ``curve_a`` matches the
    incoming tangent direction of ``curve_b`` and the magnitudes are equal
    within ``tol``. Because exact C1 requires matching derivative vectors,
    both direction and length are compared.
    """
    da = _cubic.derivative(1.0, curve_a)
    db = _cubic.derivative(0.0, curve_b)
    return (
        abs(da[0] - db[0]) <= tol and abs(da[1] - db[1]) <= tol
    )


def is_g1_continuous(curve_a: Dict, curve_b: Dict, tol: float = 1e-6) -> bool:
    """Check geometric (G1) tangent continuity, ignoring magnitude.

    Two curves join G1 when their unit tangents at the shared point are
    parallel and point the same way.
    """
    ta = _cubic.tangent(1.0, curve_a)
    tb = _cubic.tangent(0.0, curve_b)
    if ta == (0.0, 0.0) or tb == (0.0, 0.0):
        return False
    return abs(ta[0] - tb[0]) <= tol and abs(ta[1] - tb[1]) <= tol


def enforce_c0_chain(curves: List[Dict], tol: float = 1e-12) -> List[Dict]:
    """Repair minor C0 gaps along a chain by snapping shared endpoints.

    Each curve's start point is moved onto the previous curve's end point when
    they differ by more than ``tol``. Coefficients are regenerated so the
    record stays consistent.

    Args:
        curves: Ordered list of cubic curve records.
        tol: Gap below which no repair is performed.

    Returns:
        A new list of curve records (originals are not mutated).
    """
    if not curves:
        return []

    result = [curves[0]]
    for i in range(1, len(curves)):
        prev = result[-1]
        curr = curves[i]
        prev_end = prev["control_points"][3]
        p0, p1, p2, p3 = curr["control_points"]
        if distance(p0, prev_end) > tol:
            curr = _cubic.make_cubic(prev_end, p1, p2, p3)
        result.append(curr)
    return result