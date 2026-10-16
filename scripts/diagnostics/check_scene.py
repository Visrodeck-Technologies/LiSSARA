"""Summarize a MathScene JSON. Usage: python scripts/diagnostics/check_scene.py [scene.json]"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def check_scene(scene_path):
    """Print the scene size, path count and the first few paths."""
    with open(scene_path, 'r') as f:
        data = json.load(f)
    print('Scene width:', data['width'])
    print('Scene height:', data['height'])
    print('Number of paths:', len(data['paths']))
    for i, path in enumerate(data['paths'][:5]):
        print('  Path {}: id={}, type={}, closed={}, segments={}'.format(
            i, path.get('path_id'), path.get('path_type'), path.get('closed'),
            len(path.get('segments', []))))
        if path.get('segments'):
            seg = path['segments'][0]
            print('    First segment keys:', list(seg.keys()))
            if 'control_points' in seg:
                print('    Control points:', seg['control_points'])


def main(argv):
    """Check outputs/scene.json, or the file given on the command line."""
    target = Path(argv[0]) if argv else REPO_ROOT / 'outputs' / 'scene.json'
    if not target.is_absolute():
        target = REPO_ROOT / target
    check_scene(target)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
