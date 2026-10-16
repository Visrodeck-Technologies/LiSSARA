import numpy as np

from lissara_vectorization.edge_tracing import (
    detect_classical_edges,
    filter_edge_paths,
    trace_edge_paths,
)


def test_canny_defaults_reproduce_existing_baseline():
    gray = np.zeros((24, 24), dtype=np.uint8)
    gray[5:19, 8:16] = 255
    assert np.array_equal(
        detect_classical_edges(gray),
        __import__("cv2").Canny(gray, 50, 150),
    )


def test_branch_is_split_into_independent_ordered_paths():
    edge = np.zeros((9, 9), dtype=np.uint8)
    edge[1:8, 4] = 255
    edge[4, 1:8] = 255
    paths = trace_edge_paths(edge)
    assert len(paths) == 4
    assert all(not path["closed"] for path in paths)
    assert all(len(path["points"]) >= 4 for path in paths)
    endpoints = {path["points"][0] for path in paths} | {
        path["points"][-1] for path in paths
    }
    assert {(4, 1), (4, 7), (1, 4), (7, 4), (4, 4)} <= endpoints


def test_closed_loop_and_small_gap_are_preserved_as_separate_paths():
    edge = np.zeros((16, 20), dtype=np.uint8)
    edge[2, 2:9] = edge[8, 2:9] = 255
    edge[2:9, 2] = edge[2:9, 8] = 255
    edge[12, 2:5] = 255
    edge[12, 6:9] = 255
    paths = trace_edge_paths(edge)
    closed = [path for path in paths if path["closed"]]
    open_paths = [path for path in paths if not path["closed"]]
    assert len(closed) == 1
    assert len(open_paths) == 2
    assert closed[0]["points"][0] == closed[0]["points"][-1]


def test_tangent_aligned_small_gap_can_be_bridged_without_closing_path():
    edge = np.zeros((9, 12), dtype=np.uint8)
    edge[4, 1:4] = 255
    edge[4, 5:8] = 255
    assert len(trace_edge_paths(edge)) == 2
    bridged = trace_edge_paths(edge, gap_tolerance=1)
    assert len(bridged) == 1
    assert not bridged[0]["closed"]
    assert bridged[0]["points"][0] == (1, 4)
    assert bridged[0]["points"][-1] == (7, 4)


def test_filters_are_configurable_and_preserve_fine_strokes():
    paths = [
        {"points": [(3, 3), (4, 3)], "closed": False},
        {"points": [(3, 5), (4, 5), (5, 5), (6, 5), (7, 5)], "closed": False},
    ]
    assert len(filter_edge_paths(paths, 20, 20, min_length=0)) == 2
    assert filter_edge_paths(paths, 20, 20, min_length=3) == [paths[1]]
