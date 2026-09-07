"""Driver to sink, over a real socket. The check the whole system rests on."""

import time

import numpy as np
import pytest

from baybasi import patterns
from baybasi.pixels import Pipeline
from baybasi.sender import DDPSender, WallClockPacer, bandwidth_report
from baybasi.sink import DDPReceiver, DDPSink


@pytest.fixture
def loop(wall):
    sink = DDPSink(wall)
    rx = DDPReceiver(sink, host="127.0.0.1", port=wall.network.ddp_port)
    rx.start()
    yield sink
    rx.stop()
    sink.close()


def _send_and_settle(tx, sink, frames_out, timeout=3.0):
    for f in frames_out:
        tx.send_frame(f)
        time.sleep(0.02)
    end = time.time() + timeout
    while time.time() < end and sink.stats.frames < len(frames_out):
        time.sleep(0.02)


def test_every_pattern_survives_the_wire_byte_for_byte(wall, loop):
    got = []
    loop.on_frame = got.append
    pipe = Pipeline(wall, gamma=1.0, brightness=1.0, dither="none")
    sent = [patterns.build(n, wall).frame(11)
            for n in ("id", "strand", "scroll", "chase", "bars")]
    with DDPSender(wall, pipeline=pipe, broadcast="127.0.0.1") as tx:
        _send_and_settle(tx, loop, sent)
    loop.flush()

    assert loop.stats.violations == 0, "the sender broke a wire rule"
    assert loop.stats.torn == 0
    assert len(got) == len(sent)
    for a, b in zip(sent, got):
        assert np.array_equal(a, b)


def test_gamma_and_dither_survive_the_wire(wall, loop, frame):
    got = []
    loop.on_frame = got.append
    pipe = Pipeline(wall, gamma=2.2, brightness=0.4, dither="bayer8")
    expected = pipe.to_wire8(frame)
    with DDPSender(wall, pipeline=pipe, broadcast="127.0.0.1") as tx:
        _send_and_settle(tx, loop, [frame])
    loop.flush()
    assert np.array_equal(got[0], expected)


def test_seven_packets_and_one_broadcast_push_per_frame(wall, loop, frame):
    with DDPSender(wall, broadcast="127.0.0.1") as tx:
        pre = tx.build(frame)
    assert len(pre.packets) == 28          # 4 controllers x 7
    assert len(pre.push) == 10             # zero-length PUSH
    per_controller = {}
    for ip, pkt in pre.packets:
        per_controller.setdefault(pkt[3], []).append(pkt)
    assert sorted(per_controller) == [10, 11, 12, 13]
    assert all(len(v) == 7 for v in per_controller.values())


def test_torn_frame_is_dropped_not_shown(wall, loop, frame):
    from baybasi import ddp
    got = []
    loop.on_frame = got.append
    pipe = Pipeline(wall, gamma=1.0, brightness=1.0, dither="none")
    with DDPSender(wall, pipeline=pipe, broadcast="127.0.0.1") as tx:
        pre = tx.build(frame)
        # Drop one packet, then push. A half-written frame must never appear.
        for ip, pkt in pre.packets[:-1]:
            tx.sock.sendto(pkt, (ip, wall.network.ddp_port))
        tx.sock.sendto(pre.push, ("127.0.0.1", wall.network.ddp_port))
        time.sleep(0.4)
    loop.flush()
    assert got == []
    assert loop.stats.torn == 1


def test_sink_flags_a_push_riding_on_a_data_packet(wall, loop, frame):
    from baybasi import ddp
    bad = []
    loop.on_violation = bad.append
    with DDPSender(wall, broadcast="127.0.0.1") as tx:
        pkt = ddp.build_data_packet(b"\0" * 30, offset=0, dest_id=10, push=True)
        tx.sock.sendto(pkt, ("127.0.0.1", wall.network.ddp_port))
        time.sleep(0.3)
    assert any("PUSH" in m for m in bad)


def test_sink_flags_an_oversize_payload(wall, loop):
    from baybasi import ddp
    import socket
    bad = []
    loop.on_violation = bad.append
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    raw = ddp.pack_header(offset=0, length=1500, dest_id=10) + b"\0" * 1500
    s.sendto(raw, ("127.0.0.1", wall.network.ddp_port))
    s.close()
    time.sleep(0.3)
    assert any("1472" in m for m in bad)


def test_bandwidth_matches_the_handoff(wall):
    wall.render.fps = 30
    report = bandwidth_report(wall)
    assert "29 packets/frame" in report
    parts = report.split()
    mbps = float(parts[parts.index("Mbps") - 1])
    assert 8.5 < mbps < 9.5      # the handoff says "about 8.8 Mbps"


def test_pacer_derives_the_frame_index_from_wall_clock():
    epoch = 1000.0
    p = WallClockPacer(30, epoch)
    assert p.index_now(epoch) == 0
    assert p.index_now(epoch + 1.0) == 30
    assert p.index_now(epoch + 3600.0) == 108000
    # Two Pis with the same epoch and the same clock pick the same frame; that
    # is the entire synchronisation mechanism.
    q = WallClockPacer(30, epoch)
    t = epoch + 12345.678
    assert p.index_now(t) == q.index_now(t)
