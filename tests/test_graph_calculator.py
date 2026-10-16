"""Tests for the LiSSARA Core graph canvas (app/graph_calculator.py).

The suite covers the pure grid math, the explicit viewport transform, Fit
View bounds and the guarantee that navigation never mutates reconstructed
geometry.  Qt runs on the offscreen platform so no display is required.

Tests that depend on committed ``outputs/`` fixtures (the reconstructed real
scene) skip when those artifacts are absent.
"""
from __future__ import annotations

import json
import os
from math import floor, log10
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QWheelEvent
from PySide6.QtWidgets import QApplication, QGraphicsScene

from app.graph_calculator import (APP_NAME, DEFAULT_CONTENT_RECT, MAX_VISIBLE_UNITS,
                                  MIN_VISIBLE_UNITS, GraphView,
                                  LissaraGraphCalculator, fit_scale, format_tick,
                                  grid_steps, image_to_graph, nice_step, zoom_center)

ROOT = Path(__file__).resolve().parents[1]
SCENE_DIR = ROOT / "outputs"
SCENE_JSON = SCENE_DIR / "scene.json"
SOURCE_IMAGE = SCENE_DIR / "input_preview.png"
fixtures_required = pytest.mark.skipif(
    not (SCENE_JSON.exists() and SOURCE_IMAGE.exists()),
    reason="committed outputs/ fixtures are absent",
)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def graph(qapp):
    scene = QGraphicsScene()
    view = GraphView(scene)
    view.resize(800, 600)
    view.show()
    qapp.processEvents()
    yield view
    view.hide()
    view.deleteLater()
    qapp.processEvents()


def _viewport_center(view: GraphView) -> QPoint:
    rect = view.viewport().rect()
    return QPoint(rect.width() // 2, rect.height() // 2)


# ------------------------------------------------------------------ grid math


@pytest.mark.parametrize("target,expected", [
    (0.04, 0.05), (0.7, 1.0), (1.0, 1.0), (1.5, 2.0), (2.0, 2.0), (2.5, 5.0),
    (3.0, 5.0), (7.0, 10.0), (72.0, 100.0), (500.0, 500.0), (750.0, 1000.0),
])
def test_nice_step_returns_125_family(target, expected):
    assert nice_step(target) == pytest.approx(expected)


def test_nice_step_is_exact_on_family_members():
    for exponent in range(-6, 7):
        for mantissa in (1.0, 2.0, 5.0):
            value = mantissa * 10.0 ** exponent
            assert nice_step(value) == pytest.approx(value)
            # Anything slightly larger jumps to the next family member.
            larger = value * (1.0 + 0.05)
            expected = {1.0: 2.0, 2.0: 5.0, 5.0: 10.0}[mantissa] * 10.0 ** exponent
            assert nice_step(larger) == pytest.approx(expected)


@pytest.mark.parametrize("scale", [0.01, 0.1, 0.5, 1.0, 3.0, 10.0, 50.0, 150.0])
def test_grid_steps_spacing_is_sensible_at_any_scale(scale):
    major, minor = grid_steps(scale)
    # Major lines cover roughly the 72 px target spacing, never 10x more.
    assert 60.0 <= major * scale <= 260.0
    assert major / 10.0 ** floor(log10(major)) in (1.0, 2.0, 5.0)
    # Minor lines stay separated on screen and divide the major step evenly.
    assert 7.0 <= minor * scale <= 80.0
    assert minor in (major / 5.0, major / 2.0)


def test_grid_density_changes_spacing():
    fine = grid_steps(1.0, density=0.5)[0]
    standard = grid_steps(1.0, density=1.0)[0]
    coarse = grid_steps(1.0, density=2.0)[0]
    assert fine < standard < coarse


def test_grid_steps_guard_invalid_scale():
    assert grid_steps(0.0) == (1.0, 0.2)
    assert grid_steps(-3.0) == (1.0, 0.2)


@pytest.mark.parametrize("value,expected", [
    (0.0, "0"), (-0.0, "0"), (100.0, "100"), (0.5, "0.5"), (-2.5, "-2.5"),
])
def test_format_tick(value, expected):
    assert format_tick(value) == expected


# ------------------------------------------------------- viewport transform math


def test_fit_scale_frames_rect_with_margin():
    # min() picks the binding axis, expanded by 7 % on every side.
    assert fit_scale(QRectF(-400, -250, 800, 500), 800, 600) == pytest.approx(
        min(800 / (800 * 1.14), 600 / (500 * 1.14)))


def test_fit_scale_handles_degenerate_rects():
    flat = QRectF(0, 0, 400, 0)
    square = QRectF(0, 0, 400, 400)
    assert fit_scale(flat, 800, 600) == pytest.approx(fit_scale(square, 800, 600))
    assert fit_scale(QRectF(0, 0, 0, 0), 800, 600) == pytest.approx(min(800, 600) / 1.14)
    assert fit_scale(QRectF(-5, -5, 10, 10), 0, 0) == 1.0


def test_zoom_center_keeps_cursor_scene_point_fixed():
    center = QPointF(40.0, -25.0)
    scale, new_scale = 2.0, 4.0
    pos = QPointF(650.0, 180.0)
    center_after = zoom_center(center, scale, new_scale, pos, 800, 600)
    scene_before = QPointF(center.x() + (pos.x() - 400) / scale,
                           center.y() - (pos.y() - 300) / scale)
    scene_after = QPointF(center_after.x() + (pos.x() - 400) / new_scale,
                          center_after.y() - (pos.y() - 300) / new_scale)
    assert (scene_after.x(), scene_after.y()) == pytest.approx((scene_before.x(), scene_before.y()))


# --------------------------------------------------------------- view behaviour


def test_default_view_centres_origin_with_y_up(graph):
    assert graph.view_center() == QPointF(0.0, 0.0)
    assert graph.view_scale() == pytest.approx(1.0)
    center = _viewport_center(graph)
    assert graph.mapFromScene(QPointF(0, 0)) == QPoint(400, 300)
    scene = graph.mapToScene(center)
    above = graph.mapToScene(center + QPoint(0, -40))
    below = graph.mapToScene(center + QPoint(0, 40))
    right = graph.mapToScene(center + QPoint(100, 0))
    assert above.y() > scene.y() > below.y()      # positive y points up
    assert right.x() > scene.x()
    assert (right.x() - scene.x()) == pytest.approx(100.0, abs=1.5)


def test_zoom_is_anchored_to_cursor(graph):
    for pos in (QPointF(650, 180), QPointF(60, 540), QPointF(400, 300)):
        graph.reset_view()
        before = graph.mapToScene(pos.toPoint())
        graph.zoom_at(QPointF(pos.x(), pos.y()), 1.4)
        after = graph.mapToScene(pos.toPoint())
        assert (after - before).manhattanLength() < 1.5


def test_wheel_event_zooms_to_cursor(graph):
    graph.reset_view()
    cursor = QPoint(620, 210)
    before = graph.mapToScene(cursor)
    event = QWheelEvent(QPointF(cursor), QPointF(cursor), QPoint(0, 0), QPoint(0, 120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    graph.wheelEvent(event)
    assert graph.view_scale() > 1.0
    after = graph.mapToScene(cursor)
    assert (after - before).manhattanLength() < 1.5


def test_pan_moves_content_with_pointer(graph):
    graph.reset_view()
    center_before = graph.view_center()
    graph.pan_by(150, -90)
    assert graph.view_center().x() == pytest.approx(center_before.x() - 150.0)
    assert graph.view_center().y() == pytest.approx(center_before.y() - 90.0)
    mid = _viewport_center(graph)
    assert graph.mapFromScene(graph.view_center()) == QPoint(mid.x(), mid.y())


def test_reset_view_restores_default(graph):
    graph.zoom_at(QPointF(100, 100), 4.0)
    graph.pan_by(200, 100)
    graph.reset_view()
    assert graph.view_center() == QPointF(0.0, 0.0)
    assert graph.view_scale() == pytest.approx(1.0)


def test_fit_rect_frames_geometry_with_margin(graph):
    target = QRectF(-400, -250, 800, 500)
    graph.set_content_rect(DEFAULT_CONTENT_RECT)
    graph.fit_rect(target)
    visible = graph.visible_scene_rect()
    assert visible.contains(target)
    assert (visible.width() - target.width()) > 0
    assert (visible.height() - target.height()) > 0
    center = graph.mapToScene(_viewport_center(graph))
    target_center = target.center()
    assert (center.x(), center.y()) == pytest.approx((target_center.x(), target_center.y()), abs=1.5)


def test_zoom_limits_keep_the_graph_usable(graph):
    graph.reset_view()
    for _ in range(200):
        graph.zoom_at(QPointF(400, 300), 0.5)
    visible = graph.visible_scene_rect()
    assert visible.width() <= MAX_VISIBLE_UNITS * 1.01
    assert visible.height() <= MAX_VISIBLE_UNITS * 1.01
    for _ in range(200):
        graph.zoom_at(QPointF(400, 300), 2.0)
    visible = graph.visible_scene_rect()
    assert visible.width() >= MIN_VISIBLE_UNITS * 0.99
    assert visible.height() >= MIN_VISIBLE_UNITS * 0.99


def test_pan_keeps_the_graph_reachable(graph):
    graph.reset_view()
    for sign in (-1, 1):
        graph.pan_by(sign * 500_000, sign * 500_000)
        center = graph.view_center()
        content = DEFAULT_CONTENT_RECT
        units = graph.viewport().width() / graph.view_scale()
        assert content.left() - units <= center.x() <= content.right() + units
        units_y = graph.viewport().height() / graph.view_scale()
        assert content.top() - units_y <= center.y() <= content.bottom() + units_y


def test_set_content_rect_falls_back_to_default(graph):
    graph.set_content_rect(QRectF())
    graph.set_content_rect(None)
    graph.pan_by(100_000, 100_000)
    assert graph.view_center().x() <= DEFAULT_CONTENT_RECT.right() + 1e3


def test_grid_lines_stay_bounded_at_extreme_zoom(graph):
    for scale in (0.005, 0.05, 1.0, 50.0):
        graph._view_scale = scale
        graph._view_center = QPointF(0.0, 0.0)
        graph._apply_view()
        major, minor = graph._grid_steps(scale)
        assert minor > 0.0
        assert graph.visible_scene_rect().width() / minor < 500


def test_background_draws_grid_axes_and_labels(graph):
    from app.graph_calculator import CANVAS_BG

    canvas = QColor(CANVAS_BG)      # the canvas is a soft tint, not pure white
    def render():
        image = QImage(400, 300, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        graph.render(painter, QRectF(0, 0, 400, 300), QRect(200, 150, 400, 300))
        painter.end()
        return image

    graph.setProperty("gridVisible", True)
    graph.viewport().update()
    with_grid = render()
    axis_pixel = QColor(with_grid.pixel(200, 150))
    assert axis_pixel != canvas            # axes cross at the origin
    lit = sum(1 for y in range(0, 300, 2) for x in range(0, 400, 2)
              if QColor(with_grid.pixel(x, y)) != canvas)

    graph.setProperty("gridVisible", False)
    graph.viewport().update()
    without_grid = render()
    lit_without = sum(1 for y in range(0, 300, 2) for x in range(0, 400, 2)
                      if QColor(without_grid.pixel(x, y)) != canvas)
    assert lit_without < lit
    assert QColor(without_grid.pixel(200, 150)) != canvas  # axes remain
    graph.setProperty("gridVisible", True)


def test_grid_density_property_changes_step(graph):
    graph.setProperty("gridDensity", "Fine")
    fine = graph._grid_steps(1.0)[0]
    graph.setProperty("gridDensity", "Standard")
    standard = graph._grid_steps(1.0)[0]
    graph.setProperty("gridDensity", "Coarse")
    coarse = graph._grid_steps(1.0)[0]
    assert fine < standard < coarse
    graph.setProperty("gridDensity", "Standard")


# ------------------------------------------------------------- full application


@pytest.fixture(scope="module")
def window(qapp):
    win = LissaraGraphCalculator()
    win.resize(1440, 900)
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


def test_window_is_titled_lissara_core(window):
    assert APP_NAME == "LiSSARA Core"
    assert window.windowTitle() == "LiSSARA Core"


@fixtures_required
def test_geometry_bounds_match_reconstructed_scene(loaded_window):
    data = json.loads(SCENE_JSON.read_text(encoding="utf-8"))
    xs, ys = [], []
    for path in data["paths"]:
        for segment in path.get("segments") or []:
            for x, y in segment["control_points"]:
                xs.append(x - data["width"] / 2)
                ys.append(data["height"] / 2 - y)
    expected = (min(xs), min(ys), max(xs), max(ys))
    rect = loaded_window._geometry_rect()
    actual = (rect.left(), rect.top(), rect.right(), rect.bottom())
    assert all(a == pytest.approx(b, abs=2.0) for a, b in zip(actual, expected))


@fixtures_required
def test_fit_view_frames_every_reconstructed_path(loaded_window):
    loaded_window.graph.set_content_rect(loaded_window._image_content_rect())
    loaded_window._set_layer("curves", True)
    loaded_window._fit_view()
    visible = loaded_window.graph.visible_scene_rect().adjusted(-1, -1, 1, 1)
    unframed = [name for name, item in loaded_window.path_items.items()
                if not visible.contains(item.boundingRect())]
    assert unframed == []
    assert loaded_window.graph.view_scale() > 0.0


@fixtures_required
def test_navigation_never_modifies_reconstructed_geometry(loaded_window):
    def snapshot(items):
        return tuple((item.path().elementAt(index).x, item.path().elementAt(index).y)
                     for item in items
                     for index in range(item.path().elementCount()))

    curves = list(loaded_window.path_items.values())
    before = snapshot(curves)
    positions_before = [item.pos() for item in loaded_window.scene.items()]
    for _ in range(5):
        loaded_window.graph.zoom_at(QPointF(700, 400), 1.35)
    loaded_window.graph.pan_by(220, -140)
    loaded_window._fit_view()
    loaded_window.graph.reset_view()
    assert snapshot(curves) == before
    assert [item.pos() for item in loaded_window.scene.items()] == positions_before


@fixtures_required
def test_original_image_overlay_aligns_with_curves(loaded_window):
    data = json.loads(SCENE_JSON.read_text(encoding="utf-8"))
    overlay = next((item for item in loaded_window.scene.items()
                    if item.data(0) == "original"), None)
    assert overlay is not None
    half_w, half_h = data["width"] / 2, data["height"] / 2
    assert overlay.pos() == QPointF(-half_w, -half_h)
    assert overlay.pixmap().width() == data["width"]
    assert overlay.pixmap().height() == data["height"]
    # A curve control point must land exactly on the Cartesian image frame.
    first_path = data["paths"][0]
    first_point = first_path["segments"][0]["control_points"][0]
    expected = image_to_graph(*first_point, data["width"], data["height"])
    first_item = list(loaded_window.path_items.values())[0]
    element = first_item.path().elementAt(0)
    assert (element.x, element.y) == pytest.approx((expected.x(), expected.y()))


@fixtures_required
def test_clicking_a_curve_syncs_selection_without_reanalysis(loaded_window):
    output_dir = loaded_window.output_dir
    name = next(iter(loaded_window.path_items))
    loaded_window._select_path(name)
    assert loaded_window.tree.currentItem() is loaded_window.path_tree_items[name]
    assert loaded_window.selected_path == name
    assert loaded_window.path_items[name].pen().widthF() == 3.6
    # Other paths drop back to the base weight.
    other = next(n for n in loaded_window.path_items if n != name)
    assert loaded_window.path_items[other].pen().widthF() == 1.8
    assert loaded_window.output_dir is output_dir
    assert "cubic" in loaded_window.inspect.text()


@fixtures_required
def test_layer_toggles_hide_and_show_curves(loaded_window):
    loaded_window._set_layer("curves", False)
    assert not any(item.isVisible() for item in loaded_window.path_items.values())
    loaded_window._set_layer("curves", True)
    assert all(item.isVisible() for item in loaded_window.path_items.values())


@fixtures_required
def test_inspector_shows_segment_equation_on_demand(loaded_window):
    tree = loaded_window.path_tree_items[next(iter(loaded_window.path_tree_items))]
    segment = tree.child(0)
    loaded_window.tree.setCurrentItem(segment)
    text = loaded_window.inspect.text()
    assert "x(t) =" in text and "y(t) =" in text and "P0=" in text
    assert loaded_window.control_items  # highlight, guide polygon and 4 dots
