"""LiSSARA Core — interactive graph calculator built with PySide6 Graphics View.

Coordinate convention
---------------------
The reconstruction engine stores image-space points with the origin at the
top-left corner and y growing downward.  :func:`image_to_graph` performs the
sole display conversion to a centered Cartesian scene (origin at the image
centre, y growing upward)::

    X = x - width / 2
    Y = height / 2 - y

Curves, the original-image overlay, the edge overlay, control-point
highlights, the inspector equations and the coordinate readout all work in
scene coordinates, so the conversion is applied exactly once and never twice.

The view transform maps scene coordinates to viewport pixels explicitly::

    px = scale * (X - centre.x) + viewport.width  / 2
    py = scale * (Y - centre.y) * -1 + viewport.height / 2

Zooming and panning only ever change ``scale`` and ``centre``; the
reconstructed geometry itself is never modified.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (Qt, QEvent, QObject, QByteArray, QPoint, QPointF, QRect, QRectF, QSize,
                            QStandardPaths, QThread, QTimer, Signal)
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QImage, QPainter,
                          QPainterPath, QPen, QPixmap, QTransform)
from PySide6.QtWidgets import (QApplication, QColorDialog, QComboBox, QFileDialog,
                              QFrame, QGraphicsDropShadowEffect, QGraphicsEllipseItem,
                              QGraphicsItem, QGraphicsPathItem,
                              QGraphicsPixmapItem, QGraphicsScene, QGraphicsView,
                              QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                              QMessageBox, QPushButton, QSizePolicy, QSplitter,
                              QSplitterHandle, QStyle, QStyleOption, QStyledItemDelegate,
                              QToolButton,
                              QTreeWidget,
                              QTreeWidgetItem, QVBoxLayout, QWidget)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_NAME = "LiSSARA Core"

#: Soft, layered palette.  Nothing in the workspace is pure white: the canvas is
#: the lightest surface, panels sit a step darker, and cards a half step above
#: the panels, so the eye is not hit by large flat white areas.
CANVAS_BG = "#f1f3f7"       # graph canvas
PANEL_BG = "#e9edf3"        # expression + upload panels
PANEL_HEAD_BG = "#e1e6ee"   # panel headers and row gutters
SURFACE_BG = "#f5f7fa"      # inputs, cards, buttons resting on a panel
HAIRLINE = "#d3d9e3"        # dividers
GRID_MINOR = "#e1e6ee"
GRID_MAJOR = "#cbd2de"
INK = "#1f2733"

#: Fonts shipped with the app (SIL Open Font License, see app/fonts/OFL.txt).
FONT_DIR = Path(__file__).resolve().parent / "fonts"
UI_FONT_FILES = ("Inter-Light.otf", "Inter-Regular.otf", "Inter-SemiBold.otf")
#: Fallbacks used only when the bundled Inter files cannot be loaded.
UI_FONT_FALLBACKS = ("Segoe UI Variable Text", "Segoe UI", "SF Pro Text",
                     "Helvetica Neue", "Noto Sans", "DejaVu Sans")


def load_ui_font_family() -> str:
    """Register the bundled Inter weights and return the UI font family name."""
    for name in UI_FONT_FILES:
        QFontDatabase.addApplicationFont(str(FONT_DIR / name))
    installed = set(QFontDatabase.families())
    if "Inter" in installed:
        return "Inter"
    for family in UI_FONT_FALLBACKS:
        if family in installed:
            return family
    return QApplication.font().family()


#: Reconstructed curves are black until the user picks a colour.
DEFAULT_CURVE_COLOR = "#000000"
COLOR_ROLE = Qt.ItemDataRole.UserRole + 1
#: Extra item roles read by :class:`ExpressionDelegate` (row number, the two
#: equation lines and the caption under a path's equations).
ROW_ROLE = Qt.ItemDataRole.UserRole + 2
X_ROLE = Qt.ItemDataRole.UserRole + 3
Y_ROLE = Qt.ItemDataRole.UserRole + 4
META_ROLE = Qt.ItemDataRole.UserRole + 5
#: Expression list geometry (Desmos-style numbered rows with a colour gutter).
EXPR_GUTTER_WIDTH = 46
EXPR_PATH_HEIGHT = 80
EXPR_SEGMENT_HEIGHT = 58
EXPR_ACCENT = "#2f72dc"
#: Drawer and panel widths.
EXPORT_PANEL_WIDTH = 300
UPLOAD_PANEL_WIDTH = 320
EXPRESSION_PANEL_WIDTH = 360

EXPORT_ICON_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}"
     stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 3.5v10.5"/>
  <path d="M7.6 9.4 12 13.8l4.4-4.4"/>
  <path d="M4.5 15v4.2A1.8 1.8 0 0 0 6.3 21h11.4a1.8 1.8 0 0 0 1.8-1.8V15"/>
</svg>
"""


UPLOAD_ICON_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}"
     stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 15V4"/>
  <path d="M7.6 8.4 12 4l4.4 4.4"/>
  <path d="M4.5 15v4.2A1.8 1.8 0 0 0 6.3 21h11.4a1.8 1.8 0 0 0 1.8-1.8V15"/>
</svg>
"""

ANALYSE_ICON_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}"
     stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 17C8 17 8 7 12 7s4 10 9 10"/>
  <circle cx="3" cy="17" r="1.4" fill="{color}"/>
  <circle cx="21" cy="17" r="1.4" fill="{color}"/>
</svg>
"""

CLOSE_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}"
     stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M6 6l12 12M18 6L6 18"/>
</svg>
"""

MINIMISE_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}"
     stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M6 12h12"/>
</svg>
"""

MAXIMISE_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}"
     stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="6" y="6" width="12" height="12" rx="1.6"/>
</svg>
"""

RESTORE_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}"
     stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="5.5" y="9" width="9.5" height="9.5" rx="1.5"/>
  <path d="M9 9V7.4A1.4 1.4 0 0 1 10.4 6H16.6A1.4 1.4 0 0 1 18 7.4V13.6A1.4 1.4 0 0 1 16.6 15H15"/>
</svg>
"""

CHEVRON_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}"
     stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">
  <path d="M6 9.5l6 6 6-6"/>
</svg>
"""

#: Navigation-bar palette (the bar and status bar share it).
NAV_TEXT = "#d7deea"
NAV_TEXT_DIM = "#aab4c5"
#: Hairline colours used by the VS Code-style panel dividers.
SASH_LINE = QColor("#c9d0db")
SASH_ACTIVE = QColor("#4a7fd6")


def svg_icon(svg: str, size: int = 18, color: str = "#4d5561") -> QIcon:
    """Render an inline SVG glyph into a crisp, scaled QIcon."""
    try:
        from PySide6.QtCore import QSize
        from PySide6.QtSvg import QSvgRenderer

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        renderer = QSvgRenderer(QByteArray(svg.replace("{color}", color).encode("utf-8")))
        if not renderer.isValid():
            raise ValueError("invalid svg")
        with QPainter(pixmap) as painter:
            renderer.render(painter, QRectF(0, 0, size, size))
        return QIcon(pixmap)
    except Exception:
        return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)

#: Version of the exported ``equation.json`` schema.
EQUATION_SCHEMA_VERSION = 1
#: Cubic segments are defined on the closed unit interval.
PARAMETER_DOMAIN = {"min": 0.0, "max": 1.0}
#: Engine coordinates used by every export (see :func:`image_to_graph` for the
#: conversion to the centered, y-up Cartesian frame the graph displays.
COORDINATE_CONVENTION = {
    "name": "engine image space",
    "axes": "x increases to the right, y increases downward",
    "origin": "top-left corner of the source image",
    "units": "pixels",
    "cartesian_graph_transform": "X = x - width / 2; Y = height / 2 - y",
}

#: Target spacing between major gridlines, in screen pixels.
GRID_TARGET_PX = 72.0
#: Grid density presets: multiply :data:`GRID_TARGET_PX` (smaller = denser).
GRID_DENSITY = {"Fine": 0.5, "Standard": 1.0, "Coarse": 2.0}
#: Smallest/largest number of scene units that may be visible at once.
MIN_VISIBLE_UNITS = 6.0
MAX_VISIBLE_UNITS = 300_000.0
#: Viewport used before any data is loaded.
DEFAULT_CONTENT_RECT = QRectF(-500.0, -350.0, 1000.0, 700.0)


def nice_step(target: float) -> float:
    """Return the smallest 1/2/5 x 10^k step that is >= ``target``."""
    if not math.isfinite(target) or target <= 0.0:
        return 1.0
    exponent = math.floor(math.log10(target))
    mantissa = target / (10.0 ** exponent)
    tolerance = 1e-9
    if mantissa <= 1.0 + tolerance:
        factor = 1.0
    elif mantissa <= 2.0 + tolerance:
        factor = 2.0
    elif mantissa <= 5.0 + tolerance:
        factor = 5.0
    else:
        factor = 10.0
    return factor * (10.0 ** exponent)


def grid_steps(scale: float, target_px: float = GRID_TARGET_PX,
               density: float = 1.0) -> tuple[float, float]:
    """Major and minor grid spacing in scene units for ``scale`` px/unit.

    The major spacing is always a 1/2/5 x 10^k value and covers roughly
    ``target_px * density`` screen pixels, so the grid re-spaces itself as
    the view zooms.  Minor lines divide the major step by five, or by two
    when a five-way split would become denser than ~9 px on screen.
    """
    if not math.isfinite(scale) or scale <= 0.0:
        return 1.0, 0.2
    major = nice_step(target_px * density / scale)
    minor = major / 5.0
    if minor * scale < 9.0:
        minor = major / 2.0
    return major, minor


def format_tick(value: float) -> str:
    """Compact axis tick label (``0`` instead of ``-0``)."""
    if abs(value) < 1e-12:
        return "0"
    return f"{value:g}"


def fit_scale(rect: QRectF, view_w: float, view_h: float, margin: float = 0.07) -> float:
    """Scale (px per scene unit) that frames ``rect`` with ``margin`` extra room."""
    width, height = rect.width(), rect.height()
    if width <= 0.0 and height <= 0.0:
        width = height = 1.0
    elif width <= 0.0:
        width = height
    elif height <= 0.0:
        height = width
    width *= 1.0 + 2.0 * margin
    height *= 1.0 + 2.0 * margin
    if view_w <= 0.0 or view_h <= 0.0:
        return 1.0
    return min(view_w / width, view_h / height)


def zoom_center(center: QPointF, scale: float, new_scale: float,
                pos: QPointF, view_w: float, view_h: float) -> QPointF:
    """New view centre that keeps the scene point under ``pos`` fixed."""
    half_w = view_w / 2.0
    half_h = view_h / 2.0
    scene_x = center.x() + (pos.x() - half_w) / scale
    scene_y = center.y() - (pos.y() - half_h) / scale
    return QPointF(scene_x - (pos.x() - half_w) / new_scale,
                   scene_y + (pos.y() - half_h) / new_scale)


def image_to_graph(x: float, y: float, width: float, height: float) -> QPointF:
    """Map an engine image coordinate into centered Cartesian scene space."""
    return QPointF(float(x) - width / 2.0, height / 2.0 - float(y))


def cubic_path(path_data: dict, width: float, height: float) -> QPainterPath:
    """Build exact cubic geometry, preserving each path's independent contours."""
    result = QPainterPath()
    segments = path_data.get("segments") or []
    if not segments:
        return result
    p0 = image_to_graph(*segments[0]["control_points"][0], width, height)
    result.moveTo(p0)
    for segment in segments:
        p = [image_to_graph(*point, width, height)
             for point in segment["control_points"]]
        result.cubicTo(p[1], p[2], p[3])
    if path_data.get("closed"):
        result.closeSubpath()
    return result


def bezier_coefficients(control_points) -> tuple[tuple[float, float, float, float],
                                                 tuple[float, float, float, float]]:
    """Polynomial coefficients of a cubic BAczier curve from its control points.

    Power-basis expansion of B(t) = (1-t)^3 P0 + 3(1-t)^2 t P1 + 3(1-t) t^2 P2 + t^3 P3:

        a3 = -P0 + 3P1 - 3P2 + P3
        a2 =  3P0 - 6P1 + 3P2
        a1 = -3P0 + 3P1
        a0 =  P0

    Returns ``((a3, a2, a1, a0) for x, (a3, a2, a1, a0) for y)`` in engine image
    coordinates.  These are algebraically identical to the ``x_coeffs``/
    ``y_coeffs`` stored in canonical Lissara curve records.
    """
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = (tuple(map(float, point))
                                             for point in control_points)
    x_coeffs = (-x0 + 3 * x1 - 3 * x2 + x3,
                3 * x0 - 6 * x1 + 3 * x2,
                -3 * x0 + 3 * x1,
                x0)
    y_coeffs = (-y0 + 3 * y1 - 3 * y2 + y3,
                3 * y0 - 6 * y1 + 3 * y2,
                -3 * y0 + 3 * y1,
                y0)
    return x_coeffs, y_coeffs


def segment_equations(segment: dict, width: float, height: float):
    """Numerical x(t)/y(t) coefficients in the graph's Cartesian frame.

    Applies the :func:`image_to_graph` convention to the polynomials rather
    than to sampled points, so equations and curves can never disagree.
    """
    x_coeffs, y_coeffs = bezier_coefficients(segment["control_points"])
    cartesian_x = (*x_coeffs[:3], x_coeffs[3] - width / 2.0)
    cartesian_y = (-y_coeffs[0], -y_coeffs[1], -y_coeffs[2], height / 2.0 - y_coeffs[3])
    return cartesian_x, cartesian_y


def format_polynomial(name: str, coefficients) -> str:
    """Render ``name(t) = a*t^3 + b*t^2 + c*t + d`` with numeric coefficients."""
    parts: list[str] = []
    for position, (value, suffix) in enumerate(zip(coefficients, ("t\u00b3", "t\u00b2", "t", ""))):
        value = 0.0 if abs(value) < 1e-12 else value
        magnitude = f"{abs(value):.6g}{suffix}"
        if position == 0:
            parts.append(f"-{magnitude}" if value < 0 else magnitude)
        else:
            parts.append(f" - {magnitude}" if value < 0 else f" + {magnitude}")
    return f"{name}(t) = {''.join(parts)}"


def compact_polynomial(coefficients, precision: int = 4) -> str:
    """One-line polynomial for expression rows (zero terms dropped)."""
    parts: list[str] = []
    threshold = 10.0 ** -(precision - 1)
    for value, suffix in zip(coefficients, ("t\u00b3", "t\u00b2", "t", "")):
        value = 0.0 if abs(value) < threshold else value
        if value == 0.0:
            continue
        magnitude = f"{abs(value):.{precision}g}{suffix}"
        parts.append((f"-{magnitude}" if value < 0 else f"+{magnitude}") if parts
                     else (f"-{magnitude}" if value < 0 else magnitude))
    return "".join(parts) or "0"


def _plain_number(value: float) -> str:
    """Short, exponent-free number for the expression list (3-ish digits)."""
    magnitude = abs(value)
    if magnitude >= 100.0:
        text = f"{magnitude:.0f}"
    elif magnitude >= 10.0:
        text = f"{magnitude:.1f}"
    elif magnitude >= 1.0:
        text = f"{magnitude:.2f}"
    else:
        text = f"{magnitude:.3f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def pretty_polynomial(coefficients) -> str:
    """Readable ``a t\u00b3 \u2212 b t\u00b2 + \u2026`` for the expression list.

    Numbers are shortened for display only; the inspector and the exports keep
    full precision.  Terms that round to zero are dropped.
    """
    minus = "\u2212"
    parts: list[str] = []
    for value, suffix in zip(coefficients, ("t\u00b3", "t\u00b2", "t", "")):
        if abs(value) < 5e-4:
            continue
        magnitude = _plain_number(value) + suffix
        if not parts:
            parts.append(minus + magnitude if value < 0 else magnitude)
        else:
            sign = minus if value < 0 else "+"
            parts.append(" " + sign + " " + magnitude)
    return "".join(parts) or "0"


def segment_equation_summary(segment: dict, width: float, height: float) -> str:
    """Compact ``x(t)=…, y(t)=…`` label for a cubic segment."""
    x_coeffs, y_coeffs = segment_equations(segment, width, height)
    return (f"x(t)={compact_polynomial(x_coeffs)},  "
            f"y(t)={compact_polynomial(y_coeffs)}")


def scene_geometry_bounds(scene: dict) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) over every reconstructed control point."""
    min_x = min_y = math.inf
    max_x = max_y = -math.inf
    for path in scene.get("paths") or []:
        for segment in path.get("segments") or []:
            for x, y in segment.get("control_points") or []:
                x, y = float(x), float(y)
                min_x, min_y = min(min_x, x), min(min_y, y)
                max_x, max_y = max(max_x, x), max(max_y, y)
    if not min_x <= max_x or not min_y <= max_y:
        return 0.0, 0.0, 0.0, 0.0
    return min_x, min_y, max_x, max_y


def build_equation_document(scene: dict) -> dict:
    """Serialize every reconstructed path/segment into the equation schema."""
    image_width = scene.get("width")
    image_height = scene.get("height")
    exported_paths = []
    total_segments = 0
    for index, path in enumerate(scene.get("paths") or []):
        segments = path.get("segments") or []
        exported_segments = []
        for segment_index, segment in enumerate(segments):
            x_coeffs, y_coeffs = bezier_coefficients(segment["control_points"])
            exported_segments.append({
                "index": segment_index,
                "control_points": [[float(x), float(y)]
                                   for x, y in segment["control_points"]],
                "x_coeffs": {"a3": x_coeffs[0], "a2": x_coeffs[1],
                             "a1": x_coeffs[2], "a0": x_coeffs[3]},
                "y_coeffs": {"b3": y_coeffs[0], "b2": y_coeffs[1],
                             "b1": y_coeffs[2], "b0": y_coeffs[3]},
                "parameter_domain": dict(PARAMETER_DOMAIN),
            })
        total_segments += len(exported_segments)
        exported_paths.append({
            "path_id": str(path.get("path_id") or f"path-{index + 1:03d}"),
            "path_type": path.get("path_type", "path"),
            "closed": bool(path.get("closed")),
            "segment_count": len(exported_segments),
            "segments": exported_segments,
        })
    return {
        "schema": "lissara.equations",
        "schema_version": EQUATION_SCHEMA_VERSION,
        "image": {"width": image_width, "height": image_height},
        "coordinate_convention": {
            **COORDINATE_CONVENTION,
            "source_image": {"width": image_width, "height": image_height},
        },
        "path_count": len(exported_paths),
        "segment_count": total_segments,
        "paths": exported_paths,
    }


def build_scene_svg(scene: dict, palette=None, stroke_width: float = 1.6,
                    padding: float = 1.5) -> str:
    """Export every reconstructed path as exact SVG cubic geometry.

    The original BAczier control points are emitted as ``C`` commands (never
    resampled), each path keeps its own ``<path>`` element, and the viewBox is
    the geometry bounds, so aspect ratio and relationships are preserved on a
    transparent background.
    """
    from renderer.svg import SvgCanvas, format_number, path_data

    if palette is None:
        colors = [DEFAULT_CURVE_COLOR]
    elif isinstance(palette, dict):
        colors = [str(value) for value in palette.values()] or [DEFAULT_CURVE_COLOR]
    else:
        colors = [str(value) for value in palette] or [DEFAULT_CURVE_COLOR]
    min_x, min_y, max_x, max_y = scene_geometry_bounds(scene)
    width = max_x - min_x
    height = max_y - min_y
    if width <= 0.0 and height <= 0.0:
        raise ValueError("scene has no drawable cubic geometry")
    pad = padding + stroke_width / 2.0
    min_x -= pad
    min_y -= pad
    width += 2 * pad
    height += 2 * pad
    view_box = (f"{format_number(min_x)} {format_number(min_y)} "
                f"{format_number(width)} {format_number(height)}")
    canvas = SvgCanvas(width, height, view_box=view_box)
    for index, path in enumerate(scene.get("paths") or []):
        segments = path.get("segments") or []
        if not segments:
            continue
        data = path_data(segments, closed=bool(path.get("closed")))
        if not data:
            continue
        canvas.path(data,
                    fill="none",
                    stroke=colors[index % len(colors)],
                    stroke_width=stroke_width,
                    stroke_linecap="round",
                    stroke_linejoin="round")
    return canvas.render(background=None)


class CurveItem(QGraphicsPathItem):
    def __init__(self, name: str, path: QPainterPath, color: str):
        super().__init__(path)
        self.name = name
        self.on_selected = None
        pen = QPen(QColor(color), 1.8)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    def mousePressEvent(self, event):
        if self.on_selected:
            self.on_selected(self.name)
        super().mousePressEvent(event)


class GraphView(QGraphicsView):
    """Cartesian graph canvas with explicit scale/centre viewport state."""

    coordinates_changed = Signal(float, float)
    image_dropped = Signal(str)

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)
        self.setObjectName("graphView")
        self.setRenderHints(QPainter.RenderHint.Antialiasing |
                            QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor(CANVAS_BG))
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSceneRect(-1_000_000, -1_000_000, 2_000_000, 2_000_000)
        self._view_scale = 1.0
        self._view_center = QPointF(0.0, 0.0)
        self._content_rect = QRectF(DEFAULT_CONTENT_RECT)
        self._pan_last: QPoint | None = None
        self._pen_minor = QPen(QColor(GRID_MINOR), 0)
        self._pen_major = QPen(QColor(GRID_MAJOR), 0)
        self._pen_axis = QPen(QColor("#5f6874"), 1.15)
        self._pen_axis.setCosmetic(True)
        self._label_color = QColor("#4d5563")



    def view_scale(self) -> float:
        return self._view_scale

    def view_center(self) -> QPointF:
        return QPointF(self._view_center)

    def set_content_rect(self, rect: QRectF | None):
        """Region the viewport should stay anchored to while navigating."""
        if rect is None or rect.isNull() or rect.isEmpty():
            rect = QRectF(DEFAULT_CONTENT_RECT)
        self._content_rect = QRectF(rect)

    def _scale_limits(self, view_w: int, view_h: int) -> tuple[float, float]:
        scale_min = max(view_w, view_h) / MAX_VISIBLE_UNITS
        scale_max = max(min(view_w, view_h) / MIN_VISIBLE_UNITS, scale_min)
        return scale_min, scale_max

    def _apply_view(self):
        """Push the explicit scale/centre state onto the Qt view transform."""
        view_w = self.viewport().width()
        view_h = self.viewport().height()
        if view_w <= 0 or view_h <= 0:
            return
        scale_min, scale_max = self._scale_limits(view_w, view_h)
        scale = min(max(self._view_scale, scale_min), scale_max)
        units_x = view_w / scale
        units_y = view_h / scale
        content = self._content_rect
        centre_x = min(max(self._view_center.x(),
                           content.left() - 0.25 * units_x),
                       content.right() + 0.25 * units_x)
        centre_y = min(max(self._view_center.y(),
                           content.top() - 0.25 * units_y),
                       content.bottom() + 0.25 * units_y)
        self._view_scale = scale
        self._view_center = QPointF(centre_x, centre_y)
        self.resetTransform()
        self.scale(scale, -scale)
        self.centerOn(self._view_center)

    def visible_scene_rect(self) -> QRectF:
        """Scene rectangle currently shown, normalised (y grows upward)."""
        view_w = self.viewport().width()
        view_h = self.viewport().height()
        top_left = self.mapToScene(0, 0)
        bottom_right = self.mapToScene(view_w, view_h)
        return QRectF(top_left, bottom_right).normalized()

    def zoom_at(self, pos: QPointF, factor: float):
        """Zoom by ``factor`` keeping the scene point under ``pos`` fixed."""
        view_w = self.viewport().width()
        view_h = self.viewport().height()
        if view_w <= 0 or view_h <= 0 or factor <= 0.0:
            return
        scale_min, scale_max = self._scale_limits(view_w, view_h)
        new_scale = min(max(self._view_scale * factor, scale_min), scale_max)
        if new_scale == self._view_scale:
            return
        self._view_center = zoom_center(self._view_center, self._view_scale,
                                        new_scale, QPointF(pos), view_w, view_h)
        self._view_scale = new_scale
        self._apply_view()

    def pan_by(self, dx: float, dy: float):
        """Move the viewport by ``dx``/``dy`` screen pixels (content follows)."""
        scale = max(self._view_scale, 1e-12)
        self._view_center = QPointF(self._view_center.x() - dx / scale,
                                    self._view_center.y() + dy / scale)
        self._apply_view()

    def fit_rect(self, rect: QRectF, margin: float = 0.07):
        """Frame ``rect`` with sensible margins, centred."""
        if rect is None or rect.isNull() or rect.isEmpty():
            rect = QRectF(DEFAULT_CONTENT_RECT)
        self._view_scale = fit_scale(rect, self.viewport().width(),
                                     self.viewport().height(), margin)
        self._view_center = rect.center()
        self._apply_view()

    def reset_view(self):
        """Restore the default origin-centred viewport at 1 px per unit."""
        self._view_scale = 1.0
        self._view_center = QPointF(0.0, 0.0)
        self._apply_view()

    def _grid_steps(self, scale: float) -> tuple[float, float]:
        density = GRID_DENSITY.get(self.property("gridDensity") or "Standard", 1.0)
        return grid_steps(scale, density=density)



    def _paint_grid_axis(self, painter: QPainter, rect: QRectF, vertical: bool,
                         step: float, pen: QPen):
        if step <= 0.0:
            return
        low = rect.left() if vertical else rect.top()
        high = rect.right() if vertical else rect.bottom()
        first = math.ceil(low / step - 1e-9)
        last = math.floor(high / step + 1e-9)
        if last - first > 4000:
            return
        painter.setPen(pen)
        for index in range(first, last + 1):
            value = index * step
            if vertical:
                painter.drawLine(QPointF(value, rect.top()), QPointF(value, rect.bottom()))
            else:
                painter.drawLine(QPointF(rect.left(), value), QPointF(rect.right(), value))

    def drawBackground(self, painter: QPainter, rect: QRectF):
        visible = self.visible_scene_rect()
        painter.fillRect(visible, QColor(CANVAS_BG))
        scale = abs(self.transform().m11())
        if scale <= 1e-12:
            return
        if self.property("gridVisible") is not False:
            major, minor = self._grid_steps(scale)
            self._paint_grid_axis(painter, visible, True, minor, self._pen_minor)
            self._paint_grid_axis(painter, visible, False, minor, self._pen_minor)
            self._paint_grid_axis(painter, visible, True, major, self._pen_major)
            self._paint_grid_axis(painter, visible, False, major, self._pen_major)
        painter.setPen(self._pen_axis)
        if visible.left() <= 0.0 <= visible.right():
            painter.drawLine(QPointF(0.0, visible.top()), QPointF(0.0, visible.bottom()))
        if visible.top() <= 0.0 <= visible.bottom():
            painter.drawLine(QPointF(visible.left(), 0.0), QPointF(visible.right(), 0.0))

    def drawForeground(self, painter: QPainter, rect: QRectF):
        """Axis tick marks and labels, drawn in screen space so text stays upright."""
        scale = abs(self.transform().m11())
        if scale <= 1e-12:
            return
        major, _ = self._grid_steps(scale)
        visible = self.visible_scene_rect()
        view_w = self.viewport().width()
        view_h = self.viewport().height()
        origin = self.mapFromScene(QPointF(0.0, 0.0))
        x_axis_visible = 0.0 <= origin.y() <= view_h
        y_axis_visible = 0.0 <= origin.x() <= view_w
        both_visible = x_axis_visible and y_axis_visible

        painter.save()
        painter.resetTransform()
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(self._label_color)

        label_y = min(origin.y() + 15, view_h - 14) if x_axis_visible else view_h - 14
        first = math.ceil(visible.left() / major - 1e-9)
        last = math.floor(visible.right() / major + 1e-9)
        for index in range(first, last + 1):
            value = index * major
            if abs(value) < 1e-12 and both_visible:
                continue
            screen = self.mapFromScene(QPointF(value, 0.0))
            if screen.x() < 30 or screen.x() > view_w - 30:
                continue
            if x_axis_visible:
                painter.drawLine(screen.x(), int(origin.y()) - 3,
                                 screen.x(), int(origin.y()) + 3)
            painter.drawText(QRectF(screen.x() - 40, label_y, 80, 14),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                             format_tick(value))

        label_right = (origin.x() - 7) if y_axis_visible else 44.0
        first = math.ceil(visible.top() / major - 1e-9)
        last = math.floor(visible.bottom() / major + 1e-9)
        for index in range(first, last + 1):
            value = index * major
            if abs(value) < 1e-12 and both_visible:
                continue
            screen = self.mapFromScene(QPointF(0.0, value))
            if screen.y() < 10 or screen.y() > view_h - 10:
                continue
            if y_axis_visible:
                painter.drawLine(int(origin.x()) - 3, screen.y(),
                                 int(origin.x()) + 3, screen.y())
            label_left = max(2.0, label_right - 50.0)
            if label_right - label_left >= 18.0:
                painter.drawText(QRectF(label_left, screen.y() - 8,
                                        label_right - label_left, 16),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                                 format_tick(value))

        if both_visible:
            label_left = max(2.0, origin.x() - 28.0)
            if origin.x() - 7.0 - label_left >= 12.0:
                painter.drawText(QRectF(label_left, origin.y() + 4,
                                        origin.x() - 7.0 - label_left, 14),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, "0")
        painter.restore()



    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120.0
        if steps == 0.0:
            return
        self.zoom_at(event.position(), 1.25 ** steps)
        event.accept()

    def mouseMoveEvent(self, event):
        point = self.mapToScene(event.position().toPoint())
        self.coordinates_changed.emit(point.x(), point.y())
        if self._pan_last is not None:
            current = event.position().toPoint()
            delta = current - self._pan_last
            self.pan_by(delta.x(), delta.y())
            self._pan_last = current
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            position = event.position().toPoint()
            hit = self.itemAt(position)
            if hit is None or hit.data(0) != "curve":
                self._pan_last = position
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._pan_last is not None:
            self._pan_last = None
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_view_scale"):
            self._apply_view()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "_view_scale"):
            self._apply_view()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.image_dropped.emit(url.toLocalFile())
                break
        event.acceptProposedAction()


class ReconstructionWorker(QObject):
    finished = Signal(str, str)

    def __init__(self, image_path: str, output_dir: Path):
        super().__init__()
        self.image_path = image_path
        self.output_dir = output_dir

    def run(self):
        try:
            from scripts.run_edge_reconstruction import run_reconstruction
            run_reconstruction(self.image_path, self.output_dir, write_png=False)
            self.finished.emit(str(self.output_dir), "")
        except Exception:
            self.finished.emit("", traceback.format_exc())


def expression_row_rects(rect: QRect, is_path: bool, has_children: bool) -> dict[str, QRect]:
    """Hit/paint rectangles of one expression row (shared by paint and clicks)."""
    left, top = rect.left(), rect.top()
    width, height = rect.width(), rect.height()
    gutter = QRect(left, top, EXPR_GUTTER_WIDTH, height)
    rects = {"gutter": gutter,
             "main": QRect(left + EXPR_GUTTER_WIDTH, top,
                           width - EXPR_GUTTER_WIDTH, height)}
    if is_path:
        diameter = 20
        rects["swatch"] = QRect(gutter.center().x() - diameter // 2 + 1,
                                top + height // 2 - diameter // 2 + 5,
                                diameter, diameter)
        eye = QRect(left + width - 12 - 22, top + height // 2 - 11, 22, 22)
        rects["eye"] = eye
        outermost = eye
        if has_children:
            rects["chevron"] = QRect(eye.left() - 26, eye.top(), 22, 22)
            outermost = rects["chevron"]
        rects["info"] = QRect(outermost.left() - 26, eye.top(), 22, 22)
    else:
        rects["info"] = QRect(left + width - 12 - 22, top + height // 2 - 11, 22, 22)
    return rects


def paint_info(painter: QPainter, rect: QRect, color: QColor):
    """Small circled 'i' that opens a row's details."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(color, 1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    centre = QPointF(rect.center().x() + 0.5, rect.center().y() + 0.5)
    painter.drawEllipse(centre, 8.0, 8.0)
    painter.drawLine(QPointF(centre.x(), centre.y() - 0.8), QPointF(centre.x(), centre.y() + 3.6))
    painter.setPen(QPen(color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawPoint(QPointF(centre.x(), centre.y() - 3.5))
    painter.restore()


def paint_eye(painter: QPainter, rect: QRect, color: QColor, visible: bool):
    """Small eye glyph (struck through when the path is hidden)."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(color, 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    box = QRectF(rect).adjusted(2, 5, -2, -5)
    mid = box.center().y()
    lens = QPainterPath(QPointF(box.left(), mid))
    lens.quadTo(QPointF(box.center().x(), 2 * box.top() - mid), QPointF(box.right(), mid))
    lens.quadTo(QPointF(box.center().x(), 2 * box.bottom() - mid), QPointF(box.left(), mid))
    painter.drawPath(lens)
    if visible:
        painter.setBrush(color)
        painter.drawEllipse(box.center(), 2.2, 2.2)
    else:
        painter.drawLine(QPointF(box.left() + 1, box.bottom() + 2),
                         QPointF(box.right() - 1, box.top() - 2))
    painter.restore()


def paint_chevron(painter: QPainter, rect: QRect, color: QColor, expanded: bool):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(color, 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    cx, cy = rect.center().x() + 0.5, rect.center().y() + 0.5
    path = QPainterPath()
    if expanded:
        path.moveTo(cx - 4.5, cy - 2.2)
        path.lineTo(cx, cy + 2.4)
        path.lineTo(cx + 4.5, cy - 2.2)
    else:
        path.moveTo(cx - 2.2, cy - 4.5)
        path.lineTo(cx + 2.4, cy)
        path.lineTo(cx - 2.2, cy + 4.5)
    painter.drawPath(path)
    painter.restore()


class ExpressionDelegate(QStyledItemDelegate):
    """Paints expression rows like Desmos: numbered gutter, roomy equations.

    Path rows show a colour dot in the gutter, the first segment's ``x(t)`` and
    ``y(t)`` on separate lines, a caption, an eye toggle and an expand chevron.
    Segment rows are smaller and show just the two equations.
    """

    def __init__(self, tree: QTreeWidget):
        super().__init__(tree)
        self._tree = tree

    @staticmethod
    def _is_path(index) -> bool:
        tag = index.data(Qt.ItemDataRole.UserRole)
        return bool(tag) and tag[0] == "path"

    def sizeHint(self, option, index):
        return QSize(100, EXPR_PATH_HEIGHT if self._is_path(index) else EXPR_SEGMENT_HEIGHT)

    def editorEvent(self, event, model, option, index):
        # Visibility is driven by the eye toggle, not by Qt's built-in checkbox.
        return False

    def paint(self, painter: QPainter, option, index):
        item = self._tree.itemFromIndex(index)
        if item is None:
            return super().paint(painter, option, index)
        is_path = self._is_path(index)
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        owner = item if is_path else (item.parent() or item)
        visible = owner.checkState(0) != Qt.CheckState.Unchecked
        rects = expression_row_rects(rect, is_path, item.childCount() > 0)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(rect, QColor("#e2e8f1") if hover and not selected else QColor(PANEL_BG))
        gutter_fill = (QColor(EXPR_ACCENT) if selected
                       else QColor(PANEL_HEAD_BG) if is_path else QColor("#e5e9f0"))
        painter.fillRect(rects["gutter"], gutter_fill)
        painter.setPen(QColor(HAIRLINE))
        painter.drawLine(rect.left(), rect.bottom(), rect.left() + rect.width(), rect.bottom())
        if selected:
            outline = QPen(QColor(EXPR_ACCENT), 1.4)
            painter.setPen(outline)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(rects["main"]).adjusted(0.7, 0.7, -0.7, -1.7))

        # Row number in the gutter.
        number_font = QFont(painter.font())
        number_font.setPixelSize(11)
        painter.setFont(number_font)
        painter.setPen(QColor("#ffffff") if selected else QColor("#7b8492"))
        painter.drawText(QRect(rect.left() + 9, rect.top() + 8, EXPR_GUTTER_WIDTH - 12, 14),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                         str(index.data(ROW_ROLE) or ""))

        # Colour dot (filled = visible, ring = hidden).
        if is_path:
            color = QColor(str(index.data(COLOR_ROLE) or DEFAULT_CURVE_COLOR))
            dot = QRectF(rects["swatch"]).adjusted(1.5, 1.5, -1.5, -1.5)
            if visible:
                painter.setBrush(color)
                painter.setPen(QPen(QColor("#ffffff") if selected else QColor("#c4cad4"),
                                    2.0 if selected else 1.0))
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor("#ffffff") if selected else color, 2.0))
            painter.drawEllipse(dot)

        # Equations.
        main = rects["main"]
        text_left = main.left() + 14
        text_right = rects["info"].left() - 8
        text_width = max(text_right - text_left, 20)
        equation_font = QFont(painter.font())
        equation_font.setPixelSize(13 if is_path else 12)
        painter.setFont(equation_font)
        fm = painter.fontMetrics()
        ink = QColor(INK) if visible else QColor("#9aa3b1")
        label_ink = QColor("#6b7685") if visible else QColor("#b3bac5")
        top = rect.top() + (12 if is_path else 10)
        line_height = 20 if is_path else 18
        for line, (name, role) in enumerate((("x(t)", X_ROLE), ("y(t)", Y_ROLE))):
            y = top + line * (line_height + 3)
            label = f"{name} = "
            label_width = fm.horizontalAdvance(label)
            painter.setPen(label_ink)
            painter.drawText(QRect(text_left, y, label_width, line_height),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            painter.setPen(ink)
            body = str(index.data(role) or "")
            painter.drawText(QRect(text_left + label_width, y,
                                   max(text_width - label_width, 10), line_height),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             fm.elidedText(body, Qt.TextElideMode.ElideRight,
                                           max(text_width - label_width, 10)))

        if is_path:
            caption_font = QFont(painter.font())
            caption_font.setPixelSize(11)
            painter.setFont(caption_font)
            painter.setPen(QColor("#8a93a1") if visible else QColor("#b3bac5"))
            painter.drawText(QRect(text_left, rect.top() + 12 + 2 * 23 + 1, text_width, 16),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             str(index.data(META_ROLE) or ""))
            control_ink = QColor("#6b7685")
            paint_eye(painter, rects["eye"], control_ink if visible else QColor("#a3abb7"),
                      visible)
            if "chevron" in rects:
                paint_chevron(painter, rects["chevron"], control_ink, item.isExpanded())
        paint_info(painter, rects["info"], QColor("#6b7685") if visible else QColor("#a3abb7"))
        painter.restore()


class ExpressionTree(QTreeWidget):
    """Expression list: colour dot picks a colour, eye hides, chevron expands."""

    swatch_clicked = Signal(str)
    #: (path name, segment index or -1 for a path row, row rectangle in global coordinates)
    info_clicked = Signal(str, int, QRect)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemDelegate(ExpressionDelegate(self))
        self.setMouseTracking(True)
        self.setIndentation(0)
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(False)
        self.setExpandsOnDoubleClick(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QTreeWidget.ScrollMode.ScrollPerPixel)

    def _row_rects(self, item: QTreeWidgetItem) -> dict[str, QRect]:
        rect = self.visualRect(self.indexFromItem(item, 0))
        if rect.isNull():
            return {}
        tag = item.data(0, Qt.ItemDataRole.UserRole)
        is_path = bool(tag) and tag[0] == "path"
        return expression_row_rects(rect, is_path, item.childCount() > 0)

    def _swatch_rect(self, item: QTreeWidgetItem) -> QRectF:
        swatch = self._row_rects(item).get("swatch")
        return QRectF(swatch) if swatch is not None else QRectF()

    def swatch_rect_for(self, item: QTreeWidgetItem) -> QRectF:
        return self._swatch_rect(item)

    def _item_swatch_rect(self, item) -> QRectF | None:
        if item is None:
            return None
        rect = self._swatch_rect(item)
        return rect if not rect.isNull() else None

    @staticmethod
    def _path_name(item) -> str | None:
        tag = item.data(0, Qt.ItemDataRole.UserRole)
        return tag[1] if tag else None

    def _control_at(self, position) -> tuple[QTreeWidgetItem | None, str | None]:
        item = self.itemAt(position)
        if item is None:
            return None, None
        for name, rect in self._row_rects(item).items():
            if name in ("swatch", "eye", "chevron", "info") and rect.contains(position):
                return item, name
        return item, None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            position = event.position().toPoint()
            item, control = self._control_at(position)
            if item is not None and control == "swatch":
                name = self._path_name(item)
                if name:
                    self.swatch_clicked.emit(name)
                    event.accept()
                    return
            if item is not None and control == "eye":
                checked = item.checkState(0) == Qt.CheckState.Checked
                item.setCheckState(0, Qt.CheckState.Unchecked if checked
                                   else Qt.CheckState.Checked)
                self.viewport().update()
                event.accept()
                return
            if item is not None and control == "chevron":
                item.setExpanded(not item.isExpanded())
                self.viewport().update()
                event.accept()
                return
            if item is not None and control == "info":
                tag = item.data(0, Qt.ItemDataRole.UserRole)
                if tag:
                    self.setCurrentItem(item)  # selects the row, which fills the details
                    row = self.visualRect(self.indexFromItem(item, 0))
                    row_global = QRect(self.viewport().mapToGlobal(row.topLeft()), row.size())
                    self.info_clicked.emit(tag[1], tag[2] if tag[0] == "segment" else -1,
                                           row_global)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        _, control = self._control_at(event.position().toPoint())
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if control
                                  else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)


class DropZone(QLabel):
    """Visible drag-and-drop target for supported image files."""

    image_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumHeight(112)
        self.setText("Drop an image here\nPNG · JPEG · BMP · WebP · TIFF")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
            self.setProperty("dragging", True)
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.image_dropped.emit(url.toLocalFile())
                break
        event.acceptProposedAction()


class InfoPopover(QWidget):
    """Floating details card opened from a row's info icon.

    It owns the inspector label, so the equations and control points are only
    on screen when asked for.  It closes on any outside click or Escape.
    """

    WIDTH = 460

    def __init__(self, parent: QWidget, content: QLabel):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("infoPopover")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(self.WIDTH)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 14)
        card = QFrame()
        card.setObjectName("infoCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        title = QLabel("Details")
        title.setObjectName("infoTitle")
        layout.addWidget(title)
        layout.addWidget(content)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(20, 26, 36, 70))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

    def show_beside(self, row: QRect, right_edge: int):
        """Open next to ``row``, to the right of the expression panel."""
        # Word-wrapped text needs its height computed for the fixed width,
        # otherwise the card is cut off at the bottom.
        layout = self.layout()
        layout.activate()
        self.resize(self.WIDTH, max(layout.totalHeightForWidth(self.WIDTH),
                                    layout.sizeHint().height()))
        screen = self.screen().availableGeometry()
        x = min(right_edge + 4, screen.right() - self.width() - 6)
        y = min(max(row.top() - 10, screen.top() + 6), screen.bottom() - self.height() - 6)
        self.move(x, y)
        self.show()


class SashHandle(QSplitterHandle):
    """Splitter divider drawn like a VS Code sash.

    Normally a 1 px hairline; on hover or drag it thickens to an accent bar.
    The handle itself stays a few pixels wide so it is easy to grab, and the
    gutter around the hairline is painted in each neighbour's own background
    so the panels still look like they touch.
    """

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hover = False
        self._pressed = False

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        splitter = self.splitter()
        before, after = splitter.sash_backgrounds(splitter.indexOf(self))
        painter = QPainter(self)
        rect = self.rect()
        horizontal = self.orientation() == Qt.Orientation.Horizontal
        size = rect.width() if horizontal else rect.height()
        middle = size // 2
        active = self._hover or self._pressed
        thickness = 3 if active else 1
        start = middle - (thickness // 2)
        if horizontal:
            painter.fillRect(0, 0, middle, rect.height(), before)
            painter.fillRect(middle, 0, size - middle, rect.height(), after)
            painter.fillRect(start, 0, thickness, rect.height(),
                             SASH_ACTIVE if active else SASH_LINE)
        else:
            painter.fillRect(0, 0, rect.width(), middle, before)
            painter.fillRect(0, middle, rect.width(), size - middle, after)
            painter.fillRect(0, start, rect.width(), thickness,
                             SASH_ACTIVE if active else SASH_LINE)


class SashSplitter(QSplitter):
    """QSplitter whose dividers are thin VS Code-style sashes."""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setHandleWidth(5)
        self._sash_backgrounds: dict[int, tuple[QColor, QColor]] = {}

    def set_sash_backgrounds(self, index: int, before: str, after: str):
        """Colours of the panels on either side of the handle at ``index``."""
        self._sash_backgrounds[index] = (QColor(before), QColor(after))

    def sash_backgrounds(self, index: int) -> tuple[QColor, QColor]:
        default = QColor(PANEL_BG)
        return self._sash_backgrounds.get(index, (default, default))

    def createHandle(self):
        return SashHandle(self.orientation(), self)


class WatermarkPanel(QWidget):
    """Drawer that paints the LiSSARA credit as a faint watermark.

    The mark is part of the panel's own background, so it sits behind the
    controls instead of taking up room like a footer would, and it never
    intercepts the mouse.  It is anchored to the panel's bottom-right corner.
    """

    WORDMARK = "LiSSARA"
    SUBMARK = "CORE"
    CREDITS = ("Engineered by Emtypyie&Co", "All Rights Reserved 2026")
    MARGIN_RIGHT = 20
    MARGIN_BOTTOM = 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    @staticmethod
    def _font(family: str, pixel_size: int, weight: QFont.Weight, tracking: float) -> QFont:
        font = QFont(family)
        font.setPixelSize(pixel_size)
        font.setWeight(weight)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, tracking)
        return font

    def paintEvent(self, event):
        option = QStyleOption()
        option.initFrom(self)
        painter = QPainter(self)
        # Stylesheet background first, then the watermark on top of it.
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, option, painter, self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        family = QApplication.font().family()
        right = self.width() - self.MARGIN_RIGHT
        width = max(self.width() - 2 * self.MARGIN_RIGHT, 40)
        left = right - width
        align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        y = self.height() - self.MARGIN_BOTTOM

        def ink(alpha: int) -> QColor:
            color = QColor(INK)
            color.setAlpha(alpha)
            return color

        # Credits, stacked upwards from the bottom edge.
        painter.setFont(self._font(family, 10, QFont.Weight.Normal, 0.4))
        painter.setPen(ink(92))
        for line in reversed(self.CREDITS):
            y -= 15
            painter.drawText(QRect(left, y, width, 15), align, line)
        # Short rule between the wordmark and the credits.
        y -= 10
        painter.setPen(QPen(ink(60), 1))
        painter.drawLine(right - 34, y, right, y)
        # "CORE" under the wordmark.
        y -= 10
        painter.setFont(self._font(family, 11, QFont.Weight.DemiBold, 7.0))
        painter.setPen(ink(70))
        y -= 16
        painter.drawText(QRect(left, y, width + 7, 16), align, self.SUBMARK)
        # Large, light wordmark.
        painter.setFont(self._font(family, 38, QFont.Weight.Light, 3.0))
        painter.setPen(ink(44))
        y -= 44
        painter.drawText(QRect(left, y, width + 3, 44), align, self.WORDMARK)


class LissaraGraphCalculator(QMainWindow):
    #: Width (px) of the invisible band along the window edge that starts a resize.
    RESIZE_MARGIN = 6

    def __init__(self):
        super().__init__()
        QApplication.instance().setFont(QFont(load_ui_font_family(), 10))
        # The native title bar is replaced by controls inside the top bar.
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self._edge_cursor_active = False
        self.setWindowTitle(APP_NAME)
        self.resize(1440, 900)
        self.setMinimumSize(920, 620)
        self.scene = QGraphicsScene(self)
        self.graph = GraphView(self.scene, self)
        self.graph.coordinates_changed.connect(self._show_coordinates)
        self.graph.image_dropped.connect(self._load_input)
        self.path_items: dict[str, CurveItem] = {}
        self.path_data: dict[str, dict] = {}
        self.path_colors: dict[str, str] = {}
        self.path_tree_items: dict[str, QTreeWidgetItem] = {}
        self.layers: dict[str, QToolButton] = {}
        self.input_path: str | None = None
        self.output_dir: Path | None = None
        self.scene_data: dict = {}
        self.image_width = self.image_height = 0
        self.selected_path: str | None = None
        self.control_items: list[QGraphicsItem] = []
        self._panel_sizes_ready = False
        self._build_ui()
        self.setAcceptDrops(True)
        self._set_busy(False)
        self._set_empty_graph()



    def _build_expression_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("expressionPanel")
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(480)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("expressionHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 14, 14, 12)
        header_layout.setSpacing(10)
        heading = QHBoxLayout()
        title = QLabel("Expressions")
        title.setObjectName("panelTitle")
        heading.addWidget(title)
        heading.addStretch(1)
        self.path_count = QLabel("0 paths")
        self.path_count.setObjectName("muted")
        heading.addWidget(self.path_count)
        header_layout.addLayout(heading)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search paths")
        self.search.textChanged.connect(self._filter_paths)
        header_layout.addWidget(self.search)
        outer.addWidget(header)

        self.tree = ExpressionTree()
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self._tree_selected)
        self.tree.itemChanged.connect(self._path_visibility_changed)
        self.tree.swatch_clicked.connect(self._choose_curve_color)
        outer.addWidget(self.tree, 1)
        self.empty_note = QLabel("Upload a drawing, then analyse it to see its mathematical paths here.")
        self.empty_note.setObjectName("emptyNote")
        self.empty_note.setWordWrap(True)
        outer.addWidget(self.empty_note)

        # Details (equations, control points) live in a popover opened by each
        # row's info icon instead of taking up room in the panel.
        self.inspect = QLabel("Select a path to inspect its cubic equations and control points.")
        self.inspect.setObjectName("inspector")
        self.inspect.setWordWrap(True)
        self.inspect.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.info_popover = InfoPopover(self, self.inspect)
        self.tree.info_clicked.connect(self._show_info)
        return panel

    def _show_info(self, name: str, segment: int, row: QRect):
        """Show the details popover for the row whose info icon was clicked."""
        right_edge = self.tree.mapToGlobal(QPoint(self.tree.width(), 0)).x()
        self.info_popover.show_beside(row, right_edge)

    def _build_graph_overlay(self):
        overlay = QVBoxLayout(self.graph)
        overlay.setContentsMargins(0, 0, 10, 10)
        overlay.setSpacing(6)
        overlay.addStretch(1)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addStretch(1)
        self.fit_button = QPushButton("Fit View")
        self.fit_button.setObjectName("graphControl")
        self.fit_button.setToolTip("Frame the complete reconstructed geometry")
        self.fit_button.clicked.connect(self._fit_view)
        self.reset_button = QPushButton("Reset View")
        self.reset_button.setObjectName("graphControl")
        self.reset_button.setToolTip("Return to the default origin-centred viewport")
        self.reset_button.clicked.connect(self.graph.reset_view)
        row.addWidget(self.fit_button)
        row.addWidget(self.reset_button)
        overlay.addLayout(row)
        for button in (self.fit_button, self.reset_button):
            button.setFixedHeight(24)
            button.raise_()

    @staticmethod
    def _nav_separator() -> QFrame:
        """Thin vertical hairline that groups related navbar controls."""
        line = QFrame()
        line.setObjectName("navSep")
        line.setFixedSize(1, 18)
        return line

    def _window_button(self, tip: str, svg: str, name: str, slot) -> QToolButton:
        """Minimise / maximise / close button that lives inside the top bar."""
        button = QToolButton()
        button.setObjectName(name)
        button.setToolTip(tip)
        button.setIcon(svg_icon(svg, size=16, color=NAV_TEXT))
        button.setIconSize(QSize(14, 14))
        button.setAutoRaise(True)
        button.setFixedSize(34, 28)
        button.clicked.connect(slot)
        return button

    def _toggle_maximise(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "maximise_button"):
            maximised = self.isMaximized()
            self.maximise_button.setIcon(
                svg_icon(RESTORE_SVG if maximised else MAXIMISE_SVG, size=16, color=NAV_TEXT))
            self.maximise_button.setToolTip("Restore" if maximised else "Maximise")

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("topBar")
        grid = QGridLayout(bar)
        grid.setContentsMargins(12, 6, 12, 6)
        grid.setHorizontalSpacing(8)

        left_group = QWidget()
        left = QHBoxLayout(left_group)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(6)
        self.export_icon_button = QToolButton()
        self.export_icon_button.setObjectName("iconButton")
        self.export_icon_button.setToolTip("Export the reconstruction")
        self.export_icon_button.setIcon(svg_icon(EXPORT_ICON_SVG, color=NAV_TEXT_DIM))
        self.export_icon_button.setIconSize(QSize(18, 18))
        self.export_icon_button.clicked.connect(self._toggle_export_panel)
        left.addWidget(self.export_icon_button)
        left.addWidget(self._nav_separator())
        self.upload_button = QPushButton("Upload Image")
        self.upload_button.setObjectName("primaryButton")
        self.upload_button.setIcon(svg_icon(UPLOAD_ICON_SVG, size=16, color="#12161d"))
        self.upload_button.setIconSize(QSize(15, 15))
        self.upload_button.setToolTip("Show or hide the upload panel · drop, choose or paste an image")
        self.upload_button.clicked.connect(self._toggle_upload_panel)
        left.addWidget(self.upload_button)
        self.analyse_button = QPushButton("Analyse")
        self.analyse_button.setObjectName("analyseButton")
        self.analyse_button.setIcon(svg_icon(ANALYSE_ICON_SVG, size=16, color="#ffffff"))
        self.analyse_button.setIconSize(QSize(15, 15))
        self.analyse_button.setToolTip("Trace contours and fit cubic Bézier paths")
        self.analyse_button.clicked.connect(self._analyse)
        left.addWidget(self.analyse_button)
        left.addStretch(1)

        right_group = QWidget()
        right = QHBoxLayout(right_group)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(6)
        right.addStretch(1)
        self.grid_combo = QComboBox()
        self.grid_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.grid_combo.setMinimumWidth(104)
        self.grid_combo.addItems(["Standard", "Fine", "Coarse"])
        self.grid_combo.setToolTip("Grid density")
        self.grid_combo.currentTextChanged.connect(self._grid_density_changed)
        right.addWidget(self.grid_combo)
        self.grid_toggle = QToolButton()
        self.grid_toggle.setText("Grid")
        self.grid_toggle.setCheckable(True)
        self.grid_toggle.setChecked(True)
        self.grid_toggle.setToolTip("Show or hide the coordinate grid")
        self.grid_toggle.toggled.connect(self._toggle_grid)
        right.addWidget(self.grid_toggle)
        right.addWidget(self._nav_separator())

        # The three layer toggles read as one segmented control.
        segments = QWidget()
        segments.setObjectName("segGroup")
        segment_layout = QHBoxLayout(segments)
        segment_layout.setContentsMargins(0, 0, 0, 0)
        segment_layout.setSpacing(0)
        layer_specs = (("original", "Original", "Show the uploaded source image"),
                       ("edges", "Edges", "Show the detected edge map"),
                       ("curves", "Curves", "Show the reconstructed cubic Bézier paths"))
        for position, (key, label, tip) in enumerate(layer_specs):
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setChecked(key in ("original", "curves"))
            button.setEnabled(False)
            button.setToolTip(tip)
            button.setProperty("seg", "first" if position == 0
                               else "last" if position == len(layer_specs) - 1 else "mid")
            button.toggled.connect(lambda on, layer=key: self._set_layer(layer, on))
            self.layers[key] = button
            segment_layout.addWidget(button)
        right.addWidget(segments)
        right.addWidget(self._nav_separator())
        self.minimise_button = self._window_button(
            "Minimise", MINIMISE_SVG, "winButton", self.showMinimized)
        self.maximise_button = self._window_button(
            "Maximise", MAXIMISE_SVG, "winButton", self._toggle_maximise)
        self.close_button = self._window_button(
            "Close", CLOSE_SVG, "winClose", self.close)
        for button in (self.minimise_button, self.maximise_button, self.close_button):
            right.addWidget(button)

        title = QLabel(APP_NAME)
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        for control in (self.grid_combo, self.grid_toggle, *self.layers.values(),
                        self.upload_button, self.analyse_button, self.export_icon_button):
            control.setFixedHeight(28)

        grid.addWidget(left_group, 0, 0)
        grid.addWidget(title, 0, 1)
        grid.addWidget(right_group, 0, 2)
        side = max(left_group.sizeHint().width(), right_group.sizeHint().width(), 300)
        grid.setColumnMinimumWidth(0, side)
        grid.setColumnMinimumWidth(2, side)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 1)
        self.setMinimumWidth(max(940, 2 * side + title.sizeHint().width() + 60))
        self.top_bar_title = title
        self.top_bar = bar
        return bar

    def _build_export_panel(self) -> QWidget:
        panel = QWidget(self)
        panel.setObjectName("exportPanel")
        panel.setFixedWidth(EXPORT_PANEL_WIDTH)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)
        header = QHBoxLayout()
        title = QLabel("Export")
        title.setObjectName("drawerTitle")
        header.addWidget(title)
        header.addStretch(1)
        close = QToolButton()
        close.setObjectName("iconButton")
        close.setToolTip("Close the export panel")
        close.setIcon(svg_icon(CLOSE_SVG, size=16, color="#5d6777"))
        close.setIconSize(QSize(14, 14))
        close.setAutoRaise(True)
        close.clicked.connect(lambda: self._close_panel(panel))
        header.addWidget(close)
        layout.addLayout(header)
        intro = QLabel("Save the complete reconstruction as machine-readable mathematics. "
                       "Every path and cubic segment is exported, not just the selection.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.export_scope_label = QLabel("No scene loaded")
        self.export_scope_label.setObjectName("scopeLabel")
        self.export_scope_label.setWordWrap(True)
        layout.addWidget(self.export_scope_label)
        self.export_hint = QLabel("Nothing to export yet. Upload an image and press Analyse "
                                  "\u2014 the export buttons unlock once paths exist.")
        self.export_hint.setObjectName("exportHint")
        self.export_hint.setWordWrap(True)
        layout.addWidget(self.export_hint)
        self.export_json_button = QPushButton("Export Equations (JSON)")
        self.export_json_button.setObjectName("drawerAction")
        self.export_json_button.setToolTip("Save equation.json · all paths, segments, "
                                           "control points and polynomial coefficients")
        self.export_json_button.clicked.connect(self._export_equations_json)
        layout.addWidget(self.export_json_button)
        self.export_svg_button = QPushButton("Export Curves (SVG)")
        self.export_svg_button.setObjectName("drawerAction")
        self.export_svg_button.setToolTip("Save curves.svg · exact cubic Bézier geometry, "
                                          "one independent path per contour")
        self.export_svg_button.clicked.connect(self._export_curves_svg)
        layout.addWidget(self.export_svg_button)
        self.export_status = QLabel("")
        self.export_status.setObjectName("muted")
        self.export_status.setWordWrap(True)
        self.export_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.export_status)
        layout.addStretch(1)
        for button in (self.export_json_button, self.export_svg_button):
            button.setEnabled(False)
        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(20, 26, 36, 62))
        panel.setGraphicsEffect(shadow)
        panel.hide()
        return panel

    def _build_upload_panel(self) -> QWidget:
        panel = WatermarkPanel()
        panel.setObjectName("uploadPanel")
        panel.setMinimumWidth(UPLOAD_PANEL_WIDTH - 40)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)
        header = QHBoxLayout()
        title = QLabel("Upload Image")
        title.setObjectName("drawerTitle")
        header.addWidget(title)
        header.addStretch(1)
        close = QToolButton()
        close.setObjectName("iconButton")
        close.setToolTip("Close the upload panel")
        close.setIcon(svg_icon(CLOSE_SVG, size=16, color="#5d6777"))
        close.setIconSize(QSize(14, 14))
        close.setAutoRaise(True)
        close.clicked.connect(lambda: self._close_panel(panel))
        header.addWidget(close)
        layout.addLayout(header)

        self.drop_zone = DropZone()
        self.drop_zone.image_dropped.connect(self._load_input)
        layout.addWidget(self.drop_zone)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.choose_file_button = QPushButton("Choose File")
        self.choose_file_button.setObjectName("drawerAction")
        self.choose_file_button.setToolTip("Choose an image file from disk")
        self.choose_file_button.clicked.connect(self._choose_image)
        actions.addWidget(self.choose_file_button)
        self.paste_button = QPushButton("Paste Image")
        self.paste_button.setObjectName("drawerAction")
        self.paste_button.setToolTip("Use an image from the clipboard (screenshots work)")
        self.paste_button.clicked.connect(self._paste_image)
        actions.addWidget(self.paste_button)
        layout.addLayout(actions)

        self.upload_filename = QLabel("No image loaded")
        self.upload_filename.setObjectName("fileName")
        self.upload_filename.setWordWrap(True)
        layout.addWidget(self.upload_filename)
        self.upload_dimensions = QLabel("")
        self.upload_dimensions.setObjectName("muted")
        layout.addWidget(self.upload_dimensions)
        self.upload_preview = QLabel()
        self.upload_preview.setObjectName("previewFrame")
        self.upload_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.upload_preview.setMinimumHeight(170)
        self.upload_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.upload_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.upload_preview.setToolTip("Click to choose another image")
        layout.addWidget(self.upload_preview)

        self.upload_analyse_button = QPushButton("Analyse Image")
        self.upload_analyse_button.setObjectName("primaryButton")
        self.upload_analyse_button.setEnabled(False)
        self.upload_analyse_button.setToolTip("Run the reconstruction pipeline on this image")
        self.upload_analyse_button.clicked.connect(self._analyse)
        layout.addWidget(self.upload_analyse_button)
        self.upload_status = QLabel("")
        self.upload_status.setObjectName("muted")
        self.upload_status.setWordWrap(True)
        self.upload_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.upload_status)
        layout.addStretch(1)
        return panel

    def _build_ui(self):
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_top_bar())
        self._build_graph_overlay()

        expression_panel = self._build_expression_panel()
        self.export_panel = self._build_export_panel()
        self.upload_panel = self._build_upload_panel()

        self.splitter = SashSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(expression_panel)
        self.splitter.addWidget(self.graph)
        self.splitter.addWidget(self.upload_panel)
        for index in range(self.splitter.count()):
            self.splitter.setCollapsible(index, False)
        self.splitter.set_sash_backgrounds(1, PANEL_BG, CANVAS_BG)
        self.splitter.set_sash_backgrounds(2, CANVAS_BG, PANEL_BG)
        # The upload panel starts open; the user can close it from its header
        # or toggle it with the navbar's Upload Image button.
        self._refresh_splitter_sizes(1100)
        layout.addWidget(self.splitter, 1)

        status = QWidget()
        status.setObjectName("statusBar")
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(14, 5, 14, 5)
        self.status = QLabel("Ready · Drop an image anywhere to begin")
        self.status.setObjectName("muted")
        status_layout.addWidget(self.status)
        status_layout.addStretch(1)
        self.coordinates = QLabel("x 0 · y 0")
        self.coordinates.setObjectName("muted")
        status_layout.addWidget(self.coordinates)
        layout.addWidget(status)
        self.setCentralWidget(root)
        for widget in (self, *self.findChildren(QWidget)):
            widget.setMouseTracking(True)
        QApplication.instance().installEventFilter(self)
        self.setStyleSheet(build_stylesheet())

    def _close_panel(self, panel: QWidget):
        panel.hide()

    def _toggle_export_panel(self):
        if self.export_panel.isVisible():
            self.export_panel.hide()
            return
        self.export_panel.show()
        self.export_panel.raise_()
        self._position_export_panel()

    def _position_export_panel(self):
        if not self.export_panel.isVisible():
            return
        self.export_panel.adjustSize()
        width = self.export_panel.width()
        height = self.export_panel.height()
        origin = self.export_icon_button.mapTo(self, QPoint(0, self.export_icon_button.height() + 6))
        max_left = max(self.width() - width - 14, 12)
        max_top = max(self.height() - height - 14, 12)
        self.export_panel.move(min(origin.x(), max_left), min(origin.y(), max_top))

    def _is_within_export_panel(self, widget) -> bool:
        if widget in (self.export_panel, self.export_icon_button):
            return True
        return isinstance(widget, QWidget) and self.export_panel.isAncestorOf(widget)

    def _resize_edges(self, global_pos: QPoint) -> Qt.Edge:
        """Window edges within the resize band at ``global_pos`` (none when maximised)."""
        none = Qt.Edge(0)
        if self.isMaximized() or self.isFullScreen():
            return none
        local = self.mapFromGlobal(global_pos)
        margin = self.RESIZE_MARGIN
        edges = none
        if local.x() <= margin:
            edges |= Qt.Edge.LeftEdge
        elif local.x() >= self.width() - margin:
            edges |= Qt.Edge.RightEdge
        if local.y() <= margin:
            edges |= Qt.Edge.TopEdge
        elif local.y() >= self.height() - margin:
            edges |= Qt.Edge.BottomEdge
        return edges

    @staticmethod
    def _edge_cursor(edges: Qt.Edge):
        horizontal = bool(edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge))
        vertical = bool(edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge))
        if horizontal and vertical:
            diagonal_back = bool(edges & Qt.Edge.LeftEdge) == bool(edges & Qt.Edge.TopEdge)
            return (Qt.CursorShape.SizeFDiagCursor if diagonal_back
                    else Qt.CursorShape.SizeBDiagCursor)
        if horizontal:
            return Qt.CursorShape.SizeHorCursor
        if vertical:
            return Qt.CursorShape.SizeVerCursor
        return None

    def _update_edge_cursor(self, global_pos: QPoint):
        shape = self._edge_cursor(self._resize_edges(global_pos))
        if shape is None:
            if self._edge_cursor_active:
                QApplication.restoreOverrideCursor()
                self._edge_cursor_active = False
        elif self._edge_cursor_active:
            QApplication.changeOverrideCursor(shape)
        else:
            QApplication.setOverrideCursor(shape)
            self._edge_cursor_active = True

    def _clear_edge_cursor(self):
        if self._edge_cursor_active:
            QApplication.restoreOverrideCursor()
            self._edge_cursor_active = False

    def _handle_window_chrome(self, obj, event) -> bool:
        """Frameless-window behaviour: edge resize, drag by the top bar, double-click."""
        kind = event.type()
        if kind == QEvent.Type.Leave and obj is self:
            self._clear_edge_cursor()
            return False
        if not (isinstance(obj, QWidget) and (obj is self or self.isAncestorOf(obj))):
            return False
        if kind == QEvent.Type.MouseMove:
            if not event.buttons():
                self._update_edge_cursor(event.globalPosition().toPoint())
            return False
        left_button = getattr(event, "button", lambda: None)() == Qt.MouseButton.LeftButton
        if kind == QEvent.Type.MouseButtonPress and left_button:
            handle = self.windowHandle()
            if handle is None:
                return False
            edges = self._resize_edges(event.globalPosition().toPoint())
            if edges:
                handle.startSystemResize(edges)
                return True
            if obj is self.top_bar:
                handle.startSystemMove()
                return True
        elif kind == QEvent.Type.MouseButtonDblClick and left_button and obj is self.top_bar:
            self._toggle_maximise()
            return True
        return False

    def eventFilter(self, obj, event):
        if self._handle_window_chrome(obj, event):
            return True
        # A real click reaches the application filter twice: first aimed at the
        # native window object (a QWindow, not a QWidget), then at the widget
        # under the cursor.  Only the widget delivery says what was clicked;
        # judging the window delivery would close the popup before its own
        # buttons ever received the press.
        if (self.export_panel.isVisible()
                and event.type() == QEvent.Type.MouseButtonPress
                and isinstance(obj, QWidget)
                and not self._is_within_export_panel(obj)):
            self.export_panel.hide()
        return False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.export_panel.isVisible():
            self.export_panel.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.export_panel.isVisible():
            self._position_export_panel()

    def _toggle_upload_panel(self):
        self.upload_panel.setVisible(self.upload_panel.isHidden())
        self._refresh_splitter_sizes()

    def _refresh_splitter_sizes(self, graph_width: int | None = None):
        # isHidden() (not isVisible()) so the answer is right before the
        # window has been shown for the first time.
        upload_visible = not self.upload_panel.isHidden()
        handles = 2 if upload_visible else 1
        reserved = (UPLOAD_PANEL_WIDTH if upload_visible else 0) + \
                   EXPRESSION_PANEL_WIDTH + handles * self.splitter.handleWidth()
        available = max(self.splitter.size().width() - reserved, 320)
        graph_width = available if graph_width is None else min(graph_width, available)
        self.splitter.setSizes([
            EXPRESSION_PANEL_WIDTH,
            graph_width,
            UPLOAD_PANEL_WIDTH if upload_visible else 0,
        ])



    def showEvent(self, event):
        super().showEvent(event)
        if not self._panel_sizes_ready:
            self._panel_sizes_ready = True
            # The splitter only has its real width once the first layout pass
            # has run, so size the panels on the next event-loop turn.
            QTimer.singleShot(0, self._apply_initial_panel_sizes)

    def _apply_initial_panel_sizes(self):
        self._refresh_splitter_sizes(1100)

    def _set_empty_graph(self):
        self.scene.clear()
        self.scene_data = {}
        self.scene.setBackgroundBrush(QColor(CANVAS_BG))
        self.graph.viewport().update()
        self.graph.reset_view()
        self._update_export_actions()
        self.status.setText("Ready · Drop an image anywhere to begin")
    def _toggle_grid(self, visible: bool):
        self.graph.setProperty("gridVisible", visible)
        self.graph.viewport().update()

    def _grid_density_changed(self, value: str):
        self.graph.setProperty("gridDensity", value)
        self.graph.viewport().update()

    def _choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose an image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)")
        if path:
            self._load_input(path)

    def _paste_image(self):
        clipboard = QApplication.clipboard()
        image = clipboard.image() if clipboard is not None else QImage()
        if image is None or image.isNull():
            message = "Clipboard has no image · copy or screenshot an image first"
            self.upload_status.setText(message)
            self.status.setText(message)
            return
        destination = (Path(tempfile.gettempdir()) /
                       f"lissara_clipboard_{datetime.now():%Y%m%d-%H%M%S-%f}.png")
        if not image.save(str(destination)):
            message = "Could not save the clipboard image"
            self.upload_status.setText(message)
            self.status.setText(message)
            return
        self._load_input(str(destination))

    def _update_upload_panel(self):
        if not self.input_path:
            self.upload_filename.setText("No image loaded")
            self.upload_dimensions.setText("")
            self.upload_preview.setPixmap(QPixmap())
            self.upload_analyse_button.setEnabled(False)
            self.upload_status.setText("Paste, drop or choose an image to begin.")
            return
        image = QImage(self.input_path)
        self.upload_filename.setText(Path(self.input_path).name)
        self.upload_dimensions.setText(f"{image.width()} × {image.height()} px")
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            self.upload_preview.setPixmap(QPixmap())
        else:
            self.upload_preview.setPixmap(
                pixmap.scaled(max(self.upload_preview.width() - 24, 160), 150,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation))
        self.upload_analyse_button.setEnabled(True)
        self.upload_status.setText("Ready · click Analyse Image")

    def _load_input(self, path: str):
        if not QImage(path).isNull():
            self.input_path = str(Path(path).resolve())
            self._update_upload_panel()
            self.status.setText(f"Image ready · {Path(path).name} · Click Analyse")
            self.analyse_button.setEnabled(True)
        else:
            QMessageBox.warning(self, "Could not open image", "Choose a supported image file.")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self._load_input(url.toLocalFile())
                break
        event.acceptProposedAction()

    def _set_busy(self, busy: bool):
        self.upload_button.setEnabled(not busy)
        self.analyse_button.setEnabled(not busy and bool(self.input_path))
        self.fit_button.setEnabled(not busy)
        self.reset_button.setEnabled(not busy)
        self.upload_analyse_button.setEnabled(not busy and bool(self.input_path))
        self.choose_file_button.setEnabled(not busy)
        self.paste_button.setEnabled(not busy)

    def _analyse(self):
        if not self.input_path:
            self.upload_panel.setVisible(True)
            self._refresh_splitter_sizes()
            message = "Choose an image to analyse · upload panel opened"
            self.status.setText(message)
            self.upload_status.setText(message)
            return
        if getattr(sys, "frozen", False):
            data_root = Path(QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppLocalDataLocation))
            output_root = data_root / "outputs" / "gui_runs"
        else:
            output_root = ROOT / "outputs" / "gui_runs"
        out = output_root / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.output_dir = out
        self._set_busy(True)
        self.status.setText("Analysing · tracing contours and fitting cubic Bézier paths…")
        self.upload_status.setText("Analysing · tracing contours and fitting cubic Bézier paths…")
        self._thread = QThread(self)
        self._worker = ReconstructionWorker(self.input_path, out)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._analysis_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _analysis_finished(self, output_dir: str, error: str):
        self._set_busy(False)
        if error:
            self.status.setText("Analysis failed · see details")
            self.upload_status.setText("Analysis failed · see the error dialog")
            QMessageBox.critical(self, "Analysis failed", error[-3500:])
            return
        self.output_dir = Path(output_dir)
        self._show_scene(self.output_dir)
        self.upload_status.setText(
            f"Analysis complete · {len(self.path_data)} paths · click Analyse Image again "
            f"or drop another image")



    def _show_scene(self, output_dir: Path):
        data = json.loads((output_dir / "scene.json").read_text(encoding="utf-8"))
        self.scene_data = data
        self.image_width, self.image_height = data["width"], data["height"]
        self.scene.clear()
        self.path_items.clear()
        self.path_data.clear()
        self.path_colors.clear()
        self.path_tree_items.clear()
        self.control_items.clear()
        if self.input_path:
            source = QPixmap(self.input_path)
            if not source.isNull():
                source = source.transformed(QTransform().scale(1, -1),
                                            Qt.TransformationMode.SmoothTransformation)
                source_item = QGraphicsPixmapItem(source)
                source_item.setPos(-self.image_width / 2, -self.image_height / 2)
                source_item.setOpacity(.16)
                source_item.setZValue(-10)
                source_item.setData(0, "original")
                self.scene.addItem(source_item)
        self.tree.clear()
        total_segments = 0
        paths = data.get("paths", [])
        for index, path in enumerate(paths):
            name = str(path.get("path_id") or f"path-{index + 1:03d}")
            segments = path.get("segments") or []
            total_segments += len(segments)
            color = DEFAULT_CURVE_COLOR
            self.path_data[name] = path
            self.path_colors[name] = color
            item = CurveItem(name, cubic_path(path, self.image_width, self.image_height), color)
            item.on_selected = self._select_path
            item.setData(0, "curve")
            item.setZValue(index)
            self.scene.addItem(item)
            self.path_items[name] = item
            label = (f"{segment_equation_summary(segments[0], self.image_width, self.image_height)}"
                     f"     {len(segments)} cubics" if segments else f"{name}     no cubics")
            parent = QTreeWidgetItem([label])
            parent.setData(0, Qt.ItemDataRole.UserRole, ("path", name))
            parent.setData(0, ROW_ROLE, index + 1)
            if segments:
                first_x, first_y = segment_equations(segments[0], self.image_width,
                                                     self.image_height)
                parent.setData(0, X_ROLE, pretty_polynomial(first_x))
                parent.setData(0, Y_ROLE, pretty_polynomial(first_y))
                parent.setData(0, META_ROLE,
                               f"{len(segments)} cubic segment{'s' if len(segments) != 1 else ''}"
                               f"  \u00b7  {'closed' if path.get('closed') else 'open'}")
            else:
                parent.setData(0, META_ROLE, "no cubic segments")
            parent.setToolTip(0, f"{path.get('path_id', name)} · {path.get('path_type', 'path')} · {len(segments)} cubic Bézier segments · {'closed' if path.get('closed') else 'open'}")
            parent.setData(0, COLOR_ROLE, color)
            parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            parent.setCheckState(0, Qt.CheckState.Checked)
            self.tree.addTopLevelItem(parent)
            self.path_tree_items[name] = parent
            for segment_index, segment in enumerate(segments):
                child = QTreeWidgetItem([
                    f"Cubic {segment_index + 1:03d} · "
                    f"{segment_equation_summary(segment, self.image_width, self.image_height)}"])
                child.setData(0, Qt.ItemDataRole.UserRole, ("segment", name, segment_index))
                child.setData(0, COLOR_ROLE, color)
                child.setData(0, ROW_ROLE, segment_index + 1)
                seg_x, seg_y = segment_equations(segment, self.image_width, self.image_height)
                child.setData(0, X_ROLE, pretty_polynomial(seg_x))
                child.setData(0, Y_ROLE, pretty_polynomial(seg_y))
                cp = segment["control_points"]
                child.setToolTip(0, "P0 ({:.2f}, {:.2f}) → P3 ({:.2f}, {:.2f})".format(*cp[0], *cp[3]))
                parent.addChild(child)
        self.tree.setVisible(bool(paths))
        self.empty_note.setVisible(not bool(paths))
        self.path_count.setText(f"{len(paths)} paths · {total_segments} cubics")
        self._add_image_layers(output_dir)
        self._update_export_actions()
        bounds = self._image_content_rect()
        self.graph.set_content_rect(bounds)
        for button in self.layers.values():
            button.setEnabled(True)
        self.layers["edges"].setEnabled((output_dir / "edges.png").exists())
        self._fit_view()
        self.status.setText(f"Analysis complete · {len(self.path_data)} paths · {total_segments} cubic segments · source image coordinates centered at origin")
        self._filter_paths(self.search.text())

    def _add_image_layers(self, output_dir: Path):
        # Stage toggles stay in the toolbar. Source starts visible as a faint
        # reference; reconstructed paths are the actual interactive geometry.
        edges_path = output_dir / "edges.png"
        if edges_path.exists():
            image = QImage(str(edges_path)).convertToFormat(QImage.Format.Format_Grayscale8)
            pixmap = QPixmap.fromImage(image).transformed(
                QTransform().scale(1, -1), Qt.TransformationMode.SmoothTransformation)
            item = QGraphicsPixmapItem(pixmap)
            item.setPos(-self.image_width / 2, -self.image_height / 2)
            item.setOpacity(.52)
            item.setZValue(-5)
            item.setData(0, "edges")
            item.setVisible(self.layers["edges"].isChecked())
            self.scene.addItem(item)
        for item in self.scene.items():
            if item.data(0) == "original":
                item.setVisible(self.layers["original"].isChecked())
            elif item.data(0) == "curve":
                item.setVisible(self.layers["curves"].isChecked())


    LAYER_ITEM_TAGS = {"original": "original", "edges": "edges", "curves": "curve"}

    def _set_layer(self, key: str, visible: bool):
        tag = self.LAYER_ITEM_TAGS.get(key, key)
        for item in self.scene.items():
            if item.data(0) == tag:
                item.setVisible(visible)
        if key == "curves":
            for item in self.control_items:
                item.setVisible(visible)

    def _image_content_rect(self) -> QRectF:
        """Centred frame of the source image (the navigation anchor)."""
        if self.image_width and self.image_height:
            return QRectF(-self.image_width / 2, -self.image_height / 2,
                          self.image_width, self.image_height)
        return QRectF(DEFAULT_CONTENT_RECT)

    def _geometry_rect(self) -> QRectF:
        """Scene bounds of the visible reconstructed geometry."""
        rect = QRectF()
        for item in self.path_items.values():
            if not item.isVisible():
                continue
            bounds = item.boundingRect()
            rect = QRectF(bounds) if rect.isNull() else rect.united(bounds)
        if rect.isNull():
            if self.image_width and self.image_height:
                rect = QRectF(-self.image_width / 2, -self.image_height / 2,
                              self.image_width, self.image_height)
            else:
                rect = QRectF(DEFAULT_CONTENT_RECT)
        return rect

    def _fit_view(self):
        self.graph.fit_rect(self._geometry_rect())



    def _filter_paths(self, text: str):
        needle = text.strip().casefold()
        for name, item in self.path_tree_items.items():
            item.setHidden(bool(needle and needle not in name.casefold()))

    def _tree_selected(self):
        selected = self.tree.selectedItems()
        if not selected:
            return
        tag = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if not tag:
            return
        if tag[0] == "path":
            name = tag[1]
            self._select_path(name, from_tree=True)
            self._inspect_path(name)
        elif tag[0] == "segment":
            _, name, index = tag
            self._select_path(name, from_tree=True)
            self._inspect_segment(name, index)

    def _select_path(self, name: str, from_tree: bool = False):
        self._clear_control_items()
        self.selected_path = name
        self._apply_path_styles()
        if not from_tree:
            tree_item = self.path_tree_items.get(name)
            if tree_item is not None:
                was_blocked = self.tree.blockSignals(True)
                if self.tree.currentItem() is not tree_item:
                    self.tree.setCurrentItem(tree_item)
                    self.tree.scrollToItem(tree_item)
                self.tree.blockSignals(was_blocked)
            self._inspect_path(name)

    def _apply_path_styles(self):
        """Push configured colours; the selected path is thicker, not recoloured."""
        for path_name, item in self.path_items.items():
            color = QColor(self.path_colors.get(path_name, DEFAULT_CURVE_COLOR))
            pen = QPen(color, 3.6 if path_name == self.selected_path else 1.8)
            pen.setCosmetic(True)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            item.setPen(pen)

    def _choose_curve_color(self, name: str):
        if name not in self.path_colors:
            return
        current = QColor(self.path_colors[name])
        color = QColorDialog.getColor(current, self, f"Curve colour · {name}")
        if not color.isValid():
            self.status.setText(f"Curve colour unchanged · {name}")
            return
        self.path_colors[name] = color.name()
        item = self.path_tree_items.get(name)
        if item is not None:
            item.setData(0, COLOR_ROLE, color.name())
            for index in range(item.childCount()):
                item.child(index).setData(0, COLOR_ROLE, color.name())
        self.tree.viewport().update()
        self._apply_path_styles()
        self.status.setText(f"Curve colour · {name} → {color.name()}")

    def _path_visibility_changed(self, item: QTreeWidgetItem, column: int):
        tag = item.data(0, Qt.ItemDataRole.UserRole)
        if tag and tag[0] == "path":
            path_item = self.path_items.get(tag[1])
            if path_item:
                path_item.setVisible(item.checkState(0) == Qt.CheckState.Checked)

    def _inspect_path(self, name: str):
        segments = self.path_data[name].get("segments") or []
        if not segments:
            self._clear_control_items()
            path = self.path_data[name]
            self.inspect.setText(
                f"path: {name}\n"
                f"id: {path.get('path_id', name)}\n"
                f"{path.get('path_type', 'path')} · "
                f"{'closed' if path.get('closed') else 'open'}\n"
                f"this path has no cubic segments")
            return
        self._inspect_segment(name, 0)

    def _inspect_segment(self, name: str, index: int):
        self._clear_control_items()
        path = self.path_data[name]
        segments = path.get("segments") or []
        segment = segments[index]
        cp = segment["control_points"]
        graph_cp = [image_to_graph(x, y, self.image_width, self.image_height) for x, y in cp]
        segment_curve = QPainterPath(graph_cp[0])
        segment_curve.cubicTo(graph_cp[1], graph_cp[2], graph_cp[3])
        highlighted = QGraphicsPathItem(segment_curve)
        highlight_color = QColor(self.path_colors.get(name, DEFAULT_CURVE_COLOR))
        highlighted.setPen(QPen(highlight_color, 4.2))
        highlighted.setBrush(Qt.BrushStyle.NoBrush)
        highlighted.setZValue(10000)
        self.scene.addItem(highlighted)
        self.control_items.append(highlighted)
        polygon = QPainterPath(graph_cp[0])
        for point in graph_cp[1:]:
            polygon.lineTo(point)
        guide = QPen(QColor("#a4acb8"), 1.2, Qt.PenStyle.DashLine)
        guide.setCosmetic(True)
        polygon_item = QGraphicsPathItem(polygon)
        polygon_item.setPen(guide)
        polygon_item.setZValue(10001)
        self.scene.addItem(polygon_item)
        self.control_items.append(polygon_item)
        for point in graph_cp:
            dot = QGraphicsEllipseItem(QRectF(point.x() - 3.3, point.y() - 3.3, 6.6, 6.6))
            dot.setBrush(QColor("#ffffff"))
            dot.setPen(QPen(QColor("#27364a"), 1.6))
            dot.setZValue(10002)
            self.scene.addItem(dot)
            self.control_items.append(dot)
        points = "\n".join(
            "   ".join(f"P{i}=({graph_cp[i].x():.2f}, {graph_cp[i].y():.2f})"
                      for i in pair) for pair in ((0, 1), (2, 3)))
        x_coeffs, y_coeffs = segment_equations(segment, self.image_width, self.image_height)
        self.inspect.setText(
            f"path: {name}\n"
            f"id: {path.get('path_id', name)}\n"
            f"{path.get('path_type', 'path')} · "
            f"{'closed' if path.get('closed') else 'open'} · "
            f"{len(segments)} cubic segments\n\n"
            f"segment {index + 1} of {len(segments)}\n\n"
            f"{points}\n\n"
            f"{format_polynomial('x', x_coeffs)}\n"
            f"{format_polynomial('y', y_coeffs)}\n"
            f"0 \u2264 t \u2264 1")

    def _show_coordinates(self, x: float, y: float):
        self.coordinates.setText(f"x {x:.1f} · y {y:.1f}")

    # ------------------------------------------------------------------ exports

    def _update_export_actions(self):
        paths = self.scene_data.get("paths") or []
        segment_count = sum(len(p.get("segments") or []) for p in paths)
        has_scene = bool(paths)
        self.export_json_button.setEnabled(has_scene)
        self.export_svg_button.setEnabled(has_scene)
        if hasattr(self, "export_hint"):
            self.export_hint.setVisible(not has_scene)
        json_tip = ("Save equation.json \u00b7 all paths, segments, "
                    "control points and polynomial coefficients")
        svg_tip = ("Save curves.svg \u00b7 exact cubic B\u00e9zier geometry, "
                   "one independent path per contour")
        need_scene = "Analyse an image first \u00b7 there is nothing to export yet"
        self.export_json_button.setToolTip(json_tip if has_scene else need_scene)
        self.export_svg_button.setToolTip(svg_tip if has_scene else need_scene)
        self.export_scope_label.setText(
            f"{len(paths)} paths · {segment_count} cubic segments"
            if has_scene else "No scene loaded")
        if hasattr(self, "export_status"):
            self.export_status.setText("")

    def _export_equations_json(self):
        if not self.scene_data.get("paths"):
            self.status.setText("Nothing to export · analyse an image first")
            self.export_status.setText("Nothing to export · analyse an image first")
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, "Export Equations (JSON)", "equation.json", "JSON documents (*.json)")
        if not destination:
            return
        try:
            document = build_equation_document(self.scene_data)
            Path(destination).write_text(json.dumps(document, indent=2), encoding="utf-8")
        except Exception as error:
            QMessageBox.critical(self, "Export failed",
                                 f"Could not write {destination}:\n{error}")
            self.status.setText("Export failed · equations not saved")
            self.export_status.setText("Export failed · equations not saved")
            return
        message = (f"Exported equations · {document['path_count']} paths · "
                   f"{document['segment_count']} cubic segments → {Path(destination).name}")
        self.status.setText(message)
        self.export_status.setText(message)

    def _export_curves_svg(self):
        if not self.scene_data.get("paths"):
            self.status.setText("Nothing to export · analyse an image first")
            self.export_status.setText("Nothing to export · analyse an image first")
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, "Export Curves (SVG)", "curves.svg", "SVG drawings (*.svg)")
        if not destination:
            return
        try:
            svg = build_scene_svg(self.scene_data, self.path_colors)
            Path(destination).write_text(svg, encoding="utf-8")
        except Exception as error:
            QMessageBox.critical(self, "Export failed",
                                 f"Could not write {destination}:\n{error}")
            self.status.setText("Export failed · curves not saved")
            self.export_status.setText("Export failed · curves not saved")
            return
        message = f"Exported curves · {len(self.path_data)} paths → {Path(destination).name}"
        self.status.setText(message)
        self.export_status.setText(message)

    def _clear_control_items(self):
        for item in self.control_items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)
        self.control_items.clear()


STYLESHEET = """
    QMainWindow { background:#e9edf3; color:#1f2733; }

    /* ---- navigation bar (dark) -------------------------------------- */
    QWidget#topBar { background:qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #1e222b, stop:1 #161a21); border-bottom:1px solid #2b313d; }
    QLabel#appTitle { color:#eef2f8; font-size:14px; font-weight:700; letter-spacing:2px; }
    QFrame#navSep { background:#333a48; border:0; }

    QWidget#topBar QPushButton { background:#262b36; color:#d7deea; border:1px solid #363d4b;
        border-radius:5px; padding:3px 12px; font-size:11px; }
    QWidget#topBar QPushButton:hover { background:#303747; border-color:#454e61; }
    QWidget#topBar QPushButton:pressed { background:#1d222c; }
    QWidget#topBar QPushButton:disabled { background:#20242d; color:#687184; border-color:#2b313d; }
    QWidget#topBar QPushButton#primaryButton { background:#e7ecf4; color:#12161d;
        border-color:#e7ecf4; font-weight:600; }
    QWidget#topBar QPushButton#primaryButton:hover { background:#ffffff; border-color:#ffffff; }
    QWidget#topBar QPushButton#primaryButton:pressed { background:#cdd5e2; border-color:#cdd5e2; }
    QWidget#topBar QPushButton#primaryButton:disabled { background:#20242d; color:#687184;
        border-color:#2b313d; }
    QWidget#topBar QPushButton#analyseButton { background:#4a7fd6; color:#ffffff;
        border-color:#4a7fd6; font-weight:600; }
    QWidget#topBar QPushButton#analyseButton:hover { background:#5c8fe6; border-color:#5c8fe6; }
    QWidget#topBar QPushButton#analyseButton:pressed { background:#3d6cbb; border-color:#3d6cbb; }
    QWidget#topBar QPushButton#analyseButton:disabled { background:#20242d;
        border-color:#2b313d; color:#687184; }

    QWidget#topBar QComboBox { background:#262b36; color:#d7deea; border:1px solid #363d4b;
        border-radius:5px; padding:2px 24px 2px 9px; font-size:11px; }
    QWidget#topBar QComboBox:hover { border-color:#454e61; background:#2c3240; }
    QWidget#topBar QComboBox::drop-down { border:0; width:22px; }
    QWidget#topBar QComboBox QAbstractItemView { background:#1f242d; color:#d7deea;
        border:1px solid #363d4b; outline:0; selection-background-color:#35538a;
        selection-color:#ffffff; }

    QWidget#topBar QToolButton { background:transparent; color:#aab4c5;
        border:1px solid transparent; border-radius:5px; padding:4px 10px; font-size:11px; }
    QWidget#topBar QToolButton:hover { background:#2a303c; color:#f1f4f9; border-color:#363d4b; }
    QWidget#topBar QToolButton:checked { background:#2a3d5e; color:#b4d0ff; border-color:#3d5a8c; }
    QWidget#topBar QToolButton:disabled { color:#5f6879; }
    QWidget#topBar QToolButton#iconButton { background:transparent; border:1px solid transparent;
        padding:4px; }
    QWidget#topBar QToolButton#iconButton:hover { background:#2a303c; border-color:#363d4b; }

    /* window controls (minimise / maximise / close) */
    QWidget#topBar QToolButton#winButton, QWidget#topBar QToolButton#winClose {
        background:transparent; border:0; border-radius:6px; padding:0; }
    QWidget#topBar QToolButton#winButton:hover { background:#2e3544; }
    QWidget#topBar QToolButton#winButton:pressed { background:#252b38; }
    QWidget#topBar QToolButton#winClose:hover { background:#d4503f; }
    QWidget#topBar QToolButton#winClose:pressed { background:#b13e30; }

    /* layer toggles: one segmented control */
    QWidget#topBar QWidget#segGroup QToolButton { background:#262b36; color:#aab4c5;
        border:1px solid #363d4b; border-radius:0; padding:4px 11px; }
    QWidget#topBar QWidget#segGroup QToolButton[seg="first"] {
        border-top-left-radius:5px; border-bottom-left-radius:5px; }
    QWidget#topBar QWidget#segGroup QToolButton[seg="mid"] { border-left-width:0; }
    QWidget#topBar QWidget#segGroup QToolButton[seg="last"] { border-left-width:0;
        border-top-right-radius:5px; border-bottom-right-radius:5px; }
    QWidget#topBar QWidget#segGroup QToolButton:hover { background:#303747; color:#f1f4f9; }
    QWidget#topBar QWidget#segGroup QToolButton:checked { background:#2a3d5e; color:#b4d0ff;
        border-color:#3d5a8c; }
    QWidget#topBar QWidget#segGroup QToolButton:disabled { background:#20242d; color:#5f6879;
        border-color:#2b313d; }

    /* ---- graph overlay + panels (soft, layered light) ---------------- */
    QPushButton#graphControl { background:#f5f7fa; color:#39414c; border:1px solid #cdd4df;
        border-radius:4px; padding:3px 10px; font-size:11px; }
    QPushButton#graphControl:hover { background:#eaeef4; border-color:#b6bfcc; }
    QPushButton#graphControl:pressed { background:#dfe5ed; }
    QPushButton#graphControl:disabled { background:#eef1f5; color:#a2aab6; border-color:#dde2ea; }
    QWidget#exportPanel { background:#eef1f6; border:1px solid #cdd4df; border-radius:8px; }
    QWidget#uploadPanel { background:#e9edf3; }
    QLabel#drawerTitle { font-size:13px; font-weight:600; color:#1f2733; }
    QLabel#fileName { font-size:11px; font-weight:600; color:#2c333d; }
    QLabel#exportHint { background:#f6efd9; border:1px solid #e5d6a0; border-radius:4px;
        padding:7px 9px; color:#74561a; font-size:11px; }
    QLabel#scopeLabel { background:#e4e9f1; border:1px solid #d3dae5; border-radius:4px;
        padding:7px 9px; color:#39414c; font-size:11px; }
    QLabel#dropZone { background:#eef1f6; border:1px dashed #b4bfd0; border-radius:8px;
        color:#6f7886; font-size:11px; padding:12px; }
    QLabel#dropZone[dragging="true"] { background:#dde8f8; border:1px dashed #4a7fd6;
        color:#264d9c; }
    QLabel#previewFrame { background:#f1f3f7; border:1px solid #d3dae5; border-radius:8px; }
    QPushButton#drawerAction { background:#f3f5f9; color:#242a33; border:1px solid #c9d1dd;
        border-radius:5px; padding:7px 10px; font-size:11px; text-align:left; }
    QPushButton#drawerAction:hover { background:#e6ebf2; border-color:#b3bdcb; }
    QPushButton#drawerAction:pressed { background:#dce2eb; }
    QPushButton#drawerAction:disabled { background:#eaedf2; color:#a2aab6; border-color:#d9dee7; }
    QWidget#uploadPanel QPushButton#primaryButton { background:#1c222c; color:#f1f4f9;
        border:1px solid #1c222c; border-radius:5px; font-size:11px; font-weight:600;
        padding:8px 10px; }
    QWidget#uploadPanel QPushButton#primaryButton:hover { background:#2d3541; border-color:#2d3541; }
    QWidget#uploadPanel QPushButton#primaryButton:disabled { background:#dde2ea; color:#9aa3b1;
        border-color:#d3dae5; }
    QWidget#expressionPanel { background:#e9edf3; }
    QWidget#expressionHeader { background:#e1e6ee; border-bottom:1px solid #d0d7e2; }
    QLabel#panelTitle { font-size:13px; font-weight:600; color:#1f2733; }
    QLabel#muted { color:#6f7886; font-size:11px; }
    QLineEdit { background:#f3f5f9; border:1px solid #cbd3de; border-radius:5px; padding:6px 9px;
        color:#242a33; font-size:11px; }
    QLineEdit:focus { border-color:#4a7fd6; background:#f7f9fc; }
    QTreeWidget { border:0; background:#e9edf3; outline:0; font-size:11px; }
    QTreeWidget::item { padding:0; margin:0; border:0; }
    QTreeWidget QScrollBar:vertical { background:transparent; width:10px; margin:0; }
    QTreeWidget QScrollBar::handle:vertical { background:#c2cad7; border-radius:5px;
        min-height:28px; margin:2px; }
    QTreeWidget QScrollBar::handle:vertical:hover { background:#a8b2c1; }
    QTreeWidget QScrollBar::add-line:vertical, QTreeWidget QScrollBar::sub-line:vertical { height:0; }
    QTreeWidget QScrollBar::add-page:vertical, QTreeWidget QScrollBar::sub-page:vertical {
        background:transparent; }
    QLabel#emptyNote { color:#7a8392; font-size:12px; padding:18px 16px; background:#e9edf3; }
    QFrame#infoCard { background:#eef1f6; border:1px solid #c9d1dd; border-radius:10px; }
    QLabel#infoTitle { font-size:13px; font-weight:600; color:#1f2733; }
    QLabel#inspector { background:#e4e9f1; border:1px solid #d3dae5; border-radius:6px;
        padding:12px 14px; color:#333b46;
        font-family:'Cascadia Mono', 'JetBrains Mono', Consolas, 'DejaVu Sans Mono', monospace;
        font-size:11px; }

    /* ---- status bar (dark, matches the navbar) ---------------------- */
    QWidget#statusBar { background:#161a21; border-top:1px solid #2b313d; }
    QWidget#statusBar QLabel#muted { color:#9ba6b9; font-size:11px; }
"""

#: Extra rule that gives the navbar combo box a visible chevron on the dark bar.
CHEVRON_RULE = """
    QWidget#topBar QComboBox::down-arrow { image:url("@CHEVRON@"); width:10px; height:10px; }
"""


def _chevron_path() -> str:
    """Write the navbar chevron to a temp PNG and return its posix path ('' on failure)."""
    try:
        target = Path(tempfile.gettempdir()) / "lissara_chevron_down.png"
        pixmap = svg_icon(CHEVRON_SVG, size=20, color=NAV_TEXT_DIM).pixmap(20, 20)
        if pixmap.isNull() or not pixmap.save(str(target), "PNG"):
            return ""
        return target.as_posix()
    except Exception:
        return ""


def build_stylesheet() -> str:
    """Application stylesheet, including the generated combo-box chevron."""
    chevron = _chevron_path()
    extra = CHEVRON_RULE.replace("@CHEVRON@", chevron) if chevron else ""
    return STYLESHEET + extra


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    window = LissaraGraphCalculator()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())


