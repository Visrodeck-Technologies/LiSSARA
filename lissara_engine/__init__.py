class PathRecord:
    """Represents a path with records for rendering."""
    def __init__(self, records=None, path_id=None, path_type=None, closed=None,
                 segments=None, fill=None, stroke=None):
        self.records = records if records else []
        self.path_id = path_id
        self.path_type = path_type
        self.closed = closed
        self.segments = segments
        self.fill = fill
        self.stroke = stroke

    def add_record(self, record):
        self.records.append(record)

    def to_json(self):
        result = {"records": [r.to_dict() if hasattr(r, "to_dict") else r for r in self.records]}
        if self.path_id is not None:
            result["path_id"] = self.path_id
        if self.path_type is not None:
            result["path_type"] = self.path_type
        if self.closed is not None:
            result["closed"] = self.closed
        if self.segments is not None:
            result["segments"] = self.segments
        if self.fill is not None:
            result["fill"] = self.fill
        if self.stroke is not None:
            result["stroke"] = self.stroke
        return result

    def to_dict(self):
        return self.to_json()

    @classmethod
    def from_json(cls, data):
        records = data.get("records", [])
        instance = cls()
        for r in records:
            instance.records.append(r)
        return instance

    def export_svg_path(self):
        """Export path records as SVG path data."""
        segs = self.segments
        if segs is None:
            return ""
        # Determine format
        if isinstance(segs, list) and len(segs) > 0:
            first = segs[0]
            # Format: Bézier coefficient dicts with "control_points" key
            if isinstance(first, dict) and "control_points" in first:
                return self._export_bezier_segments(segs)
            # Format: list of pairs — [[x1, y1], [x2, y2], ...] or
            # [(x1, y1), (x2, y2), ...]. A flat [x1, y1, x2, y2, ...] list is
            # not accepted: testing `first` below raises for a scalar head.
            if all(isinstance(v, (int, float)) for v in first) and len(first) == 2:
                if all(isinstance(segs[i], (list, tuple)) and len(segs[i]) == 2
                       for i in range(min(3, len(segs)))):
                    return self._points_path(segs)
            # Format: list of segments where each segment is a list of (x, y) tuples
            # e.g., [[(0,0), (1,0), (0,1)]] or [[[0,0], [1,0], [0,1]]]
            elif isinstance(first, (list, tuple)) and len(first) > 0:
                # Check if first element is a tuple (x, y) or list [x, y]
                if isinstance(first[0], (int, float)):
                    # first element is a point [x, y] or (x, y)
                    # Could be list of points: [[x1, y1], [x2, y2], ...] or [(x1, y1), (x2, y2), ...]
                    if all(isinstance(segs[i], (list, tuple)) and len(segs[i]) == 2 for i in range(min(3, len(segs)))):
                        # List of pairs: [[x1, y1], [x2, y2], ...] or [(x1, y1), (x2, y2), ...]
                        return self._points_path(segs)
                    # List of segments where each segment has 2 points: [[[x1, y1], [x2, y2]], ...]
                    elif all(isinstance(segs[i], (list, tuple)) and len(segs[i]) > 0 for i in range(min(3, len(segs)))):
                        d = ""
                        for i, seg in enumerate(segs):
                            if i == 0 and len(seg) > 0:
                                x0, y0 = seg[0][0] if isinstance(seg[0], (list, tuple)) else seg[0]
                                d += f"M {x0} {y0}"
                            for j in range(1, len(seg)):
                                xj, yj = seg[j][0] if isinstance(seg[j], (list, tuple)) else seg[j]
                                d += f" L {xj} {yj}"
                        if self.closed:
                            d += " Z"
                        return d
                else:
                    # first element is neither int nor tuple/list of 2 - could be list of tuples (x,y)
                    # e.g., [[(0,0), (1,0), (0,1)]] - list of tuples within a segment
                    if all(isinstance(segs[i], (list, tuple)) for i in range(min(3, len(segs)))):
                        # Check if it's a list of tuples within a single segment
                        if len(segs) == 1 and all(isinstance(v, (tuple, list)) and len(v) == 2 for v in segs[0]):
                            # Single segment with points as tuples: [(0,0), (1839,0), (0,0)]
                            return self._points_path(segs[0])
                        # Multiple segments, each being a list of tuples
                        d = ""
                        for i, seg in enumerate(segs):
                            if i == 0 and len(seg) > 0:
                                for j, (x, y) in enumerate(seg):
                                    if j == 0:
                                        d += f"M {x} {y}"
                                    else:
                                        d += f" L {x} {y}"
                        if self.closed:
                            d += " Z"
                        return d
        return ""

    def _points_path(self, points) -> str:
        """``M``/``L`` path data for a flat list of points, closing when needed."""
        parts = []
        for index, point in enumerate(points):
            x, y = point[0], point[1]
            parts.append(f"M {x} {y}" if index == 0 else f" L {x} {y}")
        if self.closed:
            parts.append(" Z")
        return "".join(parts)

    def _export_bezier_segments(self, bezier_segments):
        """Export Bézier coefficient dicts as SVG path with C commands."""
        if not bezier_segments:
            return ""
        d_parts = []
        first_seg = bezier_segments[0]
        cps = first_seg["control_points"]
        x0, y0 = cps[0]
        d_parts.append(f"M {x0} {y0}")
        for seg in bezier_segments:
            cps = seg["control_points"]
            x1, y1 = cps[1]
            x2, y2 = cps[2]
            x3, y3 = cps[3]
            d_parts.append(f"C {x1} {y1} {x2} {y2} {x3} {y3}")
        if self.closed:
            d_parts.append("Z")
        return "".join(d_parts)


class MathScene:
    """Represents a mathematical scene with paths and metadata."""
    def __init__(self, width=0, height=0, paths=None, metadata=None):
        self.width = width
        self.height = height
        self.paths = paths if paths else []
        self.metadata = metadata if metadata else {}

    def add_path(self, path_record):
        self.paths.append(path_record)

    def to_json(self):
        return {
            "width": self.width,
            "height": self.height,
            "paths": [p.to_dict() if hasattr(p, "to_dict") else {"records": p.records} for p in self.paths],
            "metadata": self.metadata,
        }

    @classmethod
    def from_json(cls, data):
        instance = cls(
            width=data.get("width", 0),
            height=data.get("height", 0),
            metadata=data.get("metadata", {}),
        )
        paths_data = data.get("paths", [])
        for p in paths_data:
            path_record = PathRecord.from_json(p)
            instance.paths.append(path_record)
        return instance

    def export_svg(self, filepath=None):
        """Export the scene as SVG file or return as string."""
        from xml.sax.saxutils import quoteattr
        lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" viewBox="0 0 {self.width} {self.height}">']
        for path_record in self.paths:
            d = path_record.export_svg_path()
            if not d:
                continue
            fill = path_record.fill or {}
            stroke = path_record.stroke or {}
            fill_color = fill.get("color", "none") if path_record.closed else "none"
            stroke_color = stroke.get("color", "none")
            style = (f'fill:{fill_color};fill-opacity:{fill.get("opacity", 1)};'
                     f'stroke:{stroke_color};stroke-opacity:{stroke.get("opacity", 1)};'
                     f'stroke-width:{stroke.get("width", 1)}')
            lines.append(f'<path d={quoteattr(d)} style={quoteattr(style)} id={quoteattr(str(path_record.path_id or "path"))}/>')
        lines.append('</svg>')
        svg_str = "\n".join(lines)
        if filepath:
            with open(filepath, "w") as f:
                f.write(svg_str)
        return svg_str


def compute_pixel_loss(original, reconstructed):
    """Compute pixel-wise mean squared error loss."""
    total = 0.0
    n = 0
    for y in range(len(original)):
        for x in range(len(original[y])):
            o = original[y][x]
            r = reconstructed[y][x] if y < len(reconstructed) and x < len(reconstructed[y]) else 0.0
            total += (o - r) ** 2
            n += 1
    if n == 0:
        return 0.0
    return total / n


def compute_edge_loss(original, reconstructed):
    """Compute edge detection loss using simple gradient magnitude."""
    def gradient(img):
        h = len(img)
        w = len(img[0]) if h > 0 else 0
        grad = []
        for y in range(h):
            row = []
            for x in range(w):
                right = img[y][min(x + 1, w - 1)] if w > 1 else 0
                bottom = img[min(y + 1, h - 1)][x] if h > 1 else 0
                gx = right - img[y][x]
                gy = bottom - img[y][x]
                mag = (gx ** 2 + gy ** 2) ** 0.5
                row.append(mag)
            grad.append(row)
        return grad

    orig_grad = gradient(original)
    recon_grad = gradient(reconstructed)
    total = 0.0
    n = 0
    for y in range(len(orig_grad)):
        for x in range(len(orig_grad[y])):
            o = orig_grad[y][x]
            r = recon_grad[y][x] if y < len(recon_grad) and x < len(recon_grad[y]) else 0.0
            total += (o - r) ** 2
            n += 1
    if n == 0:
        return 0.0
    return total / n


def compute_regularization_loss(paths, lambda_val=0.1):
    """Compute regularization loss based on path complexity."""
    if isinstance(paths, PathRecord):
        paths = [paths]
    total = 0.0
    for path in paths:
        if isinstance(path, dict) or not hasattr(path, "records"):
            continue
        for record in path.records:
            if hasattr(record, "length"):
                total += lambda_val * record.length
            elif hasattr(record, "coeffs"):
                total += lambda_val * len(record.coeffs)
    return total
