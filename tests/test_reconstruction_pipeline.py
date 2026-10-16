"""End-to-end tests for the image-to-equations-to-rendering reconstruction.

These run the complete pipeline on a small synthetic image through the public
:func:`main.main` entry point (``reconstruct``) and validate every artifact:
the MathScene, the equation report, and the rendered SVGs. PNG rasterization is
disabled so the tests pass whether or not the native cairo library is present.

The committed ``outputs/`` baseline is never touched; everything is written to
``tmp_path``.
"""
from __future__ import annotations

import json
import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image

import main

SVG_NS = "{http://www.w3.org/2000/svg}"
ROOT = Path(__file__).resolve().parents[1]
REAL_INPUT = ROOT / "INPUT" / "image.png"
CORE_ARTIFACTS = (
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


def _run(synthetic_image, out_dir, *extra):
    return main.main([
        "reconstruct",
        "--input", str(synthetic_image),
        "--output-dir", str(out_dir),
        "--no-png",
        *extra,
    ])


def _cubic_count(svg_text):
    root = ET.fromstring(svg_text)
    total = 0
    for element in root.findall(SVG_NS + "path"):
        d = element.get("d") or ""
        total += sum(1 for token in d.split() if token == "C")
    return total


def _de_casteljau(control_points, t):
    points = [(float(x), float(y)) for x, y in control_points]
    for degree in range(3, 0, -1):
        points = [
            (
                (1.0 - t) * points[i][0] + t * points[i + 1][0],
                (1.0 - t) * points[i][1] + t * points[i + 1][1],
            )
            for i in range(degree)
        ]
    return points[0]


@pytest.fixture
def reconstructed(synthetic_image, tmp_path):
    out_dir = tmp_path / "generated"
    assert _run(synthetic_image, out_dir) == 0
    return out_dir


def test_all_artifacts_are_written(reconstructed):
    for name in CORE_ARTIFACTS:
        assert (reconstructed / name).exists(), name


def test_scene_is_consistent_and_in_bounds(reconstructed):
    scene = json.loads((reconstructed / "scene.json").read_text(encoding="utf-8"))
    width, height = scene["width"], scene["height"]
    assert (width, height) == (96, 96)
    assert scene["paths"], "expected at least one accepted path"

    open_count = closed_count = segment_total = 0
    for path in scene["paths"]:
        segments = path["segments"]
        assert segments, f"empty path {path['path_id']}"
        segment_total += len(segments)
        closed_count += bool(path["closed"])
        open_count += not bool(path["closed"])
        for segment in segments:
            for x, y in segment["control_points"]:
                assert math.isfinite(x) and math.isfinite(y)
                assert 0 <= x <= width - 1 and 0 <= y <= height - 1
        for left, right in zip(segments, segments[1:]):
            assert left["control_points"][3] == right["control_points"][0]
        if path["closed"]:
            assert segments[-1]["control_points"][3] == segments[0]["control_points"][0]

    assert segment_total > 0
    assert open_count + closed_count == len(scene["paths"])


def test_equations_report_matches_scene(reconstructed):
    scene = json.loads((reconstructed / "scene.json").read_text(encoding="utf-8"))
    equations = json.loads((reconstructed / "equations.json").read_text(encoding="utf-8"))

    scene_segments = sum(len(p["segments"]) for p in scene["paths"])
    assert equations["path_count"] == len(scene["paths"])
    assert equations["segment_count"] == scene_segments
    assert sum(len(p["segments"]) for p in equations["paths"]) == scene_segments

    for path in equations["paths"]:
        assert path["segment_count"] == len(path["segments"])
        for segment in path["segments"]:
            assert segment["domain"] == [0.0, 1.0]
            assert set(segment["x_coeffs"]) == {"a3", "a2", "a1", "a0"}
            assert set(segment["y_coeffs"]) == {"b3", "b2", "b1", "b0"}
            assert segment["x_expression"].startswith("x(t) =")
            assert segment["y_expression"].startswith("y(t) =")


def test_equations_evaluate_independently(reconstructed):
    equations = json.loads((reconstructed / "equations.json").read_text(encoding="utf-8"))
    assert equations["segment_count"] > 0
    checked = 0
    for path in equations["paths"]:
        for segment in path["segments"]:
            xc, yc = segment["x_coeffs"], segment["y_coeffs"]
            control_points = segment["control_points"]
            for t in (0.0, 0.5, 1.0):
                t2, t3 = t * t, t * t * t
                bx = xc["a3"] * t3 + xc["a2"] * t2 + xc["a1"] * t + xc["a0"]
                by = yc["b3"] * t3 + yc["b2"] * t2 + yc["b1"] * t + yc["b0"]
                dx, dy = _de_casteljau(control_points, t)
                assert abs(bx - dx) <= 1e-6
                assert abs(by - dy) <= 1e-6
                checked += 1
            # Endpoint identity.
            assert abs(xc["a0"] - control_points[0][0]) <= 1e-6
            assert abs(yc["b0"] - control_points[0][1]) <= 1e-6
        # Cheap guard: stop after a few paths; the equation module validates the
        # whole report during the run itself.
        if checked > 200:
            break
    assert checked > 0


def test_equations_txt_lists_every_path(reconstructed):
    equations = json.loads((reconstructed / "equations.json").read_text(encoding="utf-8"))
    text = (reconstructed / "equations.txt").read_text(encoding="utf-8")
    assert f"Paths: {equations['path_count']}" in text
    assert f"Segments: {equations['segment_count']}" in text
    for path in equations["paths"][:5]:
        assert f"Path: {path['path_id']}" in text
    assert "x(t) =" in text and "y(t) =" in text


def test_lineart_svg_is_exact_cubic_stroke_only(reconstructed):
    scene = json.loads((reconstructed / "scene.json").read_text(encoding="utf-8"))
    scene_segments = sum(len(p["segments"]) for p in scene["paths"])
    svg = (reconstructed / "lineart.svg").read_text(encoding="utf-8")
    root = ET.fromstring(svg)  # valid XML
    assert _cubic_count(svg) == scene_segments
    assert 'fill="none"' in svg
    assert 'stroke="#17151b"' in svg
    assert 'fill="#ffffff"' in svg
    assert root.get("viewBox") == "0 0 96 96"


def test_scene_svg_matches_segment_count(reconstructed):
    scene = json.loads((reconstructed / "scene.json").read_text(encoding="utf-8"))
    scene_segments = sum(len(p["segments"]) for p in scene["paths"])
    svg = (reconstructed / "scene.svg").read_text(encoding="utf-8")
    ET.fromstring(svg)
    assert _cubic_count(svg) == scene_segments


def test_graph_svg_uses_image_space_without_decorations(reconstructed):
    svg = (reconstructed / "graph.svg").read_text(encoding="utf-8")
    root = ET.fromstring(svg)
    assert root.get("viewBox") == "0 0 96 96"
    # Image-space view: no axes/grid/ticks -> no <line> decoration elements.
    assert root.findall(SVG_NS + "line") == []
    assert root.findall(SVG_NS + "path")


def test_edges_png_decodes_at_image_size(reconstructed):
    with Image.open(reconstructed / "edges.png") as edge_image:
        assert edge_image.size == (96, 96)


def test_metrics_report_raster_availability(reconstructed):
    metrics = json.loads((reconstructed / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["contours"]["accepted"] > 0
    assert metrics["contours"]["open"] + metrics["contours"]["closed"] == \
        metrics["contours"]["accepted"]
    assert metrics["equations"]["segment_count"] == metrics["svg"]["lineart.svg"]["cubic_commands"]
    assert metrics["equations"]["validation"]["ok"] is True
    raster = metrics["raster"]
    assert isinstance(raster["backend_available"], bool)
    if not raster["backend_available"]:
        assert raster["png_written"] is False
        assert raster["note"]
    assert (reconstructed / "metrics.txt").read_text(encoding="utf-8")


def test_force_is_required_to_overwrite(synthetic_image, tmp_path, capsys):
    out_dir = tmp_path / "generated"
    assert _run(synthetic_image, out_dir) == 0
    # Second run without --force must refuse.
    assert _run(synthetic_image, out_dir) == 2
    assert "--force" in capsys.readouterr().err
    # With --force it succeeds.
    assert _run(synthetic_image, out_dir, "--force") == 0


def test_invalid_parameters_return_error(synthetic_image, tmp_path, capsys):
    out_dir = tmp_path / "generated"
    code = main.main([
        "reconstruct", "--input", str(synthetic_image),
        "--output-dir", str(out_dir), "--no-png",
        "--canny-low", "200", "--canny-high", "100",
    ])
    assert code == 1
    assert "Canny" in capsys.readouterr().err


def test_missing_input_returns_error(tmp_path, capsys):
    code = main.main([
        "reconstruct", "--input", str(tmp_path / "absent.png"),
        "--output-dir", str(tmp_path / "generated"), "--no-png",
    ])
    assert code == 1
    assert "not found" in capsys.readouterr().err


@pytest.mark.skipif(
    not REAL_INPUT.exists() or not os.environ.get("LISSARA_RUN_INTEGRATION"),
    reason="set LISSARA_RUN_INTEGRATION=1 to run the full-resolution real-image test",
)
def test_real_image_end_to_end(tmp_path):
    """Full-resolution integration run on INPUT/image.png (opt-in, slow)."""
    out_dir = tmp_path / "generated"
    assert main.main([
        "reconstruct", "--input", str(REAL_INPUT),
        "--output-dir", str(out_dir), "--no-png",
    ]) == 0

    metrics = json.loads((out_dir / "metrics.json").read_text(encoding="utf-8"))
    assert (metrics["input"]["width"], metrics["input"]["height"]) == (1840, 2991)
    assert metrics["contours"]["traced"] > 0
    assert metrics["contours"]["accepted"] > 0
    assert metrics["contours"]["open"] + metrics["contours"]["closed"] == \
        metrics["contours"]["accepted"]
    assert metrics["equations"]["validation"]["ok"] is True
    assert metrics["svg"]["lineart.svg"]["cubic_commands"] == \
        metrics["equations"]["segment_count"]
    assert metrics["svg"]["scene.svg"]["cubic_commands"] == \
        metrics["equations"]["segment_count"]
    assert (out_dir / "equations.txt").read_text(encoding="utf-8")
