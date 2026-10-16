# Lissara test suite

This directory is the single canonical location for automated tests. Discovery
is configured in the repository-root `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

Because of that configuration, a bare `python -m pytest` run anywhere in the
repository collects exactly the `test_*.py` modules here — nothing else (no
root-level scripts, no `scripts/`, no manual/verification files).

## Running

```powershell
.venv\Scripts\python.exe -m pytest                 # full suite (identical to main.py test)
.venv\Scripts\python.exe main.py test              # CLI wrapper, defaults to tests/
.venv\Scripts\python.exe -m pytest tests/test_renderer.py -q   # one module
.venv\Scripts\python.exe -m pytest -k equations -q             # keyword filter
LISSARA_RUN_INTEGRATION=1 .venv\Scripts\python.exe -m pytest   # includes the real-image run
```

Default result: **226 passed, 1 skipped** (the skip is the opt-in
full-resolution integration test). With `LISSARA_RUN_INTEGRATION=1` the suite
collects 227 tests and the real input image is reconstructed end to end.

## Layout

| Path | Purpose |
|---|---|
| `conftest.py` | Shared fixtures (`synthetic_image`: a tiny PNG written to `tmp_path`) |
| `__init__.py` | Package marker only — it contains no tests and is never collected |
| `test_*.py` | Automated tests (table below) |
| `manual/` | Print-based verification scripts, **never** collected because their filenames do not match `test_*.py` |

No `tests/fixtures/` directory is needed: fixtures are generated in `tmp_path`
or read from the committed `outputs/` baseline.

## Modules

| File | Tests | Covers |
|---|---|---|
| `test_equations.py` | 25 | Canonical curve mathematics in `lissara_equations` (points, segments, quadratics, cubics, fitting, continuity) |
| `test_equation_export.py` | 35 | `equation.json` / SVG export from the GUI, numerical accuracy, export dialogs |
| `test_graph_calculator.py` | 50 | Graph viewport, grid/zoom/pan, expression tree, selection and navigation behaviour |
| `test_interface_panels.py` | 38 | Upload/export panels, popups, colours, branding, window chrome |
| `test_reconstruction_pipeline.py` | 14 | End-to-end `main.py reconstruct` artifact validation (plus the opt-in real-image run) |
| `test_cli.py` | 12 | Unified `main.py` CLI: graph/scene/lineart/previews/pipeline/check/status |
| `test_renderer.py` | 18 | Viewport transforms, curve sampling, graph and scene SVG rendering |
| `test_renderer_fixtures.py` | 5 | Committed `outputs/scene.json` / `outputs/output.svg` baselines |
| `test_edge_tracing.py` | 5 | Canny defaults, branch splitting, gap handling in `lissara_vectorization` |
| `test_anime2sketch_adapter.py` | 4 | Optional learned backend adapter (skips without a checkpoint) |
| `test_bezier_fitting.py` | 7 | Adaptive Bézier fitting on synthetic shapes + exact `C` SVG export |
| `test_pipeline.py` | 6 | Normalization, Bézier endpoints, `MathScene` SVG export, rendering losses |
| `test_svg_export.py` | 6 | `lissara_engine` SVG export: geometry, styles, open/closed paths, XML validity |
| `test_legacy_core.py` | 1 | Import/endpoint smoke test for the legacy `core.lissara_core` package |
| `test_render_previews_script.py` | 1 | `scripts/render_previews.py` runs from the repository root |

## Conventions

- Tests assert; they do not rely on printed output.
- All generated artifacts go to `tmp_path`. The committed baseline in
  `outputs/` is read-only — fixture tests only read it, and the suite never
  rewrites it.
- The full-resolution test is opt-in: `LISSARA_RUN_INTEGRATION=1` must be set,
  otherwise it is reported as skipped.
- GUI fixtures (`qapp`, `window`, `loaded_window`) and scene fixtures are
  module-level fixtures in the GUI/export test modules, so a module can be run
  on its own. Set `QT_QPA_PLATFORM=offscreen` when running on a machine
  without a display.

## Manual scripts (`tests/manual/`)

Run directly, never collected by pytest:

| Script | Purpose |
|---|---|
| `verify_legacy_core.py` | Prints an OK/FAIL report for the legacy `core/lissara_core` package (curves, scene JSON, preprocessing, contours) that `run_pipeline.py` still imports; exits non-zero on failure |

## Related tooling

- Diagnostics for the committed artifacts: `scripts/diagnostics/`
  (`check_png.py`, `check_scene.py`, `check_svg.py`, `debug_png.py`) — run from
  any working directory.
- Historical validation notes for the renderer:
  `docs/renderer/validation.md`.
