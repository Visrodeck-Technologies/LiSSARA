"""Lissara Core - Curves: Cubic Bézier curve fitting and parametric equation generation.

This module is a thin compatibility shim. The canonical implementation of
cubic Bézier mathematics lives in :mod:`lissara_equations`; the historical
names below are preserved so existing scripts, tests and serialized scenes
continue to work unchanged.
"""
from typing import Tuple

from lissara_equations import (
    bezier_control_points as _equations_bezier_control_points,
    evaluate_bezier as _equations_evaluate_bezier,
    _to_float as _equations_to_float,
)


_to_float = _equations_to_float


def bezier_control_points(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
) -> dict:
    """Generate cubic Bézier control points and parametric coefficients.

    See :func:`lissara_equations.make_cubic`. Returns the canonical record:
    {
        "control_points": [(x0,y0), (x1,y1), (x2,y2), (x3,y3)],
        "x_coeffs": {"a3": float, "a2": float, "a1": float, "a0": float},
        "y_coeffs": {"b3": float, "b2": float, "b1": float, "b0": float},
    }
    """
    return _equations_bezier_control_points(p0, p1, p2, p3)


def evaluate_bezier(t: float, coeffs: dict) -> Tuple[float, float]:
    """Evaluate a cubic Bézier curve at parameter t.

    Args:
        t: Parameter in [0, 1].
        coeffs: Record from :func:`bezier_control_points`.

    Returns:
        (x, y) coordinates at parameter t.
    """
    return _equations_evaluate_bezier(t, coeffs)
