"""Classical edge detection and ordered pixel-graph contour tracing."""

from __future__ import annotations

import math

import cv2
import numpy as np


def detect_classical_edges(gray, low_threshold=50, high_threshold=150,
                           aperture_size=3, blur_sigma=0.0, gap_close=0):
    """Reproduce the project's Canny baseline with configurable preprocessing."""
    if gray.ndim != 2:
        raise ValueError("gray must be a 2D grayscale image")
    if low_threshold < 0 or high_threshold <= low_threshold:
        raise ValueError("Canny thresholds must satisfy 0 <= low < high")
    if aperture_size not in (3, 5, 7):
        raise ValueError("aperture_size must be 3, 5, or 7")
    if blur_sigma < 0 or gap_close < 0:
        raise ValueError("blur_sigma and gap_close must be non-negative")
    image = gray
    if blur_sigma:
        image = cv2.GaussianBlur(image, (0, 0), blur_sigma)
    edges = cv2.Canny(image, low_threshold, high_threshold,
                      apertureSize=aperture_size, L2gradient=False)
    if gap_close:
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel,
                                 iterations=gap_close)
    return edges


def trace_edge_paths(edge_map, gap_tolerance=0):
    """Trace each connected edge chain independently, splitting at junctions.

    Returns dictionaries with ordered `(x, y)` points and a `closed` flag.
    Diagonal links are omitted where an orthogonal link already connects the
    same pixels, avoiding tiny triangular loops at pixel corners. Branches
    share their junction endpoint but are never concatenated into one path.
    """
    if edge_map.ndim != 2:
        raise ValueError("edge_map must be a 2D image")
    if gap_tolerance < 0:
        raise ValueError("gap_tolerance must be non-negative")
    height, width = edge_map.shape
    binary = edge_map != 0
    ids = np.flatnonzero(binary)
    if ids.size == 0:
        return []
    present = np.zeros(height * width, dtype=bool)
    present[ids] = True
    adjacency = {}
    offsets = ((-1, -1), (0, -1), (1, -1), (-1, 0),
               (1, 0), (-1, 1), (0, 1), (1, 1))

    for flat_id in ids.tolist():
        y, x = divmod(flat_id, width)
        neighbors = []
        for dx, dy in offsets:
            xx, yy = x + dx, y + dy
            if not (0 <= xx < width and 0 <= yy < height):
                continue
            other = yy * width + xx
            if not present[other]:
                continue
            if dx and dy:
                horizontal = y * width + xx
                vertical = yy * width + x
                if present[horizontal] or present[vertical]:
                    continue
            neighbors.append(other)
        adjacency[flat_id] = neighbors

    if gap_tolerance:
        component_labels = cv2.connectedComponents(binary.astype(np.uint8), 8)[1]
        endpoints = [node for node in adjacency if len(adjacency[node]) == 1]
        xy = {node: (node % width, node // width) for node in endpoints}
        directions = {}
        for node in endpoints:
            neighbor = adjacency[node][0]
            dx = xy[node][0] - neighbor % width
            dy = xy[node][1] - neighbor // width
            norm = math.hypot(dx, dy)
            directions[node] = (dx / norm, dy / norm)

        best = {}
        search_radius = gap_tolerance + 1
        cell_size = search_radius + 1
        buckets = {}
        for node in endpoints:
            x, y = xy[node]
            buckets.setdefault((x // cell_size, y // cell_size), []).append(node)
        for node in endpoints:
            x, y = xy[node]
            ux, uy = directions[node]
            options = []
            bx, by = x // cell_size, y // cell_size
            nearby = (other for yy in range(by - 1, by + 2)
                      for xx in range(bx - 1, bx + 2)
                      for other in buckets.get((xx, yy), ()))
            for other in nearby:
                if other == node:
                    continue
                ox, oy = xy[other]
                dx, dy = ox - x, oy - y
                if max(abs(dx), abs(dy)) > search_radius:
                    continue
                if component_labels[y, x] == component_labels[oy, ox]:
                    continue
                distance = math.hypot(dx, dy)
                vx, vy = dx / distance, dy / distance
                oux, ouy = directions[other]
                align_a = ux * vx + uy * vy
                align_b = oux * -vx + ouy * -vy
                if min(align_a, align_b) < 0.75:
                    continue
                options.append((distance - 0.25 * (align_a + align_b), other))
            if options:
                best[node] = min(options)[1]
        for node, other in best.items():
            if best.get(other) == node and node < other:
                adjacency[node].append(other)
                adjacency[other].append(node)

    visited = set()

    def edge_key(a, b):
        return (a, b) if a < b else (b, a)

    def trace(start, neighbor):
        chain = [start]
        previous, current = start, neighbor
        visited.add(edge_key(previous, current))
        chain.append(current)
        while len(adjacency[current]) == 2:
            options = [candidate for candidate in adjacency[current]
                       if candidate != previous]
            if not options:
                break
            following = options[0]
            key = edge_key(current, following)
            if key in visited:
                if following == start:
                    chain.append(start)
                break
            visited.add(key)
            previous, current = current, following
            chain.append(current)
            if current == start:
                break
        points = [(value % width, value // width) for value in chain]
        return {"points": points, "closed": len(points) > 2 and points[0] == points[-1]}

    paths = []
    # Endpoints and junction pixels delimit individual branches.
    for node in ids.tolist():
        if len(adjacency[node]) == 2:
            continue
        for neighbor in adjacency[node]:
            key = edge_key(node, neighbor)
            if key not in visited:
                paths.append(trace(node, neighbor))

    # Remaining edges are components consisting only of closed loops.
    for node in ids.tolist():
        for neighbor in adjacency[node]:
            if edge_key(node, neighbor) not in visited:
                paths.append(trace(node, neighbor))
    return paths


def path_length(points):
    return sum(math.hypot(x2 - x1, y2 - y1)
               for (x1, y1), (x2, y2) in zip(points, points[1:]))


def filter_edge_paths(paths, width, height, min_length=4.0, frame_margin=2,
                      frame_fraction=0.8):
    """Remove short noise and paths dominated by pixels on the image frame."""
    if min_length < 0 or frame_margin < 0 or not 0 <= frame_fraction <= 1:
        raise ValueError("invalid contour filter setting")
    accepted = []
    for path in paths:
        points = path["points"]
        if len(points) < 2 or path_length(points) < min_length:
            continue
        border_count = sum(
            x < frame_margin or x >= width - frame_margin or
            y < frame_margin or y >= height - frame_margin
            for x, y in points
        )
        if border_count / len(points) >= frame_fraction:
            continue
        accepted.append(path)
    return accepted
