# Anime2Sketch integration notes

## Model and implementation

The optional `lissara_vectorization.anime2sketch.Anime2SketchBackend` wraps the official Anime2Sketch U-Net implementation loaded from a user-provided checkout. The source model is a 3-channel to 1-channel, 8-downsample U-Net generator with 64 base filters, InstanceNorm, skip connections, and a tanh output. Its `default` variant uses transpose-convolution upsampling; `improved` replaces those stages with resize/smoothing/convolution blocks. Inference only is supported.

The official test preprocessing converts to RGB, maps channels from `[0,255]` to `[-1,1]`, resizes directly to a square (512 by default), then scales model output back to the original dimensions. That square resize changes aspect ratio. Lissara instead runs source-scale 512-pixel tiles with reflected padding, 64-pixel overlap, weighted seam blending, and no global resize. Returned coordinates therefore match the original image dimensions. The supplied 1840 by 2991 image uses a 4 by 7 grid (28 tiles).

The official source `requirements.txt` points at development Git branches and includes Gradio, torchtext, requests, tqdm, and Kornia. Its README only says Python 3 and does not define a supported version range. The `test.py` and `data.py` path additionally uses torchvision, tqdm, and Kornia CLAHE; Lissara calls the official architecture in `model.py` directly and implements preprocessing itself, so the adapter needs only PyTorch and NumPy for inference. Pillow is used by the surrounding pipeline. PyTorch remains optional. Install a CPU build from the official [PyTorch install selector](https://pytorch.org/get-started/locally/) when needed; do not install a CUDA build unless the user explicitly chooses it. The project's current environment is CPython 3.13.13 on Windows x86-64. Current Windows PyTorch package availability is documented by [PyTorch on PyPI](https://pypi.org/project/torch/); CPU build selection must be confirmed at installation time.

## License and checkpoint status

The [Anime2Sketch repository](https://github.com/Mukosame/Anime2Sketch) code declares MIT licensing, copyright Xiaoyu Xiang (2021). The README links the default `netG.pth` to a public [Google Drive folder](https://drive.google.com/drive/folders/1Srf-WYUixK0wiUddc9y3pNKHHno5PN6R?usp=sharing) and `improved.bin` to [its Drive file](https://drive.google.com/file/d/1cf90_fPW-elGOKu5mTXT5N1dum-XY_46/view?usp=sharing). The repository and linked Drive pages expose no checkpoint-specific license, model card, or usage/redistribution terms. Public download availability does not establish those rights. Lissara did not download or use these weights, and no weight files are committed. Pretrained inference and `lineart_model.png` / `lineart_mask.png` remain blocked until checkpoint terms are provided or clarified by the rights holder.

If authorized checkpoint terms become available:

1. Clone the official repository and install the optional CPU PyTorch build with the official selector.
2. Download the desired checkpoint from the README's Google Drive link only after confirming its terms. Keep it in the ignored `.models/anime2sketch/` directory.
3. Initialize the adapter with the checkpoint path and `source_repo` set to the clone, e.g. `Anime2SketchBackend('.models/anime2sketch/netG.pth', source_repo='vendor/Anime2Sketch')`.
4. Threshold the resulting confidence map for a line mask and use it to guide the existing classical contour/region pipeline; never treat it as a semantic segmentation.

The checkout and checkpoint are intentionally user-provided. There is no auto-download and no training path. If imports, checkpoint loading, or inference fail, report the error and keep the classical OpenCV pipeline active.
