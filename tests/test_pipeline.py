import math

from lissara_equations import bezier_control_points, evaluate_bezier
from lissara_vectorization import normalize_image
from lissara_engine import (
    MathScene,
    PathRecord,
    compute_edge_loss,
    compute_pixel_loss,
    compute_regularization_loss,
)


def create_synthetic_image(size=100):
    """A square image with a filled triangle inside."""
    img = [[0.0 for _ in range(size)] for _ in range(size)]
    for y in range(size):
        if y >= 20:
            x_min = 20 + (y - 20) * 30 / 60
            x_max = 80 - (y - 20) * 30 / 60
            for x in range(size):
                if x_min <= x <= x_max:
                    img[y][x] = 1.0
    return img


def test_normalize_image_preserves_shape_and_values():
    """Normalizing to the same size keeps the shape and the pixel values."""
    synthetic_img = create_synthetic_image(100)
    normalized = normalize_image(synthetic_img, target_size=(100, 100))

    assert len(normalized) == 100
    assert all(len(row) == 100 for row in normalized)
    assert normalized[0][0] == 0.0
    assert normalized[50][50] == 1.0


def test_normalize_image_resamples_to_target_size():
    """target_size is (height, width) and the image is resampled to it."""
    synthetic_img = create_synthetic_image(64)
    normalized = normalize_image(synthetic_img, target_size=(48, 32))

    assert len(normalized) == 48
    assert all(len(row) == 32 for row in normalized)


def test_bezier_endpoints_are_exact():
    """t = 0 and t = 1 return the first and last control point exactly."""
    p0, p1, p2, p3 = (0.0, 0.0), (0.3, 1.0), (0.7, 1.0), (1.0, 0.0)
    coeffs = bezier_control_points(p0, p1, p2, p3)

    start = evaluate_bezier(0.0, coeffs)
    end = evaluate_bezier(1.0, coeffs)
    assert math.isclose(start[0], p0[0], abs_tol=1e-12)
    assert math.isclose(start[1], p0[1], abs_tol=1e-12)
    assert math.isclose(end[0], p3[0], abs_tol=1e-12)
    assert math.isclose(end[1], p3[1], abs_tol=1e-12)

    midpoint = evaluate_bezier(0.5, coeffs)
    assert len(midpoint) == 2


def test_scene_svg_export_contains_both_paths():
    """A closed and an open path both appear in the SVG with their own styles."""
    scene = MathScene(width=200, height=200)

    closed_path = PathRecord(
        path_id="square",
        path_type="path",
        closed=True,
        segments=[[0, 0], [100, 0], [100, 100], [0, 100]],
        fill={"color": "#ff0000", "opacity": 0.8},
        stroke={"color": "#000000", "width": 2.0},
    )
    scene.add_path(closed_path)

    open_path = PathRecord(
        path_id="line",
        path_type="path",
        closed=False,
        segments=[[50, 50], [150, 150]],
        stroke={"color": "#00ff00", "width": 3.0},
    )
    scene.add_path(open_path)

    svg = scene.export_svg()

    assert svg.count("<path ") == 2
    assert 'fill:#ff0000' in svg
    assert 'stroke:#00ff00' in svg
    assert 'id="square"' in svg
    assert 'id="line"' in svg
    assert svg.startswith("<svg")


def test_loss_functions_compare_images():
    """Identical images give zero loss, different images give a positive loss."""
    synthetic_img = create_synthetic_image(40)
    identical = [row[:] for row in synthetic_img]

    assert compute_pixel_loss(synthetic_img, identical) == 0.0
    assert compute_edge_loss(synthetic_img, identical) == 0.0

    other = [[0.5 for _ in range(40)] for _ in range(40)]
    pixel_loss = compute_pixel_loss(synthetic_img, other)
    edge_loss = compute_edge_loss(synthetic_img, other)
    assert pixel_loss > 0.0
    assert edge_loss > 0.0


def test_regularization_loss_scales_with_record_length():
    """The loss is lambda multiplied by the total record length."""
    class _Record:
        length = 10.0

    path = PathRecord(path_id="p", path_type="path", closed=True, segments=[[0, 0], [1, 1]])
    path.add_record(_Record())

    assert compute_regularization_loss(path, lambda_val=0.1) == 1.0
