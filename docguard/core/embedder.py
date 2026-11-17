from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..errors import ImageTooSmallError
from . import dct
from .codec import PayloadCodec
from .layout import TileLayout
from .params import BLOCK, WatermarkParams


@dataclass(frozen=True)
class EmbedStats:
    psnr_db: float
    blocks_total: int
    blocks_skipped: int


class Embedder:
    def __init__(self, params: WatermarkParams) -> None:
        self.params = params
        self.codec = PayloadCodec(params)
        self.layout = TileLayout.build(params, self.codec.n_bits)
        self._bases = dct.basis_stack(params.coeffs)

    def embed(self, rgb: np.ndarray, payload_id: bytes) -> EmbedStats:
        p = self.params
        if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError("rgb: (H, W, 3) uint8 massiv bo'lishi kerak")
        h, w, _ = rgb.shape
        if min(h, w) < p.min_side:
            raise ImageTooSmallError(
                f"Rasm juda kichik ({w}x{h}); kamida {p.min_side}px kerak."
            )

        slot_bits = self.layout.slot_bits(self.codec.encode(payload_id))
        nby, nbx = dct.grid_shape(h, w)
        half = np.float32(p.step / 2.0)
        step = np.float32(p.step)
        tx = (np.arange(nbx) % p.tile_blocks)[None, :]
        lo_f = np.float32(p.headroom)
        gain = np.float32((255 - 2 * p.headroom) / 255.0)

        sq_err = 0.0
        skipped = 0
        for by0 in range(0, nby, p.strip_block_rows):
            by1 = min(by0 + p.strip_block_rows, nby)
            y0, y1, x1 = by0 * BLOCK, by1 * BLOCK, nbx * BLOCK
            region = rgb[y0:y1, :x1]                       # ko'rinish (view)
            base = region.astype(np.float32) * gain + lo_f  # headroom bilan siqilgan polosa

            luma = dct.luma(base)
            view = luma.reshape(by1 - by0, BLOCK, nbx, BLOCK)
            coefs = dct.block_coefficients(view, self._bases)           # (rows, nbx, K)
            skip = dct.saturated_blocks(view, p.saturation_lo, p.saturation_hi,
                                        p.saturated_fraction)

            ty = (np.arange(by0, by1) % p.tile_blocks)[:, None]
            target = slot_bits[ty, tx].astype(np.float32)               # (rows, nbx, K)
            origin = self.layout.dither[ty, tx] + target * half
            quantized = origin + step * np.rint((coefs - origin) / step)
            delta = quantized - coefs
            delta[skip] = 0.0
            skipped += int(skip.sum())

            d_plane = dct.synthesize(delta, self._bases)               # (rows*8, nbx*8)
            new = np.clip(np.rint(base + d_plane[..., None]), 0, 255)
            new = new.astype(np.uint8)
            diff = new.astype(np.float32) - base          # sof muhr shovqini (headroom siqishisiz)
            sq_err += float((diff.astype(np.float64) ** 2).sum())
            region[...] = new

        mse = sq_err / (nby * nbx * BLOCK * BLOCK * 3)
        psnr = float("inf") if mse == 0 else 10.0 * np.log10(255.0**2 / mse)
        return EmbedStats(psnr_db=psnr, blocks_total=nby * nbx, blocks_skipped=skipped)
