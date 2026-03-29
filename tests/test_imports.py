"""Smoke / import tests for the wheelpulsepro package refactor.

These tests verify that:
  1. All new sub-modules can be imported without triggering Gradio or any UI
     side-effects.
  2. The key symbols exist and are of the correct type.
  3. initialize_betting_mappings() populates BETTING_MAPPINGS for every valid
     roulette number (0-36).
  4. validate_roulette_data() returns no errors against the bundled data.
  5. update_scores_batch() correctly updates a RouletteState for a small batch.
  6. app.py can be imported end-to-end (skipped when Gradio is not installed).
"""

import importlib
import importlib.util
import types

import pytest

_GRADIO_AVAILABLE = importlib.util.find_spec("gradio") is not None


# ---------------------------------------------------------------------------
# 1. Package-level import
# ---------------------------------------------------------------------------

def test_wheelpulsepro_package_importable():
    pkg = importlib.import_module("wheelpulsepro")
    assert isinstance(pkg, types.ModuleType)


# ---------------------------------------------------------------------------
# 2. Sub-module imports and symbol presence
# ---------------------------------------------------------------------------

def test_mappings_module_importable():
    mod = importlib.import_module("wheelpulsepro.mappings")
    assert hasattr(mod, "BETTING_MAPPINGS")
    assert hasattr(mod, "initialize_betting_mappings")
    assert hasattr(mod, "validate_roulette_data")


def test_state_module_importable():
    mod = importlib.import_module("wheelpulsepro.state")
    assert hasattr(mod, "RouletteState")


def test_scoring_module_importable():
    mod = importlib.import_module("wheelpulsepro.scoring")
    assert hasattr(mod, "update_scores_batch")


# ---------------------------------------------------------------------------
# 3. initialize_betting_mappings populates BETTING_MAPPINGS
# ---------------------------------------------------------------------------

def test_initialize_betting_mappings_populates_all_numbers():
    from wheelpulsepro.mappings import BETTING_MAPPINGS, initialize_betting_mappings

    initialize_betting_mappings()

    assert len(BETTING_MAPPINGS) == 37, "Expected one entry per roulette number (0-36)"
    for num in range(37):
        assert num in BETTING_MAPPINGS, f"Number {num} missing from BETTING_MAPPINGS"
        entry = BETTING_MAPPINGS[num]
        for key in ("even_money", "dozens", "columns", "streets", "corners", "six_lines", "splits"):
            assert key in entry, f"Category '{key}' missing for number {num}"
            assert isinstance(entry[key], list), f"BETTING_MAPPINGS[{num}]['{key}'] must be a list"

    # Verify specific well-known mappings for number 1 (Red, Odd, Low; 1st Dozen; 1st Column)
    num1 = BETTING_MAPPINGS[1]
    assert "Red" in num1["even_money"], "Number 1 should be Red"
    assert "Odd" in num1["even_money"], "Number 1 should be Odd"
    assert "Low" in num1["even_money"], "Number 1 should be Low (1-18)"
    assert "1st Dozen" in num1["dozens"], "Number 1 should be in the 1st Dozen"
    assert "1st Column" in num1["columns"], "Number 1 should be in the 1st Column"

    # Zero should have no even-money, dozen, or column membership
    num0 = BETTING_MAPPINGS[0]
    assert num0["even_money"] == [], "Zero should not belong to any even-money category"
    assert num0["dozens"] == [], "Zero should not belong to any dozen"
    assert num0["columns"] == [], "Zero should not belong to any column"


# ---------------------------------------------------------------------------
# 4. validate_roulette_data returns no errors
# ---------------------------------------------------------------------------

def test_validate_roulette_data_no_errors():
    from wheelpulsepro.mappings import validate_roulette_data

    errors = validate_roulette_data()
    assert errors is None, f"validate_roulette_data() returned errors: {errors}"


# ---------------------------------------------------------------------------
# 5. RouletteState initialises correctly
# ---------------------------------------------------------------------------

def test_roulette_state_initialises():
    from wheelpulsepro.state import RouletteState

    s = RouletteState()
    assert isinstance(s.scores, dict)
    assert len(s.scores) == 37
    assert s.last_spins == []
    # Default bankroll is 1000 as defined in RouletteState.__init__
    assert s.bankroll == s.initial_bankroll == 1000


# ---------------------------------------------------------------------------
# 6. update_scores_batch applies increments correctly
# ---------------------------------------------------------------------------

def test_update_scores_batch_increments():
    from wheelpulsepro.mappings import BETTING_MAPPINGS, initialize_betting_mappings
    from wheelpulsepro.scoring import update_scores_batch
    from wheelpulsepro.state import RouletteState
    from roulette_data import LEFT_OF_ZERO_EUROPEAN, RIGHT_OF_ZERO_EUROPEAN

    initialize_betting_mappings()
    state = RouletteState()

    left = set(LEFT_OF_ZERO_EUROPEAN)
    right = set(RIGHT_OF_ZERO_EUROPEAN)

    spins = [1, 5, 17, 0]
    log = update_scores_batch(spins, state, left, right, BETTING_MAPPINGS)

    assert len(log) == len(spins), "Action log must have one entry per spin"
    assert state.scores[1] == 1
    assert state.scores[5] == 1
    assert state.scores[17] == 1
    assert state.scores[0] == 1

    # Verify log structure
    for entry in log:
        assert "spin" in entry
        assert "increments" in entry

    # Verify that wheel position (left/right of zero) is tracked in the log
    # Pick one number known to be on the left side and one on the right side
    left_num = next(iter(left))
    right_num = next(iter(right))

    state2 = RouletteState()
    log2 = update_scores_batch([left_num], state2, left, right, BETTING_MAPPINGS)
    assert state2.side_scores["Left Side of Zero"] == 1
    assert "side_scores" in log2[0]["increments"]
    assert "Left Side of Zero" in log2[0]["increments"]["side_scores"]

    state3 = RouletteState()
    log3 = update_scores_batch([right_num], state3, left, right, BETTING_MAPPINGS)
    assert state3.side_scores["Right Side of Zero"] == 1
    assert "side_scores" in log3[0]["increments"]
    assert "Right Side of Zero" in log3[0]["increments"]["side_scores"]


# ---------------------------------------------------------------------------
# 7. app.py is importable (thin integration smoke test – imports Gradio)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _GRADIO_AVAILABLE, reason="gradio not installed")
def test_app_importable():
    """Confirm that app.py can be imported without raising exceptions.

    This exercises the full import chain:  app.py -> wheelpulsepro.* -> roulette_data

    demo.queue() and demo.launch() are called at module level (required for HF
    Spaces, which imports app.py rather than running it as __main__).  We mock
    both methods so that no real server is started during the test.
    """
    import sys
    import unittest.mock as mock

    # Remove any cached import so the module is re-executed with the mocks active.
    sys.modules.pop("app", None)

    import gradio as gr

    with mock.patch.object(gr.Blocks, "queue", return_value=None), \
         mock.patch.object(gr.Blocks, "launch", return_value=None):
        mod = importlib.import_module("app")

    assert isinstance(mod, types.ModuleType)
    # Key symbols re-exported from wheelpulsepro should be accessible via app
    assert hasattr(mod, "state")
    assert hasattr(mod, "BETTING_MAPPINGS")
    assert hasattr(mod, "update_scores_batch")
    # HF Spaces requires a top-level `demo` (gr.Blocks) object.
    assert hasattr(mod, "demo"), "app.py must expose a top-level 'demo' Blocks object for HF Spaces"
    assert isinstance(mod.demo, gr.Blocks), "'demo' must be a gr.Blocks instance"
