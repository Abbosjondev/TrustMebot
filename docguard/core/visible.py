from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

_FONT_CANDIDATES = (
    "DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "arial.ttf", "Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
)


@lru_cache(maxsize=16)
def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)   # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def apply_visible_watermark(rgb: np.ndarray, text: str, *, opacity: float = 0.20,
                            angle: float = 30.0) -> np.ndarray:
    """Yangi massiv qaytaradi (kirish o'zgarmaydi)."""
    text = text.strip()
    if not text:
        return rgb
    h, w, _ = rgb.shape
    font = _load_font(max(14, round(max(h, w) / 42)))

    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), text, font=font)
    tw, th = right - left, bottom - top
    gap_x, gap_y = int(tw * 0.35) + 20, int(th * 2.6) + 10

    diag = int(math.hypot(w, h) + 2 * (tw + gap_x))
    layer = Image.new("RGBA", (int(diag), int(diag)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    alpha = int(255 * max(0.02, min(opacity, 0.6)))
    for row, y in enumerate(range(-gap_y, diag, gap_y)):
        shift = (tw + gap_x) // 2 if row % 2 else 0
        for x in range(int(-tw - shift), diag, int(tw + gap_x)):
            draw.text((x, y), text, font=font, fill=(128, 128, 128, alpha),
                      stroke_width=1, stroke_fill=(255, 255, 255, alpha // 2))

    layer = layer.rotate(angle, resample=Image.Resampling.BICUBIC)
    left_c, top_c = (diag - w) // 2, (diag - h) // 2
    layer = layer.crop((left_c, top_c, left_c + w, top_c + h))

    base = Image.fromarray(rgb).convert("RGBA")
    base.alpha_composite(layer)
    return np.array(base.convert("RGB"), dtype=np.uint8)
