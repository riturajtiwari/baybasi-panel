"""The wire rules from the handoff, asserted rather than assumed."""

import pytest

from baybasi import ddp


def test_header_round_trip():
    raw = ddp.pack_header(offset=1440, length=576, dest_id=12, sequence=7)
    h = ddp.parse_header(raw)
    assert (h.offset, h.length, h.dest_id, h.sequence) == (1440, 576, 12, 7)
    assert h.version == 1 and not h.push


def test_header_is_ten_bytes():
    assert len(ddp.pack_header(offset=0, length=0)) == ddp.HEADER_LEN == 10


def test_payload_ceiling_is_enforced():
    # The W5500 does not fragment IP, so an oversized packet is a bug, not a
    # tuning knob. It must fail at build time, not silently on the wire.
    with pytest.raises(ddp.DDPError):
        ddp.build_data_packet(b"\0" * (ddp.MAX_DATA_LEN + 1), offset=0)


def test_480_pixels_fits_the_documented_budget():
    pkt = ddp.build_data_packet(b"\0" * (480 * 3), offset=0)
    assert len(pkt) == 1450
    assert len(pkt) <= ddp.MAX_UDP_PAYLOAD


def test_split_frame_covers_every_byte_exactly_once():
    data = bytes(range(256)) * 36  # 9216 bytes
    assert len(data) == 9216
    packets = list(ddp.split_frame(data, dest_id=10, sequence=3))
    assert len(packets) == 7  # six full, one short

    seen = bytearray(len(data))
    rebuilt = bytearray(len(data))
    for raw in packets:
        assert len(raw) <= ddp.MAX_UDP_PAYLOAD
        pkt = ddp.parse_packet(raw)
        # No data packet may carry PUSH: that latches one column early and
        # tears at the seam.
        assert not pkt.header.push
        assert pkt.header.dest_id == 10
        o, n = pkt.header.offset, pkt.header.length
        rebuilt[o:o + n] = pkt.data
        for i in range(o, o + n):
            seen[i] += 1
    assert bytes(rebuilt) == data
    assert set(seen) == {1}


def test_push_is_zero_length_and_broadcast_addressed():
    push = ddp.build_push_packet()
    assert len(push) == ddp.HEADER_LEN
    h = ddp.parse_header(push)
    assert h.push and h.length == 0 and h.dest_id == ddp.ID_ALL


def test_sequence_never_emits_zero():
    seq = 0
    seen = set()
    for _ in range(40):
        seq = ddp.next_sequence(seq)
        seen.add(seq)
    assert seen == set(range(1, 16))


def test_rejects_wrong_version_and_timecode():
    bad = bytes([0x00]) + ddp.pack_header(offset=0, length=0)[1:]
    with pytest.raises(ddp.DDPError):
        ddp.parse_header(bad)
    tc = bytes([ddp.FLAG_VERSION_1 | ddp.FLAG_TIMECODE]) + \
        ddp.pack_header(offset=0, length=0)[1:]
    with pytest.raises(ddp.DDPError):
        ddp.parse_header(tc)
