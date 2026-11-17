from __future__ import annotations

import logging
from dataclasses import dataclass

from PIL import Image

_GPS_IFD = 0x8825
_EXIF_IFD = 0x8769
_TAG_MAKE, _TAG_MODEL, _TAG_DATETIME, _TAG_DT_ORIGINAL = 0x010F, 0x0110, 0x0132, 0x9003
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MetadataReport:
    has_gps: bool = False
    camera: str | None = None
    captured_at: str | None = None
    has_icc: bool = False
    has_xmp: bool = False
    has_comment: bool = False
    has_exif: bool = False

    @property
    def anything_removed(self) -> bool:
        return any((self.has_gps, self.camera, self.captured_at, self.has_icc,
                    self.has_xmp, self.has_comment, self.has_exif))


def inspect_metadata(img: Image.Image) -> MetadataReport:
    has_gps, camera, captured, has_exif = False, None, None, False
    try:
        exif = img.getexif()
        has_exif = len(exif) > 0
        has_gps = bool(exif.get_ifd(_GPS_IFD))
        make, model = exif.get(_TAG_MAKE), exif.get(_TAG_MODEL)
        parts = [str(x).strip("\x00 ").strip() for x in (make, model) if x]
        camera = " ".join(parts) or None
        sub = exif.get_ifd(_EXIF_IFD)
        raw = sub.get(_TAG_DT_ORIGINAL) or exif.get(_TAG_DATETIME)
        captured = str(raw).strip("\x00 ") if raw else None
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        logger.exception("Unable to inspect EXIF metadata")
    info = img.info or {}
    return MetadataReport(
        has_gps=has_gps, camera=camera, captured_at=captured, has_exif=has_exif,
        has_icc=bool(info.get("icc_profile")),
        has_xmp=bool(info.get("xmp") or info.get("XML:com.adobe.xmp")),
        has_comment=bool(info.get("comment")),
    )
