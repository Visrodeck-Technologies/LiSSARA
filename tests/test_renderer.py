"""Tests for the mathematical graphing engine."""
import math
import xml.etree.ElementTree as ET

import pytest

from renderer import (
    GraphConfig,
    GraphRenderer,
    Viewport,
    fit_bounds,
    render_scene_svg,
    scene_to_graph,
    has_raster_backend,
    svg_to_png,
    RasterBackendUnavailable,
)
from renderer import sampling
from lissara_equations import make_cubic


def test_viewport_world_to_screen_roundtrip():
    vp = Viewport(width=400, height=400, world_bounds=(-10, -5, 10, 5), margin=20)
    for x, y in [(-10, -5), (0, 0), (10, 5), (3.14, -2.0), (-7.5, 4.2)]:
        sx, sy = vp.world_to_screen(x, y)
        rx, ry = vp.screen_to_world(sx, sy)
        assert math.isclose(rx, x, abs_tol=1e-9)
        assert math.isclose(ry, y, abs_tol=1e-9)


def test_viewport_screen_to_world_roundtrip():
    vp = Viewport(width=320, height=240, world_bounds=(0, 0, 100, 50), margin=10)
    for px, py in [(10, 10), (160, 120), (330, 250), (25.5, 200.7)]:
        x, y = vp.screen_to_world(px, py)
        spx, spy = vp.world_to_screen(x, y)
        assert math.isclose(spx, px, abs_tol=1e-9)
        assert math.isclose(spy, py, abs_tol=1e-9)


def test_viewport_aspect_ratio_and_inversion():
    vp = Viewport(width=200, height=100, world_bounds=(-1, -1, 1, 1), margin=0, preserve_aspect=True)
    sx0, sy0 = vp.world_to_screen(-1, -1)
    sx1, sy1 = vp.world_to_screen(1, 1)
    assert math.isclose(sx1 - sx0, 100.0, rel_tol=1e-9)  # 200/2
    sxc, syc = vp.world_to_screen(0, 0)
    assert sx0 <= sxc <= sx1
    # with invert_y=True (default), y increases upward in world -> lower screen y at top?
    # world -1 -> screen y larger (downward), world +1 -> smaller; check relative positions
    assert sy1 < sy0  # +1 is higher -> smaller screen Y


def test_viewport_non_preserving_fills_area():
    vp = Viewport(width=200, height=100, world_bounds=(0, 0, 2, 1), margin=0, preserve_aspect=False)
    (sx0, sy0) = vp.world_to_screen(0, 0)
    (sx2, sy2) = vp.world_to_screen(2, 1)
    assert math.isclose(sx2 - sx0, 200.0)
    assert math.isclose(sy2 - sy0, -100.0)  # y increases downward on screen, so world +y maps to smaller screen y


def test_viewport_rejects_invalid():
    with pytest.raises(ValueError):
        Viewport(width=0, height=100, world_bounds=(0,0,1,1))
    with pytest.raises(ValueError):
        Viewport(width=100, height=100, world_bounds=(0,0,0,1))
    with pytest.raises(ValueError):
        Viewport(width=100, height=100, world_bounds=(0,0,1,0))
    with pytest.raises(ValueError):
        Viewport(width=40, height=40, world_bounds=(0,0,1,1), margin=20)


def test_fit_bounds_padding_and_single_point():
    bounds = fit_bounds([(0, 0)], padding=0.1)
    assert bounds[0] < 0 and bounds[2] > 0 and bounds[1] < 0 and bounds[3] > 0
    bounds2 = fit_bounds([(1, 2), (3, 4)], padding=0.0)
    assert bounds2 == (1.0, 2.0, 3.0, 4.0)


# sampling tests
def test_sample_cubic_uniform_endpoints():
    curve = make_cubic((0,0),(1,3),(4,-2),(6,1))
    pts = sampling.sample_cubic(curve, n=10)
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (6.0, 1.0)
    assert len(pts) == 11


def test_sample_cubic_adaptive_endpoints_and_fidelity():
    curve = make_cubic((0,0),(0,10),(10,10),(10,0))  # arch
    pts = sampling.sample_cubic_adaptive(curve, tolerance=0.25, max_depth=6)
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (10.0, 0.0)
    assert len(pts) >= 5


def test_sample_degenerate():
    curve = make_cubic((5,5),(5,5),(5,5),(5,5))
    pts = sampling.sample_cubic_adaptive(curve, tolerance=0.01, max_depth=3)
    assert pts[0] == pts[-1] == (5.0, 5.0)
    assert len(pts) <= 5


def test_sample_invalid_args():
    with pytest.raises(ValueError):
        sampling.sample_cubic(make_cubic((0,0),(1,1),(2,1),(3,0)), n=0)
    with pytest.raises(ValueError):
        sampling.sample_cubic_adaptive(make_cubic((0,0),(1,1),(2,1),(3,0)), tolerance=-1)


# graph renderer
def test_graph_renders_curve_and_svg_valid():
    g = GraphRenderer(GraphConfig(width=200, height=200, margin=10, show_grid=False, show_axes=False))
    g.add_cubic(make_cubic((0,0),(0,1),(1,1),(1,0)), adaptive=True, tolerance=0.5)
    svg = g.render_svg()
    assert "<svg" in svg
    assert "</svg>" in svg
    ET.fromstring(svg)  # should parse


def test_graph_multiple_curves_and_closed():
    g = GraphRenderer(GraphConfig(width=150, height=150, margin=5, show_grid=False, show_axes=False))
    g.add_cubic(make_cubic((0,0),(0,1),(1,1),(0,0)), adaptive=True, tolerance=0.3)  # just evaluate
    g.add_polyline([(1,1),(2,1),(1.5,0)], closed=True, color="#ff0000", width=1.5)
    svg = g.render_svg()
    assert svg.count('<path') >= 2
    ET.fromstring(svg)


def test_graph_infers_bounds():
    g = GraphRenderer(GraphConfig(width=100, height=100, margin=0, world_bounds=None, preserve_aspect=False, show_grid=False, show_axes=False))
    g.add_polyline([(0,0),(10,20)])
    svg = g.render_svg()
    assert "<svg" in svg


def test_non_finite_raises():
    vp = Viewport(width=100, height=100, world_bounds=(0,0,1,1))
    with pytest.raises(ValueError):
        vp.world_to_screen(float('nan'), 0)
    with pytest.raises(ValueError):
        vp.screen_to_world(50, float('inf'))


# scene rendering
def test_render_scene_svg_reads_engine_scene():
    from lissara_engine import MathScene, PathRecord
    from lissara_equations import make_cubic
    scene = MathScene(width=100, height=100)
    scene.add_path(PathRecord(path_id='p0', closed=True, segments=[make_cubic((0,0),(10,0),(10,10),(0,10))], stroke={'color':'#000000','width':1}))
    svg = render_scene_svg(scene)
    assert '<svg' in svg and '</svg>' in svg
    ET.fromstring(svg)


def test_scene_to_graph_preserves_geometry_without_mutating():
    from lissara_engine import MathScene, PathRecord
    from lissara_equations import make_cubic
    scene = MathScene(width=80, height=80)
    segs = [make_cubic((0,0),(20,0),(20,20),(0,20))]
    scene.add_path(PathRecord(path_id='a', closed=False, segments=segs))
    orig = [dict(s) for s in segs]
    g = scene_to_graph(scene, config=GraphConfig(width=80,height=80,margin=0,show_axes=False,show_grid=False))
    # check not mutated
    assert scene.paths[0].segments[0]['control_points'] == orig[0]['control_points']
    assert len(g._curves) >= 1


def test_render_scene_svg_from_dict():
    from lissara_equations import make_cubic
    scene = {
        'width': 60, 'height': 60,
        'paths': [
            {'closed': True, 'segments': [make_cubic((0,0),(5,0),(5,5),(0,5))], 'stroke': {'color':'#111111','width':2}}
        ]
    }
    svg = render_scene_svg(scene)
    ET.fromstring(svg)


# raster optional
def test_raster_backend_flag_consistent():
    flag = has_raster_backend()
    if flag:
        # try a tiny svg
        png = svg_to_png('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="#fff"/></svg>')
        assert isinstance(png, bytes) and len(png) > 0
    else:
        with pytest.raises(RasterBackendUnavailable):
            svg_to_png('<svg></svg>')
