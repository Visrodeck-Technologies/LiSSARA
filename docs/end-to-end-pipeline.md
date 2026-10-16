# Lissara — End-to-End Reconstruction Pipeline

This document describes the implemented, tested image-to-equations-to-rendering
pipeline: a raster image is analyzed, its line art is traced and fitted as cubic
Bézier curves, the fitted geometry is exported as mathematical equations, and
the result is rendered back to SVG. Everything here reflects behaviour that was
actually executed and validated (see [Validation](#validation)).

## One command

```
.venv\Scripts\python.exe main.py reconstruct --input INPUT/image.png --output-dir outputs/generated
```

The command is implemented once and delegated to: the algorithm lives in
`scripts/run_edge_reconstruction.py` (public function `run_reconstruction`), and
`main.py` loads and invokes it. No reconstruction logic is duplicated in the CLI.

### Options

| Option | Default | Meaning |
|---|---|---|
| `--input` | `INPUT/image.png` | Input raster image |
| `--output-dir` | `outputs/generated` | Destination directory (created if missing) |
| `--canny-low` | `50` | Canny lower hysteresis threshold |
| `--canny-high` | `150` | Canny upper hysteresis threshold |
| `--aperture-size` | `3` | Sobel aperture (3, 5 or 7) |
| `--blur-sigma` | `0.0` | Gaussian pre-blur sigma (0 = disabled) |
| `--gap-close` | `0` | 3×3 morphological closing iterations (0 = exact Canny pixels) |
| `--gap-tolerance` | `1` | Join tangent-aligned stroke ends across this many missing pixels |
| `--min-length` | `4.0` | Minimum contour length retained |
| `--frame-margin` | `2` | Margin (px) used to drop border/frame artifacts |
| `--fit-tolerance` | `1.5` | Adaptive cubic fitting tolerance (px) |
| `--max-segments` | `24` | Maximum cubic segments fitted per path |
| `--stroke-width` | `1.25` | Line-art stroke width |
| `--no-png` | off | Skip PNG rasterization even if a backend exists |
| `--force` | off | Overwrite an output directory that already contains artifacts |

The classical algorithm and its defaults are unchanged from the original
`run_edge_reconstruction.py`; only the outputs and entry points were expanded.

`--force` is required **only** when the destination already contains files that
would be overwritten. A new or empty destination runs without confirmation.

## Workflow stages

1. **Load and validate** the image; convert to grayscale.
2. **Edge detection** — `lissara_vectorization.edge_tracing.detect_classical_edges`
   (Gaussian pre-blur when `--blur-sigma > 0`, then `cv2.Canny`, then optional
      then optional 3x3 morphological closing).
3. **Contour tracing** — `trace_edge_paths` walks ordered edge chains, splits at
   junctions and bridges tangent-aligned gaps (`--gap-tolerance`).
4. **Filtering** — `filter_edge_paths` removes paths shorter than
   `--min-length` and frame artifacts within `--frame-margin`.
5. **Adaptive cubic fitting** — `fit_bezier_adaptive` produces canonical cubic
   records (`control_points`, `x_coeffs`, `y_coeffs`).
6. **Scene assembly** — a `lissara_engine.MathScene` is built with the image
   dimensions, one `PathRecord` per accepted contour, open/closed state, and
   stroke style; reconstruction settings and provenance go into `metadata`.
7. **Geometry validation** — every control point must be finite and inside the
   canvas; segments must be C0-continuous; closed paths must close.
8. **Scene serialization** — `scene.json`.
9. **Equation export** — `equations.json` and `equations.txt`, followed by a
   verification pass (below).
10. **Rendering** — `lineart.svg`, `scene.svg`, `graph.svg` via the `renderer`
    graphing engine; `edges.png` directly from OpenCV.
11. **Metrics** — `metrics.txt` / `metrics.json`.
12. **Optional rasterization** — `reconstructed.png` / `comparison.png` when the
    native cairo backend is available.

## Canonical cubic representation

Every fitted curve is a cubic Bézier stored in the historical Lissara schema:

```
x(t) = a3*t^3 + a2*t^2 + a1*t + a0
y(t) = b3*t^3 + b2*t^2 + b1*t + b0,     0 <= t <= 1
```

with four control points `P0..P3`. The coefficient keys are `a3/a2/a1/a0` for
`x_coeffs` and `b3/b2/b1/b0` for `y_coeffs` (the asymmetric naming is the
existing serialization format). All evaluation is delegated to
`lissara_equations` — no second evaluator exists.

## Artifacts and formats

### `scene.json`

```json
{
  "width": 1840,
  "height": 2991,
  "paths": [
    {
      "records": [],
      "path_id": "edge-path-00000",
      "path_type": "line-art-contour",
      "closed": true,
      "segments": [
        { "control_points": [[x0,y0],[x1,y1],[x2,y2],[x3,y3]],
          "x_coeffs": {"a3":...,"a2":...,"a1":...,"a0":...},
          "y_coeffs": {"b3":...,"b2":...,"b1":...,"b0":...} }
      ],
      "fill":   {"color": "none", "opacity": 0},
      "stroke": {"color": "#17151b", "width": 1.25, "opacity": 1}
    }
  ],
  "metadata": { "source": "...", "canny_low": 50, "...": "..." }
}
```

### `equations.json`

Round-trippable JSON describing exactly what the current run produced:

```json
{
  "metadata": { "...": "..." },
  "path_count": 1423,
  "segment_count": 6030,
  "paths": [
    {
      "path_id": "edge-path-00000",
      "path_type": "line-art-contour",
      "closed": true,
      "closed_loop_continuous": true,
      "segment_count": 8,
      "segments": [
        {
          "index": 0,
          "domain": [0.0, 1.0],
          "control_points": [[1797,50],[1798,50],[1799,50],[1800,50]],
          "x_coeffs": {"a3":0,"a2":0,"a1":3,"a0":1797},
          "y_coeffs": {"b3":0,"b2":0,"b1":0,"b0":50},
          "x_expression": "x(t) = 0*t^3 + 0*t^2 + 3*t + 1797",
          "y_expression": "y(t) = 0*t^3 + 0*t^2 + 0*t + 50",
          "continuous_with_previous": true
        }
      ]
    }
  ]
}
```

### `equations.txt`

Human-readable listing, one block per path and per segment:

```
Path: edge-path-00000
Closed: True
Segments: 8

Segment: 0
Domain: 0 <= t <= 1
Control points:
  P0 = (1797, 50)
  P1 = (1798, 50)
  P2 = (1799, 50)
  P3 = (1800, 50)
x(t) = 0*t^3 + 0*t^2 + 3*t + 1797
y(t) = 0*t^3 + 0*t^2 + 0*t + 50
```

### Equation verification

During every run the equation report is checked against the scene:

* path and segment counts agree between the scene, the report and the
  re-parsed JSON;
* for the first and last segment of every path, the report's coefficients are
  evaluated at `t = 0, 0.5, 1` and compared with an **independent** de Casteljau
  evaluation of the report's control points;
* each segment's `t = 0` / `t = 1` evaluations must equal `P0` / `P3`.

`metrics.json → equations.validation.ok` is `true` only when all of this holds.
On the input image the maximum observed discrepancy is `0.0` (tolerance `1e-6`).

### SVGs

* `lineart.svg` — primary artifact. White background, dark strokes
  (`#17151b`), no fills, every path emitted as cubic `C` commands. The number of
  `C` commands equals the number of Bézier segments in the scene.
* `scene.svg` — scene mode honouring each path's stored fill/stroke; also cubic
  `C` commands (exact geometry, never a resampled polyline).
* `graph.svg` — the same curves plotted through `renderer.scene_to_graph` and
  `GraphRenderer` in image pixel space: `viewBox="0 0 W H"`, no axes, grid,
  ticks or labels, and no vertical flip (the stored coordinates are already in
  image space). Curves are sampled for plotting, so this view contains `M`/`L`
  commands rather than `C`.

## Metric definitions

`metrics.json` groups metrics into:

* **input** — source path, width and height.
* **edge_detection** — Canny parameters and the number of edge pixels.
* **contours** — traced paths, accepted paths, open/closed counts, accepted
  contour pixels, gap/filter parameters.
* **fitting** — fit tolerance, `max_segments_per_path`, total fitted segments,
  and `paths_at_segment_limit` (paths that reached `--max-segments`; the fitter
  caps a path at that many segments — the limit is explicit, never silent).
* **equations** — path/segment counts and the verification result.
* **svg** — per-file path and cubic-command counts.
* **raster** — whether a PNG backend is available, whether PNGs were written,
  and an explanatory note when they were not.
* **reconstruction_metrics** — when rasterization is available, rendered-vs-Canny
  agreement (`line_map_mae`, `edge_precision_2px`, `edge_recall_2px`,
  `edge_f1_2px`, and mean distances). These measure how faithfully the rendered
  SVG reproduces the **Canny reference map**, not independent ground-truth
  fidelity. When the backend is absent this field is `null` and the note states
  which metrics were not calculated — nothing is invented.
* **runtime_seconds** and **environment**.

## Native cairo / PNG behaviour

SVG is dependency-free and always produced. PNG rasterization uses CairoSVG,
which needs the native `cairo` shared library. On hosts without it:

* `renderer.has_raster_backend()` returns `False`;
* `reconstructed.png` / `comparison.png` are skipped and `raster_metrics` are
  reported as not computed;
* **all other stages — edge extraction, tracing, fitting, scene and equation
  export, and SVG rendering — still succeed.**

No system library is installed or modified automatically. See
`docs/renderer/cairo-backend.md` for options if PNG output is required.

## Validation

Environment: repository `.venv`, Python 3.13.13, NumPy 2.5.4, OpenCV 5.0.0,
Pillow 12.3.0. Native cairo is absent, so PNG output is unavailable.

Real run:

```
.venv\Scripts\python.exe main.py reconstruct --input INPUT/image.png --output-dir outputs/generated
```

Observed on `INPUT/image.png` (1840×2991):

| Metric | Value |
|---|---|
| Traced paths | 2614 |
| Accepted paths | 1423 (open 1386, closed 37) |
| Fitted cubic segments / equations | 6030 |
| `lineart.svg` | 1423 paths, 6030 cubic `C` commands |
| `scene.svg` | 1423 paths, 6030 cubic `C` commands |
| Equation verification | `ok`, max error `0.0` |
| Runtime | ≈ 2.3 s |

Additional checks performed and passing:

* the command exits `0`; a second run without `--force` exits `2` with a clear
  message, and with `--force` exits `0`;
* `scene.json` paths are non-empty, all control points finite and inside the
  canvas, segments C0-continuous, and closed paths close;
* the traced/accepted/open/closed counts satisfy `open + closed == accepted`;
* `equations.json` re-parses and its counts equal the scene's;
* `equations.txt` contains a block for every path;
* every SVG parses as XML; `lineart.svg` and `scene.svg` contain exactly as many
  `C` commands as the scene has segments;
* `edges.png` decodes at the input dimensions;
* the committed `outputs/` baseline is not modified (all artifacts go to the
  chosen output directory).

Automated coverage: `tests/test_reconstruction_pipeline.py` runs the full
pipeline on a small synthetic image and validates every artifact;
`tests/test_cli.py` exercises the CLI. The full-resolution real-image run is
available as an opt-in integration test
(`LISSARA_RUN_INTEGRATION=1 python -m pytest tests -q`).

## Limitations

* The pipeline is classical Canny + contour tracing + adaptive Bézier fitting;
  there is no learned or color-based segmentation.
* `--max-segments` caps segments per path (reported as
  `paths_at_segment_limit`); it never drops accepted paths.
* Adaptive fitting error is measured by chord deviation, not a strict Hausdorff
  bound.
* Raster-based agreement metrics require the native cairo library and compare
  against the Canny reference map, not an independent ground truth.
* Graph rendering samples the fitted curves for plotting; use `lineart.svg` /
  `scene.svg` (or `scene.json` / `equations.json`) for exact geometry.
