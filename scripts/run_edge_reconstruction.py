"""Reconstruct line art from classical Canny edges as parametric cubic Béziers.

This script is the primary classical line-art reconstruction in Lissara. It runs
the complete end-to-end workflow:

    raster image
      -> grayscale + Canny edge detection
      -> ordered contour tracing with tangent-aligned gap bridging
      -> noise / frame-artifact filtering
      -> adaptive cubic Bézier fitting
      -> MathScene (width, height, per-path cubic segments, styles)
      -> a parametric equation report (x(t), y(t) per segment)
      -> SVG rendering (line-art, scene, graph) and metrics

Produced artifacts (inside the chosen ``--output-dir``):

* ``scene.json``     - the full machine-readable MathScene.
* ``equations.json`` - per-segment parametric equations, coefficients and
  control points.
* ``equations.txt``  - human-readable equation listing.
* ``lineart.svg``    - the primary line-art SVG (cubic ``C`` commands,
  stroke-only, opaque white background).
* ``scene.svg``      - scene-mode SVG honouring the stored path styles.
* ``graph.svg``      - the curve collection plotted through the graphing engine
  in image space (no axes/grid, y down).
* ``edges.png``      - the Canny edge map (OpenCV, no cairo required).
* ``metrics.txt``    - human-readable metrics.
* ``metrics.json``   - machine-readable metrics.

SVG output is dependency-free. PNG rasterization via CairoSVG is **optional**:
it needs the native ``cairo`` shared library. When that library is unavailable,
edge extraction, Bézier fitting, MathScene creation, equation export and SVG
rendering all still succeed; only ``reconstructed.png`` / ``comparison.png`` and
the raster-based agreement metrics are skipped and reported as not computed.
Nothing is silently invented.

The public entry point is :func:`run_reconstruction`; :func:`main` is a thin
CLI wrapper so the unified ``main.py`` can delegate to the same implementation.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
import xml.etree.ElementTree as ET

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lissara_equations import evaluate_bezier, evaluate_de_casteljau
from lissara_engine import MathScene, PathRecord
from lissara_vectorization import fit_bezier_adaptive
from lissara_vectorization.edge_tracing import (
    detect_classical_edges,
    filter_edge_paths,
    trace_edge_paths,
)
from renderer import (
    SceneRenderConfig,
    has_raster_backend,
    render_scene_svg,
    scene_to_graph,
    svg_to_png,
)

SVG_NS = "{http://www.w3.org/2000/svg}"
STROKE_COLOR = "#17151b"
CONTINUITY_EPS = 1e-9
EVAL_TOLERANCE = 1e-6

# Files written for every run (independent of the raster backend).
CORE_OUTPUT_FILES = (
    "scene.json",
    "equations.json",
    "equations.txt",
    "lineart.svg",
    "scene.svg",
    "graph.svg",
    "edges.png",
    "metrics.txt",
    "metrics.json",
)
# Extra files written only when a PNG raster backend is available.
RASTER_OUTPUT_FILES = ("reconstructed.png", "comparison.png")


class OutputExistsError(RuntimeError):
    """Raised when the output directory would be overwritten without ``force``."""


# -- helpers ----------------------------------------------------------------

def _format_number(value: float) -> str:
    """Format a coefficient compactly but without losing significant digits."""
    number = float(value)
    if number == 0.0:
        return "0"
    text = f"{number:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _poly_expression(var: str, coeffs: dict, keys) -> str:
    """Render ``var(t) = a3*t^3 + a2*t^2 + a1*t + a0`` with numbers.

    Uses the same coefficient keys as the canonical Lissara record
    (``a3/a2/a1/a0`` for x, ``b3/b2/b1/b0`` for y).
    """
    terms = [
        ("t^3", coeffs[keys[0]]),
        ("t^2", coeffs[keys[1]]),
        ("t", coeffs[keys[2]]),
        ("", coeffs[keys[3]]),
    ]
    parts = []
    for power, coeff in terms:
        magnitude = _format_number(abs(float(coeff)))
        body = f"{magnitude}*{power}" if power else magnitude
        parts.append((body, float(coeff) < 0.0))
    expression = f"{var}(t) = "
    for index, (body, negative) in enumerate(parts):
        if index == 0:
            expression += f"-{body}" if negative else body
        else:
            expression += f" {'-' if negative else '+'} {body}"
    return expression


def _svg_stats(svg_text: str):
    """Return ``(path_count, cubic_command_count)`` for an SVG document string."""
    root = ET.fromstring(svg_text)
    paths = root.findall(SVG_NS + "path")
    cubics = 0
    for element in paths:
        d = element.get("d") or ""
        cubics += sum(1 for token in d.split() if token == "C")
    return len(paths), cubics


def edge_metrics(source_edges, reconstructed):
    """Rendered-vs-reference agreement metrics (require a raster backend)."""
    output_gray = cv2.cvtColor(reconstructed, cv2.COLOR_RGB2GRAY)
    output_mask = (output_gray < 220).astype(np.uint8)
    source_mask = (source_edges > 0).astype(np.uint8)
    source_count, output_count = int(source_mask.sum()), int(output_mask.sum())
    if not source_count or not output_count:
        return output_mask, 0.0, 0.0, 0.0, float("inf"), float("inf")
    source_distance = cv2.distanceTransform(1 - source_mask, cv2.DIST_L2, 3)
    output_distance = cv2.distanceTransform(1 - output_mask, cv2.DIST_L2, 3)
    tolerance = 2.0
    precision = float((source_distance[output_mask > 0] <= tolerance).mean())
    recall = float((output_distance[source_mask > 0] <= tolerance).mean())
    f1 = (2 * precision * recall / (precision + recall)
          if precision + recall else 0.0)
    chamfer_out_to_source = float(source_distance[output_mask > 0].mean())
    chamfer_source_to_out = float(output_distance[source_mask > 0].mean())
    return (output_mask, precision, recall, f1, chamfer_out_to_source,
            chamfer_source_to_out)


def validate_paths(paths, width, height):
    """Check finiteness, canvas bounds, continuity and closure of every path."""
    for path in paths:
        segments = path.segments or []
        if not segments:
            raise ValueError(f"empty fitted path: {path.path_id}")
        points = [point for segment in segments for point in segment["control_points"]]
        for x, y in points:
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ValueError(f"non-finite coordinate in {path.path_id}: {(x, y)}")
            if not (0 <= x <= width - 1 and 0 <= y <= height - 1):
                raise ValueError(f"path coordinate outside canvas: {path.path_id} {(x, y)}")
        for left, right in zip(segments, segments[1:]):
            if left["control_points"][3] != right["control_points"][0]:
                raise ValueError(f"discontinuous segments in {path.path_id}")
        if path.closed and segments[-1]["control_points"][3] != segments[0]["control_points"][0]:
            raise ValueError(f"closed path does not close: {path.path_id}")


def build_equations(scene, metadata):
    """Build the machine-readable per-segment equation report for a scene."""
    paths_out = []
    total_segments = 0
    for path in scene.paths:
        segments = path.segments or []
        segments_out = []
        for index, segment in enumerate(segments):
            control_points = [[float(x), float(y)] for x, y in segment["control_points"]]
            x_coeffs = {key: float(value) for key, value in segment["x_coeffs"].items()}
            y_coeffs = {key: float(value) for key, value in segment["y_coeffs"].items()}
            continuous = None
            if index > 0:
                previous = segments[index - 1]["control_points"][3]
                continuous = (
                    abs(control_points[0][0] - float(previous[0])) <= CONTINUITY_EPS
                    and abs(control_points[0][1] - float(previous[1])) <= CONTINUITY_EPS
                )
            segments_out.append({
                "index": index,
                "domain": [0.0, 1.0],
                "control_points": control_points,
                "x_coeffs": x_coeffs,
                "y_coeffs": y_coeffs,
                "x_expression": _poly_expression("x", x_coeffs, ("a3", "a2", "a1", "a0")),
                "y_expression": _poly_expression("y", y_coeffs, ("b3", "b2", "b1", "b0")),
                "continuous_with_previous": continuous,
            })
            total_segments += 1
        closed_loop_continuous = None
        if path.closed and segments:
            first_start = segments[0]["control_points"][0]
            last_end = segments[-1]["control_points"][3]
            closed_loop_continuous = (
                abs(float(last_end[0]) - float(first_start[0])) <= CONTINUITY_EPS
                and abs(float(last_end[1]) - float(first_start[1])) <= CONTINUITY_EPS
            )
        paths_out.append({
            "path_id": path.path_id,
            "path_type": path.path_type,
            "closed": bool(path.closed),
            "closed_loop_continuous": closed_loop_continuous,
            "segment_count": len(segments_out),
            "segments": segments_out,
        })
    return {
        "metadata": metadata,
        "path_count": len(paths_out),
        "segment_count": total_segments,
        "paths": paths_out,
    }


def write_equations_txt(path: Path, equations) -> None:
    """Write the human-readable equation listing."""
    lines = [
        "Lissara reconstructed cubic Bezier equations",
        f"Paths: {equations['path_count']}    Segments: {equations['segment_count']}",
        "",
    ]
    for path_data in equations["paths"]:
        lines.append(f"Path: {path_data['path_id']}")
        lines.append(f"Closed: {path_data['closed']}")
        lines.append(f"Segments: {path_data['segment_count']}")
        lines.append("")
        for segment in path_data["segments"]:
            lines.append(f"Segment: {segment['index']}")
            lines.append(f"Domain: {segment['domain'][0]:g} <= t <= {segment['domain'][1]:g}")
            lines.append("Control points:")
            for index, (x, y) in enumerate(segment["control_points"]):
                lines.append(f"  P{index} = ({x:g}, {y:g})")
            lines.append(segment["x_expression"])
            lines.append(segment["y_expression"])
            lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify_equations(scene, equations):
    """Cross-check the equation report against the scene.

    * path/segment counts agree between the scene, the report and its own JSON;
    * selected equations are evaluated at ``t = 0, 0.5, 1`` from the *report's*
      coefficients and from an independent de Casteljau evaluation of the
      report's control points;
    * each segment's endpoints match ``P0`` and ``P3``.
    """
    scene_segment_count = sum(len(path.segments or []) for path in scene.paths)
    report_segment_count = sum(len(path["segments"]) for path in equations["paths"])
    counts_match = (
        scene_segment_count == equations["segment_count"] == report_segment_count
        and len(scene.paths) == equations["path_count"] == len(equations["paths"])
    )

    evaluations_checked = 0
    max_error = 0.0
    for scene_path, path_data in zip(scene.paths, equations["paths"]):
        segments = scene_path.segments or []
        if not segments:
            continue
        indices = sorted({0, len(segments) - 1})
        for index in indices:
            entry = path_data["segments"][index]
            record = {"x_coeffs": entry["x_coeffs"], "y_coeffs": entry["y_coeffs"]}
            control_points = entry["control_points"]
            for t in (0.0, 0.5, 1.0):
                coefficient_point = evaluate_bezier(t, record)
                de_casteljau_point = evaluate_de_casteljau(
                    t, {"control_points": control_points})
                max_error = max(
                    max_error,
                    abs(coefficient_point[0] - de_casteljau_point[0]),
                    abs(coefficient_point[1] - de_casteljau_point[1]),
                )
                evaluations_checked += 1
            for t, endpoint in ((0.0, control_points[0]), (1.0, control_points[3])):
                evaluated = evaluate_bezier(t, record)
                max_error = max(
                    max_error,
                    abs(evaluated[0] - endpoint[0]),
                    abs(evaluated[1] - endpoint[1]),
                )

    ok = counts_match and max_error <= EVAL_TOLERANCE
    return {
        "counts_match": counts_match,
        "evaluations_checked": evaluations_checked,
        "max_endpoint_and_evaluation_error": max_error,
        "tolerance": EVAL_TOLERANCE,
        "ok": ok,
    }


def _validate_params(*, canny_low, canny_high, aperture_size, blur_sigma,
                     gap_close, gap_tolerance, min_length, frame_margin,
                     fit_tolerance, max_segments, stroke_width) -> None:
    if not (0 <= canny_low < canny_high):
        raise ValueError("Canny thresholds must satisfy 0 <= low < high")
    if aperture_size not in (3, 5, 7):
        raise ValueError("aperture-size must be one of 3, 5, 7")
    if blur_sigma < 0:
        raise ValueError("blur-sigma must be >= 0")
    if gap_close < 0:
        raise ValueError("gap-close must be >= 0")
    if gap_tolerance < 0:
        raise ValueError("gap-tolerance must be >= 0")
    if min_length <= 0:
        raise ValueError("min-length must be > 0")
    if frame_margin < 0:
        raise ValueError("frame-margin must be >= 0")
    if fit_tolerance <= 0:
        raise ValueError("fit-tolerance must be > 0")
    if max_segments < 2:
        raise ValueError("max-segments must be >= 2")
    if stroke_width <= 0:
        raise ValueError("stroke-width must be > 0")


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


# -- workflow ---------------------------------------------------------------

def run_reconstruction(
    input_path,
    output_dir,
    *,
    canny_low: int = 50,
    canny_high: int = 150,
    aperture_size: int = 3,
    blur_sigma: float = 0.0,
    gap_close: int = 0,
    gap_tolerance: int = 1,
    min_length: float = 4.0,
    frame_margin: int = 2,
    fit_tolerance: float = 1.5,
    max_segments: int = 24,
    stroke_width: float = 1.25,
    force: bool = False,
    write_png=None,
):
    """Run the full image-to-equations-to-rendering reconstruction.

    Args:
        input_path: Path to the input raster image.
        output_dir: Directory to write artifacts into (created if missing).
        force: Allow overwriting existing artifacts in ``output_dir``.
        write_png: ``None`` (auto: attempt when the raster backend is available),
            ``True`` (attempt and warn if unavailable) or ``False`` (skip).

    Returns:
        A summary dict (written to ``metrics.json`` and printed by the CLI).
    """
    _validate_params(
        canny_low=canny_low, canny_high=canny_high, aperture_size=aperture_size,
        blur_sigma=blur_sigma, gap_close=gap_close, gap_tolerance=gap_tolerance,
        min_length=min_length, frame_margin=frame_margin,
        fit_tolerance=fit_tolerance, max_segments=max_segments,
        stroke_width=stroke_width,
    )

    input_path = Path(input_path)
    if not input_path.is_absolute():
        input_path = ROOT / input_path
    if not input_path.exists():
        raise FileNotFoundError(f"input image not found: {input_path}")

    output_dir = Path(output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    raster_available = has_raster_backend()
    if write_png is None:
        write_png = raster_available
    planned = list(CORE_OUTPUT_FILES)
    if write_png and raster_available:
        planned += list(RASTER_OUTPUT_FILES)
    existing = [name for name in planned if (output_dir / name).exists()]
    if existing and not force:
        raise OutputExistsError(
            "output directory already contains reconstruction artifacts: "
            + ", ".join(existing) + ". Re-run with --force to overwrite."
        )

    started = time.perf_counter()

    # 1. Load and validate the image, convert to grayscale.
    source = np.asarray(Image.open(input_path).convert("RGB"))
    height, width = source.shape[:2]
    gray = cv2.cvtColor(source, cv2.COLOR_RGB2GRAY)

    # 2. Canny edge detection.
    edges = detect_classical_edges(
        gray, canny_low, canny_high, aperture_size, blur_sigma, gap_close,
    )
    Image.fromarray(edges, "L").save(output_dir / "edges.png")

    # 3. Ordered contour tracing with gap bridging; 4. noise/frame filtering.
    traced = trace_edge_paths(edges, gap_tolerance=gap_tolerance)
    accepted = filter_edge_paths(traced, width, height, min_length, frame_margin)

    # 5. Adaptive cubic Bézier fitting into a MathScene.
    metadata = {
        "source": _relative(input_path),
        "representation": "classical Canny contours fitted as independent cubic Bezier strokes",
        "background": "#ffffff",
        "stroke_color": STROKE_COLOR,
        "stroke_width": stroke_width,
        "canny_low": canny_low,
        "canny_high": canny_high,
        "canny_aperture_size": aperture_size,
        "blur_sigma": blur_sigma,
        "gap_close": gap_close,
        "gap_tolerance": gap_tolerance,
        "min_path_length": min_length,
        "frame_margin": frame_margin,
        "fit_tolerance": fit_tolerance,
        "max_segments_per_path": max_segments,
    }
    scene = MathScene(width=width, height=height, metadata=metadata)

    segment_count = 0
    open_count = closed_count = 0
    paths_at_segment_limit = 0
    for index, contour in enumerate(accepted):
        points = contour["points"]
        if contour["closed"] and points[-1] != points[0]:
            points = points + [points[0]]
        segments = fit_bezier_adaptive(
            points, tolerance=fit_tolerance,
            max_segments=max_segments, max_depth=8,
        )
        if not segments:
            continue
        closed = bool(contour["closed"])
        scene.add_path(PathRecord(
            path_id=f"edge-path-{index:05d}",
            path_type="line-art-contour",
            closed=closed,
            segments=segments,
            fill={"color": "none", "opacity": 0},
            stroke={"color": STROKE_COLOR, "width": stroke_width, "opacity": 1},
        ))
        segment_count += len(segments)
        if len(segments) >= max_segments:
            paths_at_segment_limit += 1
        if closed:
            closed_count += 1
        else:
            open_count += 1

    # 10. Validate the scene geometry.
    validate_paths(scene.paths, width, height)

    # 6. Serialize the scene.
    scene_json = scene.to_json()
    (output_dir / "scene.json").write_text(
        json.dumps(scene_json, indent=2), encoding="utf-8")

    # 4/7. Export equations and verify them.
    equations = build_equations(scene, metadata)
    (output_dir / "equations.json").write_text(
        json.dumps(equations, indent=2), encoding="utf-8")
    write_equations_txt(output_dir / "equations.txt", equations)
    # Round-trip the JSON so the report is proven parseable.
    reparsed = json.loads((output_dir / "equations.json").read_text(encoding="utf-8"))
    if reparsed["segment_count"] != equations["segment_count"]:
        raise ValueError("equations.json did not round-trip")
    equation_validation = verify_equations(scene, equations)
    if not equation_validation["ok"]:
        raise ValueError(f"equation verification failed: {equation_validation}")

    # 5. Render the scene through the graphing engine.
    lineart_svg = render_scene_svg(scene, config=SceneRenderConfig(
        mode="lineart", lineart_color=STROKE_COLOR,
        lineart_width=stroke_width, background="#ffffff"))
    (output_dir / "lineart.svg").write_text(lineart_svg, encoding="utf-8")
    scene_svg = render_scene_svg(scene, config=SceneRenderConfig(
        mode="scene", background="#ffffff"))
    (output_dir / "scene.svg").write_text(scene_svg, encoding="utf-8")
    graph_svg = scene_to_graph(scene).render_svg()
    (output_dir / "graph.svg").write_text(graph_svg, encoding="utf-8")

    lineart_paths, lineart_cubics = _svg_stats(lineart_svg)
    scene_paths, scene_cubics = _svg_stats(scene_svg)
    graph_paths, graph_cubics = _svg_stats(graph_svg)

    # Optional rasterization + raster-based agreement metrics.
    png_written = False
    reconstruction_metrics = None
    raster_note = None
    if not raster_available:
        raster_note = ("PNG raster backend unavailable (native cairo missing): "
                       "reconstructed.png, comparison.png and raster-based "
                       "agreement metrics were not computed. SVG artifacts are complete.")
    elif write_png:
        png_bytes = svg_to_png(lineart_svg, width=width, height=height)
        (output_dir / "reconstructed.png").write_bytes(png_bytes)
        with Image.open(output_dir / "reconstructed.png") as rendered_image:
            if (rendered_image.mode == "RGBA"
                    and rendered_image.getchannel("A").getextrema() != (255, 255)):
                raise ValueError(
                    "SVG render contains transparent pixels despite the white background")
            reconstructed = np.asarray(rendered_image.convert("RGB"))
        Image.fromarray(np.concatenate((source, reconstructed), axis=1), "RGB").save(
            output_dir / "comparison.png")
        (rendered_mask, precision, recall, f1, chamfer_pr, chamfer_rp) = edge_metrics(
            edges, reconstructed)
        line_mae = float(np.mean(np.abs((edges > 0).astype(np.float32) - rendered_mask)))
        reconstruction_metrics = {
            "kind": "rendered-vs-Canny-reference agreement (not ground-truth fidelity)",
            "line_map_mae": line_mae,
            "edge_precision_2px": precision,
            "edge_recall_2px": recall,
            "edge_f1_2px": f1,
            "mean_distance_rendered_to_source_px": chamfer_pr,
            "mean_distance_source_to_rendered_px": chamfer_rp,
        }
        png_written = True
    else:
        raster_note = "PNG rasterization disabled by request; raster metrics not computed."

    runtime_seconds = time.perf_counter() - started

    # 8. Metrics.
    points_in_paths = sum(len(path["points"]) for path in accepted)
    metrics = {
        "input": {
            "path": _relative(input_path),
            "width": width,
            "height": height,
        },
        "edge_detection": {
            "canny_low": canny_low,
            "canny_high": canny_high,
            "aperture_size": aperture_size,
            "blur_sigma": blur_sigma,
            "gap_close": gap_close,
            "source_edge_pixels": int(np.count_nonzero(edges)),
        },
        "contours": {
            "traced": len(traced),
            "accepted": len(scene.paths),
            "open": open_count,
            "closed": closed_count,
            "accepted_pixels": points_in_paths,
            "gap_tolerance": gap_tolerance,
            "min_length": min_length,
            "frame_margin": frame_margin,
        },
        "fitting": {
            "fit_tolerance": fit_tolerance,
            "max_segments_per_path": max_segments,
            "segments": segment_count,
            "paths_at_segment_limit": paths_at_segment_limit,
        },
        "equations": {
            "path_count": equations["path_count"],
            "segment_count": equations["segment_count"],
            "evaluations_checked": equation_validation["evaluations_checked"],
            "validation": equation_validation,
        },
        "svg": {
            "lineart.svg": {"paths": lineart_paths, "cubic_commands": lineart_cubics},
            "scene.svg": {"paths": scene_paths, "cubic_commands": scene_cubics},
            "graph.svg": {"paths": graph_paths, "cubic_commands": graph_cubics},
        },
        "raster": {
            "backend_available": raster_available,
            "png_written": png_written,
            "note": raster_note,
        },
        "reconstruction_metrics": reconstruction_metrics,
        "runtime_seconds": runtime_seconds,
        "environment": {
            "python": sys.version.split()[0],
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "pillow": Image.__version__,
        },
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8")

    metrics_txt = [
        f"Input: {metrics['input']['path']} ({width}x{height})",
        f"Runtime seconds: {runtime_seconds:.3f}",
        f"Canny parameters: low={canny_low}, high={canny_high}, aperture={aperture_size}, blur_sigma={blur_sigma}",
        f"Gap closing iterations: {gap_close}",
        f"Tangent-aligned gap bridge tolerance: {gap_tolerance}px",
        f"Contour paths traced: {len(traced)}",
        f"Accepted paths: {len(scene.paths)} (open={open_count}, closed={closed_count})",
        f"Accepted contour pixels: {points_in_paths}",
        f"Adaptive Bezier segments (equations): {segment_count}",
        f"Paths that reached max_segments={max_segments}: {paths_at_segment_limit}",
        f"Filtering: min_length={min_length}, frame_margin={frame_margin}px",
        f"Fitting: tolerance={fit_tolerance}px, max_segments={max_segments}",
        f"Source edge pixels: {int(np.count_nonzero(edges))}",
        f"Line-art SVG: {lineart_paths} paths, {lineart_cubics} cubic C commands",
        f"Scene SVG: {scene_paths} paths, {scene_cubics} cubic C commands",
        f"Graph SVG: {graph_paths} paths, {graph_cubics} cubic C commands",
        f"Equation verification: counts_match={equation_validation['counts_match']}, "
        f"evaluations_checked={equation_validation['evaluations_checked']}, "
        f"max_error={equation_validation['max_endpoint_and_evaluation_error']:.3e}",
        "SVG paths use cubic C commands, stroke only, and an opaque white background.",
        "Path endpoints, segment continuity, closure, and control-point canvas bounds validated.",
        f"PNG raster backend: {'available' if raster_available else 'unavailable (native cairo missing)'}",
    ]
    if reconstruction_metrics is not None:
        metrics_txt.extend([
            f"Line-map MAE: {reconstruction_metrics['line_map_mae']:.6f}",
            f"Edge precision (2px tolerance): {reconstruction_metrics['edge_precision_2px']:.6f}",
            f"Edge recall (2px tolerance): {reconstruction_metrics['edge_recall_2px']:.6f}",
            f"Edge F1 (2px tolerance): {reconstruction_metrics['edge_f1_2px']:.6f}",
            f"Mean distance rendered-to-source (px): {reconstruction_metrics['mean_distance_rendered_to_source_px']:.4f}",
            f"Mean distance source-to-rendered (px): {reconstruction_metrics['mean_distance_source_to_rendered_px']:.4f}",
        ])
    else:
        metrics_txt.append(f"Raster metrics: not computed ({raster_note})")
    metrics_txt.append(
        f"Environment: Python {sys.version.split()[0]}, OpenCV {cv2.__version__}, "
        f"NumPy {np.__version__}, Pillow {Image.__version__}")
    (output_dir / "metrics.txt").write_text(
        "\n".join(metrics_txt) + "\n", encoding="utf-8")

    # 7/10. Validate every written artifact.
    for name in ("lineart.svg", "scene.svg", "graph.svg"):
        ET.parse(output_dir / name)
    with Image.open(output_dir / "edges.png") as edge_image:
        edge_image.verify()
    if lineart_cubics != segment_count:
        raise ValueError(
            f"lineart.svg has {lineart_cubics} C commands but the scene has "
            f"{segment_count} segments")
    if scene_cubics != segment_count:
        raise ValueError(
            f"scene.svg has {scene_cubics} C commands but the scene has "
            f"{segment_count} segments")

    summary = {
        "input": _relative(input_path),
        "output_dir": _relative(output_dir),
        "traced_paths": len(traced),
        "accepted_paths": len(scene.paths),
        "open_paths": open_count,
        "closed_paths": closed_count,
        "segments": segment_count,
        "equations": equations["segment_count"],
        "lineart_paths": lineart_paths,
        "lineart_cubics": lineart_cubics,
        "png_written": png_written,
        "runtime_seconds": runtime_seconds,
        "artifacts": planned,
        "metrics": metrics,
    }
    return summary


# -- CLI --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default=str(ROOT / "INPUT" / "image.png"))
    parser.add_argument("--output-dir", default=str(ROOT / "outputs" / "generated"))
    parser.add_argument("--canny-low", type=int, default=50)
    parser.add_argument("--canny-high", type=int, default=150)
    parser.add_argument("--aperture-size", type=int, choices=(3, 5, 7), default=3)
    parser.add_argument("--blur-sigma", type=float, default=0.0)
    parser.add_argument("--gap-close", type=int, default=0,
                        help="3x3 cross closing iterations; 0 preserves exact Canny pixels")
    parser.add_argument("--gap-tolerance", type=int, default=1,
                        help="join aligned disconnected stroke ends across this many pixels")
    parser.add_argument("--min-length", type=float, default=4.0)
    parser.add_argument("--frame-margin", type=int, default=2)
    parser.add_argument("--fit-tolerance", type=float, default=1.5)
    parser.add_argument("--max-segments", type=int, default=24)
    parser.add_argument("--stroke-width", type=float, default=1.25)
    parser.add_argument("--force", action="store_true",
                        help="overwrite existing artifacts in the output directory")
    parser.add_argument("--no-png", action="store_true",
                        help="skip PNG rasterization even when a backend is available")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_reconstruction(
            args.input, args.output_dir,
            canny_low=args.canny_low, canny_high=args.canny_high,
            aperture_size=args.aperture_size, blur_sigma=args.blur_sigma,
            gap_close=args.gap_close, gap_tolerance=args.gap_tolerance,
            min_length=args.min_length, frame_margin=args.frame_margin,
            fit_tolerance=args.fit_tolerance, max_segments=args.max_segments,
            stroke_width=args.stroke_width, force=args.force,
            write_png=False if args.no_png else None,
        )
    except (ValueError, FileNotFoundError, OutputExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2 if isinstance(exc, OutputExistsError) else 1

    metrics = summary["metrics"]
    print(f"Input: {summary['input']}")
    print(f"Output dir: {summary['output_dir']}")
    print(f"Traced paths: {summary['traced_paths']}")
    print(f"Accepted paths: {summary['accepted_paths']} "
          f"(open={summary['open_paths']}, closed={summary['closed_paths']})")
    print(f"Fitted segments / equations: {summary['segments']}")
    print(f"lineart.svg: {summary['lineart_paths']} paths, "
          f"{summary['lineart_cubics']} cubic commands")
    print(f"PNG written: {summary['png_written']}")
    print(f"Raster note: {metrics['raster']['note']}")
    print(f"Artifacts: {', '.join(summary['artifacts'])}")
    print(f"Runtime seconds: {summary['runtime_seconds']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
