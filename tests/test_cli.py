"""Tests for the unified ``main.py`` command-line interface.

These exercise the CLI through :func:`main.main` with explicit argument lists
and write any artifacts into ``tmp_path`` so the committed ``outputs/`` fixtures
are never touched. Tests that depend on committed fixtures skip when absent.
"""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import main

ROOT = Path(__file__).resolve().parents[1]
SCENE_JSON = ROOT / "outputs" / "scene.json"
BASELINE_SVG = ROOT / "outputs" / "output.svg"
NS = "{http://www.w3.org/2000/svg}"

fixtures_required = pytest.mark.skipif(
    not (SCENE_JSON.exists() and BASELINE_SVG.exists()),
    reason="committed outputs/ fixtures are absent",
)


def test_help_lists_all_commands(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main.main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    for command in ("graph", "scene", "lineart", "previews", "pipeline",
                    "reconstruct", "test", "check", "status"):
        assert command in out


def test_no_command_is_an_error(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main.main([])
    assert excinfo.value.code != 0


@fixtures_required
def test_status_reports_environment(capsys):
    assert main.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "repo root" in out
    assert "png raster" in out
    assert "fixtures" in out


@fixtures_required
def test_check_validates_committed_fixtures(capsys):
    assert main.main(["check"]) == 0
    out = capsys.readouterr().out
    assert "[OK] outputs/scene.json" in out
    assert "[OK] outputs/output.svg" in out
    assert "[FAIL]" not in out


def test_graph_writes_parseable_svg(tmp_path, capsys):
    out = tmp_path / "graph.svg"
    assert main.main(["graph", "--output", str(out)]) == 0
    ET.parse(out)
    assert out.read_text(encoding="utf-8").startswith("<svg")


@fixtures_required
def test_scene_renders_exact_geometry(tmp_path, capsys):
    out = tmp_path / "scene.svg"
    assert main.main(["scene", "--output", str(out)]) == 0
    svg = out.read_text(encoding="utf-8")
    ET.fromstring(svg)
    scene = json.loads(SCENE_JSON.read_text(encoding="utf-8"))
    total = sum(len(p.get("segments", [])) for p in scene["paths"])
    assert svg.count("C ") == total
    assert "Validated" in capsys.readouterr().out


@fixtures_required
def test_lineart_mode_forces_stroke_only(tmp_path):
    out = tmp_path / "lineart.svg"
    assert main.main(["lineart", "--output", str(out),
                      "--lineart-color", "#222222", "--lineart-width", "1.5"]) == 0
    svg = out.read_text(encoding="utf-8")
    ET.fromstring(svg)
    assert 'stroke="#222222"' in svg
    assert 'fill="none"' in svg


def test_scene_missing_input_returns_error(tmp_path, capsys):
    assert main.main(["scene", "--input", str(tmp_path / "absent.json")]) == 1
    assert "not found" in capsys.readouterr().err


def test_scene_invalid_json_returns_error(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert main.main(["scene", "--input", str(bad)]) == 1
    assert "not valid JSON" in capsys.readouterr().err


def test_scene_invalid_dimensions_returns_error(tmp_path, capsys):
    bad = tmp_path / "nodim.json"
    bad.write_text(json.dumps({"paths": []}), encoding="utf-8")
    assert main.main(["scene", "--input", str(bad)]) == 1
    assert "invalid dimensions" in capsys.readouterr().err


def test_pipeline_requires_confirmation(capsys):
    assert main.main(["pipeline"]) == 2
    assert "re-run with --yes" in capsys.readouterr().out


def test_reconstruct_runs_full_pipeline_without_cairo(synthetic_image, tmp_path, capsys):
    out_dir = tmp_path / "generated"
    code = main.main([
        "reconstruct", "--input", str(synthetic_image),
        "--output-dir", str(out_dir), "--no-png",
    ])
    assert code == 0
    for name in ("scene.json", "equations.json", "equations.txt",
                 "lineart.svg", "scene.svg", "graph.svg", "edges.png",
                 "metrics.txt", "metrics.json"):
        assert (out_dir / name).exists(), name
    out = capsys.readouterr().out
    assert "Reconstruction complete" in out
