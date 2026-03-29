"""Tests for wheelpulsepro.scoring (PR audit).

Verifies defensive behaviour introduced to prevent unhandled exceptions in
the Gradio callback chain:

  1. Non-integer spin values are skipped, not raised.
  2. Out-of-range spin values are skipped, not raised.
  3. Valid spin values update scores correctly.
  4. BETTING_MAPPINGS is populated before first use.
"""

import pytest

from wheelpulsepro.mappings import BETTING_MAPPINGS, initialize_betting_mappings
from wheelpulsepro.scoring import update_scores_batch
from wheelpulsepro.state import RouletteState

# Ensure mappings are populated for all tests in this module.
initialize_betting_mappings()

# Minimal left/right of zero sets used in the thin app.py wrapper.
_LEFT_OF_ZERO = {1, 3, 5, 7, 9, 12, 14, 16, 18, 20, 22, 24, 26, 28}
_RIGHT_OF_ZERO = {2, 4, 6, 8, 10, 11, 13, 15, 17, 19, 21, 23, 25, 27}


def _make_state() -> RouletteState:
    s = RouletteState()
    return s


# ---------------------------------------------------------------------------
# 1. Happy path — valid spins update scores correctly
# ---------------------------------------------------------------------------

def test_valid_spin_increments_straight_up():
    s = _make_state()
    update_scores_batch(["5"], s, _LEFT_OF_ZERO, _RIGHT_OF_ZERO, BETTING_MAPPINGS)
    assert s.scores[5] == 1
    assert all(s.scores[n] == 0 for n in range(37) if n != 5)


def test_valid_spin_zero():
    s = _make_state()
    log = update_scores_batch(["0"], s, _LEFT_OF_ZERO, _RIGHT_OF_ZERO, BETTING_MAPPINGS)
    assert s.scores[0] == 1
    assert len(log) == 1
    assert log[0]["spin"] == 0


def test_valid_spin_36():
    s = _make_state()
    log = update_scores_batch(["36"], s, _LEFT_OF_ZERO, _RIGHT_OF_ZERO, BETTING_MAPPINGS)
    assert s.scores[36] == 1
    assert len(log) == 1


def test_multiple_valid_spins():
    s = _make_state()
    log = update_scores_batch(["1", "2", "3"], s, _LEFT_OF_ZERO, _RIGHT_OF_ZERO, BETTING_MAPPINGS)
    assert s.scores[1] == 1
    assert s.scores[2] == 1
    assert s.scores[3] == 1
    assert len(log) == 3


def test_action_log_contains_spin_value():
    s = _make_state()
    log = update_scores_batch(["17"], s, _LEFT_OF_ZERO, _RIGHT_OF_ZERO, BETTING_MAPPINGS)
    assert log[0]["spin"] == 17
    assert "increments" in log[0]


def test_action_log_empty_for_no_spins():
    s = _make_state()
    log = update_scores_batch([], s, _LEFT_OF_ZERO, _RIGHT_OF_ZERO, BETTING_MAPPINGS)
    assert log == []


# ---------------------------------------------------------------------------
# 2. Defensive: non-integer spin values must be silently skipped, not raised
# ---------------------------------------------------------------------------

def test_non_integer_string_skipped():
    """A non-integer string must not raise — it is silently skipped."""
    s = _make_state()
    # Should not raise ValueError
    log = update_scores_batch(["abc"], s, _LEFT_OF_ZERO, _RIGHT_OF_ZERO, BETTING_MAPPINGS)
    assert log == [], "Non-integer spin should produce no action log entry"
    assert all(v == 0 for v in s.scores.values()), "Scores must remain unchanged"


def test_float_string_skipped():
    """A float string like '1.5' is not a valid integer spin."""
    s = _make_state()
    log = update_scores_batch(["1.5"], s, _LEFT_OF_ZERO, _RIGHT_OF_ZERO, BETTING_MAPPINGS)
    assert log == []


def test_empty_string_skipped():
    s = _make_state()
    log = update_scores_batch([""], s, _LEFT_OF_ZERO, _RIGHT_OF_ZERO, BETTING_MAPPINGS)
    assert log == []


def test_none_skipped():
    """None is not a valid spin value and must not raise."""
    s = _make_state()
    log = update_scores_batch([None], s, _LEFT_OF_ZERO, _RIGHT_OF_ZERO, BETTING_MAPPINGS)
    assert log == []


def test_mixed_valid_and_invalid():
    """Valid spins are processed; invalid ones are silently skipped."""
    s = _make_state()
    log = update_scores_batch(
        ["5", "abc", "12", None, "36"],
        s, _LEFT_OF_ZERO, _RIGHT_OF_ZERO, BETTING_MAPPINGS,
    )
    # Only 3 valid spins (5, 12, 36)
    assert len(log) == 3
    assert s.scores[5] == 1
    assert s.scores[12] == 1
    assert s.scores[36] == 1


# ---------------------------------------------------------------------------
# 3. Defensive: out-of-range spin values must be silently skipped, not raised
# ---------------------------------------------------------------------------

def test_spin_37_skipped():
    """37 is outside the valid roulette range (0-36) and must be skipped."""
    s = _make_state()
    log = update_scores_batch(["37"], s, _LEFT_OF_ZERO, _RIGHT_OF_ZERO, BETTING_MAPPINGS)
    assert log == []
    assert all(v == 0 for v in s.scores.values())


def test_negative_spin_skipped():
    s = _make_state()
    log = update_scores_batch(["-1"], s, _LEFT_OF_ZERO, _RIGHT_OF_ZERO, BETTING_MAPPINGS)
    assert log == []


def test_large_number_skipped():
    s = _make_state()
    log = update_scores_batch(["100"], s, _LEFT_OF_ZERO, _RIGHT_OF_ZERO, BETTING_MAPPINGS)
    assert log == []


# ---------------------------------------------------------------------------
# 4. BETTING_MAPPINGS populated before first use
# ---------------------------------------------------------------------------

def test_betting_mappings_covers_all_numbers():
    """After initialize_betting_mappings(), all 37 numbers (0-36) must be present."""
    assert len(BETTING_MAPPINGS) == 37
    for n in range(37):
        assert n in BETTING_MAPPINGS, f"Number {n} missing from BETTING_MAPPINGS"


def test_betting_mappings_not_empty():
    assert BETTING_MAPPINGS != {}
