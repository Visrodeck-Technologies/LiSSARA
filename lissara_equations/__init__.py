"""Lissara Equations — canonical curve mathematics for Lissara Core.

This package is the single source of truth for the mathematical building
blocks used across Lissara:

- 2D point primitives and vector operations        (``points``)
- Line-segment evaluation and distance queries     (``segments``)
- Quadratic Bézier representation and operations   (``quadratic``)
- Cubic Bézier representation and operations       (``cubic``)
- Cross-curve algorithms (subdivision, boxes,       (``algorithms``)
  extrema, adaptive flattening, closest point)
- Curve fitting and continuity checks              (``fitting``)

Design constraints:
- Pure Python standard library only: no NumPy, OpenCV, PIL, or SVG renderer.
  This keeps the mathematics usable in the dependency-free pipeline.
- The canonical cubic record is a plain dict with keys ``control_points``,
  ``x_coeffs`` and ``y_coeffs``. ``x_coeffs`` uses keys ``a3/a2/a1/a0`` and
  ``y_coeffs`` uses ``b3/b2/b1/b0``. This asymmetric naming is intentional:
  it matches the historical Lissara serialization format.

References:
- Pomax, "A Primer on Bézier Curves", https://pomax.github.io/bezierinfo/
- Python ``math``, https://docs.python.org/3/library/math.html
- Python ``typing``, https://docs.python.org/3/library/typing.html
- W3C SVG 2 Paths, https://www.w3.org/TR/SVG/latest/paths.html
"""

from __future__ import annotations

# --- Point primitives -------------------------------------------------------
from .points import (
    Point,
    validate_point,
    is_finite,
    point_equal,
    distance,
    distance_squared,
    midpoint,
    lerp,
    lerp_unclamped,
    point_add,
    point_sub,
    point_scale,
    point_neg,
    dot,
    cross,
    length,
    length_squared,
    normalize,
    perpendicular,
    perpendicular_cw,
    project,
    angle_between,
    polar,
    bounding_box,
    centroid,
)

# --- Line segments ----------------------------------------------------------
from .segments import (
    Segment,
    validate_segment,
    segment_length,
    segment_length_squared,
    evaluate_segment,
    segment_midpoint,
    closest_point_on_segment,
    distance_point_to_segment,
    distance_point_to_segment_squared,
    segment_intersects_segment,
    point_to_line_distance,
    project_point_onto_line,
    segment_angle,
    offset_segment,
)

# --- Quadratic Bézier -------------------------------------------------------
from .quadratic import (
    QuadraticControlPoints,
    validate_quadratic_control_points,
    quadratic_coefficients,
    make_quadratic,
    evaluate_quadratic,
    evaluate_quadratic_coeffs,
    quadratic_derivative,
    quadratic_second_derivative,
    quadratic_tangent_angle,
    quadratic_curvature,
    quadratic_arc_length,
    split_quadratic,
    quadratic_bounding_box,
    quadratic_to_cubic,
    quadratic_from_three_points,
)

# --- Cubic Bézier -----------------------------------------------------------
from .cubic import (
    CubicControlPoints,
    CubicCurve,
    validate_control_points,
    cubic_coefficients,
    make_cubic,
    bezier_control_points,        # backward-compatible alias
    evaluate,
    evaluate_bezier,              # backward-compatible alias
    evaluate_de_casteljau,
    derivative,
    second_derivative,
    tangent,
    normal,
    tangent_angle,
    curvature,
    is_degenerate,
    arc_length,
    bind_curve_to_coefficients,
    _to_float,
)

# --- Cross-curve algorithms -------------------------------------------------
from .algorithms import (
    split_cubic,
    split_cubic_many,
    cubic_derivative_roots,
    cubic_extrema,
    cubic_bounding_box,
    cubic_bounding_box_fast,
    flatten_cubic,
    flatten_cubic_adaptive,
    closest_point_on_cubic,
    curve_length,
    reverse_cubic,
)

# --- Fitting and continuity -------------------------------------------------
from .fitting import (
    chord_length_parameterize,
    cubic_fit_error,
    fit_cubic_segment,
    fit_cubic_least_squares,
    is_c0_continuous,
    is_c1_continuous,
    is_g1_continuous,
    enforce_c0_chain,
)


__all__ = [
    # points
    "Point", "validate_point", "is_finite", "point_equal", "distance",
    "distance_squared", "midpoint", "lerp", "lerp_unclamped", "point_add",
    "point_sub", "point_scale", "point_neg", "dot", "cross", "length",
    "length_squared", "normalize", "perpendicular", "perpendicular_cw",
    "project", "angle_between", "polar", "bounding_box", "centroid",
    # segments
    "Segment", "validate_segment", "segment_length", "segment_length_squared",
    "evaluate_segment", "segment_midpoint", "closest_point_on_segment",
    "distance_point_to_segment", "distance_point_to_segment_squared",
    "segment_intersects_segment", "point_to_line_distance",
    "project_point_onto_line", "segment_angle", "offset_segment",
    # quadratic
    "QuadraticControlPoints", "validate_quadratic_control_points",
    "quadratic_coefficients", "make_quadratic", "evaluate_quadratic",
    "evaluate_quadratic_coeffs", "quadratic_derivative",
    "quadratic_second_derivative", "quadratic_tangent_angle",
    "quadratic_curvature", "quadratic_arc_length", "split_quadratic",
    "quadratic_bounding_box", "quadratic_to_cubic",
    "quadratic_from_three_points",
    # cubic
    "CubicControlPoints", "CubicCurve", "validate_control_points",
    "cubic_coefficients", "make_cubic", "bezier_control_points", "evaluate",
    "evaluate_bezier", "evaluate_de_casteljau", "derivative",
    "second_derivative", "tangent", "normal", "tangent_angle", "curvature",
    "is_degenerate", "arc_length", "bind_curve_to_coefficients", "_to_float",
    # algorithms
    "split_cubic", "split_cubic_many", "cubic_derivative_roots",
    "cubic_extrema", "cubic_bounding_box", "cubic_bounding_box_fast",
    "flatten_cubic", "flatten_cubic_adaptive", "closest_point_on_cubic",
    "curve_length", "reverse_cubic",
    # fitting
    "chord_length_parameterize", "cubic_fit_error", "fit_cubic_segment",
    "fit_cubic_least_squares", "is_c0_continuous", "is_c1_continuous",
    "is_g1_continuous", "enforce_c0_chain",
]