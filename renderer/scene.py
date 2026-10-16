"""Render Lissara ``MathScene`` objects with exact between-curve geometry.

Why this is separate from :class:`renderer.graph.GraphRenderer`
----------------------------------------------------------------
Graph rendering samples curves into polylines because it plots arbitrary data.
Scene rendering must instead reproduce the *reconstruction* faithfully:

* It emits the cubic Bézier control points directly as SVG ``C`` commands, so
  the exported geometry is **exact** — never the control polygon and never a
  resampled approximation.
* It does not resample or rebuild geometry, so a scene with thousands of
  segments renders in one linear pass.
* Path boundaries and open/closed state are preserved per path.

The module reads ``lissara_engine.MathScene``/``PathRecord`` and the legacy
``core.lissara_core.scene`` equivalents (or plain dicts) through a small,
well-defined attribute interface. It never mutates the scene.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union

from .graph import GraphConfig, GraphRenderer
from .sampling import sample_cubic_segments, sample_polyline
from .svg import SvgCanvas, path_data

Point = Tuple[float, float]
PathLike = Union[object, dict]


@dataclass
class SceneRenderConfig:
    """Options for :func:`render_scene_svg`.

    Attributes:
        background: Canvas background color (``None`` for transparent).
        mode: ``"scene"`` honours each path's fill/stroke; ``"lineart"`` forces a
            white background with dark strokes and no fill (a clean line-art
            preview).
        lineart_color: Stroke color used in ``"lineart"`` mode.
        lineart_width: Stroke width used in ``"lineart"`` mode.
        default_stroke: Fallback stroke color when a path has none.
        default_stroke_width: Fallback stroke width.
        default_fill: Fallback fill color for closed paths without one.
        respect_visibility: Skip paths explicitly marked ``visible=False``.
    """

    background: Optional[str] = "#ffffff"
    mode: str = "scene"
    lineart_color: str = "#111111"
    lineart_width: float = 1.0
    default_stroke: str = "none"
    default_stroke_width: float = 1.0
    default_fill: str = "none"
    respect_visibility: bool = True

    def __post_init__(self) -> None:
        if self.mode not in ("scene", "lineart"):
            raise ValueError("mode must be 'scene' or 'lineart'")


def _attr(scene: PathLike, name: str, default=None):
    if hasattr(scene, name):
        return getattr(scene, name)
    if isinstance(scene, dict) and name in scene:
        return scene[name]
    return default


def _iter_scene_paths(scene: PathLike) -> List[PathLike]:
    paths = _attr(scene, "paths", [])
    if paths is None:
        return []
    return list(paths)


def _segments(path: PathLike) -> List:
    segs = _attr(path, "segments", [])
    return list(segs) if segs else []


def _is_closed(path: PathLike) -> bool:
    return bool(_attr(path, "closed", False))


def _has_cubic_records(segments: Sequence) -> bool:
    """True when segments are canonical cubic records (drawable as ``C``)."""
    return bool(segments) and isinstance(segments[0], dict) and "control_points" in segments[0]


def _resolve_style(path: PathLike, closed: bool, cfg: SceneRenderConfig):
    """Return presentation attributes for one path."""
    if cfg.mode == "lineart":
        return {
            "fill": "none",
            "stroke": cfg.lineart_color,
            "stroke_width": cfg.lineart_width,
            "stroke_opacity": 1.0,
        }

    fill = _attr(path, "fill", None) or {}
    stroke = _attr(path, "stroke", None) or {}
    fill_color = fill.get("color", cfg.default_fill) if isinstance(fill, dict) else (fill or cfg.default_fill)
    stroke_color = stroke.get("color", cfg.default_stroke) if isinstance(stroke, dict) else (stroke or cfg.default_stroke)
    stroke_width = stroke.get("width", cfg.default_stroke_width) if isinstance(stroke, dict) else cfg.default_stroke_width
    fill_opacity = fill.get("opacity", 1.0) if isinstance(fill, dict) else 1.0
    stroke_opacity = stroke.get("opacity", 1.0) if isinstance(stroke, dict) else 1.0

    # Open paths never receive a fill.
    if not closed:
        fill_color = "none"

    attrs = {
        "fill": fill_color or "none",
        "fill_opacity": fill_opacity if (closed and fill_color and fill_color != "none") else None,
        "stroke": stroke_color or "none",
        "stroke_width": stroke_width,
        "stroke_opacity": stroke_opacity if (stroke_color and stroke_color != "none") else None,
        "stroke_linecap": "round",
        "stroke_linejoin": "round",
    }
    return attrs


def render_scene_svg(
    scene: PathLike,
    output_path: Optional[str] = None,
    config: Optional[SceneRenderConfig] = None,
) -> str:
    """Render a MathScene to an exact SVG string (optionally write to file).

    Args:
        scene: ``lissara_engine.MathScene``, legacy scene, or dict with
            ``width``/``height``/``paths``.
        output_path: Optional path to write the SVG to (UTF-8).
        config: Rendering options.

    Returns:
        The SVG document string.

    Raises:
        ValueError: If ``scene`` has no positive width/height.
    """
    cfg = config or SceneRenderConfig()
    width = _attr(scene, "width", None)
    height = _attr(scene, "height", None)
    if not width or not height:
        raise ValueError("scene must define positive width and height")

    canvas = SvgCanvas(float(width), float(height))
    for path in _iter_scene_paths(scene):
        if cfg.respect_visibility and _attr(path, "visible", True) is False:
            continue
        segments = _segments(path)
        if not segments:
            continue
        closed = _is_closed(path)
        d = path_data(segments, closed=closed)
        if not d:
            continue
        style = _resolve_style(path, closed, cfg)
        canvas.path(d, **style)

    svg = canvas.render(background=cfg.background)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(svg)
    return svg


def scene_to_graph(
    scene: PathLike,
    config: Optional[GraphConfig] = None,
    adaptive: bool = True,
    tolerance: float = 0.5,
) -> GraphRenderer:
    """Build a :class:`GraphRenderer` that plots the scene's curves.

    Unlike :func:`render_scene_svg`, this samples the cubic segments so the
    geometry can be combined with graph decorations (axes/grid) or inspected as
    data points. The scene is not mutated.

    Args:
        scene: MathScene or dict.
        config: Optional graph configuration. Defaults to the scene's own
            pixel-space coordinate system (no axes, y increasing downward).
        adaptive: Use adaptive sampling.
        tolerance: Adaptive midpoint tolerance in world (pixel) units.

    Returns:
        A populated :class:`GraphRenderer`.

    Raises:
        ValueError: If the scene has no drawable geometry and no explicit bounds
            were supplied.
    """
    width = _attr(scene, "width", None)
    height = _attr(scene, "height", None)

    if config is None:
        config = GraphConfig(
            width=float(width or 800),
            height=float(height or 600),
            margin=0.0,
            world_bounds=(0.0, 0.0, float(width or 800), float(height or 600)),
            preserve_aspect=True,
            invert_y=False,
            show_axes=False,
            show_grid=False,
            show_ticks=False,
            show_labels=False,
        )

    renderer = GraphRenderer(config)
    for path in _iter_scene_paths(scene):
        segments = _segments(path)
        if not segments:
            continue
        closed = _is_closed(path)
        stroke = _attr(path, "stroke", None) or {}
        color = stroke.get("color") if isinstance(stroke, dict) else None
        width_attr = stroke.get("width") if isinstance(stroke, dict) else None
        if _has_cubic_records(segments):
            points = sample_cubic_segments(segments, adaptive=adaptive, tolerance=tolerance)
        else:
            # Non-cubic records: treat as an already-sampled polyline.
            points = sample_polyline(segments, closed=False)
        renderer.add_polyline(points, color=color, width=width_attr, closed=closed)

    if not renderer._curves and config.world_bounds is None:
        raise ValueError("scene contains no drawable geometry")

    return renderer
