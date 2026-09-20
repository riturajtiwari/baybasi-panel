"""Commissioning: binding a MAC to a column without creating a duplicate.

Two boards on one column is the expensive failure here. A quarter of the wall
renders twice, the other quarter goes dark, and it looks like a content bug
rather than a wiring one - so it gets debugged in the wrong place, at height,
at night. These tests exist to make that state unreachable by accident.
"""

import json

import pytest

from baybasi.control import AssignmentTable, DuplicateColumn

A = "ae:27:6e:a5:83:8d"
B = "ae:27:6e:a5:83:99"


@pytest.fixture
def table(tmp_path):
    return AssignmentTable(tmp_path / "controllers.json")


def test_a_column_belongs_to_one_board(table):
    table.set(A, 0)
    assert table.holder_of(0) == A
    assert table.get(A) == 0


def test_a_second_board_cannot_take_a_held_column(table):
    table.set(A, 0)
    with pytest.raises(DuplicateColumn) as e:
        table.set(B, 0)
    # The message has to say what to do, not just that it refused: this is
    # read on a ladder.
    assert A in str(e.value) and "--force" in str(e.value)
    assert table.holder_of(0) == A, "the refusal must not have changed anything"
    assert table.get(B) is None


def test_force_moves_the_column_and_leaves_exactly_one_holder(table):
    table.set(A, 0)
    table.set(B, 0, force=True)
    assert table.holder_of(0) == B
    assert table.get(A) is None, "the old board must not still hold it"
    assert list(table.map.values()).count(0) == 1


def test_reassigning_the_same_board_is_not_a_duplicate(table):
    table.set(A, 0)
    table.set(A, 0)          # idempotent, no force needed
    assert table.holder_of(0) == A


def test_a_board_can_move_to_a_free_column(table):
    table.set(A, 0)
    table.set(A, 2)
    assert table.holder_of(2) == A
    assert table.holder_of(0) is None, "it must not hold both"


def test_assignments_survive_a_restart(table, tmp_path):
    table.set(A, 1)
    again = AssignmentTable(tmp_path / "controllers.json")
    assert again.get(A) == 1
    assert again.holder_of(1) == A


def test_clear_frees_the_column(table):
    table.set(A, 0)
    table.clear(A)
    assert table.holder_of(0) is None
    table.set(B, 0)          # no force needed now
    assert table.holder_of(0) == B


def test_the_table_on_disk_is_a_plain_mac_to_column_map(table, tmp_path):
    """Someone will edit this by hand at some point. It should be obvious."""
    table.set(A, 3)
    doc = json.loads((tmp_path / "controllers.json").read_text())
    assert doc == {A: 3}
