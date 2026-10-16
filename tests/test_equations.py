"""Unit tests for the canonical ``lissara_equations`` curve mathematics.

These tests validate mathematical correctness (endpoints, derivatives,
subdivision, bounding boxes, fitting) and the backward-compatible serialized
record format consumed by the SVG exporter.
"""
import pytest

import lissara_equations as eq


# ---------------------------------------------------------------------------
# Point primitives
# ---------------------------------------------------------------------------

def test_point_validation_and_distance():
    assert eq.validate_point([3, 4]) == (3.0, 4.0)
    assert eq.distance((0, 0), (3, 4)) == pytest.approx(5.0)
    assert eq.distance_squared((0, 0), (3, 4)) == pytest.approx(25.0)
    with pytest.raises(TypeError):
        eq.validate_point((1,))
    with pytest.raises(TypeError):
        eq.validate_point(None)


def test_linear_interpolation_endpoints_and_midpoint():
    p0, p1 = (0.0, 0.0), (10.0, 20.0)
    assert eq.lerp(p0, p1, 0.0) == p0
    assert eq.lerp(p0, p1, 1.0) == p1
    assert eq.lerp(p0, p1, 0.5) == (5.0, 10.0)
    # Clamping outside [0, 1]
    assert eq.lerp(p0, p1, -1.0) == p0
    assert eq.lerp(p0, p1, 2.0) == p1
    assert eq.lerp_unclamped(p0, p1, 2.0) == (20.0, 40.0)


def test_vector_algebra():
    assert eq.dot((1, 2), (3, 4)) == 11
    assert eq.cross((1, 2), (3, 4)) == -2
    assert eq.length((3, 4)) == pytest.approx(5.0)
    assert eq.normalize((0, 0)) == (0.0, 0.0)
    assert eq.perpendicular((1, 0)) == (0, 1)


def test_bounding_box_and_centroid():
    pts = [(0, 0), (2, 4), (-1, 3)]
    assert eq.bounding_box(pts) == ((-1, 0), (2, 4))
    cx, cy = eq.centroid(pts)
    assert cx == pytest.approx(1.0 / 3.0)
    assert cy == pytest.approx(7.0 / 3.0)


# ---------------------------------------------------------------------------
# Line segments
# ---------------------------------------------------------------------------

def test_segment_evaluation_and_distance():
    seg = ((0.0, 0.0), (10.0, 0.0))
    assert eq.evaluate_segment(seg, 0.5) == (5.0, 0.0)
    assert eq.segment_length(seg) == pytest.approx(10.0)
    # Point above the middle of the segment.
    assert eq.distance_point_to_segment((5.0, 3.0), seg) == pytest.approx(3.0)
    # Point beyond the endpoint clamps to the endpoint.
    assert eq.distance_point_to_segment((14.0, 0.0), seg) == pytest.approx(4.0)
    closest, t = eq.closest_point_on_segment(seg, (5.0, 3.0))
    assert closest == (5.0, 0.0)
    assert t == pytest.approx(0.5)


def test_segment_intersection():
    a = ((0.0, 0.0), (10.0, 10.0))
    b = ((0.0, 10.0), (10.0, 0.0))
    hit, point, t1, t2 = eq.segment_intersects_segment(a, b)
    assert hit
    assert point == pytest.approx((5.0, 5.0))
    assert t1 == pytest.approx(0.5)
    assert t2 == pytest.approx(0.5)

    parallel = ((0.0, 0.0), (10.0, 0.0))
    other = ((0.0, 1.0), (10.0, 1.0))
    assert not eq.segment_intersects_segment(parallel, other)[0]


# ---------------------------------------------------------------------------
# Quadratic Bézier
# ---------------------------------------------------------------------------

def test_quadratic_endpoints_and_derivative():
    curve = eq.make_quadratic((0.0, 0.0), (1.0, 2.0), (2.0, 0.0))
    assert eq.evaluate_quadratic(0.0, curve) == (0.0, 0.0)
    assert eq.evaluate_quadratic(1.0, curve) == (2.0, 0.0)
    # B(0.5) = 0.25 P0 + 0.5 P1 + 0.25 P2
    assert eq.evaluate_quadratic(0.5, curve) == pytest.approx((1.0, 1.0))
    # Tangent at t=0 points along P1-P0.
    assert eq.quadratic_derivative(0.0, curve) == (2.0, 4.0)


def test_quadratic_degree_elevation_matches_cubic():
    quad = eq.make_quadratic((0.0, 0.0), (1.0, 2.0), (2.0, 0.0))
    cubic = eq.quadratic_to_cubic(quad)
    for i in range(11):
        t = i / 10.0
        assert eq.evaluate_quadratic(t, quad) == pytest.approx(
            eq.evaluate(t, cubic), abs=1e-12
        )


def test_quadratic_bounding_box_contains_curve():
    quad = eq.make_quadratic((0.0, 0.0), (5.0, 10.0), (10.0, 0.0))
    (min_x, min_y), (max_x, max_y) = eq.quadratic_bounding_box(quad)
    for i in range(21):
        x, y = eq.evaluate_quadratic(i / 20.0, quad)
        assert min_x - 1e-9 <= x <= max_x + 1e-9
        assert min_y - 1e-9 <= y <= max_y + 1e-9
    # The apex (10 at t=0.5) should be captured exactly.
    assert max_y == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Cubic Bézier
# ---------------------------------------------------------------------------

def test_cubic_record_schema_is_svg_compatible():
    curve = eq.make_cubic((0, 0), (1, 1), (2, 1), (3, 0))
    assert set(curve.keys()) == {"control_points", "x_coeffs", "y_coeffs"}
    assert set(curve["x_coeffs"].keys()) == {"a3", "a2", "a1", "a0"}
    assert set(curve["y_coeffs"].keys()) == {"b3", "b2", "b1", "b0"}
    assert len(curve["control_points"]) == 4


def test_cubic_endpoint_interpolation_exact():
    p0, p1, p2, p3 = (1.0, 2.0), (3.0, 5.0), (8.0, -1.0), (10.0, 4.0)
    curve = eq.make_cubic(p0, p1, p2, p3)
    assert eq.evaluate(0.0, curve) == p0
    assert eq.evaluate(1.0, curve) == p3
    assert eq.evaluate_bezier(0.0, curve) == p0
    assert eq.evaluate_bezier(1.0, curve) == p3


def test_power_basis_matches_de_casteljau():
    curve = eq.make_cubic((0, 0), (1, 3), (4, -2), (6, 1))
    for i in range(21):
        t = i / 20.0
        assert eq.evaluate(t, curve) == pytest.approx(
            eq.evaluate_de_casteljau(t, curve), abs=1e-9
        )


def test_cubic_derivative_matches_finite_difference():
    curve = eq.make_cubic((0, 0), (1, 3), (4, -2), (6, 1))
    h = 1e-6
    for t in (0.2, 0.5, 0.8):
        numeric = (
            (eq.evaluate(t + h, curve)[0] - eq.evaluate(t - h, curve)[0]) / (2 * h),
            (eq.evaluate(t + h, curve)[1] - eq.evaluate(t - h, curve)[1]) / (2 * h),
        )
        assert eq.derivative(t, curve) == pytest.approx(numeric, abs=1e-4)


def test_cubic_split_preserves_geometry_and_continuity():
    curve = eq.make_cubic((0, 0), (1, 3), (4, -2), (6, 1))
    left, right = eq.split_cubic(curve, 0.4)
    # Split point is shared and equals the original curve at t=0.4.
    assert left["control_points"][3] == right["control_points"][0]
    assert eq.evaluate(1.0, left) == pytest.approx(eq.evaluate(0.4, curve))
    # Sub-curves reproduce the original geometry on their parameter ranges.
    for i in range(11):
        u = i / 10.0
        assert eq.evaluate(u, left) == pytest.approx(eq.evaluate(0.4 * u, curve), abs=1e-9)
        assert eq.evaluate(u, right) == pytest.approx(
            eq.evaluate(0.4 + 0.6 * u, curve), abs=1e-9
        )
    with pytest.raises(ValueError):
        eq.split_cubic(curve, 0.0)


def test_cubic_bounding_box_contains_curve_and_beats_hull():
    curve = eq.make_cubic((0, 0), (0, 10), (10, 10), (10, 0))
    tight = eq.cubic_bounding_box(curve)
    hull = eq.cubic_bounding_box_fast(curve)
    for i in range(41):
        x, y = eq.evaluate(i / 40.0, curve)
        (min_x, min_y), (max_x, max_y) = tight
        assert min_x - 1e-9 <= x <= max_x + 1e-9
        assert min_y - 1e-9 <= y <= max_y + 1e-9
    # Tight box must not exceed the control hull.
    assert tight[1][1] <= hull[1][1] + 1e-9


def test_cubic_extrema_of_arch():
    # Symmetric arch peaks at t=0.5 with y=7.5.
    curve = eq.make_cubic((0, 0), (0, 10), (10, 10), (10, 0))
    extrema = eq.cubic_extrema(curve)
    ts = [t for t, _pt in extrema]
    assert any(abs(t - 0.5) < 1e-9 for t in ts)


def test_cubic_curvature_sign_and_line_degeneracy():
    # A straight-line cubic has zero curvature everywhere.
    line = eq.make_cubic((0, 0), (1, 1), (2, 2), (3, 3))
    assert eq.curvature(0.5, line) == pytest.approx(0.0)
    assert eq.is_degenerate(line)["line"] is True

    # A genuine arc has non-zero magnitude curvature.
    arc = eq.make_cubic((0, 0), (0, 1), (1, 1), (1, 0))
    assert abs(eq.curvature(0.5, arc)) > 1e-6


def test_cubic_arc_length_of_straight_line():
    line = eq.make_cubic((0, 0), (1, 0), (2, 0), (3, 0))
    assert eq.arc_length(line, n_samples=64) == pytest.approx(3.0, abs=1e-6)


def test_cubic_reverse_preserves_locus():
    curve = eq.make_cubic((0, 0), (1, 3), (4, -2), (6, 1))
    rev = eq.reverse_cubic(curve)
    for i in range(11):
        t = i / 10.0
        assert eq.evaluate(t, rev) == pytest.approx(eq.evaluate(1.0 - t, curve), abs=1e-9)


def test_adaptive_flatten_endpoints_and_accuracy():
    curve = eq.make_cubic((0, 0), (0, 10), (10, 10), (10, 0))
    poly = eq.flatten_cubic_adaptive(curve, flatness=0.1)
    assert poly[0] == (0.0, 0.0)
    assert poly[-1] == pytest.approx((10.0, 0.0))
    # Polyline should stay close to the true curve.
    for pt in poly:
        _cp, _t, dist = eq.closest_point_on_cubic(curve, pt, n_samples=64)
        assert dist < 0.5


def test_closest_point_on_cubic_hits_endpoints():
    curve = eq.make_cubic((0, 0), (0, 10), (10, 10), (10, 0))
    pt, t, d = eq.closest_point_on_cubic(curve, (-1.0, 0.0))
    assert t == pytest.approx(0.0, abs=1e-6)
    assert d == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Fitting and continuity
# ---------------------------------------------------------------------------

def test_chord_length_parameterization_bounds():
    pts = [(0, 0), (1, 0), (3, 0), (6, 0)]
    u = eq.chord_length_parameterize(pts)
    assert u[0] == 0.0 and u[-1] == 1.0
    assert all(u[i] <= u[i + 1] for i in range(len(u) - 1))


def test_fit_cubic_segment_preserves_endpoints():
    pts = [(0, 0), (10, 0), (20, 0), (30, 0), (40, 0)]
    curve, error = eq.fit_cubic_segment(pts)
    assert curve is not None
    assert curve["control_points"][0] == (0.0, 0.0)
    assert curve["control_points"][3] == (40.0, 0.0)
    assert error >= 0.0


def test_fit_cubic_least_squares_endpoints():
    pts = [(0, 0), (5, 4), (10, 6), (15, 4), (20, 0)]
    curve, _err = eq.fit_cubic_least_squares(pts)
    assert curve["control_points"][0] == (0.0, 0.0)
    assert curve["control_points"][3] == (20.0, 0.0)


def test_continuity_checks_and_chain_repair():
    a = eq.make_cubic((0, 0), (1, 0), (2, 0), (3, 0))
    b = eq.make_cubic((3, 0), (4, 0), (5, 0), (6, 0))
    assert eq.is_c0_continuous(a, b)
    assert eq.is_c1_continuous(a, b)
    assert eq.is_g1_continuous(a, b)

    # Deliberately misaligned start point; repair restores C0.
    c = eq.make_cubic((3.5, 0), (4.5, 0), (5.5, 0), (6.5, 0))
    assert not eq.is_c0_continuous(a, c)
    repaired = eq.enforce_c0_chain([a, c])
    assert eq.is_c0_continuous(repaired[0], repaired[1])
