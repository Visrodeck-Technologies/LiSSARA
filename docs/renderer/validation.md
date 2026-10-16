# Lissara Renderer — Validation

This document records the actual tests, commands, generated artifacts, geometric
checks, and known limitations observed when the graphing engine was built.

Environment: repository `.venv`, Python 3.13.13, NumPy 2.5.4, OpenCV 5.0.0,
Pillow 12.3.0. CairoSVG is installed but its **native `cairo` library is
absent** on this Windows host, so PNG rasterization is unavailable.

## Test suite

Command:

```
python -m pytest tests -q
```

Result:

```
83 passed, 1 skipped
```

(The skipped test is the opt-in full-resolution real-image integration test; run
it with `LISSARA_RUN_INTEGRATION=1 python -m pytest tests -q`.)

Breakdown by file:

| File | Tests | Covers |
|---|---|---|
| `tests/test_equations.py` | 25 | Phase 1 curve mathematics (regression) |
| `tests/test_renderer.py` | 18 | Sampling, viewport, graph, scene, raster |
| `tests/test_renderer_fixtures.py` | 5 | Committed-artifact fixtures (scene.json, output.svg) |
| `tests/test_edge_tracing.py` | 5 | Vectorization edge tracing (regression) |
| `tests/test_anime2sketch_adapter.py` | 4 | Optional backend adapter (regression) |
| `tests/test_render_previews_script.py` | 1 | `render_previews.py` runs from repository root (regression) |
| `tests/test_cli.py` | 12 | Unified `main.py` CLI (graph/scene/lineart/check/reconstruct) |
| `tests/test_reconstruction_pipeline.py` | 14 | End-to-end image→equations→render pipeline (synthetic + opt-in real image) |

### Renderer test coverage (`tests/test_renderer.py`)

1. Uniform sampling of linear and cubic Béziers.
2. Endpoint preservation (uniform and adaptive).
3. Adaptive sampling on straight, curved, and degenerate (coincident) geometry.
4. World→screen and screen→world coordinate round-trips (both directions).
5. Viewport bounds, aspect-ratio preservation, non-preserving fill, and
   vertical-axis inversion.
6. Validation/rejection of illegal viewports (zero size, degenerate bounds,
   oversized margin).
7. `fit_bounds` padding and single-point/line expansion.
8. Graph rendering of individual curves with structural SVG assertions.
9. Multiple independent curves; closed vs open path behaviour.
10. SVG parses with `xml.etree.ElementTree` (valid XML).
11. Non-finite coordinate rejection (`NaN`/`inf`).
12. Scene rendering from a `MathScene` and from a dict; geometry not mutated.
13. Deterministic raster backend flag + `RasterBackendUnavailable` when absent.

Geometric assertions use `math.isclose`; SVG assertions parse the document and
inspect structure.

## Integration validation against a real MathScene

The reconstructed scene `outputs/scene.json` (1840×2991, 128 paths) was rendered
with the exact scene renderer:

```
python scripts/render_previews.py
```

Observed output:

```
Wrote outputs\renderer_graph_preview.svg (5135 chars)
Wrote outputs\renderer_scene_preview.svg (115308 chars)
Segments in scene: 1372; C commands in SVG: 1372
Wrote outputs\renderer_lineart_preview.svg (109804 chars)
PNG raster backend unavailable (native cairo missing); SVG only.
Validation OK: all exported SVGs parse; cubic geometry preserved exactly.
```

**Key geometric check:** the number of SVG `C` commands equals the number of
Bézier segments in the scene (1372 = 1372). This confirms the renderer reproduces
the recorded cubic geometry exactly and does not substitute the control polygon
or a resampled approximation.

## Committed fixtures for renderer validation

Two committed artifacts under `outputs/` are used as fixtures. No
image-reconstruction run is required to validate the renderer.

### `outputs/scene.json` — MathScene fixture

* A real `MathScene` (JSON): `width=1840`, `height=2991`,
  `path_type="region-contour"`, **128 closed paths**, **1372 cubic segments**
  (keys `control_points`, `x_coeffs`, `y_coeffs`), fill black.
* **Suitable** for validating `render_scene_svg`: a deterministic, self-contained
  cubic scene.
* `tests/test_renderer_fixtures.py` asserts the render emits exactly 1372 `C`
  commands, a `viewBox` of `0 0 1840 2991`, valid XML, byte-identical repeated
  output, and that the scene object is not mutated.

### `outputs/output.svg` — Canny line-art baseline

* The committed baseline SVG: `viewBox="0 0 1840 2991"`, **1423 `<path>`
  elements**, **6030 cubic `C` commands**, stroke-only `edge-path-*` paths with
  `stroke:#17151b`, one white background `<rect>`.
* It is an **SVG**, not a `MathScene`, so it is not fed to the renderer directly.
  Instead the test/script parses each `d` (`M`/`L`/`C`/`Z`) into canonical cubic
  segment records, rebuilds a scene, and renders it. This exercises the renderer
  against the *actual* committed stroke-only, open-path geometry.
* Result — **exact reproduction**:

  ```
  Baseline recheck: 1423 paths / 6030 cubics reproduced exactly from committed output.svg
  ```

  `tests/test_renderer_fixtures.py` verifies both the counts and
  control-point-for-control-point equality of every rebuilt segment.

### Verdict

| Fixture | Loadable as MathScene | Use |
|---|---|---|
| `outputs/scene.json` | Yes | Exact render + determinism + no-mutation |
| `outputs/output.svg` | No (parsed to segments) | Baseline geometry reproduction (1423/6030) |

Fixture tests `skipif` the file is absent, so the suite remains usable in a bare
checkout.

## Generated artifacts

| Artifact | Description |
|---|---|
| `outputs/renderer_graph_preview.svg` | Mathematical graph: two cubic arches, one quadratic, a marker, with axes/grid/ticks/labels |
| `outputs/renderer_scene_preview.svg` | The reconstructed scene rendered with exact cubic `C` commands (black fills) |
| `outputs/renderer_lineart_preview.svg` | The same scene as a white-background dark-stroke line-art preview |
| `outputs/renderer_scene_preview.png` | **Not produced** — native cairo unavailable |

All three SVG files were parsed successfully with `xml.etree.ElementTree`.

## Reconstruction pipeline regression

The reconstruction pipeline was re-run unchanged on `INPUT/image.png` (in a
temporary working directory so committed outputs were not modified):

```
Image: 1840x2991; contours: 173; paths: 100; Bézier segments: 717
Pixel MAE: 0.274424
Edge loss: 0.008367
```

Identical to the Phase 1 baseline (717 segments, MAE 0.274424). No pipeline code
was modified in Phase 2.

The four root-level smoke scripts (`test_pipeline.py`, `test_bezier_fitting.py`,
`test_svg.py`, `test_svg_export.py`) were later moved into `tests/` and rewritten
as assertion-based tests, so they are part of the suite above.

## Collection scope

`pytest.ini` sets `testpaths = tests`, so a bare `python -m pytest` collects only
the automated suite. Manual scripts under `tests/manual/` (currently
`verify_legacy_core.py`) use filenames that do not match `test_*.py` and are
never executed during discovery.

The obsolete prototype scripts that used to abort a repo-wide collection run —
`scripts/final_test.py`, `scripts/test_integration.py`,
`scripts/test_runner.py`, `scripts/verify_core.py` and
`scripts/verify_final.py` — were removed during repository cleanup. Their only
still-valuable checks (the legacy `core.lissara_core` package imported by
`run_pipeline.py`) were repaired as `tests/manual/verify_legacy_core.py`.
`core.lissara_core.optimization` still raises `IndentationError` at import time
(pre-existing, now unreferenced) and is reported by no test or script.

## Known limitations

* PNG previews require the native cairo library, which is not installed here.
* Adaptive sampling error is a midpoint chord-deviation proxy, not a strict
  Hausdorff bound.
* Graph ticks use a "nice number" heuristic; label collisions at extreme aspect
  ratios are not resolved.
* No font embedding; labels use a generic `monospace` family.
