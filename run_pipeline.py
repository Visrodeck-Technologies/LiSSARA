"""Run the standard-library Lissara raster-to-SVG diagnostic pipeline."""
import json
import os

from lissara_equations import evaluate_bezier
from lissara_vectorization import load_image, write_png, fit_bezier_adaptive
from lissara_engine import MathScene, PathRecord, compute_edge_loss
from core.lissara_core.contours import extract_contours, simplify_contour


def main():
    os.makedirs("outputs", exist_ok=True)
    image = load_image("INPUT/image.png")
    height, width = len(image), len(image[0])
    # Save a real RGB diagnostic PNG from the decoded grayscale input.
    write_png("outputs/input_preview.png", [[(round(v*255),)*3 for v in row] for row in image])

    # Ignore tiny isolated noise; discard image-frame contours and use all
    # remaining meaningful components in descending boundary size.
    contours = extract_contours(image, threshold=0.5, min_area=40, backend="pure")
    contours = [c for c in contours if len(c) >= 4 and
                not any(x <= 0 or y <= 0 or x >= width-1 or y >= height-1 for x, y in c)]
    contours.sort(key=len, reverse=True)
    scene = MathScene(width=width, height=height)
    selected = contours[:100]
    simplified_count = 0
    bezier_segment_count = 0
    for i, contour in enumerate(selected):
        points = simplify_contour(contour, tolerance=2.0, backend="pure")
        if len(points) < 3 or len(set(points)) < 3:
            continue
        # Reject geometrically degenerate paths using their signed area.
        area = abs(sum(points[j][0]*points[(j+1)%len(points)][1] -
                       points[(j+1)%len(points)][0]*points[j][1]
                       for j in range(len(points))) / 2)
        if area < 4:
            continue
        # Fit adaptive cubic Bézier segments to the simplified contour
        bezier_segs = fit_bezier_adaptive(points, tolerance=2.0, max_segments=16, max_depth=5)
        if not bezier_segs:
            continue
        scene.add_path(PathRecord(path_id=f"contour-{i}", path_type="path", closed=True,
                                  segments=bezier_segs, fill={"color":"#000000", "opacity":1},
                                  stroke={"color":"none", "width":0}))
        simplified_count += len(points)
        bezier_segment_count += len(bezier_segs)

    with open("outputs/scene.json", "w", encoding="utf-8") as f:
        json.dump(scene.to_json(), f, indent=2)
    with open("outputs/output.svg", "w", encoding="utf-8") as f:
        f.write(scene.export_svg())

    # Rasterize the actual exported polygon geometry with a scanline fill so
    # metrics compare the reconstruction to the source, not a placeholder.
    reconstructed = [[1.0] * width for _ in range(height)]
    for path in scene.paths:
        # For Bézier paths, sample the curves for rasterization
        pts = []
        for seg in path.segments:
            cps = seg["control_points"]
            # Sample 10 points per Bézier segment
            for t in [j/10.0 for j in range(11)]:
                pt = evaluate_bezier(t, seg)
                pts.append(pt)
        # Close the path
        if pts and pts[0] != pts[-1]:
            pts.append(pts[0])
        if len(pts) < 3:
            continue
        for y in range(max(0, min(int(p[1]) for p in pts)), min(height, max(int(p[1]) for p in pts) + 1)):
            crossings = []
            for a, b in zip(pts, pts[1:] + pts[:1]):
                x1, y1 = a
                x2, y2 = b
                if (y1 <= y < y2) or (y2 <= y < y1):
                    crossings.append(round(x1 + (y-y1)*(x2-x1)/(y2-y1)))
            crossings.sort()
            for left, right in zip(crossings[::2], crossings[1::2]):
                for x in range(max(0, left), min(width, right + 1)):
                    reconstructed[y][x] = 0.0
    write_png("outputs/reconstructed.png", [[(round(v*255),)*3 for v in row] for row in reconstructed])
    pixel_mae = sum(abs(image[y][x]-reconstructed[y][x]) for y in range(height) for x in range(width))/(width*height)
    edge_loss = compute_edge_loss(image, reconstructed)
    with open("outputs/metrics.txt", "w", encoding="utf-8") as f:
        f.write(f"Contours selected: {len(selected)}\n")
        f.write(f"Rendered paths: {len(scene.paths)}\n")
        f.write(f"Simplified points: {simplified_count}\n")
        f.write(f"Bézier segments: {bezier_segment_count}\n")
        f.write(f"Image dimensions: {width}x{height}\n")
        f.write(f"Pixel MAE: {pixel_mae:.6f}\n")
        f.write(f"Edge loss: {edge_loss:.6f}\n")
        f.write("Rasterized reconstruction: outputs/reconstructed.png (Bézier scanline renderer)\n")
    print(f"Image: {width}x{height}; contours: {len(contours)}; paths: {len(scene.paths)}; Bézier segments: {bezier_segment_count}")


if __name__ == "__main__":
    main()
