"""Fixture-based renderer validation against real committed Lissara artifacts.

These tests use the committed ``outputs/`` fixtures (there is no need to re-run
the image-reconstruction pipeline):

* ``outputs/scene.json`` — a real ``MathScene`` (region-contour representation).
* ``outputs/output.svg`` — the committed Canny line-art baseline (stroke-only
  ``edge-path-*`` cubic paths). It is parsed here into canonical cubic segment
  records and fed back through :func:`renderer.render_scene_svg` to prove the
  renderer reproduces every segment exactly.

Tests skip when the fixtures are absent so the suite stays usable in a bare
checkout.
"""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from renderer import SceneRenderConfig, render_scene_svg

ROOT = Path(__file__).resolve().parents[1]
SCENE_JSON = ROOT / "outputs" / "scene.json"
BASELINE_SVG = ROOT / "outputs" / "output.svg"
NS = "{http://www.w3.org/2000/svg}"

_PATH_TOKEN = re.compile(r"([MLCZ])\s*([^MLCZ]*)")
_NUMBER = re.compile(r"-?\d+\.?\d*(?:[eE]-?\d+)?")


def _parse_svg_path(d):
    """Parse an ``M``/``L``/``C``/``Z`` path into canonical cubic segments."""
    segments = []
    start = last = None
    closed = False
    for letter, body in _PATH_TOKEN.findall(d):
        nums = [float(token) for token in _NUMBER.findall(body)]
        if letter == "M":
            start = last = (nums[0], nums[1])
        elif letter == "L":
            last = (nums[0], nums[1])
        elif letter == "C":
            control_1 = (nums[0], nums[1])
            control_2 = (nums[2], nums[3])
            end = (nums[4], nums[5])
            segments.append({"control_points": [last, control_1, control_2, end]})
            last = end
        elif letter == "Z":
            closed = True
    return segments, closed, start


def _baseline_scene():
    root = ET.parse(str(BASELINE_SVG)).getroot()
    paths = []
    for element in root.findall(NS + "path"):
        segments, closed, _ = _parse_svg_path(element.get("d"))
        paths.append({
            "path_id": element.get("id"),
            "segments": segments,
            "closed": closed,
            "fill": {"color": "none"},
            "stroke": {"color": "#17151b", "width": 1.25},
        })
    return {"width": 1840, "height": 2991, "paths": paths}


# --- scene.json -----------------------------------------------------------

scene_json_required = pytest.mark.skipif(
    not SCENE_JSON.exists(), reason="outputs/scene.json fixture is absent"
)


@scene_json_required
def test_scene_json_render_preserves_every_segment():
    scene = json.loads(SCENE_JSON.read_text(encoding="utf-8"))
    total_segments = sum(len(p.get("segments", [])) for p in scene["paths"])

    svg = render_scene_svg(scene, config=SceneRenderConfig(mode="scene"))

    ET.fromstring(svg)  # must be valid XML
    assert svg.count("C ") == total_segments
    assert scene["width"] == 1840 and scene["height"] == 2991
    assert f'viewBox="0 0 {scene["width"]} {scene["height"]}"' in svg


@scene_json_required
def test_scene_json_render_is_deterministic():
    scene = json.loads(SCENE_JSON.read_text(encoding="utf-8"))
    first = render_scene_svg(scene, config=SceneRenderConfig(mode="scene"))
    second = render_scene_svg(scene, config=SceneRenderConfig(mode="scene"))
    assert first == second


@scene_json_required
def test_scene_json_render_does_not_mutate_scene():
    scene = json.loads(SCENE_JSON.read_text(encoding="utf-8"))
    snapshot = json.dumps(scene, sort_keys=True)
    render_scene_svg(scene, config=SceneRenderConfig(mode="lineart"))
    assert json.dumps(scene, sort_keys=True) == snapshot


# --- output.svg (Canny line-art baseline) ---------------------------------

baseline_required = pytest.mark.skipif(
    not BASELINE_SVG.exists(), reason="outputs/output.svg baseline is absent"
)


@baseline_required
def test_baseline_roundtrip_preserves_all_cubics():
    scene = _baseline_scene()
    source_paths = len(scene["paths"])
    source_cubics = sum(len(p["segments"]) for p in scene["paths"])
    assert source_paths == 1423
    assert source_cubics == 6030

    svg = render_scene_svg(scene, config=SceneRenderConfig(mode="lineart"))

    ET.fromstring(svg)
    assert svg.count("C ") == source_cubics
    rendered = ET.fromstring(svg).findall(NS + "path")
    assert len(rendered) == source_paths


@baseline_required
def test_baseline_roundtrip_matches_geometry_exactly():
    scene = _baseline_scene()
    svg = render_scene_svg(scene, config=SceneRenderConfig(mode="lineart"))
    rebuilt = []
    for element in ET.fromstring(svg).findall(NS + "path"):
        segments, _, _ = _parse_svg_path(element.get("d"))
        rebuilt.append(segments)

    for original, rendered in zip(scene["paths"], rebuilt):
        assert len(original["segments"]) == len(rendered)
        for left, right in zip(original["segments"], rendered):
            assert left["control_points"] == right["control_points"]
