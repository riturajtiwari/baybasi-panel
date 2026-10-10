"""Rev B boards take their column from a DIP switch, not from the Pi.

The switch is the whole configuration: a board reads it at boot, derives its
address and DDP id from it, and refuses an `assign`. The Pi's job shrinks to
noticing two things - which boards configure themselves, and whether two of
them have been set alike, which puts both on one column AND one address.
"""

import json
import logging
import time

import pytest

from baybasi.control import ControlPlane, SwitchConfigured

A = "ec:da:3b:45:a7:c8"
B = "ec:da:3b:45:a7:d0"
C = "ec:da:3b:45:a7:e4"


@pytest.fixture
def cp(wall, tmp_path):
    plane = ControlPlane(wall, table_path=tmp_path / "controllers.json",
                         listen=False)
    plane.sent = []
    plane._send = lambda payload, ip=None: plane.sent.append(payload) or True
    return plane


def announce(cp, mac, col, src="dip", ip="192.168.50.11"):
    msg = {"t": "announce", "mac": mac, "col": col, "fw": "0.2.0+c55754e",
           "up": 5, "link": True, "ip": ip}
    if src is not None:
        msg["col_src"] = src
    cp._on_message(json.dumps(msg).encode(), ip)


def row(cp, mac):
    return next(r for r in cp.snapshot() if r["mac"] == mac)


def test_the_announcement_says_where_the_column_came_from(cp):
    announce(cp, A, 1, "dip")
    assert row(cp, A)["col_src"] == "dip"


def test_a_switch_board_cannot_be_assigned(cp):
    announce(cp, A, 1, "dip")
    with pytest.raises(SwitchConfigured) as e:
        cp.assign(A, 2)
    # Read on a ladder: it has to say what to do instead.
    assert "switch" in str(e.value) and "column 1" in str(e.value)
    assert cp.sent == [], "nothing may go on the wire"
    assert cp.table.get(A) is None, "and nothing may be recorded"


def test_an_nvs_board_is_still_assigned_as_before(cp):
    announce(cp, A, None, "none")
    assert cp.assign(A, 2) is True
    assert cp.sent and cp.sent[-1]["t"] == "assign" and cp.sent[-1]["col"] == 2


def test_a_stale_table_entry_is_not_a_mismatch_on_a_switch_board(cp):
    # This board was commissioned as column 2 before it had a switch; the
    # switch now says 1. The switch wins, so this is healthy, not a fault.
    cp.table.set(A, 2)
    announce(cp, A, 1, "dip")
    assert row(cp, A)["state"] == "ok"


def test_the_same_disagreement_on_an_nvs_board_is_still_a_mismatch(cp):
    cp.table.set(A, 2)
    announce(cp, A, 1, "nvs")
    assert row(cp, A)["state"] == "mismatch"


def test_two_boards_set_alike_are_both_flagged(cp):
    announce(cp, A, 1, "dip", ip="192.168.50.12")
    announce(cp, B, 1, "dip", ip="192.168.50.12")
    announce(cp, C, 2, "dip", ip="192.168.50.13")
    assert row(cp, A)["state"] == "duplicate"
    assert row(cp, B)["state"] == "duplicate"
    assert row(cp, C)["state"] == "ok"
    assert "duplicate" in cp.firmware_report()


def test_a_board_that_went_offline_does_not_make_a_duplicate(cp):
    announce(cp, A, 1, "dip")
    announce(cp, B, 1, "dip")
    cp.seen[B].last_seen = time.time() - 60       # long gone
    assert row(cp, A)["state"] == "ok"
    assert row(cp, B)["state"] == "offline"


def test_firmware_too_old_to_say_still_parses(cp):
    announce(cp, A, 0, src=None)
    r = row(cp, A)
    assert r["col_src"] == "" and r["state"] == "ok"


def test_a_refusal_is_logged_with_its_reason(cp, caplog):
    with caplog.at_level(logging.WARNING, logger="baybasi.control"):
        cp._on_message(json.dumps({
            "t": "ack", "mac": A, "of": "assign", "ok": False,
            "why": "column is set by the DIP switch on this board"}).encode(),
            "192.168.50.12")
    assert "DIP switch" in caplog.text and A in caplog.text
