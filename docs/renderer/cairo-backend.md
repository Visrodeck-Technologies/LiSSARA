# Renderer — Native Cairo / PNG backend investigation

Status: **investigated, not changed.** No system-level dependency was installed
and the environment was not modified. This document records the findings and the
proposed options so a decision can be made explicitly.

## Symptom

`import cairosvg` fails on this Windows host:

```
no library called "cairo" was found
no library called "libcairo-2" was found
cannot load library 'libcairo.so.2': error 0x7e
cannot load library 'libcairo.2.dylib': error 0x7e
cannot load library 'libcairo-2.dll': error 0x7e
```

Consequences:

* `renderer.has_raster_backend()` returns `False`.
* `renderer.svg_to_png(...)` raises `RasterBackendUnavailable`.
* `scripts/run_edge_reconstruction.py` no longer imports `cairosvg` at module
  load; it treats PNG rasterization as optional. The full reconstruction
  pipeline therefore **runs to completion without cairo** — it produces
  `scene.json`, `equations.json`, `equations.txt`, `lineart.svg`, `scene.svg`,
  `graph.svg`, `edges.png` and metrics, and only skips `reconstructed.png` /
  `comparison.png` and the raster-based agreement metrics (reported as not
  computed).

SVG output is unaffected — it is dependency-free and remains the primary
deliverable.

## Root cause

`CairoSVG` does not implement rasterization itself; it calls `cairocffi`, which
loads the **native Cairo library** at import time via `ctypes.util.find_library`
(looking for `cairo`, `cairo-2`, `libcairo-2`, `libcairo.so.2`, …).

* The `cairosvg` pip wheel is pure Python (`py3-none-any`) and does **not** bundle
  the C library.
* The native `cairo` shared library is not present on this machine and is not
  reachable through `ctypes.util.find_library` / `PATH`.
* Installing `pycairo` (which bundles a `libcairo-2.dll` inside its wheel) does
  **not** automatically help: `cairocffi` does not search `pycairo`'s package
  directory. `cairocffi`'s own documentation states that on Windows you must
  install Cairo (typically via the GTK runtime).

## Options (none executed)

### A. Install the GTK3 Windows runtime (thorough)

Install *GTK for Windows Runtime Environment* (the `tschoonj` installer), which
ships `libcairo-2.dll`, `libpango`, `libgdk-pixbuf` and friends, and adds its
`bin` directory to `PATH`.

* **Pros:** restores `import cairosvg`; allows full reproduction of the
  committed Canny baseline metrics (the baseline was produced with CairoSVG
  2.9.1). Also enables the renderer's PNG previews.
* **Cons:** system-level install (not pip, not per-project); modifies `PATH`;
  larger footprint; needs matching 64-bit build; may require
  `os.add_dll_directory` on newer Python if `PATH` changes are not picked up.
* **Scope:** environment only — no code change strictly required, but a small
  helper to `os.add_dll_directory` can make it robust (see issue #329 workaround).

### B. Provide only `libcairo-2.dll` (lighter)

Obtain a trustworthy 64-bit `libcairo-2.dll` (for example from an existing
MSYS2 `mingw64/bin`, a Graphviz install, or the Uniconvertor headless MSI) and
prepend its folder to `PATH` (or call `os.add_dll_directory`) **before**
importing `cairosvg`.

* **Pros:** no full GTK install; smallest change to get PNG output.
* **Cons:** requires sourcing a matching DLL from a reputable source; version
  drift; the DLL's own dependencies must also resolve; still environment-level.

### C. Keep SVG-only, add a dependency-free rasterizer (no environment change)

Leave the native backend optional and implement renderer PNG previews with a
pure-Python scanline fill (the approach `run_pipeline.py` already uses).

* **Pros:** no system dependency; hermetic and reproducible; keeps the renderer
  self-contained; works in CI and on any machine.
* **Cons:** a second rasterizer diverging from CairoSVG's AA output; the
  reconstruction baseline metrics are defined against CairoSVG and would not be
  byte-identical.

## Recommendation

* For **previewing renderer output**, prefer **C** (pure-Python) to avoid a
  system dependency, since SVG is already the primary artifact and PNG is only a
  convenience preview.
* If the goal is to **regenerate or re-verify the committed reconstruction
  baseline** with identical rasterization, use **A** (GTK runtime), because the
  baseline metrics were computed through CairoSVG.

Either way the renderer already degrades gracefully: `has_raster_backend()`
reports availability and `svg_to_png` raises `RasterBackendUnavailable`, so no
code change is required to tolerate the missing library.

## What would change if approved

* Option A: document a one-time GTK install step (plus optional
  `os.add_dll_directory` helper); no source changes required.
* Option B: document the DLL/PATH step; no source changes required.
* Option C: add a small pure-Python raster module under `renderer/` and a
  `--png` path in `scripts/render_previews.py`; no new dependencies.

No dependencies were added to `requirements.txt` and no manifest was changed.
