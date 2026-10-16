"""Shared pytest fixtures for the Lissara test suite."""
from __future__ import annotations

import pytest
from PIL import Image, ImageDraw


@pytest.fixture
def synthetic_image(tmp_path):
    """A small black-on-white shape image (rectangle outline + ellipse outline).

    Kept tiny so the full reconstruction pipeline runs in well under a second
    during unit tests (the real image is reserved for the integration test).
    """
    path = tmp_path / "shape.png"
    image = Image.new("RGB", (96, 96), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([16, 16, 80, 80], outline="black", width=3)
    draw.ellipse([30, 30, 66, 66], outline="black", width=3)
    image.save(path)
    return path
