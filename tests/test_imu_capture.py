"""Native tests for the companion IMU serial protocol (no board required)."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
from imu_capture import TickUnwrapper, cobs_decode, crc16_ccitt, decode_sample


def encode_cobs(data: bytes) -> bytes:
    dst = bytearray()
    start = 0
    for i, v in enumerate(data):
        if v == 0 or i - start == 254:
            dst.append(i - start + 1)
            dst.extend(data[start:i])
            start = i + 1 if v == 0 else i
    # Standard COBS final block, including trailing-empty input blocks.
    end = data[start:]
    while len(end) >= 254:
        dst.append(255)
        dst.extend(end[:254])
        end = end[254:]
    dst.append(len(end) + 1)
    dst.extend(end)
    return bytes(dst)


class TestIMUPackets(unittest.TestCase):
    def test_crc_reference(self):
        self.assertEqual(crc16_ccitt(b"123456789"), 0x29B1)

    def test_cobs_roundtrip(self):
        for data in (b"\x00", b"a\x00b", b"\x00\x00", bytes(range(255)), b"hi"):
            self.assertEqual(cobs_decode(encode_cobs(data)), data)

    def test_valid_packet(self):
        payload = struct.pack("<4sBIIhhhI", b"IMU1", 0, 123, 0xFFFF_FFF0,
                              -123, 456, -789, 7)
        frame = payload + struct.pack("<H", crc16_ccitt(payload))
        self.assertEqual(len(frame), 25)
        d = decode_sample(encode_cobs(frame))
        self.assertEqual(d["sensor"], "gyro")
        self.assertEqual(d["sequence"], 123)
        self.assertEqual(d["capture_ticks32"], 0xFFFF_FFF0)
        self.assertEqual((d["x_raw"], d["y_raw"], d["z_raw"]), (-123, 456, -789))
        self.assertEqual(d["dropped_isr_events"], 7)

    def test_corrupt_crc(self):
        payload = struct.pack("<4sBIIhhhI", b"IMU1", 1, 123, 4, -1, 2, 3, 0)
        frame = bytearray(payload + struct.pack("<H", crc16_ccitt(payload)))
        frame[10] ^= 0x80
        with self.assertRaises(ValueError):
            decode_sample(encode_cobs(frame))

    def test_wrap_and_reordering(self):
        u = TickUnwrapper()
        t0, reordered = u.add(0xFFFF_FFE0)
        self.assertFalse(reordered)
        t1, reordered = u.add(0x0000_0020)
        self.assertFalse(reordered)
        self.assertEqual(t1 - t0, 64)
        earlier, reordered = u.add(0x0000_001F)
        self.assertTrue(reordered)
        self.assertEqual(t1-earlier, 1)
        t2, reordered = u.add(0x0000_0040)
        self.assertFalse(reordered)
        self.assertEqual(t2 - t1, 32)

    def test_reject_bad_magic(self):
        p = b"ABCD" + bytes(19)
        with self.assertRaises(ValueError):
            decode_sample(encode_cobs(p + struct.pack("<H", crc16_ccitt(p))))


if __name__ == "__main__":
    unittest.main()
