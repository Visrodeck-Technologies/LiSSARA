"""Optional Anime2Sketch inference adapter.

Anime2Sketch source is loaded from a user-provided checkout so this package
does not vendor the model. PyTorch is imported only when inference is asked
for. The caller must supply a checkpoint and accept its terms independently.
"""

from __future__ import annotations

import functools
import importlib.util
import os
from pathlib import Path
import sys
from typing import Optional


class Anime2SketchUnavailable(RuntimeError):
    """Raised when optional model files or dependencies are not available."""


class Anime2SketchBackend:
    """Run official Anime2Sketch U-Net weights on aspect-preserving tiles.

    The official repo uses 512-square resizing by default. This adapter sends
    512x512 crops at source scale, with reflected padding at image borders and
    weighted overlap blending. Coordinates therefore remain in source pixels.
    """

    def __init__(self, checkpoint: str, source_repo: Optional[str] = None,
                 variant: str = "default", tile_size: int = 512,
                 overlap: int = 64):
        self.checkpoint = Path(checkpoint).expanduser().resolve()
        repo = source_repo or os.environ.get("ANIME2SKETCH_REPO")
        self.source_repo = Path(repo).expanduser().resolve() if repo else None
        self.variant = variant
        self.tile_size = int(tile_size)
        self.overlap = int(overlap)
        self._model = None
        self._torch = None
        self._np = None
        if variant not in ("default", "improved"):
            raise ValueError("variant must be 'default' or 'improved'")
        if self.tile_size != 512:
            raise ValueError("Anime2Sketch checkpoint expects 512-pixel tiles")
        if not 0 <= self.overlap < self.tile_size // 2:
            raise ValueError("overlap must be between 0 and 255 pixels")

    def _load(self):
        if self._model is not None:
            return
        if not self.checkpoint.is_file():
            raise Anime2SketchUnavailable(f"checkpoint not found: {self.checkpoint}")
        if self.source_repo is None or not self.source_repo.is_dir():
            raise Anime2SketchUnavailable(
                "Anime2Sketch source checkout not found; set ANIME2SKETCH_REPO"
            )
        try:
            import numpy as np
            import torch
        except ImportError as exc:
            raise Anime2SketchUnavailable(
                "Optional inference requires NumPy and PyTorch; classical processing remains available"
            ) from exc

        model_file = self.source_repo / "model.py"
        if not model_file.is_file():
            raise Anime2SketchUnavailable(f"model.py not found in {self.source_repo}")
        spec = importlib.util.spec_from_file_location("_lissara_anime2sketch_model", model_file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        norm = functools.partial(
            torch.nn.InstanceNorm2d, affine=False, track_running_stats=False
        )
        model = module.UnetGenerator(3, 1, 8, 64, norm_layer=norm, use_dropout=False)
        if self.variant == "improved":
            base = model.model.model[1]
            for _ in range(6):
                inc, outc = base.model[5].in_channels, base.model[5].out_channels
                base.model[5] = module.Upsample(inc, outc)
                base = base.model[3]

        # PyTorch >=2.6 defaults to weights_only=True. Keep deserialization
        # restricted to tensor state dictionaries across compatible versions.
        try:
            state = torch.load(self.checkpoint, map_location="cpu", weights_only=True)
        except TypeError:
            state = torch.load(self.checkpoint, map_location="cpu")
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        if any(key.startswith("module.") for key in state):
            state = {key.removeprefix("module."): value for key, value in state.items()}
        model.load_state_dict(state)
        model.eval()
        self._model, self._torch, self._np = model, torch, np

    @staticmethod
    def _starts(length: int, tile: int, step: int):
        if length <= tile:
            return [0]
        starts = list(range(0, length - tile + 1, step))
        if starts[-1] != length - tile:
            starts.append(length - tile)
        return starts

    def extract(self, rgb):
        """Return a float32 sketch-confidence array in original image size.

        Input is an HxWx3 uint8 RGB NumPy array. A value near 1 denotes dark
        extracted sketch strokes, matching the model's tanh output convention.
        """
        self._load()
        np, torch = self._np, self._torch
        if rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError("rgb must have shape (height, width, 3)")
        h, w = rgb.shape[:2]
        tile, overlap = self.tile_size, self.overlap
        step = tile - overlap
        xs, ys = self._starts(w, tile, step), self._starts(h, tile, step)
        accum = np.zeros((h, w), dtype=np.float32)
        weights = np.zeros((h, w), dtype=np.float32)
        axis = np.ones(tile, dtype=np.float32)
        if overlap:
            ramp = np.linspace(0.0, 1.0, overlap + 2, dtype=np.float32)[1:-1]
            axis[:overlap], axis[-overlap:] = ramp, ramp[::-1]
        window = np.outer(axis, axis)
        with torch.inference_mode():
            for y in ys:
                for x in xs:
                    crop = rgb[y:min(y + tile, h), x:min(x + tile, w)]
                    ph, pw = tile - crop.shape[0], tile - crop.shape[1]
                    if ph or pw:
                        crop = np.pad(crop, ((0, ph), (0, pw), (0, 0)), mode="reflect")
                    tensor = torch.from_numpy(
                        np.ascontiguousarray(crop.transpose(2, 0, 1))
                    ).float().div_(127.5).sub_(1.0).unsqueeze(0)
                    prediction = self._model(tensor).squeeze().cpu().numpy()
                    confidence = (1.0 - prediction) * 0.5
                    vh, vw = min(tile, h - y), min(tile, w - x)
                    blend = window[:vh, :vw]
                    accum[y:y + vh, x:x + vw] += confidence[:vh, :vw] * blend
                    weights[y:y + vh, x:x + vw] += blend
        return accum / np.maximum(weights, 1e-8)
