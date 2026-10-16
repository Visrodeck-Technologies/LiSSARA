"""Lissara Core - Scene: MathScene format, path grouping, and layer ordering."""
import json
from typing import List, Dict, Any

MathSceneVersion = "0.1"


class PathRecord:
    """Minimal path record for MathScene format."""
    def __init__(self, path_id: str, path_type: str, layer: int = 0,
                 closed: bool = False, segments: List[Any] = None,
                 fill: Dict = None, stroke: Dict = None, label: str = None,
                 provenance: Dict = None):
        self.id = path_id
        self.type = path_type
        self.layer = layer
        self.closed = closed
        self.segments = segments or []
        self.fill = fill or {}
        self.stroke = stroke or {}
        self.label = label
        self.provenance = provenance or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "layer": self.layer,
            "closed": self.closed,
            "segments": self.segments,
            "fill": self.fill,
            "stroke": self.stroke,
            "label": self.label,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PathRecord":
        return cls(
            path_id=data.get("id", ""),
            path_type=data.get("type", "path"),
            layer=data.get("layer", 0),
            closed=data.get("closed", False),
            segments=data.get("segments", []),
            fill=data.get("fill", {}),
            stroke=data.get("stroke", {}),
            label=data.get("label"),
            provenance=data.get("provenance", {}),
        )


def _decode_segment(seg) -> list:
    """Decode a segment into a list of (x, y) points."""
    if isinstance(seg, dict):
        pts = seg.get("points", [])
        if not pts:
            return []
        return [(float(p[0]), float(p[1])) if isinstance(p, (list, tuple)) else (float(p), 0.0)
                for p in pts]

    if isinstance(seg, list) and len(seg) > 0 and isinstance(seg[0], (int, float)):
        if len(seg) % 2 != 0:
            seg = seg + [seg[-1]]
        return [(seg[i], seg[i+1]) for i in range(0, len(seg), 2)]

    return [(float(p[0]), float(p[1])) if isinstance(p, (list, tuple)) else (float(p), 0.0)
            for p in seg]


def _is_single_path(segments: List[Any]) -> bool:
    """Check if segments represent a single path (list of [x,y] points)."""
    if not segments:
        return False
    for seg in segments:
        if isinstance(seg, dict):
            return False
        if not isinstance(seg, (list, tuple)):
            return False
        if len(seg) != 2:
            return False
        if not all(isinstance(v, (int, float)) for v in seg):
            return False
    return True


def _build_svg_path_from_points(segments: List[Any], closed: bool) -> str:
    """Build SVG path data from a flat list of [x, y] points."""
    d_parts: List[str] = []

    if not segments:
        return ""

    # First point: Move
    first_pt = segments[0]
    if isinstance(first_pt, (list, tuple)) and len(first_pt) >= 2:
        x0, y0 = float(first_pt[0]), float(first_pt[1])
        d_parts.append("M " + str(x0) + "," + str(y0))

    # remaining points: Line to each subsequent point
    for pt in segments[1:]:
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            x = float(pt[0])
            y = float(pt[1])
            d_parts.append("L " + str(x) + "," + str(y))

    # Close if needed
    if closed and len(segments) > 2:
        first = (float(segments[0][0]), float(segments[0][1]))
        last = (float(segments[-1][0]), float(segments[-1][1]))
        if abs(first[0] - last[0]) > 0.01 or abs(first[1] - last[1]) > 0.01:
            d_parts.append("Z")

    return "".join(d_parts)


def _build_svg_path_multi(segments: List[Any], closed: bool) -> str:
    """Build SVG path data from multi-segment list (dict-based segments)."""
    d_parts: List[str] = []

    for seg_idx, seg in enumerate(segments):
        if isinstance(seg, dict):
            seg_type = seg.get("type", "C")
            pts = seg.get("points", [])
        else:
            pts = seg if isinstance(seg, list) else [seg]

        if not pts:
            continue

        pts = [(float(p[0]), float(p[1])) if isinstance(p, (list, tuple)) else (float(p), 0.0)
               for p in pts]

        if seg_idx == 0:
            x0 = float(pts[0][0])
            y0 = float(pts[0][1])
            d_parts.append("M " + str(x0) + "," + str(y0))

        if len(pts) >= 4 and seg_type == "C":
            p0 = pts[0]
            p1 = pts[1] if len(pts) > 1 else p0
            p2 = pts[2] if len(pts) > 2 else p1
            p3 = pts[3] if len(pts) > 3 else p0
            d_parts.append("C " + str(p1[0]) + "," + str(p1[1]) + " " +
                          str(p2[0]) + "," + str(p2[1]) + " " +
                          str(p3[0]) + "," + str(p3[1]))
        elif len(pts) >= 2:
            x1 = float(pts[1][0])
            y1 = float(pts[1][1])
            d_parts.append("L " + str(x1) + "," + str(y1))

    if closed and d_parts:
        d_parts.append("Z")

    return " ".join(d_parts)


class MathScene:
    """Versioned MathScene document container."""
    def __init__(self, version: str = MathSceneVersion, width: float = None, height: float = None,
                 transforms: Dict = None, paths: List[PathRecord] = None):
        self.version = version
        self.width = width
        self.height = height
        self.transforms = transforms or {}
        self.paths = paths or []

    def add_path(self, path: PathRecord):
        self.paths.append(path)

    def to_json(self) -> str:
        return json.dumps({
            "version": self.version,
            "width": self.width,
            "height": self.height,
            "transforms": self.transforms,
            "paths": [p.to_dict() for p in self.paths],
        }, indent=2)

    def export_svg(self) -> str:
        """Export the MathScene as SVG string."""
        path_elements: List[str] = []

        for path in self.paths:
            segments = path.segments
            closed = path.closed

            if _is_single_path(segments):
                d = _build_svg_path_from_points(segments, closed)
            else:
                d = _build_svg_path_multi(segments, closed)

            fill = path.fill.get("color", "#ffffff") if path.fill else "#ffffff"
            stroke = path.stroke.get("color", "#000000") if path.stroke else "#000000"
            stroke_width = path.stroke.get("width", 1.0) if path.stroke else 1.0
            fill_opacity = path.fill.get("opacity", 1.0) if path.fill else 1.0
            stroke_opacity = path.stroke.get("opacity", 1.0) if path.stroke else 1.0

            if closed:
                style = "fill:" + fill + ";fill-opacity:" + str(fill_opacity) + \
                       ";stroke:" + stroke + ";stroke-opacity:" + str(stroke_opacity) + \
                       ";stroke-width:" + str(stroke_width)
            else:
                style = "stroke:" + stroke + ";stroke-opacity:" + str(stroke_opacity) + \
                       ";stroke-width:" + str(stroke_width) + ";fill:none"

            el = "<path d=" + d + " style=" + style + " id=" + path.id + "/>"
            path_elements.append(el)

        svg_width = str(self.width) if self.width else "100%"
        svg_height = str(self.height) if self.height else "100%"

        result = "<svg width=" + svg_width + " height=" + svg_height + \
                 " xmlns=\"http://www.w3.org/2000/svg\">\\n"
        result += "\\n".join(path_elements)
        result += "\\n</svg>"
        return result

    @classmethod
    def from_json(cls, json_str: str) -> "MathScene":
        data = json.loads(json_str)
        scene = cls(version=data.get("version", MathSceneVersion),
                    width=data.get("width"),
                    height=data.get("height"),
                    transforms=data.get("transforms", {}))
        for path_data in data.get("paths", []):
            scene.add_path(PathRecord.from_dict(path_data))
        return scene