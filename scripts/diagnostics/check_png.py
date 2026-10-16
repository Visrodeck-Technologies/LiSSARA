"""Print PNG header details. Usage: python scripts/diagnostics/check_png.py [image.png ...]"""
import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def check_png(path):
    """Print the size, signature validity and IHDR fields of one PNG."""
    with open(path, 'rb') as f:
        data = f.read()
    print(str(path) + ':')
    print('  Size:', len(data))
    print('  Valid:', data[:8] == b'\x89PNG\r\n\x1a\n')
    pos = 8
    chunk_len = struct.unpack('>I', data[pos:pos + 4])[0]
    ihdr = data[pos + 8:pos + 8 + chunk_len]
    w, h, bd, ct = struct.unpack('>IIBBBBB', ihdr[:13])[:4]
    print('  Dimensions:', w, 'x', h, 'bit_depth:', bd, 'color_type:', ct)


def main(argv):
    """Check the default previews, or the paths given on the command line."""
    targets = [REPO_ROOT / name for name in argv] if argv else [
        REPO_ROOT / 'outputs' / 'input_preview.png',
        REPO_ROOT / 'outputs' / 'reconstructed.png',
    ]
    for index, target in enumerate(targets):
        if index:
            print()
        check_png(target)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
