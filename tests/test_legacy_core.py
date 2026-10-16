from core.lissara_core.curves import bezier_control_points, evaluate_bezier


def test_bezier_basic():
    """The legacy curve module evaluates exactly at t = 0 and t = 1."""
    p0, p1, p2, p3 = (0.0, 0.0), (0.5, 1.0), (1.5, -0.5), (1.0, 0.0)
    coeffs = bezier_control_points(p0, p1, p2, p3)
    x, y = evaluate_bezier(0.0, coeffs)
    assert abs(x - 0.0) < 1e-10
    assert abs(y - 0.0) < 1e-10
    x, y = evaluate_bezier(1.0, coeffs)
    assert abs(x - 1.0) < 1e-10
    assert abs(y - 0.0) < 1e-10
