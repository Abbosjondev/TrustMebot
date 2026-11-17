from __future__ import annotations

from collections.abc import Sequence

from ..errors import ReedSolomonError

_PRIM = 0x11D
_EXP = [0] * 512
_LOG = [0] * 256


def _build_tables() -> None:
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= _PRIM
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_build_tables()


def _mul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("GF(256) bo'linmasi nolga")
    return 0 if a == 0 else _EXP[(_LOG[a] - _LOG[b]) % 255]


def _pmul(p: Sequence[int], q: Sequence[int]) -> list[int]:
    out = [0] * (len(p) + len(q) - 1)
    for i, a in enumerate(p):
        if a:
            for j, b in enumerate(q):
                out[i + j] ^= _mul(a, b)
    return out


def _peval_lf(p: Sequence[int], x: int) -> int:
    y = 0
    for c in reversed(p):
        y = _mul(y, x) ^ c
    return y


def _peval_hf(p: Sequence[int], x: int) -> int:
    y = 0
    for c in p:
        y = _mul(y, x) ^ c
    return y


def _berlekamp_massey(s: Sequence[int]) -> list[int]:
    c = [1]
    b = [1]
    big_l = 0
    m = 1
    bb = 1
    for n in range(len(s)):
        d = s[n]
        for i in range(1, big_l + 1):
            if i < len(c):
                d ^= _mul(c[i], s[n - i])
        if d == 0:
            m += 1
            continue
        t = c[:]
        coef = _div(d, bb)
        if len(c) < len(b) + m:
            c = c + [0] * (len(b) + m - len(c))
        for i, bi in enumerate(b):
            c[i + m] ^= _mul(coef, bi)
        if 2 * big_l <= n:
            big_l = n + 1 - big_l
            b = t
            bb = d
            m = 1
        else:
            m += 1
    c = c + [0] * max(0, big_l + 1 - len(c))
    return c[: big_l + 1]


class ReedSolomon:

    def __init__(self, nsym: int) -> None:
        if not 2 <= nsym <= 254:
            raise ValueError("nsym 2..254")
        self.nsym = nsym
        gen = [1]
        for i in range(nsym):
            gen = _pmul(gen, [_EXP[i], 1])
        self._gen_hf = gen[::-1]

    # ------------------------------------------------------------------ encode
    def encode(self, message: bytes) -> bytes:
        k = len(message)
        if k + self.nsym > 255:
            raise ValueError("Kod so'zi 255 baytdan oshmasligi kerak")
        buf = list(message) + [0] * self.nsym
        gen = self._gen_hf
        for i in range(k):
            coef = buf[i]
            if coef:
                for j in range(1, len(gen)):
                    buf[i + j] ^= _mul(gen[j], coef)
        return bytes(message) + bytes(buf[k:])

    # ------------------------------------------------------------------ decode
    def _syndromes(self, word: Sequence[int]) -> list[int]:
        return [_peval_hf(word, _EXP[j]) for j in range(self.nsym)]

    def decode(self, codeword: bytes, erasures: Sequence[int] = ()) -> tuple[bytes, int]:
        n = len(codeword)
        nsym = self.nsym
        if n > 255 or n <= nsym:
            raise ReedSolomonError("Kod so'zi uzunligi noto'g‘ri")
        word = list(codeword)
        synd = self._syndromes(word)
        if not any(synd):
            return bytes(word[:-nsym]), 0

        erase = sorted({int(p) for p in erasures})
        if any(p < 0 or p >= n for p in erase):
            raise ReedSolomonError("o'chirilgan pozitsiya diapazondan tashqarida")
        e = len(erase)
        if e > nsym:
            raise ReedSolomonError("Juda ko'p o'chirilgan pozitsiya")

        # o'chirilganlar lokatori: Gamma(x) = prod (1 + X x)
        gamma = [1]
        for p in erase:
            gamma = _pmul(gamma, [1, _EXP[n - 1 - p]])

        xi = _pmul(synd, gamma)[:nsym]
        xi = xi + [0] * (nsym - len(xi))
        err_loc = _berlekamp_massey(xi[e:])
        v = len(err_loc) - 1
        if 2 * v > nsym - e:
            raise ReedSolomonError("Xatolar soni tuzatish imkoniyatidan oshdi")

        psi = _pmul(err_loc, gamma)
        while len(psi) > 1 and psi[-1] == 0:
            psi.pop()
        deg = len(psi) - 1

        positions = [
            i for i in range(n) if _peval_lf(psi, _EXP[(255 - (n - 1 - i)) % 255]) == 0
        ]
        if len(positions) != deg:
            raise ReedSolomonError("Xato pozitsiyalarini aniqlab bo'lmadi")

        omega = _pmul(synd, psi)[:nsym]
        dpsi = [psi[i] if i % 2 == 1 else 0 for i in range(1, len(psi))]
        for pos in positions:
            power = n - 1 - pos
            x_i = _EXP[power]
            x_inv = _EXP[(255 - power) % 255]
            denom = _peval_lf(dpsi, x_inv)
            if denom == 0:
                raise ReedSolomonError("error")
            word[pos] ^= _mul(x_i, _div(_peval_lf(omega, x_inv), denom))

        if any(self._syndromes(word)):
            raise ReedSolomonError("error")
        corrected = sum(1 for a, b in zip(word, codeword) if a != b)
        return bytes(word[:-nsym]), corrected
