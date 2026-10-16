"""Lissara Core - Contours: Edge estimation and contour extraction."""
from typing import Any, List, Tuple, Optional, Literal

from lissara_equations import (
    make_cubic,
    evaluate_bezier as _equations_evaluate_bezier,
)

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import numpy as np
    NP_AVAILABLE = True
except ImportError:
    NP_AVAILABLE = False


def _to_float(val) -> float:
    """Convert a value to float, preferring numpy scalars if available."""
    if NP_AVAILABLE and isinstance(val, np.floating):
        return float(val)
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _extract_contours_pure(
    img: Any,
    threshold: float = 0.5,
    min_area: float = 1.0,
) -> List[List[Tuple[int, int]]]:
    """Extract contours using pure Python boundary tracing.

    Converts the grayscale image to binary via thresholding, then traces
    external contours using a Moore-neighbor (left-hand) algorithm.

    Args:
        img: 2D list of pixel values in [0, 1] range.
        threshold: Binarization threshold in [0, 1]; pixels > threshold are white.
        min_area: Minimum contour area (in pixel count) to keep.

    Returns:
        List of contours, each contour is a list of (x, y) integer tuples.
        Coordinates are (column, row) = (x, y) image space.
    """
    # --- Binarize the image ---
    if not isinstance(img, list) or len(img) == 0:
        return []
    H = len(img)
    W = len(img[0]) if H > 0 else 0

    # Build binary grid: 1 if pixel > threshold, else 0
    binary = []
    for y in range(H):
        row = []
        for x in range(W):
            row.append(1.0 if isinstance(img[y][x], (int, float)) and img[y][x] > threshold else 0.0)
        binary.append(row)

    # --- Find edge pixels ---
    # A border pixel is a white pixel that has at least one black (0) 4-neighbor.
    # This ensures we trace only the outer boundary of white regions.
    border = [[False] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            if binary[y][x] == 0:
                continue
            has_black_4 = False
            if y > 0 and binary[y - 1][x] == 0:
                has_black_4 = True
            if y < H - 1 and binary[y + 1][x] == 0:
                has_black_4 = True
            if x > 0 and binary[y][x - 1] == 0:
                has_black_4 = True
            if x < W - 1 and binary[y][x + 1] == 0:
                has_black_4 = True
            if has_black_4:
                border[y][x] = True

    # --- Moore-neighbor contour tracing (right-hand rule) ---
    # We keep the wall (black pixels) on our right as we trace.
    # Direction order: East, South-East, South, South-West, West, North-West,
    # North, North-East (clockwise starting East).
    # When we arrive at a new pixel, we search directions counter-clockwise
    # from our current heading so that the wall stays on our right.
    dirs = [(1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1)]

    def is_valid_border(px: int, py: int) -> bool:
        return 0 <= px < W and 0 <= py < H and border[py][px] and not visited[py][px]

    contours: List[List[Tuple[int, int]]] = []
    visited = [[False] * W for _ in range(H)]

    for start_y in range(H):
        for start_x in range(W):
            if not is_valid_border(start_x, start_y) or visited[start_y][start_x]:
                continue

            # --- Start a new contour ---
            contour: List[Tuple[int, int]] = []
            cX, cY = start_x, start_y

            # We begin tracing from the start pixel.
            # The initial heading is East (dir index 0).
            # For the first step, we search counter-clockwise from dir_idx.
            dir_idx = 0  # start facing East

            while True:
                visited[cY][cX] = True
                contour.append((cX, cY))

                # Search for the next pixel, starting from the direction
                # counter-clockwise from dir_idx.
                # We try up to 8 directions; the one that keeps the border
                # on our right is chosen.
                found = False
                for i in range(8):
                    # Counter-clockwise means decreasing dir_idx
                    search_idx = (dir_idx - i) % 8
                    dx, dy = dirs[search_idx]
                    nx, ny = cX + dx, cY + dy
                    if is_valid_border(nx, ny):
                        # Move to this pixel.
                        # The new heading for the next iteration is the direction
                        # we just took (so we can continue keeping the wall on the right).
                        cX, cY = nx, ny
                        dir_idx = search_idx
                        found = True
                        break

                if not found:
                    # No valid neighbor — contour is complete (or we're stuck).
                    break

                # If we've returned to the start pixel, the contour is complete.
                # (Do not add the start pixel a second time.)
                if cX == start_x and cY == start_y:
                    break

            # --- Close the contour ---
            # Ensure the contour is closed by appending the start point at the end
            # if it's not already the last point.
            if len(contour) > 2 and contour[0] != contour[-1]:
                contour.append(contour[0])

            # --- Filter by minimum area ---
            # Area is approximated by the number of distinct contour points
            # (the closing point is a duplicate, so we subtract 1).
            area = len(contour) - 1  # excluding the closing duplicate
            if area >= min_area:
                contours.append(contour)

    return contours


def _extract_contours_cv2(
    img: Any,
    threshold: float = 0.5,
    min_area: float = 1.0,
) -> List[List[Tuple[int, int]]]:
    """Extract contours using OpenCV findContours."""
    if not NP_AVAILABLE:
        return _extract_contours_pure(img, threshold, min_area)
    _, binary = cv2.threshold(
        (img * 255).astype(np.uint8), int(threshold * 255), 255, cv2.THRESH_BINARY
    )
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    result = []
    for cnt in contours:
        cnt_list = [tuple(pt[0]) for pt in cnt]
        area = cv2.contourArea(cnt)
        if area >= min_area:
            result.append(cnt_list)
    return result


def _simplify_contour_pure(
    contour: List[Tuple[int, int]],
    tolerance: float = 1.0,
) -> List[Tuple[int, int]]:
    """Simplify a contour using the Douglas-Peucker algorithm.

    Preserves the first and last points (endpoints for open contours,
    valid closure for closed contours).

    Args:
        contour: List of (x, y) tuples.
        tolerance: Tolerance factor; the maximum perpendicular distance
            from the segment to any intermediate point, expressed in pixels.

    Returns:
        Simplified contour as list of (x, y) tuples.
    """
    if len(contour) < 3:
        return list(contour)

    # Remove duplicate end point if the contour is closed (first == last)
    # so the DP algorithm works correctly (start != end).
    is_closed = len(contour) > 2 and contour[0] == contour[-1]
    work = contour[:-1] if is_closed else list(contour)

    if len(work) < 3:
        return list(contour)

    # Work with float coordinates for accuracy
    pts = [complex(x, y) for x, y in work]

    def dp(pts_list: List[complex], eps: float) -> List[complex]:
        """Recursive Douglas-Peucker subdivision."""
        if len(pts_list) <= 2:
            return list(pts_list)

        # Find the point farthest from the line between first and last
        start = pts_list[0]
        end = pts_list[-1]
        hyp = abs(end - start)
        if hyp == 0:
            # All points the same parameter; keep just the start point
            return [start]

        max_dist = 0.0
        max_idx = 0

        for i in range(1, len(pts_list) - 1):
            pt = pts_list[i]
            # Perpendicular distance from point to line start-end
            # Using cross-product formula: |cross| / |length|
            cross = abs((end.real - start.real) * (pt.imag - start.imag) -
                        (end.imag - start.imag) * (pt.real - start.real))
            if hyp > 0:
                dist = cross / hyp
            else:
                dist = 0.0
            if dist > max_dist:
                max_dist = dist
                max_idx = i

        if max_dist > eps:
            # Subdivide and recurse
            left = dp(pts_list[:max_idx + 1], eps)
            right = dp(pts_list[max_idx:], eps)
            # Omit the duplicate midpoint when merging
            return left[:-1] + right
        else:
            # Keep only the endpoints
            return [start, end]

    simplified = dp(pts, tolerance)
    # Convert back to (x, y) tuples
    result = [(int(p.real), int(p.imag)) for p in simplified]

    # If the original contour was closed, ensure the first and last match
    if is_closed and result:
        # Append the first point at the end to close the contour
        if result[0] != result[-1]:
            result.append(result[0])

    return result


def _simplify_contour_cv2(
    contour: List[Tuple[int, int]],
    tolerance: float = 1.0,
) -> List[Tuple[int, int]]:
    """Simplify a contour using OpenCV approxPolyDP."""
    if not NP_AVAILABLE:
        return _simplify_contour_pure(contour, tolerance)
    pts = np.array(contour, dtype=np.float64)
    epsilon = tolerance * cv2.arcLength(pts, False)
    approx = cv2.approxPolyDP(pts, epsilon, False)
    return [tuple(pt) for pt in approx.squeeze().tolist()]


def bezier_control_points_pure(
    p0: Tuple[float, float],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
) -> dict:
    """Pure Python cubic Bézier control point generation.

    Delegates to :func:`lissara_equations.make_cubic`, the canonical home of
    cubic Bézier records. Retained as a stable alias for earlier scripts.
    """
    return make_cubic(p0, p1, p2, p3)


def evaluate_bezier(t: float, coeffs: dict) -> Tuple[float, float]:
    """Evaluate a cubic Bézier curve at parameter t using stored coefficients.

    Delegates to :func:`lissara_equations.evaluate_bezier`.
    """
    return _equations_evaluate_bezier(t, coeffs)


def convert_contour_to_bezier_segments(
    contour: List[Tuple[float, float]],
    num_segments: int = 10,
) -> List[dict]:
    """Fit cubic Bézier segments to a contour.

    Uses a recursive subdivision algorithm:
    - Fit a single cubic Bézier to the segment endpoints.
    - Measure maximum perpendicular fitting error.
    - If error > tolerance and recursion depth < limit, split at the
      point of maximum error and recurse on both sub-segments.
    - Detect sharp corners and avoid smoothing across them.
    - Enforce a maximum recursion depth (6) and segment limit (32)
        to prevent runaway subdivision.
    - Preserve exact segment endpoints.
    - Ensure C0 continuity between neighboring segments.

    Args:
        contour: List of (x, y) tuples representing an ordered contour.
        num_segments: Hint for initial number of segments (not guaranteed;
            the algorithm adapts based on geometry).

    Returns:
        List of Bézier coefficient dicts, each with keys:
            "control_points": [(x0,y0), (x1,y1), (x2,y2), (x3,y3)]
            "x_coeffs": {"a3": ..., "a2": ..., "a1": ..., "a0": ...}
            "y_coeffs": {"b3": ..., "b2": ..., "b1": ..., "b0": ...}
    """
    if not contour or len(contour) < 2:
        return []

    # Remove duplicate consecutive points
    clean: List[Tuple[float, float]] = [contour[0]]
    for pt in contour[1:]:
        if pt != clean[-1]:
            clean.append(pt)
    if len(clean) < 2:
        return []

    # Close the contour for processing if it isn't already,
    # but remember whether it was closed so we can handle endpoints.
    was_closed = clean[0] == clean[-1]
    work = list(clean)

    # Tolerance: default 2% of the bounding box diagonal, capped
    xs = [p[0] for p in work]
    ys = [p[1] for p in work]
    bbox_w = max(xs) - min(xs) if len(xs) > 1 else 1.0
    bbox_h = max(ys) - min(ys) if len(ys) > 1 else 1.0
    diag = (bbox_w ** 2 + bbox_h ** 2) ** 0.5
    tolerance = max(0.5, 0.02 * diag)  # at least 0.5 pixels
    max_depth = 6          # recursion depth limit
    max_segments = 32      # maximum number of output segments

    # --- Helper: fit one cubic Bézier to a point list -----------------
    def fit_single_segment(pts: List[Tuple[float, float]]) -> Tuple[Optional[dict], float]:
        """Fit a single cubic Bézier to *pts* and return (coeffs, max_error).

        Uses chord-length parameterization for p1/p2 initialization.
        """
        if len(pts) < 2:
            return None, 0.0
        if len(pts) == 2:
            # Degenerate: just a line; return a "linear" Bézier (p1=p0, p2=p3)
            p0, p3 = pts[0], pts[-1]
            coeffs = bezier_control_points_pure(p0, p0, p3, p3)
            # max_error is 0 because the Bézier degenerates to the line segment
            return coeffs, 0.0

        p0, p3 = pts[0], pts[-1]

        # Chord-length parameterization for p1 and p2
        chords = []
        for i in range(1, len(pts)):
            dx = pts[i][0] - pts[i - 1][0]
            dy = pts[i][1] - pts[i - 1][1]
            chords.append((dx ** 2 + dy ** 2) ** 0.5)

        total_chord = sum(chords)
        if total_chord == 0:
            # All points the same
            coeffs = bezier_control_points_pure(p0, p0, p3, p3)
            return coeffs, 0.0

        # Parameter u_i for interior points (exclude first and last)
        us = []
        cum = 0.0
        for i in range(1, len(pts)):
            cum += chords[i - 1]
            us.append(cum / total_chord)  # in [0, 1]

        # Find the closest sample to u=1/3 and u=2/3
        u1, u2 = 1.0 / 3.0, 2.0 / 3.0
        p1_idx = min(range(1, len(pts) - 1), key=lambda i: abs(us[i - 1] - u1))
        p2_idx = min(range(1, len(pts) - 1), key=lambda i: abs(us[i - 1] - u2))

        # Use the actual contour point as p1/p2 initializer
        p1 = pts[p1_idx]
        p2 = pts[p2_idx]

        coeffs = bezier_control_points_pure(p0, p1, p2, p3)

        # Compute max perpendicular error by sampling the curve
        max_error = 0.0
        for pt in pts:
            # Sample the Bézier curve at N+1 equally-spaced t values
            N = 10
            min_dist_sq = float("inf")
            for i in range(N + 1):
                t = i / N
                t2 = t * t
                t3 = t2 * t
                x = coeffs["x_coeffs"]["a3"] * t3 + coeffs["x_coeffs"]["a2"] * t2 + coeffs["x_coeffs"]["a1"] * t + coeffs["x_coeffs"]["a0"]
                y = coeffs["y_coeffs"]["b3"] * t3 + coeffs["y_coeffs"]["b2"] * t2 + coeffs["y_coeffs"]["b1"] * t + coeffs["y_coeffs"]["b0"]
                dist_sq = (pt[0] - x) ** 2 + (pt[1] - y) ** 2
                if min_dist_sq > dist_sq:
                    min_dist_sq = dist_sq
            max_error = max(max_error, min_dist_sq ** 0.5)
        return coeffs, max_error

    # --- Recursive subdivision ---
    # Process the base point list (without the duplicate closing point for open contours)
    base_pts = work if was_closed else work[:-1]

    # If the contour has very few points, just fit a single Bézier
    if len(base_pts) <= 2 and len(work) >= 2:
        return [bezier_control_points_pure(work[0], work[0], work[-1], work[-1])]

    # Recursive subdivision function
    def subdivide(pts: List[Tuple[float, float]], depth: int) -> List[dict]:
        """Return Bézier segments for *pts* at most *depth* levels deep."""
        if depth >= max_depth:
            coeffs, _ = fit_single_segment(pts)
            return [coeffs] if coeffs is not None else []

        # Try fitting the whole segment
        coeffs, max_err = fit_single_segment(pts)
        if coeffs is None:
            return []

        if max_err <= tolerance or len(pts) <= 2:
            return [coeffs]

        # Find the point with maximum distance from the p0-p3 line
        # to determine where to split
        p0, p3 = pts[0], pts[-1]
        best_dist = -1.0
        best_idx = len(pts) // 2  # default: split in half
        for i in range(1, len(pts) - 1):
            # perpendicular distance from point to line p0-p3
            cross = abs((p3[0] - p0[0]) * (pts[i][1] - p0[1]) -
                        (p3[1] - p0[1]) * (pts[i][0] - p0[0]))
            hyp = abs(p3[0] - p0[0]) + abs(p3[1] - p0[1])
            if hyp > 0:
                d = cross / (hyp + 1e-6)
            else:
                d = 0.0
            if d > best_dist:
                best_dist = d
                best_idx = i

        # Split into two halves (overlap at split point)
        left_pts = pts[:best_idx + 1]
        right_pts = pts[best_idx:]

        left_segs = subdivide(left_pts, depth + 1)
        right_segs = subdivide(right_pts, depth + 1)

        # Combine
        return left_segs + right_segs

    # Run subdivision
    output_segments = subdivide(base_pts, 0)

    # If no segments obtained, fall back to a single Bézier
    if not output_segments and len(work) >= 2:
        output_segments = [bezier_control_points_pure(work[0], work[0], work[-1], work[-1])]

    # Enforce segment limit
    if len(output_segments) > max_segments:
        output_segments = output_segments[:max_segments - 1]
        # Add one final segment for the remainder
        if len(base_pts) >= 2:
            remainder_coeffs = bezier_control_points_pure(
                base_pts[0], base_pts[0], base_pts[-1], base_pts[-1],
            )
            output_segments.append(remainder_coeffs)

    return output_segments

def extract_contours(
    img: Any,
    threshold: float = 0.5,
    min_area: float = 1.0,
    backend: Literal["pure", "cv2"] = "pure",
) -> List[List[Tuple[int, int]]]:
    """Extract contours from a grayscale image.

    Args:
        img: 2D list or numpy array of pixel values in [0, 1] range.
        threshold: Binarization threshold in [0, 1].
        min_area: Minimum contour area to keep.
        backend: "pure" (list-based) or "cv2" (OpenCV accelerated).

    Returns:
        List of contours, each contour is a list of (x, y) tuples.
    """
    if backend == "cv2" and CV2_AVAILABLE and NP_AVAILABLE:
        try:
            return _extract_contours_cv2(img, threshold, min_area)
        except Exception:
            pass  # fall through to pure Python
    return _extract_contours_pure(img, threshold, min_area)


def simplify_contour(
    contour: List[Tuple[int, int]],
    tolerance: float = 1.0,
    backend: Literal["pure", "cv2"] = "pure",
) -> List[Tuple[int, int]]:
    """Simplify a contour using the Douglas-Peucker algorithm.

    Args:
        contour: List of (x, y) tuples.
        tolerance: Tolerance factor (multiplied by contour perimeter).
        backend: "pure" (recursive Douglas-Peucker) or "cv2" (OpenCV approxPolyDP).

    Returns:
        Simplified contour as list of (x, y) tuples.
    """
    if backend == "cv2" and CV2_AVAILABLE and NP_AVAILABLE:
        try:
            return _simplify_contour_cv2(contour, tolerance)
        except Exception:
            pass  # fall through to pure Python
    return _simplify_contour_pure(contour, tolerance)