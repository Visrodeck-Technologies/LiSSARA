"""Lissara unified command-line interface.

A single entry point for the Lissara toolchain: mathematical graph rendering,
exact scene/line-art SVG export, preview generation, the classical
raster-to-vector pipeline, and validation/reporting.

Commands delegate to the existing, tested implementations where an entry point
already exists (``scripts/render_previews.py``, ``run_pipeline.py``,
``scripts/run_edge_reconstruction.py``); the graph/scene/lineart commands call
the public ``renderer`` API directly. The ``reconstruct`` command loads the
reconstruction implementation from ``scripts/run_edge_reconstruction.py`` and
runs the complete image-to-equations-to-rendering workflow (no cairo required).
It writes to an isolated ``outputs/generated`` directory by default and only
overwrites an existing output directory when ``--force`` is given.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUTPUTS = ROOT / "outputs"
SVG_NS = "{http://www.w3.org/2000/svg}"

SCENE_JSON = OUTPUTS / "scene.json"
BASELINE_SVG = OUTPUTS / "output.svg"
METRICS_TXT = OUTPUTS / "metrics.txt"
GRAPH_PREVIEW = OUTPUTS / "renderer_graph_preview.svg"
SCENE_PREVIEW = OUTPUTS / "renderer_scene_preview.svg"
LINEART_PREVIEW = OUTPUTS / "renderer_lineart_preview.svg"
RASTER_PREVIEW = OUTPUTS / "renderer_scene_preview.png"

PREVIEW_SVGS = {
    "output.svg": BASELINE_SVG,
    "renderer_graph_preview.svg": GRAPH_PREVIEW,
    "renderer_scene_preview.svg": SCENE_PREVIEW,
    "renderer_lineart_preview.svg": LINEART_PREVIEW,
}


def _resolve(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _validate_scene(data, source) -> tuple[float, float, int, int]:
    """Validate a scene mapping and return ``(width, height, paths, segments)``."""
    if not isinstance(data, dict):
        raise ValueError(f"{source}: top-level JSON must be an object")
    width = data.get("width")
    height = data.get("height")
    if (not isinstance(width, (int, float)) or not isinstance(height, (int, float))
            or isinstance(width, bool) or isinstance(height, bool)
            or width <= 0 or height <= 0):
        raise ValueError(
            f"{source}: invalid dimensions width={width!r} height={height!r}")
    paths = data.get("paths")
    if not isinstance(paths, list):
        raise ValueError(f"{source}: 'paths' must be a list")
    segments = sum(len(p.get("segments", [])) for p in paths if isinstance(p, dict))
    return float(width), float(height), len(paths), segments


def _svg_stats(path: Path) -> tuple[int, int]:
    """Return ``(path_count, cubic_command_count)`` for an SVG file."""
    root = ET.parse(path).getroot()
    paths = root.findall(SVG_NS + "path")
    cubics = path.read_text(encoding="utf-8").count("C ")
    return len(paths), cubics


def _write_svg(svg: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    ET.fromstring(svg)


def _confirm(flag: bool, action: str, files) -> bool:
    if flag:
        return True
    print(f"warning: '{action}' rewrites committed files under outputs/:")
    for name in files:
        print(f"  - {name}")
    print("re-run with --yes to proceed")
    return False


# -- commands ---------------------------------------------------------------

def cmd_graph(args) -> int:
    from lissara_equations import make_cubic, make_quadratic
    from renderer import GraphConfig, GraphRenderer

    config = GraphConfig(
        width=args.width,
        height=args.height,
        margin=args.margin,
        show_grid=not args.no_grid,
        show_axes=not args.no_axes,
        show_ticks=not args.no_ticks,
        show_labels=not args.no_labels,
        tick_target=args.tick_target,
    )
    renderer = GraphRenderer(config)
    renderer.add_cubic(make_cubic((0, 0), (0, 6), (6, 6), (6, 0)), tolerance=0.1)
    renderer.add_cubic(make_cubic((0, 0), (2, -3), (4, 3), (6, 0)),
                       tolerance=0.1, color="#d81b60")
    renderer.add_curve(make_quadratic((0, 0), (3, 5), (6, 0)),
                       adaptive=True, tolerance=0.1, color="#2e7d32")
    renderer.add_point((3, 4.5), radius_world=0.08, color="#2e7d32")

    svg = renderer.render_svg()
    out = _resolve(args.output)
    _write_svg(svg, out)
    print(f"Wrote {_display(out)} "
          f"({len(svg)} chars, {svg.count('C ')} cubic commands, "
          f"{config.width:.0f}x{config.height:.0f})")
    return 0


def _render_scene(args, mode: str, default_output: Path) -> int:
    from renderer import SceneRenderConfig, render_scene_svg

    scene_path = _resolve(args.input)
    if not scene_path.exists():
        print(f"error: scene file not found: {scene_path}", file=sys.stderr)
        return 1
    try:
        scene = json.loads(scene_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: {scene_path} is not valid JSON: {exc}", file=sys.stderr)
        return 1
    try:
        width, height, paths, segments = _validate_scene(scene, scene_path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    config = SceneRenderConfig(mode=mode)
    if mode == "lineart":
        config.lineart_color = args.lineart_color
        config.lineart_width = args.lineart_width

    out = _resolve(args.output) if args.output else default_output
    svg = render_scene_svg(scene, output_path=str(out), config=config)
    ET.fromstring(svg)
    print(f"Validated {_display(scene_path)}: "
          f"{width:.0f}x{height:.0f}, {paths} paths, {segments} segments")
    print(f"Wrote {_display(out)} "
          f"({len(svg)} chars, {svg.count('C ')} cubic commands, mode={mode})")
    return 0


def cmd_scene(args) -> int:
    return _render_scene(args, "scene", SCENE_PREVIEW)


def cmd_lineart(args) -> int:
    return _render_scene(args, "lineart", LINEART_PREVIEW)


def _run_script(script: Path, extra) -> int:
    return subprocess.run(
        [sys.executable, str(script), *extra], cwd=str(ROOT)).returncode


def cmd_previews(args) -> int:
    files = [p.name for p in PREVIEW_SVGS.values()]
    if RASTER_PREVIEW.exists():
        files.append(RASTER_PREVIEW.name)
    print(f"note: regenerates {', '.join(files)} (deterministic previews)")
    if args.yes and RASTER_PREVIEW.exists():
        RASTER_PREVIEW.unlink()
    return _run_script(ROOT / "scripts" / "render_previews.py", [])


def cmd_pipeline(args) -> int:
    files = ["scene.json", "output.svg", "metrics.txt",
             "input_preview.png", "reconstructed.png"]
    if not _confirm(args.yes, "pipeline", files):
        return 2
    return _run_script(ROOT / "run_pipeline.py", [])


def _load_reconstruction_module():
    """Load ``scripts/run_edge_reconstruction.py`` as an importable module.

    The reconstruction algorithm lives in that script; the CLI must not
    duplicate it, so it is loaded by path and invoked directly.
    """
    import importlib.util

    script = ROOT / "scripts" / "run_edge_reconstruction.py"
    spec = importlib.util.spec_from_file_location("lissara_run_edge_reconstruction", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cmd_reconstruct(args) -> int:
    module = _load_reconstruction_module()
    try:
        summary = module.run_reconstruction(
            args.input, args.output_dir,
            canny_low=args.canny_low,
            canny_high=args.canny_high,
            aperture_size=args.aperture_size,
            blur_sigma=args.blur_sigma,
            gap_close=args.gap_close,
            gap_tolerance=args.gap_tolerance,
            min_length=args.min_length,
            frame_margin=args.frame_margin,
            fit_tolerance=args.fit_tolerance,
            max_segments=args.max_segments,
            stroke_width=args.stroke_width,
            force=args.force,
            write_png=False if args.no_png else None,
        )
    except module.OutputExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    metrics = summary["metrics"]
    print(f"Reconstruction complete: {summary['accepted_paths']} paths "
          f"(open={summary['open_paths']}, closed={summary['closed_paths']}), "
          f"{summary['segments']} cubic segments")
    print(f"Traced paths: {summary['traced_paths']}")
    print(f"Artifacts in {summary['output_dir']}: {', '.join(summary['artifacts'])}")
    print(f"lineart.svg: {summary['lineart_paths']} paths, "
          f"{summary['lineart_cubics']} cubic commands; "
          f"equations: {summary['equations']}")
    if metrics["raster"]["note"]:
        print(f"note: {metrics['raster']['note']}")
    return 0


def cmd_test(args) -> int:
    command = [sys.executable, "-m", "pytest", args.path, "-q", *args.pytest_args]
    return subprocess.run(command, cwd=str(ROOT)).returncode


def cmd_check(args) -> int:
    ok = True

    def report(label: str, good: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and good
        line = f"[{'OK' if good else 'FAIL'}] {label}"
        if detail:
            line += f" -- {detail}"
        print(line)

    if SCENE_JSON.exists():
        try:
            data = json.loads(SCENE_JSON.read_text(encoding="utf-8"))
            width, height, paths, segments = _validate_scene(data, SCENE_JSON)
            report("outputs/scene.json", True,
                   f"{width:.0f}x{height:.0f}, {paths} paths, {segments} segments")
        except (ValueError, json.JSONDecodeError) as exc:
            report("outputs/scene.json", False, str(exc))
    else:
        report("outputs/scene.json", False, "missing")

    for name, path in PREVIEW_SVGS.items():
        label = f"outputs/{name}"
        if not path.exists():
            report(label, False, "missing")
            continue
        try:
            paths, cubics = _svg_stats(path)
            good = paths > 0
            report(label, good, f"{paths} paths, {cubics} cubic commands")
        except ET.ParseError as exc:
            report(label, False, f"XML parse error: {exc}")

    if METRICS_TXT.exists():
        first = METRICS_TXT.read_text(encoding="utf-8").splitlines()
        report("outputs/metrics.txt", bool(first),
               f"{len(first)} lines")
    else:
        report("outputs/metrics.txt", False, "missing")

    return 0 if ok else 1


def cmd_status(args) -> int:
    import platform
    import importlib

    print(f"repo root : {ROOT}")
    print(f"python    : {platform.python_version()} ({sys.platform})")
    print(f"executable: {sys.executable}")
    for module in ("numpy", "PIL", "cv2", "cairosvg"):
        try:
            loaded = importlib.import_module(module)
            print(f"{module:<10}: {getattr(loaded, '__version__', 'unknown')}")
        except Exception as exc:  # noqa: BLE001
            print(f"{module:<10}: unavailable ({exc.__class__.__name__})")

    from renderer import has_raster_backend
    backend = "available" if has_raster_backend() else "unavailable (native cairo missing)"
    print(f"png raster: {backend}")

    print("fixtures  :")
    for name in ("scene.json", "output.svg", "metrics.txt",
                 "renderer_graph_preview.svg", "renderer_scene_preview.svg",
                 "renderer_lineart_preview.svg"):
        path = OUTPUTS / name
        if path.exists():
            print(f"  {name:<32} {path.stat().st_size} bytes")
        else:
            print(f"  {name:<32} MISSING")

    if shutil.which("git"):
        status = subprocess.run(["git", "status", "--short"], cwd=str(ROOT),
                                capture_output=True, text=True)
        print("git status:")
        print(status.stdout.rstrip() or "  (clean)")
        log = subprocess.run(["git", "log", "--oneline", "-5"], cwd=str(ROOT),
                             capture_output=True, text=True)
        print("recent commits:")
        for line in log.stdout.splitlines():
            print(f"  {line}")
    return 0


# -- parser -----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lissara",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    graph = sub.add_parser("graph", help="render a mathematical graph preview")
    graph.add_argument("--output", default=str(GRAPH_PREVIEW.relative_to(ROOT)))
    graph.add_argument("--width", type=float, default=640.0)
    graph.add_argument("--height", type=float, default=480.0)
    graph.add_argument("--margin", type=float, default=48.0)
    graph.add_argument("--tick-target", type=int, default=10)
    graph.add_argument("--no-grid", action="store_true")
    graph.add_argument("--no-axes", action="store_true")
    graph.add_argument("--no-ticks", action="store_true")
    graph.add_argument("--no-labels", action="store_true")
    graph.set_defaults(func=cmd_graph)

    scene = sub.add_parser("scene", help="render an exact scene SVG")
    scene.add_argument("--input", default=str(SCENE_JSON.relative_to(ROOT)))
    scene.add_argument("--output", default=None)
    scene.set_defaults(func=cmd_scene)

    lineart = sub.add_parser("lineart", help="render a line-art SVG preview")
    lineart.add_argument("--input", default=str(SCENE_JSON.relative_to(ROOT)))
    lineart.add_argument("--output", default=None)
    lineart.add_argument("--lineart-color", default="#111111")
    lineart.add_argument("--lineart-width", type=float, default=1.0)
    lineart.set_defaults(func=cmd_lineart)

    previews = sub.add_parser("previews",
                              help="generate all renderer validation previews")
    previews.add_argument("--yes", action="store_true",
                          help="overwrite existing preview artifacts")
    previews.set_defaults(func=cmd_previews)

    pipeline = sub.add_parser("pipeline",
                              help="run the pure-Python raster-to-SVG pipeline")
    pipeline.add_argument("--yes", action="store_true",
                          help="allow overwriting committed outputs/ files")
    pipeline.set_defaults(func=cmd_pipeline)

    reconstruct = sub.add_parser(
        "reconstruct",
        help="run the full image-to-equations-to-rendering reconstruction")
    reconstruct.add_argument("--input", default=str(Path("INPUT") / "image.png"))
    reconstruct.add_argument("--output-dir",
                             default=str(Path("outputs") / "generated"))
    reconstruct.add_argument("--canny-low", type=int, default=50)
    reconstruct.add_argument("--canny-high", type=int, default=150)
    reconstruct.add_argument("--aperture-size", type=int, choices=(3, 5, 7), default=3)
    reconstruct.add_argument("--blur-sigma", type=float, default=0.0)
    reconstruct.add_argument("--gap-close", type=int, default=0)
    reconstruct.add_argument("--gap-tolerance", type=int, default=1)
    reconstruct.add_argument("--min-length", type=float, default=4.0)
    reconstruct.add_argument("--frame-margin", type=int, default=2)
    reconstruct.add_argument("--fit-tolerance", type=float, default=1.5)
    reconstruct.add_argument("--max-segments", type=int, default=24)
    reconstruct.add_argument("--stroke-width", type=float, default=1.25)
    reconstruct.add_argument("--no-png", action="store_true",
                             help="skip PNG rasterization even if a backend is available")
    reconstruct.add_argument("--force", "--yes", dest="force", action="store_true",
                             help="overwrite existing artifacts in the output directory")
    reconstruct.set_defaults(func=cmd_reconstruct)

    test = sub.add_parser("test", help="run the test suite")
    test.add_argument("--path", default="tests")
    test.add_argument("pytest_args", nargs=argparse.REMAINDER)
    test.set_defaults(func=cmd_test)

    check = sub.add_parser("check", help="validate committed fixtures")
    check.set_defaults(func=cmd_check)

    status = sub.add_parser("status", help="report environment and repo state")
    status.set_defaults(func=cmd_status)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
