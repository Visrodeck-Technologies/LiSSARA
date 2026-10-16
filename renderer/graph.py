"""Two-dimensional mathematical graph rendering.

:class:`GraphRenderer` draws mathematical curves in a world coordinate system,
optionally with grid lines, axes, ticks and labels. It reuses
:mod:`renderer.sampling` for evaluation and :class:`renderer.viewport.Viewport`
for world/screen mapping, so the three concerns (evaluate / map / draw) stay
separable.

Chain of responsibilities:

* ``lissara_equations`` evaluates the curves.
* :mod:`renderer.sampling` decides *where* to evaluate them.
* :class:`renderer.viewport.Viewport` maps world -> screen.
* :class:`GraphRenderer` decides *what markup* to emit.

World bounds are inferred from the added curves (with configurable padding)
unless the caller supplies explicit bounds.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .sampling import (
    sample_curve,
    sample_cubic_segments,
    sample_polyline,
)
from .svg import SvgCanvas, format_number, path_data
from .viewport import Bounds, Viewport, fit_bounds

Point = Tuple[float, float]
CubicCurve = dict


@dataclass
class GraphConfig:
    """Configuration for :class:`GraphRenderer`.

    Attributes:
        width, height: Output canvas size in pixels.
        margin: Inner margin (pixels) reserved for axes/labels.
        world_bounds: Explicit ``(xmin, ymin, xmax, ymax)``; inferred from data
            when ``None``.
        preserve_aspect: Keep equal world-unit scaling on both axes.
        invert_y: Flip the screen vertical axis (world +y up).
        padding: Fractional padding applied to inferred bounds.
        background: Canvas background color.
        show_grid, show_axes, show_ticks, show_labels: Toggle decorations.
        tick_target: Approximate number of ticks per axis when auto-spacing.
        grid_spacing: Explicit ``(dx, dy)`` tick spacing; overrides auto-spacing.
        axis_color, grid_color, label_color: Decoration colors.
        font_family, font_size: Label typography.
        stroke, stroke_width: Default curve style.
        x_label, y_label: Axis captions.
    """

    width: float = 640.0
    height: float = 480.0
    margin: float = 48.0
    world_bounds: Optional[Bounds] = None
    preserve_aspect: bool = True
    invert_y: bool = True
    padding: float = 0.05
    background: str = "#ffffff"
    show_grid: bool = True
    show_axes: bool = True
    show_ticks: bool = True
    show_labels: bool = True
    tick_target: int = 8
    grid_spacing: Optional[Tuple[float, float]] = None
    axis_color: str = "#666666"
    grid_color: str = "#e6e6e6"
    label_color: str = "#333333"
    font_family: str = "monospace"
    font_size: float = 11.0
    stroke: str = "#1f4fd8"
    stroke_width: float = 1.75
    x_label: str = "x"
    y_label: str = "y"


@dataclass
class _Curve:
    points: List[Point]
    color: str
    width: float
    closed: bool
    marker_radius: Optional[float] = None


def nice_step(span: float, target: int) -> float:
    """Return a "nice" tick step (1/2/5 * 10^k) approximating ``span/target``."""
    if span <= 0.0 or target < 1:
        return 1.0
    raw = span / target
    magnitude = 10.0 ** math.floor(math.log10(raw))
    normalized = raw / magnitude
    if normalized <= 1.0:
        multiple = 1.0
    elif normalized <= 2.0:
        multiple = 2.0
    elif normalized <= 5.0:
        multiple = 5.0
    else:
        multiple = 10.0
    return multiple * magnitude


def tick_values(lo: float, hi: float, step: float) -> List[float]:
    """Return tick positions in ``[lo, hi]`` separated by ``step``.

    Raises:
        ValueError: If ``step`` is not a positive finite number.
    """
    if not math.isfinite(step) or step <= 0.0:
        raise ValueError("step must be a positive finite number")
    if hi < lo:
        lo, hi = hi, lo
    start = math.ceil(lo / step - 1e-9) * step
    values: List[float] = []
    value = start
    guard = 0
    while value <= hi + 1e-9 and guard < 100000:
        # Snap values that are within rounding noise of zero.
        snapped = 0.0 if abs(value) < step * 1e-9 else value
        values.append(snapped)
        value += step
        guard += 1
    return values


def _tick_decimals(step: float) -> int:
    if step <= 0.0 or not math.isfinite(step):
        return 2
    return max(0, -int(math.floor(math.log10(step))))


class GraphRenderer:
    """Accumulate curves and render them to SVG (optionally PNG)."""

    def __init__(self, config: Optional[GraphConfig] = None):
        self.config = config or GraphConfig()
        self._curves: List[_Curve] = []

    # -- curve input --------------------------------------------------------
    def add_polyline(
        self,
        points: Sequence[Point],
        color: Optional[str] = None,
        width: Optional[float] = None,
        closed: bool = False,
    ) -> None:
        """Add an already-sampled polyline."""
        self._curves.append(
            _Curve(
                points=sample_polyline(points, closed=False),
                color=color or self.config.stroke,
                width=self.config.stroke_width if width is None else float(width),
                closed=closed,
            )
        )

    def add_curve(
        self,
        curve: dict,
        n: int = 64,
        adaptive: bool = True,
        tolerance: float = 0.25,
        interval: Tuple[float, float] = (0.0, 1.0),
        color: Optional[str] = None,
        width: Optional[float] = None,
        closed: bool = False,
    ) -> None:
        """Add a single quadratic/cubic Bézier, sampled for rendering."""
        points = sample_curve(
            curve,
            n=n,
            adaptive=adaptive,
            tolerance=tolerance,
            t_start=interval[0],
            t_end=interval[1],
        )
        self._curves.append(
            _Curve(
                points=points,
                color=color or self.config.stroke,
                width=self.config.stroke_width if width is None else float(width),
                closed=closed,
            )
        )

    def add_cubic(
        self,
        curve: CubicCurve,
        n: int = 64,
        adaptive: bool = True,
        tolerance: float = 0.25,
        interval: Tuple[float, float] = (0.0, 1.0),
        **style,
    ) -> None:
        """Add a single cubic Bézier (convenience wrapper over :meth:`add_curve`)."""
        self.add_curve(curve, n=n, adaptive=adaptive, tolerance=tolerance,
                       interval=interval, **style)

    def add_cubic_segments(
        self,
        segments: Sequence[CubicCurve],
        n: int = 16,
        adaptive: bool = True,
        tolerance: float = 0.25,
        color: Optional[str] = None,
        width: Optional[float] = None,
        closed: bool = False,
    ) -> None:
        """Add a chain of cubic segments as one continuous polyline."""
        points = sample_cubic_segments(segments, n=n, adaptive=adaptive, tolerance=tolerance)
        self._curves.append(
            _Curve(
                points=points,
                color=color or self.config.stroke,
                width=self.config.stroke_width if width is None else float(width),
                closed=closed,
            )
        )

    def add_point(self, point: Point, radius_world: float = 0.04,
                  color: Optional[str] = None) -> None:
        """Add a small circular marker at a world point.

        Args:
            point: World ``(x, y)``.
            radius_world: Marker radius in world units (scaled to pixels).
            color: Marker fill color (defaults to the curve stroke color).
        """
        x, y = float(point[0]), float(point[1])
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError("marker point must be finite")
        self._curves.append(
            _Curve(
                points=[(x, y)],
                color=color or self.config.stroke,
                width=0.0,
                closed=False,
                marker_radius=float(radius_world),
            )
        )

    def clear(self) -> None:
        """Remove all added curves."""
        self._curves.clear()

    # -- bounds and viewport ------------------------------------------------
    def data_bounds(self) -> Optional[Bounds]:
        """World bounds enclosing every added curve, or ``None`` if empty."""
        points: List[Point] = []
        for curve in self._curves:
            points.extend(curve.points)
        if not points:
            return None
        return fit_bounds(points, self.config.padding)

    def _resolve_bounds(self) -> Bounds:
        if self.config.world_bounds is not None:
            return tuple(self.config.world_bounds)  # type: ignore[return-value]
        inferred = self.data_bounds()
        if inferred is not None:
            return inferred
        return (-5.0, -5.0, 5.0, 5.0)

    def viewport(self) -> Viewport:
        """Build the :class:`Viewport` for the current configuration and data."""
        return Viewport(
            width=self.config.width,
            height=self.config.height,
            world_bounds=self._resolve_bounds(),
            margin=self.config.margin,
            preserve_aspect=self.config.preserve_aspect,
            invert_y=self.config.invert_y,
        )

    # -- decorations --------------------------------------------------------
    def _axis_spacings(self, bounds: Bounds) -> Tuple[float, float]:
        if self.config.grid_spacing is not None:
            dx, dy = self.config.grid_spacing
            return float(dx), float(dy)
        return (
            nice_step(bounds[2] - bounds[0], self.config.tick_target),
            nice_step(bounds[3] - bounds[1], self.config.tick_target),
        )

    def render_svg(self) -> str:
        """Render the graph to an SVG document string."""
        cfg = self.config
        viewport = self.viewport()
        bounds = viewport.world_bounds
        canvas = SvgCanvas(cfg.width, cfg.height, view_box=viewport.to_svg_viewbox())

        dx, dy = self._axis_spacings(bounds)
        x_ticks = tick_values(bounds[0], bounds[2], dx)
        y_ticks = tick_values(bounds[1], bounds[3], dy)

        # Axes placed at world 0, clamped to the visible region.
        axis_y_world = min(max(0.0, bounds[1]), bounds[3])
        axis_x_world = min(max(0.0, bounds[0]), bounds[2])

        if cfg.show_grid:
            self._draw_grid(canvas, viewport, x_ticks, y_ticks)
        if cfg.show_axes:
            self._draw_axes(canvas, viewport, axis_x_world, axis_y_world)
        if cfg.show_ticks or cfg.show_labels:
            self._draw_ticks_and_labels(
                canvas, viewport, x_ticks, y_ticks, axis_x_world, axis_y_world, dx, dy
            )
        self._draw_curves(canvas, viewport)

        return canvas.render(background=cfg.background)

    def _draw_grid(self, canvas, viewport, x_ticks, y_ticks) -> None:
        cfg = self.config
        for xt in x_ticks:
            x_px, _ = viewport.world_to_screen(xt, viewport.ymin)
            top = viewport.margin
            bottom = cfg.height - viewport.margin
            canvas.line(x_px, top, x_px, bottom, stroke=cfg.grid_color, stroke_width=1)
        for yt in y_ticks:
            _, y_px = viewport.world_to_screen(viewport.xmin, yt)
            left = viewport.margin
            right = cfg.width - viewport.margin
            canvas.line(left, y_px, right, y_px, stroke=cfg.grid_color, stroke_width=1)

    def _draw_axes(self, canvas, viewport, axis_x_world, axis_y_world) -> None:
        cfg = self.config
        # X axis (horizontal line at axis_y_world).
        x0, y0 = viewport.world_to_screen(viewport.xmin, axis_y_world)
        x1, y1 = viewport.world_to_screen(viewport.xmax, axis_y_world)
        canvas.line(x0, y0, x1, y1, stroke=cfg.axis_color, stroke_width=1.2)
        # Y axis (vertical line at axis_x_world).
        x2, y2 = viewport.world_to_screen(axis_x_world, viewport.ymin)
        x3, y3 = viewport.world_to_screen(axis_x_world, viewport.ymax)
        canvas.line(x2, y2, x3, y3, stroke=cfg.axis_color, stroke_width=1.2)

    def _draw_ticks_and_labels(
        self, canvas, viewport, x_ticks, y_ticks, axis_x_world, axis_y_world, dx, dy
    ) -> None:
        cfg = self.config
        tick_len = 4.0
        x_decimals = _tick_decimals(dx)
        y_decimals = _tick_decimals(dy)

        for xt in x_ticks:
            x_px, y_px = viewport.world_to_screen(xt, axis_y_world)
            if cfg.show_ticks:
                canvas.line(x_px, y_px - tick_len, x_px, y_px + tick_len,
                            stroke=cfg.axis_color, stroke_width=1.2)
            if cfg.show_labels:
                canvas.text(
                    x_px, y_px + tick_len + cfg.font_size, f"{xt:.{x_decimals}f}",
                    fill=cfg.label_color, font_family=cfg.font_family,
                    font_size=format_number(cfg.font_size), text_anchor="middle",
                )

        for yt in y_ticks:
            x_px, y_px = viewport.world_to_screen(axis_x_world, yt)
            if cfg.show_ticks:
                canvas.line(x_px - tick_len, y_px, x_px + tick_len, y_px,
                            stroke=cfg.axis_color, stroke_width=1.2)
            if cfg.show_labels:
                canvas.text(
                    x_px - tick_len - 2.0, y_px + cfg.font_size * 0.35,
                    f"{yt:.{y_decimals}f}",
                    fill=cfg.label_color, font_family=cfg.font_family,
                    font_size=format_number(cfg.font_size), text_anchor="end",
                )

        if cfg.show_labels:
            # Axis captions near the far ends of each axis.
            ex, ey = viewport.world_to_screen(viewport.xmax, axis_y_world)
            canvas.text(ex, ey - cfg.font_size * 0.6, cfg.x_label,
                        fill=cfg.label_color, font_family=cfg.font_family,
                        font_size=format_number(cfg.font_size + 1), text_anchor="end")
            tx, ty = viewport.world_to_screen(axis_x_world, viewport.ymax)
            canvas.text(tx + cfg.font_size * 0.6, ty, cfg.y_label,
                        fill=cfg.label_color, font_family=cfg.font_family,
                        font_size=format_number(cfg.font_size + 1), text_anchor="start")

    def _draw_curves(self, canvas, viewport) -> None:
        for curve in self._curves:
            if curve.marker_radius is not None:
                px, py = viewport.world_to_screen(*curve.points[0])
                r_px = max(1.0, viewport.scale_length(curve.marker_radius))
                canvas.circle(px, py, r_px, fill=curve.color, stroke="none")
                continue
            screen = [viewport.world_to_screen(x, y) for (x, y) in curve.points]
            d = path_data(screen, closed=curve.closed)
            canvas.path(
                d,
                fill="none",
                stroke=curve.color,
                stroke_width=format_number(curve.width),
                stroke_linecap="round",
                stroke_linejoin="round",
            )

    def render_png(self, path: Optional[str] = None, scale: float = 1.0):
        """Rasterize the rendered SVG to a PNG preview (requires CairoSVG).

        See :func:`renderer.raster.svg_to_png`. Raises
        :class:`renderer.raster.RasterBackendUnavailable` when the native Cairo
        library is not installed.
        """
        from .raster import svg_to_png

        return svg_to_png(self.render_svg(), path=path, scale=scale)
