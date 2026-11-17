from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..errors import ReedSolomonError
from .params import WatermarkParams
from .reed_solomon import ReedSolomon


def crc16_ccitt(data: bytes, init: int = 0xFFFF) -> int:
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


@dataclass(frozen=True)
class DecodedPayload:
    payload_id: bytes
    corrected_symbols: int
    erasures_used: int


class PayloadCodec:
    def __init__(self, params: WatermarkParams) -> None:
        self.params = params
        self._rs = ReedSolomon(params.ecc_symbols)
        self.n_bits = params.n_codeword_bits

    # ------------------------------------------------------------------ encode
    def encode(self, payload_id: bytes) -> np.ndarray:
        if len(payload_id) != self.params.id_bytes:
            raise ValueError(f"ID uzunligi {self.params.id_bytes} bayt bo'lishi kerak")
        message = payload_id + crc16_ccitt(payload_id).to_bytes(2, "big")
        codeword = self._rs.encode(message)
        return np.unpackbits(np.frombuffer(codeword, dtype=np.uint8))

    # ------------------------------------------------------------------ decode
    def decode(self, llr: np.ndarray) -> DecodedPayload | None:
        if llr.shape != (self.n_bits,):
            raise ValueError("LLR uzunligi kod so'zi bitlariga teng bo'lishi kerak")
        hard = (llr < 0).astype(np.uint8)
        word = np.packbits(hard).tobytes()
        reliability = np.abs(llr).reshape(-1, 8).min(axis=1)
        order = np.argsort(reliability, kind="stable")

        nsym = self.params.ecc_symbols
        for n_erase in range(0, nsym, 2):
            erasures = [int(i) for i in order[:n_erase]]
            try:
                message, corrected = self._rs.decode(word, erasures)
            except ReedSolomonError:
                continue
            payload_id = message[: self.params.id_bytes]
            crc = int.from_bytes(message[self.params.id_bytes:], "big")
            if crc == crc16_ccitt(payload_id):
                return DecodedPayload(payload_id, corrected, n_erase)
        return None
