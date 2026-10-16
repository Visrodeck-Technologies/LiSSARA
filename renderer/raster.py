"""Optional raster preview generation via CairoSVG.

CairoSVG is listed as a dependency but requires the native ``cairo`` library
to be present on the system. Windows environments (as in this repo's CI/local
setup) often do not have it, so PNG output must be treated as an optional
feature.

The module returns a well-defined exception when the backend is unavailable
and never crashes with an unhandled import error during module import. Tests
skip gracefully if the native backend is missing.
"""
from __future__ import annotations

from typing import Optional


class RasterBackendUnavailable(RuntimeError):
    """Raised when PNG rasterisation is requested but CairoSVG/cairo is absent."""


def has_raster_backend() -> bool:
    """Return ``True`` if CairoSVG can be imported *and* its native cairo DLLs
    are loadable.

    Importing ``cairosvg`` causes it to attempt to load its C back-end
    immediately. The check therefore tries to import and returns False on the
    first (predictable) OSError.
    """
    try:
        import cairosvg  # noqa: F401
    except Exception:
        return False
    return True


def svg_to_png(
    svg_content: str,
    path: Optional[str] = None,
    scale: float = 1.0,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> bytes:
    """Convert SVG to PNG bytes or write to ``path``.

    Args:
        svg_content: SVG markup as a string.
        path: If provided, write the PNG to this filesystem path.
        scale: Optional scaling factor applied to the output.
        width, height: Explicit pixel dimensions (overrides ``scale``).

    Returns:
        Raw PNG bytes.

    Raises:
        RasterBackendUnavailable: If CairoSVG or the native cairo library is not
            available.
        ValueError: If ``scale`` is not positive or dimensions are invalid.

    Implementation note:
        The function defers importing ``cairosvg`` until runtime to avoid
        propagating the backend import failure to callers that only need SVG.
    """
    try:
        import cairosvg
    except Exception as exc:  # noqa: BLE001
        raise RasterBackendUnavailable(f"CairoSVG backend unavailable: {exc}") from exc

    if scale <= 0.0:
        raise ValueError("scale must be > 0")
    if width is not None and width <= 0:
        raise ValueError("width must be > 0")
    if height is not None and height <= 0:
        raise ValueError("height must be > 0")

    kwargs = {"scale": scale}
    if width is not None:
        kwargs["output_width"] = width
    if height is not None:
        kwargs["output_height"] = height
    if path is not None:
        kwargs["output_path"] = path

    try:
        png_data = cairosvg.svg2png(bytestring=svg_content.encode("utf-8"), **kwargs)
    except Exception as exc:  # noqa: BLE001
        raise RasterBackendUnavailable(f"CairoSVG backend unavailable: {exc}") from exc

    return png_data if png_data is not None else b""
