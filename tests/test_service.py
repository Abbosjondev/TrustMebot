import io
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from docguard.config import Settings
from docguard.errors import ImageTooLargeError, InvalidImageError
from docguard.service import ProtectionService, VerifyStatus, normalize_label
from docguard.storage import Repository
from tests.helpers import jpeg_roundtrip, synth_photo, to_jpeg_bytes


def _jpeg_with_gps(rgb: np.ndarray) -> bytes:
    exif = Image.Exif()
    exif[0x010F], exif[0x0110] = "Apple", "iPhone 15"
    exif[0x8825] = {1: "N", 2: (41.0, 18.0, 0.0), 3: "E", 4: (69.0, 16.0, 0.0)}
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, "JPEG", quality=90, exif=exif)
    return buf.getvalue()


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.settings = Settings(secret_key="k" * 32, db_path=Path(self._tmp.name) / "t.sqlite3",
                                 max_input_pixels=30_000_000)
        self.repo = Repository(self.settings.db_path)
        self.addCleanup(self.repo.close)
        self.svc = ProtectionService(self.settings, self.repo)

    def test_protect_strips_metadata_and_resizes(self):
        src = _jpeg_with_gps(synth_photo(2000, 3000, 3))
        self.assertTrue(Image.open(io.BytesIO(src)).getexif().get_ifd(0x8825))

        res = self.svc.protect(src, owner_id=1, label="Makler Rustamga berildi, 16.11.2026")
        self.assertTrue(res.metadata.has_gps)
        self.assertEqual(res.metadata.camera, "Apple iPhone 15")
        self.assertEqual(max(res.size), self.svc.params.max_side)

        out = Image.open(io.BytesIO(res.jpeg))
        self.assertEqual(len(out.getexif()), 0)
        self.assertFalse({"exif", "icc_profile", "xmp", "comment"} & set(out.info))

    def test_roundtrip_through_telegram_like_recompression(self):
        res = self.svc.protect(to_jpeg_bytes(synth_photo()), owner_id=1, label="Rustamga")
        leaked = to_jpeg_bytes(jpeg_roundtrip(np.array(Image.open(io.BytesIO(res.jpeg)).convert("RGB")), 70))
        v = self.svc.verify(leaked, owner_id=1)
        self.assertIs(v.status, VerifyStatus.OWN)
        self.assertEqual(v.record.label, "Rustamga")

    def test_other_user_cannot_read_label(self):
        res = self.svc.protect(to_jpeg_bytes(synth_photo()), owner_id=1, label="Maxfiy")
        v = self.svc.verify(res.jpeg, owner_id=2)
        self.assertIs(v.status, VerifyStatus.FOREIGN)
        self.assertIsNone(v.record)

    def test_visible_watermark_keeps_invisible_one_readable(self):
        res = self.svc.protect(to_jpeg_bytes(synth_photo()), owner_id=1, label="Rustamga", visible=True)
        self.assertTrue(res.visible_applied)
        self.assertIs(self.svc.verify(res.jpeg, owner_id=1).status, VerifyStatus.OWN)

    def test_unmarked_image_not_found(self):
        v = self.svc.verify(to_jpeg_bytes(synth_photo()), owner_id=1)
        self.assertIs(v.status, VerifyStatus.NOT_FOUND)

    def test_rejects_invalid_and_oversized_input(self):
        with self.assertRaises(InvalidImageError):
            self.svc.protect(b"not an image", owner_id=1, label="x")
        buf = io.BytesIO()
        Image.new("L", (6000, 6000)).save(buf, "PNG")           # 36 MP > 30 MP limit
        with self.assertRaises(ImageTooLargeError):
            self.svc.protect(buf.getvalue(), owner_id=1, label="x")

    def test_png_with_alpha_is_accepted(self):
        buf = io.BytesIO()
        Image.new("RGBA", (800, 600), (255, 255, 255, 0)).save(buf, "PNG")
        res = self.svc.protect(buf.getvalue(), owner_id=1, label="alpha")
        self.assertIs(self.svc.verify(res.jpeg, owner_id=1).status, VerifyStatus.OWN)

    def test_visible_preference_toggle(self):
        self.assertFalse(self.svc.visible_enabled(5))
        self.assertTrue(self.svc.toggle_visible(5))
        self.assertTrue(self.svc.visible_enabled(5))

    def test_label_normalization(self):
        self.assertEqual(normalize_label("  a\n\tb \x00 c  "), "a b c")
        self.assertEqual(len(normalize_label("x" * 1000)), 200)


if __name__ == "__main__":
    unittest.main()
