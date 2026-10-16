"""Lissara Renderer — mathematical graphing engine.

This package exposes a cohesive public API for visualising mathematical curves
and the existing Lissara ``MathScene`` representation. It delegates all curve
evaluation to :mod:`lissara_equations` and keeps SVG output dependency-free.

Public API
----------
* :class:`renderer.viewport.Viewport`, :func:`renderer.viewport.fit_bounds`
  — world/screen mapping.
* :mod:`renderer.sampling` — uniform and adaptive curve sampling.
* :mod:`renderer.graph.GraphConfig`, :class:`renderer.graph.GraphRenderer`
  — two-dimensional graph plotting (axes, grid, ticks, labels).
* :mod:`renderer.scene` — adapter for ``lissara_engine``/``core.lissara_core``
  ``MathScene`` objects.
* :class:`renderer.raster.RasterBackendUnavailable`, :func:`renderer.raster.svg_to_png`,
  :func:`renderer.raster.has_raster_backend` — optional PNG preview (requires
  CairoSVG/native cairo).

Examples
--------
Plot a simple cubic:

>>> from lissara_equations import make_cubic
>>> from renderer import GraphConfig, GraphRenderer
>>> curve = make_cubic((0,0),(0,10),(10,10),(10,0))
>>> g = GraphRenderer(GraphConfig(width=400, height=400))
>>> g.add_cubic(curve, adaptive=True, tolerance=0.25)
>>> svg = g.render_svg()  # dependency-free SVG

Render an existing MathScene:

>>> from renderer import render_scene_svg
>>> svg = render_scene_svg(scene)  # reads the scene's Bézier segments
"""
from __future__ import annotations

from .graph import GraphConfig, GraphRenderer
from .raster import RasterBackendUnavailable, has_raster_backend, svg_to_png
from .scene import SceneRenderConfig, render_scene_svg, scene_to_graph
from .viewport import Viewport, fit_bounds

__all__ = [
    "GraphConfig",
    "GraphRenderer",
    "Viewport",
    "fit_bounds",
    "scene_to_graph",
    "render_scene_svg",
    "SceneRenderConfig",
    "RasterBackendUnavailable",
    "has_raster_backend",
    "svg_to_png",
]
