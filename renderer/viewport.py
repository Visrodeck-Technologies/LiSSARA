"""World/screen coordinate mapping for the Lissara graphing engine.

Conventions
-----------
* **World (mathematical) coordinates** use the usual convention: ``x`` grows to
  the right and ``y`` grows upward.
* **Screen (rendering) coordinates** are pixels with the origin at the top-left
  corner and ``y`` growing downward. With ``invert_y=True`` (the default) the
  vertical axis is flipped so that world ``+y`` appears upward on screen.

The :class:`Viewport` owns the affine mapping between the two spaces and
validates its configuration eagerly so that invalid dimensions or degenerate
world bounds fail loudly instead of producing silently corrupt geometry.

Both :meth:`Viewport.world_to_screen` and :meth:`Viewport.screen_to_world` are
exact inverses (up to floating-point rounding), which the test-suite verifies
with round-trip checks.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

from .svg import format_number

WorldPoint = Tuple[float, float]
ScreenPoint = Tuple[float, float]
Bounds = Tuple[float, float, float, float]  # (xmin, ymin, xmax, ymax)


def _require_finite(name: str, value: float) -> float:
    """Return ``value`` as a float, raising ``ValueError`` if it is not finite."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return result


def validate_bounds(bounds: Bounds) -> Tuple[float, float, float, float]:
    """Validate ``(xmin, ymin, xmax, ymax)`` and return it as floats.

    Raises:
        ValueError: If the sequence is malformed, non-finite, or degenerate
            (``xmin >= xmax`` or ``ymin >= ymax``).
    """
    if bounds is None or len(bounds) != 4:
        raise ValueError("world_bounds must be a 4-tuple (xmin, ymin, xmax, ymax)")
    xmin, ymin, xmax, ymax = (_require_finite("bounds", b) for b in bounds)
    if xmin >= xmax:
        raise ValueError(f"world_bounds requires xmin < xmax, got {xmin} >= {xmax}")
    if ymin >= ymax:
        raise ValueError(f"world_bounds requires ymin < ymax, got {ymin} >= {ymax}")
    return (xmin, ymin, xmax, ymax)


@dataclass(frozen=True)
class Viewport:
    """An affine mapping between world space and a pixel canvas.

    Args:
        width: Canvas width in pixels (must be > 0).
        height: Canvas height in pixels (must be > 0).
        world_bounds: ``(xmin, ymin, xmax, ymax)`` region mapped into the canvas.
        margin: Uniform inner margin in pixels; the drawing area is inset by
            this amount on all four sides. Must satisfy ``2*margin < min(w,h)``.
        preserve_aspect: When ``True`` a single scale factor (the smaller of the
            two axis ratios) is used and the world box is centred in the plot
            area. When ``False`` the horizontal and vertical scales are
            independent so the bounds exactly fill the plot area.
        invert_y: When ``True`` (default) the screen vertical axis is flipped so
            world ``+y`` points up.

    Raises:
        ValueError: If any numeric argument is invalid or the resolved plot area
            is empty.
    """

    width: float
    height: float
    world_bounds: Bounds
    margin: float = 0.0
    preserve_aspect: bool = True
    invert_y: bool = True

    def __post_init__(self) -> None:
        width = _require_finite("width", self.width)
        height = _require_finite("height", self.height)
        margin = _require_finite("margin", self.margin)
        if width <= 0.0:
            raise ValueError(f"width must be > 0, got {width}")
        if height <= 0.0:
            raise ValueError(f"height must be > 0, got {height}")
        if margin < 0.0:
            raise ValueError(f"margin must be >= 0, got {margin}")
        if 2.0 * margin >= min(width, height):
            raise ValueError(
                f"margin {margin} is too large for a {width}x{height} canvas"
            )
        bounds = validate_bounds(self.world_bounds)

        plot_w = width - 2.0 * margin
        plot_h = height - 2.0 * margin
        world_w = bounds[2] - bounds[0]
        world_h = bounds[3] - bounds[1]

        if self.preserve_aspect:
            scale = min(plot_w / world_w, plot_h / world_h)
            scale_x = scale_y = scale
            offset_x = (plot_w - world_w * scale) / 2.0
            offset_y = (plot_h - world_h * scale) / 2.0
        else:
            scale_x = plot_w / world_w
            scale_y = plot_h / world_h
            offset_x = offset_y = 0.0

        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "margin", margin)
        object.__setattr__(self, "world_bounds", bounds)
        object.__setattr__(self, "_scale_x", scale_x)
        object.__setattr__(self, "_scale_y", scale_y)
        object.__setattr__(self, "_offset_x", offset_x)
        object.__setattr__(self, "_offset_y", offset_y)

    # -- derived geometry ---------------------------------------------------
    @property
    def xmin(self) -> float:
        return self.world_bounds[0]

    @property
    def ymin(self) -> float:
        return self.world_bounds[1]

    @property
    def xmax(self) -> float:
        return self.world_bounds[2]

    @property
    def ymax(self) -> float:
        return self.world_bounds[3]

    @property
    def scale_x(self) -> float:
        """Horizontal pixels-per-world-unit factor actually used."""
        return self._scale_x

    @property
    def scale_y(self) -> float:
        """Vertical pixels-per-world-unit factor actually used."""
        return self._scale_y

    # -- transforms ---------------------------------------------------------
    def world_to_screen(self, x: float, y: float) -> ScreenPoint:
        """Map a world point to screen pixels."""
        x = _require_finite("x", x)
        y = _require_finite("y", y)
        px = self.margin + self._offset_x + (x - self.xmin) * self._scale_x
        if self.invert_y:
            py = self.margin + self._offset_y + (self.ymax - y) * self._scale_y
        else:
            py = self.margin + self._offset_y + (y - self.ymin) * self._scale_y
        return (px, py)

    def screen_to_world(self, px: float, py: float) -> WorldPoint:
        """Map a screen pixel back to world coordinates."""
        px = _require_finite("px", px)
        py = _require_finite("py", py)
        x = self.xmin + (px - self.margin - self._offset_x) / self._scale_x
        if self.invert_y:
            y = self.ymax - (py - self.margin - self._offset_y) / self._scale_y
        else:
            y = self.ymin + (py - self.margin - self._offset_y) / self._scale_y
        return (x, y)

    def scale_length(self, world_length: float) -> float:
        """Convert a world-space length to pixels using the smaller scale.

        Useful for sizing markers so they never become larger than the tighter
        axis ratio.
        """
        world_length = _require_finite("world_length", world_length)
        return world_length * min(self._scale_x, self._scale_y)

    def to_svg_viewbox(self) -> str:
        """Return the SVG ``viewBox`` value for this canvas."""
        return f"0 0 {format_number(self.width)} {format_number(self.height)}"


def fit_bounds(
    points,
    padding: float = 0.05,
) -> Tuple[float, float, float, float]:
    """Compute world bounds enclosing ``points`` with fractional padding.

    Args:
        points: Iterable of ``(x, y)`` world points (at least one).
        padding: Fraction of the larger span added on every side (0.05 = 5%).

    Returns:
        ``(xmin, ymin, xmax, ymax)`` guaranteed non-degenerate.

    Raises:
        ValueError: If ``points`` is empty or contains only non-finite values.
    """
    xs = []
    ys = []
    for px, py in points:
        if math.isfinite(px) and math.isfinite(py):
            xs.append(float(px))
            ys.append(float(py))
    if not xs:
        raise ValueError("fit_bounds requires at least one finite point")
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    span = max(xmax - xmin, ymax - ymin, 1e-9)
    pad = span * max(0.0, float(padding))
    # Guarantee a strictly positive extent even for a single point or a line.
    if xmax - xmin <= 0.0:
        xmin -= 0.5 * span
        xmax += 0.5 * span
    if ymax - ymin <= 0.0:
        ymin -= 0.5 * span
        ymax += 0.5 * span
    return (xmin - pad, ymin - pad, xmax + pad, ymax + pad)
