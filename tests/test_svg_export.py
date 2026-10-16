import xml.etree.ElementTree as ET

from lissara_engine import MathScene, PathRecord

SVG_NS = "http://www.w3.org/2000/svg"


def _closed_square_scene(explicit_closure=False):
    """A scene with one closed square path (optionally repeating the first point)."""
    scene = MathScene(width=200, height=200)
    square = [[0, 0], [100, 0], [100, 100], [0, 100]]
    if explicit_closure:
        square = square + [[0, 0]]
    scene.add_path(PathRecord(
        path_id="square",
        path_type="path",
        closed=True,
        segments=square,
        fill={"color": "#ff0000", "opacity": 0.8},
        stroke={"color": "#000000", "width": 2.0},
    ))
    return scene


def test_closed_path_svg_geometry_and_style():
    """A closed square exports M/L/Z plus its fill and stroke styles."""
    svg = _closed_square_scene().export_svg()

    assert svg.count("<path ") == 1
    assert 'd="M 0 0 L 100 0 L 100 100 L 0 100 Z"' in svg
    assert "fill:#ff0000" in svg
    assert "fill-opacity:0.8" in svg
    assert "stroke:#000000" in svg
    assert "stroke-width:2.0" in svg


def test_explicitly_closed_point_list_still_emits_z():
    """Repeating the first point still ends the path with a single Z."""
    svg = _closed_square_scene(explicit_closure=True).export_svg()

    assert 'd="M 0 0 L 100 0 L 100 100 L 0 100 L 0 0 Z"' in svg


def test_open_path_is_stroke_only():
    """An open path has a stroke, no fill and no closing Z."""
    scene = _closed_square_scene()
    scene.add_path(PathRecord(
        path_id="line",
        path_type="path",
        closed=False,
        segments=[[50, 50], [150, 150]],
        stroke={"color": "#00ff00", "width": 3.0},
    ))
    svg = scene.export_svg()

    assert svg.count("<path ") == 2
    root = ET.fromstring(svg)
    line = root.find(f"{{{SVG_NS}}}path[@id='line']")

    assert line is not None
    assert line.get("d") == "M 50 50 L 150 150"
    assert "Z" not in line.get("d")
    assert "fill:none" in line.get("style")
    assert "stroke:#00ff00" in line.get("style")


def test_exported_svg_is_valid_xml_with_scene_dimensions():
    """The exported SVG parses as XML and carries the scene width, height and viewBox."""
    svg = _closed_square_scene().export_svg()
    root = ET.fromstring(svg)

    assert root.tag == f"{{{SVG_NS}}}svg"
    assert root.get("width") == "200"
    assert root.get("height") == "200"
    assert root.get("viewBox") == "0 0 200 200"


def test_export_writes_to_file(tmp_path):
    """Passing a filepath writes exactly the string that is returned."""
    scene = _closed_square_scene()
    target = tmp_path / "scene.svg"

    returned = scene.export_svg(filepath=str(target))

    assert target.read_text(encoding="utf-8") == returned


def test_path_without_geometry_is_skipped():
    """A path with no points is left out of the SVG entirely."""
    scene = MathScene(width=10, height=10)
    scene.add_path(PathRecord(path_id="empty", path_type="path", closed=True, segments=[]))

    svg = scene.export_svg()

    assert "<path " not in svg
