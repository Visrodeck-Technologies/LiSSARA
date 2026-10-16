"""Count path commands in an SVG. Usage: python scripts/diagnostics/check_svg.py [output.svg]"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def check_svg(path):
    """Print the path-command counts and the first path data."""
    with open(path, 'r') as f:
        svg = f.read()
    print('SVG length:', len(svg))
    print('C commands:', svg.count('C '))
    print('M commands:', svg.count('M '))
    print('Z commands:', svg.count('Z'))
    paths = re.findall(r'd="([^"]+)"', svg)
    if paths:
        print('First path (first 200 chars):', paths[0][:200])
        print('C commands in first path:', paths[0].count('C'))


def main(argv):
    """Check outputs/output.svg, or the file given on the command line."""
    target = Path(argv[0]) if argv else REPO_ROOT / 'outputs' / 'output.svg'
    if not target.is_absolute():
        target = REPO_ROOT / target
    check_svg(target)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
