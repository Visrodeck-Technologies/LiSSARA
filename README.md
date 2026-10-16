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

## How LiSSARA Works

LiSSARA combines classical image processing with computational geometry. It does not need to understand the semantic meaning of an illustration to reconstruct its visible line structure.

### Edge Detection

An image contains changes in brightness, colour and local texture. Edge detection identifies locations where image intensity changes significantly, helping reveal boundaries and line work.

LiSSARA uses edge extraction as a starting point for identifying the illustration's visible contours. The resulting edge map is a representation of image boundaries, not yet a mathematical drawing.

Edge detection can produce fragmented lines, unwanted edges and closely spaced responses around thick strokes. These must be handled during subsequent processing.

### Contour Tracing

Edge pixels are organised into ordered paths. Tracing attempts to follow connected line structures, separating independent contours rather than connecting unrelated image regions.

Filtering and gap handling help remove short fragments and bridge selected discontinuities. Their effectiveness depends on the input image and processing parameters.

### Cubic Bézier Fitting

The traced paths contain discrete points. LiSSARA approximates these paths using cubic Bézier curves.

A cubic Bézier segment is defined by four control points:

- \(P_0\): starting point.
- \(P_1\): first control point, influencing the departure direction.
- \(P_2\): second control point, influencing the arrival direction.
- \(P_3\): ending point.

Its parametric representation is:

\[
B(t)=(1-t)^3P_0+3(1-t)^2tP_1+
3(1-t)t^2P_2+t^3P_3
\]

where:

\[
0\leq t\leq1
\]

The x- and y-coordinates can each be expressed as cubic polynomials in \(t\). This is why a reconstructed path can be inspected as mathematical equations rather than merely as pixels.

A contour may require many Bézier segments to follow its shape accurately. LiSSARA fits and joins segments in sequence while retaining separate paths for independent contours.

### Interactive Mathematical Plotting

The fitted curves are displayed on a graph using their control points and mathematical geometry. The graph lets users inspect the result, select individual paths, navigate segments and examine the corresponding equations.

Changing the graph view does not change the underlying reconstruction. Curve visibility and display colours control presentation rather than the mathematical geometry itself.

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
