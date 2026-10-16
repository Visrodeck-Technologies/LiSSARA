"""Curve sampling for the graphing engine.

Sampling turns continuous curves into finite point sequences so they can be
drawn, measured, or rasterised. All mathematical evaluation is delegated to
:mod:`lissara_equations`; this module contains no curve mathematics of its own —
it only chooses *where* to evaluate.

Two strategies are provided:

* **Uniform sampling** (:func:`sample_cubic`, :func:`sample_quadratic`,
  :func:`sample_segment`) evaluates the curve at ``n + 1`` evenly spaced
  parameters. Cheap and predictable, ideal when the caller already knows the
  required resolution.
* **Adaptive sampling** (:func:`sample_cubic_adaptive`,
  :func:`sample_quadratic_adaptive`) recursively bisects the parameter interval
  and stops when the midpoint lies within ``tolerance`` of the chord. This
  materially reduces the point count on straight regions while keeping curved
  regions accurate, and is the default for graph curves.

Approximation behaviour (documented so error is controllable):

* Adaptive error is measured as the perpendicular distance from the sub-interval
  midpoint to the chord joining the sub-interval endpoints. It is a
  *max-deviation* proxy, not a strict Hausdorff bound, and shrinks as
  ``tolerance`` decreases. ``max_depth`` caps worst-case point counts.
* Endpoints of the requested interval are always emitted exactly, so a curve
  sampled over ``[0, 1]`` preserves its true start and end points.

Degenerate handling: a cubic whose control points coincide (or that collapses to
a point) immediately satisfies the flatness test and yields just the two
interval endpoints. Non-finite results raise ``ValueError`` rather than emitting
``NaN`` coordinates.
"""
from __future__ import annotations

import math
from typing import Callable, List, Optional, Sequence, Tuple

from lissara_equations import (
    evaluate_bezier,
    evaluate_quadratic,
    evaluate_segment,
)

Point = Tuple[float, float]
CubicCurve = dict


def _check_interval(t_start: float, t_end: float) -> Tuple[float, float]:
    if not math.isfinite(t_start) or not math.isfinite(t_end):
        raise ValueError("sampling interval must be finite")
    if t_end < t_start:
        raise ValueError(f"require t_start <= t_end, got {t_start} > {t_end}")
    return float(t_start), float(t_end)


def _checked_point(name: str, point) -> Point:
    try:
        px, py = point
    except (TypeError, ValueError):
        raise ValueError(f"{name} produced a malformed point: {point!r}")
    px = float(px)
    py = float(py)
    if not (math.isfinite(px) and math.isfinite(py)):
        raise ValueError(f"{name} produced a non-finite coordinate: {point!r}")
    return (px, py)


# ---------------------------------------------------------------------------
# Uniform sampling
# ---------------------------------------------------------------------------

def sample_cubic(
    curve: CubicCurve,
    n: int = 32,
    t_start: float = 0.0,
    t_end: float = 1.0,
) -> List[Point]:
    """Sample a cubic Bézier uniformly.

    Args:
        curve: Canonical cubic record from :func:`lissara_equations.make_cubic`.
        n: Number of *segments*; the result has ``n + 1`` points. Must be >= 1.
        t_start, t_end: Parameter interval to sample (defaults to the whole
            curve). Endpoints are emitted exactly.

    Returns:
        Ordered ``(x, y)`` points from ``t_start`` to ``t_end`` inclusive.

    Raises:
        ValueError: If ``n < 1`` or the interval is invalid/non-finite.
    """
    if n < 1:
        raise ValueError("n must be >= 1")
    t_start, t_end = _check_interval(t_start, t_end)
    span = t_end - t_start
    points = []
    for i in range(n + 1):
        t = t_start if i == 0 else (t_end if i == n else t_start + span * i / n)
        points.append(_checked_point("sample_cubic", evaluate_bezier(t, curve)))
    return points


def sample_quadratic(
    curve: dict,
    n: int = 32,
    t_start: float = 0.0,
    t_end: float = 1.0,
) -> List[Point]:
    """Sample a quadratic Bézier uniformly (see :func:`sample_cubic`)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    t_start, t_end = _check_interval(t_start, t_end)
    span = t_end - t_start
    points = []
    for i in range(n + 1):
        t = t_start if i == 0 else (t_end if i == n else t_start + span * i / n)
        points.append(_checked_point("sample_quadratic", evaluate_quadratic(t, curve)))
    return points


def sample_segment(
    segment: Tuple[Point, Point],
    n: int = 1,
    t_start: float = 0.0,
    t_end: float = 1.0,
) -> List[Point]:
    """Sample a line segment uniformly (a segment is already linear)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    t_start, t_end = _check_interval(t_start, t_end)
    span = t_end - t_start
    points = []
    for i in range(n + 1):
        t = t_start if i == 0 else (t_end if i == n else t_start + span * i / n)
        points.append(_checked_point("sample_segment", evaluate_segment(segment, t)))
    return points


# ---------------------------------------------------------------------------
# Adaptive sampling
# ---------------------------------------------------------------------------

def _adaptive(
    evaluator: Callable[[float], Point],
    t_start: float,
    t_end: float,
    tolerance: float,
    max_depth: int,
    name: str,
) -> List[Point]:
    """Recursive parametric bisection with a midpoint chord-deviation test."""
    if tolerance < 0.0 or not math.isfinite(tolerance):
        raise ValueError("tolerance must be a finite value >= 0")
    if max_depth < 0:
        raise ValueError("max_depth must be >= 0")

    p0 = _checked_point(name, evaluator(t_start))
    p1 = _checked_point(name, evaluator(t_end))
    points: List[Point] = [p0]

    def deviation(a: Point, m: Point, b: Point) -> float:
        ux, uy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(ux, uy)
        if length <= 1e-12:
            return math.hypot(m[0] - a[0], m[1] - a[1])
        return abs(ux * (m[1] - a[1]) - uy * (m[0] - a[0])) / length

    def recurse(a: Point, ta: float, b: Point, tb: float, depth: int) -> None:
        tm = 0.5 * (ta + tb)
        m = _checked_point(name, evaluator(tm))
        if depth >= max_depth or deviation(a, m, b) <= tolerance:
            points.append(b)
            return
        recurse(a, ta, m, tm, depth + 1)
        recurse(m, tm, b, tb, depth + 1)

    recurse(p0, t_start, p1, t_end, 0)
    return points


def sample_cubic_adaptive(
    curve: CubicCurve,
    tolerance: float = 0.25,
    max_depth: int = 16,
    t_start: float = 0.0,
    t_end: float = 1.0,
) -> List[Point]:
    """Adaptively sample a cubic Bézier.

    Args:
        curve: Canonical cubic record.
        tolerance: Maximum allowed midpoint deviation from the chord (in world
            units). Smaller values give more points and higher fidelity.
        max_depth: Recursion cap; bounds the point count at ``2**max_depth + 1``.
        t_start, t_end: Parameter interval (endpoints preserved exactly).

    Returns:
        Ordered points approximating the curve over the interval.
    """
    t_start, t_end = _check_interval(t_start, t_end)
    return _adaptive(
        lambda t: evaluate_bezier(t, curve),
        t_start,
        t_end,
        tolerance,
        max_depth,
        "sample_cubic_adaptive",
    )


def sample_quadratic_adaptive(
    curve: dict,
    tolerance: float = 0.25,
    max_depth: int = 16,
    t_start: float = 0.0,
    t_end: float = 1.0,
) -> List[Point]:
    """Adaptively sample a quadratic Bézier (see :func:`sample_cubic_adaptive`)."""
    t_start, t_end = _check_interval(t_start, t_end)
    return _adaptive(
        lambda t: evaluate_quadratic(t, curve),
        t_start,
        t_end,
        tolerance,
        max_depth,
        "sample_quadratic_adaptive",
    )


# ---------------------------------------------------------------------------
# Dispatch helpers
# ---------------------------------------------------------------------------

def _curve_degree(curve: dict) -> Optional[int]:
    """Best-effort classification of a curve record's degree (2 or 3)."""
    if not isinstance(curve, dict):
        return None
    if "degree" in curve:
        try:
            return int(curve["degree"])
        except (TypeError, ValueError):
            return None
    cps = curve.get("control_points")
    if isinstance(cps, (list, tuple)):
        return {3: 2, 4: 3}.get(len(cps))
    return None


def sample_curve(
    curve: dict,
    n: int = 32,
    adaptive: bool = False,
    tolerance: float = 0.25,
    max_depth: int = 16,
    t_start: float = 0.0,
    t_end: float = 1.0,
) -> List[Point]:
    """Sample a quadratic or cubic Bézier, choosing the evaluator by degree.

    Args:
        curve: Quadratic or cubic curve record.
        n: Uniform segment count (ignored when ``adaptive`` is True).
        adaptive: Use adaptive sampling when True.
        tolerance, max_depth: Adaptive parameters.
        t_start, t_end: Parameter interval.

    Returns:
        Ordered points.

    Raises:
        ValueError: If the curve degree cannot be determined, or the underlying
            sampler rejects the arguments.
    """
    degree = _curve_degree(curve)
    if degree == 3:
        if adaptive:
            return sample_cubic_adaptive(curve, tolerance, max_depth, t_start, t_end)
        return sample_cubic(curve, n, t_start, t_end)
    if degree == 2:
        if adaptive:
            return sample_quadratic_adaptive(curve, tolerance, max_depth, t_start, t_end)
        return sample_quadratic(curve, n, t_start, t_end)
    raise ValueError(f"unsupported curve record: {curve!r}")


def sample_polyline(
    points: Sequence[Point],
    closed: bool = False,
) -> List[Point]:
    """Validate (and optionally close) an existing polyline.

    Args:
        points: Sequence of ``(x, y)`` points.
        closed: When True and the first and last points differ, append a final
            point equal to the first so consumers can rely on closure.

    Returns:
        A new list of validated ``(x, y)`` tuples.

    Raises:
        ValueError: If ``points`` is empty or contains a non-finite/malformed
            entry.
    """
    if not points:
        raise ValueError("polyline requires at least one point")
    validated = [_checked_point("sample_polyline", p) for p in points]
    if closed and len(validated) > 1 and validated[0] != validated[-1]:
        validated.append(validated[0])
    return validated


def sample_cubic_segments(
    segments: Sequence[CubicCurve],
    n: int = 16,
    adaptive: bool = False,
    tolerance: float = 0.25,
) -> List[Point]:
    """Sample a chain of cubic segments into one continuous polyline.

    Shared endpoints between consecutive segments are emitted once, so the
    result is a continuous polyline even when the segments are only C0
    continuous.
    """
    if not segments:
        raise ValueError("sample_cubic_segments requires at least one segment")
    out: List[Point] = []
    for index, seg in enumerate(segments):
        pts = (
            sample_cubic_adaptive(seg, tolerance)
            if adaptive
            else sample_cubic(seg, n)
        )
        if index > 0 and out and out[-1] == pts[0]:
            pts = pts[1:]
        out.extend(pts)
    return out
