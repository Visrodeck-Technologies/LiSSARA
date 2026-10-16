"""Tests for the LiSSARA Core workspace: centered title, drawers, colours.

Covers the graph-calculator shell (centered application title, right-side
upload drawer, left-side export drawer) and the per-expression colour model
(black defaults, isolated colour changes, persistence across selection and
navigation).  Qt runs on the offscreen platform, so no display is required.
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPointF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication, QColorDialog, QFileDialog

from app.graph_calculator import (COLOR_ROLE, DEFAULT_CURVE_COLOR,
                                  UPLOAD_PANEL_WIDTH, LissaraGraphCalculator, svg_icon,
                                  EXPORT_ICON_SVG)

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


@pytest.fixture
def window(qapp):
    win = LissaraGraphCalculator()
    win.resize(1440, 900)
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


@pytest.fixture
def sample_image(tmp_path) -> Path:
    image = QImage(120, 80, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    with QPainter(image) as painter:
        painter.setPen(QColor("black"))
        painter.drawRect(10, 10, 100, 60)
    path = tmp_path / "sample.png"
    assert image.save(str(path))
    return path


# ------------------------------------------------------------------ title and shell


def test_window_title_is_lissara_core(window):
    assert window.windowTitle() == "LiSSARA Core"
    assert window.top_bar_title.text() == "LiSSARA Core"


def test_application_title_is_centred_in_window(qapp):
    win = LissaraGraphCalculator()
    win.resize(1600, 900)
    win.show()
    qapp.processEvents()
    title = win.top_bar_title
    centre = title.mapTo(win, title.rect().center()).x()
    assert centre == pytest.approx(win.width() / 2, abs=2)
    win.resize(1000, 900)
    qapp.processEvents()
    centre = title.mapTo(win, title.rect().center()).x()
    assert centre == pytest.approx(win.width() / 2, abs=2)
    win.close()
    win.deleteLater()
    qapp.processEvents()


def test_graph_options_survive_the_refactor(window):
    assert window.upload_button.text() == "Upload Image"
    assert window.analyse_button.text() == "Analyse"
    assert window.fit_button.text() == "Fit View"
    assert window.reset_button.text() == "Reset View"
    assert [window.grid_combo.itemText(i) for i in range(window.grid_combo.count())] == \
        ["Standard", "Fine", "Coarse"]
    assert set(window.layers) == {"original", "edges", "curves"}


def test_upload_panel_is_open_by_default_and_export_is_not(window):
    assert not window.export_panel.isVisible()
    assert window.upload_panel.isVisible()
    assert window.upload_panel.width() == pytest.approx(UPLOAD_PANEL_WIDTH, abs=4)
    window._toggle_upload_panel()
    assert not window.upload_panel.isVisible()
    window._toggle_upload_panel()
    assert window.upload_panel.isVisible()
    assert window.upload_panel.width() == pytest.approx(UPLOAD_PANEL_WIDTH, abs=4)
    window._toggle_export_panel()
    assert window.export_panel.isVisible()
    window._toggle_export_panel()
    assert not window.export_panel.isVisible()


def test_export_popup_is_an_overlay_not_a_drawer(window):
    assert window.export_panel.parent() is window
    columns = [window.splitter.widget(i).objectName() for i in range(window.splitter.count())]
    assert columns == ["expressionPanel", "graphView", "uploadPanel"]
    base = window.splitter.sizes()
    window._toggle_export_panel()
    assert window.export_panel.isVisible()
    assert window.splitter.sizes() == base
    assert window.export_panel.geometry().right() <= window.width()
    assert window.export_panel.geometry().bottom() <= window.height()
    window._toggle_export_panel()


def test_export_popup_anchors_under_the_icon_and_follows_resize(window, qapp):
    window._toggle_export_panel()
    icon = window.export_icon_button.mapTo(window, icon_point(window.export_icon_button))
    assert window.export_panel.pos().x() == pytest.approx(icon.x(), abs=2)
    assert window.export_panel.pos().y() > icon.y()
    window.resize(900, 620)
    qapp.processEvents()
    assert window.export_panel.isVisible()
    assert window.export_panel.geometry().right() <= window.width()
    assert window.export_panel.geometry().bottom() <= window.height()


def icon_point(button) -> QPointF:
    return QPointF(0, button.height())


def test_export_popup_closes_on_outside_click(window, qapp):
    window._toggle_export_panel()
    event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(50, 50), QPointF(50, 50),
                       QPointF(50, 50), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)
    app_send(window.graph.viewport(), event)
    assert not window.export_panel.isVisible()
    window._toggle_export_panel()
    inside = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(20, 20), QPointF(20, 20),
                        QPointF(20, 20), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    app_send(window.export_json_button, inside)
    assert window.export_panel.isVisible()


def app_send(widget, event):
    QApplication.instance().sendEvent(widget, event)


def _real_click(window, qapp, widget):
    """Click ``widget`` through the native window, like a real mouse would.

    ``sendEvent`` on a widget skips the window-level delivery that the app
    event filter also sees, which is exactly where the export popup once broke.
    """
    from PySide6.QtTest import QTest

    position = widget.mapTo(window, widget.rect().center())
    QTest.mouseClick(window.windowHandle(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, position)
    for _ in range(4):
        qapp.processEvents()


@fixtures_required
def test_export_buttons_work_with_real_mouse_clicks(loaded_window, qapp, monkeypatch, tmp_path):
    saved = []

    def fake_dialog(*args, **kwargs):
        target = tmp_path / ("equation.json" if "JSON" in args[1] else "curves.svg")
        saved.append(target)
        return str(target), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake_dialog))
    _real_click(loaded_window, qapp, loaded_window.export_icon_button)
    assert loaded_window.export_panel.isVisible()
    _real_click(loaded_window, qapp, loaded_window.export_json_button)
    assert [path.name for path in saved] == ["equation.json"]
    assert saved[0].exists()
    assert json.loads(saved[0].read_text(encoding="utf-8"))["path_count"] == \
        len(loaded_window.path_items)
    # The popup stays open so a second export is one click away.
    assert loaded_window.export_panel.isVisible()
    _real_click(loaded_window, qapp, loaded_window.export_svg_button)
    assert [path.name for path in saved] == ["equation.json", "curves.svg"]
    ET.fromstring(saved[1].read_text(encoding="utf-8"))


def test_export_popup_toggles_and_closes_with_real_clicks(window, qapp):
    _real_click(window, qapp, window.export_icon_button)
    assert window.export_panel.isVisible()
    _real_click(window, qapp, window.export_icon_button)
    assert not window.export_panel.isVisible()
    _real_click(window, qapp, window.export_icon_button)
    assert window.export_panel.isVisible()
    _real_click(window, qapp, window.graph.viewport())
    assert not window.export_panel.isVisible()


def test_export_popup_closes_on_escape(window, qapp):
    window._toggle_export_panel()
    qapp.sendEvent(window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                    Qt.KeyboardModifier.NoModifier))
    assert not window.export_panel.isVisible()


def test_file_icon_is_an_svg_glyph(window):
    assert not window.export_icon_button.icon().isNull()
    assert window.export_icon_button.iconSize() == QSize(18, 18)
    assert not window.export_icon_button.text()


def test_svg_icon_renders_dark_glyph():
    icon = svg_icon(EXPORT_ICON_SVG, size=24, color="#4d5561")
    assert not icon.isNull()
    pixmap = icon.pixmap(QSize(24, 24)).toImage()
    opaque = 0
    for y in range(pixmap.height()):
        for x in range(pixmap.width()):
            if pixmap.pixelColor(x, y).alpha() > 24:
                opaque += 1
    assert 40 < opaque < 24 * 24  # a real glyph: visible but not a filled square


@fixtures_required
def test_opening_panels_keeps_graph_state(loaded_window):
    graph = loaded_window.graph
    loaded_window.graph.zoom_at(QPointF(700, 400), 2.0)
    loaded_window._select_path(next(iter(loaded_window.path_items)))
    scale, center, selection = graph.view_scale(), graph.view_center(), loaded_window.selected_path
    loaded_window._toggle_export_panel()
    loaded_window._toggle_upload_panel()
    assert (graph.view_scale(), graph.view_center()) == (scale, center)
    assert loaded_window.selected_path == selection
    loaded_window._toggle_export_panel()
    loaded_window._toggle_upload_panel()
    assert (graph.view_scale(), graph.view_center()) == (scale, center)


# ------------------------------------------------------------------ upload drawer


def test_choose_file_loads_image_into_panel(window, sample_image, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *args, **kwargs: (str(sample_image), "")))
    assert window.upload_panel.isVisible()
    window.choose_file_button.click()
    assert window.input_path == str(sample_image)
    assert window.upload_filename.text() == "sample.png"
    assert "120 × 80" in window.upload_dimensions.text()
    assert not window.upload_preview.pixmap().isNull()
    assert window.upload_analyse_button.isEnabled()
    assert "Ready" in window.upload_status.text()


def test_paste_image_from_clipboard(window, qapp, monkeypatch, tmp_path):
    image = QImage(64, 64, QImage.Format.Format_RGB32)
    image.fill(QColor("#204080"))
    qapp.clipboard().setImage(image)
    window.paste_button.click()
    assert window.input_path
    stored = QImage(window.input_path)
    assert not stored.isNull()
    assert (stored.width(), stored.height()) == (64, 64)
    assert window.upload_dimensions.text() == "64 × 64 px"
    Path(window.input_path).unlink(missing_ok=True)


def test_drop_zone_loads_image(window, sample_image):
    window.drop_zone.image_dropped.emit(str(sample_image))
    assert window.input_path == str(sample_image)
    assert window.upload_filename.text() == "sample.png"


def test_upload_button_toggles_the_panel(window):
    window.upload_button.click()
    assert not window.upload_panel.isVisible()
    window.upload_button.click()
    assert window.upload_panel.isVisible()


def test_panels_are_separated_by_thin_sashes(window):
    from app.graph_calculator import SashHandle, SashSplitter

    assert isinstance(window.splitter, SashSplitter)
    for index in (1, 2):
        handle = window.splitter.handle(index)
        assert isinstance(handle, SashHandle)
        assert handle.isVisible()
    # painting a sash must not raise, hovered or not
    handle = window.splitter.handle(1)
    handle._hover = True
    assert not handle.grab().isNull()
    handle._hover = False
    assert not handle.grab().isNull()


def test_navbar_is_dark_and_grouped(window):
    window.grab()
    assert window.findChild(type(window.top_bar_title.parent()), "topBar") is not None
    assert len(window.findChildren(type(window.top_bar_title.parent()), "segGroup")) == 1
    assert [button.property("seg") for button in window.layers.values()] == \
        ["first", "mid", "last"]
    assert not window.upload_button.icon().isNull()
    assert not window.analyse_button.icon().isNull()


def test_analyse_without_image_opens_upload_panel(window):
    window._toggle_upload_panel()
    assert not window.upload_panel.isVisible()
    window.input_path = None
    window._analyse()
    assert window.upload_panel.isVisible()
    assert not hasattr(window, "_worker")
    assert "upload panel" in window.status.text()


@fixtures_required
def test_analyse_runs_pipeline_from_panel(loaded_window, qapp, sample_image, monkeypatch):
    """The upload panel drives the existing worker-thread reconstruction."""
    from PySide6.QtCore import QObject, Signal

    started = []

    class FakeWorker(QObject):
        finished = Signal(str, str)

        def __init__(self, image_path, output_dir):
            super().__init__()
            self.image_path = image_path
            self.output_dir = Path(output_dir)
            started.append(str(image_path))

        def run(self):
            scene = {"width": 120, "height": 80,
                     "paths": [{"path_id": "test-path", "closed": True,
                                "segments": [{
                                    "control_points": [[10, 10], [40, 20], [70, 40], [100, 70]],
                                    "x_coeffs": {}, "y_coeffs": {}}]}]}
            self.output_dir.mkdir(parents=True, exist_ok=True)
            (self.output_dir / "scene.json").write_text(json.dumps(scene), encoding="utf-8")
            self.finished.emit(str(self.output_dir), "")

    monkeypatch.setattr("app.graph_calculator.ReconstructionWorker", FakeWorker)
    loaded_window._load_input(str(sample_image))
    loaded_window.upload_analyse_button.click()

    import time
    deadline = time.time() + 10
    while time.time() < deadline and "test-path" not in loaded_window.path_items:
        qapp.processEvents()
        time.sleep(0.02)
    assert started == [str(sample_image)]
    assert list(loaded_window.path_items) == ["test-path"]
    assert loaded_window.path_colors["test-path"] == DEFAULT_CURVE_COLOR
    assert "Analysis complete" in loaded_window.status.text()
    assert "1 paths" in loaded_window.path_count.text()


class _RecordingThread:
    def __init__(self, calls, fake_thread=False):
        self.calls = calls
        self.started = _FakeSignal()
        self.finished = _FakeSignal()

    def start(self):
        pass

    def quit(self):
        pass


class _FakeSignal:
    def connect(self, *_):
        pass

    def emit(self, *args):
        pass

# ------------------------------------------------------------------ colour model


@fixtures_required
def test_all_curves_are_black_by_default(loaded_window):
    assert set(loaded_window.path_colors.values()) == {DEFAULT_CURVE_COLOR}
    assert {item.pen().color().name() for item in loaded_window.path_items.values()} == \
        {DEFAULT_CURVE_COLOR}
    assert DEFAULT_CURVE_COLOR == "#000000"


@fixtures_required
def test_swatch_click_changes_only_that_path(loaded_window, monkeypatch):
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#d62728")))
    names = list(loaded_window.path_items)
    target = names[0]
    loaded_window.tree.swatch_clicked.emit(target)
    assert loaded_window.path_colors[target] == "#d62728"
    assert {loaded_window.path_colors[name] for name in names[1:]} == {DEFAULT_CURVE_COLOR}
    assert loaded_window.path_items[target].pen().color().name() == "#d62728"
    assert loaded_window.path_items[names[5]].pen().color().name() == DEFAULT_CURVE_COLOR
    item = loaded_window.path_tree_items[target]
    assert item.data(0, COLOR_ROLE) == "#d62728"
    assert item.child(0).data(0, COLOR_ROLE) == "#d62728"
    assert loaded_window.path_tree_items[names[5]].data(0, COLOR_ROLE) == DEFAULT_CURVE_COLOR
    assert loaded_window.path_tree_items[names[5]].child(0).data(0, COLOR_ROLE) == \
        DEFAULT_CURVE_COLOR


@fixtures_required
def test_cancelled_colour_dialog_keeps_the_colour(loaded_window, monkeypatch):
    monkeypatch.setattr(QColorDialog, "getColor",
                        staticmethod(lambda *a, **k: QColor(Qt.GlobalColor.transparent)))
    name = next(iter(loaded_window.path_items))
    loaded_window.tree.swatch_clicked.emit(name)
    assert loaded_window.path_colors[name] == DEFAULT_CURVE_COLOR
    assert loaded_window.path_items[name].pen().color().name() == DEFAULT_CURVE_COLOR


@fixtures_required
def test_colours_persist_through_selection_and_navigation(loaded_window, monkeypatch):
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#1f9d55")))
    names = list(loaded_window.path_items)
    loaded_window.tree.swatch_clicked.emit(names[2])
    snapshot = dict(loaded_window.path_colors)
    loaded_window._select_path(names[7])
    assert dict(loaded_window.path_colors) == snapshot
    assert loaded_window.path_items[names[7]].pen().widthF() == 3.6
    assert loaded_window.path_items[names[2]].pen().widthF() == 1.8
    loaded_window.graph.pan_by(120, -60)
    loaded_window.graph.zoom_at(QPointF(600, 400), 1.4)
    loaded_window._fit_view()
    loaded_window.graph.reset_view()
    assert dict(loaded_window.path_colors) == snapshot
    loaded_window._inspect_segment(names[2], 1)
    assert dict(loaded_window.path_colors) == snapshot


@fixtures_required
def test_visibility_toggle_is_independent_of_colour(loaded_window, monkeypatch):
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#8a2be2")))
    name = next(iter(loaded_window.path_items))
    loaded_window.tree.swatch_clicked.emit(name)
    loaded_window._set_layer("curves", False)
    assert loaded_window.path_colors[name] == "#8a2be2"
    loaded_window._set_layer("curves", True)
    assert loaded_window.path_items[name].pen().color().name() == "#8a2be2"


@fixtures_required
def test_selected_highlight_does_not_change_configured_colour(loaded_window):
    name = next(iter(loaded_window.path_items))
    loaded_window._select_path(name)
    assert loaded_window.path_colors[name] == DEFAULT_CURVE_COLOR
    item = loaded_window.path_items[name]
    assert item.pen().color().name() == DEFAULT_CURVE_COLOR
    assert item.pen().widthF() > 1.8


@fixtures_required
def test_exported_svg_uses_current_curve_colours(loaded_window, monkeypatch, tmp_path):
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#d62728")))
    name = next(iter(loaded_window.path_items))
    loaded_window.tree.swatch_clicked.emit(name)
    destination = tmp_path / "curves.svg"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *args, **kwargs: (str(destination), "")))
    loaded_window.export_svg_button.click()
    root = ET.fromstring(destination.read_text(encoding="utf-8"))
    elements = root.findall(f"{SVG_NS}path")
    assert len(elements) == len(loaded_window.path_items)
    assert elements[0].get("stroke") == "#d62728"
    assert all(element.get("stroke") == DEFAULT_CURVE_COLOR for element in elements[1:])


@fixtures_required
def test_export_panel_writes_complete_reconstruction(loaded_window, monkeypatch, tmp_path):
    json_target = tmp_path / "equation.json"
    svg_target = tmp_path / "curves.svg"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *args, **kwargs: (str(json_target), "")))
    loaded_window.export_json_button.click()
    document = json.loads(json_target.read_text(encoding="utf-8"))
    assert document["path_count"] == len(loaded_window.path_items)
    assert document["segment_count"] == \
        sum(len(p.get("segments") or []) for p in loaded_window.scene_data["paths"])
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *args, **kwargs: (str(svg_target), "")))
    loaded_window.export_svg_button.click()
    root = ET.fromstring(svg_target.read_text(encoding="utf-8"))
    assert len(root.findall(f"{SVG_NS}path")) == len(loaded_window.path_items)


# ------------------------------------------------------------------ details popover and footer


@fixtures_required
def test_details_open_from_the_info_icon_not_from_a_box_in_the_panel(loaded_window, qapp):
    from PySide6.QtTest import QTest

    window = loaded_window
    panel = window.splitter.widget(0)
    assert not panel.isAncestorOf(window.inspect)
    assert window.info_popover.isAncestorOf(window.inspect)
    assert not window.info_popover.isVisible()

    path_item = next(iter(window.path_tree_items.values()))
    path_item.setExpanded(True)
    qapp.processEvents()
    segment = path_item.child(2)
    assert "info" in window.tree._row_rects(segment)
    assert "info" in window.tree._row_rects(path_item)

    rect = window.tree._row_rects(segment)["info"]
    QTest.mouseClick(window.tree.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, rect.center())
    qapp.processEvents()
    assert window.info_popover.isVisible()
    assert window.tree.currentItem() is segment
    assert "segment 3 of" in window.inspect.text()
    window.info_popover.hide()

    rect = window.tree._row_rects(path_item)["info"]
    QTest.mouseClick(window.tree.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, rect.center())
    qapp.processEvents()
    assert window.info_popover.isVisible()
    assert window.tree.currentItem() is path_item
    assert "segment 1 of" in window.inspect.text()
    window.info_popover.hide()


@fixtures_required
def test_info_icon_does_not_toggle_visibility_or_open_the_colour_dialog(loaded_window, qapp,
                                                                         monkeypatch):
    from PySide6.QtTest import QTest

    window = loaded_window
    monkeypatch.setattr(QColorDialog, "getColor",
                        staticmethod(lambda *a, **k: pytest.fail("colour dialog opened")))
    path_item = next(iter(window.path_tree_items.values()))
    before = path_item.checkState(0)
    rect = window.tree._row_rects(path_item)["info"]
    QTest.mouseClick(window.tree.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, rect.center())
    qapp.processEvents()
    assert path_item.checkState(0) == before
    window.info_popover.hide()


def test_brand_is_a_watermark_painted_on_the_upload_panel(window, qapp):
    from PySide6.QtWidgets import QLabel, QWidget

    from app.graph_calculator import WatermarkPanel

    panel = window.upload_panel
    assert isinstance(panel, WatermarkPanel)
    # The credit is painted into the panel's background: no footer widget and
    # no label carrying the brand text any more.
    assert panel.findChild(QWidget, "brandFooter") is None
    assert not any("Emtypyie" in label.text() for label in panel.findChildren(QLabel))
    assert WatermarkPanel.WORDMARK == "LiSSARA"
    assert "Engineered by Emtypyie&Co" in WatermarkPanel.CREDITS
    assert "All Rights Reserved 2026" in WatermarkPanel.CREDITS
    # ...and it is actually drawn: the bottom-right corner differs from the
    # plain panel colour, while the top-right (behind the controls) does not.
    image = panel.grab().toImage()
    base = image.pixelColor(4, 4)
    painted = {image.pixelColor(x, y).rgb()
               for x in range(image.width() // 2, image.width() - 4)
               for y in range(image.height() - 110, image.height() - 4)}
    assert len(painted) > 3
    assert image.pixelColor(image.width() - 4, 4) == base


def test_font_is_the_bundled_inter(window):
    from PySide6.QtGui import QFontDatabase

    assert "Inter" in QFontDatabase.families()
    assert QApplication.instance().font().family() == "Inter"


def test_window_is_frameless_with_controls_inside_the_top_bar(window, qapp):
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    for button in (window.minimise_button, window.maximise_button, window.close_button):
        assert window.top_bar.isAncestorOf(button)
        assert button.isVisible()
    # close is the right-most control
    assert (window.close_button.mapTo(window, window.close_button.rect().center()).x()
            > window.maximise_button.mapTo(window, window.maximise_button.rect().center()).x()
            > window.minimise_button.mapTo(window, window.minimise_button.rect().center()).x())
    assert window.maximise_button.toolTip() == "Maximise"
    window.maximise_button.click()
    qapp.processEvents()
    assert window.isMaximized()
    assert window.maximise_button.toolTip() == "Restore"
    window.maximise_button.click()
    qapp.processEvents()
    assert not window.isMaximized()
    assert window.maximise_button.toolTip() == "Maximise"


def test_close_button_closes_the_window(qapp):
    win = LissaraGraphCalculator()
    win.show()
    qapp.processEvents()
    win.close_button.click()
    qapp.processEvents()
    assert not win.isVisible()
    win.deleteLater()


def test_title_stays_centred_with_window_controls(qapp):
    win = LissaraGraphCalculator()
    win.resize(1500, 900)
    win.show()
    qapp.processEvents()
    title = win.top_bar_title
    assert title.mapTo(win, title.rect().center()).x() == pytest.approx(win.width() / 2, abs=2)
    win.close()
    win.deleteLater()


def test_resize_band_reports_edges_only_when_not_maximised(window, qapp):
    from PySide6.QtCore import QPoint

    corner = window.mapToGlobal(QPoint(window.width() - 2, window.height() - 2))
    assert window._resize_edges(corner) == (Qt.Edge.RightEdge | Qt.Edge.BottomEdge)
    middle = window.mapToGlobal(QPoint(window.width() // 2, window.height() // 2))
    assert not window._resize_edges(middle)
    window.showMaximized()
    qapp.processEvents()
    assert not window._resize_edges(window.mapToGlobal(QPoint(window.width() - 2,
                                                              window.height() - 2)))
    window.showNormal()
    qapp.processEvents()


def test_panels_are_not_pure_white(window):
    image = window.grab().toImage()
    white = 0
    for x in range(0, image.width(), 7):
        for y in range(0, image.height(), 7):
            if image.pixelColor(x, y).rgb() == 0xFFFFFFFF:
                white += 1
    assert white == 0
