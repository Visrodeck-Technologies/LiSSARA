"""Regression: ``scripts/render_previews.py`` must run from the repository root.

Invoking ``python scripts/render_previews.py`` puts the ``scripts/`` directory on
``sys.path`` instead of the repository root, which previously made the local
packages unimportable (``ModuleNotFoundError: No module named
'lissara_equations'``). This test reproduces that exact invocation in an isolated
copy so the committed ``outputs/`` artifacts are never touched.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCENE_JSON = ROOT / "outputs" / "scene.json"
BASELINE_SVG = ROOT / "outputs" / "output.svg"

pytestmark = pytest.mark.skipif(
    not SCENE_JSON.exists(), reason="outputs/scene.json fixture is absent"
)

_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def test_render_previews_runs_from_repository_root(tmp_path):
    shutil.copytree(ROOT / "renderer", tmp_path / "renderer", ignore=_IGNORE)
    shutil.copytree(
        ROOT / "lissara_equations", tmp_path / "lissara_equations", ignore=_IGNORE
    )
    (tmp_path / "scripts").mkdir()
    shutil.copy2(
        ROOT / "scripts" / "render_previews.py",
        tmp_path / "scripts" / "render_previews.py",
    )
    (tmp_path / "outputs").mkdir()
    shutil.copy2(SCENE_JSON, tmp_path / "outputs" / "scene.json")
    if BASELINE_SVG.exists():
        shutil.copy2(BASELINE_SVG, tmp_path / "outputs" / "output.svg")

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, os.path.join("scripts", "render_previews.py")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "ModuleNotFoundError" not in combined
    assert "Segments in scene: 1372; C commands in SVG: 1372" in result.stdout
    assert (tmp_path / "outputs" / "renderer_graph_preview.svg").exists()
    assert (tmp_path / "outputs" / "renderer_scene_preview.svg").exists()
    assert (tmp_path / "outputs" / "renderer_lineart_preview.svg").exists()
