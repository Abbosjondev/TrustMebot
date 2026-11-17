import unittest

import numpy as np

from docguard.core.codec import PayloadCodec
from docguard.core.layout import TileLayout
from docguard.core.params import WatermarkParams
from tests.helpers import KEY


class CodecTests(unittest.TestCase):
    def setUp(self):
        self.params = WatermarkParams(secret_key=KEY)
        self.codec = PayloadCodec(self.params)
        self.pid = bytes.fromhex("0123456789ab")

    def _llr(self, bits, flips=0, seed=1):
        llr = 1.0 - 2.0 * bits.astype(np.float64)           # bit 0 -> +1, bit 1 -> -1
        rng = np.random.default_rng(seed)
        for i in rng.choice(len(bits), flips, replace=False):
            llr[i] *= -0.3                                   # ishonchsiz xato
        return llr

    def test_clean(self):
        d = self.codec.decode(self._llr(self.codec.encode(self.pid)))
        self.assertIsNotNone(d)
        self.assertEqual(d.payload_id, self.pid)

    def test_survives_scattered_bit_errors(self):
        d = self.codec.decode(self._llr(self.codec.encode(self.pid), flips=12))
        self.assertIsNotNone(d)
        self.assertEqual(d.payload_id, self.pid)

    def test_garbage_is_rejected(self):
        rng = np.random.default_rng(5)
        hits = sum(self.codec.decode(rng.uniform(-1, 1, self.codec.n_bits)) is not None
                   for _ in range(200))
        self.assertEqual(hits, 0)

    def test_layout_is_deterministic_and_key_dependent(self):
        a = TileLayout.build(self.params, self.codec.n_bits)
        b = TileLayout.build(self.params, self.codec.n_bits)
        c = TileLayout.build(WatermarkParams(secret_key=b"a-totally-different-key"), self.codec.n_bits)
        self.assertTrue(np.array_equal(a.data_index, b.data_index))
        self.assertFalse(np.array_equal(a.data_index, c.data_index))
        self.assertEqual(int((a.data_index >= 0).sum()) + int((a.pilot_sign != 0).sum()), self.params.n_slots)


if __name__ == "__main__":
    unittest.main()
