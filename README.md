# LiSSARA Core

### Mathematical Reconstruction of Illustrations

> *Dedicated to Cute Anime Girls.*  
> Please refrain from using LiSSARA Core for any other purpose.  

<table>
  <tr>
    <td align="center" width="50%">
      <img
        src="assets\ouushi.webp"
        alt="LiSSARA Core — Graph Calculator"
        width="100%"
      />
    </td>
    <td align="center" width="50%">
      <img
        src="assets\sexynoona.webp"
        alt="LiSSARA Core — Image Reconstruction"
        width="100%"
      />
    </td>
  </tr>
</table>
LiSSARA Core transforms illustrations into mathematical curves that can be explored, inspected and manipulated on an interactive graph.

Upload an image. Let LiSSARA analyse its edges. Explore the resulting curves and their equations.

## Installation

### Using Emtypyie.cli

LiSSARA Core is intended to be distributed through [Emtypyie.cli](https://github.com/emtypyie/Emtypyie.cli), the Emtypyie project manager.

Install Emtypyie.cli on Windows:

```powershell
winget install emtypyie.cli
```

Alternatively, install it through npm:

```powershell
npm install -g emtypyie-cli
```

Then install LiSSARA Core through the project manager:

```powershell
emtypyie /get lissara
```

The project package and setup script handle the application installation and its required runtime components. Once installed, launch LiSSARA Core using the installed application shortcut or the entry point provided by the package.

See the [documentation](https://github.com/emtypyie/Emtypyie.cli) for package-manager commands and updates.

### Running from source

For development or running directly from the repository:

```powershell
git clone https://github.com/emtypyie/LiSSARA.git
cd LiSSARA

py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe launch_gui.py
```

## Getting Started

### 1. Load an illustration

Open LiSSARA Core and select **Upload Image**. You can choose an image file, drag and drop an image into the upload area, or paste an image from your clipboard.

Select **Analyse Image** to begin reconstruction.

### 2. Explore the graph

When analysis finishes, LiSSARA plots the reconstructed curves on its interactive Cartesian graph.

Use the graph to:

- Zoom in and out with the mouse wheel.
- Pan around the reconstruction.
- Fit the entire reconstruction into view.
- Reset the graph view.
- Toggle the original image and detected edge map.
- Show or hide individual curves.
- Change the colour of individual curves.

Reconstructed curves are black by default. Each curve can be assigned its own colour without changing the others.

### 3. Inspect the mathematics

Select a curve in the expression panel to inspect its mathematical representation.

LiSSARA displays the numerical parametric equations, cubic Bézier segments, control points and parameter domain. Paths made of multiple segments can be inspected segment by segment.

Each segment represents a portion of the reconstructed contour. The collection of segments approximates the original image's detected line structure.

### 4. Export your work

Use the export panel to save the mathematical reconstruction.

**Equation JSON — `equation.json`**

Exports the reconstructed paths, segment definitions, Bézier control points, polynomial coefficients and parameter domains as structured mathematical data.

**Vector SVG — `.svg`**

Exports the reconstructed curves as vector paths. The geometry can be opened in a vector editor, scaled without raster pixelation, or used in other graphics workflows.

JSON is intended for accessing the underlying mathematical representation. SVG is intended for using the reconstructed vector artwork.

## References & Research

LiSSARA Core builds on established work in computer vision, curve geometry and vector graphics. The following references provide background for the techniques used in the project and related research.

### Edge Detection & Image Processing

1. **Canny, J. (1986).** *A Computational Approach to Edge Detection.* IEEE Transactions on Pattern Analysis and Machine Intelligence, 8(6), 679–698.  
   [Read the paper — DOI: 10.1109/TPAMI.1986.4767851](https://doi.org/10.1109/TPAMI.1986.4767851)

   Foundational research on edge detection, including detection accuracy, edge localisation and reducing multiple responses to a single edge.

2. **OpenCV — Edge Detection Using OpenCV.**  
   [Read the tutorial](https://opencv.org/edge-detection-using-opencv/)

   A practical reference for Canny, Sobel and Laplacian edge-detection methods.

### Curve Approximation & Mathematical Geometry

3. **Pomax — A Primer on Bézier Curves.**  
   [Read the interactive primer](https://pomax.github.io/bezierinfo/)

   A detailed reference covering Bézier curves, Bernstein polynomials, control points, derivatives, subdivision, curve fitting and geometric properties.

4. **Douglas, D. H., & Peucker, T. K. (1973).** *Algorithms for the Reduction of the Number of Points Required to Represent a Digitized Line or Its Caricature.* Cartographica, 10(2), 112–122.  
   [Read the paper — DOI: 10.3138/FM57-6770-U75U-7727](https://doi.org/10.3138/FM57-6770-U75U-7727)

   Foundational work on reducing the number of points needed to represent a line while retaining its overall shape. Relevant background for contour simplification.

5. **Encyclopedia of Mathematics — Bézier Curve.**  
   [Read the mathematical reference](https://encyclopediaofmath.org/index.php?title=B%C3%A9zier_curve)

   A concise mathematical treatment of Bézier curves as parametric polynomials defined by control points.

### Vector Graphics & Path Representation

6. **W3C — Scalable Vector Graphics (SVG) 2: Paths.**  
   [Read the specification](https://www.w3.org/TR/SVG/latest/paths.html)

   The specification for SVG path commands, including cubic Bézier geometry represented by the `C` command used for vector-path export.

### Related Research: Anime Line-Art Extraction

7. **Xiang, X., Liu, D., Yang, X., Zhu, Y., Shen, X., & Allebach, J. P. (2021).** *Adversarial Open Domain Adaptation for Sketch-to-Photo Synthesis.*  
   [Read the paper on arXiv](https://arxiv.org/abs/2104.05703)

8. **Anime2Sketch — Sketch Extractor for Illustration, Anime Art and Manga.**  
   [Research implementation and project documentation](https://github.com/Mukosame/Anime2Sketch)

   Related work on extracting sketch-like line art from illustrations. Anime2Sketch is an optional research direction for LiSSARA; its pretrained model is not part of the default classical reconstruction workflow.

---

*These resources are provided for technical background and further study. Their inclusion does not imply that LiSSARA Core implements every referenced method or reproduces the results of the cited research.*

## What to Expect

LiSSARA produces an approximation of an illustration's line structure, not a guaranteed pixel-perfect reconstruction.

Results depend on image resolution, contrast, line thickness, overlapping details and the complexity of the source illustration. Fine hair strands, textured shading, crossed lines and low-contrast details can be difficult to separate reliably.

The number of reconstructed paths and Bézier segments depends on the image and the fitting parameters. More segments can represent detail more closely but also create a more complex mathematical representation.

**Current scope:** edge-based line reconstruction and mathematical curve plotting. Flat-colour region segmentation and flat-colour reconstruction are not included in the current version and may be explored in a later release.

## Project

**LiSSARA Core**  
Mathematical Reconstruction of Illustrations

Engineered By Emtypyie&Co

All Rights Reserved.
