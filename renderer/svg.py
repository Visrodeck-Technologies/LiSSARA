"""Minimal, dependency-free SVG serialization helpers.

The graphing engine emits SVG strings directly. This module centralises number
formatting, attribute escaping and path-data construction so every element is
valid XML (attributes are quoted/escaped with :func:`xml.sax.saxutils.quoteattr`
and text content is escaped).

Nothing here knows about curves or viewports — it only builds markup, keeping
the mathematical evaluation, coordinate mapping and rendering concerns separate.
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape, quoteattr

Point = Tuple[float, float]

_DEFAULT_PRESENTATION = (
    "fill",
    "fill-opacity",
    "stroke",
    "stroke-opacity",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "opacity",
)


def format_number(value: float) -> str:
    """Format a finite number compactly for SVG (integers without decimals).

    Raises:
        ValueError: If ``value`` is not finite.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"cannot format non-numeric value {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"cannot format non-finite value {value!r}")
    if number == int(number) and abs(number) < 1e15:
        return str(int(number))
    text = f"{number:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def attributes(values: Dict[str, object]) -> str:
    """Serialize a mapping into `` key="value"`` attribute text.

    ``None`` values are skipped. Keys with underscores are emitted with hyphens
    (``stroke_width`` -> ``stroke-width``) to match SVG presentation attributes.
    Values are quoted and escaped.
    """
    parts: List[str] = []
    for key, value in values.items():
        if value is None:
            continue
        name = key.replace("_", "-")
        parts.append(f" {name}={quoteattr(str(value))}")
    return "".join(parts)


def path_data(points_or_segments, closed: bool = False) -> str:
    """Build SVG path data from points, cubic segments, or command tuples.

    Accepts:
        * a sequence of ``(x, y)`` points -> ``M ... L ...`` polyline;
        * a sequence of canonical cubic segment dicts (each with
          ``control_points``) -> ``M ... C ...`` cubic path;
        * a sequence of ``("M"|"L"|"C", *coords)`` command tuples.

    Returns an empty string when there is nothing to draw.
    """
    seq = list(points_or_segments)
    if not seq:
        return ""

    if isinstance(seq[0], dict) and "control_points" in seq[0]:
        return _cubic_path_data(seq, closed)
    if isinstance(seq[0], (tuple, list)) and seq[0] and isinstance(seq[0][0], str):
        return _command_path_data(seq, closed)
    return _polyline_path_data(seq, closed)


def _polyline_path_data(points: Sequence[Point], closed: bool) -> str:
    parts: List[str] = []
    for index, point in enumerate(points):
        x, y = format_number(point[0]), format_number(point[1])
        parts.append(("M " if index == 0 else "L ") + f"{x} {y}")
    if closed and len(points) > 1 and tuple(points[0]) != tuple(points[-1]):
        parts.append("Z")
    return " ".join(parts)


def _cubic_path_data(segments: Sequence[dict], closed: bool) -> str:
    parts: List[str] = []
    for index, seg in enumerate(segments):
        cps = seg["control_points"]
        if index == 0:
            x0, y0 = cps[0]
            parts.append(f"M {format_number(x0)} {format_number(y0)}")
        triple = " ".join(
            f"{format_number(point[0])} {format_number(point[1])}"
            for point in cps[1:4]
        )
        parts.append(f"C {triple}")
    if closed:
        parts.append("Z")
    return " ".join(parts)


def _command_path_data(commands: Iterable, closed: bool) -> str:
    parts: List[str] = []
    for command in commands:
        letter = str(command[0])
        coords = command[1:]
        numbers = " ".join(format_number(float(c)) for c in coords)
        parts.append(f"{letter} {numbers}".strip())
    if closed:
        parts.append("Z")
    return " ".join(parts)


class SvgCanvas:
    """An ordered SVG element accumulator.

    Elements are stored in insertion order and rendered deterministically, which
    makes the output stable for testing and diffing.
    """

    def __init__(self, width: float, height: float, view_box: Optional[str] = None):
        self.width = float(width)
        self.height = float(height)
        self.view_box = view_box or f"0 0 {format_number(width)} {format_number(height)}"
        self._elements: List[str] = []

    # -- primitives ---------------------------------------------------------
    def add_raw(self, markup: str) -> None:
        """Append raw, already-escaped markup."""
        self._elements.append(markup)

    def path(self, d: str, **presentation) -> None:
        """Append a ``<path>`` element. Empty ``d`` is ignored."""
        if not d:
            return
        attrs = {"d": d}
        attrs.update(presentation)
        self._elements.append(f"<path{attributes(attrs)} />")

    def line(self, x1, y1, x2, y2, **presentation) -> None:
        attrs = {
            "x1": format_number(x1),
            "y1": format_number(y1),
            "x2": format_number(x2),
            "y2": format_number(y2),
        }
        attrs.update(presentation)
        self._elements.append(f"<line{attributes(attrs)} />")

    def rect(self, x, y, w, h, **presentation) -> None:
        attrs = {
            "x": format_number(x),
            "y": format_number(y),
            "width": format_number(w),
            "height": format_number(h),
        }
        attrs.update(presentation)
        self._elements.append(f"<rect{attributes(attrs)} />")

    def circle(self, cx, cy, r, **presentation) -> None:
        attrs = {
            "cx": format_number(cx),
            "cy": format_number(cy),
            "r": format_number(r),
        }
        attrs.update(presentation)
        self._elements.append(f"<circle{attributes(attrs)} />")

    def text(self, x, y, content, **presentation) -> None:
        attrs = {"x": format_number(x), "y": format_number(y)}
        attrs.update(presentation)
        self._elements.append(f"<text{attributes(attrs)}>{escape(str(content))}</text>")

    # -- output -------------------------------------------------------------
    def render(self, background: Optional[str] = None) -> str:
        """Serialize the canvas to an SVG document string.

        Args:
            background: Optional CSS color painted as a full-canvas rectangle
                beneath every element.
        """
        body: List[str] = []
        if background is not None:
            body.append(
                f'<rect x="0" y="0" width="{format_number(self.width)}" '
                f'height="{format_number(self.height)}" fill={quoteattr(str(background))} />'
            )
        body.extend(self._elements)
        header = (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{format_number(self.width)}" height="{format_number(self.height)}" '
            f'viewBox={quoteattr(self.view_box)}>'
        )
        return header + "".join(body) + "</svg>"

    def __len__(self) -> int:
        return len(self._elements)
