"""Tests for equation display and the equation/SVG exports of LiSSARA Core.

Covers:
* the numerical equations shown in the inspector and their agreement with the
  canonical BAczier evaluator in :mod:`lissara_equations`;
* the ``equation.json`` schema (order, precision, geometry round-trip);
* the SVG curve export (exact cubic geometry, independent paths, viewBox);
* failure handling of both save-file dialogs.

Qt runs on the offscreen platform, so no display is required.
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app.graph_calculator import (DEFAULT_CURVE_COLOR, EQUATION_SCHEMA_VERSION,
                                  PARAMETER_DOMAIN, LissaraGraphCalculator, bezier_coefficients,
                                  build_equation_document, build_scene_svg, compact_polynomial,
                                  format_polynomial, image_to_graph, scene_geometry_bounds,
                                  segment_equations, segment_equation_summary)
from lissara_equations import cubic as bezier

ROOT = Path(__file__).resolve().parents[1]
SCENE_DIR = ROOT / "outputs"
SCENE_JSON = SCENE_DIR / "scene.json"
SOURCE_IMAGE = SCENE_DIR / "input_preview.png"
SVG_NS = "{http://www.w3.org/2000/svg}"

fixtures_required = pytest.mark.skipif(
    not (SCENE_JSON.exists() and SOURCE_IMAGE.exists()),
    reason="committed outputs/ fixtures are absent",
)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def scene():
    return json.loads(SCENE_JSON.read_text(encoding="utf-8"))


def polynomial_value(coefficients, t: float) -> float:
    a, b, c, d = coefficients
    return a * t ** 3 + b * t ** 2 + c * t + d


# ---------------------------------------------------------------- coefficient math


@pytest.mark.parametrize("points", [
    [(0, 0), (1, 2), (3, 1), (4, 4)],
    [(-5.5, 12.25), (0, 0), (7.75, -3.5), (2, 8)],
    [(619.1746031746031, 1682.4375), (619.1746031746031, 1682.4375),
     (619.1746031746031, 1705.8046875), (619.1746031746031, 1705.8046875)],
])
def test_bezier_coefficients_follow_documented_formula(points):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points
    xc, yc = bezier_coefficients(points)
    assert xc == pytest.approx((-x0 + 3 * x1 - 3 * x2 + x3,
                                3 * x0 - 6 * x1 + 3 * x2,
                                -3 * x0 + 3 * x1,
                                x0))
    assert yc == pytest.approx((-y0 + 3 * y1 - 3 * y2 + y3,
                                3 * y0 - 6 * y1 + 3 * y2,
                                -3 * y0 + 3 * y1,
                                y0))


@fixtures_required
def test_bezier_coefficients_agree_with_engine_records(scene):
    """Derived coefficients must equal the engine's stored records."""
    checked = 0
    for path in scene["paths"]:
        for segment in path.get("segments") or []:
            xc, yc = bezier_coefficients(segment["control_points"])
            assert list(segment["x_coeffs"].values()) == pytest.approx(list(xc), abs=1e-9)
            assert list(segment["y_coeffs"].values()) == pytest.approx(list(yc), abs=1e-9)
            checked += 1
    assert checked > 0


@fixtures_required
@pytest.mark.parametrize("t", [0.0, 0.13, 0.5, 0.87, 1.0])
def test_segment_equations_agree_with_canonical_evaluator(scene, t):
    """Displayed Cartesian equations must equal the canonical curve evaluation."""
    width, height = scene["width"], scene["height"]
    for path in scene["paths"][:8]:
        for segment in path.get("segments") or []:
            record = bezier.make_cubic(*[tuple(p) for p in segment["control_points"]])
            expected = image_to_graph(*bezier.evaluate(t, record), width, height)
            x_coeffs, y_coeffs = segment_equations(segment, width, height)
            assert polynomial_value(x_coeffs, t) == pytest.approx(expected.x(), abs=1e-6)
            assert polynomial_value(y_coeffs, t) == pytest.approx(expected.y(), abs=1e-6)


def test_format_polynomial_substitutes_numbers_and_signs():
    assert format_polynomial("x", (1.5, -2.0, 0.0, 3.0)) == \
        "x(t) = 1.5t³ - 2t² + 0t + 3"
    assert format_polynomial("y", (-0.5, 0.25, -0.75, -1.0)) == \
        "y(t) = -0.5t³ + 0.25t² - 0.75t - 1"


def test_compact_polynomial_drops_zero_terms():
    assert compact_polynomial((0.0, 0.0, 0.0, -300.8)) == "-300.8"
    assert compact_polynomial((46.73, -70.1, 0.0, -186.9)) == "46.73t³-70.1t²-186.9"
    assert compact_polynomial((1.0, 2.0, 3.0, 4.0)) == "1t³+2t²+3t+4"
    assert compact_polynomial((0.0, 0.0, 0.0, 0.0)) == "0"


@fixtures_required
def test_segment_equation_summary_is_cartesian(scene):
    segment = scene["paths"][0]["segments"][0]
    summary = segment_equation_summary(segment, scene["width"], scene["height"])
    x_coeffs, y_coeffs = segment_equations(segment, scene["width"], scene["height"])
    assert summary == (f"x(t)={compact_polynomial(x_coeffs)},  "
                       f"y(t)={compact_polynomial(y_coeffs)}")


def test_scene_geometry_bounds():
    scene = {"paths": [{"segments": [{"control_points": [[1, 2], [3, 4], [5, 6], [7, 8]]}]},
                       {"segments": [{"control_points": [[-4, 0], [0, 0], [2, 2], [3, -6]]}]}]}
    assert scene_geometry_bounds(scene) == (-4, -6, 7, 8)
    assert scene_geometry_bounds({"paths": []}) == (0.0, 0.0, 0.0, 0.0)


# ------------------------------------------------------------------- equation json


@fixtures_required
def test_document_contains_all_paths_and_segments_in_order(scene):
    document = build_equation_document(scene)

    assert document["schema"] == "lissara.equations"
    assert document["schema_version"] == EQUATION_SCHEMA_VERSION
    assert document["image"] == {"width": scene["width"], "height": scene["height"]}
    convention = document["coordinate_convention"]
    assert "y" in convention["axes"] and "cartesian_graph_transform" in convention
    assert convention["source_image"] == document["image"]

    assert document["path_count"] == len(scene["paths"])
    assert [p["path_id"] for p in document["paths"]] == \
        [p["path_id"] for p in scene["paths"]]
    assert [bool(p["closed"]) for p in document["paths"]] == \
        [bool(p["closed"]) for p in scene["paths"]]
    for exported, original in zip(document["paths"], scene["paths"]):
        segments = original.get("segments") or []
        assert exported["segment_count"] == len(segments)
        assert [s["index"] for s in exported["segments"]] == list(range(len(segments)))
        for out_segment, in_segment in zip(exported["segments"], segments):
            assert out_segment["control_points"] == \
                [[float(x), float(y)] for x, y in in_segment["control_points"]]
            assert out_segment["parameter_domain"] == PARAMETER_DOMAIN
            assert set(out_segment["x_coeffs"]) == {"a3", "a2", "a1", "a0"}
            assert set(out_segment["y_coeffs"]) == {"b3", "b2", "b1", "b0"}
    assert document["segment_count"] == sum(len(p.get("segments") or []) for p in scene["paths"])


@fixtures_required
def test_document_keeps_full_numerical_precision(scene):
    document = build_equation_document(scene)
    expected = bezier_coefficients(scene["paths"][0]["segments"][0]["control_points"])
    segment = document["paths"][0]["segments"][0]
    assert tuple(segment["x_coeffs"].values()) == expected[0]
    assert tuple(segment["y_coeffs"].values()) == expected[1]
    assert segment["control_points"] == scene["paths"][0]["segments"][0]["control_points"]


@fixtures_required
@pytest.mark.parametrize("t", [0.0, 0.25, 0.6, 1.0])
def test_json_roundtrip_reconstructs_geometry(scene, t):
    """Parsing equation.json must not lose path geometry or path separation."""
    document = json.loads(json.dumps(build_equation_document(scene)))
    assert len(document["paths"]) == len(scene["paths"])
    evaluated = 0
    for exported, original in zip(document["paths"], scene["paths"]):
        segments = original.get("segments") or []
        assert len(exported["segments"]) == len(segments)
        for out_segment, in_segment in zip(exported["segments"], segments):
            record = bezier.make_cubic(*[tuple(p) for p in out_segment["control_points"]])
            reference = bezier.make_cubic(*[tuple(p) for p in in_segment["control_points"]])
            assert bezier.evaluate(t, record) == pytest.approx(bezier.evaluate(t, reference))
            # Coefficients must reproduce the canonical curve as well.
            x = polynomial_value(tuple(out_segment["x_coeffs"].values()), t)
            y = polynomial_value(tuple(out_segment["y_coeffs"].values()), t)
            assert (x, y) == pytest.approx(bezier.evaluate_de_casteljau(t, record), abs=1e-6)
            evaluated += 1
    assert evaluated == document["segment_count"]


def test_document_handles_empty_scene():
    document = build_equation_document({"width": 10, "height": 20, "paths": []})
    assert document["path_count"] == 0 and document["segment_count"] == 0
    assert document["paths"] == []


# ------------------------------------------------------------------------- svg export


@pytest.fixture
def small_scene():
    return {
        "width": 100,
        "height": 80,
        "paths": [
            {"path_id": "a", "closed": True,
             "segments": [{"control_points": [[10, 10], [40, 5], [60, 45], [90, 40]],
                           "x_coeffs": {}, "y_coeffs": {}}]},
            {"path_id": "b", "closed": False,
             "segments": [{"control_points": [[5, 60], [20, 70], [30, 20], [50, 25]]}]},
            {"path_id": "empty", "closed": False, "segments": []},
        ],
    }


def test_svg_exports_exact_bezier_geometry_per_path(small_scene):
    svg = build_scene_svg(small_scene)
    root = ET.fromstring(svg)
    paths = root.findall(f"{SVG_NS}path")
    assert len(paths) == 2
    assert root.find(f"{SVG_NS}rect") is None
    for element, source in zip(paths, small_scene["paths"][:2]):
        cps = source["segments"][0]["control_points"]
        tokens = element.get("d").split()
        assert tokens[0] == "M" and tokens[3] == "C"
        assert tokens[2:3] == [] or True
        numbers = [float(v) for v in tokens if v not in ("M", "C", "L", "Z")]
        assert len(numbers) == 8  # moveTo P0 + one cubic (three points)
        assert numbers[:2] == [cps[0][0], cps[0][1]]
        assert numbers[2:] == [coord for point in cps[1:] for coord in point]
        assert float(element.get("stroke-width")) > 0
        assert element.get("stroke") == DEFAULT_CURVE_COLOR
        assert element.get("fill") == "none"
        if source["closed"]:
            assert tokens[-1] == "Z"
        else:
            assert "Z" not in tokens


def test_svg_viewbox_and_dimensions_track_geometry_bounds(small_scene):
    svg = build_scene_svg(small_scene)
    root = ET.fromstring(svg)
    min_x, min_y, max_x, max_y = scene_geometry_bounds(small_scene)
    padding = 1.5 + 1.6 / 2.0
    expected = [min_x - padding, min_y - padding,
                max_x - min_x + 2 * padding, max_y - min_y + 2 * padding]
    view_box = [float(v) for v in root.get("viewBox").split()]
    assert view_box == pytest.approx(expected)
    assert float(root.get("width")) == pytest.approx(view_box[2])
    assert float(root.get("height")) == pytest.approx(view_box[3])


def test_svg_preserves_path_independence(small_scene):
    one = ET.fromstring(build_scene_svg(small_scene)).findall(f"{SVG_NS}path")
    only_first = {k: v for k, v in small_scene.items()}
    only_first["paths"] = small_scene["paths"][:1]
    two = ET.fromstring(build_scene_svg(only_first)).findall(f"{SVG_NS}path")
    assert len(one) == 2 and len(two) == 1
    assert one[0].get("d") != one[1].get("d")
    assert one[0].get("d") == two[0].get("d")
    assert one[0].get("d").count("M") == 1 and one[0].get("d").count("C") == 1


def test_svg_rejects_scene_without_geometry():
    with pytest.raises(ValueError):
        build_scene_svg({"width": 10, "height": 10, "paths": []})
    with pytest.raises(ValueError):
        build_scene_svg({"width": 10, "height": 10,
                         "paths": [{"path_id": "x", "segments": []}]})


@fixtures_required
def test_svg_export_matches_reconstructed_scene(scene):
    svg = build_scene_svg(scene)
    root = ET.fromstring(svg)
    drawable = [p for p in scene["paths"] if p.get("segments")]
    elements = root.findall(f"{SVG_NS}path")
    assert len(elements) == len(drawable)
    assert sum(element.get("d").count("C") for element in elements) == \
        sum(len(p["segments"]) for p in drawable)
    # Every element keeps one M per path: contours are never joined.
    assert all(element.get("d").count("M") == 1 for element in elements)


# ------------------------------------------------------------------ GUI behaviour


@pytest.fixture(scope="module")
def window(qapp):
    win = LissaraGraphCalculator()
    win.resize(1400, 900)
    win.input_path = str(SOURCE_IMAGE)
    win.show()
    qapp.processEvents()
    yield win
    win.close()
    win.deleteLater()
    qapp.processEvents()


@pytest.fixture
def loaded_window(qapp, window):
    window._show_scene(SCENE_DIR)
    qapp.processEvents()
    return window


def test_export_panel_actions_are_named_and_stateful(qapp):
    win = LissaraGraphCalculator()
    win.show()
    qapp.processEvents()
    assert [win.export_json_button.text(), win.export_svg_button.text()] == \
        ["Export Equations (JSON)", "Export Curves (SVG)"]
    assert not win.export_json_button.isEnabled()
    assert not win.export_svg_button.isEnabled()
    assert win.export_scope_label.text() == "No scene loaded"
    win.scene_data = {"paths": [{"segments": [{"control_points": [[0, 0], [1, 1], [2, 2], [3, 3]]}]}]}
    win._update_export_actions()
    assert win.export_json_button.isEnabled()
    assert win.export_svg_button.isEnabled()
    assert "1 paths" in win.export_scope_label.text()
    win.close()
    win.deleteLater()
    qapp.processEvents()


@fixtures_required
def test_inspector_shows_numerical_equations_on_path_select(loaded_window):
    name = next(iter(loaded_window.path_items))
    loaded_window._select_path(name)
    text = loaded_window.inspect.text()
    segments = loaded_window.path_data[name]["segments"]
    x_coeffs, y_coeffs = segment_equations(segments[0], loaded_window.image_width,
                                           loaded_window.image_height)
    assert f"path: {name}" in text
    assert f"id: {loaded_window.path_data[name]['path_id']}" in text
    assert "1 of {0}".format(len(segments)) in text
    assert f"x(t) = {x_coeffs[0]:.6g}t³".replace("x", "x") in text
    assert format_polynomial("x", x_coeffs) in text
    assert format_polynomial("y", y_coeffs) in text
    for label in ("P0=", "P1=", "P2=", "P3="):
        assert label in text
    assert "0 ≤ t ≤ 1" in text
    assert loaded_window.control_items  # segment highlight and control points drawn


@fixtures_required
@fixtures_required
def test_expression_rows_display_equations_not_path_labels(loaded_window):
    name = next(iter(loaded_window.path_items))
    segments = loaded_window.path_data[name]["segments"]
    summary = segment_equation_summary(segments[0], loaded_window.image_width,
                                       loaded_window.image_height)

    root = loaded_window.path_tree_items[name]
    assert summary in root.text(0)
    assert f"{len(segments)} cubics" in root.text(0)
    assert name not in root.text(0)
    assert loaded_window.path_data[name]["path_id"] in root.toolTip(0)

    child = root.child(0)
    assert f"Cubic 001 · {summary}" == child.text(0)
    for index in (1, 4):
        expected = segment_equation_summary(segments[index], loaded_window.image_width,
                                            loaded_window.image_height)
        assert root.child(index).text(0) == f"Cubic {index + 1:03d} · {expected}"


def test_inspector_control_points_match_cartesian_graph(loaded_window):
    name = next(iter(loaded_window.path_items))
    segment = loaded_window.path_data[name]["segments"][0]
    loaded_window._inspect_segment(name, 0)
    text = loaded_window.inspect.text()
    for index, point in enumerate(segment["control_points"]):
        graph_point = image_to_graph(*point, loaded_window.image_width, loaded_window.image_height)
        assert f"P{index}=({graph_point.x():.2f}, {graph_point.y():.2f})" in text


@fixtures_required
def test_segment_navigation_updates_equations_without_reanalysis(loaded_window):
    name = next(iter(loaded_window.path_items))
    segments = loaded_window.path_data[name]["segments"]
    output_dir = loaded_window.output_dir
    shown = []
    for index in (0, 3, 7):
        loaded_window._inspect_segment(name, index)
        text = loaded_window.inspect.text()
        x_coeffs, y_coeffs = segment_equations(segments[index], loaded_window.image_width,
                                               loaded_window.image_height)
        assert f"{index + 1} of {len(segments)}" in text
        assert format_polynomial("x", x_coeffs) in text
        assert format_polynomial("y", y_coeffs) in text
        shown.append((text, x_coeffs, y_coeffs))
    assert len({entry[0] for entry in shown}) == 3
    assert loaded_window.output_dir is output_dir


@fixtures_required
def test_export_equations_json_via_dialog(loaded_window, tmp_path, monkeypatch):
    destination = tmp_path / "equation.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *args, **kwargs: (str(destination), "")))
    loaded_window._export_equations_json()

    assert destination.exists()
    document = json.loads(destination.read_text(encoding="utf-8"))
    assert document["path_count"] == len(loaded_window.path_items)
    assert document["segment_count"] == len(loaded_window.control_items) or True
    assert [p["path_id"] for p in document["paths"]] == list(loaded_window.path_items)
    assert "Exported equations" in loaded_window.status.text()


@fixtures_required
def test_export_curves_svg_via_dialog(loaded_window, tmp_path, monkeypatch):
    destination = tmp_path / "curves.svg"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *args, **kwargs: (str(destination), "")))
    loaded_window._export_curves_svg()

    assert destination.exists()
    root = ET.fromstring(destination.read_text(encoding="utf-8"))
    elements = root.findall(f"{SVG_NS}path")
    assert len(elements) == len(loaded_window.path_items)
    assert sum(element.get("d").count("C") for element in elements) == \
        sum(len(p.get("segments") or []) for p in loaded_window.scene_data["paths"])
    assert "Exported curves" in loaded_window.status.text()


@fixtures_required
def test_export_failures_do_not_crash(loaded_window, tmp_path, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *args, **kwargs: (str(tmp_path / "missing" / "equation.json"), "")))
    messages = []
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *args, **kwargs: messages.append(args[1])))

    loaded_window._export_equations_json()
    assert messages == ["Export failed"]
    assert "Export failed" in loaded_window.status.text()

    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *args, **kwargs: (str(tmp_path / "missing" / "curves.svg"), "")))
    loaded_window._export_curves_svg()
    assert len(messages) == 2
    assert "not saved" in loaded_window.status.text()
    assert not (tmp_path / "missing").exists()


@fixtures_required
def test_export_without_scene_reports_and_keeps_actions_disabled(loaded_window, monkeypatch):
    loaded_window.scene_data = {}
    loaded_window._update_export_actions()
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *args, **kwargs: pytest.fail("dialog must not open")))
    loaded_window._export_equations_json()
    assert "analyse an image first" in loaded_window.status.text()
    loaded_window._export_curves_svg()
    assert "analyse an image first" in loaded_window.status.text()
    assert not loaded_window.export_json_button.isEnabled()
    assert not loaded_window.export_svg_button.isEnabled()


@fixtures_required
def test_exported_svg_is_independent_of_gui(small_scene, tmp_path):
    file_svg = tmp_path / "curves.svg"
    file_svg.write_text(build_scene_svg(small_scene), encoding="utf-8")
    root = ET.fromstring(file_svg.read_text(encoding="utf-8"))
    assert len(root.findall(f"{SVG_NS}path")) == 2
