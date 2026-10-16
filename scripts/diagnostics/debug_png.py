"""Dump raw PNG bytes and verify the signature. Usage: python scripts/diagnostics/debug_png.py [image.png]"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
SIGNATURE_BYTES = [137, 80, 78, 71, 13, 10, 26, 10]


def debug_png(path):
    """Print the first bytes of the file and verify the PNG signature."""
    with open(path, 'rb') as f:
        data = f.read()
    print(str(path))
    print('First 20 bytes:')
    for i, b in enumerate(data[:20]):
        print('  byte %d: %d (0x%02x)' % (i, b, b))
    print()
    print('Signature check:')
    for i, expected in enumerate(SIGNATURE_BYTES):
        print('  data[%d]: %d (expected %d)' % (i, data[i], expected))
    print()
    print('Signature valid:', data[:8] == PNG_SIGNATURE)


def main(argv):
    """Check outputs/input_preview.png, or the file given on the command line."""
    target = Path(argv[0]) if argv else REPO_ROOT / 'outputs' / 'input_preview.png'
    if not target.is_absolute():
        target = REPO_ROOT / target
    debug_png(target)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
