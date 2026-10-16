"""Lissara Core - Preprocessing: Image preprocessing, normalization, and parameter recording."""
from typing import List, Tuple


def _to_float(val) -> float:
    """Convert a value to float."""
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def load_image(path: str) -> List[List[float]]:
    """Load an image from file path.

    Returns a 2D list of pixel values (for RGB/RGBA, returns mean of channels).
    """
    from PIL import Image
    img = Image.open(path)
    arr = list(img.getdata())

    if img.mode == "RGBA":
        width, height = img.size
        result = []
        for y in range(height):
            row = []
            for x in range(width):
                idx = y * width + x
                r, g, b, a = arr[idx]
                gray = int(0.299 * r + 0.587 * g + 0.114 * b)
                row.append(gray / 255.0)
            result.append(row)
        return result
    elif img.mode == "RGB":
        width, height = img.size
        result = []
        for y in range(height):
            row = []
            for x in range(width):
                idx = y * width + x
                r, g, b = arr[idx]
                gray = int(0.299 * r + 0.587 * g + 0.114 * b)
                row.append(gray / 255.0)
            result.append(row)
        return result
    else:
        width, height = img.size
        result = []
        for y in range(height):
            row = []
            for x in range(width):
                val = arr[idx := y * width + x]
                if isinstance(val, tuple):
                    gray = int(sum(val) / len(val))
                else:
                    gray = val
                row.append(gray / 255.0)
            result.append(row)
        return result


def normalize_image(img: List[List[float]], target_size: Tuple[int, int] = None) -> List[List[float]]:
    """Normalize image to target size and format.

    Args:
        img: 2D list of pixel values in [0, 1] range.
        target_size: (width, height) to resize to. If None, keep original size.

    Returns:
        Normalized 2D list of float values.
    """
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
    else:
        result = []
        for row in img:
            result.append([_to_float(v) for v in row])
        return result


def record_preprocessing_params(params: dict):
    """Record preprocessing parameters for geometry preservation."""
    pass