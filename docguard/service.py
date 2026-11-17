from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from enum import Enum

from .config import Settings
from .core import Embedder, ExtractResult, Extractor
from .core.imaging import encode_jpeg, load_image
from .core.metadata import MetadataReport
from .core.visible import apply_visible_watermark
from .errors import DocGuardError
from .storage import Repository, WatermarkRecord

MAX_LABEL_LEN = 200
_CTRL = re.compile(r"[\x00-\x1f\x7f]+")
_DECODE_MAX_SIDE = 4096


def normalize_label(raw: str) -> str:
    label = _CTRL.sub(" ", raw)
    label = re.sub(r"\s+", " ", label).strip()
    return label[:MAX_LABEL_LEN]


def _resolve_tz(name: str) -> tzinfo:
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        return ZoneInfo(name)
    except (ImportError, ZoneInfoNotFoundError):
        return timezone(timedelta(hours=5))


@dataclass(frozen=True)
class ProtectResult:
    jpeg: bytes
    payload_id: str
    label: str
    created_at: datetime
    metadata: MetadataReport
    psnr_db: float
    size: tuple[int, int]
    visible_applied: bool


class VerifyStatus(Enum):
    NOT_FOUND = "not_found"
    OWN = "own"
    FOREIGN = "foreign"
    UNKNOWN_ID = "unknown_id"


@dataclass(frozen=True)
class VerifyResult:
    status: VerifyStatus
    extract: ExtractResult
    record: WatermarkRecord | None = None


class ProtectionService:
    def __init__(self, settings: Settings, repository: Repository) -> None:
        self.settings = settings
        self.repo = repository
        self.params = settings.watermark_params()
        self._embedder = Embedder(self.params)
        self._extractor = Extractor(self.params)
        self.tz = _resolve_tz(settings.timezone)

    def visible_enabled(self, user_id: int) -> bool:
        pref = self.repo.get_visible_pref(user_id)
        return self.settings.visible_default if pref is None else pref

    def toggle_visible(self, user_id: int) -> bool:
        new = not self.visible_enabled(user_id)
        self.repo.set_visible_pref(user_id, new)
        return new

    def protect(
        self, data: bytes, *, owner_id: int, label: str, visible: bool | None = None
    ) -> ProtectResult:
        label = normalize_label(label)
        if not label:
            raise ValueError("Izoh (label) bo'sh bo'lmasligi kerak")
        visible = self.visible_enabled(owner_id) if visible is None else visible

        loaded = load_image(
            data,
            max_side=self.params.max_side,
            max_pixels=self.settings.max_input_pixels,
        )
        rgb = loaded.rgb
        now = datetime.now(timezone.utc)

        if visible:
            local = now.astimezone(self.tz)
            text = f"{label[:40]} • {local:%d.%m.%Y}"
            rgb = apply_visible_watermark(rgb, text)

        for _ in range(5):
            payload_id = secrets.token_bytes(self.params.id_bytes)
            work = rgb.copy()
            stats = self._embedder.embed(work, payload_id)
            if self.repo.add_record(
                WatermarkRecord(
                    payload_id=payload_id.hex(),
                    owner_id=owner_id,
                    label=label,
                    created_at=now,
                    params_fp=self.params.fingerprint(),
                )
            ):
                break
        else:
            raise DocGuardError("Unique. Cant make ID")
        rgb = work

        jpeg = encode_jpeg(rgb, quality=self.settings.jpeg_quality)
        return ProtectResult(
            jpeg=jpeg,
            payload_id=payload_id.hex(),
            label=label,
            created_at=now,
            metadata=loaded.metadata,
            psnr_db=float(stats.psnr_db),
            size=(rgb.shape[1], rgb.shape[0]),
            visible_applied=visible,
        )

    def verify(self, data: bytes, *, owner_id: int) -> VerifyResult:
        loaded = load_image(
            data,
            max_side=_DECODE_MAX_SIDE,
            max_pixels=self.settings.max_input_pixels,
            honor_orientation=False,
        )
        result = self._extractor.extract(loaded.rgb)
        if not result.found:
            return VerifyResult(VerifyStatus.NOT_FOUND, result)
        payload_id = result.id_hex
        if payload_id is None:
            return VerifyResult(VerifyStatus.UNKNOWN_ID, result)
        record = self.repo.get_record(payload_id)
        if record is None:
            return VerifyResult(VerifyStatus.UNKNOWN_ID, result)
        if record.owner_id != owner_id:
            return VerifyResult(VerifyStatus.FOREIGN, result)
        return VerifyResult(VerifyStatus.OWN, result, record)

    def local_time(self, dt: datetime) -> datetime:
        return dt.astimezone(self.tz)
