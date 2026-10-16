"""Manual check for the legacy core/lissara_core package (run directly, never collected by pytest).

    python tests/manual/verify_legacy_core.py
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def check_curves():
    """Bézier endpoints match the first and last control point."""
    from core.lissara_core.curves import bezier_control_points, evaluate_bezier

    p0, p1, p2, p3 = (0.0, 0.0), (0.5, 1.0), (1.5, -0.5), (1.0, 0.0)
    coeffs = bezier_control_points(p0, p1, p2, p3)
    start = evaluate_bezier(0.0, coeffs)
    end = evaluate_bezier(1.0, coeffs)
    assert abs(start[0] - p0[0]) < 1e-9 and abs(start[1] - p0[1]) < 1e-9
    assert abs(end[0] - p3[0]) < 1e-9 and abs(end[1] - p3[1]) < 1e-9
    return "t=0: %s, t=1: %s" % (start, end)


def check_scene_json():
    """A scene survives a save and reload through JSON."""
    from core.lissara_core.scene import MathScene, PathRecord

    path = PathRecord(path_id='test', path_type='path', closed=True,
                      segments=[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]])
    scene = MathScene(width=200, height=200)
    scene.add_path(path)
    loaded = MathScene.from_json(scene.to_json())
    assert loaded.version == '0.1'
    assert len(loaded.paths) == 1
    return "version=%s, paths=%d" % (loaded.version, len(loaded.paths))


def check_preprocessing():
    """Normalization keeps the image shape and the values."""
    from core.lissara_core.preprocessing import normalize_image

    result = normalize_image([[0.5, 0.6], [0.7, 0.8]])
    assert len(result) == 2 and len(result[0]) == 2
    assert result[0][0] == 0.5
    return "2x2 normalized"


def check_contours():
    """The legacy contour helper evaluates a curve at a given t."""
    from core.lissara_core.contours import bezier_control_points_pure, evaluate_bezier

    coeffs = bezier_control_points_pure((0, 0), (1, 1), (2, -1), (3, 0))
    x, y = evaluate_bezier(0.5, coeffs)
    assert abs(x - 1.5) < 1e-9 and abs(y) < 1e-9
    return "t=0.5: (%f, %f)" % (x, y)


CHECKS = [
    ("Curves", check_curves),
    ("Scene JSON", check_scene_json),
    ("Preprocessing", check_preprocessing),
    ("Contours", check_contours),
]


def main():
    """Print one line per check and exit 1 if any check fails."""
    print("Legacy core verification (%s)" % REPO_ROOT)
    failures = 0
    for index, (name, func) in enumerate(CHECKS, start=1):
        try:
            detail = func()
        except Exception as exc:
            failures += 1
            print("%d. %-14s FAIL - %s: %s" % (index, name, type(exc).__name__, exc))
        else:
            print("%d. %-14s OK   - %s" % (index, name, detail))
    print()
    print("All legacy core checks passed!" if not failures
          else "%d check(s) failed." % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
