from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ..errors import ConfigError

BLOCK = 8  # JPEG DCT bloki o'lchami (piksel)


@dataclass(frozen=True)
class WatermarkParams:
    secret_key: bytes

    # --- Joylash geometriyasi -------------------------------------------
    tile_blocks: int = 16            # panjara (tile) tomoni, 8x8 bloklarda: 16 -> 128 px
    coeffs: tuple[tuple[int, int], ...] = ((1, 2), (2, 1))  # o'rta-past chastotali DCT koeffitsiyentlari
    step: float = 32.0               # QIM qadami (katta = chidamli, lekin ko'proq ko'rinadi)
    pilot_ratio: float = 0.25        # slotlarning qancha qismi sinxronlash (pilot) uchun

    # --- Payload va xatoni tuzatish ---------------------------------------
    id_bytes: int = 6                # 48 bit ID
    ecc_symbols: int = 14            # Reed–Solomon: 7 ta bayt xatosini tuzatadi

    # --- Rasm bilan ishlash -----------------------------------------------
    max_side: int = 1280             # chiqish rasmining uzun tomoni (Telegram "photo" chegarasi)
    min_side: int = 256              # shundan kichik rasmga muhr qo'yilmaydi
    headroom: int = 8                # piksel diapazoni [headroom, 255-headroom] ga siqiladi: toza oq/qora
                                     # skanerlarda ham muhr qo'yish uchun "joy" qoldiradi
    saturation_lo: int = 3           # shu qiymatdan quyi/yuqori piksellar "to'yingan" hisoblanadi
    saturation_hi: int = 252
    saturated_fraction: float = 0.25 # blokda to'yingan piksellar ulushi shundan oshsa — blok o'tkaziladi
    strip_block_rows: int = 32       # bir martada ishlanadigan blok-qatorlar (RAM nazorati)

    def __post_init__(self) -> None:
        if len(self.secret_key) < 8:
            raise ConfigError("SECRET_KEY kamida 8 bayt bo'lishi kerak (tavsiya: 32+ belgi).")
        if self.tile_blocks < 4:
            raise ConfigError("tile_blocks >= 4 bo'lishi kerak.")
        for u, v in self.coeffs:
            if not (0 <= u < BLOCK and 0 <= v < BLOCK) or (u, v) == (0, 0):
                raise ConfigError(f"Yaroqsiz DCT koeffitsiyenti: {(u, v)}")
        if not (0.05 <= self.pilot_ratio <= 0.6):
            raise ConfigError("pilot_ratio 0.05..0.6 oralig‘ida bo'lishi kerak.")
        if self.n_codeword_bits > self.n_data_slots:
            raise ConfigError(
                f"Payload ({self.n_codeword_bits} bit) bitta panjaradagi "
                f"ma'lumot slotlariga ({self.n_data_slots}) sig‘maydi."
            )
        if not (0 <= self.headroom <= 24):
            raise ConfigError("headroom 0..24 oralig‘ida bo'lishi kerak.")
        if self.min_side < self.tile_px * 2:
            raise ConfigError("min_side kamida ikkita panjara (2 * tile_px) bo'lishi kerak.")

    # --- Hosilaviy kattaliklar -------------------------------------------
    @property
    def tile_px(self) -> int:
        return self.tile_blocks * BLOCK

    @property
    def n_slots(self) -> int:
        return self.tile_blocks * self.tile_blocks * len(self.coeffs)

    @property
    def n_pilot_slots(self) -> int:
        return round(self.n_slots * self.pilot_ratio)

    @property
    def n_data_slots(self) -> int:
        return self.n_slots - self.n_pilot_slots

    @property
    def crc_bytes(self) -> int:
        return 2

    @property
    def n_message_bytes(self) -> int:
        return self.id_bytes + self.crc_bytes

    @property
    def n_codeword_bytes(self) -> int:
        return self.n_message_bytes + self.ecc_symbols

    @property
    def n_codeword_bits(self) -> int:
        return self.n_codeword_bytes * 8

    def key_material(self) -> bytes:
        """Kalitdan domen-ajratilgan 32 baytlik material."""
        return hashlib.sha256(b"docguard/v1|" + self.secret_key).digest()

    def fingerprint(self) -> str:
        """Parametrlar (kalitsiz) barmoq izi — versiya nazorati uchun."""
        raw = repr((self.tile_blocks, self.coeffs, self.step, self.pilot_ratio,
                    self.id_bytes, self.ecc_symbols, self.headroom)).encode()
        return hashlib.sha256(raw).hexdigest()[:12]
