import io
import math
from pathlib import Path

from PIL import Image


def rotated_aabb(rel_w: float, rel_h: float, page_w: float, page_h: float, rotation: float):
    """Return normalized AABB (w',h') of rotated box around center."""
    if rotation % 360 == 0:
        return rel_w, rel_h
    rad = math.radians(rotation % 360)
    c = abs(math.cos(rad))
    s = abs(math.sin(rad))
    w_px = rel_w * page_w
    h_px = rel_h * page_h
    w2 = w_px * c + h_px * s
    h2 = w_px * s + h_px * c
    return w2 / max(0.001, page_w), h2 / max(0.001, page_h)


def prepare_stamp_bytes(stamp_path: Path, rotation: float) -> bytes:
    p = Path(stamp_path)
    if not p.exists():
        return b""
    if rotation % 360 == 0:
        return p.read_bytes()
    try:
        im = Image.open(str(p)).convert("RGBA")
        # Pillow rotates CCW, Qt clockwise -> negate
        im = im.rotate(-rotation, expand=True, resample=Image.BICUBIC)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return p.read_bytes()
