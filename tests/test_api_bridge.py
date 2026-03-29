"""Tests for wheelpulsepro.api_bridge.

Verifies:
  1. The module is importable without Gradio.
  2. export_state_for_aidea returns a dict with all expected top-level keys.
  3. Works with empty state (no spins recorded).
  4. Works with populated state (manually set scores).
  5. All values are JSON-serializable (json.dumps does not raise).
  6. straight_up list is capped at 18 items.
  7. streets capped at 3, corners at 3, splits at 5.
  8. strongest_with_neighbors includes correct left/right neighbor values.
  9. even_money["best"] is None when no even-money scores exist.
  10. timestamp is a valid positive float.
"""

import importlib
import json
import sys
import types

import pytest

from wheelpulsepro.state import RouletteState
from wheelpulsepro.api_bridge import export_state_for_aidea

# Minimal neighbor dict that mirrors NEIGHBORS_EUROPEAN's structure
_NEIGHBORS = {
    0: (26, 32),
    32: (0, 15),
    15: (32, 19),
    19: (15, 4),
    4: (19, 21),
    5: (10, 24),
    7: (29, 28),
    17: (25, 34),
    26: (3, 0),
    36: (13, 11),
}

_EXPECTED_KEYS = {
    "connected",
    "timestamp",
    "total_spins",
    "last_spins",
    "straight_up",
    "even_money",
    "dozens",
    "columns",
    "streets",
    "corners",
    "splits",
    "sides_of_zero",
    "strongest_with_neighbors",
    "strategy",
}


# ---------------------------------------------------------------------------
# 1. Import
# ---------------------------------------------------------------------------

def test_api_bridge_importable():
    mod = importlib.import_module("wheelpulsepro.api_bridge")
    assert isinstance(mod, types.ModuleType)
    assert hasattr(mod, "export_state_for_aidea")


def test_api_bridge_no_gradio_dependency():
    """api_bridge must not import gradio."""
    if "wheelpulsepro.api_bridge" in sys.modules:
        del sys.modules["wheelpulsepro.api_bridge"]
    importlib.import_module("wheelpulsepro.api_bridge")
    bridge_mod = sys.modules["wheelpulsepro.api_bridge"]
    assert "gr" not in vars(bridge_mod), "api_bridge must not import gradio as 'gr'"
    assert "gradio" not in vars(bridge_mod), "api_bridge must not import gradio"


# ---------------------------------------------------------------------------
# 2. All expected keys are present
# ---------------------------------------------------------------------------

def test_returns_all_expected_keys_empty_state():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert _EXPECTED_KEYS.issubset(result.keys()), (
        f"Missing keys: {_EXPECTED_KEYS - result.keys()}"
    )


def test_even_money_has_scores_and_best_keys():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert "scores" in result["even_money"]
    assert "best" in result["even_money"]


def test_dozens_has_scores_and_best_keys():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert "scores" in result["dozens"]
    assert "best" in result["dozens"]


def test_columns_has_scores_and_best_keys():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert "scores" in result["columns"]
    assert "best" in result["columns"]


# ---------------------------------------------------------------------------
# 3. Empty state — sensible defaults
# ---------------------------------------------------------------------------

def test_empty_state_connected_true():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert result["connected"] is True


def test_empty_state_total_spins_zero():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert result["total_spins"] == 0


def test_empty_state_last_spins_empty():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert result["last_spins"] == []


def test_empty_state_straight_up_empty():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert result["straight_up"] == []


def test_empty_state_even_money_best_is_none():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert result["even_money"]["best"] is None


def test_empty_state_dozens_best_is_none():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert result["dozens"]["best"] is None


def test_empty_state_columns_best_is_none():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert result["columns"]["best"] is None


def test_empty_state_streets_empty():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert result["streets"] == []


def test_empty_state_strongest_with_neighbors_empty():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert result["strongest_with_neighbors"] == []


# ---------------------------------------------------------------------------
# 4. Populated state
# ---------------------------------------------------------------------------

def _make_populated_state():
    """Return a RouletteState with some scores set for testing."""
    s = RouletteState()
    # Scores for several numbers
    for num, score in [(0, 5), (7, 10), (17, 8), (32, 3), (19, 7), (4, 6)]:
        s.scores[num] = score
    # Even money
    s.even_money_scores["Red"] = 12
    s.even_money_scores["Black"] = 4
    # Dozens
    s.dozen_scores["1st Dozen"] = 9
    s.dozen_scores["2nd Dozen"] = 2
    # Columns
    s.column_scores["1st Column"] = 7
    # Streets — pick the first key available
    first_street = next(iter(s.street_scores))
    s.street_scores[first_street] = 5
    # Corners
    first_corner = next(iter(s.corner_scores))
    s.corner_scores[first_corner] = 3
    # Splits
    first_split = next(iter(s.split_scores))
    s.split_scores[first_split] = 4
    # Side scores
    s.side_scores["Left Side of Zero"] = 11
    s.side_scores["Right Side of Zero"] = 3
    # Spins
    s.last_spins = [str(n) for n in [7, 17, 19, 4, 32, 0, 7, 17, 19, 4, 32, 7]]
    return s


def test_populated_state_total_spins():
    s = _make_populated_state()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert result["total_spins"] == len(s.last_spins)


def test_populated_state_last_spins_capped_at_10():
    s = _make_populated_state()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert len(result["last_spins"]) <= 10


def test_populated_state_last_spins_are_strings():
    s = _make_populated_state()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert all(isinstance(x, str) for x in result["last_spins"])


def test_populated_state_even_money_best_is_red():
    s = _make_populated_state()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert result["even_money"]["best"]["name"] == "Red"
    assert result["even_money"]["best"]["score"] == 12


def test_populated_state_dozens_best_is_first():
    s = _make_populated_state()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert result["dozens"]["best"]["name"] == "1st Dozen"
    assert result["dozens"]["best"]["score"] == 9


def test_populated_state_sides_of_zero_present():
    s = _make_populated_state()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert "Left Side of Zero" in result["sides_of_zero"]
    assert result["sides_of_zero"]["Left Side of Zero"] == 11


def test_populated_state_straight_up_sorted_descending():
    s = _make_populated_state()
    result = export_state_for_aidea(s, _NEIGHBORS)
    scores = [item["score"] for item in result["straight_up"]]
    assert scores == sorted(scores, reverse=True)


def test_populated_state_strategy_label():
    s = _make_populated_state()
    result = export_state_for_aidea(s, _NEIGHBORS, strategy_name="cold")
    assert result["strategy"] == "cold"


# ---------------------------------------------------------------------------
# 5. JSON-serializable
# ---------------------------------------------------------------------------

def test_empty_state_json_serializable():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    # Must not raise
    json.dumps(result)


def test_populated_state_json_serializable():
    s = _make_populated_state()
    result = export_state_for_aidea(s, _NEIGHBORS)
    json.dumps(result)


# ---------------------------------------------------------------------------
# 6. straight_up capped at 18
# ---------------------------------------------------------------------------

def test_straight_up_capped_at_18():
    s = RouletteState()
    # Give every number a positive score
    for n in range(37):
        s.scores[n] = n + 1
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert len(result["straight_up"]) <= 18


# ---------------------------------------------------------------------------
# 7. streets ≤ 3, corners ≤ 3, splits ≤ 5
# ---------------------------------------------------------------------------

def test_streets_capped_at_3():
    s = RouletteState()
    for i, key in enumerate(list(s.street_scores.keys())[:6]):
        s.street_scores[key] = i + 1
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert len(result["streets"]) <= 3


def test_corners_capped_at_3():
    s = RouletteState()
    for i, key in enumerate(list(s.corner_scores.keys())[:6]):
        s.corner_scores[key] = i + 1
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert len(result["corners"]) <= 3


def test_splits_capped_at_5():
    s = RouletteState()
    for i, key in enumerate(list(s.split_scores.keys())[:10]):
        s.split_scores[key] = i + 1
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert len(result["splits"]) <= 5


# ---------------------------------------------------------------------------
# 8. strongest_with_neighbors — correct left/right lookup
# ---------------------------------------------------------------------------

def test_strongest_with_neighbors_lookup():
    s = RouletteState()
    # Number 32 is in _NEIGHBORS: (0, 15)
    s.scores[32] = 99
    result = export_state_for_aidea(s, _NEIGHBORS)
    entry = next(
        (x for x in result["strongest_with_neighbors"] if x["number"] == 32), None
    )
    assert entry is not None, "Number 32 should appear in strongest_with_neighbors"
    assert entry["left"] == 0
    assert entry["right"] == 15


def test_strongest_with_neighbors_capped_at_5():
    s = RouletteState()
    for n in range(37):
        s.scores[n] = n + 1
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert len(result["strongest_with_neighbors"]) <= 5


def test_strongest_with_neighbors_unknown_number_none():
    """A number absent from the neighbors dict should get None for left/right."""
    s = RouletteState()
    unknown_neighbors: dict = {}  # empty — no entry for any number
    s.scores[5] = 50
    result = export_state_for_aidea(s, unknown_neighbors)
    entry = next(
        (x for x in result["strongest_with_neighbors"] if x["number"] == 5), None
    )
    assert entry is not None
    assert entry["left"] is None
    assert entry["right"] is None


# ---------------------------------------------------------------------------
# 9. timestamp is a valid positive number
# ---------------------------------------------------------------------------

def test_timestamp_is_positive_float():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert isinstance(result["timestamp"], float)
    assert result["timestamp"] > 0


# ---------------------------------------------------------------------------
# 10. connected flag
# ---------------------------------------------------------------------------

def test_connected_flag_always_true():
    s = RouletteState()
    result = export_state_for_aidea(s, _NEIGHBORS)
    assert result["connected"] is True
