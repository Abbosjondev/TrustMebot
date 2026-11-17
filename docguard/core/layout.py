from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from .params import WatermarkParams


def _u64(key: bytes, label: bytes, index: int) -> int:
    digest = hashlib.sha256(key + label + index.to_bytes(4, "big")).digest()
    return int.from_bytes(digest[:8], "big")


@dataclass(frozen=True)
class TileLayout:
    size: int                 # tile_blocks
    n_coeffs: int
    n_bits: int               # kod so'zi bitlari soni
    n_pilot: int
    pilot_sign: np.ndarray    # (P,P,K) float32: pilot slotda +1 (bit 0) / -1 (bit 1), boshqa joyda 0
    pilot_bits: np.ndarray    # (P,P,K) uint8
    data_index: np.ndarray    # (P,P,K) int32: ma'lumot slotida bit indeksi, aks holda -1
    dither: np.ndarray        # (P,P,K) float32 in [0, step)
    rot: np.ndarray           # (P,P,K) complex64: exp(-i*2*pi*dither/step)

    @classmethod
    def build(cls, params: WatermarkParams, n_bits: int) -> TileLayout:
        p, k = params.tile_blocks, len(params.coeffs)
        n_slots = p * p * k
        key = params.key_material()

        order = sorted(range(n_slots), key=lambda i: _u64(key, b"perm", i))
        n_pilot = params.n_pilot_slots

        pilot_bits = np.zeros(n_slots, dtype=np.uint8)
        pilot_sign = np.zeros(n_slots, dtype=np.float32)
        for slot in order[:n_pilot]:
            bit = _u64(key, b"pilot", slot) & 1
            pilot_bits[slot] = bit
            pilot_sign[slot] = 1.0 - 2.0 * bit

        data_index = np.full(n_slots, -1, dtype=np.int32)
        for rank, slot in enumerate(order[n_pilot:]):
            data_index[slot] = rank % n_bits

        dither = np.array(
            [_u64(key, b"dither", i) / 2.0**64 * params.step for i in range(n_slots)],
            dtype=np.float32,
        )
        rot = np.exp(-2j * np.pi * dither / params.step).astype(np.complex64)

        shape = (p, p, k)
        return cls(
            size=p, n_coeffs=k, n_bits=n_bits, n_pilot=n_pilot,
            pilot_sign=pilot_sign.reshape(shape), pilot_bits=pilot_bits.reshape(shape),
            data_index=data_index.reshape(shape), dither=dither.reshape(shape),
            rot=rot.reshape(shape),
        )

    def slot_bits(self, codeword_bits: np.ndarray) -> np.ndarray:
        out = self.pilot_bits.copy()
        mask = self.data_index >= 0
        out[mask] = codeword_bits[self.data_index[mask]]
        return out
