import random
import unittest

from docguard.core.reed_solomon import ReedSolomon
from docguard.errors import ReedSolomonError


class ReedSolomonTests(unittest.TestCase):
    def setUp(self):
        self.rs = ReedSolomon(14)
        self.rnd = random.Random(7)

    def _msg(self, n=8):
        return bytes(self.rnd.randrange(256) for _ in range(n))

    def test_clean_roundtrip(self):
        msg = self._msg()
        out, fixed = self.rs.decode(self.rs.encode(msg))
        self.assertEqual((out, fixed), (msg, 0))

    def test_corrects_errors_and_erasures_within_capacity(self):
        for _ in range(300):
            msg = self._msg()
            cw = bytearray(self.rs.encode(msg))
            n_erase = self.rnd.randrange(0, 6)
            n_err = self.rnd.randrange(0, (14 - n_erase) // 2 + 1)      # e + 2v <= nsym
            pos = self.rnd.sample(range(len(cw)), n_erase + n_err)
            for p in pos:
                cw[p] ^= self.rnd.randrange(1, 256)
            out, _ = self.rs.decode(bytes(cw), pos[:n_erase])
            self.assertEqual(out, msg)

    def test_beyond_capacity_never_returns_wrong_message_silently(self):
        wrong = 0
        for _ in range(200):
            msg = self._msg()
            cw = bytearray(self.rs.encode(msg))
            for p in self.rnd.sample(range(len(cw)), 10):
                cw[p] ^= self.rnd.randrange(1, 256)
            try:
                out, _ = self.rs.decode(bytes(cw))
                wrong += out != msg
            except ReedSolomonError:
                pass
        self.assertEqual(wrong, 0)


if __name__ == "__main__":
    unittest.main()
