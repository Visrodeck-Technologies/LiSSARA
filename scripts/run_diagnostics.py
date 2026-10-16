"""Build a classical, model-ready vectorization diagnostic for INPUT/image.png."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import cairosvg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lissara_equations import evaluate_bezier
from lissara_engine import MathScene, PathRecord
from lissara_vectorization import fit_bezier_adaptive


def save_rgb(path: Path, pixels):
    Image.fromarray(np.asarray(pixels, dtype=np.uint8), "RGB").save(path)


def make_regions(rgb, clusters=8, max_side=512, line_mask=None):
    h, w = rgb.shape[:2]
    scale = max_side / max(h, w)
    small = cv2.resize(rgb, (max(1, round(w * scale)), max(1, round(h * scale))),
                       interpolation=cv2.INTER_AREA)
    samples = small.reshape((-1, 3)).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 35, 0.6)
    _, labels, centers = cv2.kmeans(samples, clusters, None, criteria, 2,
                                    cv2.KMEANS_PP_CENTERS)
    labels = labels.reshape(small.shape[:2])
    if line_mask is not None:
        line_small = cv2.resize(line_mask.astype(np.float32), (small.shape[1], small.shape[0]),
                                interpolation=cv2.INTER_AREA) >= 0.25
        labels[line_small] = -1
    return small, labels, centers


def edge_f1(source_edges, rendered_edges, tolerance=2):
    src = source_edges > 0
    dst = rendered_edges > 0
    if not src.any() or not dst.any():
        return 0.0, 0.0, 0.0
    src_distance = cv2.distanceTransform((~src).astype(np.uint8), cv2.DIST_L2, 3)
    dst_distance = cv2.distanceTransform((~dst).astype(np.uint8), cv2.DIST_L2, 3)
    precision = float(np.mean(src[dst_distance <= tolerance]))
    recall = float(np.mean(dst[src_distance <= tolerance]))
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", help="authorized Anime2Sketch checkpoint file")
    parser.add_argument("--anime2sketch-repo", help="official Anime2Sketch source checkout")
    parser.add_argument("--line-threshold", type=float, default=0.5,
                        help="dark-stroke confidence threshold in [0,1]")
    args = parser.parse_args()
    if not 0.0 <= args.line_threshold <= 1.0:
        parser.error("--line-threshold must be between 0 and 1")
    start_time = time.perf_counter()
    input_path = ROOT / "INPUT" / "image.png"
    out = ROOT / "outputs"
    out.mkdir(exist_ok=True)
    rgb = np.asarray(Image.open(input_path).convert("RGB"))
    h, w = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    save_rgb(out / "classical_edges.png", np.repeat(edges[:, :, None], 3, axis=2))

    model_confidence = None
    model_line_mask = None
    if args.checkpoint:
        from lissara_vectorization.anime2sketch import Anime2SketchBackend
        model_confidence = Anime2SketchBackend(
            args.checkpoint, source_repo=args.anime2sketch_repo
        ).extract(rgb)
        model_line_mask = model_confidence >= args.line_threshold
        raw = np.clip((1.0 - model_confidence) * 255.0, 0, 255).astype(np.uint8)
        Image.fromarray(raw, "L").save(out / "lineart_model.png")
        Image.fromarray((model_line_mask * 255).astype(np.uint8), "L").save(out / "lineart_mask.png")
    small, labels, centers = make_regions(rgb, line_mask=model_line_mask)
    sh, sw = labels.shape
    scale_x, scale_y = w / sw, h / sh
    proposal = np.clip(centers[np.maximum(labels, 0)].reshape(sh, sw, 3), 0, 255).astype(np.uint8)
    if model_line_mask is not None:
        proposal[labels == -1] = small[labels == -1]
    proposal_full = cv2.resize(proposal, (w, h), interpolation=cv2.INTER_NEAREST)
    contour_overlay = rgb.copy()
    cv2.addWeighted(proposal_full, 0.2, contour_overlay, 0.8, 0, contour_overlay)
    scene = MathScene(width=w, height=h, metadata={
        "source": str(input_path.relative_to(ROOT)).replace("\\", "/"),
        "method": "classical color clustering, external contours, adaptive cubic Bezier fitting",
        "pretrained_lineart": "used" if model_confidence is not None else "not_run",
    })
    curve_overlay = rgb.copy()
    component_count = 0
    segment_count = 0
    path_count = 0
    max_components_per_region = 18

    for cluster_id, center in enumerate(centers):
        mask = (labels == cluster_id).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = list(contours)
        contours.sort(key=cv2.contourArea, reverse=True)
        color = "#{:02x}{:02x}{:02x}".format(*np.clip(center, 0, 255).astype(int))
        for contour in contours[:max_components_per_region]:
            area = cv2.contourArea(contour)
            if area < 20:
                continue
            component_count += 1
            approx = cv2.approxPolyDP(contour, 1.1, True).reshape(-1, 2)
            if len(approx) < 3:
                continue
            points = [(float(x) * scale_x, float(y) * scale_y) for x, y in approx]
            points.append(points[0])
            segments = fit_bezier_adaptive(
                points, tolerance=2.0, max_segments=16, max_depth=5
            )
            if not segments:
                continue
            path_id = f"region-{cluster_id}-component-{path_count}"
            scene.add_path(PathRecord(
                path_id=path_id,
                path_type="region-contour",
                closed=True,
                segments=segments,
                fill={"color": color, "opacity": 1.0},
                stroke={"color": "none", "width": 0},
            ))
            path_count += 1
            segment_count += len(segments)
            curve = []
            for seg in segments:
                curve.extend([evaluate_bezier(t / 16, seg) for t in range(17)])
            points_cv = np.round(curve).astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(curve_overlay, [points_cv], True, (255, 30, 210), 1,
                          lineType=cv2.LINE_AA)
            cv2.polylines(contour_overlay, [np.round(points).astype(np.int32).reshape(-1, 1, 2)],
                          True, (20, 30, 250), 1, lineType=cv2.LINE_AA)

    # Region proposal diagnostics show the cluster colors with boundary outlines.
    save_rgb(out / "region_proposals.png", contour_overlay)
    # No model output or mask is fabricated when pretrained inference is absent.
    line_overlay = rgb.copy()
    if model_line_mask is not None:
        line_overlay[model_line_mask] = (255, 35, 35)
    else:
        line_overlay[edges > 0] = (255, 35, 35)
    save_rgb(out / "lineart_overlay.png", line_overlay)
    save_rgb(out / "fitted_curves.png", curve_overlay)

    scene_path = out / "scene.json"
    scene_path.write_text(json.dumps(scene.to_json(), indent=2), encoding="utf-8")
    svg_path = out / "output.svg"
    svg_path.write_text(scene.export_svg(), encoding="utf-8")
    rendered = cairosvg.svg2png(bytestring=svg_path.read_bytes(), output_width=w,
                                output_height=h)
    (out / "reconstructed.png").write_bytes(rendered)
    recon = np.asarray(Image.open(out / "reconstructed.png").convert("RGB"))
    recon_gray = cv2.cvtColor(recon, cv2.COLOR_RGB2GRAY)
    recon_edges = cv2.Canny(recon_gray, 50, 150)
    precision, recall, f1 = edge_f1(edges, recon_edges)
    mae = float(np.abs(rgb.astype(np.float32) - recon.astype(np.float32)).mean() / 255.0)
    comparison = np.concatenate((rgb, recon), axis=1)
    save_rgb(out / "comparison.png", comparison)

    metrics = [
        f"Image dimensions: {w}x{h}",
        f"Runtime seconds: {time.perf_counter() - start_time:.3f}",
        f"Python: {sys.version.split()[0]} ({sys.platform}); runtime dependencies: "
        f"OpenCV {cv2.__version__}, NumPy {np.__version__}, Pillow {Image.__version__}, CairoSVG {cairosvg.__version__}",
        "Inference device: CPU (optional PyTorch is not installed)",
        f"Pretrained model: Anime2Sketch {'inference completed' if model_confidence is not None else 'adapter available; inference not run'}",
        "Checkpoint source: official README Google Drive folder (netG.pth / improved.bin)",
        "Checkpoint license: no license or usage terms located; usage/redistribution rights unverified",
        ("Pretrained outputs: lineart_model.png and lineart_mask.png generated from inference"
         if model_confidence is not None else
         "Pretrained outputs: lineart_model.png and lineart_mask.png not generated (no authorized checkpoint)"),
        f"Color clusters: {len(centers)}",
        f"Region components considered: {component_count}",
        f"Fitted MathScene paths: {path_count}",
        f"Adaptive Bezier segments: {segment_count}",
        f"RGB normalized MAE: {mae:.6f}",
        f"Edge precision (2px tolerance): {precision:.6f}",
        f"Edge recall (2px tolerance): {recall:.6f}",
        f"Edge F1 (2px tolerance): {f1:.6f}",
        "Boundary metrics compare the classical color-region reconstruction against source Canny edges.",
        "SVG rasterized by CairoSVG; output reopened as RGB PNG for validation.",
    ]
    (out / "metrics.txt").write_text("\n".join(metrics) + "\n", encoding="utf-8")
    # Verify every generated PNG can be decoded and has expected dimensions.
    for name in ("classical_edges.png", "region_proposals.png", "lineart_overlay.png",
                 "fitted_curves.png", "reconstructed.png", "comparison.png"):
        with Image.open(out / name) as im:
            im.verify()
        with Image.open(out / name) as im:
            expected = (w * 2, h) if name == "comparison.png" else (w, h)
            if im.size != expected:
                raise RuntimeError(f"{name}: got {im.size}, expected {expected}")
    print("\n".join(metrics))
    print("Validated PNGs: classical_edges.png, region_proposals.png, lineart_overlay.png, "
          "fitted_curves.png, reconstructed.png, comparison.png")


if __name__ == "__main__":
    main()
