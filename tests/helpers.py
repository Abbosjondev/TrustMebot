"""Testlar uchun umumiy yordamchilar: sintetik "foto" va Telegram siqishini taqlid qilish."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

KEY = b"unit-test-secret-key-0123456789"


def synth_photo(h: int = 960, w: int = 1280, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)

    def smooth(scale: float) -> np.ndarray:
        f = np.fft.rfft2(rng.standard_normal((h, w)).astype(np.float32))
        fy, fx = np.fft.fftfreq(h)[:, None], np.fft.rfftfreq(w)[None, :]
        f *= np.exp(-(fx**2 + fy**2) * scale**2)
        o = np.fft.irfft2(f, s=(h, w))
        return (o - o.mean()) / o.std()

    base = 128 + 40 * smooth(60) + 18 * smooth(12) + 6 * smooth(3)
    xx = np.arange(w)[None, :]
    base = base + 30 * np.sin(xx / 200.0)
    img = np.stack([base, base * 0.9 + 10 * smooth(40), base * 0.8 + 15 * smooth(30)], axis=-1)
    img[h // 5: h // 2, w // 4: w // 2] = (235, 235, 230)
    return np.clip(img, 0, 255).astype(np.uint8)


def white_scan(h: int = 1280, w: int = 900) -> np.ndarray:
    """Toza oq (255) fonli skaner: matn qatorlari + foto bo'lagi."""
    doc = np.full((h, w, 3), 255, np.uint8)
    doc[100:h - 100:22, 80:w - 80] = 20
    doc[300:700, 100:400] = synth_photo(400, 300, 5)
    return doc


def jpeg_roundtrip(rgb: np.ndarray, quality: int = 75, subsampling: int = 2) -> np.ndarray:
    """Telegram "photo" siqishiga o'xshash: JPEG (4:2:0) kodlab, qayta dekodlash."""
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=quality, subsampling=subsampling)
    return np.array(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))


def to_jpeg_bytes(rgb: np.ndarray, quality: int = 75) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=quality, subsampling=2)
    return buf.getvalue()
