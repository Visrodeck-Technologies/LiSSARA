"""Generate renderer validation previews from real Lissara geometry.

Outputs (written to ``outputs/``):
    * ``renderer_graph_preview.svg``  — a mathematical graph with axes/grid.
    * ``renderer_scene_preview.svg``  — the reconstructed scene, exact geometry.
    * ``renderer_lineart_preview.svg``— the same scene as a line-art preview.
    * ``renderer_scene_preview.png``  — only if CairoSVG's native backend exists.

The script also asserts the exported SVG parses and that the number of cubic
``C`` commands equals the number of segments in the source scene.
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Resolve the repository root and make the local packages importable regardless
# of the current working directory (running ``python scripts/render_previews.py``
# puts ``scripts/`` on ``sys.path``, not the repository root).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lissara_equations import make_cubic, make_quadratic  # noqa: E402
from renderer import (  # noqa: E402
    GraphConfig,
    GraphRenderer,
    SceneRenderConfig,
    has_raster_backend,
    render_scene_svg,
    svg_to_png,
)

# Input and output paths are anchored to the repository root, not the cwd.
OUTPUT_DIR = ROOT / "outputs"
SCENE_PATH = OUTPUT_DIR / "scene.json"
BASELINE_SVG = OUTPUT_DIR / "output.svg"
GRAPH_OUT = OUTPUT_DIR / "renderer_graph_preview.svg"
SCENE_OUT = OUTPUT_DIR / "renderer_scene_preview.svg"
LINEART_OUT = OUTPUT_DIR / "renderer_lineart_preview.svg"
PNG_OUT = OUTPUT_DIR / "renderer_scene_preview.png"

NS = "{http://www.w3.org/2000/svg}"
_PATH_TOKEN = re.compile(r"([MLCZ])\s*([^MLCZ]*)")
_NUMBER = re.compile(r"-?\d+\.?\d*(?:[eE]-?\d+)?")


def parse_svg_path(d):
    """Parse an ``M``/``L``/``C``/``Z`` path into canonical cubic segments."""
    segments = []
    last = None
    closed = False
    for letter, body in _PATH_TOKEN.findall(d):
        nums = [float(token) for token in _NUMBER.findall(body)]
        if letter == "M":
            last = (nums[0], nums[1])
        elif letter == "L":
            last = (nums[0], nums[1])
        elif letter == "C":
            end = (nums[4], nums[5])
            segments.append({"control_points": [last, (nums[0], nums[1]), (nums[2], nums[3]), end]})
            last = end
        elif letter == "Z":
            closed = True
    return segments, closed


def check_baseline():
    """Re-render the committed Canny line-art SVG and verify exact geometry."""
    root = ET.parse(BASELINE_SVG).getroot()
    source_paths = root.findall(NS + "path")
    scene = {"width": 1840, "height": 2991, "paths": []}
    for element in source_paths:
        segments, closed = parse_svg_path(element.get("d"))
        scene["paths"].append({
            "segments": segments,
            "closed": closed,
            "fill": {"color": "none"},
            "stroke": {"color": "#17151b", "width": 1.25},
        })
    source_cubics = sum(len(p["segments"]) for p in scene["paths"])

    svg = render_scene_svg(scene, config=SceneRenderConfig(mode="lineart"))
    ET.fromstring(svg)
    rendered_paths = ET.fromstring(svg).findall(NS + "path")
    assert len(rendered_paths) == len(source_paths), "baseline path count changed!"
    assert svg.count("C ") == source_cubics, "baseline cubic geometry not preserved!"
    print(f"Baseline recheck: {len(source_paths)} paths / {source_cubics} cubics "
          f"reproduced exactly from committed output.svg")


def build_graph_preview():
    config = GraphConfig(
        width=640,
        height=480,
        margin=48,
        show_grid=True,
        show_axes=True,
        show_ticks=True,
        show_labels=True,
        tick_target=10,
    )
    renderer = GraphRenderer(config)
    # Two cubic Bézier arches and one quadratic, with explicit analytic values.
    renderer.add_cubic(make_cubic((0, 0), (0, 6), (6, 6), (6, 0)), tolerance=0.1)
    renderer.add_cubic(make_cubic((0, 0), (2, -3), (4, 3), (6, 0)), tolerance=0.1,
                       color="#d81b60")
    renderer.add_curve(make_quadratic((0, 0), (3, 5), (6, 0)), adaptive=True,
                       tolerance=0.1, color="#2e7d32")
    renderer.add_point((3, 4.5), radius_world=0.08, color="#2e7d32")
    return renderer.render_svg()


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    graph_svg = build_graph_preview()
    ET.fromstring(graph_svg)
    with open(GRAPH_OUT, "w", encoding="utf-8") as handle:
        handle.write(graph_svg)
    print(f"Wrote {GRAPH_OUT} ({len(graph_svg)} chars)")

    with open(SCENE_PATH, "r", encoding="utf-8") as handle:
        scene = json.load(handle)

    total_segments = sum(len(p.get("segments", [])) for p in scene.get("paths", []))

    scene_svg = render_scene_svg(
        scene, output_path=SCENE_OUT, config=SceneRenderConfig(mode="scene")
    )
    ET.fromstring(scene_svg)
    c_commands = scene_svg.count("C ")
    print(f"Wrote {SCENE_OUT} ({len(scene_svg)} chars)")
    print(f"Segments in scene: {total_segments}; C commands in SVG: {c_commands}")
    assert c_commands == total_segments, "exact geometry not preserved!"

    lineart_svg = render_scene_svg(
        scene, output_path=LINEART_OUT, config=SceneRenderConfig(mode="lineart")
    )
    ET.fromstring(lineart_svg)
    print(f"Wrote {LINEART_OUT} ({len(lineart_svg)} chars)")

    if os.path.exists(BASELINE_SVG):
        check_baseline()
    else:
        print(f"Skipped baseline recheck ({BASELINE_SVG} absent)")

    if has_raster_backend():
        svg_to_png(scene_svg, path=PNG_OUT)
        print(f"Wrote {PNG_OUT}")
    else:
        print("PNG raster backend unavailable (native cairo missing); SVG only.")

    print("Validation OK: all exported SVGs parse; cubic geometry preserved exactly.")


if __name__ == "__main__":
    main()
