"""Smoke / import tests for wheelpulsepro.rendering (PR17).

Verifies:
  1. wheelpulsepro.rendering imports successfully (no Gradio required).
  2. All four moved functions exist and are callable.
  3. Each function returns a string (or tuple of strings) when called with
     minimal viable dummy inputs.
"""

import importlib
import types

import pytest

from wheelpulsepro.state import RouletteState


# ---------------------------------------------------------------------------
# Minimal test fixtures / helpers
# ---------------------------------------------------------------------------

def _minimal_colors():
    return {
        "0": "green",
        "1": "red", "2": "black", "3": "red", "4": "black", "5": "red",
        "6": "black", "7": "red", "8": "black", "9": "red", "10": "black",
        "11": "black", "12": "red", "13": "black", "14": "red", "15": "black",
        "16": "red", "17": "black", "18": "red", "19": "red", "20": "black",
        "21": "red", "22": "black", "23": "red", "24": "black", "25": "red",
        "26": "black", "27": "red", "28": "black", "29": "black", "30": "red",
        "31": "black", "32": "red", "33": "black", "34": "red", "35": "black",
        "36": "red",
    }


def _minimal_dozens():
    return {
        "1st Dozen": list(range(1, 13)),
        "2nd Dozen": list(range(13, 25)),
        "3rd Dozen": list(range(25, 37)),
    }


def _minimal_columns():
    return {
        "1st Column": [1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34],
        "2nd Column": [2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35],
        "3rd Column": [3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36],
    }


def _minimal_even_money():
    return {
        "Red": {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36},
        "Black": {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35},
        "Even": {n for n in range(2, 37, 2)},
        "Odd": {n for n in range(1, 37, 2)},
        "Low": set(range(1, 19)),
        "High": set(range(19, 37)),
    }


def _minimal_neighbors():
    # Just a tiny stub – any dict works for the JS embed
    return {str(n): [str((n + 1) % 37), str((n - 1) % 37)] for n in range(37)}


# ---------------------------------------------------------------------------
# 1. Module importable
# ---------------------------------------------------------------------------

def test_rendering_module_importable():
    mod = importlib.import_module("wheelpulsepro.rendering")
    assert isinstance(mod, types.ModuleType)


# ---------------------------------------------------------------------------
# 2. Function presence
# ---------------------------------------------------------------------------

def test_rendering_functions_present():
    from wheelpulsepro import rendering
    assert callable(rendering.format_spins_as_html)
    assert callable(rendering.render_sides_of_zero_display)
    assert callable(rendering.render_aidea_roadmap_html)
    assert callable(rendering.generate_labouchere_html)
    assert callable(rendering.render_strategy_alert_html)


# ---------------------------------------------------------------------------
# 3. format_spins_as_html returns a string
# ---------------------------------------------------------------------------

def test_format_spins_as_html_returns_string():
    from wheelpulsepro.rendering import format_spins_as_html

    result = format_spins_as_html(
        "1, 5, 17",
        num_to_show=10,
        show_trends=True,
        colors=_minimal_colors(),
        DOZENS=_minimal_dozens(),
        COLUMNS=_minimal_columns(),
        EVEN_MONEY=_minimal_even_money(),
    )
    assert isinstance(result, str)
    assert "Last Spins" in result


def test_format_spins_as_html_empty_input():
    from wheelpulsepro.rendering import format_spins_as_html

    result = format_spins_as_html(
        "",
        num_to_show=10,
        show_trends=False,
        colors=_minimal_colors(),
        DOZENS=_minimal_dozens(),
        COLUMNS=_minimal_columns(),
        EVEN_MONEY=_minimal_even_money(),
    )
    assert isinstance(result, str)
    assert "No spins yet" in result


def test_format_spins_as_html_with_zero_no_crash():
    """Spin sequence containing zero must not raise and must return a string."""
    from wheelpulsepro.rendering import format_spins_as_html

    result = format_spins_as_html(
        "0, 1, 2",
        num_to_show=10,
        show_trends=True,
        colors=_minimal_colors(),
        DOZENS=_minimal_dozens(),
        COLUMNS=_minimal_columns(),
        EVEN_MONEY=_minimal_even_money(),
    )
    assert isinstance(result, str)
    assert "Last Spins" in result


def test_format_spins_as_html_zero_only_no_crash():
    """A sequence of only zeros must not crash pattern detection."""
    from wheelpulsepro.rendering import format_spins_as_html

    result = format_spins_as_html(
        "0, 0, 0",
        num_to_show=10,
        show_trends=True,
        colors=_minimal_colors(),
        DOZENS=_minimal_dozens(),
        COLUMNS=_minimal_columns(),
        EVEN_MONEY=_minimal_even_money(),
    )
    assert isinstance(result, str)
    assert "Last Spins" in result


def test_format_spins_as_html_zero_in_middle_no_crash():
    """Zero sandwiched between non-zero spins must not crash pattern detection."""
    from wheelpulsepro.rendering import format_spins_as_html

    result = format_spins_as_html(
        "5, 0, 12, 1, 0, 3",
        num_to_show=10,
        show_trends=True,
        colors=_minimal_colors(),
        DOZENS=_minimal_dozens(),
        COLUMNS=_minimal_columns(),
        EVEN_MONEY=_minimal_even_money(),
    )
    assert isinstance(result, str)
    assert "Last Spins" in result


# ---------------------------------------------------------------------------
# 4. render_sides_of_zero_display returns a string
# ---------------------------------------------------------------------------

def test_render_sides_of_zero_display_returns_string():
    from wheelpulsepro.rendering import render_sides_of_zero_display

    state = RouletteState()
    result = render_sides_of_zero_display(state, _minimal_colors(), _minimal_neighbors())
    assert isinstance(result, str)
    assert len(result) > 0


def test_render_sides_of_zero_display_with_spins():
    from wheelpulsepro.rendering import render_sides_of_zero_display

    state = RouletteState()
    state.last_spins = ["1", "5", "0"]
    state.scores[1] = 1
    state.scores[5] = 1
    state.scores[0] = 1
    state.side_scores["Left Side of Zero"] = 2
    result = render_sides_of_zero_display(state, _minimal_colors(), _minimal_neighbors())
    assert isinstance(result, str)
    assert "Left Side" in result


def test_render_sides_of_zero_display_cluster_detection_no_crash():
    """Cluster detection must not raise even when last_spins contains repeated or zero values."""
    from wheelpulsepro.rendering import render_sides_of_zero_display

    state = RouletteState()
    # Mix of valid numbers and zero; repeated spins to exercise the _checked_nums guard too
    state.last_spins = ["0", "1", "1", "5", "0", "12", "0", "7"]
    for n in [0, 1, 5, 12, 7]:
        state.scores[n] = 1
    result = render_sides_of_zero_display(state, _minimal_colors(), _minimal_neighbors())
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# 5. render_aidea_roadmap_html returns a tuple of two strings
# ---------------------------------------------------------------------------

def test_render_aidea_roadmap_html_no_phases():
    from wheelpulsepro.rendering import render_aidea_roadmap_html

    state = RouletteState()
    roadmap, banner = render_aidea_roadmap_html(state, _minimal_dozens(), multiplier=1)
    assert isinstance(roadmap, str)
    assert isinstance(banner, str)
    assert "Waiting for Strategy" in roadmap or len(roadmap) > 0


def test_render_aidea_roadmap_html_with_phases():
    from wheelpulsepro.rendering import render_aidea_roadmap_html

    state = RouletteState()
    state.aidea_phases = [
        {
            "id": "p1",
            "name": "Phase 1 (SHIELD)",
            "instructions": "WIN: Bet on Red|LOSE: Stay",
            "bets": [{"amount": 1.0}],
        }
    ]
    state.aidea_current_id = "p1"
    roadmap, banner = render_aidea_roadmap_html(state, _minimal_dozens(), multiplier=1)
    assert isinstance(roadmap, str)
    assert isinstance(banner, str)
    assert len(roadmap) > 0
    assert len(banner) > 0


# ---------------------------------------------------------------------------
# 6. generate_labouchere_html returns a string
# ---------------------------------------------------------------------------

def test_generate_labouchere_html_inactive():
    from wheelpulsepro.rendering import generate_labouchere_html

    state = RouletteState()
    result = generate_labouchere_html(state)
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_labouchere_html_active():
    from wheelpulsepro.rendering import generate_labouchere_html

    state = RouletteState()
    state.lab_active = True
    state.lab_sequence = [1.0, 2.0, 1.0]
    state.lab_status = "ACTIVE"
    state.lab_bankroll = 5.0
    state.lab_mode = "2 Targets (Dozens/Columns)"
    result = generate_labouchere_html(state)
    assert isinstance(result, str)
    assert "Labouchere" in result


# ---------------------------------------------------------------------------
# 7. render_strategy_alert_html returns a string
# ---------------------------------------------------------------------------

def test_render_strategy_alert_html_no_trigger():
    from wheelpulsepro.rendering import render_strategy_alert_html

    state = RouletteState()
    result = render_strategy_alert_html(state)
    assert isinstance(result, str)
    # Should return a hidden/empty placeholder when nothing is active
    assert "display:none" in result


def test_render_strategy_alert_html_sniper_active():
    from wheelpulsepro.rendering import render_strategy_alert_html

    state = RouletteState()
    state.sniper_locked = True
    result = render_strategy_alert_html(state)
    assert isinstance(result, str)
    assert "Sniper" in result
    assert "STRATEGY TRIGGERED" in result
    assert "1, 2, 3 Street" in result


def test_render_strategy_alert_html_sniper_high_phase():
    from wheelpulsepro.rendering import render_strategy_alert_html

    state = RouletteState()
    state.sniper_locked = True
    # Set up phases so phase_num > 85
    state.aidea_phases = [{"id": f"p{i}", "name": f"Phase {i} (SHIELD)", "bets": [{"amount": 0.01}]} for i in range(1, 88)]
    state.aidea_current_id = "p86"  # phase 86, > 85
    result = render_strategy_alert_html(state)
    assert isinstance(result, str)
    assert "2, 3, 5, 6 Corner" in result


def test_render_strategy_alert_html_aidea_active():
    from wheelpulsepro.rendering import render_strategy_alert_html

    state = RouletteState()
    state.aidea_phases = [
        {
            "id": "p1",
            "name": "Phase 1 (SHIELD)",
            "instructions": "WIN: Bet on Red|LOSE: Stay",
            "bets": [{"amount": 2.5}],
        }
    ]
    state.aidea_current_id = "p1"
    result = render_strategy_alert_html(state)
    assert isinstance(result, str)
    assert "AIDEA" in result
    assert "STRATEGY TRIGGERED" in result
    assert "SHIELD" in result
    assert "$2.50" in result


def test_render_strategy_alert_html_labouchere_active():
    from wheelpulsepro.rendering import render_strategy_alert_html

    state = RouletteState()
    state.lab_active = True
    state.lab_sequence = [1.0, 2.0, 1.0]
    state.lab_status = "Active"
    state.lab_bankroll = 0.0
    result = render_strategy_alert_html(state)
    assert isinstance(result, str)
    assert "Labouchere" in result
    assert "STRATEGY TRIGGERED" in result
    # next bet = first + last = 1.0 + 1.0 = 2.0
    assert "$2.00" in result


# ---------------------------------------------------------------------------
# Tests for render_strategy_summary_html
# ---------------------------------------------------------------------------

def test_render_strategy_summary_html_empty_state():
    """With a default state (no spins), the summary should always be visible."""
    from wheelpulsepro.rendering import render_strategy_summary_html

    state = RouletteState()
    result = render_strategy_summary_html(state)
    assert isinstance(result, str)
    # Must not use display:none
    assert "display:none" not in result
    # Should always contain the outer flex container
    assert "display:flex" in result


def test_render_strategy_summary_html_sniper_active():
    """When sniper is locked the summary should mention Sniper."""
    from wheelpulsepro.rendering import render_strategy_summary_html

    state = RouletteState()
    state.sniper_locked = True
    result = render_strategy_summary_html(state)
    assert isinstance(result, str)
    assert "Sniper" in result
    assert "display:none" not in result


def test_render_strategy_summary_html_trinity_data():
    """Corner numbers from the trinity sensor should appear in the summary."""
    from wheelpulsepro.rendering import render_strategy_summary_html

    state = RouletteState()
    state.trinity_corner_nums = [25, 26, 28, 29]
    result = render_strategy_summary_html(state)
    assert isinstance(result, str)
    assert "25" in result
    assert "29" in result
    assert "Trinity" in result


def test_render_strategy_summary_html_non_repeaters():
    """Non-repeater count should appear in the summary."""
    from wheelpulsepro.rendering import render_strategy_summary_html

    state = RouletteState()
    state.current_non_repeaters = {1, 5, 9, 12, 17, 22}
    result = render_strategy_summary_html(state)
    assert isinstance(result, str)
    assert "NR" in result
    assert "6" in result  # 6 non-repeaters


def test_render_strategy_summary_html_lab_active():
    """When Labouchere is active the summary should show TR step info."""
    from wheelpulsepro.rendering import render_strategy_summary_html

    state = RouletteState()
    state.lab_active = True
    state.lab_sequence = [1.0, 2.0, 1.0]
    state.lab_status = "Active"
    result = render_strategy_summary_html(state)
    assert isinstance(result, str)
    assert "TR" in result
    assert "display:none" not in result


def test_render_strategy_summary_html_active_uses_red_border():
    """When any alert is active, the summary bar should use the red accent border."""
    from wheelpulsepro.rendering import render_strategy_summary_html

    state = RouletteState()
    state.lab_active = True
    state.lab_sequence = [1.0, 2.0, 1.0]
    result = render_strategy_summary_html(state)
    assert "#ef4444" in result


def test_render_strategy_summary_html_inactive_uses_dark_background():
    """When no alert is active, the summary bar should use the default dark background."""
    from wheelpulsepro.rendering import render_strategy_summary_html

    state = RouletteState()
    result = render_strategy_summary_html(state)
    # Active red border should not be present
    assert "3px solid #ef4444" not in result
    # Default dark background should be present
    assert "#0f172a" in result


def test_render_strategy_alert_html_active_uses_dark_red_background():
    """When a strategy alert is active, the card should use a dark-red gradient background."""
    from wheelpulsepro.rendering import render_strategy_alert_html

    state = RouletteState()
    state.sniper_locked = True
    result = render_strategy_alert_html(state)
    assert "#1a0000" in result
    assert "#ef4444" in result


def test_render_strategy_alert_html_active_has_transition():
    """Active alert card should include a CSS transition for smooth color changes."""
    from wheelpulsepro.rendering import render_strategy_alert_html

    state = RouletteState()
    state.lab_active = True
    state.lab_sequence = [1.0, 2.0, 1.0]
    state.lab_status = "Active"
    result = render_strategy_alert_html(state)
    assert "transition" in result


# ---------------------------------------------------------------------------
# Tests for render_sigma_analysis_html (new Feature 1 + 4)
# ---------------------------------------------------------------------------

def test_render_sigma_analysis_html_no_spins():
    """With no spins the function returns a valid HTML string with a prompt."""
    from wheelpulsepro.rendering import render_sigma_analysis_html

    state = RouletteState()
    result = render_sigma_analysis_html(state)
    assert isinstance(result, str)
    assert len(result) > 0
    assert "Sigma" in result or "sigma" in result


def test_render_sigma_analysis_html_with_spins():
    """With enough spins sigma badges and category names appear in the output."""
    from wheelpulsepro.rendering import render_sigma_analysis_html

    state = RouletteState()
    # Simulate 20 spins covering all categories
    state.last_spins = [str(i % 36 + 1) for i in range(20)]
    state.dozen_scores = {"1st Dozen": 8, "2nd Dozen": 7, "3rd Dozen": 5}
    state.column_scores = {"1st Column": 7, "2nd Column": 7, "3rd Column": 6}
    state.even_money_scores = {"Red": 10, "Black": 10, "Even": 10, "Odd": 10, "Low": 10, "High": 10}
    state.analysis_window = 50
    result = render_sigma_analysis_html(state)
    assert isinstance(result, str)
    assert "1st Dozen" in result
    assert "σ" in result


def test_render_sigma_analysis_html_hot_category():
    """A category with very high hits relative to expected should show hot badge."""
    from wheelpulsepro.rendering import render_sigma_analysis_html

    state = RouletteState()
    # 100 spins; 1st Dozen expected ~32, give it 55 to force hot
    state.last_spins = ["1"] * 100
    state.dozen_scores = {"1st Dozen": 55, "2nd Dozen": 5, "3rd Dozen": 5}
    state.column_scores = {"1st Column": 5, "2nd Column": 5, "3rd Column": 5}
    state.even_money_scores = {"Red": 50, "Black": 50, "Even": 50, "Odd": 50, "Low": 50, "High": 50}
    state.analysis_window = 50
    result = render_sigma_analysis_html(state)
    assert isinstance(result, str)
    # Hot should produce green emoji marker
    assert "🟢" in result


# ---------------------------------------------------------------------------
# Tests for render_drought_table_html (new Feature 2 + 3)
# ---------------------------------------------------------------------------

def test_render_drought_table_html_no_data():
    """With empty drought_counters the function returns a valid placeholder."""
    from wheelpulsepro.rendering import render_drought_table_html

    state = RouletteState()
    state.drought_counters = {}
    result = render_drought_table_html(state)
    assert isinstance(result, str)
    assert len(result) > 0


def test_render_drought_table_html_with_droughts():
    """Drought data appears in the rendered table."""
    from wheelpulsepro.rendering import render_drought_table_html

    state = RouletteState()
    state.drought_counters = {
        "1st Dozen": 15,
        "2nd Dozen": 3,
        "3rd Dozen": 0,
        "1st Column": 8,
        "2nd Column": 2,
        "3rd Column": 1,
        "Red": 5,
        "Black": 0,
        "Even": 4,
        "Odd": 3,
        "Low": 6,
        "High": 2,
    }
    state.last_spins = ["1"] * 30
    result = render_drought_table_html(state)
    assert isinstance(result, str)
    assert "1st Dozen" in result
    assert "15 spins dry" in result
    assert "Sniper" in result  # Sniper explanation note


def test_render_drought_table_html_convergence_probabilities():
    """Convergence probability percentages appear in the rendered output."""
    from wheelpulsepro.rendering import render_drought_table_html

    state = RouletteState()
    state.drought_counters = {"1st Dozen": 10}
    state.last_spins = ["5"] * 20
    result = render_drought_table_html(state)
    assert isinstance(result, str)
    # Should show 'Next 5' and 'Next 10' probability labels
    assert "Next 5" in result
    assert "Next 10" in result


# ---------------------------------------------------------------------------
# Tests for render_smart_decision_summary_html (new Feature 5)
# ---------------------------------------------------------------------------

def test_render_smart_decision_summary_html_no_spins():
    """With no spins the summary asks for more data."""
    from wheelpulsepro.rendering import render_smart_decision_summary_html

    state = RouletteState()
    result = render_smart_decision_summary_html(state)
    assert isinstance(result, str)
    assert "Smart Decision" in result


def test_render_smart_decision_summary_html_all_clear():
    """With normal data and no active strategies the summary says ALL CLEAR."""
    from wheelpulsepro.rendering import render_smart_decision_summary_html

    state = RouletteState()
    # 30 spins, perfectly distributed — no sigma triggers
    state.last_spins = [str((i % 36) + 1) for i in range(30)]
    state.dozen_scores = {"1st Dozen": 10, "2nd Dozen": 10, "3rd Dozen": 10}
    state.column_scores = {"1st Column": 10, "2nd Column": 10, "3rd Column": 10}
    state.even_money_scores = {"Red": 15, "Black": 15, "Even": 15, "Odd": 15, "Low": 15, "High": 15}
    state.drought_counters = {k: 1 for k in state.drought_counters}
    # Clear trinity/NR so they don't generate signals
    state.trinity_dozen = ""
    state.current_non_repeaters = set()
    result = render_smart_decision_summary_html(state)
    assert isinstance(result, str)
    assert "ALL CLEAR" in result


def test_render_smart_decision_summary_html_sniper_active():
    """When sniper is locked the summary highlights it."""
    from wheelpulsepro.rendering import render_smart_decision_summary_html

    state = RouletteState()
    state.sniper_locked = True
    state.sniper_locked_misses = 22
    state.last_spins = ["5"] * 30
    result = render_smart_decision_summary_html(state)
    assert isinstance(result, str)
    assert "SNIPER" in result


def test_render_smart_decision_summary_html_strong_signal():
    """A category that is deeply cold produces a STRONG SIGNAL."""
    from wheelpulsepro.rendering import render_smart_decision_summary_html

    state = RouletteState()
    # 100 spins; 1st Dozen expected ~32, give it only 5 to force cold sigma
    state.last_spins = [str((i % 24) + 13) for i in range(100)]  # All in 2nd+3rd dozen
    state.dozen_scores = {"1st Dozen": 5, "2nd Dozen": 48, "3rd Dozen": 47}
    state.column_scores = {"1st Column": 10, "2nd Column": 10, "3rd Column": 10}
    state.even_money_scores = {"Red": 50, "Black": 50, "Even": 50, "Odd": 50, "Low": 50, "High": 50}
    # Large drought for 1st Dozen too
    state.drought_counters = {"1st Dozen": 20, **{k: 1 for k in state.drought_counters if k != "1st Dozen"}}
    result = render_smart_decision_summary_html(state)
    assert isinstance(result, str)
    assert "STRONG SIGNAL" in result or "Cold" in result or "cold" in result



# ---------------------------------------------------------------------------
# Tests for render_alerts_bar_html (strategy card alerts bar in app.py)
# ---------------------------------------------------------------------------
# app.py imports gradio which is not installed in the test environment, so we
# extract and exec the function from source with a minimal mock namespace.

def _make_render_alerts_bar_fn(mock_cards: dict):
    """Return a callable version of render_alerts_bar_html with mocked globals."""
    import pathlib, ast, types, logging

    src = pathlib.Path("wheelpulsepro/rendering.py").read_text()
    tree = ast.parse(src)

    # Extract the function definition node
    fn_node = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "render_alerts_bar_html"
    )

    # Compile just the function body into a module so exec gives us the fn
    mod = ast.Module(body=[fn_node], type_ignores=[])
    code = compile(mod, "<rendering_extract>", "exec")

    ns: dict = {
        "_prev_active_cards": mock_cards,
        "logger": logging.getLogger("test"),
    }
    exec(code, ns)  # noqa: S102
    return ns["render_alerts_bar_html"]


def test_render_alerts_bar_html_no_active_stays_dark():
    """When no cards are active the bar should stay dark/muted with no red styling."""
    fn = _make_render_alerts_bar_fn({})
    result = fn()
    assert isinstance(result, str)
    assert "wp-alerts-bar" in result
    # No red glow or red border when inactive
    assert "ef4444" not in result
    assert "1a0505" not in result


def test_render_alerts_bar_html_active_uses_dark_red_gradient():
    """When cards are active the bar should use a dark-red gradient background."""
    fn = _make_render_alerts_bar_fn({"5DS STRATEGY ALERT": "5DS STRATEGY ALERT"})
    result = fn()
    assert isinstance(result, str)
    assert "1a0505" in result
    assert "0f172a" in result


def test_render_alerts_bar_html_active_has_red_border():
    """When cards are active the bar should have a red left-border accent."""
    fn = _make_render_alerts_bar_fn({"EVEN MONEY DROUGHT": "EVEN MONEY DROUGHT"})
    result = fn()
    assert "3px solid #ef4444" in result


def test_render_alerts_bar_html_active_has_glow_animation():
    """When cards are active the bar should include the breathing glow animation."""
    fn = _make_render_alerts_bar_fn({"PATTERN MATCH": "PATTERN MATCH"})
    result = fn()
    assert "wpBarGlow" in result


def test_render_alerts_bar_html_active_has_corner_pulses():
    """When cards are active the bar should include pulsing corner elements."""
    fn = _make_render_alerts_bar_fn({"5DS SAFETY MODE": "5DS SAFETY MODE"})
    result = fn()
    assert "wpCornerPulse" in result
    # Four corners — verify there are at least 3 staggered animation-delay entries
    assert result.count("animation-delay") >= 3


def test_render_alerts_bar_html_active_pill_is_red():
    """When cards are active the Active: N pill should have a red background."""
    fn = _make_render_alerts_bar_fn({"STREAK ATTACK": "STREAK ATTACK"})
    result = fn()
    assert "background:#ef4444" in result
    assert "Active: 1" in result


def test_render_alerts_bar_html_always_visible():
    """The bar must always render a visible div regardless of active count."""
    for cards in ({}, {"CARD_A": "CARD_A"}, {"CARD_A": "A", "CARD_B": "B"}):
        fn = _make_render_alerts_bar_fn(cards)
        result = fn()
        assert "wp-alerts-bar" in result
        assert "display:none" not in result
