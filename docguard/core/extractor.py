from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import dct
from .codec import DecodedPayload, PayloadCodec
from .imaging import resize_long_side
from .layout import TileLayout
from .params import BLOCK, WatermarkParams

_DECODE_SAT_MARGIN = 2


@dataclass(frozen=True)
class ExtractResult:
    found: bool
    payload_id: bytes | None = None
    confidence: float = 0.0          # signal kuchi (0..1); found=True bo'lsa ID ishonchli
    pilot_score: float = 0.0         # pilot korrelyatsiyasi (0..1)
    corrected_symbols: int = 0
    pixel_offset: tuple[int, int] = (0, 0)
    tile_shift: tuple[int, int] = (0, 0)
    rescaled_to: int | None = None   # topilgan bo'lsa: qaysi uzun tomonga qayta masshtablangan
    reason: str = ""

    @property
    def id_hex(self) -> str | None:
        return self.payload_id.hex() if self.payload_id is not None else None


class Extractor:
    def __init__(self, params: WatermarkParams, *, sync_blocks: int = 96, top_candidates: int = 3) -> None:
        self.params = params
        self.codec = PayloadCodec(params)
        self.layout = TileLayout.build(params, self.codec.n_bits)
        self._bases = dct.basis_stack(params.coeffs)
        self._sync_blocks = sync_blocks
        self._top = top_candidates
        p = params.tile_blocks
        idx = (np.arange(p)[None, :] - np.arange(p)[:, None]) % p   # idx[a, y] = (y - a) % p
        self._shift_y = idx[:, None, :, None]
        self._shift_x = idx[None, :, None, :]

    # ------------------------------------------------------------------ public
    def extract(self, rgb: np.ndarray) -> ExtractResult:
        p = self.params
        h, w, _ = rgb.shape
        if min(h, w) < p.tile_px:
            return ExtractResult(False, reason="Rasm muhr o'qish uchun juda kichik")

        best = self._attempt(rgb)
        if best.found:
            return best

        long_side = max(h, w)
        if long_side != p.max_side:
            scaled = resize_long_side(rgb, p.max_side)
            if min(scaled.shape[:2]) >= p.tile_px:
                res = self._attempt(scaled)
                if res.found:
                    return ExtractResult(**{**res.__dict__, "rescaled_to": p.max_side})
                if res.pilot_score > best.pilot_score:
                    best = res
        return best

    # ----------------------------------------------------------------- internals
    def _attempt(self, rgb: np.ndarray) -> ExtractResult:
        luma = dct.luma(rgb)
        candidates = self._sync_candidates(luma)
        best = ExtractResult(False, reason="Muhr topilmadi")
        for _, oy, ox in candidates:
            z, wgt = self._phasors(luma, oy, ox)
            zavg, wsum = self._fold(z, wgt)
            scores = self._score_map(zavg)
            a, b = np.unravel_index(int(np.argmax(scores)), scores.shape)
            pilot = float(scores[a, b])

            aligned = np.roll(zavg, (a, b), axis=(0, 1))
            values = np.real(aligned * self.layout.rot)
            weights = np.roll(wsum, (a, b), axis=(0, 1))[..., None] * np.ones(
                (1, 1, self.layout.n_coeffs), dtype=np.float32)
            llr = self._bit_llr(values, weights)

            decoded = self.codec.decode(llr)
            if decoded is not None:
                return self._success(decoded, pilot, (oy, ox), (int(a), int(b)))
            if pilot > best.pilot_score:
                best = ExtractResult(False, pilot_score=pilot, pixel_offset=(oy, ox),
                                     tile_shift=(int(a), int(b)),
                                     reason="Sinxronlash bor, lekin ID o'qilmadi")
        return best

    def _success(self, d: DecodedPayload, pilot: float, offset: tuple[int, int],
                 shift: tuple[int, int]) -> ExtractResult:
        t_max = max(1, self.params.ecc_symbols // 2)
        q_pilot = float(np.clip(pilot / 0.5, 0.0, 1.0))
        q_ecc = float(np.clip(1.0 - d.corrected_symbols / t_max, 0.0, 1.0))
        return ExtractResult(
            found=True, payload_id=d.payload_id,
            confidence=round(0.7 * q_pilot + 0.3 * q_ecc, 3),
            pilot_score=round(pilot, 3), corrected_symbols=d.corrected_symbols,
            pixel_offset=offset, tile_shift=shift,
        )

    def _sync_candidates(self, luma: np.ndarray) -> list[tuple[float, int, int]]:
        h, w = luma.shape
        side = self._sync_blocks * BLOCK
        r0 = max(0, (h - side) // 2)
        c0 = max(0, (w - side) // 2)
        region = luma[r0: r0 + side, c0: c0 + side]
        scored = []
        for oy in range(BLOCK):
            for ox in range(BLOCK):
                z, wgt = self._phasors(region, oy, ox)
                if z.shape[0] == 0 or z.shape[1] == 0:
                    continue
                zavg, _ = self._fold(z, wgt)
                scored.append((float(self._score_map(zavg).max()),
                               (oy + r0) % BLOCK, (ox + c0) % BLOCK))
        scored.sort(reverse=True)
        seen, out = set(), []
        for s, oy, ox in scored:
            if (oy, ox) not in seen:
                seen.add((oy, ox))
                out.append((s, oy, ox))
            if len(out) >= self._top:
                break
        return out

    def _phasors(self, plane: np.ndarray, oy: int, ox: int) -> tuple[np.ndarray, np.ndarray]:
        p = self.params
        h, w = plane.shape
        nby, nbx = dct.grid_shape(h, w, oy, ox)
        k = len(p.coeffs)
        z = np.zeros((max(nby, 0), max(nbx, 0), k), dtype=np.complex64)
        wgt = np.zeros((max(nby, 0), max(nbx, 0)), dtype=np.float32)
        if nby <= 0 or nbx <= 0:
            return z, wgt
        lo = p.saturation_lo + _DECODE_SAT_MARGIN
        hi = p.saturation_hi - _DECODE_SAT_MARGIN
        for by0 in range(0, nby, p.strip_block_rows):
            by1 = min(by0 + p.strip_block_rows, nby)
            view = dct.block_view(plane, oy, ox, by0, by1, nbx)
            coefs = dct.block_coefficients(view, self._bases)
            bad = dct.saturated_blocks(view, lo, hi, p.saturated_fraction)
            ok = (~bad).astype(np.float32)
            z[by0:by1] = np.exp(1j * (2.0 * np.pi / p.step) * coefs).astype(np.complex64) * ok[..., None]
            wgt[by0:by1] = ok
        return z, wgt

    def _fold(self, z: np.ndarray, wgt: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        p = self.params.tile_blocks
        nby, nbx, k = z.shape
        ny, nx = -(-nby // p), -(-nbx // p)
        zp = np.zeros((ny * p, nx * p, k), dtype=np.complex64)
        wp = np.zeros((ny * p, nx * p), dtype=np.float32)
        zp[:nby, :nbx] = z
        wp[:nby, :nbx] = wgt
        zsum = zp.reshape(ny, p, nx, p, k).sum(axis=(0, 2))
        wsum = wp.reshape(ny, p, nx, p).sum(axis=(0, 2))
        zavg = zsum / np.maximum(wsum, 1.0)[..., None]
        return zavg.astype(np.complex64), wsum

    def _score_map(self, zavg: np.ndarray) -> np.ndarray:
        shifted = zavg[self._shift_y, self._shift_x]                 # (a, b, y, x, K)
        vals = np.real(shifted * self.layout.rot)
        score = np.einsum("abyxk,yxk->ab", vals, self.layout.pilot_sign)
        return (score / max(1, self.layout.n_pilot)).astype(np.float32)

    def _bit_llr(self, values: np.ndarray, weights: np.ndarray) -> np.ndarray:
        idx = self.layout.data_index
        mask = idx >= 0
        flat_idx = idx[mask]
        num = np.bincount(flat_idx, weights=(values * weights)[mask], minlength=self.layout.n_bits)
        den = np.bincount(flat_idx, weights=weights[mask], minlength=self.layout.n_bits)
        return (num / np.maximum(den, 1e-6)).astype(np.float64)
