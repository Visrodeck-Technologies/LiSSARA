# Lissara Renderer — API Reference

All public names are importable from the top-level `renderer` package. Run
examples from the repository root (the packages are found on the current
directory).

## Public API

| Name | Kind | Purpose |
|---|---|---|
| `Viewport` | class | World ⇄ screen affine mapping with validation |
| `fit_bounds` | function | Enclosing world bounds for a point set (with padding) |
| `GraphConfig` | dataclass | Graph layout/style configuration |
| `GraphRenderer` | class | Plot curves with axes/grid/ticks/labels to SVG |
| `SceneRenderConfig` | dataclass | Scene render options (`scene` / `lineart` modes) |
| `scene_to_graph` | function | Build a `GraphRenderer` from a `MathScene` |
| `render_scene_svg` | function | Render a `MathScene` to exact SVG |
| `svg_to_png` | function | Optional PNG preview (CairoSVG backend) |
| `has_raster_backend` | function | Whether the PNG backend is available |
| `RasterBackendUnavailable` | exception | Raised when PNG is requested but unavailable |

Submodules: `renderer.sampling`, `renderer.viewport`, `renderer.svg`,
`renderer.graph`, `renderer.scene`, `renderer.raster`.

---

## `Viewport`

```python
Viewport(width, height, world_bounds, margin=0.0,
         preserve_aspect=True, invert_y=True)
```

* `world_bounds` — `(xmin, ymin, xmax, ymax)`, strictly non-degenerate.
* `margin` — pixels inset on all sides; `2*margin` must be `< min(width, height)`.
* `preserve_aspect` — one scale factor (`min` of both ratios) and centring when
  `True`; independent axis scales when `False`.
* `invert_y` — flip the screen vertical axis (world `+y` up).

**Methods / properties:** `world_to_screen(x, y)`, `screen_to_world(px, py)`,
`scale_length(length)`, `to_svg_viewbox()`, `scale_x`, `scale_y`, `xmin`,
`ymin`, `xmax`, `ymax`.

**Raises:** `ValueError` for non-positive dimensions, a too-large margin,
non-finite values, or degenerate bounds.

```python
>>> from renderer import Viewport
>>> vp = Viewport(400, 400, (-10, -10, 10, 10), margin=20)
>>> vp.world_to_screen(0, 0)
(200.0, 200.0)
>>> vp.screen_to_world(200.0, 200.0)
(0.0, 0.0)
>>> vp.world_to_screen(-10, 10)[1] < vp.world_to_screen(-10, -10)[1]
True
```

## `fit_bounds`

```python
fit_bounds(points, padding=0.05) -> (xmin, ymin, xmax, ymax)
```

Encloses finite points with fractional padding. Degenerate inputs (a single
point, a vertical/horizontal line) are expanded to a strictly positive extent.
Raises `ValueError` if no finite point is supplied.

```python
>>> from renderer import fit_bounds
>>> fit_bounds([(0, 0), (4, 2)], padding=0.0)
(0.0, 0.0, 4.0, 2.0)
```

## Sampling (`renderer.sampling`)

| Function | Description |
|---|---|
| `sample_cubic(curve, n=32, t_start=0.0, t_end=1.0)` | Uniform cubic sampling (`n+1` points) |
| `sample_quadratic(curve, n=32, t_start=0.0, t_end=1.0)` | Uniform quadratic sampling |
| `sample_segment(segment, n=1, t_start=0.0, t_end=1.0)` | Uniform segment sampling |
| `sample_cubic_adaptive(curve, tolerance=0.25, max_depth=16, t_start=0.0, t_end=1.0)` | Adaptive cubic sampling |
| `sample_quadratic_adaptive(curve, tolerance=0.25, max_depth=16, t_start=0.0, t_end=1.0)` | Adaptive quadratic sampling |
| `sample_curve(curve, n=32, adaptive=False, tolerance=0.25, max_depth=16, t_start=0.0, t_end=1.0)` | Degree-dispatching sampler |
| `sample_cubic_segments(segments, n=16, adaptive=False, tolerance=0.25)` | Sample a segment chain into one polyline |
| `sample_polyline(points, closed=False)` | Validate (and optionally close) a polyline |

Interval endpoints are preserved exactly. Invalid intervals, `n < 1`, negative
tolerance, and non-finite results raise `ValueError`.

```python
>>> from lissara_equations import make_cubic
>>> from renderer.sampling import sample_cubic, sample_cubic_adaptive
>>> c = make_cubic((0, 0), (0, 10), (10, 10), (10, 0))
>>> sample_cubic(c, n=4)[0], sample_cubic(c, n=4)[-1]
((0.0, 0.0), (10.0, 0.0))
>>> pts = sample_cubic_adaptive(c, tolerance=0.1)
>>> pts[0], pts[-1]
((0.0, 0.0), (10.0, 0.0))
```

## `GraphConfig`

A dataclass; all fields optional. Highlights: `width`, `height`, `margin`,
`world_bounds`, `preserve_aspect`, `invert_y`, `padding`, `background`,
`show_grid`/`show_axes`/`show_ticks`/`show_labels`, `tick_target`, `grid_spacing`,
`axis_color`, `grid_color`, `label_color`, `font_family`, `font_size`,
`stroke`, `stroke_width`, `x_label`, `y_label`.

## `GraphRenderer`

```python
GraphRenderer(config=None)
```

Methods: `add_polyline(points, color=None, width=None, closed=False)`,
`add_curve(curve, n=64, adaptive=True, tolerance=0.25, interval=(0.0, 1.0),
color=None, width=None, closed=False)`, `add_cubic(...)`,
`add_cubic_segments(segments, n=16, adaptive=True, tolerance=0.25, color=None,
width=None, closed=False)`, `add_point(point, radius_world=0.04, color=None)`,
`clear()`, `data_bounds()`, `viewport()`, `render_svg()`, `render_png(path=None,
scale=1.0)`.

```python
>>> from lissara_equations import make_cubic, make_quadratic
>>> from renderer import GraphConfig, GraphRenderer
>>> g = GraphRenderer(GraphConfig(width=320, height=240))
>>> g.add_cubic(make_cubic((0, 0), (0, 5), (5, 5), (5, 0)))
>>> g.add_curve(make_quadratic((0, 0), (2.5, 4), (5, 0)), color="#d81b60")
>>> svg = g.render_svg()
>>> svg.startswith("<svg") and "viewBox" in svg
True
```

Module helpers: `renderer.graph.nice_step(span, target)` and
`renderer.graph.tick_values(lo, hi, step)` produce tick positions.

```python
>>> from renderer.graph import nice_step, tick_values
>>> nice_step(9.5, 8)
1.0
>>> tick_values(0, 5, 1)
[0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
```

## Scene rendering

### `SceneRenderConfig`

Fields: `background="#ffffff"`, `mode="scene"|"lineart"`, `lineart_color`,
`lineart_width`, `default_stroke`, `default_stroke_width`, `default_fill`,
`respect_visibility`. Invalid `mode` raises `ValueError`.

### `render_scene_svg(scene, output_path=None, config=None) -> str`

Renders a `MathScene` (engine, legacy core, or dict) to **exact** SVG: cubic
segments become `C` commands directly. Path boundaries and open/closed state are
preserved; order is deterministic. Raises `ValueError` if width/height are
missing.

```python
>>> from lissara_engine import MathScene, PathRecord
>>> from lissara_equations import make_cubic
>>> from renderer import render_scene_svg, SceneRenderConfig
>>> scene = MathScene(width=100, height=100)
>>> _ = scene.add_path(PathRecord(path_id="p", closed=True,
...     segments=[make_cubic((0, 0), (100, 0), (100, 100), (0, 100))],
...     stroke={"color": "#111111", "width": 2}))
>>> svg = render_scene_svg(scene, config=SceneRenderConfig(mode="lineart"))
>>> "C " in svg
True
```

### `scene_to_graph(scene, config=None, adaptive=True, tolerance=0.5) -> GraphRenderer`

Builds a plotted (sampled) view of the scene's curves for inspection; the scene
is not mutated. Defaults to the scene's own pixel coordinate system with no
decorations.

## PNG raster (`renderer.raster`)

```python
has_raster_backend() -> bool
svg_to_png(svg_content, path=None, scale=1.0, width=None, height=None) -> bytes
```

Raises `RasterBackendUnavailable` when CairoSVG or the native `cairo` library is
absent. On this repository's Windows environment the native library is missing,
so PNG output is unavailable and callers should fall back to SVG.

```python
>>> from renderer import has_raster_backend
>>> isinstance(has_raster_backend(), bool)
True
```
