"""Parser for the Grove Vision track packet. Standard library only."""
from __future__ import annotations
from dataclasses import dataclass
import struct

MAGIC = b"VTF1"
IMAGE_MAGIC = b"VTI1"
HEADER = struct.Struct("<4sBBHIQIHH")
TRACK = struct.Struct("<HHHBB")
IMAGE_HEADER = struct.Struct("<4sBHHII")
MAX_IMAGE_PIXELS = 320 * 240

@dataclass(frozen=True)
class Track:
    id: int
    x: int
    y: int
    quality: int
    age: int

@dataclass(frozen=True)
class Frame:
    sequence: int
    frame_ready_ticks: int
    process_ticks: int
    tracked_ok: int
    rejected: int
    timestamp_kind: int
    features: tuple[Track, ...]

@dataclass(frozen=True)
class CameraImage:
    sequence: int
    width: int
    height: int
    pixels: bytes

def crc16(data: bytes) -> int:
    crc = 0xffff
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xffff
    return crc

def cobs_decode(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        code = data[i]
        if code == 0:
            raise ValueError("embedded COBS delimiter")
        i += 1
        count = code - 1
        if i + count > len(data):
            raise ValueError("truncated COBS")
        out += data[i:i+count]
        i += count
        if code < 255 and i < len(data):
            out.append(0)
    return bytes(out)

def _check_crc(raw: bytes) -> None:
    if len(raw) < 6:
        raise ValueError("short packet")
    stored_crc, = struct.unpack_from("<H", raw, len(raw)-2)
    if crc16(raw[:-2]) != stored_crc:
        raise ValueError("bad CRC")

def _parse_frame_raw(raw: bytes) -> Frame:
    if len(raw) < HEADER.size + 2:
        raise ValueError("short packet")
    _check_crc(raw)
    magic, ver, kind, count, seq, ticks, dt, ok, rejected = HEADER.unpack_from(raw)
    if magic != MAGIC or ver != 1 or kind != 1:
        raise ValueError("wrong packet type")
    if count > 96 or len(raw) != HEADER.size + count*TRACK.size + 2:
        raise ValueError("invalid feature count / packet length")
    features = tuple(Track(*TRACK.unpack_from(raw, HEADER.size+i*TRACK.size)) for i in range(count))
    return Frame(seq, ticks, dt, ok, rejected, kind, features)

def _parse_image_raw(raw: bytes) -> CameraImage:
    if len(raw) < IMAGE_HEADER.size + 2:
        raise ValueError("short camera packet")
    _check_crc(raw)
    magic, version, width, height, sequence, payload_size = IMAGE_HEADER.unpack_from(raw)
    if magic != IMAGE_MAGIC or version != 1:
        raise ValueError("wrong camera packet type")
    if not width or not height or width * height > MAX_IMAGE_PIXELS:
        raise ValueError("invalid camera image dimensions")
    if payload_size != width * height or len(raw) != IMAGE_HEADER.size + payload_size + 2:
        raise ValueError("invalid camera image payload length")
    pixels = raw[IMAGE_HEADER.size:-2]
    return CameraImage(sequence, width, height, pixels)

def parse_packet(encoded: bytes) -> Frame:
    return _parse_frame_raw(cobs_decode(encoded))

def parse_image_packet(encoded: bytes) -> CameraImage:
    return _parse_image_raw(cobs_decode(encoded))

class StreamDecoder:
    """Decode mixed COBS-framed VTF1 tracking and VTI1 image packets."""
    def __init__(self, max_encoded=32768):
        self.buffer = bytearray()
        self.started = False
        self.ok = 0
        self.bad = 0
        self.max_encoded = max_encoded

    def feed(self, data: bytes) -> list[Frame | CameraImage]:
        frames = []
        for value in data:
            if value == 0:
                if self.started and self.buffer:
                    try:
                        raw = cobs_decode(bytes(self.buffer))
                        if raw.startswith(MAGIC):
                            frames.append(_parse_frame_raw(raw))
                        elif raw.startswith(IMAGE_MAGIC):
                            frames.append(_parse_image_raw(raw))
                        else:
                            raise ValueError("wrong packet type")
                        self.ok += 1
                    except ValueError:
                        self.bad += 1
                self.started = True
                self.buffer.clear()
                continue
            if self.started:
                if len(self.buffer) < self.max_encoded:
                    self.buffer.append(value)
                else:
                    self.started = False
                    self.buffer.clear()
                    self.bad += 1
        return frames

class PacketDecoder(StreamDecoder):
    """Feature-only compatibility wrapper; valid image packets are ignored."""
    def feed(self, data: bytes) -> list[Frame]:
        return [packet for packet in super().feed(data) if isinstance(packet, Frame)]
