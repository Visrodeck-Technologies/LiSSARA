"""Lissara Vectorization — image loading, normalization and adaptive fitting.

This package owns image-processing concerns and the contour-specific adaptive
Bézier fitter. All reusable curve mathematics (representation, evaluation,
single-segment fitting) is imported from :mod:`lissara_equations` so there is a
single source of truth.

The public names below are kept stable for existing callers and scripts:
``load_image``, ``normalize_image``, ``write_png``, ``bezier_control_points``,
``fit_bezier_segment``, ``fit_bezier_adaptive`` and ``contour_to_bezier_paths``.
"""

import struct
import zlib

from lissara_equations import (
    bezier_control_points,
    evaluate_bezier,
    fit_cubic_segment,
    make_cubic,
)


def write_png(path, pixels):
    """Write an 8-bit RGB image (rows of RGB byte triples) as a PNG."""
    height = len(pixels)
    width = len(pixels[0]) if height else 0
    if not width or any(len(row) != width for row in pixels):
        raise ValueError("pixels must be a non-empty rectangular RGB image")

    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload +
                struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))

    scanlines = bytearray()
    for row in pixels:
        scanlines.append(0)  # PNG filter: None
        for pixel in row:
            if len(pixel) != 3:
                raise ValueError("each pixel must contain three RGB channels")
            scanlines.extend(max(0, min(255, int(channel))) for channel in pixel)
    data = (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes(scanlines))) + chunk(b"IEND", b""))
    with open(path, "wb") as output:
        output.write(data)


def load_image(path):
    """Load an image from file path."""
    try:
        from PIL import Image as PILImage
        img = PILImage.open(path)
        arr = list(img.getdata())
        if img.mode == "RGBA":
            width, height = img.size
            result = []
            for y in range(height):
                row = []
                for x in range(width):
                    idx = y * width + x
                    r, g, b, a = arr[idx]
                    row.append((r + g + b) / 3 / 255.0)
                result.append(row)
            return result
        else:
            width, height = img.size
            result = []
            for y in range(height):
                row = []
                for x in range(width):
                    idx = y * width + x
                    r, g, b = arr[idx]
                    row.append((r + g + b) / 3 / 255.0)
                result.append(row)
            return result
    except ImportError:
        pass
    except Exception:
        pass
    # Fallback minimal reader
    with open(path, "rb") as f:
        data = f.read()
    sig = data[:8]
    expect = b"\x89PNG\r\n\x1a\n"
    if sig != expect:
        raise ValueError("Not a PNG file")
    pos = 8
    width = height = bit_depth = color_type = None
    raw_data = b""
    while pos < len(data):
        if pos + 4 > len(data):
            break
        chunk_len = struct.unpack(">I", data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8].decode("ascii", errors="replace")
        pos += 8
        if pos + chunk_len + 4 > len(data):
            break
        chunk_data = data[pos:pos + chunk_len]
        if chunk_type == "IHDR":
            parsed = struct.unpack(">IIBBBBB", chunk_data)
            width, height, bit_depth, color_type = parsed[:4]
        elif chunk_type == "IDAT":
            raw_data += chunk_data
        elif chunk_type == "IEND":
            break
        pos += chunk_len + 4
    if width is None or height is None or raw_data is None:
        raise ValueError("Malformed PNG file")
    try:
        raw_data = zlib.decompress(raw_data)
    except zlib.error as e:
        raise ValueError(f"Failed to decompress: {e}")
    # Sample layout per PNG colour type: grey, RGB, grey+alpha, RGBA.
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    bytes_per_row = width * channels + 1
    expected_size = bytes_per_row * height
    if len(raw_data) != expected_size:
        raise ValueError(f"Data size mismatch: {len(raw_data)} vs {expected_size}")
    # Reverse PNG row filters before interpreting samples. The former fallback
    # silently treated filtered bytes as pixels, corrupting image geometry.
    stride = width * channels
    decoded = bytearray()
    prior = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        filter_type = raw_data[start]
        scan = bytearray(raw_data[start + 1:start + 1 + stride])
        for i in range(stride):
            left = scan[i - channels] if i >= channels else 0
            up = prior[i]
            upper_left = prior[i - channels] if i >= channels else 0
            if filter_type == 1:
                scan[i] = (scan[i] + left) & 255
            elif filter_type == 2:
                scan[i] = (scan[i] + up) & 255
            elif filter_type == 3:
                scan[i] = (scan[i] + ((left + up) >> 1)) & 255
            elif filter_type == 4:
                p = left + up - upper_left
                pa, pb, pc = abs(p-left), abs(p-up), abs(p-upper_left)
                predictor = left if pa <= pb and pa <= pc else (up if pb <= pc else upper_left)
                scan[i] = (scan[i] + predictor) & 255
            elif filter_type != 0:
                raise ValueError(f"Unsupported PNG filter: {filter_type}")
        decoded.extend(scan)
        prior = scan
    result = []
    for y in range(height):
        row_start = y * stride
        row_data = decoded[row_start : row_start + stride]
        row = []
        for x in range(width):
            idx = x * channels
            if color_type in (2, 6):
                # RGB (and RGBA): mean of the colour channels.
                val = (row_data[idx] + row_data[idx + 1] + row_data[idx + 2]) / 3
            else:
                # Grey (and grey+alpha): the first byte is the value.
                val = row_data[idx]
            row.append(val / 255.0)
        result.append(row)
    return result

def normalize_image(img, target_size=None):
    if target_size:
        orig_h = len(img)
        orig_w = len(img[0]) if orig_h > 0 else 0
        new_h, new_w = target_size
        result = []
        for y in range(new_h):
            src_y = int(y * orig_h / new_h)
            src_y = min(src_y, orig_h - 1)
            row = []
            for x in range(new_w):
                src_x = int(x * orig_w / new_w)
                src_x = min(src_x, orig_w - 1)
                row.append(img[src_y][src_x])
            result.append(row)
        return result
    return [list(row) for row in img]


def fit_bezier_segment(points):
    """Fit a single cubic Bézier segment to ordered points.

    Delegates to :func:`lissara_equations.fit_cubic_segment`; the endpoint
    interpolation, chord-length parameterization and max-error measurement are
    identical to the historical implementation.

    Args:
        points: List of (x, y) tuples, length >= 2.

    Returns:
        Tuple of (coeffs_dict, max_error), or (None, 0.0) when unfit.
    """
    return fit_cubic_segment(points)


def fit_bezier_adaptive(contour, tolerance=None, max_segments=32, max_depth=6):
    """Adaptively fit cubic Bézier segments to a contour with recursive subdivision.

    Args:
        contour: List of (x, y) tuples representing an ordered contour.
        tolerance: Maximum fitting error (pixels). If None, defaults to 2% of bbox diagonal.
        max_segments: Maximum number of output Bézier segments.
        max_depth: Maximum recursion depth for subdivision.

    Returns:
        List of Bézier coefficient dicts, each with "control_points", "x_coeffs", "y_coeffs".
    """
    if not contour or len(contour) < 2:
        return []

    clean = [contour[0]]
    for pt in contour[1:]:
        if pt != clean[-1]:
            clean.append(pt)
    if len(clean) < 2:
        return []

    was_closed = len(clean) > 2 and clean[0] == clean[-1]
    if was_closed:
        if max_segments < 2:
            raise ValueError("Closed contours require max_segments >= 2")
        ring = clean[:-1]
        start = ring[0]
        # Split the ring opposite its start so neither fit is a zero-chord loop.
        pivot = max(range(1, len(ring)), key=lambda i:
                    (ring[i][0] - start[0]) ** 2 + (ring[i][1] - start[1]) ** 2)
        first_arc = ring[:pivot + 1]
        second_arc = ring[pivot:] + [start]
        first_budget = max(1, max_segments // 2)
        second_budget = max_segments - first_budget
        left = fit_bezier_adaptive(first_arc, tolerance, first_budget, max_depth)
        right = fit_bezier_adaptive(second_arc, tolerance, second_budget, max_depth)
        segments = left + right
        if segments:
            # Preserve exact closure and C0 continuity at the shared split.
            for i in range(len(segments) - 1):
                cps = segments[i]["control_points"]
                next_cps = segments[i + 1]["control_points"]
                if cps[3] != next_cps[0]:
                    next_cps[0] = cps[3]
                    segments[i + 1] = make_cubic(*next_cps)
            if segments[-1]["control_points"][3] != start:
                cps = segments[-1]["control_points"]
                cps[3] = start
                segments[-1] = make_cubic(*cps)
        return segments
    work = list(clean)

    if tolerance is None:
        xs = [p[0] for p in work]
        ys = [p[1] for p in work]
        bbox_w = max(xs) - min(xs) if len(xs) > 1 else 1.0
        bbox_h = max(ys) - min(ys) if len(ys) > 1 else 1.0
        diag = (bbox_w ** 2 + bbox_h ** 2) ** 0.5
        tolerance = max(0.5, 0.02 * diag)

    def subdivide(pts, depth):
        if depth >= max_depth:
            coeffs, _ = fit_bezier_segment(pts)
            return [coeffs] if coeffs is not None else []

        coeffs, max_err = fit_bezier_segment(pts)
        if coeffs is None:
            return []
        if max_err <= tolerance or len(pts) <= 2:
            return [coeffs]

        p0, p3 = pts[0], pts[-1]
        best_dist = -1.0
        best_idx = len(pts) // 2
        for i in range(1, len(pts) - 1):
            cross = abs((p3[0] - p0[0]) * (pts[i][1] - p0[1]) -
                        (p3[1] - p0[1]) * (pts[i][0] - p0[0]))
            hyp = ((p3[0] - p0[0]) ** 2 + (p3[1] - p0[1]) ** 2) ** 0.5
            if hyp > 0:
                d = cross / hyp
            else:
                d = 0.0
            if d > best_dist:
                best_dist = d
                best_idx = i

        left_pts = pts[:best_idx + 1]
        right_pts = pts[best_idx:]

        left_segs = subdivide(left_pts, depth + 1)
        right_segs = subdivide(right_pts, depth + 1)

        return left_segs + right_segs

    base_pts = work

    if len(base_pts) <= 2 and len(work) >= 2:
        return [make_cubic(work[0], work[0], work[-1], work[-1])]

    output_segments = subdivide(base_pts, 0)

    if not output_segments and len(work) >= 2:
        output_segments = [make_cubic(work[0], work[0], work[-1], work[-1])]

    if len(output_segments) > max_segments:
        output_segments = output_segments[:max_segments - 1]
        if output_segments and len(base_pts) >= 2:
            remainder_start = output_segments[-1]["control_points"][3]
            remainder_coeffs = make_cubic(
                remainder_start, remainder_start, base_pts[-1], base_pts[-1],
            )
            output_segments.append(remainder_coeffs)

    return output_segments


def contour_to_bezier_paths(contours, tolerance=None, max_segments=32, max_depth=6):
    """Convert multiple contours to lists of Bézier segments.

    Args:
        contours: List of contours, each a list of (x, y) tuples.
        tolerance: Fitting tolerance per contour (or single value for all).
        max_segments: Max segments per contour.
        max_depth: Max recursion depth.

    Returns:
        List of lists of Bézier coefficient dicts (one list per contour).
    """
    results = []
    for contour in contours:
        segs = fit_bezier_adaptive(contour, tolerance, max_segments, max_depth)
        results.append(segs)
    return results
