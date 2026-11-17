from __future__ import annotations

import numpy as np

from .params import BLOCK


def _dct_matrix() -> np.ndarray:
    t = np.zeros((BLOCK, BLOCK), dtype=np.float64)
    for u in range(BLOCK):
        alpha = np.sqrt(1.0 / BLOCK) if u == 0 else np.sqrt(2.0 / BLOCK)
        for x in range(BLOCK):
            t[u, x] = alpha * np.cos((2 * x + 1) * u * np.pi / (2 * BLOCK))
    return t


_T = _dct_matrix()


def basis_stack(coeffs: tuple[tuple[int, int], ...]) -> np.ndarray:
    return np.stack([np.outer(_T[u], _T[v]) for u, v in coeffs]).astype(np.float32)


def luma(rgb: np.ndarray) -> np.ndarray:
    y = rgb[..., 0] * np.float32(0.299)
    y += rgb[..., 1] * np.float32(0.587)
    y += rgb[..., 2] * np.float32(0.114)
    return y


def grid_shape(height: int, width: int, oy: int = 0, ox: int = 0) -> tuple[int, int]:
    return (height - oy) // BLOCK, (width - ox) // BLOCK


def block_view(plane: np.ndarray, oy: int, ox: int, by0: int, by1: int, nbx: int) -> np.ndarray:
    sub = plane[oy + by0 * BLOCK: oy + by1 * BLOCK, ox: ox + nbx * BLOCK]
    return sub.reshape(by1 - by0, BLOCK, nbx, BLOCK)


def block_coefficients(view: np.ndarray, bases: np.ndarray) -> np.ndarray:
    return np.einsum("ayhx,kyx->ahk", view, bases, optimize=True)


def saturated_blocks(view: np.ndarray, lo: float, hi: float, fraction: float) -> np.ndarray:
    sat = (view <= lo) | (view >= hi)
    return sat.mean(axis=(1, 3)) > fraction


def synthesize(delta: np.ndarray, bases: np.ndarray) -> np.ndarray:
    rows, nbx, _ = delta.shape
    out = np.einsum("ahk,kyx->ayhx", delta, bases, optimize=True)
    return out.reshape(rows * BLOCK, nbx * BLOCK)
