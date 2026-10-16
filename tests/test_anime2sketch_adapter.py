import pytest
from lissara_vectorization import fit_bezier_adaptive
from lissara_equations import evaluate_bezier

from lissara_vectorization.anime2sketch import (
    Anime2SketchBackend,
    Anime2SketchUnavailable,
)


def test_tile_starts_cover_without_gaps_and_anchor_final_edge():
    starts = Anime2SketchBackend._starts(1840, 512, 448)
    assert starts == [0, 448, 896, 1328]
    assert starts[0] == 0
    assert starts[-1] + 512 == 1840
    assert all(right - left <= 448 for left, right in zip(starts, starts[1:]))


def test_adapter_requires_explicit_supported_geometry(tmp_path):
    with pytest.raises(ValueError, match="512-pixel"):
        Anime2SketchBackend(str(tmp_path / "model.pth"), tile_size=256)


def test_missing_checkpoint_fails_without_importing_torch(tmp_path):
    backend = Anime2SketchBackend(str(tmp_path / "absent.pth"), source_repo=str(tmp_path))
    with pytest.raises(Anime2SketchUnavailable, match="checkpoint not found"):
        backend._load()


def test_closed_contour_fitting_preserves_closure_and_segment_continuity():
    contour = [(0, 0), (12, 0), (16, 8), (12, 16), (0, 16), (-4, 8), (0, 0)]
    segments = fit_bezier_adaptive(contour, tolerance=0.5, max_segments=8)
    assert 2 <= len(segments) <= 8
    assert evaluate_bezier(0, segments[0]) == (0.0, 0.0)
    assert evaluate_bezier(1, segments[-1]) == (0.0, 0.0)
    for left, right in zip(segments, segments[1:]):
        assert evaluate_bezier(1, left) == evaluate_bezier(0, right)
