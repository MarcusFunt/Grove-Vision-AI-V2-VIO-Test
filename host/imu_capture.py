"""Record and validate XIAO ESP32-S3 hardware-captured LSM6DS3 packets.

This is a standalone companion stream, not synchronized with Grove VTF1 yet.
Requires: pip install pyserial
"""
from __future__ import annotations
import argparse
import json
import struct
import time
from dataclasses import dataclass
from pathlib import Path

PAYLOAD_LEN = 25
CAPTURE_HZ_DEFAULT = 80_000_000  # ESP32-S3 APB capture clock; check device header.


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def cobs_decode(encoded: bytes) -> bytes:
    if not encoded:
        raise ValueError("empty COBS frame")
    result = bytearray()
    i = 0
    while i < len(encoded):
        code = encoded[i]
        if code == 0:
            raise ValueError("zero code inside COBS frame")
        i += 1
        take = code - 1
        if i + take > len(encoded):
            raise ValueError("truncated COBS frame")
        result.extend(encoded[i:i + take])
        i += take
        if code < 255 and i < len(encoded):
            result.append(0)
    return bytes(result)


def decode_sample(encoded: bytes) -> dict:
    raw = cobs_decode(encoded)
    if len(raw) != PAYLOAD_LEN:
        raise ValueError(f"wrong packet length: {len(raw)}")
    if raw[:4] != b"IMU1":
        raise ValueError("wrong packet magic")
    observed_crc, = struct.unpack_from("<H", raw, 23)
    if crc16_ccitt(raw[:23]) != observed_crc:
        raise ValueError("bad CRC16")
    kind, seq, ticks, ax, ay, az, dropped = struct.unpack_from("<BIIhhhI", raw, 4)
    if kind not in (0, 1):
        raise ValueError("unknown sensor source")
    return {
        "sensor": "gyro" if kind == 0 else "accel",
        "sequence": seq,
        "capture_ticks32": ticks,
        "x_raw": ax,
        "y_raw": ay,
        "z_raw": az,
        "dropped_isr_events": dropped,
    }


@dataclass
class TickUnwrapper:
    """Order-preserving modular unwrapping; assumes consecutive captures < 2^31 ticks apart."""
    previous: int | None = None
    absolute: int = 0

    def add(self, ticks: int) -> tuple[int, bool]:
        if self.previous is None:
            self.previous = ticks
            self.absolute = ticks
            return self.absolute, False
        forward = (ticks - self.previous) & 0xFFFFFFFF
        if forward >= 0x80000000:
            # An out-of-order capture; keep reference at the last ordered event.
            return self.absolute - ((self.previous - ticks) & 0xFFFFFFFF), True
        self.absolute += forward
        self.previous = ticks
        return self.absolute, False


def record(port: str, baud: int, output: Path, seconds: float, clock_hz: int) -> None:
    import serial  # optional dependency
    unwrapped = TickUnwrapper()
    errors = 0
    samples = 0
    last_seq: int | None = None
    seq_gaps = 0
    started = time.monotonic()
    packet = bytearray()

    output.parent.mkdir(parents=True, exist_ok=True)
    with serial.Serial(port, baudrate=baud, timeout=0.2) as stream, output.open("w", encoding="utf-8") as out:
        while seconds <= 0 or time.monotonic() - started < seconds:
            chunk = stream.read(512)
            received_ns = time.monotonic_ns()
            for byte in chunk:
                if byte != 0:
                    packet.append(byte)
                    if len(packet) > 512:
                        packet.clear()
                        errors += 1
                    continue
                if not packet:
                    continue
                try:
                    sample = decode_sample(bytes(packet))
                except ValueError:
                    errors += 1  # Boot log, unframed text, bad data, etc.
                    packet.clear()
                    continue
                packet.clear()

                ticks64, reordered = unwrapped.add(sample["capture_ticks32"])
                sample["capture_ticks_unwrapped"] = ticks64
                sample["capture_seconds_relative_clock"] = ticks64 / clock_hz
                sample["capture_reordered"] = reordered
                sample["host_receipt_monotonic_ns"] = received_ns
                sample["timestamp_semantics"] = "IMU DRDY edge (not analog sample instant)"
                if last_seq is not None:
                    step = (sample["sequence"] - last_seq) & 0xFFFFFFFF
                    if step > 1 and step < 0x80000000:
                        seq_gaps += step - 1
                last_seq = sample["sequence"]
                out.write(json.dumps(sample, separators=(",", ":")) + "\n")
                samples += 1
                if samples % 1000 == 0:
                    print(f"samples={samples} parser_errors={errors} seq_gaps={seq_gaps} last_ISR_drops={sample['dropped_isr_events']}",
                          flush=True)
    print(f"Finished: {samples} samples, {errors} invalid/framing packets, {seq_gaps} sequence gaps; saved {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Serial device such as COM5 or /dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--out", type=Path, default=Path("logs/imu_capture.jsonl"))
    parser.add_argument("--capture-hz", type=int, default=CAPTURE_HZ_DEFAULT,
                        help="Check the board's #capture_clock_hz boot line; do not guess")
    opts = parser.parse_args()
    try:
        record(opts.port, opts.baud, opts.out, opts.seconds, opts.capture_hz)
    except KeyboardInterrupt:
        print("Interrupted")


if __name__ == "__main__":
    main()
