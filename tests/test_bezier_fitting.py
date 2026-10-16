import math

from lissara_equations import evaluate_bezier
from lissara_vectorization import fit_bezier_adaptive
from lissara_engine import PathRecord, MathScene


def _endpoints(segment):
    """Start and end point of one fitted segment."""
    return evaluate_bezier(0.0, segment), evaluate_bezier(1.0, segment)


def test_line():
    """A straight line fits into segments that stay on y = x."""
    points = [(0, 0), (10, 10), (20, 20), (30, 30), (40, 40)]
    segs = fit_bezier_adaptive(points, tolerance=1.0)

    assert segs, "a straight line must fit at least one segment"
    for seg in segs:
        assert len(seg["control_points"]) == 4
        start, end = _endpoints(seg)
        assert math.isclose(start[0], start[1], abs_tol=1e-9)
        assert math.isclose(end[0], end[1], abs_tol=1e-9)


def test_quadratic_curve():
    """A parabola-shaped point list fits into cubic segments."""
    points = [(0, 0), (10, 5), (20, 15), (30, 25), (40, 30),
              (50, 25), (60, 15), (70, 5), (80, 0)]
    segs = fit_bezier_adaptive(points, tolerance=1.0)

    assert segs
    for seg in segs:
        assert len(seg["control_points"]) == 4


def test_sharp_corner():
    """An L-shaped corner is split across two joined segments."""
    points = [(0, 0), (10, 0), (20, 0), (30, 0), (30, 10), (30, 20), (30, 30), (30, 40)]
    segs = fit_bezier_adaptive(points, tolerance=1.0)

    assert len(segs) >= 2, "an L-shaped contour needs more than one segment"
    for i in range(len(segs) - 1):
        _, end = _endpoints(segs[i])
        start, _ = _endpoints(segs[i + 1])
        if abs(end[0] - 30) < 1e-6 and abs(end[1]) < 1e-6:
            assert math.isclose(start[0], end[0], abs_tol=1e-6)
            assert math.isclose(start[1], end[1], abs_tol=1e-6)


def test_circle_approximation():
    """A circle needs several segments and control points stay near the radius."""
    points = []
    for i in range(16):
        angle = i * 2 * math.pi / 16
        points.append((50 + 30 * math.cos(angle), 50 + 30 * math.sin(angle)))
    points.append(points[0])

    segs = fit_bezier_adaptive(points, tolerance=1.0)
    assert len(segs) >= 3, "a circle should need several cubic segments"

    for seg in segs:
        for x, y in seg["control_points"]:
            distance = math.hypot(x - 50, y - 50)
            assert 20 <= distance <= 45


def test_degenerate():
    """One point or repeated points fit nothing; two points fit one segment."""
    assert fit_bezier_adaptive([(10, 10)], tolerance=1.0) == []

    two_points = fit_bezier_adaptive([(0, 0), (10, 10)], tolerance=1.0)
    assert len(two_points) == 1
    start, end = _endpoints(two_points[0])
    assert start == (0.0, 0.0)
    assert end == (10.0, 10.0)

    assert fit_bezier_adaptive([(5, 5), (5, 5), (5, 5)], tolerance=1.0) == []


def test_endpoint_preservation():
    """The first and last input points are kept exactly and segments join without gaps."""
    points = [(100, 200), (110, 205), (125, 215), (140, 230), (150, 250)]
    segs = fit_bezier_adaptive(points, tolerance=2.0)

    assert segs
    start, _ = _endpoints(segs[0])
    _, end = _endpoints(segs[-1])
    assert math.isclose(start[0], points[0][0], abs_tol=1e-6)
    assert math.isclose(start[1], points[0][1], abs_tol=1e-6)
    assert math.isclose(end[0], points[-1][0], abs_tol=1e-6)
    assert math.isclose(end[1], points[-1][1], abs_tol=1e-6)

    for i in range(len(segs) - 1):
        _, end_i = _endpoints(segs[i])
        start_next, _ = _endpoints(segs[i + 1])
        assert math.isclose(end_i[0], start_next[0], abs_tol=1e-6)
        assert math.isclose(end_i[1], start_next[1], abs_tol=1e-6)


def test_svg_export_uses_exact_cubic_commands():
    """Fitted segments export as one path built from exact C commands."""
    points = [(50, 50), (100, 30), (150, 80), (120, 150), (60, 120), (50, 50)]
    segs = fit_bezier_adaptive(points, tolerance=2.0)

    path = PathRecord(
        path_id="test_shape",
        path_type="path",
        closed=True,
        segments=segs,
        fill={"color": "#00ff00", "opacity": 0.5},
        stroke={"color": "#000000", "width": 1.0},
    )
    scene = MathScene(width=200, height=200)
    scene.add_path(path)
    svg = scene.export_svg()

    assert svg.count("<path ") == 1
    assert "M " in svg
    assert "C " in svg
    assert svg.rstrip().endswith("</svg>")
    assert 'id="test_shape"' in svg
