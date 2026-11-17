from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .core.params import WatermarkParams
from .errors import ConfigError


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError as exc:
        raise ConfigError(f"{name} invalid: {raw!r}") from exc


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError as exc:
        raise ConfigError(f"{name} invalid: {raw!r}") from exc


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw in (None, "") else raw.strip().lower() in ("1", "true", "yes", "on", "ha")


@dataclass(frozen=True)
class Settings:
    secret_key: str
    db_path: Path
    bot_token: str | None = None
    max_side: int = 1280
    wm_step: float = 32.0
    jpeg_quality: int = 93
    max_input_pixels: int = 120_000_000
    max_file_bytes: int = 20 * 1024 * 1024
    max_workers: int = 2
    visible_default: bool = False
    timezone: str = "Asia/Tashkent"

    @classmethod
    def from_env(cls, *, require_token: bool = False) -> Settings:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        secret = os.environ.get("SECRET_KEY", "")
        if len(secret) < 16:
            raise ConfigError(
                "secret not found"                
            )
        token = os.environ.get("BOT_TOKEN") or None
        if require_token and not token:
            raise ConfigError("BOT_TOKEN not found")

        return cls(
            secret_key=secret,
            db_path=Path(os.environ.get("DB_PATH", "data/docguard.sqlite3")),
            bot_token=token,
            max_side=_int("MAX_SIDE", 1280),
            wm_step=_float("WM_STEP", 32.0),
            jpeg_quality=_int("JPEG_QUALITY", 93),
            max_input_pixels=_int("MAX_INPUT_PIXELS", 120_000_000),
            max_file_bytes=_int("MAX_FILE_MB", 20) * 1024 * 1024,
            max_workers=max(1, _int("MAX_WORKERS", 2)),
            visible_default=_bool("VISIBLE_WATERMARK_DEFAULT", False),
            timezone=os.environ.get("TIMEZONE", "Asia/Tashkent"),
        )

    def watermark_params(self) -> WatermarkParams:
        return WatermarkParams(
            secret_key=self.secret_key.encode("utf-8"),
            step=self.wm_step,
            max_side=self.max_side,
        )
