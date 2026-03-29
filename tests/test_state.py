"""Tests for wheelpulsepro.state.

Verifies:
  1. The module and RouletteState can be imported without Gradio.
  2. RouletteState() can be constructed with no arguments.
  3. Key default values are set as expected.
  4. gradio is NOT imported as a side-effect of importing the module.
  5. reset() restores every mutable strategy attribute to its __init__ default
     while preserving casino_data and use_casino_winners.
"""

import importlib
import sys
import types

import pytest

from wheelpulsepro.state import RouletteState


# ---------------------------------------------------------------------------
# 1. Import
# ---------------------------------------------------------------------------

def test_state_module_importable():
    mod = importlib.import_module("wheelpulsepro.state")
    assert isinstance(mod, types.ModuleType)
    assert hasattr(mod, "RouletteState")


def test_state_no_gradio_dependency():
    """wheelpulsepro.state must not pull in gradio."""
    # Force a fresh import to confirm no gradio side-effect
    if "wheelpulsepro.state" in sys.modules:
        del sys.modules["wheelpulsepro.state"]
    importlib.import_module("wheelpulsepro.state")
    # gradio may already be present from other tests; the key check is that the
    # state module itself does not contain a reference to the gradio module.
    state_mod = sys.modules["wheelpulsepro.state"]
    assert "gr" not in vars(state_mod), "state.py must not import gradio as 'gr'"
    assert "gradio" not in vars(state_mod), "state.py must not import gradio"


# ---------------------------------------------------------------------------
# 2. Instantiation
# ---------------------------------------------------------------------------

def test_state_instantiates():
    s = RouletteState()
    assert isinstance(s, RouletteState)


# ---------------------------------------------------------------------------
# 3. Default values
# ---------------------------------------------------------------------------

def test_state_default_scores():
    s = RouletteState()
    assert isinstance(s.scores, dict)
    assert len(s.scores) == 37, "scores must contain one entry per number (0-36)"
    assert all(v == 0 for v in s.scores.values()), "all scores start at 0"


def test_state_default_spin_history():
    s = RouletteState()
    assert s.last_spins == []
    assert s.spin_history == []
    assert s.selected_numbers == set()


def test_state_default_bankroll():
    s = RouletteState()
    assert s.bankroll == 1000
    assert s.initial_bankroll == 1000
    assert s.base_unit == 10
    assert s.stop_loss == -500
    assert s.stop_win == 200


def test_state_default_bet_settings():
    s = RouletteState()
    assert s.bet_type == "Even Money"
    assert isinstance(s.progression, str)
    assert s.current_bet == s.base_unit
    assert s.next_bet == s.base_unit
    assert s.is_stopped is False
    assert s.status == "Active"


def test_state_default_side_scores():
    s = RouletteState()
    assert "Left Side of Zero" in s.side_scores
    assert "Right Side of Zero" in s.side_scores
    assert s.side_scores["Left Side of Zero"] == 0
    assert s.side_scores["Right Side of Zero"] == 0


def test_state_default_labouchere():
    s = RouletteState()
    assert s.lab_active is False
    assert s.lab_sequence == []
    assert s.lab_bankroll == 0.0
    assert s.lab_mode == "2 Targets (Dozens/Columns)"
    assert s.lab_split_limit == 0.0


def test_state_default_aidea():
    s = RouletteState()
    assert s.aidea_phases == []
    assert s.aidea_current_id is None
    assert s.aidea_completed_ids == set()


# ---------------------------------------------------------------------------
# 4. Independent instances
# ---------------------------------------------------------------------------

def test_state_instances_are_independent():
    """Two RouletteState instances must not share mutable state."""
    s1 = RouletteState()
    s2 = RouletteState()
    s1.scores[7] = 42
    assert s2.scores[7] == 0, "Mutating s1 must not affect s2"

    s1.last_spins.append("5")
    assert s2.last_spins == [], "last_spins lists must be independent"


# ---------------------------------------------------------------------------
# 5. reset() — comprehensive coverage
# ---------------------------------------------------------------------------

def _dirty_state(s: RouletteState) -> None:
    """Set every strategy-related attribute to a non-default value."""
    # Scores & history
    for k in s.scores:
        s.scores[k] = 99
    for k in s.even_money_scores:
        s.even_money_scores[k] = 5
    for k in s.dozen_scores:
        s.dozen_scores[k] = 5
    for k in s.column_scores:
        s.column_scores[k] = 5
    for k in s.street_scores:
        s.street_scores[k] = 2
    for k in s.corner_scores:
        s.corner_scores[k] = 2
    for k in s.six_line_scores:
        s.six_line_scores[k] = 2
    for k in s.split_scores:
        s.split_scores[k] = 2
    s.side_scores["Left Side of Zero"] = 7
    s.side_scores["Right Side of Zero"] = 7
    s.selected_numbers = {1, 2, 3}
    s.last_spins = ["5", "17", "0"]
    s.spin_history = [{"spin": 5}, {"spin": 17}]

    # Alert tracking
    s.last_dozen_alert_index = 10
    s.alerted_patterns = {"some_pattern"}
    s.last_alerted_spins = ["5"]

    # Dynamic 17 Assault
    s.d17_list = [1, 2, 3]
    s.d17_locked = True

    # Sniper Latch
    s.sniper_locked = True
    s.sniper_locked_misses = 7
    s.sniper_threshold = 30  # config — should NOT be reset

    # Pinned Numbers
    s.pinned_numbers = {14, 22}

    # Top Picks / Stability
    s.current_top_picks = ["Red", "1st Dozen"]
    s.previous_top_picks = ["Black"]
    s.stability_counter = 5

    # Non-Repeater Memory
    s.current_non_repeaters = {1, 2, 3}
    s.previous_non_repeaters = {4, 5}
    s.nr_last_spin_count = 12

    # AIDEA Roadmap
    s.aidea_phases = [{"id": "A"}]
    s.aidea_rules = {"A": {"win": "B"}}
    s.aidea_current_id = "A"
    s.aidea_completed_ids = {"A", "B"}
    s.active_strategy_targets = [1, 2, 3]
    s.aidea_active_targets = [4, 5]
    s.aidea_last_result = "WIN"
    s.aidea_bankroll = 50.0
    s.aidea_phase_repeats = {"A": 3}

    # Trinity Sensor
    s.trinity_dozen = "3rd Dozen"
    s.trinity_ds = "DS 31-36"
    s.trinity_corner_nums = [32, 33, 35, 36]

    # Labouchere Tracker
    s.lab_active = True
    s.lab_sequence = [1, 2, 3]
    s.lab_base = 5.0
    s.lab_target = 100.0
    s.lab_bankroll = 25.0
    s.lab_status = "Running"
    s.lab_mode = "1 Target (Even Money)"
    s.lab_split_limit = 15.0

    # Analysis Cache
    s.analysis_cache = {"key": "value"}

    # Render/Strategy Step Counters
    s.aidea_unit_multiplier = 4
    s.play_specific_numbers_counter = 9
    s.grind_step_index = 3
    s.grind_last_spin_count = 20
    s.ramp_step_index = 2
    s.ramp_last_spin_count = 15

    # Live Brain
    s.live_brain_active = True
    s.live_brain_bankroll = 200.0
    s.live_brain_start_bankroll = 150.0
    s.live_brain_base_unit = 1.0
    s.live_brain_bets = [{"spin_num": 1}]
    s.live_brain_suggestions_followed = 5
    s.live_brain_suggestions_total = 10
    s.live_brain_last_suggestion = "Bet Red"
    s.live_brain_auto_follow = True
    s.live_brain_auto_size = True
    s.live_brain_last_confidence = 80
    s.live_brain_next_bet_amount = 2.50
    s.live_brain_custom_progression_name = "Even Money Drought"
    s.live_brain_custom_progression_step = 3

    # Strategy enabled flags
    s.strategy_sniper_enabled = True
    s.strategy_trinity_enabled = True
    s.strategy_nr_enabled = True
    s.strategy_lab_enabled = True
    s.strategy_ramp_enabled = True
    s.strategy_grind_enabled = True


def test_reset_clears_scores_and_history():
    """Scores and spin history are zeroed after reset()."""
    s = RouletteState()
    _dirty_state(s)
    s.reset()

    assert all(v == 0 for v in s.scores.values()), "scores must be 0 after reset"
    assert all(v == 0 for v in s.even_money_scores.values())
    assert all(v == 0 for v in s.dozen_scores.values())
    assert all(v == 0 for v in s.column_scores.values())
    assert s.side_scores["Left Side of Zero"] == 0
    assert s.side_scores["Right Side of Zero"] == 0
    assert s.selected_numbers == set()
    assert s.last_spins == []
    assert s.spin_history == []


def test_reset_preserves_casino_data_and_flag():
    """casino_data and use_casino_winners must survive reset()."""
    s = RouletteState()
    s.use_casino_winners = True
    s.casino_data["spins_count"] = 500
    s.reset()

    assert s.use_casino_winners is True
    assert s.casino_data["spins_count"] == 500


def test_reset_sniper_latch():
    """Sniper session state is cleared; sniper_threshold (config) is preserved."""
    s = RouletteState()
    s.sniper_locked = True
    s.sniper_locked_misses = 7
    s.sniper_threshold = 30  # custom config — must survive reset
    s.reset()

    assert s.sniper_locked is False
    assert s.sniper_locked_misses == 0
    assert s.sniper_threshold == 30, "sniper_threshold is config — must not be reset"


def test_reset_pinned_numbers():
    s = RouletteState()
    s.pinned_numbers = {14, 22}
    s.reset()
    assert s.pinned_numbers == set()


def test_reset_top_picks_and_stability():
    s = RouletteState()
    s.current_top_picks = ["Red"]
    s.previous_top_picks = ["Black"]
    s.stability_counter = 5
    s.reset()

    assert s.current_top_picks == []
    assert s.previous_top_picks == []
    assert s.stability_counter == 0


def test_reset_non_repeater_memory():
    s = RouletteState()
    s.current_non_repeaters = {1, 2}
    s.previous_non_repeaters = {3, 4}
    s.nr_last_spin_count = 12
    s.reset()

    assert s.current_non_repeaters == set()
    assert s.previous_non_repeaters == set()
    assert s.nr_last_spin_count == 0


def test_reset_aidea_roadmap():
    s = RouletteState()
    s.aidea_phases = [{"id": "A"}]
    s.aidea_rules = {"A": {}}
    s.aidea_current_id = "A"
    s.aidea_completed_ids = {"A"}
    s.active_strategy_targets = [1, 2]
    s.aidea_active_targets = [3]
    s.aidea_last_result = "WIN"
    s.aidea_bankroll = 50.0
    s.aidea_phase_repeats = {"A": 2}
    s.reset()

    assert s.aidea_phases == []
    assert s.aidea_rules == {}
    assert s.aidea_current_id is None
    assert s.aidea_completed_ids == set()
    assert s.active_strategy_targets == []
    assert s.aidea_active_targets == []
    assert s.aidea_last_result is None
    assert s.aidea_bankroll == 0.0
    assert s.aidea_phase_repeats == {}


def test_reset_trinity_sensor():
    s = RouletteState()
    s.trinity_dozen = "3rd Dozen"
    s.trinity_ds = "DS 31-36"
    s.trinity_corner_nums = [32, 33, 35, 36]
    s.reset()

    assert s.trinity_dozen == "1st Dozen"
    assert s.trinity_ds == "DS 1-6"
    assert s.trinity_corner_nums == [1, 2, 4, 5]


def test_reset_labouchere():
    s = RouletteState()
    s.lab_active = True
    s.lab_sequence = [1, 2, 3]
    s.lab_base = 5.0
    s.lab_target = 100.0
    s.lab_bankroll = 25.0
    s.lab_status = "Running"
    s.lab_mode = "1 Target (Even Money)"
    s.lab_split_limit = 10.0
    s.reset()

    assert s.lab_active is False
    assert s.lab_sequence == []
    assert s.lab_base == 1.0
    assert s.lab_target == 10.0
    assert s.lab_bankroll == 0.0
    assert s.lab_status == "Waiting to Start"
    assert s.lab_mode == "2 Targets (Dozens/Columns)"
    assert s.lab_split_limit == 0.0


def test_reset_analysis_cache():
    s = RouletteState()
    s.analysis_cache = {"key": "value"}
    s.reset()
    assert s.analysis_cache == {}


def test_reset_render_strategy_counters():
    s = RouletteState()
    s.aidea_unit_multiplier = 4
    s.play_specific_numbers_counter = 9
    s.grind_step_index = 3
    s.grind_last_spin_count = 20
    s.ramp_step_index = 2
    s.ramp_last_spin_count = 15
    s.reset()

    assert s.aidea_unit_multiplier == 1
    assert s.play_specific_numbers_counter == 0
    assert s.grind_step_index == 0
    assert s.grind_last_spin_count == 0
    assert s.ramp_step_index == 0
    assert s.ramp_last_spin_count == 0


def test_reset_live_brain():
    s = RouletteState()
    s.live_brain_active = True
    s.live_brain_bankroll = 200.0
    s.live_brain_start_bankroll = 150.0
    s.live_brain_base_unit = 1.0
    s.live_brain_bets = [{"spin_num": 1}]
    s.live_brain_suggestions_followed = 5
    s.live_brain_suggestions_total = 10
    s.live_brain_last_suggestion = "Bet Red"
    s.live_brain_auto_follow = True
    s.live_brain_auto_size = True
    s.live_brain_last_confidence = 80
    s.live_brain_next_bet_amount = 2.50
    s.live_brain_custom_progression_name = "Even Money Drought"
    s.live_brain_custom_progression_step = 3
    s.reset()

    assert s.live_brain_active is False
    assert s.live_brain_bankroll == 100.0
    assert s.live_brain_start_bankroll == 100.0
    assert s.live_brain_base_unit == 0.10
    assert s.live_brain_bets == []
    assert s.live_brain_suggestions_followed == 0
    assert s.live_brain_suggestions_total == 0
    assert s.live_brain_last_suggestion == ""
    assert s.live_brain_auto_follow is False
    assert s.live_brain_auto_size is False
    assert s.live_brain_last_confidence == 0
    assert s.live_brain_next_bet_amount == 0.10
    assert s.live_brain_custom_progression_name == ""
    assert s.live_brain_custom_progression_step == 0


def test_reset_strategy_enabled_flags():
    s = RouletteState()
    s.strategy_sniper_enabled = True
    s.strategy_trinity_enabled = True
    s.strategy_nr_enabled = True
    s.strategy_lab_enabled = True
    s.strategy_ramp_enabled = True
    s.strategy_grind_enabled = True
    s.reset()

    assert s.strategy_sniper_enabled is False
    assert s.strategy_trinity_enabled is False
    assert s.strategy_nr_enabled is False
    assert s.strategy_lab_enabled is False
    assert s.strategy_ramp_enabled is False
    assert s.strategy_grind_enabled is False


def test_reset_progression_state():
    """reset() must call reset_progression() so bet state is restored."""
    s = RouletteState()
    s.current_bet = 9999
    s.next_bet = 9999
    s.progression_state = [1, 2, 3]
    s.consecutive_wins = 7
    s.is_stopped = True
    s.reset()

    assert s.current_bet == s.base_unit
    assert s.next_bet == s.base_unit
    assert s.progression_state is None
    assert s.consecutive_wins == 0
    assert s.is_stopped is False


def test_reset_full_dirty_state():
    """End-to-end: dirty every field, reset, verify all strategy fields are default."""
    s = RouletteState()
    _dirty_state(s)
    s.reset()

    # Scores
    assert all(v == 0 for v in s.scores.values())
    assert all(v == 0 for v in s.even_money_scores.values())
    assert all(v == 0 for v in s.dozen_scores.values())
    assert all(v == 0 for v in s.column_scores.values())
    assert s.last_spins == []
    assert s.spin_history == []
    assert s.selected_numbers == set()

    # Sniper (config preserved, session cleared)
    assert s.sniper_locked is False
    assert s.sniper_locked_misses == 0
    assert s.sniper_threshold == 30  # was set to 30 in _dirty_state, must persist

    # Pinned numbers
    assert s.pinned_numbers == set()

    # Top picks / stability
    assert s.current_top_picks == []
    assert s.previous_top_picks == []
    assert s.stability_counter == 0

    # Non-Repeater
    assert s.current_non_repeaters == set()
    assert s.previous_non_repeaters == set()
    assert s.nr_last_spin_count == 0

    # AIDEA
    assert s.aidea_phases == []
    assert s.aidea_rules == {}
    assert s.aidea_current_id is None
    assert s.aidea_completed_ids == set()
    assert s.active_strategy_targets == []
    assert s.aidea_active_targets == []
    assert s.aidea_last_result is None
    assert s.aidea_bankroll == 0.0
    assert s.aidea_phase_repeats == {}

    # Trinity
    assert s.trinity_dozen == "1st Dozen"
    assert s.trinity_ds == "DS 1-6"
    assert s.trinity_corner_nums == [1, 2, 4, 5]

    # Labouchere
    assert s.lab_active is False
    assert s.lab_sequence == []
    assert s.lab_base == 1.0
    assert s.lab_target == 10.0
    assert s.lab_bankroll == 0.0
    assert s.lab_status == "Waiting to Start"
    assert s.lab_mode == "2 Targets (Dozens/Columns)"
    assert s.lab_split_limit == 0.0

    # Analysis cache
    assert s.analysis_cache == {}

    # Step counters
    assert s.aidea_unit_multiplier == 1
    assert s.play_specific_numbers_counter == 0
    assert s.grind_step_index == 0
    assert s.grind_last_spin_count == 0
    assert s.ramp_step_index == 0
    assert s.ramp_last_spin_count == 0

    # Live Brain
    assert s.live_brain_active is False
    assert s.live_brain_bankroll == 100.0
    assert s.live_brain_start_bankroll == 100.0
    assert s.live_brain_base_unit == 0.10
    assert s.live_brain_bets == []
    assert s.live_brain_suggestions_followed == 0
    assert s.live_brain_suggestions_total == 0
    assert s.live_brain_last_suggestion == ""
    assert s.live_brain_auto_follow is False
    assert s.live_brain_auto_size is False
    assert s.live_brain_last_confidence == 0
    assert s.live_brain_next_bet_amount == 0.10
    assert s.live_brain_custom_progression_name == ""
    assert s.live_brain_custom_progression_step == 0

    # Strategy flags
    assert s.strategy_sniper_enabled is False
    assert s.strategy_trinity_enabled is False
    assert s.strategy_nr_enabled is False
    assert s.strategy_lab_enabled is False
    assert s.strategy_ramp_enabled is False
    assert s.strategy_grind_enabled is False
