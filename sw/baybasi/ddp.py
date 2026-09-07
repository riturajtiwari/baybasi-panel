"""DDP (Distributed Display Protocol) over UDP, port 4048.

Header layout, from the 3waylabs DDP specification::

    byte 0    flags1   V V x T S R Q P
                       VV = version (01), T = timecode present, S = storage,
                       R = reply, Q = query, P = push
    byte 1    flags2   x x x x n n n n     sequence 1..15, 0 = unused
    byte 2    type     C R T T T S S S     TTT = 001 RGB, SSS = 011 8 bits
    byte 3    id       1 = default output device, 2..249 custom, 255 = all
    byte 4-7  offset   byte offset into the destination's own address space, MSB first
    byte 8-9  length   length of the data field in bytes, MSB first

Wire rules for this wall, from HANDOFF-software.md:

* UDP payload must never exceed 1472 bytes, because the W5500 does not
  fragment IP.  480 pixels is 1440 bytes of data plus the 10-byte header,
  so 1450 bytes on the wire.
* Data packets never carry PUSH.  A single zero-length broadcast PUSH latches
  all four controllers on the same frame.
* ``offset`` is relative to the controller, not to the wall.  Each controller
  owns 3072 pixels / 9216 bytes and its first packet is always offset 0.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterator, Optional

DDP_PORT = 4048
CONTROL_PORT = 4049  # announce / assign / OTA, not pixels

HEADER_LEN = 10

FLAG_VERSION_MASK = 0xC0
FLAG_VERSION_1 = 0x40
FLAG_TIMECODE = 0x10
FLAG_STORAGE = 0x08
FLAG_REPLY = 0x04
FLAG_QUERY = 0x02
FLAG_PUSH = 0x01

TYPE_RGB8 = 0x0B  # customer=0, reserved=0, type=001 (RGB), size=011 (8 bit)

ID_RESERVED = 0
ID_DEFAULT_OUTPUT = 1
ID_ALL = 255

# Hard ceiling from the handoff.  A payload over this is a bug, not a tuning knob.
MAX_UDP_PAYLOAD = 1472
MAX_DATA_LEN = MAX_UDP_PAYLOAD - HEADER_LEN  # 1462

# What we actually use: 480 px * 3 bytes.
DEFAULT_PIXELS_PER_PACKET = 480


class DDPError(ValueError):
    """A malformed or out-of-spec DDP packet."""


@dataclass(frozen=True)
class DDPHeader:
    flags: int
    sequence: int
    data_type: int
    dest_id: int
    offset: int
    length: int

    @property
    def version(self) -> int:
        return (self.flags & FLAG_VERSION_MASK) >> 6

    @property
    def push(self) -> bool:
        return bool(self.flags & FLAG_PUSH)

    @property
    def query(self) -> bool:
        return bool(self.flags & FLAG_QUERY)

    @property
    def reply(self) -> bool:
        return bool(self.flags & FLAG_REPLY)

    @property
    def timecode(self) -> bool:
        return bool(self.flags & FLAG_TIMECODE)


_HDR = struct.Struct("!BBBBIH")


def pack_header(
    *,
    offset: int,
    length: int,
    dest_id: int = ID_DEFAULT_OUTPUT,
    sequence: int = 0,
    push: bool = False,
    data_type: int = TYPE_RGB8,
) -> bytes:
    if not 0 <= sequence <= 15:
        raise DDPError(f"sequence must be 0..15, got {sequence}")
    if not 0 <= dest_id <= 255:
        raise DDPError(f"dest_id must be 0..255, got {dest_id}")
    if offset < 0 or offset > 0xFFFFFFFF:
        raise DDPError(f"offset out of range: {offset}")
    if length < 0 or length > 0xFFFF:
        raise DDPError(f"length out of range: {length}")
    flags = FLAG_VERSION_1 | (FLAG_PUSH if push else 0)
    return _HDR.pack(flags, sequence & 0x0F, data_type, dest_id, offset, length)


def parse_header(buf: bytes) -> DDPHeader:
    if len(buf) < HEADER_LEN:
        raise DDPError(f"short packet: {len(buf)} bytes, need {HEADER_LEN}")
    flags, seq, dtype, dest, offset, length = _HDR.unpack_from(buf, 0)
    hdr = DDPHeader(
        flags=flags,
        sequence=seq & 0x0F,
        data_type=dtype,
        dest_id=dest,
        offset=offset,
        length=length,
    )
    if hdr.version != 1:
        raise DDPError(f"unsupported DDP version {hdr.version}")
    if hdr.timecode:
        # A timecode adds 4 bytes between header and data.  We never send one;
        # rejecting it is honest, and silently mis-parsing it is not.
        raise DDPError("timecode header is not supported by this implementation")
    return hdr


def build_data_packet(
    payload: bytes,
    *,
    offset: int,
    dest_id: int = ID_DEFAULT_OUTPUT,
    sequence: int = 0,
    push: bool = False,
    data_type: int = TYPE_RGB8,
) -> bytes:
    if len(payload) > MAX_DATA_LEN:
        raise DDPError(
            f"payload {len(payload)} bytes exceeds {MAX_DATA_LEN}; "
            "the W5500 does not fragment IP"
        )
    pkt = pack_header(
        offset=offset,
        length=len(payload),
        dest_id=dest_id,
        sequence=sequence,
        push=push,
        data_type=data_type,
    ) + payload
    assert len(pkt) <= MAX_UDP_PAYLOAD
    return pkt


def build_push_packet(
    *, dest_id: int = ID_ALL, sequence: int = 0, data_type: int = TYPE_RGB8
) -> bytes:
    """A zero-length PUSH.  Broadcast this to latch every controller together."""
    return pack_header(
        offset=0, length=0, dest_id=dest_id, sequence=sequence, push=True,
        data_type=data_type,
    )


def split_frame(
    data: bytes,
    *,
    dest_id: int = ID_DEFAULT_OUTPUT,
    sequence: int = 0,
    pixels_per_packet: int = DEFAULT_PIXELS_PER_PACKET,
    bytes_per_pixel: int = 3,
    data_type: int = TYPE_RGB8,
) -> Iterator[bytes]:
    """Chunk one controller's pixel buffer into DDP data packets.

    No packet carries PUSH; the caller sends one broadcast PUSH afterwards.
    """
    chunk = pixels_per_packet * bytes_per_pixel
    if chunk > MAX_DATA_LEN:
        raise DDPError(
            f"{pixels_per_packet} px/packet is {chunk} bytes, over the "
            f"{MAX_DATA_LEN}-byte limit"
        )
    for off in range(0, len(data), chunk):
        yield build_data_packet(
            data[off : off + chunk],
            offset=off,
            dest_id=dest_id,
            sequence=sequence,
            data_type=data_type,
        )


def next_sequence(seq: int) -> int:
    """1..15, wrapping.  0 means 'not used' and we never emit it."""
    return seq % 15 + 1


@dataclass(frozen=True)
class DDPPacket:
    header: DDPHeader
    data: bytes

    @property
    def truncated(self) -> bool:
        return len(self.data) < self.header.length


def parse_packet(buf: bytes) -> DDPPacket:
    hdr = parse_header(buf)
    return DDPPacket(header=hdr, data=buf[HEADER_LEN : HEADER_LEN + hdr.length])


def describe(pkt: DDPPacket, wire_len: Optional[int] = None) -> str:
    bits = []
    if pkt.header.push:
        bits.append("PUSH")
    if pkt.header.query:
        bits.append("QUERY")
    if pkt.header.reply:
        bits.append("REPLY")
    flags = "|".join(bits) or "-"
    size = f" wire={wire_len}" if wire_len is not None else ""
    return (
        f"id={pkt.header.dest_id} seq={pkt.header.sequence} "
        f"off={pkt.header.offset} len={pkt.header.length} {flags}{size}"
    )
