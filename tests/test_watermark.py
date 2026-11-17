"""Yadro: joylash -> (Telegram'ga o'xshash buzilishlar) -> o'qish."""

import unittest

import numpy as np
from PIL import Image

from docguard.core import Embedder, Extractor, WatermarkParams
from docguard.errors import ImageTooSmallError
from tests.helpers import KEY, jpeg_roundtrip, synth_photo, white_scan

PID = bytes.fromhex("a1b2c3d4e5f6")


class WatermarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.params = WatermarkParams(secret_key=KEY)
        cls.embedder = Embedder(cls.params)
        cls.extractor = Extractor(cls.params)
        cls.original = synth_photo()
        cls.marked = cls.original.copy()
        cls.stats = cls.embedder.embed(cls.marked, PID)

    def assertFound(self, arr, msg=""):
        res = self.extractor.extract(arr)
        self.assertTrue(res.found, f"{msg}: topilmadi ({res.reason}, pilot={res.pilot_score})")
        self.assertEqual(res.payload_id, PID, msg)
        return res

    def test_invisible_enough(self):
        self.assertGreater(self.stats.psnr_db, 40.0)

    def test_lossless(self):
        self.assertFound(self.marked, "lossless")

    def test_telegram_like_jpeg_qualities(self):
        for q in (90, 75, 60, 50):
            self.assertFound(jpeg_roundtrip(self.marked, q), f"jpeg q{q}")

    def test_double_compression(self):
        self.assertFound(jpeg_roundtrip(jpeg_roundtrip(self.marked, 80), 70), "double jpeg")

    def test_crop_with_arbitrary_offset(self):
        img = jpeg_roundtrip(self.marked, 75)
        self.assertFound(img[37:737, 53:953], "crop 37,53")
        self.assertFound(img[3:303, 5:305], "crop 300x300")

    def test_downscaled_copy_is_recovered_via_canonical_rescale(self):
        small = Image.fromarray(self.marked).resize((1024, 768), Image.Resampling.LANCZOS)
        res = self.assertFound(jpeg_roundtrip(np.array(small), 75), "scale 0.8")
        self.assertEqual(res.rescaled_to, self.params.max_side)

    def test_pure_white_scan_is_watermarked(self):
        scan = white_scan()
        marked = scan.copy()
        self.embedder.embed(marked, PID)
        self.assertFound(jpeg_roundtrip(marked, 75), "white scan")
        self.assertFound(jpeg_roundtrip(marked, 75)[50:900, 40:700], "white scan crop")

    def test_unmarked_image_is_not_found(self):
        self.assertFalse(self.extractor.extract(jpeg_roundtrip(self.original, 75)).found)

    def test_wrong_key_does_not_read_watermark(self):
        other = Extractor(WatermarkParams(secret_key=b"another-secret-key-999"))
        self.assertFalse(other.extract(jpeg_roundtrip(self.marked, 75)).found)

    def test_too_small_image_is_rejected(self):
        with self.assertRaises(ImageTooSmallError):
            self.embedder.embed(np.zeros((100, 100, 3), np.uint8), PID)

    def test_embed_is_deterministic(self):
        again = self.original.copy()
        self.embedder.embed(again, PID)
        self.assertTrue(np.array_equal(again, self.marked))


if __name__ == "__main__":
    unittest.main()
