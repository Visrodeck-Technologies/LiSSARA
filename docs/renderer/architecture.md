# Lissara Renderer — Architecture

## Role in Lissara

The `renderer` package is the mathematical **graphing and visualization** layer.
It sits on top of the completed Phase 1 foundation and turns curves and scenes
into inspectable output (primarily SVG). It exists to:

* visualize mathematical curves and parametric Bézier equations accurately;
* support inspection of connected Bézier segments;
* provide a rendering foundation for the existing line-art reconstruction
  results — **without changing the reconstruction algorithm**.

The renderer performs no image analysis. It never implements edge detection,
contour tracing, or Bézier fitting; those live in `lissara_vectorization`.

## Package boundaries

```
lissara_equations        (pure Python math, no deps)
        ▲        ▲
        │        │
lissara_vectorization    (image I/O, contour tracing, adaptive fitting)
        ▲        │
        │        │
lissara_engine  ─────────┘ (MathScene, PathRecord, SVG export, losses)
        ▲
        │
    renderer             (sampling, viewport, graph, scene rendering, raster)
```

* `renderer` depends on `lissara_equations` (curve evaluation) and
  `lissara_engine` (the canonical `MathScene`/`PathRecord`).
* The dependencies are **acyclic**. `renderer` is a leaf package: nothing below
  imports it.
* All curve mathematics is delegated to `lissara_equations`; the renderer does
  not re-implement evaluation, derivatives, split, or flattening.

### Discrepancy fixed during the audit

`renderer/__init__.py` previously contained `from .scene import MathScene,
PathRecord`, but `renderer/scene.py` did **not** exist, so `import renderer`
raised `ModuleNotFoundError`. Rather than create a second, conflicting scene
class, `renderer/scene.py` now re-exports `MathScene`/`PathRecord` from
`lissara_engine` **and** provides the scene-rendering adapter. This is the
smallest correction consistent with "reuse the compatible `lissara_engine`
functionality".

## Module layout

| Module | Responsibility |
|---|---|
| `renderer/viewport.py` | World ⇄ screen affine mapping, bounds validation, `fit_bounds` |
| `renderer/sampling.py` | Uniform and adaptive curve sampling |
| `renderer/svg.py` | Dependency-free SVG serialization (`SvgCanvas`, `path_data`, escaping) |
| `renderer/graph.py` | `GraphConfig` + `GraphRenderer`: curves, axes, grid, ticks, labels |
| `renderer/scene.py` | Exact MathScene rendering + `scene_to_graph` adapter |
| `renderer/raster.py` | Optional PNG preview via CairoSVG |

The design keeps three concerns separate: **evaluate** (`lissara_equations`),
**map** (`viewport`), **draw** (`svg`, `graph`, `scene`).

## Curve sampling strategy

Sampling decides *where* to evaluate; it delegates every evaluation to
`lissara_equations.evaluate_bezier` / `evaluate_quadratic` / `evaluate_segment`.

* **Uniform** (`sample_cubic`, `sample_quadratic`, `sample_segment`) evaluates
  `n + 1` evenly spaced parameters. Predictable cost.
* **Adaptive** (`sample_cubic_adaptive`, `sample_quadratic_adaptive`) recursively
  bisects the interval and stops when the midpoint deviates from the chord by at
  most `tolerance`. This materially reduces point counts on straight regions
  while preserving fidelity on curved regions. `max_depth` bounds the worst case
  at `2**max_depth + 1` points.

Two fidelity guarantees, verified by tests:

1. **Exact endpoints.** The interval endpoints are emitted verbatim, so a curve
   sampled over `[0, 1]` keeps its exact start/end points.
2. **Controllable deviation.** The adaptive error metric is the perpendicular
   midpoint-to-chord distance (a max-deviation proxy, not a strict Hausdorff
   bound); lowering `tolerance` monotonically reduces it.

Degenerate curves (coincident control points) satisfy the flatness test
immediately and yield just the two interval endpoints. Non-finite evaluations
raise `ValueError` instead of emitting `NaN`/`inf` coordinates.

`sample_curve` dispatches on the record's degree (2 or 3) using the
`control_points` length or the explicit `"degree"` key.

## Coordinate systems and transformations

* **World (mathematical):** `x` right, `y` up.
* **Screen (pixels):** origin top-left, `y` down.

`Viewport(width, height, world_bounds, margin, preserve_aspect, invert_y)`
performs the affine map:

```
px = margin + offset_x + (x - xmin) * scale_x
py = margin + offset_y + (ymax - y) * scale_y      # invert_y == True
```

* `preserve_aspect=True` uses a single `scale = min(plot_w/world_w,
  plot_h/world_h)` and centres the world box in the plot area.
* `preserve_aspect=False` scales each axis independently to fill the area.
* `invert_y=False` is used for reconstruction scenes, whose coordinates are
  already in pixel space with `y` down, so the geometry maps 1:1.

`world_to_screen` and `screen_to_world` are exact inverses (verified with
round-trip tests). Invalid dimensions, non-finite values, and degenerate bounds
(`xmin >= xmax` or `ymin >= ymax`) raise `ValueError` at construction.

## Rendering flow

**Graph rendering** (`GraphRenderer`):

1. Curves are added (polyline / single Bézier / cubic-segment chain / marker).
2. World bounds are taken from config or inferred from the data with padding.
3. A `Viewport` is built.
4. Grid lines, axes, ticks and labels are emitted (each toggleable).
5. Curves are mapped to screen space and written as `<path>` elements.

**Scene rendering** (`render_scene_svg`) takes a **different, exact path**: it
serializes each cubic segment's control points directly as SVG `C` commands via
`svg.path_data`, so the reconstruction geometry is reproduced exactly — never a
resampled approximation and never the control polygon. Open/closed state and per
path boundaries are preserved; a deterministic path order (scene order) is used.

## SVG and optional PNG backends

* **SVG is the primary output** and is dependency-free. Attributes are quoted and
  escaped with `xml.sax.saxutils.quoteattr`/`escape`; the document carries a
  correct `viewBox` and canvas dimensions; elements are emitted in a stable
  order.
* **PNG is optional** (`renderer/raster.py`) and requires CairoSVG **and** the
  native `cairo` shared library. When either is missing, `svg_to_png` raises
  `RasterBackendUnavailable` and `has_raster_backend()` returns `False`. On this
  Windows environment the native library is **not** present, so only SVG output
  is produced. This is detected, not assumed.

## Performance considerations

* Scene rendering does **no sampling and no rebuilding**: each segment becomes
  one `C` command in a single linear pass, so a scene with thousands of segments
  scales linearly (1372 segments → 1372 commands in the validation run).
* Graph rendering uses adaptive sampling by default to avoid oversampling
  straight regions.
* No caching layer is needed because scene geometry is emitted directly; if a
  future interactive UI needs incremental redraws, geometry can be cached per
  `path_id` since ids are stable.

## Current limitations

* PNG previews are unavailable without the native cairo library.
* Adaptive sampling uses a midpoint chord-deviation proxy (not a strict
  Hausdorff distance).
* The graph renderer targets 2D Cartesian plotting only; no 3D, no logarithmic
  axes, no symbolic math.
* Axis tick placement uses a "nice number" heuristic (1/2/5·10ᵏ) rather than
  minimizing tick-label collisions.
* Text is rendered with a generic `monospace` family; no font embedding.

## References

* Bézier evaluation/flattening — `lissara_equations/MATHEMATICS.md`
  (Pomax, *A Primer on Bézier Curves*, https://pomax.github.io/bezierinfo/).
* SVG 2 Paths — https://www.w3.org/TR/SVG/latest/paths.html
* `xml.sax.saxutils` — https://docs.python.org/3/library/xml.sax.saxutils.html
