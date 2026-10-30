"""Turn the big pixel CSV into a small zip of JPEG frames (plus an index CSV) so it can be shared.

    pip install pillow
    python analysis\\pack_frames.py "D:\\Codekarma\\video_2000_frames_224x224_rgb_pixels_encoded.csv" [out.zip]

Writes D:\\Codekarma\\my_video_frames.zip (next to the CSV).
"""
import base64
import csv
import io
import os
import sys
import zipfile
import zlib

import numpy as np
from PIL import Image

csv.field_size_limit(2 ** 31 - 1)


def decode(text, h, w):
    raw = base64.b64decode(text)
    for unpack in (zlib.decompress, lambda b: zlib.decompress(b, -15), lambda b: zlib.decompress(b, 31), lambda b: b):
        try:
            b = unpack(raw)
        except zlib.error:
            continue
        if len(b) == h * w * 3:
            return np.frombuffer(b, np.uint8).reshape(h, w, 3)
    try:  # maybe the bytes are an encoded image (PNG/JPEG)
        return np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"))
    except Exception:
        raise SystemExit(f"Could not decode pixel data (first bytes: {raw[:8]!r}); send this line to Claude.")


src = sys.argv[1]
stem = os.path.splitext(os.path.basename(src))[0].replace("_224x224_rgb_pixels_encoded", "")
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(src)), stem + "_frames.zip")
n = 0
with open(src, newline="", encoding="utf-8") as fh, zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
    rd = csv.DictReader(fh)
    pix = next((c for c in rd.fieldnames if "base64" in c.lower()), None) or \
        next(c for c in rd.fieldnames if "pixel_data" in c.lower())
    meta_cols = [c for c in rd.fieldnames if c != pix]
    print("columns:", rd.fieldnames)
    index = io.StringIO()
    w = csv.writer(index)
    w.writerow(["jpg"] + meta_cols)
    for row in rd:
        a = decode(row[pix], int(row.get("height") or 224), int(row.get("width") or 224))
        if n == 0:
            print("pixel_encoding:", row.get("pixel_encoding"), "| frame shape:", a.shape)
        buf = io.BytesIO()
        Image.fromarray(a).save(buf, "JPEG", quality=92)
        name = f"frames/{n:04d}.jpg"
        z.writestr(name, buf.getvalue())
        w.writerow([name] + [row[c] for c in meta_cols])
        n += 1
        if n % 250 == 0:
            print(n, "frames")
    z.writestr("index.csv", index.getvalue())
print(f"done: {n} frames -> {out} ({os.path.getsize(out) / 1e6:.1f} MB)")
if n < 2000:
    print(f"NOTE: the CSV has only {n} complete rows; it may have been cut off when it was created.")
