"""Derives web assets from the team logo (resources/Logo tech FAULTLINE géométrique.png), standard library only.
Crops the mark, turns the white background into transparency (colours un-blended from white, so the artwork is unchanged),
and writes public/assets/brand/logo-mark.png (320 px, transparent) and favicon.png (64 px, on the logo's own white).
Run: python3 docs/design/countermove/build_logo_assets.py"""
import struct, zlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "resources" / "Logo tech FAULTLINE géométrique.png"
OUT = ROOT / "public" / "assets" / "brand"

def read_png(p):
    d = p.read_bytes(); i = 8; idat = b""
    while i < len(d):
        n, t = struct.unpack(">I4s", d[i:i + 8]); body = d[i + 8:i + 8 + n]; i += 12 + n
        if t == b"IHDR": w, h, bd, ct = struct.unpack(">IIBB", body[:10])
        elif t == b"IDAT": idat += body
    bpp = {2: 3, 6: 4}[ct]; raw = zlib.decompress(idat); st = w * bpp; prev = bytearray(st); rows = []; k = 0
    for _ in range(h):
        f = raw[k]; line = bytearray(raw[k + 1:k + 1 + st]); k += 1 + st
        for x in range(st):
            a = line[x - bpp] if x >= bpp else 0; b = prev[x]; c = prev[x - bpp] if x >= bpp else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c); line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line); prev = line
    return w, h, bpp, rows

def write_png(p, w, h, rgba):
    ch = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(r) for r in rgba)
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + ch(b"IDAT", zlib.compress(raw, 9)) + ch(b"IEND", b""))

def crop_scale(rows, bpp, x0, y0, size, out):  # box filter
    f = size / out; res = []
    for oy in range(out):
        line = []
        for ox in range(out):
            xa, xb = int(x0 + ox * f), max(int(x0 + ox * f) + 1, int(x0 + (ox + 1) * f)); ya, yb = int(y0 + oy * f), max(int(y0 + oy * f) + 1, int(y0 + (oy + 1) * f))
            s = [0, 0, 0]; n = 0
            for y in range(ya, yb):
                r = rows[y]
                for x in range(xa, xb): s[0] += r[x * bpp]; s[1] += r[x * bpp + 1]; s[2] += r[x * bpp + 2]; n += 1
            line.append((s[0] / n, s[1] / n, s[2] / n))
        res.append(line)
    return res

w, h, bpp, rows = read_png(SRC)
X0, Y0, SIZE = 327, 240, 600          # square around the mark, above the wordmark
px = crop_scale(rows, bpp, X0, Y0, SIZE, 320)
mark = []
for line in px:
    o = bytearray()
    for r, g, b in line:
        a = 1 - min(r, g, b) / 255.0     # white -> transparent
        if a < 0.035: o += b"\x00\x00\x00\x00"; continue
        un = lambda c: max(0, min(255, round((c - (1 - a) * 255) / a)))
        o += bytes((un(r), un(g), un(b), round(a * 255)))
    mark.append(o)
OUT.mkdir(parents=True, exist_ok=True)
write_png(OUT / "logo-mark.png", 320, 320, mark)
fav = crop_scale(rows, bpp, X0 - 20, Y0 - 20, SIZE + 40, 64)
write_png(OUT / "favicon.png", 64, 64, [bytearray(b"".join(bytes((round(r), round(g), round(b), 255)) for r, g, b in line)) for line in fav])
# wordmark blue: average of the saturated blue pixels in "LINE"
s = [0, 0, 0]; n = 0
for y in range(870, 990, 3):
    for x in range(745, 1150, 3):
        r, g, b = rows[y][x * bpp:x * bpp + 3]
        if b > 200 and r < 90: s[0] += r; s[1] += g; s[2] += b; n += 1
print("wrote logo-mark.png, favicon.png; LINE blue = #%02x%02x%02x" % tuple(round(v / n) for v in s))
