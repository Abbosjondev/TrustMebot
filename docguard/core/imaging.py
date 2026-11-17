from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from ..errors import ImageTooLargeError, InvalidImageError
from .metadata import MetadataReport, inspect_metadata

Image.MAX_IMAGE_PIXELS = None  # o'z limitimiz bor (load_image ichida, dekodlashdan oldin)


@dataclass(frozen=True)
class LoadedImage:
    rgb: np.ndarray                 # (H, W, 3) uint8, yozish mumkin
    metadata: MetadataReport
    original_size: tuple[int, int]  # (W, H) yuklashdan oldingi


def load_image(data: bytes, *, max_side: int, max_pixels: int,
               honor_orientation: bool = True) -> LoadedImage:
    try:
        img = Image.open(io.BytesIO(data))
        width, height = img.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError("Fayl rasm sifatida o'qilmadi.") from exc

    if width * height > max_pixels:
        raise ImageTooLargeError(
            f"Rasm juda katta ({width}x{height} = {width * height / 1e6:.0f} MP)."
        )

    try:
        report = inspect_metadata(img)
        if img.format == "JPEG":
            img.draft("RGB", (max_side, max_side))
        img.load()
        if honor_orientation:
            img = ImageOps.exif_transpose(img)
        img = _to_rgb(img)
        if max(img.size) > max_side:
            img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        rgb = np.array(img, dtype=np.uint8)
    except (OSError, ValueError, SyntaxError) as exc:
        raise InvalidImageError("Rasm buzilgan yoki qo'llab-quvvatlanmaydi.") from exc

    return LoadedImage(rgb=rgb, metadata=report, original_size=(width, height))


def _to_rgb(img: Image.Image) -> Image.Image:
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)
    if has_alpha:
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    return img.convert("RGB")


def resize_long_side(rgb: np.ndarray, side: int) -> np.ndarray:
    h, w, _ = rgb.shape
    scale = side / max(h, w)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    img = Image.fromarray(rgb).resize(size, Image.Resampling.LANCZOS)
    return np.asarray(img, dtype=np.uint8)


def encode_jpeg(rgb: np.ndarray, quality: int = 93) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=quality, subsampling=0, optimize=True)
    return buf.getvalue()
