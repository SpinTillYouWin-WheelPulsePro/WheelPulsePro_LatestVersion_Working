import gradio as gr
import os
import shutil
import math
import pandas as pd
import json
import time
import tempfile
import logging
import re
import base64
from itertools import combinations
from datetime import datetime
import random
import traceback
from roulette_data import (
    EVEN_MONEY, DOZENS, COLUMNS, STREETS, CORNERS, SIX_LINES, SPLITS,
    NEIGHBORS_EUROPEAN, LEFT_OF_ZERO_EUROPEAN, RIGHT_OF_ZERO_EUROPEAN
)
from wheelpulsepro.state import RouletteState
from wheelpulsepro.mappings import (
    BETTING_MAPPINGS,
    initialize_betting_mappings,
    validate_roulette_data,
)
from wheelpulsepro.scoring import update_scores_batch as _core_update_scores_batch
from wheelpulsepro.spins import MAX_SPINS, parse_spins_input, validate_spins
import sys as _sys
import importlib.util as _importlib_util
from wheelpulsepro.persistence import autosave, autorestore

# ✅ Sync Test: GitHub → Hugging Face pipeline verified (2026-03-29)


def _lazy_module(name: str):
    """Return a lazily-loaded module; its body runs only on first attribute access.

    Using importlib.util.LazyLoader defers parsing, compilation, and execution
    of the module until the first attribute is accessed, which keeps app.py
    import time fast on HF Spaces free tier (avoids init-timeout errors).
    """
    if name in _sys.modules:
        return _sys.modules[name]
    spec = _importlib_util.find_spec(name)
    loader = _importlib_util.LazyLoader(spec.loader)
    spec.loader = loader
    module = _importlib_util.module_from_spec(spec)
    _sys.modules[name] = module
    loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Heavy modules — deferred until first user interaction to keep startup fast.
# The actual module bodies (222 KB rendering, 203 KB trackers, 91 KB analysis,
# 81 KB strategies, 36 KB sessions) are only compiled and executed on first
# attribute access, so demo.launch() is reached well within HF Spaces' timeout.
# ---------------------------------------------------------------------------
_rendering = _lazy_module("wheelpulsepro.rendering")
strategies = _lazy_module("wheelpulsepro.strategies")
trackers   = _lazy_module("wheelpulsepro.trackers")
analysis   = _lazy_module("wheelpulsepro.analysis")
sessions   = _lazy_module("wheelpulsepro.sessions")

# Thin wrappers for names previously imported directly from heavy modules.
# Keeping the original names means zero changes to call sites in callbacks.

# -- wheelpulsepro.sessions --
def save_session(*args, **kwargs): return sessions.save_session(*args, **kwargs)
def combine_sessions(*args, **kwargs): return sessions.combine_sessions(*args, **kwargs)
def load_session(*args, **kwargs): return sessions.load_session(*args, **kwargs)
def analyze_spins(*args, **kwargs): return sessions.analyze_spins(*args, **kwargs)
def undo_last_spin(*args, **kwargs): return sessions.undo_last_spin(*args, **kwargs)
def clear_spins(*args, **kwargs): return sessions.clear_spins(*args, **kwargs)
def generate_random_spins(*args, **kwargs): return sessions.generate_random_spins(*args, **kwargs)
def play_specific_numbers(*args, **kwargs): return sessions.play_specific_numbers(*args, **kwargs)

# -- wheelpulsepro.analysis --
def statistical_insights(*args, **kwargs): return analysis.statistical_insights(*args, **kwargs)
def calculate_hit_percentages(*args, **kwargs): return analysis.calculate_hit_percentages(*args, **kwargs)
def summarize_spin_traits(*args, **kwargs): return analysis.summarize_spin_traits(*args, **kwargs)
def cache_analysis(*args, **kwargs): return analysis.cache_analysis(*args, **kwargs)
def select_next_spin_top_pick(*args, **kwargs): return analysis.select_next_spin_top_pick(*args, **kwargs)
def create_html_table(*args, **kwargs): return analysis.create_html_table(*args, **kwargs)
def render_rank_table(*args, **kwargs): return analysis.render_rank_table(*args, **kwargs)
def create_strongest_numbers_with_neighbours_table(*args, **kwargs): return analysis.create_strongest_numbers_with_neighbours_table(*args, **kwargs)

# -- wheelpulsepro.trackers (callables) --
def de2d_tracker_logic(*args, **kwargs): return trackers.de2d_tracker_logic(*args, **kwargs)
def dozen_tracker(*args, **kwargs): return trackers.dozen_tracker(*args, **kwargs)
def _dozen_tracker_inner(*args, **kwargs): return trackers._dozen_tracker_inner(*args, **kwargs)
def even_money_tracker(*args, **kwargs): return trackers.even_money_tracker(*args, **kwargs)
def _even_money_tracker_inner(*args, **kwargs): return trackers._even_money_tracker_inner(*args, **kwargs)
def _coerce_int(*args, **kwargs): return trackers._coerce_int(*args, **kwargs)
def _clamp(*args, **kwargs): return trackers._clamp(*args, **kwargs)
def _safe_slider_val(*args, **kwargs): return trackers._safe_slider_val(*args, **kwargs)

# -- wheelpulsepro.trackers (shared data objects) --
# _DE2D_SLIDER_CFG and _nudge_state are mutable dicts/lists shared between
# app.py callbacks and trackers.py internals.  They cannot be safely imported
# at module load time because trackers.py is lazy.  Instead they are bound to
# the actual objects inside _on_page_load() (the demo.load handler), which
# runs before any user interaction is possible.
_DE2D_SLIDER_CFG = None  # bound to trackers._DE2D_SLIDER_CFG in _on_page_load
_nudge_state = None      # bound to trackers._nudge_state in _on_page_load

# -- wheelpulsepro.strategies --
def calculate_top_pick_movement(*args, **kwargs): return strategies.calculate_top_pick_movement(*args, **kwargs)
def calculate_trending_sections(*args, **kwargs): return strategies.calculate_trending_sections(*args, **kwargs)
def get_strongest_numbers_with_neighbors(*args, **kwargs): return strategies.get_strongest_numbers_with_neighbors(*args, **kwargs)
def best_even_money_bets(*args, **kwargs): return strategies.best_even_money_bets(*args, **kwargs)
def hot_bet_strategy(*args, **kwargs): return strategies.hot_bet_strategy(*args, **kwargs)
def cold_bet_strategy(*args, **kwargs): return strategies.cold_bet_strategy(*args, **kwargs)
def best_dozens(*args, **kwargs): return strategies.best_dozens(*args, **kwargs)
def best_columns(*args, **kwargs): return strategies.best_columns(*args, **kwargs)
def fibonacci_strategy(*args, **kwargs): return strategies.fibonacci_strategy(*args, **kwargs)
def best_streets(*args, **kwargs): return strategies.best_streets(*args, **kwargs)
def sniper_best_street_corner(*args, **kwargs): return strategies.sniper_best_street_corner(*args, **kwargs)
def best_double_streets(*args, **kwargs): return strategies.best_double_streets(*args, **kwargs)
def best_corners(*args, **kwargs): return strategies.best_corners(*args, **kwargs)
def best_splits(*args, **kwargs): return strategies.best_splits(*args, **kwargs)
def best_dozens_and_streets(*args, **kwargs): return strategies.best_dozens_and_streets(*args, **kwargs)
def best_columns_and_streets(*args, **kwargs): return strategies.best_columns_and_streets(*args, **kwargs)
def non_overlapping_double_street_strategy(*args, **kwargs): return strategies.non_overlapping_double_street_strategy(*args, **kwargs)
def non_overlapping_corner_strategy(*args, **kwargs): return strategies.non_overlapping_corner_strategy(*args, **kwargs)
def romanowksy_missing_dozen_strategy(*args, **kwargs): return strategies.romanowksy_missing_dozen_strategy(*args, **kwargs)
def fibonacci_to_fortune_strategy(*args, **kwargs): return strategies.fibonacci_to_fortune_strategy(*args, **kwargs)
def three_eight_six_rising_martingale(*args, **kwargs): return strategies.three_eight_six_rising_martingale(*args, **kwargs)
def one_dozen_one_column_strategy(*args, **kwargs): return strategies.one_dozen_one_column_strategy(*args, **kwargs)
def top_pick_18_numbers_without_neighbours(*args, **kwargs): return strategies.top_pick_18_numbers_without_neighbours(*args, **kwargs)
def best_column_till_tie_break(*args, **kwargs): return strategies.best_column_till_tie_break(*args, **kwargs)
def best_dozen_till_tie_break(*args, **kwargs): return strategies.best_dozen_till_tie_break(*args, **kwargs)
def best_even_money_bet_till_tie_break(*args, **kwargs): return strategies.best_even_money_bet_till_tie_break(*args, **kwargs)
def best_even_money_and_top_18(*args, **kwargs): return strategies.best_even_money_and_top_18(*args, **kwargs)
def best_dozens_and_top_18(*args, **kwargs): return strategies.best_dozens_and_top_18(*args, **kwargs)
def best_columns_and_top_18(*args, **kwargs): return strategies.best_columns_and_top_18(*args, **kwargs)
def best_dozens_even_money_and_top_18(*args, **kwargs): return strategies.best_dozens_even_money_and_top_18(*args, **kwargs)
def best_columns_even_money_and_top_18(*args, **kwargs): return strategies.best_columns_even_money_and_top_18(*args, **kwargs)
def top_numbers_with_neighbours_tiered(*args, **kwargs): return strategies.top_numbers_with_neighbours_tiered(*args, **kwargs)
def neighbours_of_strong_number(*args, **kwargs): return strategies.neighbours_of_strong_number(*args, **kwargs)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("wheelPulsePro")

# ---------------------------------------------------------------------------
# DE2D Slider centralised configuration
# ---------------------------------------------------------------------------
# Each entry is (default, minimum, maximum) for one slider, in the exact
# order that de2d_sliders / preset functions use:
#   miss, even, streak, pattern, voisins, tiers, left, right,
#   ds, d17, corner, x19_start, sniper, nr_spins, nr_target
#

# HUD visibility constants — single source of truth for checkbox defaults.
# _HUD_DEFAULT_VISIBLE: cards shown on fresh load (Sniper Strike, Cold Trinity,
#   Ramp/Grind/X-19 and Non-Repeaters are hidden by default so users must
#   explicitly opt-in to those noisy/advanced cards).
_HUD_DEFAULT_VISIBLE = [
    "Missing Dozen/Col",
    "Even Money Drought", "Trend Reversal", "Streak Attack", "Pattern Match",
    "Voisins/Tiers", "Left/Right Sides", "5DS/Corners/D17", "Zero Guard",
]

# _HUD_ALL_CHOICES: every available card (used by "Check All" button).
_HUD_ALL_CHOICES = [
    "Sniper Strike", "Ramp/Grind/X-19", "Cold Trinity", "Missing Dozen/Col",
    "Even Money Drought", "Trend Reversal", "Streak Attack", "Pattern Match",
    "Voisins/Tiers", "Left/Right Sides", "5DS/Corners/D17", "Zero Guard", "Non-Repeaters",
]


def _get_file_path(file):
    """Return the filesystem path for a Gradio file object or plain string.

    Gradio file objects expose a ``.name`` attribute containing the path to
    the temporary file on disk.  Plain strings are accepted as-is so that
    callers can also pass a path directly.  Returns ``None`` when *file* does
    not expose a usable path.
    """
    return getattr(file, "name", None) or (file if isinstance(file, str) else None)


def update_scores_batch(spins):
    """Thin wrapper around wheelpulsepro.scoring.update_scores_batch.

    Passes the application-level globals (state, current_left_of_zero,
    current_right_of_zero, BETTING_MAPPINGS) so that all existing call sites
    inside app.py remain unchanged.
    """
    return _core_update_scores_batch(
        spins, state, current_left_of_zero, current_right_of_zero, BETTING_MAPPINGS
    )


def _update_drought_counters():
    """Recompute state.drought_counters from state.last_spins.

    Scans spins in reverse order to find how many spins have elapsed since
    each tracked category (dozens, columns, even-money) last hit.  O(N) where
    N = len(state.last_spins).
    """
    try:
        _update_drought_counters_inner()
    except Exception as e:
        logger.exception("Failed to update drought counters")


def _update_drought_counters_inner():
    if not hasattr(state, 'drought_counters'):
        return
    if not hasattr(state, 'last_spins'):
        return

    _DOZEN_RANGES = {
        "1st Dozen": range(1, 13),
        "2nd Dozen": range(13, 25),
        "3rd Dozen": range(25, 37),
    }
    _COL_NUMS = {
        "1st Column": {1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34},
        "2nd Column": {2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35},
        "3rd Column": {3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36},
    }
    _RED = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
    _BLACK = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}

    # For each category, drought = number of spins from the end until (not including) last hit
    _all_categories = (
        list(_DOZEN_RANGES.keys())
        + list(_COL_NUMS.keys())
        + ["Red", "Black", "Even", "Odd", "Low", "High"]
    )

    def _hits(n, cat):
        if cat in _DOZEN_RANGES:
            return n in _DOZEN_RANGES[cat]
        if cat in _COL_NUMS:
            return n in _COL_NUMS[cat]
        if cat == "Red":
            return n in _RED
        if cat == "Black":
            return n in _BLACK
        if cat == "Even":
            return n != 0 and n % 2 == 0
        if cat == "Odd":
            return n != 0 and n % 2 == 1
        if cat == "Low":
            return 1 <= n <= 18
        if cat == "High":
            return 19 <= n <= 36
        return False

    for cat in _all_categories:
        d = 0
        for spin_str in reversed(state.last_spins):
            try:
                num = int(spin_str)
            except (ValueError, TypeError):
                d += 1
                continue
            if not (0 <= num <= 36):
                d += 1
                continue
            if _hits(num, cat):
                break
            d += 1
        state.drought_counters[cat] = d

state = RouletteState()
# Attempt to restore the last auto-saved state (survives restarts/redeploys).
# Falls back to a clean default state silently when no save file exists.
autorestore(state)

# Validate roulette data at startup
data_errors = validate_roulette_data()
if data_errors:
    raise RuntimeError("Roulette data validation failed:\n" + "\n".join(data_errors))

initialize_betting_mappings()

current_table_type = "European"
current_neighbors = NEIGHBORS_EUROPEAN
current_left_of_zero = set(LEFT_OF_ZERO_EUROPEAN)
current_right_of_zero = set(RIGHT_OF_ZERO_EUROPEAN)

# Inject state and neighbor lookup into the strategies module.
# Calling init() here triggers the lazy loads so modules are ready before
# demo.launch() is called.  This keeps the Gradio startup events lightweight.
strategies.init(state, current_neighbors)

scores = {n: 0 for n in range(37)}
even_money_scores = {name: 0 for name in EVEN_MONEY.keys()}
dozen_scores = {name: 0 for name in DOZENS.keys()}
column_scores = {name: 0 for name in COLUMNS.keys()}
street_scores = {name: 0 for name in STREETS.keys()}
corner_scores = {name: 0 for name in CORNERS.keys()}
six_line_scores = {name: 0 for name in SIX_LINES.keys()}
split_scores = {name: 0 for name in SPLITS.keys()}
side_scores = {"Left Side of Zero": 0, "Right Side of Zero": 0}
selected_numbers = set()

last_spins = []

colors = {
    "0": "green",
    "1": "red", "3": "red", "5": "red", "7": "red", "9": "red", "12": "red",
    "14": "red", "16": "red", "18": "red", "19": "red", "21": "red", "23": "red",
    "25": "red", "27": "red", "30": "red", "32": "red", "34": "red", "36": "red",
    "2": "black", "4": "black", "6": "black", "8": "black", "10": "black", "11": "black",
    "13": "black", "15": "black", "17": "black", "20": "black", "22": "black", "24": "black",
    "26": "black", "28": "black", "29": "black", "31": "black", "33": "black", "35": "black"
}

trackers.init(state, colors, _HUD_DEFAULT_VISIBLE)
analysis.init(state, colors, current_neighbors)
# Bind the shared data objects after trackers has been loaded by init()
_DE2D_SLIDER_CFG = trackers._DE2D_SLIDER_CFG
_nudge_state = trackers._nudge_state

# Lines before (context)
def format_spins_as_html(spins, num_to_show, show_trends=True):
    """Thin wrapper – delegates to wheelpulsepro.rendering."""
    try:
        return _rendering.format_spins_as_html(
            spins, num_to_show, show_trends, colors, DOZENS, COLUMNS, EVEN_MONEY
        )
    except Exception as e:
        logger.error(f"format_spins_as_html error: {e}")
        return "<h4>Last Spins</h4><p>⚠️ Error rendering spins.</p>"


def render_sides_of_zero_display():
    """Thin wrapper – delegates to wheelpulsepro.rendering."""
    try:
        return _rendering.render_sides_of_zero_display(state, colors, current_neighbors)
    except Exception as e:
        logger.error(f"render_sides_of_zero_display error: {e}")
        return ""


def render_sigma_analysis_html():
    """Thin wrapper – delegates to wheelpulsepro.rendering."""
    try:
        return _rendering.render_sigma_analysis_html(state)
    except Exception:
        return _rendering._FALLBACK_SIGMA_HTML


def render_drought_table_html():
    """Thin wrapper – delegates to wheelpulsepro.rendering."""
    try:
        return _rendering.render_drought_table_html(state)
    except Exception:
        return _rendering._FALLBACK_DROUGHT_HTML


def render_smart_decision_summary_html():
    """Thin wrapper – delegates to wheelpulsepro.rendering."""
    try:
        return _rendering.render_smart_decision_summary_html(state)
    except Exception:
        return _rendering._FALLBACK_SUMMARY_HTML


def render_final_brain_html():
    """Thin wrapper – delegates to wheelpulsepro.rendering."""
    try:
        return _rendering.render_final_brain_html(state)
    except Exception:
        return _rendering._FALLBACK_FINAL_BRAIN_HTML


def render_master_information_html(precomputed_recommendation=None):
    """Thin wrapper – delegates to wheelpulsepro.rendering."""
    try:
        return _rendering.render_master_information_html(state, precomputed_recommendation=precomputed_recommendation)
    except Exception:
        return _rendering._FALLBACK_MASTER_INFO_HTML


def render_master_information_summary_html(precomputed_recommendation=None):
    """Render a compact one-liner summary for the Master Information section.

    Always visible above the collapsed accordion, showing the current best
    bet label, master score, and analysis window so the user can glance at
    the recommendation without expanding the section.
    """
    try:
        ranked = (
            precomputed_recommendation
            if precomputed_recommendation is not None
            else _rendering.compute_last_money_recommendation(state)
        )
        if not ranked:
            return ""
        best = ranked[0]
        last_spins = getattr(state, 'last_spins', [])
        n = len(last_spins)
        if n < 3:
            return ""
        W = min(getattr(_rendering, '_MI_WINDOW', 36), n)
        score_pct = int(best['score'] * 100)
        return (
            f'<div style="background:linear-gradient(90deg,#1e1b4b,#0f172a);'
            f'border:1px solid #7c3aed;border-radius:8px;padding:8px 14px;'
            f'margin-bottom:6px;display:flex;align-items:center;gap:12px;'
            f'font-family:\'Segoe UI\',system-ui,sans-serif;flex-wrap:wrap;">'
            f'<span style="color:#a78bfa;font-size:11px;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:1px;white-space:nowrap;">🎯 Last Bet:</span>'
            f'<span style="color:#fff;font-size:14px;font-weight:900;white-space:nowrap;">'
            f'{best["label"]}</span>'
            f'<span style="color:#94a3b8;font-size:11px;white-space:nowrap;">'
            f'Score&nbsp;<b style="color:#c4b5fd;">{score_pct}</b>&nbsp;·&nbsp;'
            f'W=<b style="color:#c4b5fd;">{W}</b></span>'
            f'</div>'
        )
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# In-app Alerts system (server-side; no JS popups — avoids connection errors)
# ---------------------------------------------------------------------------

# Module-level state: tracks the currently-active cards from the latest render.
_prev_active_cards: dict = {}   # {card_key: headline_str} from latest render




def _extract_cards_fingerprint(html: str) -> dict:
    """Extract a ``{card_key: headline_str}`` dict from strategy-cards HTML.

    The card_key is the hud-title text (stable card ID).  The headline_str
    equals the card title for regular strategy cards and the brain
    recommendation target for the ``__brain__`` entry.

    Fails gracefully — never raises an exception.
    """
    result: dict = {}
    try:
        for title in re.findall(r'class="hud-title"[^>]*>\s*([^<]+?)\s*<', html):
            title = title.strip()
            if title and 'SCANNING' not in title.upper():
                # Value equals key: for strategy cards the title is both the
                # stable ID and the headline (the card's content doesn't change
                # headline independently the way the brain recommendation does).
                result[title] = title
        brain = re.search(r'I would target\s*<b[^>]*>\s*([^<]+?)\s*<', html)
        if brain:
            result['__brain__'] = brain.group(1).strip()
    except Exception:
        pass
    return result


def render_alerts_bar_html() -> str:
    """Render the sticky Alerts Bar showing currently-active strategy cards only.

    Reflects the *current* set of visible/active strategy cards. When a card
    disappears it is automatically removed from the bar on the next render —
    no manual clearing required.

    The sticky positioning is handled by the ``_EXTRA_CSS`` passed to
    ``gr.Blocks``; this function returns only the bar's inner HTML content.
    Returns a safe HTML string; never raises an exception.
    """
    try:
        card_names = [k for k in _prev_active_cards if k != '__brain__']

        if not card_names:
            return (
                "<div id='wp-alerts-bar' style='"
                "background:rgba(15,23,42,0.85);padding:7px 16px;"
                "display:flex;align-items:center;gap:12px;"
                "font-family:system-ui,sans-serif;font-size:13px;"
                "color:rgba(255,255,255,0.4);'>"
                "🔔 No active strategy alerts"
                "</div>"
            )

        parts = []
        for name in card_names:
            parts.append(
                f"<span style='display:inline-flex;align-items:center;gap:5px;"
                f"background:rgba(239,68,68,0.18);border:1px solid rgba(239,68,68,0.5);"
                f"border-radius:6px;padding:3px 10px;font-size:12px;color:#fca5a5;"
                f"white-space:nowrap;'>"
                f"🚨&nbsp;<b style='color:#fca5a5;'>{name}</b>"
                f"</span>"
            )

        count_badge = (
            f"<span style='background:#ef4444;color:#fff;border-radius:12px;"
            f"padding:2px 9px;font-size:11px;font-weight:700;white-space:nowrap;"
            f"flex-shrink:0;'>"
            f"Active: {len(card_names)}"
            f"</span>"
        )

        _corner_style = (
            "position:absolute;width:7px;height:7px;"
            "border-radius:1px;background:#ef4444;"
            "animation:wpCornerPulse 1.4s ease-in-out infinite;"
        )
        corners = (
            f"<span style='{_corner_style}top:3px;left:3px;'></span>"
            f"<span style='{_corner_style}top:3px;right:3px;animation-delay:0.35s;'></span>"
            f"<span style='{_corner_style}bottom:3px;left:3px;animation-delay:0.7s;'></span>"
            f"<span style='{_corner_style}bottom:3px;right:3px;animation-delay:1.05s;'></span>"
        )

        return (
            "<style>"
            "@keyframes wpBarGlow{"
            "0%,100%{box-shadow:0 0 12px rgba(239,68,68,0.15),0 2px 12px rgba(239,68,68,0.1);}"
            "50%{box-shadow:0 0 24px rgba(239,68,68,0.4),0 2px 20px rgba(239,68,68,0.25);}}"
            "@keyframes wpCornerPulse{"
            "0%,100%{opacity:1;transform:scale(1);}"
            "50%{opacity:0.35;transform:scale(1.6);}}"
            "</style>"
            f"<div id='wp-alerts-bar' style='"
            f"position:relative;"
            f"background:linear-gradient(90deg,#1a0505,#0f172a);"
            f"border-left:3px solid #ef4444;"
            f"padding:7px 16px;"
            f"display:flex;align-items:center;gap:10px;flex-wrap:wrap;"
            f"font-family:system-ui,sans-serif;"
            f"animation:wpBarGlow 2.5s ease-in-out infinite;"
            f"transition:background 0.5s ease,border-color 0.5s ease,box-shadow 0.5s ease;'>"
            f"{corners}"
            f"<span style='font-size:15px;flex-shrink:0;'>🔔</span>"
            f"{''.join(parts)}"
            f"{count_badge}"
            f"</div>"
        )
    except Exception as e:
        logger.error(f"render_alerts_bar_html error: {e}")
        return ""


def render_cards_and_alerts(*args):
    """Render strategy cards and update the Alerts Bar.

    Returns ``(cards_html, alerts_bar_html)`` for use as outputs of Gradio
    callbacks that update ``strategy_cards_area`` and ``alerts_bar_output``.

    The Alerts Bar reflects the *current* set of visible/active cards; cards
    that disappear are automatically removed on the next render — no history
    or manual clearing is needed.

    All steps are wrapped in try/except so alert failures can never crash the
    core card-rendering logic.
    """
    global _prev_active_cards
    try:
        cards_html = render_strategy_cards_area_html(*args)
    except Exception as e:
        logger.error(f"render_cards_and_alerts: render error: {e}")
        cards_html = ""

    try:
        _prev_active_cards = _extract_cards_fingerprint(cards_html)
    except Exception as e:
        logger.error(f"render_cards_and_alerts: fingerprint error: {e}")

    try:
        alerts_bar = render_alerts_bar_html()
    except Exception as e:
        logger.error(f"render_cards_and_alerts: alert render error: {e}")
        alerts_bar = ""

    return cards_html, alerts_bar


def render_ai_coach_html(precomputed_recommendation=None, pinned_numbers_raw=None):
    """Return the live Pulse AI Coach HTML, reading from module-level state."""
    try:
        return _rendering.render_ai_coach_prompt_html(
            state,
            precomputed_recommendation=precomputed_recommendation,
            pinned_numbers_raw=pinned_numbers_raw,
        )
    except Exception as e:
        logger.error(f"render_ai_coach_html error: {e}")
        return ""


def render_master_info_both(pinned_numbers_raw=None):
    """Return ``(summary_html, detail_html, ai_coach_html)`` for all three components.

    Used in callbacks so a single ``.then()`` step updates the compact summary
    strip, the full detail panel, and the Pulse AI Coach together.

    ``compute_last_money_recommendation`` is called **once** here and the result
    is forwarded to all three renderers to avoid redundant expensive computation.
    """
    try:
        ranked = _rendering.compute_last_money_recommendation(state)
        return (
            render_master_information_summary_html(ranked),
            render_master_information_html(ranked),
            render_ai_coach_html(ranked, pinned_numbers_raw=pinned_numbers_raw),
        )
    except Exception as e:
        logger.error(f"render_master_info_both error: {e}")
        return "", "", ""


def _sync_strategy_flags_from_hud_filters(hud_filters):
    """Sync strategy_enabled state flags from HUD visibility filter selections.

    Called whenever the hud_visibility_filters CheckboxGroup changes so that
    _render_final_brain_html_inner can gate Active Strategy Cards correctly.
    """
    try:
        filters = hud_filters or []
        state.strategy_sniper_enabled = "Sniper Strike" in filters
        state.strategy_trinity_enabled = "Cold Trinity" in filters
        state.strategy_nr_enabled = "Non-Repeaters" in filters
        state.strategy_ramp_enabled = "Ramp/Grind/X-19" in filters
        state.strategy_grind_enabled = "Ramp/Grind/X-19" in filters
        # Labouchere is controlled by starting a Lab session, not the HUD filter
    except Exception as e:
        logger.error(f"_sync_strategy_flags_from_hud_filters error: {e}")


def validate_spins_input(spins_input):
    """Validate manually entered spins and update state."""
    start_time = time.time()

    logger.debug(f"validate_spins_input: Processing spins_input='{spins_input}'")
    try:
        if not spins_input or not spins_input.strip():
            logger.debug("validate_spins_input: No spins input provided.")
            return "", "<h4>Last Spins</h4><p>No spins entered.</p>"

        # Delegate parsing and validation to wheelpulsepro.spins (no Gradio inside)
        raw_spins = parse_spins_input(spins_input)
        if len(raw_spins) > MAX_SPINS:
            error_msg = f"Too many spins ({len(raw_spins)}). Maximum allowed is {MAX_SPINS}."
            gr.Warning(error_msg)
            logger.debug(f"validate_spins_input: Error - {error_msg}")
            return "", f"<h4>Last Spins</h4><p>{error_msg}</p>"

        valid_spins, errors = validate_spins(raw_spins)

        if not valid_spins:
            error_msg = "No valid spins found:\n- " + "\n- ".join(errors) + "\nUse comma-separated integers between 0 and 36 (e.g., 5, 12, 0)."
            gr.Warning(error_msg)
            logger.debug(f"validate_spins_input: Errors - {error_msg}")
            return "", f"<h4>Last Spins</h4><p>{error_msg}</p>"

        # Update state and scores
        state.last_spins = valid_spins
        state.selected_numbers = set(int(s) for s in valid_spins)
        action_log = update_scores_batch(valid_spins)
        for i, spin in enumerate(valid_spins):
            state.spin_history.append(action_log[i])
            if len(state.spin_history) > 100:
                state.spin_history.pop(0)
        _update_drought_counters()

        spins_display_value = ", ".join(valid_spins)
        formatted_html = format_spins_as_html(spins_display_value, 36)

        logger.debug(f"validate_spins_input: Processed {len(valid_spins)} valid spins, spins_display_value='{spins_display_value}', time={time.time() - start_time:.3f}s")
        if errors:
            logger.debug(f"validate_spins_input: Ignored invalid inputs (errors): {errors}")

        if errors:
            warning_msg = f"Processed {len(valid_spins)} valid spins. Invalid inputs ignored:\n- " + "\n- ".join(errors) + "\nUse integers 0-36."
            gr.Warning(warning_msg)
            logger.debug(f"validate_spins_input: Warning - {warning_msg}")

        return spins_display_value, formatted_html

    except Exception as e:
        logger.error(
            f"validate_spins_input: Unexpected error: {str(e)}\n{traceback.format_exc()}"
        )
        gr.Warning(
            f"⚠️ Input validation error (spins preserved): "
            f"{type(e).__name__}: {str(e)}"
        )
        safe_spins = ", ".join(str(s) for s in state.last_spins) if state.last_spins else (spins_input or "")
        return safe_spins, f"<h4>Last Spins</h4><p>⚠️ Error processing input — please try again.</p>"

# Line 1: Start of updated add_spin function
def add_spin(number, current_spins, num_to_show):
    start_time = time.time()

    logger.debug(f"add_spin: Processing number='{number}', current_spins='{current_spins}', num_to_show={num_to_show}")
    try:
        numbers = [n.strip() for n in number.split(",") if n.strip()]
        unique_numbers = list(dict.fromkeys(numbers))
        
        if not unique_numbers:
            gr.Warning("No valid input provided. Please enter numbers between 0 and 36.")
            logger.debug("add_spin: No valid numbers provided.")
            return current_spins, current_spins, "<h4>Last Spins</h4><p>Error: No valid numbers provided.</p>", update_spin_counter(), render_sides_of_zero_display()
        
        current_spins_list = current_spins.split(", ") if current_spins and current_spins.strip() else []
        if current_spins_list == [""]:
            current_spins_list = []
        
        new_spins = current_spins_list + unique_numbers
        new_spins_str = ", ".join(new_spins)

        # CHANGED: Directly update the state history here so the counter reads the exact total before the UI updates.
        # Removed the destructive validate_spins_input call that was wiping out the history array.
        state.last_spins = new_spins

        # --- NEW: Auto-Pilot Logic (The "Brain") ---
        # Prioritize AIDEA JSON targets if a sequence is loaded
        if state.aidea_phases and state.aidea_active_targets:
            eval_targets = state.aidea_active_targets
        else:
            eval_targets = state.active_strategy_targets

        # --- SNIPER HARDCODE OVERRIDE (Hottest Street/Corner) ---
        if getattr(state, 'sniper_locked', False):
            current_idx = next((i for i, p in enumerate(getattr(state, 'aidea_phases', [])) if p['id'] == getattr(state, 'aidea_current_id', None)), 0)
            phase_num = current_idx + 1
            # Use hottest street/corner from current scores
            street_active = {k: v for k, v in state.street_scores.items() if v > 0}
            corner_active = {k: v for k, v in state.corner_scores.items() if v > 0}
            if phase_num <= 65:
                if street_active:
                    best_street = max(street_active, key=street_active.get)
                    eval_targets = list(STREETS[best_street])
                else:
                    eval_targets = [1, 2, 3]
            else:
                if corner_active:
                    best_corner = max(corner_active, key=corner_active.get)
                    eval_targets = list(CORNERS[best_corner])
                else:
                    eval_targets = [1, 2, 4, 5]

        if eval_targets and unique_numbers:
            try:
                latest_spin_int = int(unique_numbers[-1])
            except (ValueError, TypeError):
                logger.warning(f"add_spin: Cannot convert '{unique_numbers[-1]}' to int; skipping auto-pilot evaluation.")
                latest_spin_int = None

            if latest_spin_int is not None:
                if latest_spin_int in eval_targets:
                    state.aidea_last_result = "WIN"
                    coverage = len(eval_targets)
                    multiplier = (36 / coverage) - 1 if coverage > 0 else 0
                    state.aidea_bankroll += multiplier 
                else:
                    state.aidea_last_result = "LOSS"
                    state.aidea_bankroll -= 1 
                    
                logger.debug(f"AUTO-PILOT: Spin {latest_spin_int} vs Targets {eval_targets} -> {state.aidea_last_result}")

        # --- LABOUCHERE SEQUENCE TRACKER INTEGRATION ---
        # Runs independently of eval_targets so the sequence updates on every spin.
        # Targets are resolved from pre-spin scores (correct betting behaviour —
        # you decide what to back before the wheel spins).
        if state.lab_active and state.lab_sequence and unique_numbers:
            try:
                lab_spin_int = int(unique_numbers[-1])
            except (ValueError, TypeError):
                lab_spin_int = None

            if lab_spin_int is not None:
                bet_calc = (state.lab_sequence[0] + state.lab_sequence[-1]
                            if len(state.lab_sequence) > 1 else state.lab_sequence[0])

                is_single_target = "1 Target" in state.lab_mode
                total_risk = bet_calc if is_single_target else bet_calc * 2
                profit_on_win = bet_calc

                # Resolve which numbers count as a win for this spin.
                # Prefer active strategy targets; fall back to score-based resolution.
                lab_targets = (state.active_strategy_targets
                               if state.active_strategy_targets
                               else _resolve_lab_targets())

                if lab_targets and lab_spin_int in lab_targets:
                    # WIN — cancel first and last elements of the sequence.
                    state.lab_bankroll += profit_on_win
                    state.lab_sequence = (state.lab_sequence[1:-1]
                                          if len(state.lab_sequence) >= 2 else [])
                    if not state.lab_sequence:
                        state.lab_status = "Complete: Profit Secured!"
                        state.lab_active = False
                else:
                    # LOSS — append the risk to the sequence.
                    state.lab_bankroll -= total_risk
                    if state.lab_split_limit > 0 and total_risk >= state.lab_split_limit:
                        half1 = round(total_risk / 2.0, 2)
                        half2 = round(total_risk - half1, 2)
                        state.lab_sequence.extend([half1, half2])
                    else:
                        state.lab_sequence.append(total_risk)
        # -----------------------------------------------
        if len(unique_numbers) < len(numbers):
            duplicates = [n for n in numbers if numbers.count(n) > 1]
            logger.debug(f"add_spin: Removed duplicates: {', '.join(set(duplicates))}")
        
        logger.debug(f"add_spin: Added {len(unique_numbers)} spins, new_spins_str='{new_spins_str}', time={time.time() - start_time:.3f}s")
        
        _update_drought_counters()
        formatted_html = format_spins_as_html(new_spins_str, num_to_show)
        autosave(state)
        return new_spins_str, new_spins_str, formatted_html, update_spin_counter(), render_sides_of_zero_display()

    except Exception as e:
        logger.error(
            f"add_spin: Unexpected error: {str(e)}\n{traceback.format_exc()}"
        )
        gr.Warning(
            f"⚠️ Spin processing error (spins preserved): "
            f"{type(e).__name__}: {str(e)}"
        )
        # Return last known state so the user can continue entering spins
        safe_spins_str = ", ".join(str(s) for s in state.last_spins) if state.last_spins else (current_spins or "")
        try:
            safe_html = format_spins_as_html(safe_spins_str, num_to_show)
        except Exception:
            logger.error(f"add_spin: Failed to render fallback spins HTML\n{traceback.format_exc()}")
            safe_html = "<h4>Last Spins</h4><p>⚠️ Error rendering spins — please enter another spin.</p>"
        return safe_spins_str, safe_spins_str, safe_html, update_spin_counter(), render_sides_of_zero_display()


def process_aidea_upload(file):
    if file is None:
        return gr.update(visible=False), "", "" # Return empty strings for HTML components
    try:
        file_path = _get_file_path(file)
        if not file_path:
            return gr.update(visible=False), "Error: Unable to read uploaded file path.", ""
        with open(file_path, 'r') as f:
            data = json.load(f)
        # Validate expected top-level structure
        if not isinstance(data, dict):
            return gr.update(visible=False), "Invalid Strategy JSON: Root must be an object.", ""
        phases = data.get("phases", [])
        rules = data.get("phaseRules", {})
        if not isinstance(phases, list):
            return gr.update(visible=False), "Invalid Strategy JSON: 'phases' must be a list.", ""
        if not isinstance(rules, dict):
            return gr.update(visible=False), "Invalid Strategy JSON: 'phaseRules' must be an object.", ""
        if not phases:
            return gr.update(visible=False), "Invalid Strategy JSON: No phases found.", ""
        # Validate each phase has required 'id' field
        for i, phase in enumerate(phases):
            if not isinstance(phase, dict) or "id" not in phase:
                return gr.update(visible=False), f"Invalid Strategy JSON: Phase {i} is missing required 'id' field.", ""
        state.aidea_phases = phases
        state.aidea_rules = rules
        state.aidea_current_id = state.aidea_phases[0]["id"]
        state.aidea_completed_ids = set()
        roadmap_html, banner_html = render_aidea_roadmap_html()
        return gr.update(visible=True), roadmap_html, banner_html
    except json.JSONDecodeError as e:
        return gr.update(visible=False), f"Invalid JSON file: {str(e)}", ""
    except Exception as e:
        return gr.update(visible=False), f"Error parsing strategy: {str(e)}", ""

def get_aidea_multiplier():
    """Helper to get the current multiplier, defaulting to 1."""
    return state.aidea_unit_multiplier

def set_aidea_multiplier(value_str):
    """Update the multiplier state based on dropdown value."""
    try:
        if "x100" in value_str: val = 100
        elif "x10" in value_str: val = 10
        else: val = 1
        state.aidea_unit_multiplier = val
    except Exception as e:
        logger.error(f"set_aidea_multiplier error: {e}")
    return render_aidea_roadmap_html()

def reset_aidea_progress():
    try:
        if state.aidea_phases:
            state.aidea_current_id = state.aidea_phases[0]["id"]
            state.aidea_completed_ids = set()
    except Exception as e:
        logger.error(f"reset_aidea_progress error: {e}")
    return render_aidea_roadmap_html()

def nav_aidea_prev():
    """Move selection to the previous phase."""
    try:
        if not state.aidea_phases: return render_aidea_roadmap_html()
        
        current_idx = 0
        for i, p in enumerate(state.aidea_phases):
            if p['id'] == state.aidea_current_id:
                current_idx = i
                break
                
        new_idx = max(0, current_idx - 1)
        state.aidea_current_id = state.aidea_phases[new_idx]['id']
        return render_aidea_roadmap_html()
    except Exception as e:
        logger.error(f"nav_aidea_prev error: {e}")
        return render_aidea_roadmap_html()

def nav_aidea_next():
    """Move selection to the next phase."""
    try:
        if not state.aidea_phases: return render_aidea_roadmap_html()
        
        current_idx = 0
        for i, p in enumerate(state.aidea_phases):
            if p['id'] == state.aidea_current_id:
                current_idx = i
                break
                
        new_idx = min(len(state.aidea_phases) - 1, current_idx + 1)
        state.aidea_current_id = state.aidea_phases[new_idx]['id']
        return render_aidea_roadmap_html()
    except Exception as e:
        logger.error(f"nav_aidea_next error: {e}")
        return render_aidea_roadmap_html()

def nav_aidea_toggle(auto_trigger=False, result=None, auto_enabled=False, shield_down_mode=False, aggressor_reset_mode=False):
    """
    Toggle phase status. 
    Applies Strict JSON Logic: Reads exact onWin/onLose routing from the active AIDEA file.
    """
    try:
        # Safety Check: If no phases loaded, just return the view
        if not state.aidea_phases or state.aidea_current_id is None: 
            return render_aidea_roadmap_html()
        
        pid = state.aidea_current_id
        
        # --- MANUAL CLICK (Just Toggle Checkmark) ---
        if not auto_trigger:
            if pid in state.aidea_completed_ids:
                state.aidea_completed_ids.remove(pid) # Toggle Off
            else:
                state.aidea_completed_ids.add(pid) # Toggle On
                nav_aidea_next() # Move to next visually
            return render_aidea_roadmap_html()

        # --- AUTO-PILOT LOGIC (STRICT JSON READER) ---
        if not auto_enabled:
            return render_aidea_roadmap_html()

        # 1. Find where we are in the list (Index 0, 1, 2...)
        current_idx = -1
        for i, p in enumerate(state.aidea_phases):
            if p['id'] == pid:
                current_idx = i
                break
                
        # Safety: If ID not found, stop
        if current_idx == -1: return render_aidea_roadmap_html()

        total_phases = len(state.aidea_phases)
        next_idx = current_idx
        
        # Initialize repeat counter if not exists
        if pid not in state.aidea_phase_repeats:
            state.aidea_phase_repeats[pid] = 0

        # Retrieve specific rules for this phase from the JSON Memory
        str_pid = str(pid)
        # Clean float formatting if JS passed IDs as floats (e.g. "123.0")
        if str_pid.endswith('.0'): str_pid = str_pid[:-2]
        
        phase_rules = state.aidea_rules.get(str_pid, {})

        # 2. APPLY STRICT JSON RULES
        if result == "LOSS":
            state.aidea_phase_repeats[pid] = 0 # Reset repeat counter on loss
            
            rule = phase_rules.get("onLose", {"action": "next"})
            action = rule.get("action", "next")
            
            if action == "goto":
                target_id = rule.get("targetPhaseId")
                target_idx = next((i for i, p in enumerate(state.aidea_phases) if p['id'] == target_id), -1)
                next_idx = target_idx if target_idx != -1 else min(current_idx + 1, total_phases - 1)
            elif action == "reset":
                next_idx = 0
            elif action == "repeat":
                next_idx = current_idx
            else: # "next" or missing
                next_idx = min(current_idx + 1, total_phases - 1)

        elif result == "WIN":
            state.aidea_completed_ids.add(pid) # Mark won phase as done
            
            rule = phase_rules.get("onWin", {"action": "reset"})
            action = rule.get("action", "reset")
            
            if action == "repeat":
                max_repeats = rule.get("repeatCount", 1)
                if state.aidea_phase_repeats[pid] < max_repeats:
                    state.aidea_phase_repeats[pid] += 1
                    next_idx = current_idx # Stay and repeat
                else:
                    state.aidea_phase_repeats[pid] = 0 # Counter met
                    next_idx = 0 # Hard reset after fulfilling max repeats
            elif action == "goto":
                state.aidea_phase_repeats[pid] = 0
                target_id = rule.get("targetPhaseId")
                target_idx = next((i for i, p in enumerate(state.aidea_phases) if p['id'] == target_id), -1)
                next_idx = target_idx if target_idx != -1 else 0
            elif action == "next":
                state.aidea_phase_repeats[pid] = 0
                next_idx = min(current_idx + 1, total_phases - 1)
            else: # "reset" or missing
                state.aidea_phase_repeats[pid] = 0
                next_idx = 0

        # 3. EXECUTE MOVE
        if 0 <= next_idx < total_phases:
            state.aidea_current_id = state.aidea_phases[next_idx]['id']

        return render_aidea_roadmap_html()
    except Exception as e:
        logger.error(f"nav_aidea_toggle error: {e}")
        return render_aidea_roadmap_html()

def render_aidea_roadmap_html():
    """Thin wrapper – delegates to wheelpulsepro.rendering."""
    try:
        return _rendering.render_aidea_roadmap_html(state, DOZENS, get_aidea_multiplier())
    except Exception as e:
        logger.error(f"render_aidea_roadmap_html error: {e}")
        empty_roadmap = "<div style='text-align:center;padding:20px;color:#ccc;'><h4>Waiting for Strategy...</h4></div>"
        empty_banner = "<div style='padding:10px;background:#333;color:#fff;border-radius:4px;text-align:center;'><b>NO ACTIVE STRATEGY</b></div>"
        return empty_roadmap, empty_banner

def generate_labouchere_html():
    """Render the Labouchere sequence tracker HTML (delegates to rendering module)."""
    try:
        return _rendering.generate_labouchere_html(state)
    except Exception as e:
        logger.error(f"generate_labouchere_html error: {e}")
        return "<div style='padding:10px;color:#ef4444;'>⚠️ Error rendering Sequence Tracker view.</div>"


def _labouchere_update():
    """Return (html, accordion_update) keeping the accordion open on every refresh."""
    return generate_labouchere_html(), gr.update(open=True)


def render_strategy_alert_html():
    """Thin wrapper – delegates to wheelpulsepro.rendering."""
    return _rendering.render_strategy_alert_html(state)

def render_strategy_summary_html():
    """Thin wrapper – delegates to wheelpulsepro.rendering."""
    return _rendering.render_strategy_summary_html(state)

def render_strategy_cards_area_html(*args):
    """Render full-size strategy cards for the near-table area.

    When called with the same positional arguments as de2d_tracker_logic
    (i.e., with de2d_inputs_list), those slider/filter values are forwarded
    so the accordion cards match the DE2D section exactly — including the
    user's HUD visibility checkboxes and threshold sliders.

    When called with no arguments (e.g. for the initial component value),
    uses the same defaults as the DE2D section slider initial values.
    """
    if args:
        # Pass all de2d inputs through; append return_cards_only=True
        return de2d_tracker_logic(*args, return_cards_only=True)
    # No args: derive defaults from _DE2D_SLIDER_CFG so the cards always
    # match the slider initial values and the "Default" preset exactly.
    _d = [cfg[0] for cfg in _DE2D_SLIDER_CFG]  # index 0 = default value
    all_filters = _HUD_DEFAULT_VISIBLE
    return de2d_tracker_logic(
        miss_threshold=_d[0], even_threshold=_d[1], streak_threshold=_d[2], pattern_x=_d[3],
        voisins_threshold=_d[4], tiers_threshold=_d[5], left_threshold=_d[6], right_threshold=_d[7],
        ds_threshold=_d[8], d17_threshold=_d[9], corner_threshold=_d[10],
        tr_short_window=_d[15], tr_short_hits=_d[16],
        tr_long_window=_d[17], tr_long_hits=_d[18],
        tr_min_streak=_d[19], tr_density_window=_d[20],
        tr_density_hits=_d[21], tr_active_lifetime=_d[22],
        hud_filters=all_filters, return_cards_only=True
    )

def _resolve_lab_targets():
    """Resolve which roulette numbers count as a WIN for the current Labouchere session.

    Uses ``state.lab_mode`` to pick the top-trending categories from the live
    scoring data and returns the union of their number sets.

    Modes:
      "2 Targets (Dozens/Columns)" — top-2 dozens OR top-2 columns (whichever
        group has the higher combined score; dozens win ties).
      "1 Target (Even Money)"      — single best even-money category.

    Returns an empty set when no scores have been recorded yet.
    """
    mode = state.lab_mode
    targets = set()

    if "1 Target" in mode:
        em_scores = getattr(state, 'even_money_scores', {})
        if em_scores and any(v > 0 for v in em_scores.values()):
            best_em = max(em_scores, key=em_scores.get)
            targets.update(EVEN_MONEY.get(best_em, []))
    else:
        dz_scores = getattr(state, 'dozen_scores', {})
        col_scores = getattr(state, 'column_scores', {})
        dz_total = sum(dz_scores.values()) if dz_scores else 0
        col_total = sum(col_scores.values()) if col_scores else 0

        if dz_total >= col_total and dz_total > 0:
            for name, _ in sorted(dz_scores.items(), key=lambda x: x[1], reverse=True)[:2]:
                if dz_scores[name] > 0:
                    targets.update(DOZENS.get(name, []))
        elif col_total > 0:
            for name, _ in sorted(col_scores.items(), key=lambda x: x[1], reverse=True)[:2]:
                if col_scores[name] > 0:
                    targets.update(COLUMNS.get(name, []))

    return targets


def start_lab_session(base, target, mode, split_limit):
    """Initialise a new Labouchere sequence session.

    Divides ``target`` by ``base`` to build the opening sequence, then stores
    all session parameters in state.  Returns ``_labouchere_update()`` so
    Gradio can refresh the tracker HTML and keep the accordion open.
    """
    try:
        base = float(base)
        if base <= 0:
            base = 1.0
    except (TypeError, ValueError):
        base = 1.0

    try:
        target = float(target)
        if target <= 0:
            target = 10.0
    except (TypeError, ValueError):
        target = 10.0

    try:
        split_limit = float(split_limit)
        if split_limit < 0:
            split_limit = 0.0
    except (TypeError, ValueError):
        split_limit = 0.0

    # Build sequence: N equal units plus an optional remainder.
    # Round before int() to avoid floating-point drift (e.g. 10/1 → 9.999999).
    count = int(round(target / base, 6))
    remainder = round(target - count * base, 2)
    seq = [round(base, 2)] * count
    if remainder > 0.005:
        seq.append(remainder)

    state.lab_sequence = seq
    state.lab_active = True
    state.lab_base = base
    state.lab_target = target
    state.lab_mode = mode if mode else "2 Targets (Dozens/Columns)"
    state.lab_split_limit = split_limit
    state.lab_bankroll = 0.0
    state.lab_status = "ACTIVE"
    state.strategy_lab_enabled = True

    logger.debug(
        f"start_lab_session: base={base}, target={target}, "
        f"mode={state.lab_mode}, split_limit={split_limit}, seq={seq}"
    )
    return _labouchere_update()


def reset_lab_session(mode):
    """Reset the Labouchere session to idle/waiting state."""
    state.lab_active = False
    state.lab_sequence = []
    state.lab_base = 1.0
    state.lab_target = 10.0
    state.lab_bankroll = 0.0
    state.lab_status = "Waiting to Start"
    state.lab_mode = mode if mode else "2 Targets (Dozens/Columns)"
    state.lab_split_limit = 0.0
    state.strategy_lab_enabled = False

    logger.debug(f"reset_lab_session: mode={state.lab_mode}")
    return _labouchere_update()

def highlight_even_money(strategy_name, sorted_sections, top_color, middle_color, lower_color):
    """Highlight even money bets for relevant strategies."""
    if sorted_sections is None:
        return None, None, None, {}
    trending, second, third = None, None, None
    number_highlights = {}
    if strategy_name in ["Best Even Money Bets", "Best Even Money Bets + Top Pick 18 Numbers", 
                         "Best Dozens + Best Even Money Bets + Top Pick 18 Numbers", 
                         "Best Columns + Best Even Money Bets + Top Pick 18 Numbers"]:
        even_money_hits = [item for item in sorted_sections["even_money"] if item[1] > 0]
        if even_money_hits:
            trending = even_money_hits[0][0]
            second = even_money_hits[1][0] if len(even_money_hits) > 1 else None
            third = even_money_hits[2][0] if len(even_money_hits) > 2 else None
    elif strategy_name == "Hot Bet Strategy":
        trending = sorted_sections["even_money"][0][0] if sorted_sections["even_money"] else None
        second = sorted_sections["even_money"][1][0] if len(sorted_sections["even_money"]) > 1 else None
    elif strategy_name == "Cold Bet Strategy":
        sorted_even_money = sorted(state.even_money_scores.items(), key=lambda x: x[1])
        trending = sorted_even_money[0][0] if sorted_even_money else None
        second = sorted_even_money[1][0] if len(sorted_even_money) > 1 else None
    elif strategy_name in ["3-8-6 Rising Martingale", "Fibonacci To Fortune"]:
        # For Fibonacci To Fortune, highlight only the top even money bet
        trending = sorted_sections["even_money"][0][0] if sorted_sections["even_money"] else None
    elif strategy_name == "Best Even Money Bet (Till the tie breaks, No Highlighting)":
        sorted_em = sorted(state.even_money_scores.items(), key=lambda x: x[1], reverse=True)
        if sorted_em and sorted_em[0][1] > 0:
            # Check if 1st place is strictly greater than 2nd place
            if len(sorted_em) > 1 and sorted_em[0][1] > sorted_em[1][1]:
                trending = sorted_em[0][0]
            # If tied (sorted_em[0][1] == sorted_em[1][1]), trending remains None (No Highlight)
    return trending, second, third, number_highlights

def highlight_dozens(strategy_name, sorted_sections, top_color, middle_color, lower_color):
    """Highlight dozens for relevant strategies."""
    if sorted_sections is None:
        return None, None, {}
    trending, second = None, None
    number_highlights = {}
    if strategy_name in ["Best Dozens", "Best Dozens + Top Pick 18 Numbers", 
                         "Best Dozens + Best Even Money Bets + Top Pick 18 Numbers", 
                         "Best Dozens + Best Streets"]:
        dozens_hits = [item for item in sorted_sections["dozens"] if item[1] > 0]
        if dozens_hits:
            trending = dozens_hits[0][0]
            second = dozens_hits[1][0] if len(dozens_hits) > 1 else None
    elif strategy_name == "Hot Bet Strategy":
        trending = sorted_sections["dozens"][0][0] if sorted_sections["dozens"] else None
        second = sorted_sections["dozens"][1][0] if len(sorted_sections["dozens"]) > 1 else None
    elif strategy_name == "Cold Bet Strategy":
        sorted_dozens = sorted(state.dozen_scores.items(), key=lambda x: x[1])
        trending = sorted_dozens[0][0] if sorted_dozens else None
        second = sorted_dozens[1][0] if len(sorted_dozens) > 1 else None
    elif strategy_name in ["Fibonacci Strategy", "Fibonacci To Fortune"]:
        # For Fibonacci To Fortune, always highlight the top two dozens
        trending = sorted_sections["dozens"][0][0] if sorted_sections["dozens"] else None
        second = sorted_sections["dozens"][1][0] if len(sorted_sections["dozens"]) > 1 else None
    elif strategy_name == "1 Dozen +1 Column Strategy":
        trending = sorted_sections["dozens"][0][0] if sorted_sections["dozens"] and sorted_sections["dozens"][0][1] > 0 else None
    elif strategy_name == "Best Single Dozen (Till the tie breaks, No Highlighting)":
        sorted_d = sorted(state.dozen_scores.items(), key=lambda x: x[1], reverse=True)
        if sorted_d and sorted_d[0][1] > 0:
            if len(sorted_d) > 1 and sorted_d[0][1] > sorted_d[1][1]:
                trending = sorted_d[0][0]
    elif strategy_name == "Romanowksy Missing Dozen":
        trending = sorted_sections["dozens"][0][0] if sorted_sections["dozens"] and sorted_sections["dozens"][0][1] > 0 else None
        second = sorted_sections["dozens"][1][0] if len(sorted_sections["dozens"]) > 1 and sorted_sections["dozens"][1][1] > 0 else None
        weakest_dozen = min(state.dozen_scores.items(), key=lambda x: x[1], default=("1st Dozen", 0))[0]
        straight_up_df = pd.DataFrame(list(state.scores.items()), columns=["Number", "Score"])
        straight_up_df = straight_up_df[straight_up_df["Score"] > 0].sort_values(by="Score", ascending=False)
        weak_numbers = [row["Number"] for _, row in straight_up_df.iterrows() if row["Number"] in DOZENS[weakest_dozen]][:8]
        for num in weak_numbers:
            number_highlights[str(num)] = top_color
    return trending, second, number_highlights

def highlight_columns(strategy_name, sorted_sections, top_color, middle_color, lower_color):
    """Highlight columns for relevant strategies."""
    if sorted_sections is None:
        return None, None, {}
    trending, second = None, None
    number_highlights = {}
    if strategy_name in ["Best Columns", "Best Columns + Top Pick 18 Numbers", 
                         "Best Columns + Best Even Money Bets + Top Pick 18 Numbers", 
                         "Best Columns + Best Streets"]:
        columns_hits = [item for item in sorted_sections["columns"] if item[1] > 0]
        if columns_hits:
            trending = columns_hits[0][0]
            second = columns_hits[1][0] if len(columns_hits) > 1 else None
    elif strategy_name == "Hot Bet Strategy":
        trending = sorted_sections["columns"][0][0] if sorted_sections["columns"] else None
        second = sorted_sections["columns"][1][0] if len(sorted_sections["columns"]) > 1 else None
    elif strategy_name == "Cold Bet Strategy":
        sorted_columns = sorted(state.column_scores.items(), key=lambda x: x[1])
        trending = sorted_columns[0][0] if sorted_columns else None
        second = sorted_columns[1][0] if len(sorted_columns) > 1 else None
    elif strategy_name in ["Fibonacci Strategy", "Fibonacci To Fortune"]:
        # For Fibonacci To Fortune, always highlight the top two columns
        trending = sorted_sections["columns"][0][0] if sorted_sections["columns"] else None
        second = sorted_sections["columns"][1][0] if len(sorted_sections["columns"]) > 1 else None
    elif strategy_name == "Best Column (Till the tie breaks, No Highlighting)":
        sorted_c = sorted(state.column_scores.items(), key=lambda x: x[1], reverse=True)
        if sorted_c and sorted_c[0][1] > 0:
            if len(sorted_c) > 1 and sorted_c[0][1] > sorted_c[1][1]:
                trending = sorted_c[0][0]
    elif strategy_name == "1 Dozen +1 Column Strategy":
        trending = sorted_sections["columns"][0][0] if sorted_sections["columns"] and sorted_sections["columns"][0][1] > 0 else None
    return trending, second, number_highlights

def highlight_numbers(strategy_name, sorted_sections, top_color, middle_color, lower_color, strong_numbers_count=18):
    """Highlight straight-up numbers for relevant strategies, supporting dynamic counts from 1-34."""
    if sorted_sections is None:
        return {}
    number_highlights = {}
    straight_up_df = pd.DataFrame(list(state.scores.items()), columns=["Number", "Score"])
    straight_up_df = straight_up_df[straight_up_df["Score"] > 0].sort_values(by="Score", ascending=False)
    
    # List of strategies that use the 'Top Pick' number highlighting
    top_pick_strategies = [
        "Top Pick 18 Numbers without Neighbours", 
        "Best Even Money Bets + Top Pick 18 Numbers", 
        "Best Dozens + Top Pick 18 Numbers", 
        "Best Columns + Top Pick 18 Numbers", 
        "Best Dozens + Best Even Money Bets + Top Pick 18 Numbers", 
        "Best Columns + Best Even Money Bets + Top Pick 18 Numbers"
    ]

    if strategy_name in top_pick_strategies:
        # Get the count from the slider (passed via strong_numbers_count)
        # We cap it at 34 as requested
        count = max(1, min(int(strong_numbers_count), 34))
        
        if not straight_up_df.empty:
            # Take the top N numbers based on score
            top_n_numbers = straight_up_df["Number"].head(count).tolist()
            
            # Divide the count into 3 tiers for coloring
            tier_size = count // 3
            remainder = count % 3
            
            # First tier gets the remainder
            size1 = tier_size + remainder
            size2 = tier_size
            
            for i, num in enumerate(top_n_numbers):
                if i < size1: color = top_color
                elif i < (size1 + size2): color = middle_color
                else: color = lower_color
                number_highlights[str(num)] = color

            # --- GHOST PREDICTOR LOGIC ---
            # Identify the NEXT 3 strongest numbers that didn't make the primary cut
            ghost_picks = straight_up_df["Number"].iloc[count:count+3].tolist()
            for ghost_num in ghost_picks:
                # Use semi-transparent white to trigger the dashed border CSS
                number_highlights[str(ghost_num)] = "rgba(255, 255, 255, 0.2)"
                
    elif strategy_name == "Top Numbers with Neighbours (Tiered)":
        num_to_take = min(8, len(straight_up_df))
        top_numbers = set(straight_up_df["Number"].head(num_to_take).tolist())
        number_groups = []
        for num in top_numbers:
            left, right = current_neighbors.get(num, (None, None))
            group = [num]
            if left is not None:
                group.append(left)
            if right is not None:
                group.append(right)
            number_groups.append((state.scores[num], group))
        number_groups.sort(key=lambda x: x[0], reverse=True)
        ordered_numbers = []
        for _, group in number_groups:
            ordered_numbers.extend(group)
        ordered_numbers = ordered_numbers[:24]
        for i, num in enumerate(ordered_numbers):
            color = top_color if i < 8 else (middle_color if i < 16 else lower_color)
            number_highlights[str(num)] = color
    return number_highlights

def highlight_other_bets(strategy_name, sorted_sections, top_color, middle_color, lower_color):
    """Highlight streets, corners, splits, and double streets for relevant strategies."""
    if sorted_sections is None:
        return {}
    number_highlights = {}
    
    if strategy_name == "Hot Bet Strategy":
        for i, (street_name, _) in enumerate(sorted_sections["streets"][:9]):
            numbers = STREETS[street_name]
            color = top_color if i < 3 else (middle_color if 3 <= i < 6 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
        for i, (corner_name, _) in enumerate(sorted_sections["corners"][:9]):
            numbers = CORNERS[corner_name]
            color = top_color if i < 3 else (middle_color if 3 <= i < 6 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
        for i, (split_name, _) in enumerate(sorted_sections["splits"][:9]):
            numbers = SPLITS[split_name]
            color = top_color if i < 3 else (middle_color if 3 <= i < 6 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
    elif strategy_name == "Cold Bet Strategy":
        sorted_streets = sorted(state.street_scores.items(), key=lambda x: x[1])
        sorted_corners = sorted(state.corner_scores.items(), key=lambda x: x[1])
        sorted_splits = sorted(state.split_scores.items(), key=lambda x: x[1])
        for i, (street_name, _) in enumerate(sorted_streets[:9]):
            numbers = STREETS[street_name]
            color = top_color if i < 3 else (middle_color if 3 <= i < 6 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
        for i, (corner_name, _) in enumerate(sorted_corners[:9]):
            numbers = CORNERS[corner_name]
            color = top_color if i < 3 else (middle_color if 3 <= i < 6 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
        for i, (split_name, _) in enumerate(sorted_splits[:9]):
            numbers = SPLITS[split_name]
            color = top_color if i < 3 else (middle_color if 3 <= i < 6 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
    elif strategy_name == "Best Streets":
        for i, (street_name, _) in enumerate(sorted_sections["streets"][:9]):
            numbers = STREETS[street_name]
            color = top_color if i < 3 else (middle_color if 3 <= i < 6 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
    elif strategy_name in ["Best Dozens + Best Streets", "Best Columns + Best Streets"]:
        for i, (street_name, _) in enumerate(sorted_sections["streets"][:9]):
            numbers = STREETS[street_name]
            color = top_color if i < 3 else (middle_color if 3 <= i < 6 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
    elif strategy_name == "Best Double Streets":
        for i, (six_line_name, _) in enumerate(sorted_sections["six_lines"][:9]):
            numbers = SIX_LINES[six_line_name]
            color = top_color if i < 3 else (middle_color if 3 <= i < 6 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
    elif strategy_name == "Best Corners":
        for i, (corner_name, _) in enumerate(sorted_sections["corners"][:9]):
            numbers = CORNERS[corner_name]
            color = top_color if i < 3 else (middle_color if 3 <= i < 6 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
    elif strategy_name == "Sniper: Best Street + Corner":
        # Highlight top 3 streets (yellow, cyan, green) + top 3 corners
        # Streets get priority on overlapping numbers
        for i, (corner_name, _) in enumerate(sorted_sections["corners"][:3]):
            numbers = CORNERS[corner_name]
            color = top_color if i == 0 else (middle_color if i == 1 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
        # Streets painted on top so they take visual priority
        for i, (street_name, _) in enumerate(sorted_sections["streets"][:3]):
            numbers = STREETS[street_name]
            color = top_color if i == 0 else (middle_color if i == 1 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
    elif strategy_name == "Best Splits":
        for i, (split_name, _) in enumerate(sorted_sections["splits"][:9]):
            numbers = SPLITS[split_name]
            color = top_color if i < 3 else (middle_color if 3 <= i < 6 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
    elif strategy_name == "Non-Overlapping Double Street Strategy":
        non_overlapping_sets = [
            ["1ST D.STREET – 1, 4", "3RD D.STREET – 7, 10", "5TH D.STREET – 13, 16", "7TH D.STREET – 19, 22", "9TH D.STREET – 25, 28"],
            ["2ND D.STREET – 4, 7", "4TH D.STREET – 10, 13", "6TH D.STREET – 16, 19", "8TH D.STREET – 22, 25", "10TH D.STREET – 28, 31"]
        ]
        set_scores = []
        for idx, non_overlapping_set in enumerate(non_overlapping_sets):
            total_score = sum(state.six_line_scores.get(name, 0) for name in non_overlapping_set)
            set_scores.append((idx, total_score, non_overlapping_set))
        best_set = max(set_scores, key=lambda x: x[1], default=(0, 0, non_overlapping_sets[0]))
        sorted_best_set = sorted(best_set[2], key=lambda name: state.six_line_scores.get(name, 0), reverse=True)[:9]
        for i, double_street_name in enumerate(sorted_best_set):
            numbers = SIX_LINES[double_street_name]
            color = top_color if i < 3 else (middle_color if 3 <= i < 6 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
    elif strategy_name == "Non-Overlapping Corner Strategy":
        sorted_corners = sorted(state.corner_scores.items(), key=lambda x: x[1], reverse=True)
        selected_corners = []
        selected_numbers = set()
        for corner_name, _ in sorted_corners:
            if len(selected_corners) >= 9:
                break
            corner_numbers = set(CORNERS[corner_name])
            if not corner_numbers & selected_numbers:
                selected_corners.append(corner_name)
                selected_numbers.update(corner_numbers)
        for i, corner_name in enumerate(selected_corners):
            numbers = CORNERS[corner_name]
            color = top_color if i < 3 else (middle_color if 3 <= i < 6 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
    elif strategy_name == "3-8-6 Rising Martingale":
        top_streets = sorted_sections["streets"][:8]
        for i, (street_name, _) in enumerate(top_streets):
            numbers = STREETS[street_name]
            color = top_color if i < 3 else (middle_color if 3 <= i < 6 else lower_color)
            for num in numbers:
                number_highlights[str(num)] = color
    elif strategy_name == "Fibonacci To Fortune":
        # Highlight the best double street in the weakest dozen, excluding numbers from the top two dozens
        sorted_dozens = sorted(state.dozen_scores.items(), key=lambda x: x[1], reverse=True)
        weakest_dozen = min(state.dozen_scores.items(), key=lambda x: x[1], default=("1st Dozen", 0))[0]
        top_two_dozens = [item[0] for item in sorted_dozens[:2]]
        top_two_dozen_numbers = set()
        for dozen_name in top_two_dozens:
            top_two_dozen_numbers.update(DOZENS[dozen_name])
        double_streets_in_weakest = [
            (name, state.six_line_scores.get(name, 0))
            for name, numbers in SIX_LINES.items()
            if set(numbers).issubset(DOZENS[weakest_dozen]) and not set(numbers).intersection(top_two_dozen_numbers)
        ]
        if double_streets_in_weakest:
            top_double_street = max(double_streets_in_weakest, key=lambda x: x[1])[0]
            for num in SIX_LINES[top_double_street]:
                number_highlights[str(num)] = top_color
    return number_highlights

def highlight_neighbors(strategy_name, sorted_sections, neighbours_count, strong_numbers_count, top_color, middle_color):
    """Highlight neighbors for the Neighbours of Strong Number strategy."""
    if sorted_sections is None:
        return {}
    number_highlights = {}
    if strategy_name == "Neighbours of Strong Number":
        sorted_numbers = sorted(state.scores.items(), key=lambda x: (-x[1], x[0]))
        numbers_hits = [item for item in sorted_numbers if item[1] > 0]
        if numbers_hits:
            strong_numbers_count = min(strong_numbers_count, len(numbers_hits))
            top_numbers = set(item[0] for item in numbers_hits[:strong_numbers_count])
            neighbors_set = set()
            for strong_number in top_numbers:
                current_number = strong_number
                for _ in range(neighbours_count):
                    left, _ = current_neighbors.get(current_number, (None, None))
                    if left is not None:
                        neighbors_set.add(left)
                        current_number = left
                    else:
                        break
                current_number = strong_number
                for _ in range(neighbours_count):
                    _, right = current_neighbors.get(current_number, (None, None))
                    if right is not None:
                        neighbors_set.add(right)
                        current_number = right
                    else:
                        break
            neighbors_set = neighbors_set - top_numbers
            for num in top_numbers:
                number_highlights[str(num)] = top_color
            for num in neighbors_set:
                number_highlights[str(num)] = middle_color
    return number_highlights
# Apply strategy highlights with neighbor highlights
def apply_strategy_highlights(strategy_name, neighbours_count, strong_numbers_count, sorted_sections, top_color=None, middle_color=None, lower_color=None, suggestions=None):
    """Apply highlights based on the selected strategy with custom colors, passing suggestions for outside bets."""
    if sorted_sections is None:
        return None, None, None, None, None, None, None, {}, "white", "white", "white", None

    # Set default colors unless overridden
    if strategy_name == "Cold Bet Strategy":
        top_color = "#D3D3D3"  # Light Gray (Cold Top)
        middle_color = "#DDA0DD"  # Plum (Cold Middle)
        lower_color = "#E0FFFF"  # Light Cyan (Cold Lower)
    else:
        top_color = top_color if top_color else "rgba(255, 255, 0, 0.5)"  # Yellow
        middle_color = middle_color if middle_color else "rgba(0, 255, 255, 0.5)"  # Cyan
        lower_color = lower_color if lower_color else "rgba(0, 255, 0, 0.5)"  # Green

    # Initialize highlight variables
    trending_even_money, second_even_money, third_even_money = None, None, None
    trending_dozen, second_dozen = None, None
    trending_column, second_column = None, None
    number_highlights = {}

    # Apply highlights based on strategy
    if strategy_name and strategy_name in STRATEGIES:
        strategy_info = STRATEGIES[strategy_name]
        if strategy_name == "Neighbours of Strong Number":
            result = strategy_info["function"](neighbours_count, strong_numbers_count)
            # Handle the tuple return value
            if isinstance(result, tuple) and len(result) == 2:
                recommendations, strategy_suggestions = result
                suggestions = suggestions if suggestions is not None else strategy_suggestions
            else:
                # Fallback in case the function doesn't return the expected tuple
                recommendations = result
                suggestions = None
        else:
            # Other strategies return a single string
            recommendations = strategy_info["function"]()
            suggestions = None
        
        # Delegate to helper functions
        em_trending, em_second, em_third, em_highlights = highlight_even_money(strategy_name, sorted_sections, top_color, middle_color, lower_color)
        dz_trending, dz_second, dz_highlights = highlight_dozens(strategy_name, sorted_sections, top_color, middle_color, lower_color)
        col_trending, col_second, col_highlights = highlight_columns(strategy_name, sorted_sections, top_color, middle_color, lower_color)
        num_highlights = highlight_numbers(strategy_name, sorted_sections, top_color, middle_color, lower_color, strong_numbers_count)
        neighbor_highlights = highlight_neighbors(strategy_name, sorted_sections, neighbours_count, strong_numbers_count, top_color, middle_color)
        other_highlights = highlight_other_bets(strategy_name, sorted_sections, top_color, middle_color, lower_color)

        # Combine highlights
        trending_even_money = em_trending
        second_even_money = em_second
        third_even_money = em_third
        trending_dozen = dz_trending
        second_dozen = dz_second
        trending_column = col_trending
        second_column = col_second
        number_highlights.update(em_highlights)
        number_highlights.update(dz_highlights)
        number_highlights.update(col_highlights)
        number_highlights.update(num_highlights)
        number_highlights.update(neighbor_highlights)
        number_highlights.update(other_highlights)

    # Dozen Tracker Logic (When No Strategy is Selected)
    if strategy_name == "None":
        recent_spins = state.last_spins[-neighbours_count:] if len(state.last_spins) >= neighbours_count else state.last_spins
        dozen_counts = {"1st Dozen": 0, "2nd Dozen": 0, "3rd Dozen": 0}
        for spin in recent_spins:
            spin_value = int(spin)
            if spin_value != 0:
                for name, numbers in DOZENS.items():
                    if spin_value in numbers:
                        dozen_counts[name] += 1
                        break
        sorted_dozens = sorted(dozen_counts.items(), key=lambda x: x[1], reverse=True)
        if sorted_dozens[0][1] > 0:
            trending_dozen = sorted_dozens[0][0]
        if sorted_dozens[1][1] > 0:
            second_dozen = sorted_dozens[1][0]

    return trending_even_money, second_even_money, third_even_money, trending_dozen, second_dozen, trending_column, second_column, number_highlights, top_color, middle_color, lower_color, suggestions

def render_dynamic_table_html(trending_even_money, second_even_money, third_even_money, trending_dozen, second_dozen, trending_column, second_column, number_highlights, top_color, middle_color, lower_color, suggestions=None, hot_numbers=None, scores=None):
    """Generate HTML for the dynamic roulette table with improved visual clarity."""
    # Safety check for empty data
    if all(v is None for v in [trending_even_money, second_even_money, third_even_money, trending_dozen, second_dozen, trending_column, second_column]) and not number_highlights and not suggestions:
        return "<p>Please analyze some spins first to see highlights on the dynamic table.</p>"

    # Define casino winners
    casino_winners = {"hot_numbers": set(), "cold_numbers": set(), "even_money": set(), "dozens": set(), "columns": set()}
    if state.use_casino_winners:
        casino_winners["hot_numbers"] = set(state.casino_data["hot_numbers"].keys())
        casino_winners["cold_numbers"] = set(state.casino_data["cold_numbers"].keys())
        if any(state.casino_data["even_odd"].values()):
            casino_winners["even_money"].add(max(state.casino_data["even_odd"], key=state.casino_data["even_odd"].get))
        if any(state.casino_data["red_black"].values()):
            casino_winners["even_money"].add(max(state.casino_data["red_black"], key=state.casino_data["red_black"].get))
        if any(state.casino_data["low_high"].values()):
            casino_winners["even_money"].add(max(state.casino_data["low_high"], key=state.casino_data["low_high"].get))
        if any(state.casino_data["dozens"].values()):
            casino_winners["dozens"] = {max(state.casino_data["dozens"], key=state.casino_data["dozens"].get)}
        if any(state.casino_data["columns"].values()):
            casino_winners["columns"] = {max(state.casino_data["columns"], key=state.casino_data["columns"].get)}

    # Initialize suggestion highlights
    suggestion_highlights = {}
    if suggestions:
        best_even_money = None
        best_bet = None
        play_two_first = None
        play_two_second = None

        for key, value in suggestions.items():
            if key == "best_even_money" and "(Tied with" not in value:
                best_even_money = value.split(":")[0].strip()
            elif key == "best_bet" and "(Tied with" not in value:
                best_bet = value.split(":")[0].strip()
            elif key == "play_two" and "(Tied with" not in value:
                parts = value.split(":", 1)[1].split(" and ")
                if len(parts) >= 2:
                    play_two_first = parts[0].split("(")[0].strip()
                    play_two_second = parts[1].split("(")[0].strip()

        if best_even_money:
            suggestion_highlights[best_even_money] = top_color
        if best_bet:
            suggestion_highlights[best_bet] = top_color
        if play_two_first and play_two_second:
            if best_bet and play_two_first == best_bet:
                suggestion_highlights[play_two_first] = top_color
            else:
                suggestion_highlights[play_two_first] = top_color
            suggestion_highlights[play_two_second] = lower_color

    table_layout = [
        ["", "3", "6", "9", "12", "15", "18", "21", "24", "27", "30", "33", "36"],
        ["0", "2", "5", "8", "11", "14", "17", "20", "23", "26", "29", "32", "35"],
        ["", "1", "4", "7", "10", "13", "16", "19", "22", "25", "28", "31", "34"]
    ]

    html = '<table class="large-table dynamic-roulette-table" border="1" style="border-collapse: collapse; text-align: center; font-size: 14px; font-family: Arial, sans-serif; border-color: black; table-layout: fixed; width: 100%; max-width: 600px;">'
    html += '<colgroup><col style="width: 40px;">'
    for _ in range(12):
        html += '<col style="width: 40px;">'
    html += '<col style="width: 80px;"></colgroup>'

    hot_numbers = set(hot_numbers) if hot_numbers else set()
    scores = scores if scores is not None else {}

    for row_idx, row in enumerate(table_layout):
        html += "<tr>"
        for num in row:
            if num == "":
                html += '<td style="height: 40px; border-color: black; box-sizing: border-box;"></td>'
            else:
                base_color = colors.get(num, "black")
                highlight_color = number_highlights.get(num, base_color)
                
                border_style = "3px solid black"
                if num in casino_winners["hot_numbers"]:
                    border_style = "3px solid #FFD700"
                elif num in casino_winners["cold_numbers"]:
                    border_style = "3px solid #C0C0C0"
                
                text_style = "color: white; font-weight: bold; text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.8);"
                cell_class = "hot-number has-tooltip" if num in hot_numbers else "has-tooltip"
                hit_count = scores.get(num, scores.get(int(num), 0) if num.isdigit() else 0)
                tooltip = f"Hit {hit_count} times"
                html += f'<td style="height: 40px; background-color: {highlight_color}; {text_style} border: {border_style}; padding: 0; vertical-align: middle; box-sizing: border-box; text-align: center;" class="{cell_class}" data-tooltip="{tooltip}">{num}</td>'
        
        # Add Columns Logic
        if row_idx == 0:
            col_name = "3rd Column"
        elif row_idx == 1:
            col_name = "2nd Column"
        elif row_idx == 2:
            col_name = "1st Column"
        
        bg_color = suggestion_highlights.get(col_name, top_color if trending_column == col_name else (middle_color if second_column == col_name else "white"))
        border_style = "3px dashed #FFD700" if col_name in casino_winners["columns"] else "1px solid black"
        tier_class = "top-tier" if bg_color == top_color else "middle-tier" if bg_color == middle_color else "lower-tier" if bg_color == lower_color else ""
        col_score = state.column_scores.get(col_name, 0)
        max_col_score = max(state.column_scores.values(), default=1) or 1
        fill_percentage = (col_score / max_col_score) * 100
        html += f'<td style="background-color: {bg_color}; border: {border_style}; padding: 0; font-size: 10px; vertical-align: middle; box-sizing: border-box; height: 40px; text-align: center;" class="{tier_class}"><span>{col_name}</span><div class="progress-bar"><div class="progress-fill {tier_class}" style="width: {fill_percentage}%;"></div></div></td>'
        html += "</tr>"

    # Row for Low/High
    html += "<tr>"
    html += '<td style="height: 40px; border-color: black; box-sizing: border-box;"></td>'
    for name, label in [("Low", "Low (1 to 18)"), ("High", "High (19 to 36)")]:
        bg_color = suggestion_highlights.get(name, top_color if trending_even_money == name else (middle_color if second_even_money == name else (lower_color if third_even_money == name else "white")))
        border_style = "3px dashed #FFD700" if name in casino_winners["even_money"] else "1px solid black"
        tier_class = "top-tier" if bg_color == top_color else "middle-tier" if bg_color == middle_color else "lower-tier" if bg_color == lower_color else ""
        score = state.even_money_scores.get(name, 0)
        max_score = max(state.even_money_scores.values(), default=1) or 1
        fill_percentage = (score / max_score) * 100
        html += f'<td colspan="6" style="background-color: {bg_color}; color: black; border: {border_style}; padding: 0; font-size: 10px; vertical-align: middle; box-sizing: border-box; height: 40px; text-align: center;" class="{tier_class}"><span>{label}</span><div class="progress-bar"><div class="progress-fill {tier_class}" style="width: {fill_percentage}%;"></div></div></td>'
    html += '<td style="border-color: black; box-sizing: border-box;"></td>'
    html += "</tr>"

    # Row for Dozens
    html += "<tr>"
    html += '<td style="height: 40px; border-color: black; box-sizing: border-box;"></td>'
    for name in ["1st Dozen", "2nd Dozen", "3rd Dozen"]:
        bg_color = suggestion_highlights.get(name, top_color if trending_dozen == name else (middle_color if second_dozen == name else "white"))
        border_style = "3px dashed #FFD700" if name in casino_winners["dozens"] else "1px solid black"
        tier_class = "top-tier" if bg_color == top_color else "middle-tier" if bg_color == middle_color else "lower-tier" if bg_color == lower_color else ""
        score = state.dozen_scores.get(name, 0)
        max_score = max(state.dozen_scores.values(), default=1) or 1
        fill_percentage = (score / max_score) * 100
        html += f'<td colspan="4" style="background-color: {bg_color}; color: black; border: {border_style}; padding: 0; font-size: 10px; vertical-align: middle; box-sizing: border-box; height: 40px; text-align: center;" class="{tier_class}"><span>{name}</span><div class="progress-bar"><div class="progress-fill {tier_class}" style="width: {fill_percentage}%;"></div></div></td>'
    html += '<td style="border-color: black; box-sizing: border-box;"></td>'
    html += "</tr>"

    # Row for Even Money
    html += "<tr>"
    html += '<td style="height: 40px; border-color: black; box-sizing: border-box;"></td>'
    html += '<td colspan="4" style="border-color: black; box-sizing: border-box;"></td>'
    for name, label in [("Odd", "ODD"), ("Red", "RED"), ("Black", "BLACK"), ("Even", "EVEN")]:
        bg_color = suggestion_highlights.get(name, top_color if trending_even_money == name else (middle_color if second_even_money == name else (lower_color if third_even_money == name else "white")))
        border_style = "3px dashed #FFD700" if name in casino_winners["even_money"] else "1px solid black"
        tier_class = "top-tier" if bg_color == top_color else "middle-tier" if bg_color == middle_color else "lower-tier" if bg_color == lower_color else ""
        score = state.even_money_scores.get(name, 0)
        max_score = max(state.even_money_scores.values(), default=1) or 1
        fill_percentage = (score / max_score) * 100
        html += f'<td style="background-color: {bg_color}; color: black; border: {border_style}; padding: 0; font-size: 10px; vertical-align: middle; box-sizing: border-box; height: 40px; text-align: center;" class="{tier_class}"><span>{label}</span><div class="progress-bar"><div class="progress-fill {tier_class}" style="width: {fill_percentage}%;"></div></div></td>'
    html += '<td colspan="4" style="border-color: black; box-sizing: border-box;"></td>'
    html += '<td style="border-color: black; box-sizing: border-box;"></td>'
    html += "</tr>"

    html += "</table>"

    # --- STRATEGY RECOMMENDATIONS: Best Street & Best Corner ---
    street_scores_active = {k: v for k, v in state.street_scores.items() if v > 0}
    corner_scores_active = {k: v for k, v in state.corner_scores.items() if v > 0}

    if street_scores_active or corner_scores_active:
        html += '<div style="margin-top: 12px; background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 12px;">'
        html += '<div style="font-size: 13px; font-weight: 900; color: #ff00ff; text-transform: uppercase; margin-bottom: 10px; text-align: center; letter-spacing: 1px;">Strategy Recommendations</div>'

        if street_scores_active:
            sorted_st = sorted(street_scores_active.items(), key=lambda x: x[1], reverse=True)[:5]
            html += '<div style="margin-bottom: 10px;">'
            html += '<div style="font-size: 11px; color: #00BFFF; font-weight: bold; margin-bottom: 6px; border-bottom: 1px solid #1e3a5f; padding-bottom: 3px;">BEST STREETS (11:1)</div>'
            for i, (sname, shits) in enumerate(sorted_st):
                s_short = sname.split(" – ")[0] if " – " in sname else sname
                s_nums = sorted(STREETS[sname])
                is_top = (i == 0)
                bg = "rgba(0, 191, 255, 0.12)" if is_top else "transparent"
                border = "1px solid #00BFFF" if is_top else "1px solid #1e293b"
                html += f'<div style="display: flex; justify-content: space-between; align-items: center; padding: 5px 8px; background: {bg}; border: {border}; border-radius: 4px; margin-bottom: 3px;">'
                html += f'<span style="color: {"#00BFFF" if is_top else "#64748b"}; font-weight: {"900" if is_top else "normal"}; font-size: 12px;">{"→ " if is_top else ""}{s_short}</span>'
                html += f'<span style="color: #94a3b8; font-size: 11px;">[{", ".join(str(n) for n in s_nums)}]</span>'
                html += f'<span style="color: {"#4ade80" if is_top else "#64748b"}; font-weight: bold; font-size: 12px;">{shits}x</span>'
                html += '</div>'
            html += '</div>'

        if corner_scores_active:
            sorted_co = sorted(corner_scores_active.items(), key=lambda x: x[1], reverse=True)[:5]
            html += '<div>'
            html += '<div style="font-size: 11px; color: #FFD700; font-weight: bold; margin-bottom: 6px; border-bottom: 1px solid #5a4500; padding-bottom: 3px;">BEST CORNERS (8:1)</div>'
            for i, (cname, chits) in enumerate(sorted_co):
                c_short = cname.split(" – ")[0] if " – " in cname else cname
                c_nums_display = cname.split(" – ")[1] if " – " in cname else ""
                is_top = (i == 0)
                bg = "rgba(255, 215, 0, 0.12)" if is_top else "transparent"
                border = "1px solid #FFD700" if is_top else "1px solid #1e293b"
                html += f'<div style="display: flex; justify-content: space-between; align-items: center; padding: 5px 8px; background: {bg}; border: {border}; border-radius: 4px; margin-bottom: 3px;">'
                html += f'<span style="color: {"#FFD700" if is_top else "#64748b"}; font-weight: {"900" if is_top else "normal"}; font-size: 12px;">{"→ " if is_top else ""}{c_short}</span>'
                html += f'<span style="color: #94a3b8; font-size: 11px;">[{c_nums_display}]</span>'
                html += f'<span style="color: {"#4ade80" if is_top else "#64748b"}; font-weight: bold; font-size: 12px;">{chits}x</span>'
                html += '</div>'
            html += '</div>'

        html += '</div>'

    return html

def update_casino_data(spins_count, even_percent, odd_percent, red_percent, black_percent, low_percent, high_percent, dozen1_percent, dozen2_percent, dozen3_percent, col1_percent, col2_percent, col3_percent, use_winners):
    """Parse casino data inputs, update state, and generate HTML output."""
    try:
        state.casino_data["spins_count"] = int(spins_count)
        state.use_casino_winners = use_winners

        # Remove Hot/Cold Numbers parsing
        state.casino_data["hot_numbers"] = {}
        state.casino_data["cold_numbers"] = {}

        # Parse percentages from dropdowns
        def parse_percent(value, category, key):
            try:
                return float(value) if value != "00" else 0.0
            except ValueError:
                raise ValueError(f"Invalid {category} percentage for {key}: {value}")

        # Even/Odd
        even_val = parse_percent(even_percent, "Even vs Odd", "Even")
        odd_val = parse_percent(odd_percent, "Even vs Odd", "Odd")
        state.casino_data["even_odd"] = {"Even": even_val, "Odd": odd_val}
        has_even_odd = even_val > 0 or odd_val > 0

        # Red/Black
        red_val = parse_percent(red_percent, "Red vs Black", "Red")
        black_val = parse_percent(black_percent, "Red vs Black", "Black")
        state.casino_data["red_black"] = {"Red": red_val, "Black": black_val}
        has_red_black = red_val > 0 or black_val > 0

        # Low/High
        low_val = parse_percent(low_percent, "Low vs High", "Low")
        high_val = parse_percent(high_percent, "Low vs High", "High")
        state.casino_data["low_high"] = {"Low": low_val, "High": high_val}
        has_low_high = low_val > 0 or high_val > 0

        # Dozens
        d1_val = parse_percent(dozen1_percent, "Dozens", "1st Dozen")
        d2_val = parse_percent(dozen2_percent, "Dozens", "2nd Dozen")
        d3_val = parse_percent(dozen3_percent, "Dozens", "3rd Dozen")
        state.casino_data["dozens"] = {"1st Dozen": d1_val, "2nd Dozen": d2_val, "3rd Dozen": d3_val}
        has_dozens = d1_val > 0 or d2_val > 0 or d3_val > 0

        # Columns
        c1_val = parse_percent(col1_percent, "Columns", "1st Column")
        c2_val = parse_percent(col2_percent, "Columns", "2nd Column")
        c3_val = parse_percent(col3_percent, "Columns", "3rd Column")
        state.casino_data["columns"] = {"1st Column": c1_val, "2nd Column": c2_val, "3rd Column": c3_val}
        has_columns = c1_val > 0 or c2_val > 0 or c3_val > 0

        # Check for empty data when highlighting is enabled
        if use_winners and not any([has_even_odd, has_red_black, has_low_high, has_dozens, has_columns]):
            gr.Warning("Highlight Casino Winners is enabled, but no casino data is provided. Enter percentages to see highlights.")
            return "<p>Warning: No casino data provided for highlighting. Please enter percentages for Even/Odd, Red/Black, Low/High, Dozens, or Columns.</p>"

        # Generate HTML Output
        output = f"<h4>Casino Data Insights (Last {spins_count} Spins):</h4>"
        for key, name, has_data in [
            ("even_odd", "Even vs Odd", has_even_odd),
            ("red_black", "Red vs Black", has_red_black),
            ("low_high", "Low vs High", has_low_high)
        ]:
            if has_data:
                winner = max(state.casino_data[key], key=state.casino_data[key].get)
                output += f"<p>{name}: " + " vs ".join(
                    f"<b>{v:.1f}%</b>" if k == winner else f"{v:.1f}%" for k, v in state.casino_data[key].items()
                ) + f" (Winner: {winner})</p>"
            else:
                output += f"<p>{name}: Not set</p>"
        for key, name, has_data in [
            ("dozens", "Dozens", has_dozens),
            ("columns", "Columns", has_columns)
        ]:
            if has_data:
                winner = max(state.casino_data[key], key=state.casino_data[key].get)
                output += f"<p>{name}: " + " vs ".join(
                    f"<b>{v:.1f}%</b>" if k == winner else f"{v:.1f}%" for k, v in state.casino_data[key].items()
                ) + f" (Winner: {winner})</p>"
            else:
                output += f"<p>{name}: Not set</p>"
        logger.debug(f"Generated HTML Output: {output}")
        return output
    except ValueError as e:
        return f"<p>Error: {str(e)}</p>"
    except Exception as e:
        return f"<p>Unexpected error parsing casino data: {str(e)}</p>"
        
def reset_casino_data():
    """Reset casino data to defaults and clear UI inputs."""
    state.casino_data = {
        "spins_count": 100,
        "hot_numbers": {},
        "cold_numbers": {},
        "even_odd": {"Even": 0.0, "Odd": 0.0},
        "red_black": {"Red": 0.0, "Black": 0.0},
        "low_high": {"Low": 0.0, "High": 0.0},
        "dozens": {"1st Dozen": 0.0, "2nd Dozen": 0.0, "3rd Dozen": 0.0},
        "columns": {"1st Column": 0.0, "2nd Column": 0.0, "3rd Column": 0.0}
    }
    state.use_casino_winners = False
    return (
        "100",  # spins_count_dropdown
        "",     # hot_numbers_input
        "",     # cold_numbers_input
        "",     # even_odd_input
        "",     # red_black_input
        "",     # low_high_input
        "",     # dozens_input
        "",     # columns_input
        False,  # use_winners_checkbox
        "<p>Casino data reset to defaults.</p>"  # casino_data_output
    )

# Line 1: Start of create_dynamic_table function (updated)
def create_dynamic_table(strategy_name=None, neighbours_count=2, strong_numbers_count=1, dozen_tracker_spins=5, top_color=None, middle_color=None, lower_color=None, tracked_tiers=None):
    try:
        # Default tracked tiers if None
        if tracked_tiers is None: tracked_tiers = ["Yellow (Top)", "Cyan (Middle)"]

        # Ensure Colors are Resolved (Defaulting if None)
        top_color = top_color if top_color else "rgba(255, 255, 0, 0.5)"
        middle_color = middle_color if middle_color else "rgba(0, 255, 255, 0.5)"
        lower_color = lower_color if lower_color else "rgba(0, 255, 0, 0.5)"

        logger.debug(f"create_dynamic_table called with strategy: {strategy_name}, neighbours_count: {neighbours_count}, tracked_tiers: {tracked_tiers}")
        
        logger.debug("create_dynamic_table: Calculating trending sections")
        sorted_sections = calculate_trending_sections()
        logger.debug(f"create_dynamic_table: sorted_sections={sorted_sections}")
        
        # If no spins yet, initialize with default even money focus
        if sorted_sections is None and strategy_name == "Best Even Money Bets":
            logger.debug("create_dynamic_table: No spins yet, using default even money focus")
            trending_even_money = "Red"  # Default to "Red" as an example
            second_even_money = "Black"
            third_even_money = "Even"
            trending_dozen = None
            second_dozen = None
            trending_column = None
            second_column = None
            number_highlights = {}
            top_color = top_color if top_color else "rgba(255, 255, 0, 0.5)"
            middle_color = middle_color if middle_color else "rgba(0, 255, 255, 0.5)"
            lower_color = lower_color if lower_color else "rgba(0, 255, 0, 0.5)"
            suggestions = None
            hot_numbers = []  # No hot numbers without spins
        else:
            logger.debug("create_dynamic_table: Applying strategy highlights")
            trending_even_money, second_even_money, third_even_money, trending_dozen, second_dozen, trending_column, second_column, number_highlights, top_color, middle_color, lower_color, suggestions = apply_strategy_highlights(strategy_name, int(dozen_tracker_spins) if strategy_name == "None" else neighbours_count, strong_numbers_count, sorted_sections, top_color, middle_color, lower_color)
            
            # --- FIX: TRANSLATE VISUAL HIGHLIGHTS TO DATA FOR AUTO-PILOT ---
            # Strict Logic: Only numbers belonging to the CHECKED color tiers are valid targets.
            # If a tier is UNCHECKED, its numbers are NOT added, effectively treating them as "Losses" 
            # (unless they overlap with a Checked tier).
            active_targets = set()
            
            # Helper to check if a specific color string matches the user's "Yellow/Cyan/Green" selection
            # We compare the RGBA strings directly.
            def is_color_tracked(color_val):
                if color_val == top_color and "Yellow (Top)" in tracked_tiers: return True
                if color_val == middle_color and "Cyan (Middle)" in tracked_tiers: return True
                if color_val == lower_color and "Green (Lower)" in tracked_tiers: return True
                return False

            # 1. Collect straight-up numbers (e.g. from Number Strategies)
            if number_highlights:
                for num_str, color in number_highlights.items():
                    if num_str.isdigit():
                        if is_color_tracked(color):
                            active_targets.add(int(num_str))
            
            # 2. Collect numbers from Section Highlights (Even Money)
            # Only add if the SECTION's color matches a CHECKED tier.
            # Even Money Logic:
            em_map = {
                trending_even_money: top_color,
                second_even_money: middle_color,
                third_even_money: lower_color
            }
            for em_name, em_color in em_map.items():
                if em_name and em_name in EVEN_MONEY and is_color_tracked(em_color):
                    active_targets.update(EVEN_MONEY[em_name])

            # 3. Collect numbers from Section Highlights (Dozens)
            # Dozen Logic:
            dz_map = {
                trending_dozen: top_color,
                second_dozen: middle_color
            }
            for dz_name, dz_color in dz_map.items():
                if dz_name and dz_name in DOZENS and is_color_tracked(dz_color):
                    active_targets.update(DOZENS[dz_name])
            
            # 4. Collect numbers from Section Highlights (Columns)
            # Column Logic:
            col_map = {
                trending_column: top_color,
                second_column: middle_color
            }
            for col_name, col_color in col_map.items():
                if col_name and col_name in COLUMNS and is_color_tracked(col_color):
                    active_targets.update(COLUMNS[col_name])

            # 5. Save to global state for the Auto-Pilot to read
            state.active_strategy_targets = sorted(list(active_targets))
            logger.debug(f"DEBUG: Auto-Pilot Targets Updated ({tracked_tiers}): {len(state.active_strategy_targets)} numbers covered")
            # ---------------------------------------------------------------

            logger.debug(f"create_dynamic_table: Strategy highlights applied - trending_even_money={trending_even_money}, second_even_money={second_even_money}, third_even_money={third_even_money}, trending_dozen={trending_dozen}, second_dozen={second_dozen}, trending_column={trending_column}, second_column={second_column}, number_highlights={number_highlights}")
            
            # Determine hot numbers (top 5 with hits)
            sorted_scores = sorted(state.scores.items(), key=lambda x: x[1], reverse=True)
            hot_numbers = [str(num) for num, score in sorted_scores[:5] if score > 0]
            logger.debug(f"create_dynamic_table: Hot numbers={hot_numbers}, Scores={dict(state.scores)}")
        
        # If still no highlights and no sorted_sections, provide a default message
        if sorted_sections is None and not any([trending_even_money, second_even_money, third_even_money, trending_dozen, second_dozen, trending_column, second_column, number_highlights]):
            logger.debug("create_dynamic_table: No spins and no highlights, returning default message")
            return "<p>No spins yet. Select a strategy to see default highlights.</p>"
        
        logger.debug("create_dynamic_table: Rendering dynamic table HTML")
        html = render_dynamic_table_html(trending_even_money, second_even_money, third_even_money, trending_dozen, second_dozen, trending_column, second_column, number_highlights, top_color, middle_color, lower_color, suggestions, hot_numbers, scores=state.scores)
        logger.debug("create_dynamic_table: Table generated successfully")
        return html
    
    except Exception as e:
        logger.error(f"create_dynamic_table: Error: {str(e)}\n{traceback.format_exc()}")
        return "<div style='color:#ef4444;padding:8px;'>⚠️ Table rendering error — spins are preserved.</div>"
    
# Function to reset scores (no longer needed, but kept for compatibility)
def reset_scores():
    state.reset()
    return "Scores reset!"

def clear_all():
    state.selected_numbers.clear()
    state.last_spins = []
    
    # Hard reset Labouchere & AIDEA memory safely
    state.lab_active = False
    state.lab_sequence = []
    state.lab_status = "Waiting to Start"
    state.lab_bankroll = 0.0
    state.aidea_bankroll = 0.0
    state.aidea_last_result = None
    state.aidea_phase_repeats = {}
    
    state.sniper_locked = False
    state.sniper_locked_misses = 0
    
    # --- Reset Non-Repeater Memory ---
    state.current_non_repeaters.clear()
    state.previous_non_repeaters.clear()
    state.nr_last_spin_count = 0
    if hasattr(state, 'nr_mem_in'): state.nr_mem_in = []
    if hasattr(state, 'nr_mem_out'): state.nr_mem_out = []
    if hasattr(state, 'nr_mem_spin_in'): state.nr_mem_spin_in = 0
    if hasattr(state, 'nr_mem_spin_out'): state.nr_mem_spin_out = 0
    
    state.reset()
    ts = int(time.time() * 1000)
    js_clear = f'<script id="pin-clear-{ts}">localStorage.setItem("wp_rank_pins_v3","[]"); localStorage.setItem("wp_num_pins_v3","[]"); if(typeof fastUpdateWatchlist==="function") fastUpdateWatchlist();</script>'
    return "", "", "All spins and scores cleared successfully!", "<h4>Last Spins</h4><p>No spins yet.</p>", "", "", "", "", "", "", "", "", "", "", "", update_spin_counter(), render_sides_of_zero_display(), js_clear

def master_reset():
    """Full app reset — clears spins, scores, pins, Labouchere, AIDEA, and all watchlists."""
    state.selected_numbers.clear()
    state.last_spins = []
    state.spin_history = []
    state.side_scores = {"Left Side of Zero": 0, "Right Side of Zero": 0}
    state.scores = {n: 0 for n in range(37)}
    state.pinned_numbers = set()
    state.analysis_cache = {}
    state.current_top_picks = []
    state.previous_top_picks = []
    state.stability_counter = 0

    # Reset Labouchere
    state.lab_active = False
    state.lab_sequence = []
    state.lab_status = "Waiting to Start"
    state.lab_bankroll = 0.0

    # Reset AIDEA
    state.aidea_bankroll = 0.0
    state.aidea_last_result = None
    state.aidea_phase_repeats = {}
    state.aidea_phases = []
    state.aidea_rules = {}
    state.aidea_current_id = None
    state.aidea_completed_ids = set()
    state.aidea_active_targets = []
    state.active_strategy_targets = []

    # Reset Sniper & D17
    state.sniper_locked = False
    state.sniper_locked_misses = 0
    state.d17_list = []
    state.d17_locked = False

    # Reset Grind/Ramp
    state.grind_step_index = 0
    state.grind_last_spin_count = 0
    state.ramp_step_index = 0
    state.ramp_last_spin_count = 0
    
    # --- Reset Non-Repeater Memory ---
    state.current_non_repeaters.clear()
    state.previous_non_repeaters.clear()
    state.nr_last_spin_count = 0
    if hasattr(state, 'nr_mem_in'): state.nr_mem_in = []
    if hasattr(state, 'nr_mem_out'): state.nr_mem_out = []
    if hasattr(state, 'nr_mem_spin_in'): state.nr_mem_spin_in = 0
    if hasattr(state, 'nr_mem_spin_out'): state.nr_mem_spin_out = 0

    state.reset()

    js_full_reset = """<script>
        localStorage.setItem('wp_rank_pins_v3', '[]');
        localStorage.setItem('wp_num_pins_v3', '[]');
        if (typeof fastUpdateWatchlist === 'function') fastUpdateWatchlist();
        console.log('Master Reset: All pins and watchlists cleared.');
    </script>"""

    return (
        "", "",                                                              # spins_display, spins_textbox
        "✅ Master Reset Complete! App is ready for a new session.",     # spin_analysis_output
        "<h4>Last Spins</h4><p>No spins yet.</p>",                       # last_spin_display
        "", "", "", "", "", "", "", "", "", "", "",                      # all analysis outputs
        update_spin_counter(),                                           # spin_counter
        render_sides_of_zero_display(),                                  # sides_of_zero_display
        js_full_reset                                                    # js trigger
    )

def reset_strategy_dropdowns():
    default_category = "Even Money Strategies"
    default_strategy = "Best Even Money Bets"
    strategy_choices = strategy_categories[default_category]
    return default_category, default_strategy, strategy_choices

def create_color_code_table():
    html = '''
    <div style="margin-top: 20px;">
        <h3 style="margin-bottom: 10px; font-family: Arial, sans-serif;">Color Code Key</h3>
        <table border="1" style="border-collapse: collapse; text-align: left; font-size: 14px; font-family: Arial, sans-serif; width: 100%; max-width: 600px; border-color: #333;">
            <thead>
                <tr style="background-color: #f2f2f2;">
                    <th style="padding: 8px; width: 20%;">Color</th>
                    <th style="padding: 8px;">Meaning</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="padding: 8px; background-color: rgba(255, 255, 0, 0.5); text-align: center;">Yellow (Top Tier)</td>
                    <td style="padding: 8px;">Indicates the hottest or top-ranked numbers/sections (e.g., top 3 or top 6 in most strategies). For Dozen Tracker, this highlights the most frequent Dozen when no strategy is selected. Can be changed via color pickers.</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background-color: rgba(0, 255, 255, 0.5); text-align: center;">Cyan (Middle Tier)</td>
                    <td style="padding: 8px;">Represents the second tier of trending numbers/sections (e.g., ranks 4-6 or secondary picks). For Dozen Tracker, this highlights the second most frequent Dozen when no strategy is selected. Can be changed via color pickers.</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background-color: rgba(0, 255, 0, 0.5); text-align: center;">Green (Lower Tier)</td>
                    <td style="padding: 8px;">Marks the third tier of strong numbers/sections (e.g., ranks 7-9 or lower priority). Can be changed via color pickers.</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background-color: #D3D3D3; text-align: center;">Light Gray (Cold Top)</td>
                    <td style="padding: 8px;">Used in Cold Bet Strategy for the coldest top-tier sections (least hits). Fixed for this strategy.</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background-color: #DDA0DD; text-align: center;">Plum (Cold Middle)</td>
                    <td style="padding: 8px;">Used in Cold Bet Strategy for middle-tier cold sections. Fixed for this strategy.</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background-color: #E0FFFF; text-align: center;">Light Cyan (Cold Lower)</td>
                    <td style="padding: 8px;">Used in Cold Bet Strategy for lower-tier cold sections. Fixed for this strategy.</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background-color: red; color: white; text-align: center;">Red</td>
                    <td style="padding: 8px;">Default color for red numbers on the roulette table.</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background-color: black; color: white; text-align: center;">Black</td>
                    <td style="padding: 8px;">Default color for black numbers on the roulette table.</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background-color: green; color: white; text-align: center;">Green</td>
                    <td style="padding: 8px;">Default color for zero (0) on the roulette table.</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background-color: #FF6347; color: white; text-align: center;">Tomato Red</td>
                    <td style="padding: 8px;">Used in Dozen Tracker to represent the 1st Dozen.</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background-color: #4682B4; color: white; text-align: center;">Steel Blue</td>
                    <td style="padding: 8px;">Used in Dozen Tracker to represent the 2nd Dozen.</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background-color: #32CD32; color: white; text-align: center;">Lime Green</td>
                    <td style="padding: 8px;">Used in Dozen Tracker to represent the 3rd Dozen.</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background-color: #808080; color: white; text-align: center;">Gray</td>
                    <td style="padding: 8px;">Used in Dozen Tracker to represent spins not in any Dozen (i.e., 0).</td>
                </tr>
            </tbody>
        </table>
    </div>
    '''
    return html
    
def update_spin_counter():
    """Update the spin counter HTML with total spins and phase indicator."""
    try:
        current_list = getattr(state, 'last_spins', [])
        total_spins = len(current_list)
    except Exception:
        total_spins = 0

    if total_spins <= 20:
        phase_label = "EARLY"
        phase_color = "#1565c0"
        phase_bg    = "linear-gradient(135deg,#1565c0,#1976d2)"
        phase_icon  = "🔵"
        phase_tip   = "Gathering data"
    elif total_spins <= 50:
        phase_label = "MID"
        phase_color = "#e65100"
        phase_bg    = "linear-gradient(135deg,#e65100,#f57c00)"
        phase_icon  = "🟠"
        phase_tip   = "Patterns forming"
    else:
        phase_label = "DEEP"
        phase_color = "#b71c1c"
        phase_bg    = "linear-gradient(135deg,#b71c1c,#d32f2f)"
        phase_icon  = "🔴"
        phase_tip   = "Full analysis ready"

    return (
        f'<div style="display:flex;justify-content:center;align-items:center;width:100%;">'
        f'<div style="display:inline-flex;align-items:center;gap:8px;'
        f'background:{phase_bg};border-radius:20px;padding:6px 20px;'
        f'min-width:220px;justify-content:center;'
        f'box-shadow:0 2px 6px rgba(0,0,0,0.25);">'
        f'<span style="font-size:16px;">{phase_icon}</span>'
        f'<span class="spin-counter glow" style="font-size:14px;font-weight:900;color:#fff;">'
        f'Total Spins: {total_spins}</span>'
        f'<span style="background:rgba(255,255,255,0.25);color:#fff;font-size:10px;'
        f'font-weight:900;padding:2px 8px;border-radius:10px;text-transform:uppercase;letter-spacing:0.5px;">'
        f'{phase_label}</span>'
        f'<span style="font-size:10px;color:rgba(255,255,255,0.8);font-style:italic;">{phase_tip}</span>'
        f'</div>'
        f'</div>'
    )

def sync_spins_display(spins_display):
    """Passthrough to sync spins display state after hot/cold play."""
    return spins_display

def validate_hot_cold_numbers(numbers_input, type_label):
    """Validate hot or cold numbers input (1 to 10 numbers, 0-36)."""
    if not numbers_input or not numbers_input.strip():
        return None, f"Please enter 1 to 10 {type_label} numbers."

    try:
        numbers = [int(n.strip()) for n in numbers_input.split(",") if n.strip()]
        if len(numbers) < 1 or len(numbers) > 10:
            return None, f"Enter 1 to 10 {type_label} numbers (entered {len(numbers)})."
        if not all(0 <= n <= 36 for n in numbers):
            return None, f"All {type_label} numbers must be between 0 and 36."
        return numbers, None
    except ValueError:
        return None, f"Invalid {type_label} numbers. Use comma-separated integers (e.g., 1, 3, 5, 7, 9)."


def clear_hot_cold_picks(type_label, current_spins_display):
    """Clear hot or cold numbers input."""
    state.casino_data[f"{type_label.lower()}_numbers"] = []
    success_msg = f"Cleared {type_label} Picks successfully"
    logger.debug(f"clear_hot_cold_picks: {success_msg}")
    return "", success_msg, update_spin_counter(), render_sides_of_zero_display(), current_spins_display

def _sync_auto_sliders():
    """Return gr.update() calls to sync DE2D sliders to AUTO overrides.

    Returns a tuple of 10 gr.update() values for the nudgeable sliders (indices
    0–2, 4–10 in _DE2D_SLIDER_CFG, mapping to miss/even/streak/voisins/tiers/
    left/right/ds/d17/corner sliders).

    When mode is AUTO each gr.update carries the current effective value from
    _nudge_state['overrides'] (falling back to the cfg default).  When mode is
    not AUTO, gr.update() is returned without a value so the component is not
    touched.
    """
    try:
        if _nudge_state.get("mode") != "AUTO":
            return tuple(gr.update() for _ in range(10))
        ov = _nudge_state.get("overrides", {})
        def _v(cfg_idx):
            cfg = _DE2D_SLIDER_CFG[cfg_idx]
            return gr.update(value=_safe_slider_val(ov.get(cfg_idx, cfg[0]), cfg_idx))
        return (
            _v(0), _v(1), _v(2),   # miss, even, streak
            _v(4), _v(5),          # voisins, tiers
            _v(6), _v(7),          # left, right
            _v(8), _v(9), _v(10),  # ds, d17, corner
        )
    except Exception:
        return tuple(gr.update() for _ in range(10))


# ── Extra CSS for improved readability ──────────────────────────────────────
_EXTRA_CSS = """
/* Selected Spins Input - full width and more readable */
#selected-spins,
#selected-spins > .wrap,
#selected-spins > label,
#selected-spins-input,
#selected-spins-input > .wrap,
#selected-spins-input > label {
    width: 100% !important;
    max-width: 100% !important;
}
#selected-spins textarea,
#selected-spins input,
#selected-spins-input textarea,
#selected-spins-input input {
    width: 100% !important;
    max-width: 100% !important;
    font-size: 16px !important;
    padding: 12px !important;
    min-height: 50px !important;
    letter-spacing: 1px;
    font-family: 'Courier New', monospace;
}
#selected-spins label span,
#selected-spins-input label span {
    font-size: 16px !important;
    font-weight: 700 !important;
}

/* Accordion headers - more readable */
.gradio-accordion > .label-wrap {
    font-size: 16px !important;
    font-weight: 700 !important;
    padding: 12px !important;
}

/* Status bar: keep spin counter centered */
#status-bar-container {
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    justify-content: center !important;
    background: rgba(0, 0, 0, 0.05);
    border-radius: 12px;
    padding: 5px 15px !important;
    margin: 10px 0 !important;
    width: 100% !important;
}

#strategy-alert-overlay {
    width: 100% !important;
    border-left: 2px solid rgba(0,0,0,0.1);
    margin-left: 10px;
    border-radius: 8px;
    padding: 2px 8px;
    display: flex;
    align-items: center;
    min-height: 40px;
}

/* Spin counter: centered and wider */
.spin-counter-box {
    display: flex !important;
    justify-content: center !important;
    min-width: 220px !important;
    width: 100% !important;
    white-space: nowrap !important;
}

/* Selected spins row: full width matching accordions */
#selected-spins-row > div,
#selected-spins-row .gradio-column {
    width: 100% !important;
    max-width: 100% !important;
    flex: 1 1 100% !important;
    min-width: 0 !important;
}

/* Statistical Intelligence Layer — ensure all text is light on dark background */
#stat-intel-accordion > .label-wrap,
#stat-intel-accordion > .label-wrap span,
#stat-intel-accordion > .label-wrap button {
    color: #f1f5f9 !important;
}
#stat-intel-accordion b,
#stat-intel-accordion strong,
#stat-intel-accordion small,
#stat-intel-accordion h3,
#stat-intel-accordion h4,
#stat-intel-accordion label,
#stat-intel-accordion span {
    color: #e2e8f0 !important;
}
/* Ensure accordion label itself is visible */
.gradio-accordion#stat-intel-accordion > .label-wrap span,
details#stat-intel-accordion > summary span,
details#stat-intel-accordion > summary {
    color: #f1f5f9 !important;
}

/* Pulsing glow animation for the "If I were you" strong-signal card */
@keyframes pulse-glow {
    0%, 100% { box-shadow: 0 0 8px #ef4444aa; border-color: #ef4444; }
    50%       { box-shadow: 0 0 22px #ef4444, 0 0 35px #ef4444aa; border-color: #fca5a5; }
}

/* Final Brain display — always visible live decision engine */
#final-brain-output {
    margin: 8px 0 10px 0;
}
/* Ensure all bold/strong text in Final Brain renders white, not browser-default black */
#final-brain-output b,
#final-brain-output strong,
#final-brain-output li {
    color: #e2e8f0 !important;
}
@keyframes final-brain-glow {
    0%, 100% { box-shadow: 0 0 10px rgba(99,102,241,0.4); border-color: #6366f1; }
    50%       { box-shadow: 0 0 28px rgba(99,102,241,0.8), 0 0 50px rgba(99,102,241,0.3); border-color: #818cf8; }
}

/* Roulette table pulse/glow when strategy cards are active */
@keyframes table-pulse-glow {
    0%, 100% { box-shadow: 0 0 15px 4px rgba(255, 215, 0, 0.5), inset 0 0 15px 2px rgba(255, 215, 0, 0.1); border-color: #FFD700; }
    50% { box-shadow: 0 0 30px 10px rgba(255, 165, 0, 0.8), inset 0 0 25px 5px rgba(255, 165, 0, 0.15); border-color: #FFA500; }
}
.roulette-table-pulse {
    animation: table-pulse-glow 1.5s ease-in-out infinite !important;
    border: 4px solid #FFD700 !important;
    border-radius: 8px !important;
}

/* Siren indicator — flashing 🚨 emoji at top-right of roulette table */
@keyframes siren-flash {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.3; transform: scale(1.3); }
}
.siren-indicator {
    position: absolute;
    top: 6px;
    right: 10px;
    font-size: 24px;
    z-index: 10;
    animation: siren-flash 0.8s ease-in-out infinite;
}

/* Alerts Sidebar — fixed right-side panel that follows the user as they scroll */
#alerts-sidebar {
    background: linear-gradient(145deg, #0f172a, #1e293b);
    border: 2px solid #FFD700;
    border-radius: 8px;
    padding: 8px 12px;
    margin-top: 6px;
    margin-bottom: 10px;
    font-size: 12px;
    box-shadow: 0 2px 12px rgba(255, 215, 0, 0.2);
}
"""

with gr.Blocks(title="🎰 WheelPulse Pro Max — Roulette Spin Analyzer", css=_EXTRA_CSS) as demo:
    # Removed the Terms and Conditions Modal (gr.HTML block)

    # Compact Resource Bar (replaces old Discover WheelPulse section)
    gr.HTML("""
        <div id="resource-bar">
            <a href="https://youtu.be/Wn0xJTiVcdg" target="_blank" class="resource-link">
                <span>🎥</span> Video Guide
            </a>
            <span class="resource-divider"></span>
            <a href="https://drive.google.com/file/d/154GfZaiNUfAFB73WEIA617ofdZbRaEIN/view?usp=drive_link" target="_blank" class="resource-link">
                <span>📖</span> View Guide
            </a>
        </div>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Poppins:wght@600;700;800&family=Dancing+Script:wght@400;700&display=swap');
            #resource-bar {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 16px;
                padding: 8px 20px;
                margin: 6px auto 0;
                max-width: 1200px;
                background: rgba(15, 23, 42, 0.85);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 50px;
                box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3);
            }
            .resource-link {
                display: flex;
                align-items: center;
                gap: 6px;
                padding: 6px 16px;
                font-family: 'Inter', sans-serif;
                font-size: 13px;
                font-weight: 600;
                color: rgba(255, 255, 255, 0.85);
                text-decoration: none;
                border-radius: 20px;
                transition: all 0.2s ease;
                background: rgba(255, 255, 255, 0.06);
                letter-spacing: 0.3px;
            }
            .resource-link:hover {
                background: rgba(255, 215, 0, 0.15);
                color: #FFD700;
                transform: translateY(-1px);
                box-shadow: 0 2px 8px rgba(255, 215, 0, 0.2);
            }
            .resource-divider {
                width: 1px;
                height: 18px;
                background: rgba(255, 255, 255, 0.15);
            }
            @media (max-width: 600px) {
                #resource-bar {
                    gap: 10px;
                    padding: 6px 14px;
                }
                .resource-link {
                    font-size: 12px;
                    padding: 5px 12px;
                }
            }
        </style>
    """)
    
    # We create them here but don't show them yet (render=False). 
    # We will show them later in the "Dynamic AIDEA Roadmap" section using .render()
    initial_roadmap, initial_banner = render_aidea_roadmap_html()
    aidea_status_banner = gr.HTML(value=initial_banner, render=False)
    aidea_roadmap_view = gr.HTML(value=initial_roadmap, render=False)

    # Pre-define Labouchere view — rendered inside the Labouchere accordion below
    labouchere_view = gr.HTML(value=generate_labouchere_html(), render=False)
    
    # Pre-define the checkboxes so they exist for the table button click event
    # Auto-Pilot default is unchecked (value=False)
    aidea_auto_checkbox = gr.Checkbox(label="🤖 Enable Auto-Pilot (Navigates based on Win/Loss)", value=False, interactive=True, render=False)
    
    # New Options for Shield and Aggressor logic
    shield_down_checkbox = gr.Checkbox(label="🛡️ Shield: Move Down 1 on Win (Default: Reset)", value=False, interactive=True, render=False)
    aggressor_reset_checkbox = gr.Checkbox(label="⚔️ Aggressor: Reset to P1 after Repeat Win", value=False, interactive=True, render=False)

    # App Content (Header Section - Updated)
    with gr.Group(elem_id="appContent"):
        with gr.Row(elem_id="header-row"):
            gr.HTML("""
                <div class="header-container">
                    <h1 class="header-title">
                        <span class="wheelpulse-text">🎰 WheelPulse Pro Max</span>
                        <span class="by-styw">— Roulette Spin Analyzer</span>
                        <span class="roulette-icon">
                            <svg width="40" height="40" viewBox="0 0 100 100" class="spin-roulette">
                                <circle cx="50" cy="50" r="45" fill="#8a0707" stroke="#339e45" stroke-width="5"/>
                                <circle cx="50" cy="50" r="35" fill="#2e7d32"/>
                                <path d="M50 15 A35 35 0 0 1 85 50 A35 35 0 0 1 50 85 A35 35 0 0 1 15 50 A35 35 0 0 1 50 15" fill="#ff4444"/>
                                <path d="M50 15 A35 35 0 0 0 15 50 A35 35 0 0 0 50 85 A35 35 0 0 0 85 50 A35 35 0 0 0 50 15" fill="#000000"/>
                                <circle cx="50" cy="20" r="5" fill="#e4f2e4"/>
                                <circle cx="50" cy="50" r="5" fill="#000000"/>
                            </svg>
                        </span>
                    </h1>
                </div>
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@700&family=Dancing+Script:wght@400;700&display=swap');
                    .header-container {
                        display: flex !important;
                        justify-content: center !important;
                        align-items: center !important;
                        width: 100% !important;
                        padding: 15px 0 !important;
                        background: linear-gradient(135deg, #D3D3D3, #A9A9A9, #000000) !important;
                        border-radius: 10px !important;
                        box-shadow: 0 0 20px rgba(0, 0, 0, 0.7) !important;
                        margin-bottom: 20px !important;
                        position: relative !important;
                        overflow: hidden !important;
                    }
                    .header-title {
                        font-size: 2.8em !important;
                        color: #ffffff !important;
                        text-shadow: 0 0 15px rgba(255, 215, 0, 0.8), 0 0 5px rgba(0, 0, 0, 0.5) !important;
                        margin: 0 !important;
                        display: flex !important;
                        align-items: center !important;
                        gap: 10px !important;
                        position: relative !important;
                        z-index: 2 !important;
                        transition: transform 0.3s ease, text-shadow 0.3s ease !important;
                        animation: neonFlicker 2s ease-in-out infinite !important;
                    }
                    .header-title:hover {
                        transform: perspective(500px) rotateX(10deg) scale(1.05) !important;
                        text-shadow: 0 0 20px rgba(255, 215, 0, 1), 0 0 10px rgba(0, 0, 0, 0.7) !important;
                    }
                    .wheelpulse-text {
                        font-family: 'Poppins', sans-serif !important;
                        font-weight: 700 !important;
                        background: linear-gradient(90deg, #4B4B4B, #1C2526, #4B4B4B) !important;
                        background-size: 200% !important;
                        -webkit-background-clip: text !important;
                        background-clip: text !important;
                        color: transparent !important;
                        letter-spacing: 2px !important;
                        animation: shimmer 3s linear infinite !important;
                        text-shadow: none !important;
                    }
                    .by-styw {
                        font-family: 'Dancing Script', cursive !important;
                        font-size: 0.7em !important;
                        color: #333333 !important;
                        font-weight: 700 !important;
                        letter-spacing: 1px !important;
                        text-shadow: 0 0 5px rgba(255, 215, 0, 0.3) !important;
                        animation: subtleGlow 1.5s ease-in-out infinite !important;
                    }
                    .roulette-icon {
                        display: inline-block !important;
                        width: 40px !important;
                        height: 40px !important;
                    }
                    .spin-roulette {
                        animation: spin 4s linear infinite !important;
                    }
                    @keyframes neonFlicker {
                        0%, 100% { text-shadow: 0 0 15px rgba(255, 215, 0, 0.8), 0 0 5px rgba(0, 0, 0, 0.5); }
                        50% { text-shadow: 0 0 25px rgba(255, 215, 0, 1), 0 0 10px rgba(0, 0, 0, 0.7); }
                    }
                    @keyframes shimmer {
                        0% { background-position: 200%; }
                        100% { background-position: -200%; }
                    }
                    @keyframes subtleGlow {
                        0%, 100% { text-shadow: 0 0 5px rgba(255, 215, 0, 0.3); }
                        50% { text-shadow: 0 0 10px rgba(255, 215, 0, 0.6); }
                    }
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                    @media (max-width: 768px) {
                        .header-title {
                            font-size: 2em !important;
                        }
                        .by-styw {
                            font-size: 0.6em !important;
                        }
                        .roulette-icon {
                            width: 30px !important;
                            height: 30px !important;
                        }
                        .header-container {
                            padding: 10px 0 !important;
                        }
                    }
                    @media (max-width: 600px) {
                        .header-title {
                            font-size: 1.5em !important;
                            flex-direction: column !important;
                            gap: 5px !important;
                        }
                        .by-styw {
                            font-size: 0.55em !important;
                        }
                        .roulette-icon {
                            width: 25px !important;
                            height: 25px !important;
                        }
                        .header-container {
                            border-radius: 8px !important;
                        }
                    }
                    @media (prefers-reduced-motion: reduce) {
                        .roulette-button, .action-button, .spin-counter, .number-badge, 
                        .hot-number, .trait-badge, .pattern-badge, .new-spin, 
                        .switch-alert, .dozen-badge {
                            animation: none !important;
                            transition: none !important;
                        }
                    }
                </style>
            """)
    
        # Ensure app content is shown after acceptance
        gr.HTML("""
            <script>
                window.onload = function() {
                    if (localStorage.getItem('termsAccepted') === 'true') {
                        document.getElementById('appContent').style.display = 'block';
                    }
                };
            </script>
            <style>
                #appContent {
                    display: none;
                }
                #appContent[style*="display: block"] {
                    display: block !important;
                }
            </style>
        """)


    # Updated Selected Spins Accordion Styling (Modern)
    gr.HTML("""
    <style>
        /* ── Container ── */
        #selected-spins-row {
            background: linear-gradient(160deg, rgba(15,23,42,0.85) 0%, rgba(10,20,35,0.9) 100%) !important;
            backdrop-filter: blur(20px) !important;
            -webkit-backdrop-filter: blur(20px) !important;
            border: 1px solid rgba(20,184,166,0.2) !important;
            border-radius: 18px !important;
            padding: 18px 22px 14px !important;
            margin: 10px 0 !important;
            box-shadow: 0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.05) !important;
        }
        /* ── Label pill ── */
        #selected-spins label {
            background: linear-gradient(135deg, #0d9488, #14b8a6) !important;
            color: #fff !important;
            padding: 6px 16px !important;
            border-radius: 24px !important;
            font-family: 'Inter', sans-serif !important;
            font-size: 13px !important;
            font-weight: 700 !important;
            letter-spacing: 0.6px !important;
            text-transform: uppercase !important;
            text-shadow: none !important;
            transition: all 0.2s ease !important;
            display: inline-flex !important;
            width: fit-content !important;
            max-width: fit-content !important;
            align-items: center !important;
            gap: 6px !important;
            margin-bottom: 10px !important;
            box-shadow: 0 2px 10px rgba(13,148,136,0.4) !important;
        }
        #selected-spins label:hover {
            transform: translateY(-1px) !important;
            box-shadow: 0 4px 18px rgba(13,148,136,0.55) !important;
        }
        /* ── Input / Textarea field (Gradio 5 uses textarea) ── */
        #selected-spins textarea,
        #selected-spins input {
            background: rgba(255,255,255,0.97) !important;
            border: 2px solid rgba(13,148,136,0.25) !important;
            border-radius: 12px !important;
            padding: 13px 18px !important;
            font-family: 'Inter', monospace !important;
            font-size: 16px !important;
            font-weight: 600 !important;
            color: #0f172a !important;
            letter-spacing: 0.5px !important;
            transition: all 0.25s ease !important;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08), inset 0 1px 2px rgba(0,0,0,0.03) !important;
            resize: none !important;
            min-height: 46px !important;
            height: 46px !important;
            overflow: hidden !important;
            width: 100% !important;
            max-width: 100% !important;
            flex-grow: 1 !important;
            min-width: 0 !important;
        }
        #selected-spins,
        #selected-spins > div,
        #selected-spins .wrap,
        #selected-spins .container {
            width: 100% !important;
            max-width: 100% !important;
            flex-grow: 1 !important;
            min-width: 0 !important;
        }
        #selected-spins textarea:focus,
        #selected-spins input:focus {
            border-color: #14b8a6 !important;
            box-shadow: 0 0 0 3px rgba(20,184,166,0.22), 0 2px 10px rgba(0,0,0,0.08) !important;
            outline: none !important;
        }
        #selected-spins textarea::placeholder,
        #selected-spins input::placeholder {
            color: #94a3b8 !important;
            font-weight: 400 !important;
            letter-spacing: 0 !important;
        }
        #selected-spins textarea.typing,
        #selected-spins input.typing {
            animation: spinPulse 1.2s infinite ease-in-out;
        }
        @keyframes spinPulse {
            0%, 100% { box-shadow: 0 0 0 3px rgba(20,184,166,0.12); }
            50%       { box-shadow: 0 0 0 5px rgba(20,184,166,0.28); }
        }
        /* ── Badges row ── */
        #selected-spins-display {
            margin-top: 14px !important;
            display: flex !important;
            gap: 5px !important;
            flex-wrap: wrap !important;
            align-items: center !important;
        }
        .number-badge {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 36px !important;
            height: 36px !important;
            border-radius: 50% !important;
            font-family: 'Inter', sans-serif !important;
            font-size: 13px !important;
            font-weight: 800 !important;
            color: #fff !important;
            border: 2px solid rgba(255,255,255,0.15) !important;
            box-shadow: 0 3px 8px rgba(0,0,0,0.35) !important;
            transition: all 0.18s ease !important;
            animation: popIn 0.22s cubic-bezier(0.34,1.56,0.64,1);
            cursor: default !important;
        }
        .number-badge:hover {
            transform: scale(1.2) translateY(-3px) !important;
            box-shadow: 0 6px 16px rgba(0,0,0,0.45) !important;
            border-color: rgba(255,255,255,0.4) !important;
        }
        .number-badge.red   { background: linear-gradient(145deg,#b91c1c,#ef4444) !important; }
        .number-badge.black { background: linear-gradient(145deg,#0f172a,#1e293b) !important; }
        .number-badge.green { background: linear-gradient(145deg,#15803d,#22c55e) !important; }

        /* ── Live Streak Tracker ── */
        #spins-live-stats {
            display: none;
            margin-top: 14px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 10px 14px;
            gap: 0;
        }
        /* top row: last spin + streak pill */
        #spins-stats-top {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
            margin-bottom: 9px;
        }
        #spins-last-label {
            font-family: 'Inter', sans-serif;
            font-size: 11px;
            font-weight: 600;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.8px;
        }
        #spins-last-circle {
            width: 42px;
            height: 42px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-family: 'Inter', sans-serif;
            font-size: 15px;
            font-weight: 900;
            color: #fff;
            border: 2px solid rgba(255,255,255,0.25);
            box-shadow: 0 4px 14px rgba(0,0,0,0.5);
            transition: all 0.3s cubic-bezier(0.34,1.56,0.64,1);
        }
        #spins-streak-pill {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 5px 12px;
            border-radius: 20px;
            font-family: 'Inter', sans-serif;
            font-size: 13px;
            font-weight: 700;
            color: #fff;
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.15);
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            transition: background 0.3s ease;
        }
        #spins-streak-pill.streak-red   { background: rgba(185,28,28,0.45); border-color: rgba(239,68,68,0.5); }
        #spins-streak-pill.streak-black { background: rgba(15,23,42,0.6);   border-color: rgba(100,116,139,0.5); }
        #spins-streak-pill.streak-green { background: rgba(21,128,61,0.5);  border-color: rgba(34,197,94,0.5); }
        #spins-total-badge {
            margin-left: auto;
            font-family: 'Inter', sans-serif;
            font-size: 11px;
            font-weight: 700;
            color: #94a3b8;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 10px;
            padding: 4px 10px;
        }
        /* colour ratio bar */
        #spins-color-bar-wrap {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        #spins-color-bar-track {
            flex: 1;
            height: 8px;
            border-radius: 6px;
            background: rgba(255,255,255,0.08);
            overflow: hidden;
            display: flex;
        }
        #spins-bar-red   { height: 100%; background: linear-gradient(90deg,#b91c1c,#ef4444); transition: width 0.4s ease; }
        #spins-bar-black { height: 100%; background: linear-gradient(90deg,#1e293b,#475569); transition: width 0.4s ease; }
        #spins-bar-green { height: 100%; background: linear-gradient(90deg,#15803d,#22c55e); transition: width 0.4s ease; }
        #spins-color-legend {
            font-family: 'Inter', sans-serif;
            font-size: 11px;
            font-weight: 600;
            color: #94a3b8;
            white-space: nowrap;
        }

        /* ── Validation message ── */
        #selected-spins-validation {
            margin-top: 7px !important;
            font-family: 'Inter', sans-serif !important;
            font-size: 11px !important;
            font-weight: 600 !important;
            color: #64748b !important;
            display: none !important;
            letter-spacing: 0.3px !important;
        }
        #selected-spins-validation.valid   { color: #22c55e !important; display: block !important; }
        #selected-spins-validation.invalid {
            color: #ef4444 !important;
            display: block !important;
            animation: shake 0.3s ease-in-out;
        }
        /* ── Keyframes ── */
        @keyframes popIn {
            0%   { transform: scale(0) rotate(-15deg); opacity: 0; }
            100% { transform: scale(1) rotate(0deg);   opacity: 1; }
        }
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25%       { transform: translateX(-5px); }
            75%       { transform: translateX(5px); }
        }
    </style>
    """)

    # Start of the app layout (next section after the header)
    def suggest_hot_cold_numbers():
        """Suggest top 5 hot and bottom 5 cold numbers based on state.scores."""
        try:
            if not state.scores or not any(state.scores.values()):
                return "", "<p>No spin data available for suggestions.</p>"
            sorted_scores = sorted(state.scores.items(), key=lambda x: x[1], reverse=True)
            hot_numbers = [str(num) for num, score in sorted_scores[:5] if score > 0]
            cold_numbers = [str(num) for num, score in sorted_scores[-5:] if score >= 0]
            if not hot_numbers:
                hot_numbers = ["No hot numbers"]
            if not cold_numbers:
                cold_numbers = ["No cold numbers"]
            state.hot_suggestions = ", ".join(hot_numbers)
            state.cold_suggestions = ", ".join(cold_numbers)
            return state.hot_suggestions, state.cold_suggestions
        except Exception as e:
            logger.error(f"suggest_hot_cold_numbers: Error: {str(e)}")
            return "", "<p>Error generating suggestions.</p>"

    STRATEGIES = {
        "Hot Bet Strategy": {"function": hot_bet_strategy, "categories": ["even_money", "dozens", "columns", "streets", "corners", "six_lines", "splits", "sides", "numbers"]},
        "Cold Bet Strategy": {"function": cold_bet_strategy, "categories": ["even_money", "dozens", "columns", "streets", "corners", "six_lines", "splits", "sides", "numbers"]},
        "Best Even Money Bets": {"function": best_even_money_bets, "categories": ["even_money"]},
        "Best Even Money Bet (Till the tie breaks, No Highlighting)": {"function": best_even_money_bet_till_tie_break, "categories": ["even_money"]},
        "Best Even Money Bets + Top Pick 18 Numbers": {"function": best_even_money_and_top_18, "categories": ["even_money", "numbers"]},
        "Best Dozens": {"function": best_dozens, "categories": ["dozens"]},
        "Best Single Dozen (Till the tie breaks, No Highlighting)": {"function": best_dozen_till_tie_break, "categories": ["dozens"]},
        "Best Dozens + Top Pick 18 Numbers": {"function": best_dozens_and_top_18, "categories": ["dozens", "numbers"]},
        "Best Columns": {"function": best_columns, "categories": ["columns"]},
        "Best Column (Till the tie breaks, No Highlighting)": {"function": best_column_till_tie_break, "categories": ["columns"]},
        "Best Columns + Top Pick 18 Numbers": {"function": best_columns_and_top_18, "categories": ["columns", "numbers"]},
        "Best Dozens + Best Even Money Bets + Top Pick 18 Numbers": {"function": best_dozens_even_money_and_top_18, "categories": ["dozens", "even_money", "numbers", "trends"]},
        "Best Columns + Best Even Money Bets + Top Pick 18 Numbers": {"function": best_columns_even_money_and_top_18, "categories": ["columns", "even_money", "numbers", "trends"]},
        "Fibonacci Strategy": {"function": fibonacci_strategy, "categories": ["dozens", "columns"]},
        "Best Streets": {"function": best_streets, "categories": ["streets"]},
        "Best Double Streets": {"function": best_double_streets, "categories": ["six_lines"]},
        "Best Corners": {"function": best_corners, "categories": ["corners"]},
        "Best Splits": {"function": best_splits, "categories": ["splits"]},
        "Best Dozens + Best Streets": {"function": best_dozens_and_streets, "categories": ["dozens", "streets"]},
        "Best Columns + Best Streets": {"function": best_columns_and_streets, "categories": ["columns", "streets"]},
        "Non-Overlapping Double Street Strategy": {"function": non_overlapping_double_street_strategy, "categories": ["six_lines"]},
        "Non-Overlapping Corner Strategy": {"function": non_overlapping_corner_strategy, "categories": ["corners"]},
        "Romanowksy Missing Dozen": {"function": romanowksy_missing_dozen_strategy, "categories": ["dozens", "numbers"]},
        "Fibonacci To Fortune": {"function": fibonacci_to_fortune_strategy, "categories": ["even_money", "dozens", "columns", "six_lines"]},
        "3-8-6 Rising Martingale": {"function": three_eight_six_rising_martingale, "categories": ["streets"]},
        "1 Dozen +1 Column Strategy": {"function": one_dozen_one_column_strategy, "categories": ["dozens", "columns"]},
        "Top Pick 18 Numbers without Neighbours": {"function": top_pick_18_numbers_without_neighbours, "categories": ["numbers"]},
        "Top Numbers with Neighbours (Tiered)": {"function": top_numbers_with_neighbours_tiered, "categories": ["numbers"]},
        "Neighbours of Strong Number": {"function": neighbours_of_strong_number, "categories": ["neighbours"]},
        "Sniper: Best Street + Corner": {"function": sniper_best_street_corner, "categories": ["streets", "corners"]}
    }

    # Line 1: Start of show_strategy_recommendations function (updated)
    def show_strategy_recommendations(strategy_name, neighbours_count, *args):
        """Generate strategy recommendations based on the selected strategy."""
        try:
            logger.debug(f"show_strategy_recommendations: scores = {dict(state.scores)}")
            logger.debug(f"show_strategy_recommendations: even_money_scores = {dict(state.even_money_scores)}")
            logger.debug(f"show_strategy_recommendations: any_scores = {any(state.scores.values())}, any_even_money = {any(state.even_money_scores.values())}")
            logger.debug(f"show_strategy_recommendations: strategy_name = {strategy_name}, neighbours_count = {neighbours_count}, args = {args}")

            if strategy_name == "None":
                return "<p>No strategy selected. Please choose a strategy to see recommendations.</p>"
            
            # If no spins yet, provide a default for "Best Even Money Bets"
            if not any(state.scores.values()) and not any(state.even_money_scores.values()):
                if strategy_name == "Best Even Money Bets":
                    return "<p>No spins yet. Default Even Money Bets to consider:<br>1. Red<br>2. Black<br>3. Even</p>"
                return "<p>Please analyze some spins first to generate scores.</p>"

            strategy_info = STRATEGIES[strategy_name]
            strategy_func = strategy_info["function"]

            if strategy_name == "Neighbours of Strong Number":
                try:
                    neighbours_count = int(neighbours_count)
                    strong_numbers_count = int(args[0]) if args else 1  # Assuming strong_numbers_count is first in args
                    logger.debug(f"show_strategy_recommendations: Using neighbours_count = {neighbours_count}, strong_numbers_count = {strong_numbers_count}")
                except (ValueError, TypeError) as e:
                    logger.debug(f"show_strategy_recommendations: Error converting inputs: {str(e)}, defaulting to 2 and 1.")
                    neighbours_count = 2
                    strong_numbers_count = 1
                result = strategy_func(neighbours_count, strong_numbers_count)
                # Handle the tuple return value for Neighbours of Strong Number
                if isinstance(result, tuple) and len(result) == 2:
                    recommendations, _ = result  # We only need the recommendations string for display
                else:
                    recommendations = result
            elif strategy_name == "Top Pick 18 Numbers without Neighbours":
                try:
                    # Slider value is the 2nd argument in the Gradio event, mapped to args[0]
                    dynamic_count = int(args[0]) if args else 18
                except (ValueError, TypeError, IndexError):
                    dynamic_count = 18
                recommendations = strategy_func(dynamic_count)
            elif strategy_name in ["Best Even Money Bets + Top Pick 18 Numbers", 
                                  "Best Dozens + Top Pick 18 Numbers", 
                                  "Best Columns + Top Pick 18 Numbers", 
                                  "Best Dozens + Best Even Money Bets + Top Pick 18 Numbers", 
                                  "Best Columns + Best Even Money Bets + Top Pick 18 Numbers"]:
                try:
                    dynamic_count = int(args[0]) if args else 18
                except (ValueError, TypeError, IndexError):
                    dynamic_count = 18
                recommendations = strategy_func() # Get base combo text
                recommendations += "\n\n" + top_pick_18_numbers_without_neighbours(dynamic_count)
            elif strategy_name == "Dozen Tracker":
                # Dozen Tracker expects multiple arguments and returns a tuple
                result = strategy_func(*args)
                if isinstance(result, tuple) and len(result) == 3:
                    recommendations, _, _ = result  # Unpack the tuple, we only need the first element
                else:
                    recommendations = result
            elif strategy_name == "Top Numbers Strategy":
                # Handle Top Numbers Strategy
                try:
                    strong_numbers_count = int(args[0]) if args else 5  # Number of top numbers to show
                    logger.debug(f"show_strategy_recommendations: Using strong_numbers_count = {strong_numbers_count} for Top Numbers Strategy")
                except (ValueError, TypeError) as e:
                    logger.debug(f"show_strategy_recommendations: Error converting inputs: {str(e)}, defaulting to 5.")
                    strong_numbers_count = 5
                # Call the strategy function to get the top numbers
                top_numbers = strategy_func()  # Assuming this returns a list of (number, score) tuples
                if not top_numbers:
                    return "<p>No top numbers available. Please analyze more spins.</p>"
                # Limit to strong_numbers_count and sort by score
                top_numbers = sorted(top_numbers, key=lambda x: x[1], reverse=True)[:strong_numbers_count]
                # Generate neighbors for each number
                html = "<p>Here are the top numbers to consider based on recent spins:</p>"
                html += '<table class="strongest-numbers-table">'
                html += "<tr><th>Number</th><th>Score</th><th>Neighbors</th><th>Number</th><th>Score</th><th>Neighbors</th><th>Number</th><th>Score</th><th>Neighbors</th></tr>"
                # Pad the list with empty entries to make it divisible by 3
                while len(top_numbers) % 3 != 0:
                    top_numbers.append(("", ""))
                # Group numbers into sets of 3
                for i in range(0, len(top_numbers), 3):
                    group = top_numbers[i:i+3]
                    html += "<tr>"
                    for number, score in group:
                        if number:
                            neighbors = get_neighbors(number, neighbours_count)
                            html += f"<td>{number}</td><td>{score}</td><td>{', '.join(map(str, neighbors))}</td>"
                        else:
                            html += "<td></td><td></td><td></td>"
                    html += "</tr>"
                html += "</table>"
                return html
            else:
                # Other strategies return a single string
                recommendations = strategy_func()

            logger.debug(f"show_strategy_recommendations: Raw strategy output for {strategy_name} = '{recommendations}'")

            # --- Quick Bet Card: prepend a bold top-recommendation card ---
            def _build_quick_bet_card(raw_text, strat_name):
                """Extract the first meaningful bet line and render it as a prominent card."""
                if not raw_text or not str(raw_text).strip():
                    return ""
                lines = [l.strip() for l in str(raw_text).split("\n") if l.strip()]
                # Find first line that looks like a bet recommendation (contains 'Bet', a number name, or →)
                top_line = ""
                for l in lines:
                    if any(kw in l for kw in ["Bet:", "Bet ", "→", "Play:", "Target:", "Best:", "1.", "#1", "Top:"]):
                        top_line = l; break
                if not top_line and lines:
                    top_line = lines[0]
                # Truncate to 80 chars for card
                if len(top_line) > 80:
                    top_line = top_line[:77] + "…"
                return f'''<div style="margin-bottom:12px; padding:12px 16px;
                                background:linear-gradient(135deg,#1a237e,#283593);
                                border-radius:12px; border-left:5px solid #FFD700;
                                box-shadow:0 3px 10px rgba(0,0,0,0.25); color:#fff;">
                    <div style="font-size:10px; text-transform:uppercase; letter-spacing:1px;
                                color:rgba(255,255,255,0.6); margin-bottom:4px; font-weight:700;">
                        ⚡ TOP BET — {strat_name}
                    </div>
                    <div style="font-size:16px; font-weight:900; color:#FFD700;
                                text-shadow:0 1px 4px rgba(0,0,0,0.4); line-height:1.3;">
                        {top_line}
                    </div>
                </div>'''

            # If the output is already HTML (e.g., for "Top Numbers with Neighbours (Tiered)"), return it as is
            if strategy_name == "Top Numbers with Neighbours (Tiered)":
                return recommendations
            # Special handling for "Neighbours of Strong Number" to format Suggestions section
            elif strategy_name == "Neighbours of Strong Number":
                lines = recommendations.split("\n")
                html_lines = []
                in_suggestions = False
                for line in lines:
                    if line.strip() == "Suggestions:":
                        in_suggestions = True
                        html_lines.append('<p style="margin: 2px 0; font-weight: bold;">Suggestions:</p>')
                    elif line.strip() == "" and in_suggestions:
                        in_suggestions = False
                        html_lines.append('<p style="margin: 2px 0;"></p>')
                    elif in_suggestions:
                        html_lines.append(f'<p style="margin: 2px 0; padding-left: 10px;">{line}</p>')
                    else:
                        html_lines.append(f'<p style="margin: 2px 0;">{line}</p>')
                _card = _build_quick_bet_card(recommendations, strategy_name)
                return _card + '<div style="font-family: Arial, sans-serif; font-size: 14px;">' + "".join(html_lines) + "</div>"
            # Otherwise, convert plain text to HTML with proper line breaks
            else:
                # Split the output into lines, removing any empty lines
                lines = [line for line in recommendations.split("\n") if line.strip()]
                # Wrap each line in <p> tags and join with <br> for proper spacing
                html_lines = [f"<p style='margin: 2px 0;'>{line}</p>" for line in lines]
                _card = _build_quick_bet_card(recommendations, strategy_name)
                return _card + "<div style='font-family: Arial, sans-serif; font-size: 14px;'>" + "".join(html_lines) + "</div>"

        except Exception as e:
            logger.error(f"show_strategy_recommendations: Error: {str(e)}\n{traceback.format_exc()}")
            return f"<div style='color:#ef4444;padding:8px;'>⚠️ Strategy recommendations error — spins are preserved. ({type(e).__name__}: {str(e)})</div>"

    # Inject all app-level callbacks into the sessions module now that
    # show_strategy_recommendations is defined.
    sessions.init(
        state_obj=state,
        neighbors=current_neighbors,
        update_scores_batch_fn=update_scores_batch,
        update_drought_counters_fn=_update_drought_counters,
        get_file_path_fn=_get_file_path,
        render_sides_of_zero_display_fn=render_sides_of_zero_display,
        update_spin_counter_fn=update_spin_counter,
        create_color_code_table_fn=create_color_code_table,
        create_dynamic_table_fn=create_dynamic_table,
        show_strategy_recommendations_fn=show_strategy_recommendations,
    )

    # Line 3: Start of clear_outputs function (unchanged)
    def clear_outputs():
        return "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""

    # Lines after (context, unchanged)
    def toggle_checkboxes(strategy_name):
        return (gr.update(visible=strategy_name == "Kitchen Martingale"),
                gr.update(visible=strategy_name == "S.T.Y.W: Victory Vortex"))

    def reset_colors():
        """Reset color pickers to default values and update the dynamic table."""
        default_top = "rgba(255, 255, 0, 0.5)"  # Yellow
        default_middle = "rgba(0, 255, 255, 0.5)"  # Cyan
        default_lower = "rgba(0, 255, 0, 0.5)"  # Green
        return default_top, default_middle, default_lower

    # Define state and components used across sections
    spins_display = gr.State(value="")
    # NEW: State to hold pinned numbers for the DE2D table to read
    pinned_numbers_state = gr.State(value=[])
    # Hidden textbox that JS will write to
    hidden_pinned_trigger = gr.Textbox(visible=False, elem_id="hidden_pinned_trigger")
    js_trigger_box = gr.HTML(visible=True, elem_id="js-trigger-box")

    # --- FIX: Dummy States to catch unused text outputs and prevent buffering errors ---
    dummy_dozen_text = gr.State()
    dummy_even_text = gr.State()

    show_trends_state = gr.State(value=True)  # FIX: Default to True so "Hide Trends" button makes sense
    toggle_trends_label = gr.State(value="Hide Trends") 
    analysis_cache = gr.State(value={})  # New: Cache for analysis results
    spins_textbox = gr.Textbox(
        label="Enter Spins",
        value="",
        interactive=True,
        lines=3,
        elem_id="selected-spins"
    )
    
    gr.HTML("""
    <!-- ── Badges row ── -->
    <div id="selected-spins-display"></div>

    <!-- ── Live Streak Tracker ── -->
    <div id="spins-live-stats">
        <!-- Top row: last spin  |  streak pill  |  total count -->
        <div id="spins-stats-top">
            <span id="spins-last-label">LAST</span>
            <span id="spins-last-circle">—</span>
            <span id="spins-streak-pill">—</span>
            <span id="spins-total-badge">0 spins</span>
        </div>
        <!-- Colour ratio bar -->
        <div id="spins-color-bar-wrap">
            <div id="spins-color-bar-track">
                <div id="spins-bar-red"   style="width:0%"></div>
                <div id="spins-bar-black" style="width:0%"></div>
                <div id="spins-bar-green" style="width:0%"></div>
            </div>
            <span id="spins-color-legend">—</span>
        </div>
    </div>

    <!-- ── Validation ── -->
    <div id="selected-spins-validation"></div>

    <script>
    (function () {
        const RC = {
            "0":"green",
            "1":"red","2":"black","3":"red","4":"black","5":"red","6":"black",
            "7":"red","8":"black","9":"red","10":"black","11":"black","12":"red",
            "13":"black","14":"red","15":"black","16":"red","17":"black","18":"red",
            "19":"red","20":"black","21":"red","22":"black","23":"red","24":"black",
            "25":"red","26":"black","27":"red","28":"black","29":"black","30":"red",
            "31":"black","32":"red","33":"black","34":"red","35":"black","36":"red"
        };

        const COLOR_EMOJI  = { red:"🔴", black:"⬛", green:"🟢" };
        const COLOR_BG     = {
            red:   "linear-gradient(145deg,#b91c1c,#ef4444)",
            black: "linear-gradient(145deg,#0f172a,#334155)",
            green: "linear-gradient(145deg,#15803d,#22c55e)"
        };

        function getInput() {
            /* Gradio 5 renders a <textarea>; older versions use <input> */
            return document.querySelector("#selected-spins textarea")
                || document.querySelector("#selected-spins input");
        }

        function update() {
            const input      = getInput();
            const display    = document.querySelector("#selected-spins-display");
            const validation = document.querySelector("#selected-spins-validation");
            const statsBox   = document.querySelector("#spins-live-stats");
            if (!input || !display) return;

            display.innerHTML = "";
            const raw     = input.value.split(",").map(s => s.trim()).filter(s => s !== "");
            let   isValid = true;
            const valid   = [];

            raw.forEach(num => {
                const n = parseInt(num);
                if (isNaN(n) || n < 0 || n > 36) { isValid = false; return; }
                valid.push(String(n));
                const color = RC[String(n)] || "black";
                const badge = document.createElement("span");
                badge.className   = "number-badge " + color;
                badge.textContent = n;
                display.appendChild(badge);
            });

            /* ── Validation message ── */
            if (raw.length === 0) {
                validation.style.display = "none";
            } else if (isValid) {
                validation.className   = "valid";
                validation.textContent = "✓ Valid spins";
                validation.style.display = "block";
            } else {
                validation.className   = "invalid";
                validation.textContent = "⚠ Invalid — use numbers 0–36";
                validation.style.display = "block";
            }

            /* ── Live Streak Tracker (only when there is valid data) ── */
            if (valid.length === 0) {
                statsBox.style.display = "none";
                return;
            }
            statsBox.style.display = "block";

            /* Last spin */
            const lastNum   = valid[valid.length - 1];
            const lastColor = RC[lastNum] || "black";
            const lastCirc  = document.querySelector("#spins-last-circle");
            lastCirc.textContent  = lastNum;
            lastCirc.style.background = COLOR_BG[lastColor] || COLOR_BG.black;

            /* Current colour streak — count backwards from last spin */
            let streakCount = 0;
            const streakColor = RC[valid[valid.length - 1]] || "black";
            for (let i = valid.length - 1; i >= 0; i--) {
                if ((RC[valid[i]] || "black") === streakColor) streakCount++;
                else break;
            }
            const pill = document.querySelector("#spins-streak-pill");
            pill.className   = "spins-streak-pill streak-" + streakColor;
            // inline-flex is set in CSS; just update id attribute
            pill.id          = "spins-streak-pill";
            pill.textContent = `${COLOR_EMOJI[streakColor] || "⬛"} ×${streakCount}  streak`;
            pill.style.background = "";   // let CSS class handle it

            /* Total count badge */
            document.querySelector("#spins-total-badge").textContent =
                valid.length + (valid.length === 1 ? " spin" : " spins");

            /* Colour ratio bar */
            const counts = { red: 0, black: 0, green: 0 };
            valid.forEach(n => { const c = RC[n] || "black"; counts[c] = (counts[c] || 0) + 1; });
            const total    = valid.length;
            const pRed     = (counts.red   / total * 100).toFixed(0);
            const pBlack   = (counts.black / total * 100).toFixed(0);
            const pGreen   = (counts.green / total * 100).toFixed(0);

            document.querySelector("#spins-bar-red").style.width   = pRed   + "%";
            document.querySelector("#spins-bar-black").style.width = pBlack + "%";
            document.querySelector("#spins-bar-green").style.width = pGreen + "%";
            document.querySelector("#spins-color-legend").textContent =
                `🔴 ${pRed}%  ⬛ ${pBlack}%  🟢 ${pGreen}%`;
        }

        function attach() {
            const input = getInput();
            if (!input) { setTimeout(attach, 300); return; }

            /* 1. Native typing / paste events */
            input.addEventListener("input", () => {
                input.classList.add("typing");
                update();
            });

            /* 2. Polling — catches Gradio-programmatic updates (roulette button clicks,
                   load-session, undo, generate-random, etc.) that bypass native events */
            let _last = input.value;
            setInterval(() => {
                const el = getInput();
                if (el && el.value !== _last) {
                    _last = el.value;
                    update();
                }
            }, 250);

            /* 3. MutationObserver — handles Gradio replacing the element entirely */
            new MutationObserver(() => {
                const fresh = getInput();
                if (fresh && fresh !== input) {
                    fresh.addEventListener("input", () => { fresh.classList.add("typing"); update(); });
                    update();
                }
            }).observe(document.querySelector("#selected-spins") || document.body,
                       { childList: true, subtree: true });

            update();
        }

        if (document.readyState === "loading")
            document.addEventListener("DOMContentLoaded", attach);
        else
            attach();
    })();
    </script>
    """)
    with gr.Accordion("Dealer’s Spin Tracker (Can you spot Bias???) 🕵️", open=False, elem_id="sides-of-zero-accordion"):
        sides_of_zero_display = gr.HTML(
            label="Sides of Zero",
            value="",  # populated on page load by _on_page_load
            elem_classes=["sides-of-zero-container"]
        )

    # Start of updated section
    with gr.Accordion("Hit Percentage Overview 📊", open=False, elem_id="hit-percentage-overview"):
        gr.HTML("""
        <style>
            #hit-percentage-overview {
                background-color: #f3e5f5 !important;
                border: 2px solid #8e24aa !important;
                border-radius: 8px !important;
                padding: 12px !important;
                margin-bottom: 15px !important;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15) !important;
                animation: fadeInAccordion 0.5s ease-in-out !important;
            }
    
            @keyframes fadeInAccordion {
                0% { opacity: 0; transform: translateY(5px); }
                100% { opacity: 1; transform: translateY(0); }
            }
    
            #hit-percentage-overview summary {
                background-color: #8e24aa !important;
                color: white !important;
                padding: 12px !important;
                border-radius: 6px !important;
                font-weight: bold !important;
                font-size: 18px !important;
                cursor: pointer !important;
                transition: background-color 0.3s ease !important;
            }
    
            #hit-percentage-overview summary:hover {
                background-color: #6a1b9a !important;
            }
    
            #hit-percentage-overview summary::after {
                filter: invert(100%) !important;
            }
    
            .hit-percentage-row {
                background-color: #f3e5f5 !important;
                padding: 10px !important;
                border-radius: 6px !important;
                display: flex !important;
                flex-wrap: wrap !important;
                gap: 15px !important;
                align-items: stretch !important;
                margin-top: 10px !important;
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1) !important;
                width: 100% !important;
                min-height: fit-content !important;
                height: auto !important;
                box-sizing: border-box !important;
            }
    
            .hit-percentage-row .gr-column {
                flex: 1 !important;
                min-width: 300px !important;
                background-color: transparent !important;
                padding: 10px !important;
            }
    
            #hit-percentage-overview .hit-percentage-container {
                background: transparent !important;
                border: none !important;
                border-radius: 0 !important;
                padding: 0 !important;
                max-height: none !important;
                overflow-y: visible !important;
                width: 100% !important;
                box-sizing: border-box !important;
                position: static !important;
                box-shadow: none !important;
                animation: none !important;
            }
    
            #hit-percentage-overview .hit-percentage-container::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: radial-gradient(circle, rgba(142, 36, 170, 0.15) 0%, transparent 70%) !important;
                opacity: 0.4;
                pointer-events: none;
            }
    
            #hit-percentage-overview .hit-percentage-container .hit-percentage-overview {
                display: flex !important;
                flex-wrap: wrap !important;
                gap: 20px !important;
                width: 100% !important;
                justify-content: space-between !important;
                background: none !important;
                border: none !important;
                padding: 0 !important;
            }
    
            #hit-percentage-overview .hit-percentage-container .percentage-wrapper {
                width: 100% !important;
                max-width: 100% !important;
                box-sizing: border-box !important;
                padding-top: 15px !important;
                background: none !important;
                border: none !important;
                padding: 0 !important;
            }
    
            #hit-percentage-overview .hit-percentage-container .percentage-group {
                margin: 10px 0 !important;
                padding-top: 15px !important;
                flex: 1 1 200px !important;
                min-width: 200px !important;
                max-width: 100% !important;
                background: none !important;
                border: none !important;
                padding: 0 !important;
                box-shadow: none !important;
                overflow: visible !important;
            }
    
            #hit-percentage-overview .hit-percentage-container .percentage-group h4 {
                margin: 5px 0 !important;
                color: #ab47bc !important;
                text-shadow: 0 0 5px rgba(142, 36, 170, 0.5) !important;
                font-size: 18px !important;
                font-weight: bold !important;
            }
    
            #hit-percentage-overview .hit-percentage-container .percentage-badges {
                display: flex !important;
                flex-wrap: wrap !important;
                gap: 10px !important;
                align-items: center !important;
                padding: 5px 0 !important;
                width: 100% !important;
                background: none !important;
                border: none !important;
                overflow-x: hidden !important;
            }
    
            #hit-percentage-overview .hit-percentage-container .percentage-item {
                flex: 0 1 auto !important;
                min-width: 100px !important;
                max-width: 150px !important;
                box-sizing: border-box !important;
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
                background: transparent !important;
                color: #333 !important;
                padding: 6px 14px !important;
                border-radius: 15px !important;
                font-size: 12px !important;
                margin: 5px 3px !important;
                transition: transform 0.2s, box-shadow 0.3s, filter 0.3s !important;
                cursor: pointer !important;
                border: 1px solid transparent !important;
                box-shadow: 0 0 10px rgba(142, 36, 170, 0.3) !important;
                font-weight: bold !important;
                display: inline-block !important;
            }
    
            #hit-percentage-overview .hit-percentage-container .percentage-item:hover {
                transform: scale(1.15) !important;
                filter: brightness(1.4) !important;
            }
    
            #hit-percentage-overview .hit-percentage-container .percentage-item.even-money {
                background: rgba(255, 99, 71, 0.2) !important;
                border-color: #ff6347 !important;
                box-shadow: 0 0 12px rgba(255, 99, 71, 0.5) !important;
            }
    
            #hit-percentage-overview .hit-percentage-container .percentage-item.column {
                background: rgba(100, 149, 237, 0.2) !important;
                border-color: #6495ed !important;
                box-shadow: 0 0 12px rgba(100, 149, 237, 0.5) !important;
            }
    
            #hit-percentage-overview .hit-percentage-container .percentage-item.dozen {
                background: rgba(50, 205, 50, 0.2) !important;
                border-color: #32cd32 !important;
                box-shadow: 0 0 12px rgba(50, 205, 50, 0.5) !important;
            }
    
            #hit-percentage-overview .hit-percentage-container .percentage-item.winner {
                font-weight: bold !important;
                color: #333 !important;
                border: 2px solid #ffcc00 !important;
                box-shadow: 0 0 15px #ffcc00 !important;
                background: rgba(255, 204, 0, 0.4) !important;
                transform: scale(1.15) !important;
            }
    
            #hit-percentage-overview .hit-percentage-container .percentage-with-bar {
                display: inline-block !important;
                text-align: center !important;
                margin: 0 3px !important;
                margin-bottom: 8px !important;
            }
    
            @media (max-width: 768px) {
                .hit-percentage-row {
                    flex-direction: column !important;
                    gap: 10px !important;
                }
                .hit-percentage-row .gr-column {
                    min-width: 100% !important;
                }
                #hit-percentage-overview {
                    padding: 8px !important;
                }
                #hit-percentage-overview summary {
                    font-size: 16px !important;
                }
                #hit-percentage-overview .hit-percentage-container .percentage-group {
                    min-width: 100% !important;
                    max-width: 100% !important;
                }
                #hit-percentage-overview .hit-percentage-container .percentage-item {
                    min-width: 80px !important;
                    max-width: 120px !important;
                    font-size: 10px !important;
                    padding: 4px 8px !important;
                }
            }
    
            @media (max-width: 600px) {
                #hit-percentage-overview .hit-percentage-container .percentage-badges {
                    flex-wrap: wrap !important;
                    overflow-x: visible !important;
                }
            }
        </style>
        """)
        with gr.Row(elem_classes=["hit-percentage-row"]):
            with gr.Column(scale=1):
                hit_percentage_display = gr.HTML(
                    label="Hit Percentages",
                    value="",  # populated on page load by _on_page_load
                    elem_classes=["hit-percentage-container"]
                )
    with gr.Accordion("SpinTrend Radar 🌀", open=False, elem_id="spin-trend-radar"):
        gr.HTML("""
        <style>
            #spin-trend-radar {
                background-color: #f3e5f5 !important;
                border: 2px solid #8e24aa !important;
                border-radius: 8px !important;
                padding: 12px !important;
                margin-bottom: 15px !important;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15) !important;
                animation: fadeInAccordion 0.5s ease-in-out !important;
            }
    
            @keyframes fadeInAccordion {
                0% { opacity: 0; transform: translateY(5px); }
                100% { opacity: 1; transform: translateY(0); }
            }
    
            #spin-trend-radar summary {
                background-color: #8e24aa !important;
                color: white !important;
                padding: 12px !important;
                border-radius: 6px !important;
                font-weight: bold !important;
                font-size: 18px !important;
                cursor: pointer !important;
                transition: background-color 0.3s ease !important;
            }
    
            #spin-trend-radar summary:hover {
                background-color: #6a1b9a !important;
            }
    
            #spin-trend-radar summary::after {
                filter: invert(100%) !important;
            }
    
            .spin-trend-row {
                background-color: #f3e5f5 !important;
                padding: 10px !important;
                border-radius: 6px !important;
                display: flex !important;
                flex-wrap: wrap !important;
                gap: 15px !important;
                align-items: stretch !important;
                margin-top: 10px !important;
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1) !important;
                width: 100% !important;
                min-height: fit-content !important;
                height: auto !important;
                box-sizing: border-box !important;
            }
    
            .spin-trend-row .gr-column {
                flex: 1 !important;
                min-width: 300px !important;
                background-color: transparent !important;
                padding: 10px !important;
            }
    
            #spin-trend-radar .traits-container {
                background: transparent !important;
                border: none !important;
                border-radius: 0 !important;
                padding: 0 !important;
                max-height: none !important;
                overflow-y: visible !important;
                width: 100% !important;
                box-sizing: border-box !important;
                position: static !important;
                box-shadow: none !important;
                animation: none !important;
            }
    
            #spin-trend-radar .traits-container::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: radial-gradient(circle, rgba(142, 36, 170, 0.1) 0%, transparent 70%) !important;
                opacity: 0.3;
                pointer-events: none;
            }
    
            #spin-trend-radar .traits-container .traits-wrapper {
                width: 100% !important;
                max-width: 100% !important;
                box-sizing: border-box !important;
                display: flex !important;
                flex-wrap: wrap !important;
                gap: 15px !important;
                padding-top: 10px !important;
            }
    
            #spin-trend-radar .traits-container .traits-overview > h4 {
                color: #ab47bc !important;
                text-shadow: 0 0 8px rgba(142, 36, 170, 0.7) !important;
                font-size: 18px !important;
                font-weight: bold !important;
                margin: 0 0 10px 0 !important;
            }
    
            #spin-trend-radar .traits-container .badge-group {
                margin: 10px 0 !important;
                padding-top: 10px !important;
                flex: 1 1 200px !important;
                min-width: 200px !important;
                max-width: 100% !important;
                overflow: visible !important;
            }
    
            #spin-trend-radar .traits-container .badge-group:nth-child(1) h4 { color: #ff4d4d !important; }
            #spin-trend-radar .traits-container .badge-group:nth-child(2) h4 { color: #4d79ff !important; }
            #spin-trend-radar .traits-container .badge-group:nth-child(3) h4 { color: #4dff4d !important; }
            #spin-trend-radar .traits-container .badge-group:nth-child(4) h4 { color: #ffd700 !important; }
    
            #spin-trend-radar .traits-container .percentage-badges {
                display: flex !important;
                flex-wrap: wrap !important;
                gap: 8px !important;
                align-items: center !important;
                padding: 5px 0 !important;
                width: 100% !important;
                overflow-x: hidden !important;
            }
    
            #spin-trend-radar .traits-container .trait-badge {
                background: transparent !important;
                color: #333 !important;
                padding: 5px 12px !important;
                border-radius: 15px !important;
                font-size: 12px !important;
                margin: 5px 3px !important;
                transition: transform 0.2s, box-shadow 0.3s, filter 0.3s !important;
                cursor: pointer !important;
                border: 1px solid transparent !important;
                box-shadow: 0 0 8px rgba(142, 36, 170, 0.2) !important;
                font-weight: bold !important;
                display: inline-block !important;
            }
    
            #spin-trend-radar .traits-container .trait-badge:hover {
                transform: scale(1.1) !important;
                filter: brightness(1.3) !important;
            }
    
            #spin-trend-radar .traits-container .trait-badge.even-money {
                background: rgba(255, 77, 77, 0.2) !important;
                border-color: #ff4d4d !important;
                box-shadow: 0 0 10px rgba(255, 77, 77, 0.5) !important;
            }
    
            #spin-trend-radar .traits-container .trait-badge.column {
                background: rgba(77, 121, 255, 0.2) !important;
                border-color: #4d79ff !important;
                box-shadow: 0 0 10px rgba(77, 121, 255, 0.5) !important;
            }
    
            #spin-trend-radar .traits-container .trait-badge.dozen {
                background: rgba(77, 255, 77, 0.2) !important;
                border-color: #4dff4d !important;
                box-shadow: 0 0 10px rgba(77, 255, 77, 0.5) !important;
            }
    
            #spin-trend-radar .traits-container .trait-badge.repeat {
                background: rgba(204, 51, 255, 0.2) !important;
                border-color: #ab47bc !important;
                box-shadow: 0 0 10px rgba(142, 36, 170, 0.5) !important;
            }
    
            #spin-trend-radar .traits-container .trait-badge.winner {
                font-weight: bold !important;
                color: #333 !important;
                border: 2px solid #ffd700 !important;
                box-shadow: 0 0 12px #ffd700 !important;
                background: rgba(255, 215, 0, 0.3) !important;
                transform: scale(1.1) !important;
            }
    
            @media (max-width: 768px) {
                .spin-trend-row {
                    flex-direction: column !important;
                    gap: 10px !important;
                }
                .spin-trend-row .gr-column {
                    min-width: 100% !important;
                }
                #spin-trend-radar {
                    padding: 8px !important;
                }
                #spin-trend-radar summary {
                    font-size: 16px !important;
                }
                #spin-trend-radar .traits-container .badge-group {
                    min-width: 100% !important;
                    max-width: 100% !important;
                }
                #spin-trend-radar .traits-container .trait-badge {
                    min-width: 80px !important;
                    max-width: 120px !important;
                    font-size: 10px !important;
                    padding: 4px 8px !important;
                }
            }
        </style>
        """)
        with gr.Row(elem_classes=["spin-trend-row"]):
            with gr.Column(scale=1):
                traits_display = gr.HTML(
                    label="Spin Traits",
                    value="",  # populated on page load by _on_page_load
                    elem_classes=["traits-container"]
                )
                
    
    # NEW SECTION: DE2D ZONE (Dynamic Master + 8 Triggers)
    # ---------------------------------------------------------
    with gr.Accordion("DE2D ZONE 💀 (Dynamic Master)", open=False, elem_id="de2d-tracker-accordion"):
        gr.HTML("""
        <style>
            #de2d-tracker-accordion {
                background-color: #ffebee !important; 
                border: 2px solid #d32f2f !important; 
                border-radius: 8px !important;
                padding: 12px !important;
                margin-bottom: 15px !important;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15) !important;
            }
            #de2d-tracker-accordion summary {
                background-color: #d32f2f !important; 
                color: white !important;
                padding: 12px !important;
                border-radius: 6px !important;
                font-weight: bold !important;
                font-size: 18px !important;
            }
            #de2d-tracker-accordion summary:hover {
                background-color: #b71c1c !important; 
            }
            .de2d-output-box {
                background-color: white !important;
                padding: 15px;
                border-radius: 6px;
                border: 1px solid #ffcdd2;
                color-scheme: light !important;
            }
            .de2d-controls {
                background-color: #fff !important;
                padding: 10px;
                border-radius: 6px;
                margin-bottom: 15px;
                border: 1px solid #e0e0e0;
            }
            .cheat-sheet {
                background-color: #fff3e0;
                border-left: 4px solid #ff9800;
                padding: 10px;
                margin-bottom: 15px;
                font-size: 12px;
                color: #333;
                border-radius: 4px;
                font-family: monospace; 
            }
            .cheat-sheet h5 {
                margin: 0 0 5px 0;
                color: #e65100;
                font-weight: bold;
                text-transform: uppercase;
                font-size: 12px;
            }
            .cheat-sheet ul {
                margin: 0;
                padding-left: 20px;
                list-style-type: square;
            }
            .cheat-sheet li {
                margin-bottom: 3px;
                line-height: 1.4;
            }
            .prob-tag {
                color: #d32f2f;
                font-weight: bold;
                background: #fff;
                padding: 0 3px;
                border-radius: 3px;
                font-size: 10px;
                margin-left: 2px;
            }
            #stat-intel-accordion {
                background-color: #0a0f1a !important;
                border: 2px solid #4338ca !important;
                border-radius: 8px !important;
                padding: 10px !important;
                margin-top: 10px !important;
            }
            #stat-intel-accordion summary {
                background: linear-gradient(145deg, #1e1b4b, #312e81) !important;
                color: #a5b4fc !important;
                padding: 10px !important;
                border-radius: 6px !important;
                font-weight: bold !important;
                font-size: 16px !important;
            }
        </style>
        
        <div class="cheat-sheet">
            <h5>Strategy Settings Reference 📝</h5>
            <ul>
                <li>
                    <b>Quick Strike:</b> 
                    Dozen(6S) / Even(4S) / Streak(5H) / Voisins(5S) / TiersOrph(6S) / Sides(5S)
                </li>
                <li>
                    <b>Balanced:</b> 
                    Dozen(7S) / Even(5S) / Streak(6H) / Voisins(6S) / TiersOrph(7S) / Sides(6S)
                </li>
                <li>
                    <b>Pro-Max:</b> 
                    Dozen(8S) / Even(6S) / Streak(6H) / Voisins(7S) / TiersOrph(7S) / Sides(6S)
                </li>
                <li>
                    <b>Super Pro-Max:</b> 
                    Dozen(9S) / Even(7S) / Streak(7H) / Voisins(8S) / TiersOrph(8S) / Sides(7S)
                </li>
            </ul>
        </div>
        """)
        
        # Controls for Dynamic Configuration
        with gr.Row(elem_classes=["de2d-controls"]):
            with gr.Column():
                with gr.Row():
                    btn_minus_all = gr.Button("➖ Minus", size="sm", variant="secondary")
                    btn_default_all = gr.Button("🔄 Default", size="sm", variant="secondary")
                    btn_plus_all = gr.Button("➕ Plus", size="sm", variant="secondary")
                with gr.Row():
                    btn_min_all = gr.Button("⬇️ Min All Sliders", size="sm", variant="secondary")
                    btn_max_all = gr.Button("⬆️ Max All Sliders", size="sm", variant="secondary")
            with gr.Column():
                miss_slider = gr.Slider(label="Missing Dozen/Col (Wait)", minimum=2, maximum=20, value=14, step=1)
                even_slider = gr.Slider(label="Even Money (Wait)", minimum=4, maximum=30, value=8, step=1)
            with gr.Column():
                streak_slider = gr.Slider(label="Streak (Wait Hits)", minimum=2, maximum=10, value=9, step=1)
                pattern_slider = gr.Slider(label="Pattern Match (X)", minimum=3, maximum=8, value=6, step=1)
            with gr.Column():
                voisins_slider = gr.Slider(label="Voisins Missing (Wait)", minimum=3, maximum=15, value=10, step=1)
                tiers_slider = gr.Slider(label="Tiers+Orph Missing (Wait)", minimum=2, maximum=15, value=9, step=1)
            with gr.Column():
                left_side_slider = gr.Slider(label="Left Side Missing (Wait)", minimum=2, maximum=12, value=8, step=1)
                right_side_slider = gr.Slider(label="Right Side Missing (Wait)", minimum=2, maximum=12, value=8, step=1)
            with gr.Column():
                ds_strategy_slider = gr.Slider(label="5 Double Street Strategy (Wait Streak)", minimum=1, maximum=10, value=8, step=1)
                d17_strategy_slider = gr.Slider(label="Dynamic 17-Assault (Wait Misses)", minimum=3, maximum=15, value=9, step=1)
                corner_strategy_slider = gr.Slider(label="5-Corner Stress Shuffle (Wait Misses)", minimum=1, maximum=15, value=9, step=1)
                non_repeater_slider = gr.Slider(label="Non-Repeaters (Last Spins)", minimum=4, maximum=100, value=18, step=1)
                nr_target_slider = gr.Slider(label="Non-Repeaters (Target Alert)", minimum=1, maximum=36, value=12, step=1)
            
            with gr.Column():
                # UPDATED: Max increased to 19 to allow 19-19 Start
                x19_start_slider = gr.Slider(label="X-19 Start Count (X)", minimum=10, maximum=19, value=15, step=1)
                x19_active_checkbox = gr.Checkbox(label="X-19 Strategy", value=False, interactive=True)
                sniper_trigger_slider = gr.Slider(label="🎯 Sniper S65+C19 (No Trigger)", minimum=5, maximum=50, value=22, step=1, interactive=False)

            # --- FIXED COLUMN: REMOVED DUPLICATES ---
            with gr.Column():
                gr.Markdown("#### 🛡️ Active Strategy Controllers")
                with gr.Row():
                    grind_active_checkbox = gr.Checkbox(label="Grind Tracker", value=False, interactive=True)
                    ramp_active_checkbox = gr.Checkbox(label="4-12 Ramp", value=False, interactive=True)
                
                grind_target_dropdown = gr.Dropdown(
                    label="Grind Target", 
                    choices=["Auto (Hottest D/C)", "1st Dozen", "2nd Dozen", "3rd Dozen", "1st Column", "2nd Column", "3rd Column"], 
                    value="3rd Dozen", 
                    interactive=True
                )
                with gr.Row():
                    reset_grind_button = gr.Button("Reset Grind", size="sm", elem_classes=["action-button"])
                    reset_ramp_button = gr.Button("Reset Ramp", size="sm", elem_classes=["action-button"])

        # --- 🔥 TREND REVERSAL SLIDERS (Mode 1 – conservative defaults) ---
        with gr.Row(elem_classes=["de2d-controls"]):
            gr.Markdown("#### 🔥 Trend Reversal (Overheated) Configuration")
            with gr.Column():
                tr_short_window_slider = gr.Slider(
                    label="TR: Overheat Short Window",
                    minimum=6, maximum=15, value=10, step=1,
                    info="Rolling window size for the short-term dominance check (unchanged from original)"
                )
                tr_short_hits_slider = gr.Slider(
                    label="TR: Overheat Short Hits (≥)",
                    minimum=5, maximum=10, value=8, step=1,
                    info="Hits needed in short window. Mode 1 raised to 8/10 (80%) from original 7/10 (70%) — fewer, more confident signals"
                )
            with gr.Column():
                tr_long_window_slider = gr.Slider(
                    label="TR: Overheat Long Window",
                    minimum=10, maximum=20, value=15, step=1,
                    info="Rolling window size for the long-term dominance check (unchanged from original)"
                )
                tr_long_hits_slider = gr.Slider(
                    label="TR: Overheat Long Hits (≥)",
                    minimum=5, maximum=15, value=9, step=1,
                    info="Hits needed in long window. Mode 1 raised to 9/15 (60%) from original 8/15 (~53%) — filters out weaker trends"
                )
            with gr.Column():
                tr_min_streak_slider = gr.Slider(
                    label="TR: Min Streak (intensity A)",
                    minimum=2, maximum=10, value=5, step=1,
                    info="Consecutive target hits to satisfy intensity (zeros skipped). Mode 1 raised to 5 from original 4 — requires stronger momentum"
                )
                tr_density_window_slider = gr.Slider(
                    label="TR: Density Window",
                    minimum=4, maximum=12, value=8, step=1,
                    info="Tight window used for density (cluster) check (unchanged from original)"
                )
            with gr.Column():
                tr_density_hits_slider = gr.Slider(
                    label="TR: Density Hits (≥, intensity B)",
                    minimum=3, maximum=8, value=7, step=1,
                    info="Hits in density window to satisfy intensity. Mode 1 raised to 7/8 (87.5%) from original 6/8 (75%) — tighter cluster required"
                )
                tr_active_lifetime_slider = gr.Slider(
                    label="TR: Active Lifetime After Snap",
                    minimum=5, maximum=20, value=11, step=1,
                    info="Max spins the ACTIVE signal stays alive after the snap (unchanged from original)"
                )

        # --- NEW: HUD VISIBILITY FILTERS ---
        with gr.Row(elem_classes=["de2d-controls"]):
            with gr.Column():
                hud_visibility_filters = gr.CheckboxGroup(
                    label="🎛️ HUD Action Card Visibility (Uncheck to hide specific alert cards from your dashboard)",
                    choices=_HUD_ALL_CHOICES,
                    value=_HUD_DEFAULT_VISIBLE,
                    interactive=True
                )
                with gr.Row():
                    btn_hud_check_all = gr.Button("✅ Check All", size="sm", variant="secondary")
                    btn_hud_uncheck_all = gr.Button("❌ Uncheck All", size="sm", variant="secondary")

        # Initial Logic Call (Added 5, 5 as default for Sides)
        de2d_output = gr.HTML(
            value="",  # populated on page load by _on_page_load
            elem_classes=["de2d-output-box"],
            label="DE2D Alerts"
        )

        # --- Statistical Intelligence Layer ---
        with gr.Accordion("🧠 Statistical Intelligence Layer", open=False, elem_id="stat-intel-accordion"):
            smart_decision_output = gr.HTML(
                value="",  # populated on page load by _on_page_load
                label="Smart Decision Summary"
            )
            with gr.Row():
                with gr.Column(scale=1):
                    sigma_analysis_output = gr.HTML(
                        value="",  # populated on page load by _on_page_load
                        label="Sigma Analysis"
                    )
                with gr.Column(scale=1):
                    drought_table_output = gr.HTML(
                        value="",  # populated on page load by _on_page_load
                        label="Drought Counter"
                    )

    
    # --- Final Brain: collapsible live decision engine (collapsed by default) ---
    with gr.Accordion("🧠 WheelPulse Pro Max's Recommendation", open=False, elem_id="brain-accordion"):
        final_brain_output = gr.HTML(
            value="",  # populated on page load by _populate_deferred_outputs (.then() chain)
            elem_id="final-brain-output"
        )

    with gr.Row():
        with gr.Column():
            last_spin_display = gr.HTML(
                label="Last Spins",
                value='<h4>Last Spins</h4><p>No spins yet.</p>',
                elem_classes=["last-spins-container"]
            )
            last_spin_count = gr.Slider(
                label="📊 Display Last N Spins",
                minimum=1,
                maximum=36,
                step=1,
                value=36,
                interactive=True,
                elem_classes="long-slider"
            )
    
    # Updated CSS and Debounce Script for Last Spins
    gr.HTML("""
    <style>
        .last-spins-container {
            background-color: #f5f5f5 !important;
            border: 1px solid #d3d3d3 !important;
            padding: 10px !important;
            border-radius: 5px !important;
            margin-top: 10px !important;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1) !important;
            min-height: 100px !important; /* Fixed minimum height to prevent jitter */
            max-height: 150px !important; /* Maximum height with scrollbar */
            overflow-y: auto !important; /* Scrollable content */
            display: flex !important;
            flex-direction: column !important;
            gap: 5px !important;
        }
        .last-spins-container h4 {
            margin: 0 0 5px 0 !important;
            font-size: 16px !important;
            color: #333 !important;
        }
        .last-spins-container .spins-wrapper {
            display: flex !important;
            flex-wrap: wrap !important;
            gap: 5px !important;
            align-items: center !important;
        }
        .last-spins-container .new-spin {
            position: relative !important;
            width: 30px !important;
            height: 30px !important;
            border-radius: 15px !important;
            font-size: 14px !important;
            font-weight: bold !important;
            color: #fff !important;
            border: 1px solid #fff !important;
            box-shadow: 0 0 5px rgba(0, 0, 0, 0.2) !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            animation: pulse-highlight 1s ease-in-out !important;
        }
        .last-spins-container .new-spin.spin-red {
            background-color: #ff0000 !important;
            --highlight-color: rgba(255, 0, 0, 0.8) !important;
        }
        .last-spins-container .new-spin.spin-black {
            background-color: #000000 !important;
            --highlight-color: rgba(255, 255, 255, 0.8) !important;
        }
        .last-spins-container .new-spin.spin-green {
            background-color: #008000 !important;
            --highlight-color: rgba(0, 255, 0, 0.8) !important;
        }
        .last-spins-container .flip {
            animation: flip 0.5s ease-in-out !important;
        }
        @keyframes flip {
            0% { transform: rotateY(0deg); }
            100% { transform: rotateY(360deg); }
        }
        @keyframes pulse-highlight {
            0%, 100% { box-shadow: none; }
            50% { box-shadow: 0 0 10px 5px var(--highlight-color); }
        }
        .last-spins-container .switch-alert, .last-spins-container .dozen-shift-indicator {
            margin-top: 5px !important;
            padding: 8px !important;
            background: rgba(255, 255, 255, 0.3) !important;
            border-radius: 6px !important;
            visibility: hidden !important; /* Hidden but reserves space */
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            min-height: 40px !important; /* Fixed height for trends */
        }
        .last-spins-container .switch-alert.visible, .last-spins-container .dozen-shift-indicator.visible {
            visibility: visible !important; /* Show when trends are toggled */
        }
        .last-spins-container .switch-dot {
            width: 14px !important;
            height: 14px !important;
            border-radius: 50% !important;
        }
        .last-spins-container .switch-dot.red { background: #ff4444 !important; }
        .last-spins-container .switch-dot.black { background: #000000 !important; }
        .last-spins-container .switch-dot.green { background: #388e3c !important; }
        .last-spins-container .dozen-badge {
            display: inline-block !important;
            font-size: 12px !important;
            color: #fff !important;
            border-radius: 3px !important;
            padding: 2px 4px !important;
        }
        .last-spins-container .dozen-badge.d1 { background: #388e3c !important; }
        .last-spins-container .dozen-badge.d2 { background: #ff9800 !important; }
        .last-spins-container .dozen-badge.d3 { background: #8e24aa !important; }
        @media (max-width: 600px) {
            .last-spins-container {
                min-height: 80px !important;
                max-height: 120px !important;
            }
            .last-spins-container .new-spin {
                width: 25px !important;
                height: 25px !important;
                font-size: 12px !important;
            }
            .last-spins-container .switch-alert, .last-spins-container .dozen-shift-indicator {
                min-height: 30px !important;
            }
        }
    </style>
    <script>
        // Debounce function to smooth out rapid updates
        function debounce(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        }
    
        // Update spins display with debouncing
        const updateSpinsDisplay = debounce(function() {
            const container = document.querySelector('.last-spins-container');
            if (container) {
                // Trigger reflow only after content is stable
                container.style.display = 'none';
                setTimeout(() => {
                    container.style.display = 'flex';
                }, 0);
            }
        }, 100);
    
        // Observe changes to last-spins-container
        document.addEventListener('DOMContentLoaded', () => {
            const container = document.querySelector('.last-spins-container');
            if (container) {
                const observer = new MutationObserver(() => {
                    updateSpinsDisplay();
                });
                observer.observe(container, { childList: true, subtree: true, characterData: true });
            }
        });
    </script>
    """)

        # 2. Row 2: European Roulette Table
    roulette_buttons = [] # Store buttons to bind events later
    with gr.Group():
        gr.Markdown("### European Roulette Table")
        gr.HTML("""
        <style>
            .section-qs-bar { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:8px; align-items:center; }
            .section-qs-btn {
                cursor:pointer; border:none; border-radius:16px;
                padding:5px 14px; font-size:12px; font-weight:700;
                letter-spacing:0.4px; transition:all 0.2s; user-select:none;
                outline:none;
            }
            .section-qs-btn.voisins   { background:#1565c0; color:#fff; }
            .section-qs-btn.tiers     { background:#6a1b9a; color:#fff; }
            .section-qs-btn.orphelins { background:#4e342e; color:#fff; }
            .section-qs-btn.rightside0{ background:#b71c1c; color:#fff; }
            .section-qs-btn.leftside0 { background:#004d40; color:#fff; }
            .section-qs-btn.jeu0      { background:#1b5e20; color:#fff; }
            .section-qs-btn.active    { box-shadow:0 0 0 3px #FF00FF, 0 0 12px rgba(255,0,255,0.8); transform:scale(1.08); }
            .section-qs-btn:hover     { opacity:0.85; }
            .section-qs-label         { font-size:11px; color:#888; font-style:italic; margin-left:4px; }
            /* Section highlight: thick, high-contrast border + glow + pulse */
            @keyframes section-hl-pulse {
                0%   { box-shadow: 0 0 0 2px #FF00FF, 0 0 8px 3px rgba(255,0,255,0.7), inset 0 0 4px rgba(255,0,255,0.3); }
                50%  { box-shadow: 0 0 0 2px #fff,    0 0 18px 7px rgba(255,0,255,1),   inset 0 0 8px rgba(255,0,255,0.5); }
                100% { box-shadow: 0 0 0 2px #FF00FF, 0 0 8px 3px rgba(255,0,255,0.7), inset 0 0 4px rgba(255,0,255,0.3); }
            }
            button.section-hl {
                outline: 5px solid #FF00FF !important;
                outline-offset: 2px !important;
                border: 2px solid #fff !important;
                filter: brightness(1.45) !important;
                z-index: 5 !important;
                position: relative !important;
                animation: section-hl-pulse 1.1s ease-in-out infinite !important;
            }
        </style>
        <div class="section-qs-bar">
            <span style="font-size:11px;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:0.5px;">Section highlight:</span>
            <button class="section-qs-btn voisins"    onclick="toggleSection('voisins')">🌀 Voisins du Zéro</button>
            <button class="section-qs-btn tiers"      onclick="toggleSection('tiers')">🎯 Tiers du Cylindre</button>
            <button class="section-qs-btn orphelins"  onclick="toggleSection('orphelins')">👻 Orphelins</button>
            <button class="section-qs-btn rightside0" onclick="toggleSection('rightside0')">➡️ Right Side+0</button>
            <button class="section-qs-btn leftside0"  onclick="toggleSection('leftside0')">⬅️ Left Side+0</button>
            <button class="section-qs-btn jeu0"       onclick="toggleSection('jeu0')">0️⃣ Jeu 0</button>
            <button class="section-qs-btn" style="background:#546e7a;color:#fff;" onclick="clearSections()">✕ Clear</button>
            <span class="section-qs-label" id="section-qs-hint">Click a section to highlight its numbers on the table</span>
        </div>
        <script>
        (function() {
            var SECTIONS = {
                voisins:    [0,2,3,4,7,12,15,18,19,21,22,25,26,28,29,32,35],
                tiers:      [5,8,10,11,13,16,23,24,27,30,33,36],
                orphelins:  [1,6,9,14,17,20,31,34],
                rightside0: [0,2,4,6,8,10,11,13,15,17,19,21,23,25,26,27,28,29,30,31,32,33,34,35,36],
                leftside0:  [0,1,3,5,7,9,12,14,16,18,20,22,24,25,26,27,28,29,30,31,32,33,34,35,36],
                jeu0:       [0,3,12,15,26,32,35]
            };
            var _active = null;

            window.toggleSection = function(name) {
                clearHighlights();
                document.querySelectorAll('.section-qs-btn').forEach(function(b){ b.classList.remove('active'); });
                if (_active === name) { _active = null; updateHint(null); return; }
                _active = name;
                var nums = SECTIONS[name] || [];
                document.querySelectorAll('.roulette-button').forEach(function(btn) {
                    var v = (btn.textContent || btn.innerText || '').trim();
                    if (nums.indexOf(parseInt(v, 10)) !== -1) btn.classList.add('section-hl');
                });
                var el = document.querySelector('.section-qs-btn.' + name);
                if (el) el.classList.add('active');
                updateHint(name, nums.length);
            };

            window.clearSections = function() {
                clearHighlights();
                document.querySelectorAll('.section-qs-btn').forEach(function(b){ b.classList.remove('active'); });
                _active = null; updateHint(null);
            };

            function clearHighlights() {
                document.querySelectorAll('.section-hl').forEach(function(el){ el.classList.remove('section-hl'); });
            }

            function updateHint(name, count) {
                var hint = document.getElementById('section-qs-hint');
                if (!hint) return;
                var labels = {voisins:'Voisins du Zéro',tiers:'Tiers du Cylindre',orphelins:'Orphelins',rightside0:'Right Side+0',leftside0:'Left Side+0',jeu0:'Jeu 0'};
                hint.textContent = name ? (labels[name] + ' — ' + count + ' numbers highlighted') : 'Click a section to highlight its numbers on the table';
            }
        })();
        </script>
        """)
        table_layout = [
            ["", "3", "6", "9", "12", "15", "18", "21", "24", "27", "30", "33", "36"],
            ["0", "2", "5", "8", "11", "14", "17", "20", "23", "26", "29", "32", "35"],
            ["", "1", "4", "7", "10", "13", "16", "19", "22", "25", "28", "31", "34"]
        ]
        with gr.Column(elem_classes="roulette-table"):
            for row in table_layout:
                with gr.Row(elem_classes="table-row"):
                    for num in row:
                        if num == "":
                            gr.Button(value=" ", interactive=False, min_width=40, elem_classes="empty-button")
                        else:
                            color = colors.get(str(num), "black")
                            is_selected = int(num) in state.selected_numbers
                            btn_classes = [f"roulette-button", color]
                            if is_selected:
                                btn_classes.append("selected")
                            btn = gr.Button(
                                value=num,
                                min_width=40,
                                elem_classes=btn_classes
                            )
                            # Add to list for delayed binding (fixes NameError)
                            roulette_buttons.append((btn, num))

    # --- Alerts Bar: placed directly under the European Roulette Table ---
    with gr.Row(elem_id="wp-alerts-area-row"):
        alerts_bar_output = gr.HTML(
            value=render_alerts_bar_html(),
            elem_id="alerts-sidebar",
        )
        gr.HTML("""
<button id="wp-mute-btn"
        title="Toggle alert sound"
        onclick="wpToggleMute()"
        style="background:rgba(15,23,42,0.85);
               border:1px solid rgba(255,255,255,0.15);
               color:rgba(255,255,255,0.75);
               cursor:pointer;font-size:16px;
               padding:4px 9px;border-radius:4px;
               line-height:1;flex-shrink:0;
               align-self:center;">🔊</button>
<script>
(function () {
    var isMuted = false;
    var prevTriggers = new Set();
    var audioCtx = null;

    function getCtx() {
        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (audioCtx.state === 'suspended') { audioCtx.resume(); }
        return audioCtx;
    }

    function playTone(freq, dur, vol, t) {
        var ctx = getCtx();
        var osc = ctx.createOscillator();
        var gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.value = freq;
        osc.type = 'sine';
        gain.gain.setValueAtTime(vol, t);
        gain.gain.exponentialRampToValueAtTime(0.001, t + dur);
        osc.start(t);
        osc.stop(t + dur + 0.01);
    }

    function playBeep(count) {
        if (isMuted) return;
        var t = getCtx().currentTime;
        if (count >= 3) {
            playTone(440, 0.15, 0.7, t);
            playTone(440, 0.15, 0.7, t + 0.22);
        } else {
            playTone(440, 0.15, 0.3, t);
        }
    }

    function parseTriggers(bar) {
        var s = new Set();
        bar.querySelectorAll('b').forEach(function (b) {
            var txt = b.textContent.trim();
            if (txt) s.add(txt);
        });
        return s;
    }

    function getActiveCount(bar) {
        var m = bar.textContent.match(/Active:[ ]*([0-9]+)/);  /* jshint ignore:line */
        return m ? parseInt(m[1], 10) : 0;
    }

    function checkAlerts() {
        var bar = document.querySelector('#wp-alerts-bar');
        if (!bar) return;
        var current = parseTriggers(bar);
        var hasNew = false;
        current.forEach(function (t) { if (!prevTriggers.has(t)) hasNew = true; });
        if (hasNew) {
            var count = getActiveCount(bar) || current.size;
            playBeep(count);
        }
        prevTriggers = current;
    }

    window.wpToggleMute = function () {
        isMuted = !isMuted;
        var btn = document.getElementById('wp-mute-btn');
        if (btn) btn.textContent = isMuted ? '🔇' : '🔊';
    };

    var _attachAttempts = 0;
    function attach() {
        var container = document.querySelector('#alerts-sidebar');
        if (!container) {
            if (++_attachAttempts < 20) { setTimeout(attach, 500); }
            return;
        }
        var observer = new MutationObserver(checkAlerts);
        observer.observe(container,
            { childList: true, subtree: true, characterData: true });
        document.addEventListener('click', function () {
            if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', attach);
    } else {
        attach();
    }
})();
</script>
""")

    # STATUS BAR AREA: Spin counter centered
    with gr.Row(elem_id="status-bar-container", variant="compact"):
        spin_counter = gr.HTML(
            label="Total Spins",
            value=update_spin_counter(),
            elem_classes=["spin-counter-box"]
        )

    # Strategy cards area — collapsible accordion below the table so the user
    # can expand it for full strategy detail without scrolling to the DE2D zone.
    with gr.Accordion("📊 Strategy Dashboard", open=False, elem_id="strategy-cards-accordion"):
        # Compact mode selector for the Bet Sizing discipline / Auto-Nudge feature.
        # Sits at the very top of the dashboard so it is always visible when
        # the accordion is open, directly above the Bet Sizing Guide card.
        nudge_mode_radio = gr.Radio(
            choices=["MANUAL", "SUGGEST", "AUTO"],
            value="MANUAL",
            label="🎯 Bet Sizing Discipline Mode",
            info=(
                "MANUAL — no changes (default). "
                "SUGGEST — show per-target recommendations in the Bet Sizing Guide. "
                "AUTO — also apply bounded ±1 threshold adjustments behind the scenes."
            ),
            elem_id="nudge-mode-radio",
        )
        # Cards render first (above Master Information) so opportunities are
        # immediately visible when the dashboard is opened.
        strategy_cards_area = gr.HTML(
            value="",  # populated on page load by _on_page_load
            elem_id="strategy-cards-area"
        )
        # AI Coach — live analysis panel, collapsed by default.
        # Positioned above the Master Information panel so coaching data is
        # easy to find when the dashboard is opened.
        ai_coach_output = gr.HTML(
            value="",  # populated on page load by _on_page_load
            elem_id="ai-coach-prompt-panel-wrapper"
        )
        # Persistent sessionStorage script — survives Gradio HTML re-renders.
        # Gradio replaces innerHTML on every update so scripts inside the HTML
        # component don't re-execute.  This separate, stable component sets up
        # a MutationObserver that watches the wrapper and re-applies open/close
        # states every time Gradio pushes new coach content.
        gr.HTML("""<script>
(function(){
  function acoRestoreState(){
    var panel = document.getElementById('ai-coach-prompt-panel');
    if(!panel) return;
    var outerD = document.getElementById('ai-coach-outer-details');
    if(outerD){
      if(sessionStorage.getItem('ai_coach_open')==='1') outerD.open=true;
      if(!outerD._acoToggleAttached){
        outerD._acoToggleAttached=true;
        outerD.addEventListener('toggle',function(){
          sessionStorage.setItem('ai_coach_open',outerD.open?'1':'0');
        });
      }
    }
    panel.querySelectorAll('details[data-section-key]').forEach(function(d){
      var k='ai_coach_section_'+d.getAttribute('data-section-key');
      if(sessionStorage.getItem(k)==='1') d.open=true;
      if(!d._acoToggleAttached){
        d._acoToggleAttached=true;
        d.addEventListener('toggle',function(){
          sessionStorage.setItem(k,d.open?'1':'0');
        });
      }
    });
  }
  function acoAttachObserver(){
    var wrapper=document.getElementById('ai-coach-prompt-panel-wrapper');
    if(!wrapper){setTimeout(acoAttachObserver,100);return;}
    acoRestoreState();
    new MutationObserver(function(){setTimeout(acoRestoreState,30);})
      .observe(wrapper,{childList:true,subtree:true});
  }
  if(document.readyState==='loading')
    document.addEventListener('DOMContentLoaded',acoAttachObserver);
  else
    acoAttachObserver();
})();
</script>""")
        # Compact always-visible summary strip showing current best bet at
        # a glance, so the user doesn't need to expand the inner section.
        master_info_summary_output = gr.HTML(
            value="",  # populated on page load by _on_page_load
            elem_id="master-info-summary"
        )
        # Full Master Information detail — collapsed by default.
        with gr.Accordion("🎯 MASTER INFORMATION — LAST MONEY BET", open=False, elem_id="master-info-accordion"):
            master_info_output = gr.HTML(
                value="",  # populated on page load by _on_page_load
                elem_id="master-info-output"
            )


    # 3. Row 3: Last Spins Display and Show Last Spins Slider (already defined above)

    # 4. Row 4: Spin Controls (unchanged)
    with gr.Row():
        with gr.Column(scale=1):
            undo_button = gr.Button("Undo Spins", elem_classes=["action-button"], elem_id="undo-spins-btn")
        with gr.Column(scale=1):
            generate_spins_button = gr.Button("Generate Random Spins", elem_classes=["action-button"])
        with gr.Column(scale=1):
            toggle_trends_button = gr.Button(
                value="Hide Trends",  # Initial string value
                elem_classes=["action-button"],
                elem_id="toggle-trends-btn"
            )
    
    # 5. Row 5: Selected Spins Textbox (Updated to exclude spin_counter)
    with gr.Row(elem_id="selected-spins-row"):
        with gr.Column(scale=1, min_width=0):
            spins_textbox
       
    # Define strategy categories and choices
    strategy_categories = {
        "Trends": ["Cold Bet Strategy", "Hot Bet Strategy", "Best Dozens + Best Even Money Bets + Top Pick 18 Numbers", "Best Columns + Best Even Money Bets + Top Pick 18 Numbers"],
        "Even Money Strategies": ["Best Even Money Bets", "Best Even Money Bet (Till the tie breaks, No Highlighting)", "Best Even Money Bets + Top Pick 18 Numbers", "Fibonacci To Fortune"],
        "Dozen Strategies": ["1 Dozen +1 Column Strategy", "Best Dozens", "Best Single Dozen (Till the tie breaks, No Highlighting)", "Best Dozens + Top Pick 18 Numbers", "Best Dozens + Best Even Money Bets + Top Pick 18 Numbers", "Best Dozens + Best Streets", "Fibonacci Strategy", "Romanowksy Missing Dozen"],
        "Column Strategies": ["1 Dozen +1 Column Strategy", "Best Columns", "Best Column (Till the tie breaks, No Highlighting)", "Best Columns + Top Pick 18 Numbers", "Best Columns + Best Even Money Bets + Top Pick 18 Numbers", "Best Columns + Best Streets"],
        "Street Strategies": ["3-8-6 Rising Martingale", "Best Streets", "Best Columns + Best Streets", "Best Dozens + Best Streets"],
        "Double Street Strategies": ["Best Double Streets", "Non-Overlapping Double Street Strategy"],
        "Corner Strategies": ["Best Corners", "Non-Overlapping Corner Strategy"],
        "Split Strategies": ["Best Splits"],
        "Number Strategies": ["Top Numbers with Neighbours (Tiered)", "Top Pick 18 Numbers without Neighbours"],
        "Neighbours Strategies": ["Neighbours of Strong Number"],
        "Sniper Strategies": ["Sniper: Best Street + Corner"]
    }
    category_choices = ["None"] + sorted(strategy_categories.keys())

    # Define video categories matching strategy categories
    video_categories = {
        "Trends": [],
        "Even Money Strategies": [
            {
                "title": "S.T.Y.W: Zero Jack 2-2-3 Roulette Strategy",
                "link": "https://youtu.be/I_F9Wys3Ww0"
            },
            {
                "title": "S.T.Y.W: Fibonacci to Fortune (My Top Strategy) - Follow The Winner",
                "link": "https://youtu.be/bwa0FUk6Yps"
            },
            {
                "title": "S.T.Y.W: Triple Entry Max Climax Strategy",
                "link": "https://youtu.be/64aq0GEPww0"
            }
        ],
        "Dozen Strategies": [
            {
                "title": "S.T.Y.W: Dynamic Play: 1 Dozen with 4 Streets or 2 Double Streets?",
                "link": "https://youtu.be/8aMHrvuzBGU"
            },
            {
                "title": "S.T.Y.W: Romanowsky Missing Dozen Strategy",
                "link": "https://youtu.be/YbBtum5WVCk"
            },
            {
                "title": "S.T.Y.W: Victory Vortex (Dozen Domination)",
                "link": "https://youtu.be/aKGA_csI9lY"
            },
            {
                "title": "S.T.Y.W: The Overlap Jackpot (4 Streets + 2 Dozens) Strategy",
                "link": "https://youtu.be/rTqdMQk4_I4"
            },
            {
                "title": "S.T.Y.W: Fibonacci to Fortune (My Top Strategy) - Follow The Winner",
                "link": "https://youtu.be/bwa0FUk6Yps"
            },
            {
                "title": "S.T.Y.W: Double Up: Dozen & Street Strategy",
                "link": "https://youtu.be/Hod5gxusAVE"
            },
            {
                "title": "S.T.Y.W: Triple Entry Max Climax Strategy",
                "link": "https://youtu.be/64aq0GEPww0"
            }
        ],
        "Column Strategies": [
            {
                "title": "S.T.Y.W: Zero Jack 2-2-3 Roulette Strategy",
                "link": "https://youtu.be/I_F9Wys3Ww0"
            },
            {
                "title": "S.T.Y.W: Victory Vortex (Dozen Domination)",
                "link": "https://youtu.be/aKGA_csI9lY"
            },
            {
                "title": "S.T.Y.W: Fibonacci to Fortune (My Top Strategy) - Follow The Winner",
                "link": "https://youtu.be/bwa0FUk6Yps"
            }
        ],
        "Street Strategies": [
            {
                "title": "S.T.Y.W: Dynamic Play: 1 Dozen with 4 Streets or 2 Double Streets?",
                "link": "https://youtu.be/8aMHrvuzBGU"
            },
            {
                "title": "S.T.Y.W: 3-8-6 Rising Martingale",
                "link": "https://youtu.be/-ZcEUOTHMzA"
            },
            {
                "title": "S.T.Y.W: The Overlap Jackpot (4 Streets + 2 Dozens) Strategy",
                "link": "https://youtu.be/rTqdMQk4_I4"
            },
            {
                "title": "S.T.Y.W: Double Up: Dozen & Street Strategy",
                "link": "https://youtu.be/Hod5gxusAVE"
            }
        ],
        "Double Street Strategies": [
            {
                "title": "S.T.Y.W: Dynamic Play: 1 Dozen with 4 Streets or 2 Double Streets?",
                "link": "https://youtu.be/8aMHrvuzBGU"
            },
            {
                "title": "S.T.Y.W: The Classic Five Double Street",
                "link": "https://youtu.be/XX7lSDElwWI"
            }
        ],
        "Corner Strategies": [
            {
                "title": "S.T.Y.W: 4-Corners Strategy (Seq:1,1,2,5,8,17,28,50)",
                "link": "https://youtu.be/zw7eUllTDbg"
            }
        ],
       "Split Strategies": [
            {
                "title": "S.T.Y.W: Triple Entry Max Climax Strategy",
                "link": "https://youtu.be/64aq0GEPww0"
            }
        ],
        "Number Strategies": [
            {
                "title": "The Pulse Wheel Strategy (6 Numbers +1 Neighbours)",
                "link": "https://youtu.be/UBajAwUXWS0"
            },
            {
                "title": "Eighteen Strong Numbers with No Neighbours Strategy",
                "link": "https://youtu.be/8Nmbi8KmY9c"
            }
        ],
        "Neighbours Strategies": [
            {
                "title": "The Pulse Wheel Strategy (6 Numbers +1 Neighbours)",
                "link": "https://youtu.be/UBajAwUXWS0"
            },
            {
                "title": "Triad Spin Strategy: 87.53% (Modified Makarov-Biarritz)",
                "link": "https://youtu.be/ADhCvxNiWVc"
            }
        ]
    }
    
    # 6. Row 6: Analyze Spins, Clear Spins, and Clear All Buttons
    with gr.Row():
        with gr.Column(scale=2):
            analyze_button = gr.Button("Analyze Spins", elem_classes=["action-button", "green-btn"], interactive=True)
        with gr.Column(scale=1):
            clear_spins_button = gr.Button("Clear Spins", elem_classes=["clear-spins-btn", "small-btn"])
        with gr.Column(scale=1):
            clear_all_button = gr.Button("Clear All", elem_classes=["clear-spins-btn", "small-btn"])
        with gr.Column(scale=1):
            master_reset_button = gr.Button("🔄 Master Reset", elem_classes=["clear-spins-btn", "small-btn"], variant="stop")

    # 7. Row 7: Dynamic Roulette Table and Strategy Recommendations
    with gr.Row(elem_classes="dynamic-table-strategy-row"):
        # Column for Strategy Recommendations (Left Side)
        with gr.Column(scale=2, min_width=450, elem_classes="strategy-recommendations-container"):
            # NEW: Movement Radar HUD Component
            movement_radar_display = gr.HTML(
                label="Movement Radar", 
                value="",  # populated on page load by _on_page_load 
                elem_id="movement-radar-hud"
            )
            gr.Markdown("### Strategy Recommendations")
            # Wrap the entire section in a div with class "strategy-card"
            with gr.Row(elem_classes="strategy-card"):
                with gr.Column(scale=1):  # Use a single column to stack elements vertically
                    with gr.Row():
                        category_dropdown = gr.Dropdown(
                            label="Select Category",
                            choices=category_choices,
                            value="Even Money Strategies",
                            allow_custom_value=False,
                            elem_id="select-category"
                        )
                        strategy_dropdown = gr.Dropdown(
                            label="Select Strategy",
                            choices=strategy_categories["Even Money Strategies"],
                            value="Best Even Money Bets",
                            allow_custom_value=False,
                            elem_id="strategy-dropdown"
                        )
                    reset_strategy_button = gr.Button("Reset Category & Strategy", elem_classes=["action-button"])
                    
                    tracked_tiers_checkbox = gr.CheckboxGroup(
                        label="🎯 Auto-Pilot Targets (Select Colors to Track)",
                        choices=["Yellow (Top)", "Cyan (Middle)", "Green (Lower)"],
                        value=["Yellow (Top)", "Cyan (Middle)"], 
                        interactive=True
                    )

                    neighbours_count_slider = gr.Slider(
                        label="Number of Neighbors (Left + Right)",
                        minimum=1,
                        maximum=5,
                        step=1,
                        value=1,
                        interactive=True,
                        visible=False,
                        elem_classes="long-slider"
                    )
                    strong_numbers_count_slider = gr.Slider(
                        label="Strong Numbers to Highlight (Neighbours Strategy)",
                        minimum=1,
                        maximum=34,
                        step=1,
                        value=18,
                        interactive=True,
                        visible=False,
                        elem_classes="long-slider"
                    )
                    strategy_output = gr.HTML(
                        label="Strategy Recommendations",
                        value="",  # populated on page load by _on_page_load
                        elem_classes=["strategy-box"]
                    )
        
        # Column for Dynamic Roulette Table (Right Side)
        with gr.Column(scale=4, min_width=700, elem_classes=["dynamic-table-container"]):
            # 1. Dynamic Roulette Table (Now Top)
            gr.Markdown("### Dynamic Roulette Table", elem_id="dynamic-table-heading")
            dynamic_table_output = gr.HTML(
                label="Dynamic Table",
                value="",  # populated on page load by _on_page_load
                elem_classes=["scrollable-table", "large-table"]
            )

    # --- NEW FULL-WIDTH AIDEA ROADMAP SECTION ---
    with gr.Row(elem_classes=["aidea-full-row"]):
        with gr.Column(scale=1):
            # --- MOVED: Dynamic AIDEA Roadmap to Top of Row ---
            with gr.Accordion("Dynamic AIDEA Roadmap 🗺️", open=False, elem_id="aidea-roadmap-container"):
                gr.Markdown("Upload your AIDEA strategy JSON file to track your progression live.")
                with gr.Row():
                    aidea_upload = gr.File(label="Upload AIDEA JSON", file_types=[".json"], scale=2)
                    aidea_unit_dropdown = gr.Dropdown(
                        choices=["1¢ (x1)", "10¢ (x10)", "$1 (x100)"], 
                        value="1¢ (x1)", 
                        label="Unit Size", 
                        scale=1, 
                        interactive=True
                    )
                    aidea_hard_reset = gr.Button("Hard Reset Roadmap", variant="stop", scale=1)
                
                # STATUS BANNER
                aidea_status_banner.render()

                # NATIVE NAVIGATION BUTTONS
                with gr.Row():
                    aidea_prev_btn = gr.Button("⬅️ Prev", scale=1)
                    aidea_toggle_btn = gr.Button("✅ Mark Complete & Next", variant="primary", scale=2)
                    aidea_next_btn = gr.Button("Next ➡️", scale=1)
                
                # AUTO-PILOT TOGGLE
                with gr.Row():
                    aidea_auto_checkbox.render()
                with gr.Row():
                    shield_down_checkbox.render()
                    aggressor_reset_checkbox.render()

                # The visual roadmap
                aidea_roadmap_view.render()
                
                # --- LABOUCHERE AUTO-PILOT ROADMAP ---
            with gr.Accordion("Dynamic Labouchere Auto-Pilot 🗺️", open=True, elem_id="labouchere-roadmap-container") as lab_accordion:
                gr.Markdown("Auto-calculate and track the Labouchere sequence based on your active table targets.")
                with gr.Row():
                    lab_base_bet = gr.Number(label="Base Unit ($)", value=1.0, step=0.1, scale=1)
                    lab_target_profit = gr.Number(label="Target Profit ($)", value=10.0, step=1.0, scale=1)
                    lab_mode_dropdown = gr.Dropdown(label="Strategy Mode", choices=["2 Targets (Dozens/Columns)", "1 Target (Even Money)"], value="2 Targets (Dozens/Columns)", scale=1)
                    lab_split_limit = gr.Number(label="Split Losses Over ($)", value=0.0, step=1.0, scale=1, info="0 = Disabled (Original Labouchere)")
                with gr.Row():
                    lab_start_btn = gr.Button("▶️ Start Session", variant="primary", scale=1)
                    lab_reset_btn = gr.Button("⏹️ Reset", variant="stop", scale=1)

                labouchere_view.render()

            # --- NEW: PINNED STRONG NUMBERS WATCHLIST ---
            gr.HTML("""
                <div id="strong-numbers-watchlist" style="background: #0f172a; border: 2px solid #00FFFF; border-radius: 10px; padding: 12px; margin-top: 15px; box-shadow: 0 4px 20px rgba(0,0,0,0.6);">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                        <h4 style="color: #00FFFF; margin: 0; font-family: sans-serif; font-size: 13px; font-weight: 900; text-transform: uppercase; letter-spacing: 1px;">🎯 Pinned Strong Numbers</h4>
                        <button onclick="clearAllPins('wp_num_pins_v3')" style="background:#ef4444; color:white; border:none; padding:3px 10px; border-radius:4px; font-size:9px; cursor:pointer; font-weight:bold;">CLEAR ALL</button>
                    </div>
                    <div id="pinned-numbers-container" style="display: flex; flex-wrap: wrap; gap: 10px; color: white; min-height: 45px; align-items: center;">
                        <i style="color: #475569; font-size: 12px;">Star a Number from the Strongest Numbers Table to lock it here...</i>
                    </div>
                </div>
                <script>
                    function togglePin(el) {
                        const isNum = el.getAttribute('data-type') === 'number';
                        const storageKey = isNum ? 'wp_num_pins_v3' : 'wp_rank_pins_v3';
                        const id = el.getAttribute('data-id');
                        
                        let list = JSON.parse(localStorage.getItem(storageKey) || '[]');
                        const index = list.indexOf(id);
                        
                        if (index > -1) { list.splice(index, 1); } 
                        else { list.push(id); }
                        
                        localStorage.setItem(storageKey, JSON.stringify(list));
                        fastUpdateWatchlist();
                        
                        // NEW: Direct Bridge to DE2D using Actual Numbers
                        if (isNum) {
                            const bridge = document.querySelector("#hidden_pinned_trigger textarea") || document.querySelector("#hidden_pinned_trigger input");
                            if (bridge) {
                                let pinnedNumbers = [];
                                // Loop through all rows in the Strongest Table
                                document.querySelectorAll('#strongest-numbers-live-table .star-pin').forEach(s => {
                                    // Check if the inner text of the star element is the filled star
                                    if (s.innerHTML === "★") {
                                        const row = s.closest('tr');
                                        // Cell index 2 contains the number badge
                                        const num = row.cells[2].innerText.trim();
                                        if (num) pinnedNumbers.push(num);
                                    }
                                });
                                bridge.value = JSON.stringify(pinnedNumbers);
                                bridge.dispatchEvent(new Event("input", { bubbles: true }));
                            }
                        }
                    }

                    function clearAllPins(key) {
                        localStorage.setItem(key, '[]');
                        fastUpdateWatchlist();
                    }

                    // New: Global reset for all browser-stored pins
                    function masterResetPins() {
                        localStorage.setItem('wp_rank_pins_v3', '[]');
                        localStorage.setItem('wp_num_pins_v3', '[]');
                        fastUpdateWatchlist();
                        console.log("Browser pin storage cleared.");
                    }

                    function fastUpdateWatchlist() {
                        const rankCont = document.getElementById('pinned-container');
                        const numCont = document.getElementById('pinned-numbers-container');
                        if (!rankCont || !numCont) return;

                        const pRanks = JSON.parse(localStorage.getItem('wp_rank_pins_v3') || '[]');
                        const pNums = JSON.parse(localStorage.getItem('wp_num_pins_v3') || '[]');

                        // 1. Sync All Star Highlighting
                        document.querySelectorAll('.star-pin').forEach(star => {
                            const id = star.getAttribute('data-id');
                            const isNum = star.getAttribute('data-type') === 'number';
                            const active = isNum ? pNums.includes(id) : pRanks.includes(id);
                            
                            star.style.setProperty('color', active ? (isNum ? "#00FFFF" : "#FFD700") : "#ccc", 'important');
                            star.innerHTML = active ? "★" : "☆";
                        });

                        // 2. Update Aggregated Ranks (Top Box)
                        rankCont.innerHTML = pRanks.length === 0 ? '<i style="color:#666;font-size:11px;">Star a Rank below...</i>' : '';
                        pRanks.forEach(id => {
                            const el = document.querySelector(`.star-pin[data-id="${id}"]:not([data-type="number"])`);
                            if (!el) return;
                            const row = el.closest('tr');
                            const name = row.querySelector('.live-name-val').innerText;
                            const score = row.querySelector('.live-score-val').innerText;
                            rankCont.innerHTML += `<div style="background:#1e293b;border:1px solid #FFD700;padding:5px 10px;border-radius:8px;display:flex;align-items:center;gap:10px;border-left:4px solid #FFD700;">
                                <div style="display:flex;flex-direction:column;line-height:1.1;">
                                    <span style="color:#94a3b8;font-size:8px;font-weight:bold;text-transform:uppercase;">Ranked Pick</span>
                                    <span style="color:#FFD700;font-size:10px;font-weight:bold;">Hits: ${score}</span>
                                </div>
                                <div style="color:#FFD700;font-weight:900;font-size:24px;">${name}</div>
                            </div>`;
                        });

                        // 3. Update Strong Numbers (Chases the Rank live - Main Number focus)
                        numCont.innerHTML = pNums.length === 0 ? '<i style="color:#666;font-size:11px;">Star a Strong Number below...</i>' : '';
                        pNums.forEach(id => {
                            // Find the star by its Rank ID
                            const el = document.querySelector(`.star-pin[data-id="${id}"][data-type="number"]`);
                            if (!el) return; 
                            
                            const row = el.closest('tr');
                            const rankLabel = row.cells[1].innerText;
                            const num = row.cells[2].innerText.trim();
                            const leftN = row.cells[3].innerText;
                            const rightN = row.cells[4].innerText;
                            const score = row.cells[5].innerText;
                            
                            numCont.innerHTML += `<div style="background:#0f172a; border:2px solid #00FFFF; padding:12px; border-radius:12px; display:flex; flex-direction:column; min-width:180px; box-shadow: 0 0 15px rgba(0,255,255,0.2); position:relative;">
                                <div style="position:absolute; top:8px; right:12px; color:#00FFFF; font-size:14px; font-weight:bold; opacity:0.7;">${rankLabel}</div>
                                
                                <div style="display:flex; flex-direction:column; align-items:center; gap:2px;">
                                    <div style="color:#94a3b8; font-size:10px; font-weight:bold; text-transform:uppercase;">Main Hit</div>
                                    <div style="color:#FFD700; font-weight:900; font-size:42px; line-height:1; text-shadow: 0 0 15px rgba(255,215,0,0.4);">${num}</div>
                                    
                                    <div style="width:100%; border-top:1px solid #334155; margin:8px 0; padding-top:4px; text-align:center;">
                                        <div style="color:#94a3b8; font-size:9px; font-weight:bold; text-transform:uppercase; letter-spacing:1px;">Neighbors</div>
                                        <div style="color:#00FFFF; font-weight:700; font-size:22px; line-height:1;">${leftN} | ${rightN}</div>
                                    </div>
                                    
                                    <div style="color:white; font-size:14px; font-weight:bold; background:rgba(0,255,255,0.1); padding:2px 10px; border-radius:4px;">
                                        Hits: <span style="color:#00FFFF;">${score}</span>
                                    </div>
                                </div>
                            </div>`;
                        });
                    }

                    const wpObserver = new MutationObserver(debounce(() => fastUpdateWatchlist(), 150));
                    wpObserver.observe(document.body, { childList: true, subtree: true });

                    function startFastWatcher() {
                        setInterval(() => fastUpdateWatchlist(), 2000);
                    }
                    startFastWatcher();
                </script>
            """)

    # CSS to ensure full width behavior
    gr.HTML("""
    <style>
        .aidea-full-row {
            width: 100% !important;
            margin-top: 15px !important;
            margin-bottom: 15px !important;
        }
    </style>
    """)
# Line 1: Updated Next Spin Top Pick accordion
    with gr.Accordion("Next Spin Top Pick 🎯", open=False, elem_id="next-spin-top-pick"):
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 🎯 Select Your Top Pick")
                gr.Markdown("Adjust the slider to analyze the last X spins and find the top pick for your next spin. Add spins using the roulette table below or enter them manually.")
                trait_filter = gr.CheckboxGroup(
                    label="Include in Analysis",
                    choices=["Red/Black", "Even/Odd", "Low/High", "Dozens", "Columns", "Wheel Sections", "Neighbors"],
                    value=["Red/Black", "Even/Odd", "Low/High", "Dozens", "Columns", "Wheel Sections", "Neighbors"],
                    interactive=True,
                    elem_id="trait-filter"
                )
                top_pick_spin_count = gr.Slider(
                    label="Number of Spins to Analyze",
                    minimum=1,
                    maximum=36,
                    step=1,
                    value=18,
                    interactive=True,
                    elem_classes="long-slider"
                )
                with gr.Accordion("Adjust Scoring Weights", open=False, elem_id="scoring-weights"):
                    gr.Markdown("#### Customize Scoring Weights")
                    gr.Markdown("Fine-tune how much each factor contributes to the top pick score.")
                    trait_match_weight = gr.Number(
                        label="Trait Match Weight",
                        value=100,
                        minimum=0,
                        maximum=1000,
                        step=1,
                        interactive=True,
                        elem_id="trait-match-weight"
                    )
                    secondary_match_weight = gr.Number(
                        label="Secondary Match Weight",
                        value=10,
                        minimum=0,
                        maximum=1000,
                        step=1,
                        interactive=True,
                        elem_id="secondary-match-weight"
                    )
                    wheel_side_weight = gr.Number(
                        label="Wheel Side Weight",
                        value=5,
                        minimum=0,
                        maximum=1000,
                        step=1,
                        interactive=True,
                        elem_id="wheel-side-weight"
                    )
                    section_weight = gr.Number(
                        label="Wheel Section Weight",
                        value=10,
                        minimum=0,
                        maximum=1000,
                        step=1,
                        interactive=True,
                        elem_id="section-weight"
                    )
                    recency_weight = gr.Number(
                        label="Recency Weight",
                        value=1,
                        minimum=0,
                        maximum=1000,
                        step=1,
                        interactive=True,
                        elem_id="recency-weight"
                    )
                    hit_bonus_weight = gr.Number(
                        label="Hit Bonus Weight",
                        value=5,
                        minimum=0,
                        maximum=1000,
                        step=1,
                        interactive=True,
                        elem_id="hit-bonus-weight"
                    )
                    neighbor_weight = gr.Number(
                        label="Neighbor Boost Weight",
                        value=2,
                        minimum=0,
                        maximum=1000,
                        step=1,
                        interactive=True,
                        elem_id="neighbor-weight"
                    )
                    # NEW: Reset button
                    reset_weights_button = gr.Button("Reset Weights to Default", elem_id="reset-weights")
                top_pick_display = gr.HTML(
                    label="Top Pick",
                    value="",  # populated on page load by _on_page_load
                    elem_classes=["top-pick-container"]
                )
        gr.HTML("""
            <style>
                #next-spin-top-pick {
                    background-color: #e3f2fd !important;
                    border: 2px solid #2196f3 !important;
                    border-radius: 5px !important;
                    padding: 10px !important;
                }
                #next-spin-top-pick .top-pick-container p {
                    font-style: italic;
                    color: #666;
                }
                #next-spin-top-pick .top-pick-container h4 {
                    margin: 10px 0;
                    color: #333;
                }
                #trait-filter {
                    margin-bottom: 10px !important;
                }
                #trait-filter label {
                    font-size: 14px !important;
                    color: #333 !important;
                    font-weight: bold !important;
                }
                #trait-filter .gr-checkbox-group {
                    display: flex !important;
                    flex-wrap: wrap !important;
                    gap: 10px !important;
                }
                #scoring-weights {
                    background-color: #f5faff !important;
                    border: 1px solid #2196f3 !important;
                    border-radius: 5px !important;
                    padding: 8px !important;
                    margin-bottom: 10px !important;
                }
                #scoring-weights .gr-number {
                    margin-bottom: 8px !important;
                }
                #scoring-weights .gr-number label {
                    font-size: 14px !important;
                    color: #333 !important;
                    font-weight: bold !important;
                }
                #scoring-weights .gr-number input {
                    border: 1px solid #2196f3 !important;
                    border-radius: 4px !important;
                    padding: 5px !important;
                    width: 100px !important;
                }
                #reset-weights {
                    background-color: #2196f3 !important;
                    color: #ffffff !important;
                    border-radius: 4px !important;
                    padding: 8px 16px !important;
                    margin-top: 10px !important;
                    cursor: pointer !important;
                }
                #reset-weights:hover {
                    background-color: #1976d2 !important;
                }
            </style>
        """)
# ---------------------------------------------------------
    # 7.1. Row 7.1: Dozen Tracker
    with gr.Row():
        with gr.Column(scale=3):
            with gr.Accordion("Create Dozen/Even Bet Triggers", open=False, elem_id="dozen-tracker"):
                gr.HTML("""
                <style>
                    #dozen-tracker {
                        background-color: #fce4ec !important;
                        border: 2px solid #f06292 !important;
                        border-radius: 8px !important;
                        padding: 12px !important;
                        margin-bottom: 15px !important;
                        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15) !important;
                        animation: fadeInAccordion 0.5s ease-in-out !important;
                    }
    
                    @keyframes fadeInAccordion {
                        0% { opacity: 0; transform: translateY(5px); }
                        100% { opacity: 1; transform: translateY(0); }
                    }
    
                    #dozen-tracker summary {
                        background-color: #f06292 !important;
                        color: white !important;
                        padding: 12px !important;
                        border-radius: 6px !important;
                        font-weight: bold !important;
                        font-size: 18px !important;
                        cursor: pointer !important;
                        transition: background-color 0.3s ease !important;
                    }
    
                    #dozen-tracker summary:hover {
                        background-color: #d81b60 !important;
                    }
    
                    #dozen-tracker summary::after {
                        filter: invert(100%) !important;
                    }
    
                    #dozen-tracker .gr-accordion {
                        background-color: #fce4ec !important;
                        border: 1px solid #f06292 !important;
                        border-radius: 6px !important;
                        margin: 5px 0 !important;
                    }
    
                    #dozen-tracker .gr-accordion summary {
                        background-color: #f48fb1 !important;
                        color: white !important;
                        padding: 10px !important;
                        border-radius: 4px !important;
                        font-size: 16px !important;
                        cursor: pointer !important;
                        transition: background-color 0.3s ease !important;
                    }
    
                    #dozen-tracker .gr-accordion summary:hover {
                        background-color: #f06292 !important;
                    }
    
                    @media (max-width: 768px) {
                        #dozen-tracker {
                            padding: 8px !important;
                        }
                        #dozen-tracker summary {
                            font-size: 16px !important;
                        }
                        #dozen-tracker .gr-accordion summary {
                            font-size: 14px !important;
                        }
                    }
                </style>
                """)
                with gr.Accordion("Dozen Triggers", open=False, elem_id="dozen-triggers"):
                    dozen_tracker_spins_dropdown = gr.Dropdown(
                        label="Number of Spins to Track",
                        choices=["3", "4", "5", "6", "10", "15", "20", "25", "30", "40", "50", "75", "100", "150", "200"],
                        value="5",
                        interactive=True
                    )
                    dozen_tracker_consecutive_hits_dropdown = gr.Dropdown(
                        label="Alert on Consecutive Dozen Hits",
                        choices=["3", "4", "5"],
                        value="3",
                        interactive=True
                    )
                    dozen_tracker_alert_checkbox = gr.Checkbox(
                        label="Enable Consecutive Dozen Hits Alert",
                        value=False,
                        interactive=True
                    )
                    dozen_tracker_sequence_length_dropdown = gr.Dropdown(
                        label="Sequence Length to Match (X)",
                        choices=["3", "4", "5"],
                        value="4",
                        interactive=True
                    )
                    dozen_tracker_follow_up_spins_dropdown = gr.Dropdown(
                        label="Follow-Up Spins to Track (Y)",
                        choices=["3", "4", "5", "6", "7", "8", "9", "10"],
                        value="5",
                        interactive=True
                    )
                    dozen_tracker_sequence_alert_checkbox = gr.Checkbox(
                        label="Enable Sequence Matching Alert",
                        value=False,
                        interactive=True
                    )
                    dozen_tracker_output = gr.HTML(
                        label="Dozen Tracker",
                        value="<p>Select the number of spins to track and analyze spins to see the Dozen history.</p>"
                    )
                    dozen_tracker_sequence_output = gr.HTML(
                        label="Sequence Matching Results",
                        value="<p>Enable sequence matching to see results here.</p>"
                    )
                with gr.Accordion("Even Money", open=False, elem_id="even-money-tracker"):
                    even_money_tracker_spins_dropdown = gr.Dropdown(
                        label="Number of Spins to Track",
                        choices=["1", "2", "3", "4", "5", "6", "10", "15", "20", "25", "30", "40", "50", "75", "100", "150", "200"],
                        value="5",
                        interactive=True
                    )
                    even_money_tracker_consecutive_hits_dropdown = gr.Dropdown(
                        label="Alert on Consecutive Even Money Hits",
                        choices=["1", "2", "3", "4", "5"],
                        value="3",
                        interactive=True
                    )
                    even_money_tracker_combination_mode_dropdown = gr.Dropdown(
                        label="Combination Mode",
                        choices=["And", "Or"],
                        value="And",
                        interactive=True
                    )
                    even_money_tracker_identical_traits_checkbox = gr.Checkbox(
                        label="Track Consecutive Identical Traits",
                        value=False,
                        interactive=True
                    )
                    even_money_tracker_consecutive_identical_dropdown = gr.Dropdown(
                        label="Number of Consecutive Identical Traits",
                        choices=["1", "2", "3", "4", "5"],
                        value="2",
                        interactive=True
                    )
                    with gr.Row():
                        even_money_tracker_red_checkbox = gr.Checkbox(label="Red", value=False, interactive=True)
                        even_money_tracker_black_checkbox = gr.Checkbox(label="Black", value=False, interactive=True)
                        even_money_tracker_even_checkbox = gr.Checkbox(label="Even", value=False, interactive=True)
                        even_money_tracker_odd_checkbox = gr.Checkbox(label="Odd", value=False, interactive=True)
                        even_money_tracker_low_checkbox = gr.Checkbox(label="Low", value=False, interactive=True)
                        even_money_tracker_high_checkbox = gr.Checkbox(label="High", value=False, interactive=True)
                    even_money_tracker_alert_checkbox = gr.Checkbox(
                        label="Enable Even Money Hits Alert",
                        value=False,
                        interactive=True
                    )
                    even_money_tracker_output = gr.HTML(
                        label="Even Money Tracker",
                        value="<p>Select categories to track and analyze spins to see even money bet history.</p>"
                    )
        with gr.Column(scale=2):
            pass
    
    # 8. Row 8: Betting Progression Tracker
    with gr.Accordion("Betting Progression Tracker", open=False, elem_id="betting-progression", elem_classes=["betting-progression"]):
        gr.HTML("""
        <style>
            .betting-progression {
                background-color: #fffde7 !important;
                border: 2px solid #ffca28 !important;
                border-radius: 8px !important;
                padding: 12px !important;
                margin-bottom: 15px !important;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15) !important;
                animation: fadeInAccordion 0.5s ease-in-out !important;
            }
            
            @keyframes fadeInAccordion {
                0% { opacity: 0; transform: translateY(5px); }
                100% { opacity: 1; transform: translateY(0); }
            }
            
            .betting-progression summary {
                background-color: #ffca28 !important;
                color: white !important;
                padding: 12px !important;
                border-radius: 6px !important;
                font-weight: bold !important;
                font-size: 18px !important;
                cursor: pointer !important;
                transition: background-color 0.3s ease !important;
            }
            
            .betting-progression summary:hover {
                background-color: #ffb300 !important;
            }
            
            .betting-progression summary::after {
                filter: invert(100%) !important;
            }
            
            .betting-progression .gr-row {
                background-color: #fffde7 !important;
                padding: 5px !important;
                border-radius: 6px !important;
                margin: 5px 0 !important;
            }
            
            .betting-progression .gr-textbox {
                background: transparent !important;
                border: 1px solid #ffca28 !important;
                border-radius: 6px !important;
                padding: 8px !important;
                color: #333 !important;
                font-size: 14px !important;
                width: 100% !important;
                box-sizing: border-box !important;
            }
            
            @media (max-width: 768px) {
                .betting-progression {
                    padding: 8px !important;
                }
                .betting-progression summary {
                    font-size: 16px !important;
                }
                .betting-progression .gr-textbox {
                    font-size: 12px !important;
                    padding: 6px !important;
                }
            }
        </style>
        """)
        with gr.Row():
            bankroll_input = gr.Number(label="Bankroll", value=1000)
            base_unit_input = gr.Number(label="Base Unit", value=10)
            stop_loss_input = gr.Number(label="Stop Loss", value=-500)
            stop_win_input = gr.Number(label="Stop Win", value=200)
            target_profit_input = gr.Number(label="Target Profit (Units)", value=10, step=1)
        with gr.Row():
            bet_type_dropdown = gr.Dropdown(
                label="Bet Type",
                choices=["Even Money", "Dozens", "Columns", "Streets", "Straight Bets"],
                value="Even Money"
            )
            progression_dropdown = gr.Dropdown(
                label="Progression",
                choices=[
                    "Martingale", "Fibonacci", "Triple Martingale", "Ladder", "D’Alembert",
                    "Double After a Win", "+1 Win / -1 Loss", "+2 Win / -1 Loss",
                    "Double Loss / +50% Win", "Victory Vortex V.2"
                ],
                value="Martingale"
            )
        with gr.Row():
            win_button = gr.Button("Win")
            lose_button = gr.Button("Lose")
            reset_progression_button = gr.Button("Reset Progression")
            reset_bankroll_button = gr.Button("Reset Bankroll")
        with gr.Row():
            bankroll_output = gr.Textbox(label="Current Bankroll", value="1000", interactive=False)
            current_bet_output = gr.Textbox(label="Current Bet", value="10", interactive=False)
            next_bet_output = gr.Textbox(label="Next Bet", value="10", interactive=False)
        with gr.Row():
            message_output = gr.Textbox(label="Message", value="Start with base bet of 10 on Even Money (Martingale)", interactive=False)
            status_output = gr.HTML(label="Status", value='<div style="background-color: white; padding: 5px; border-radius: 3px;">Active</div>')

    # 8.1. Row 8.1: Casino Data Insights
    with gr.Row():
        with gr.Accordion("Casino Data Insights", open=False, elem_classes=["betting-progression"], elem_id="casino-data-insights"):
            gr.HTML("""
            <style>
                #casino-data-insights {
                    background-color: #e3f2fd !important;
                    border: 2px solid #42a5f5 !important;
                    border-radius: 8px !important;
                    padding: 12px !important;
                    margin-bottom: 15px !important;
                    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15) !important;
                    animation: fadeInAccordion 0.5s ease-in-out !important;
                }
    
                @keyframes fadeInAccordion {
                    0% { opacity: 0; transform: translateY(5px); }
                    100% { opacity: 1; transform: translateY(0); }
                }
    
                #casino-data-insights summary {
                    background-color: #42a5f5 !important;
                    color: white !important;
                    padding: 12px !important;
                    border-radius: 6px !important;
                    font-weight: bold !important;
                    font-size: 18px !important;
                    cursor: pointer !important;
                    transition: background-color 0.3s ease !important;
                }
    
                #casino-data-insights summary:hover {
                    background-color: #1e88e5 !important;
                }
    
                #casino-data-insights summary::after {
                    filter: invert(100%) !important;
                }
    
                #casino-data-insights .gr-row {
                    background-color: #e3f2fd !important;
                    padding: 5px !important;
                    border-radius: 6px !important;
                    margin: 5px 0 !important;
                }
    
                #casino-data-insights .gr-textbox {
                    background: transparent !important;
                    border: 1px solid #42a5f5 !important;
                    border-radius: 6px !important;
                    padding: 8px !important;
                    color: #333 !important;
                    font-size: 14px !important;
                    width: 100% !important;
                    box-sizing: border-box !important;
                }
    
                #casino-data-insights .gr-accordion {
                    background-color: #e3f2fd !important;
                    border: 1px solid #42a5f5 !important;
                    border-radius: 6px !important;
                    margin: 5px 0 !important;
                }
    
                #casino-data-insights .gr-accordion summary {
                    background-color: #90caf9 !important;
                    color: white !important;
                    padding: 10px !important;
                    border-radius: 4px !important;
                    font-size: 16px !important;
                    cursor: pointer !important;
                    transition: background-color 0.3s ease !important;
                }
    
                #casino-data-insights .gr-accordion summary:hover {
                    background-color: #42a5f5 !important;
                }
    
                @media (max-width: 768px) {
                    #casino-data-insights {
                        padding: 8px !important;
                    }
                    #casino-data-insights summary {
                        font-size: 16px !important;
                    }
                    #casino-data-insights .gr-textbox {
                        font-size: 12px !important;
                        padding: 6px !important;
                    }
                    #casino-data-insights .gr-accordion summary {
                        font-size: 14px !important;
                    }
                }
            </style>
            """)
            spins_count_dropdown = gr.Dropdown(
                label="Past Spins Count",
                choices=["30", "50", "100", "200", "300", "500"],
                value="100",
                interactive=True
            )
            with gr.Row():
                even_percent = gr.Dropdown(
                    label="Even %",
                    choices=[f"{i:02d}" for i in range(100)],
                    value="00",
                    interactive=True
                )
                odd_percent = gr.Dropdown(
                    label="Odd %",
                    choices=[f"{i:02d}" for i in range(100)],
                    value="00",
                    interactive=True
                )
            with gr.Row():
                red_percent = gr.Dropdown(
                    label="Red %",
                    choices=[f"{i:02d}" for i in range(100)],
                    value="00",
                    interactive=True
                )
                black_percent = gr.Dropdown(
                    label="Black %",
                    choices=[f"{i:02d}" for i in range(100)],
                    value="00",
                    interactive=True
                )
            with gr.Row():
                low_percent = gr.Dropdown(
                    label="Low %",
                    choices=[f"{i:02d}" for i in range(100)],
                    value="00",
                    interactive=True
                )
                high_percent = gr.Dropdown(
                    label="High %",
                    choices=[f"{i:02d}" for i in range(100)],
                    value="00",
                    interactive=True
                )
            with gr.Row():
                dozen1_percent = gr.Dropdown(
                    label="1st Dozen %",
                    choices=[f"{i:02d}" for i in range(100)],
                    value="00",
                    interactive=True
                )
                dozen2_percent = gr.Dropdown(
                    label="2nd Dozen %",
                    choices=[f"{i:02d}" for i in range(100)],
                    value="00",
                    interactive=True
                )
                dozen3_percent = gr.Dropdown(
                    label="3rd Dozen %",
                    choices=[f"{i:02d}" for i in range(100)],
                    value="00",
                    interactive=True
                )
            with gr.Row():
                col1_percent = gr.Dropdown(
                    label="1st Column %",
                    choices=[f"{i:02d}" for i in range(100)],
                    value="00",
                    interactive=True
                )
                col2_percent = gr.Dropdown(
                    label="2nd Column %",
                    choices=[f"{i:02d}" for i in range(100)],
                    value="00",
                    interactive=True
                )
                col3_percent = gr.Dropdown(
                    label="3rd Column %",
                    choices=[f"{i:02d}" for i in range(100)],
                    value="00",
                    interactive=True
                )
            use_winners_checkbox = gr.Checkbox(
                label="Highlight Casino Winners",
                value=False,
                interactive=True
            )
            reset_casino_data_button = gr.Button(
                "Reset Casino Data",
                elem_classes=["action-button"]
            )
            casino_data_output = gr.HTML(
                label="Casino Data Insights",
                value="<p>No casino data entered yet.</p>",
                elem_classes=["fade-in"]
            )
            with gr.Accordion("Hot and Cold Numbers", open=False, elem_id="hot-cold-numbers"):
                with gr.Row():
                    gr.HTML('<span class="hot-icon">🔥</span>')
                    hot_numbers_input = gr.Textbox(
                        label="Hot Numbers (1 to 10 comma-separated numbers, e.g., 1, 3, 5, 7, 9)",
                        value="",
                        interactive=True,
                        placeholder="Enter 1 to 10 hot numbers"
                    )
                hot_suggestions = gr.Textbox(
                    label="Suggested Hot Numbers (based on recent spins)",
                    value="",
                    interactive=False,
                    elem_classes=["suggestion-box"]
                )
                gr.Button("Use Suggested Hot Numbers", elem_classes=["action-button", "suggestion-btn"]).click(
                    fn=lambda: state.hot_suggestions,
                    inputs=[],
                    outputs=[hot_numbers_input]
                )
                with gr.Row():
                    gr.HTML('<span class="cold-icon">❄️</span>')
                    cold_numbers_input = gr.Textbox(
                        label="Cold Numbers (1 to 10 comma-separated numbers, e.g., 2, 4, 6, 8, 10)",
                        value="",
                        interactive=True,
                        placeholder="Enter 1 to 10 cold numbers"
                    )
                cold_suggestions = gr.Textbox(
                    label="Suggested Cold Numbers (based on recent spins)",
                    value="",
                    interactive=False,
                    elem_classes=["suggestion-box"]
                )
                gr.Button("Use Suggested Cold Numbers", elem_classes=["action-button", "suggestion-btn"]).click(
                    fn=lambda: state.cold_suggestions,
                    inputs=[],
                    outputs=[cold_numbers_input]
                )
                with gr.Row():
                    play_hot_button = gr.Button("Play Hot Numbers", elem_classes=["action-button", "play-btn"])
                    play_cold_button = gr.Button("Play Cold Numbers", elem_classes=["action-button", "play-btn"])
                with gr.Row():
                    clear_hot_button = gr.Button("Clear Hot Picks", elem_classes=["action-button", "clear-btn"])
                    clear_cold_button = gr.Button("Clear Cold Picks", elem_classes=["action-button", "clear-btn"])
    
    # 9. Row 9: Color Code Key (Collapsible, with Color Pickers Inside)
    with gr.Accordion("Color Code Key", open=False, elem_id="color-code-key"):
        gr.HTML("""
        <style>
            #color-code-key {
                background-color: #ede7f6 !important;
                border: 2px solid #ab47bc !important;
                border-radius: 8px !important;
                padding: 12px !important;
                margin-bottom: 15px !important;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15) !important;
                animation: fadeInAccordion 0.5s ease-in-out !important;
            }
    
            @keyframes fadeInAccordion {
                0% { opacity: 0; transform: translateY(5px); }
                100% { opacity: 1; transform: translateY(0); }
            }
    
            #color-code-key summary {
                background-color: #ab47bc !important;
                color: white !important;
                padding: 12px !important;
                border-radius: 6px !important;
                font-weight: bold !important;
                font-size: 18px !important;
                cursor: pointer !important;
                transition: background-color 0.3s ease !important;
            }
    
            #color-code-key summary:hover {
                background-color: #8e24aa !important;
            }
    
            #color-code-key summary::after {
                filter: invert(100%) !important;
            }
    
            #color-code-key .gr-row {
                background-color: #ede7f6 !important;
                padding: 5px !important;
                border-radius: 6px !important;
                margin: 5px 0 !important;
            }
    
            @media (max-width: 768px) {
                #color-code-key {
                    padding: 8px !important;
                }
                #color-code-key summary {
                    font-size: 16px !important;
                }
            }
        </style>
        """)
        with gr.Row():
            top_color_picker = gr.ColorPicker(
                label="Top Tier Color",
                value="rgba(255, 255, 0, 0.5)",
                interactive=True,
                elem_id="top-color-picker"
            )
            middle_color_picker = gr.ColorPicker(
                label="Middle Tier Color",
                value="rgba(0, 255, 255, 0.5)",
                interactive=True
            )
            lower_color_picker = gr.ColorPicker(
                label="Lower Tier Color",
                value="rgba(0, 255, 0, 0.5)",
                interactive=True
            )
            reset_colors_button = gr.Button("Reset Colors", elem_classes=["action-button"])
        color_code_output = gr.HTML(label="Color Code Key")

    # 10. Row 10: Analysis Outputs (Collapsible, Renumbered)
    with gr.Accordion("Spin Logic Reactor 🧠", open=False, elem_id="spin-analysis"):
        gr.HTML("""
        <style>
            #spin-analysis {
                background-color: #e0f7fa !important;
                border: 2px solid #00bcd4 !important;
                border-radius: 8px !important;
                padding: 12px !important;
                margin-bottom: 15px !important;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15) !important;
                animation: fadeInAccordion 0.5s ease-in-out !important;
            }
    
            @keyframes fadeInAccordion {
                0% { opacity: 0; transform: translateY(5px); }
                100% { opacity: 1; transform: translateY(0); }
            }
    
            #spin-analysis summary {
                background-color: #00bcd4 !important;
                color: white !important;
                padding: 12px !important;
                border-radius: 6px !important;
                font-weight: bold !important;
                font-size: 18px !important;
                cursor: pointer !important;
                transition: background-color 0.3s ease !important;
            }
    
            #spin-analysis summary:hover {
                background-color: #0097a7 !important;
            }
    
            #spin-analysis summary::after {
                filter: invert(100%) !important;
            }
    
            .spin-analysis-row {
                background-color: #e0f7fa !important;
                padding: 10px !important;
                border-radius: 6px !important;
                display: flex !important;
                flex-wrap: wrap !important;
                gap: 15px !important;
                align-items: stretch !important;
                margin-top: 10px !important;
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1) !important;
                width: 100% !important;
                min-height: fit-content !important;
                height: auto !important;
                box-sizing: border-box !important;
            }
    
            .spin-analysis-row .gr-textbox {
                background: transparent !important;
                border: 1px solid #00bcd4 !important;
                border-radius: 6px !important;
                padding: 8px !important;
                color: #333 !important;
                font-size: 14px !important;
                width: 100% !important;
                box-sizing: border-box !important;
            }
    
            @media (max-width: 768px) {
                #spin-analysis {
                    padding: 8px !important;
                }
                #spin-analysis summary {
                    font-size: 16px !important;
                }
                .spin-analysis-row {
                    flex-direction: column !important;
                    gap: 10px !important;
                }
                .spin-analysis-row .gr-textbox {
                    font-size: 12px !important;
                    padding: 6px !important;
                }
            }
        </style>
        """)
        with gr.Row(elem_classes=["spin-analysis-row"]):
            spin_analysis_output = gr.Textbox(
                label="",
                value="",
                interactive=False,
                lines=5
            )

    with gr.Accordion("Strongest Numbers Tables", open=False, elem_id="strongest-numbers-table"):
        gr.HTML("""
        <style>
            /* Styling for Strongest Numbers Tables accordion */
            #strongest-numbers-table {
                background-color: #e8f5e9 !important; /* Light green background */
                border: 2px solid #4caf50 !important; /* Green border */
                border-radius: 8px !important;
                padding: 12px !important;
                margin-bottom: 15px !important;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15) !important;
                animation: fadeInAccordion 0.5s ease-in-out !important;
            }
    
            /* Styling for the accordion summary */
            #strongest-numbers-table summary {
                background-color: #4caf50 !important; /* Green background for header */
                color: white !important;
                padding: 12px !important;
                border-radius: 6px !important;
                font-weight: bold !important;
                font-size: 18px !important;
                cursor: pointer !important;
                transition: background-color 0.3s ease !important;
            }
    
            #strongest-numbers-table summary:hover {
                background-color: #388e3c !important; /* Darker green on hover */
            }
    
            /* Ensure the summary arrow is styled */
            #strongest-numbers-table summary::after {
                filter: invert(100%) !important; /* White arrow for contrast */
            }
    
            /* Styling for the row inside the accordion */
            .strongest-numbers-row {
                background-color: #ffffff !important; /* White background for clarity */
                padding: 10px !important;
                border-radius: 6px !important;
                display: flex !important;
                flex-wrap: wrap !important;
                gap: 15px !important;
                align-items: stretch !important;
                margin-top: 10px !important;
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1) !important;
            }
    
            /* Styling for columns inside the row */
            .strongest-numbers-row .gr-column {
                flex: 1 !important;
                min-width: 300px !important; /* Ensure columns don't get too narrow */
                background-color: transparent !important;
                padding: 10px !important;
            }
    
            /* Styling for HTML outputs (straight_up_html and top_18_html) */
            .strongest-numbers-row .scrollable-table {
                max-height: 800px !important; /* Increased height to show more numbers */
                overflow-y: auto !important;
                background: #111 !important; /* Darker theme background */
                border: 2px solid #4caf50 !important;
                border-radius: 12px !important;
                padding: 15px !important;
                font-size: 20px !important; /* Larger text inside table */
            }
            /* Animation for accordion opening */
            @keyframes fadeInAccordion {
                0% { opacity: 0; transform: translateY(5px); }
                100% { opacity: 1; transform: translateY(0); }
            }
    
            /* Responsive adjustments */
            @media (max-width: 768px) {
                .strongest-numbers-row {
                    flex-direction: column !important;
                    gap: 10px !important;
                }
                .strongest-numbers-row .gr-column {
                    min-width: 100% !important;
                }
                #strongest-numbers-table {
                    padding: 8px !important;
                }
                #strongest-numbers-table summary {
                    font-size: 16px !important;
                }
            }
        </style>
        """)
        with gr.Row(elem_classes=["strongest-numbers-row"]):
            with gr.Column():
                straight_up_html = gr.HTML(label="Strongest Numbers", elem_classes="scrollable-table")
            with gr.Column():
                top_18_html = gr.HTML(label="Top 18 Strongest Numbers (Sorted Lowest to Highest)", elem_classes="scrollable-table")
        with gr.Row():
            strongest_numbers_dropdown = gr.Dropdown(
                label="Select Number of Strongest Numbers",
                choices=["3", "6", "9", "12", "15", "18", "21", "24", "27", "30", "33"],
                value="3",
                allow_custom_value=False,
                interactive=True,
                elem_id="strongest-numbers-dropdown",
                visible=False  # Hide the dropdown
            )
            strongest_numbers_output = gr.Textbox(
                label="Strongest Numbers (Sorted Lowest to Highest)",
                value="",
                lines=2,
                visible=False  # Hide the textbox
            )
    
    with gr.Accordion("Aggregated Scores", open=False, elem_id="aggregated-scores"):
        gr.HTML("""
        <style>
            /* Styling for Aggregated Scores accordion */
            #aggregated-scores {
                background-color: #f3e5f5 !important; /* Light purple background */
                border: 2px solid #8e24aa !important; /* Neon purple border */
                border-radius: 8px !important;
                padding: 12px !important;
                margin-bottom: 15px !important;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15) !important;
                animation: fadeInAccordion 0.5s ease-in-out !important;
            }
    
            /* Styling for the accordion summary */
            #aggregated-scores summary {
                background-color: #8e24aa !important; /* Neon purple background for header */
                color: white !important;
                padding: 12px !important;
                border-radius: 6px !important;
                font-weight: bold !important;
                font-size: 18px !important;
                cursor: pointer !important;
                transition: background-color 0.3s ease !important;
            }
    
            #aggregated-scores summary:hover {
                background-color: #6a1b9a !important; /* Darker purple on hover */
            }
    
            /* Ensure the summary arrow is styled */
            #aggregated-scores summary::after {
                filter: invert(100%) !important; /* White arrow for contrast */
            }
    
            /* Styling for rows inside the accordion */
            .aggregated-scores-row {
                background-color: #ffffff !important; /* White background for clarity */
                padding: 10px !important;
                border-radius: 6px !important;
                display: flex !important;
                flex-wrap: wrap !important;
                gap: 15px !important;
                align-items: stretch !important;
                margin: 10px 0 !important;
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1) !important;
            }
    
            /* Styling for columns inside the rows */
            .aggregated-scores-row .gr-column {
                flex: 1 !important;
                min-width: 300px !important; /* Ensure columns don't get too narrow */
                background-color: transparent !important;
                padding: 10px !important;
            }
    
            /* Styling for nested accordions */
            .aggregated-scores-row .gr-accordion {
                background-color: #fafafa !important; /* Slightly off-white for nested accordions */
                border: 1px solid #8e24aa !important; /* Match purple border */
                border-radius: 6px !important;
                margin: 5px 0 !important;
            }
    
            .aggregated-scores-row .gr-accordion summary {
                background-color: #ab47bc !important; /* Lighter purple for nested summaries */
                color: white !important;
                padding: 10px !important;
                border-radius: 4px !important;
                font-size: 16px !important;
                cursor: pointer !important;
                transition: background-color 0.3s ease !important;
            }
    
            .aggregated-scores-row .gr-accordion summary:hover {
                background-color: #8e24aa !important; /* Match main accordion color on hover */
            }
    
            /* Styling for textboxes inside nested accordions */
            .aggregated-scores-row .gr-textbox {
                background: linear-gradient(135deg, #f5f5f5, #e0e0e0) !important;
                border: 1px solid #8e24aa !important;
                border-radius: 6px !important;
                padding: 8px !important;
                max-height: 250px !important;
                overflow-y: auto !important;
            }
    
            /* Animation for accordion opening */
            @keyframes fadeInAccordion {
                0% { opacity: 0; transform: translateY(5px); }
                100% { opacity: 1; transform: translateY(0); }
            }
    
            /* Responsive adjustments */
            @media (max-width: 768px) {
                .aggregated-scores-row {
                    flex-direction: column !important;
                    gap: 10px !important;
                }
                .aggregated-scores-row .gr-column {
                    min-width: 100% !important;
                }
                #aggregated-scores {
                    padding: 8px !important;
                }
                #aggregated-scores summary {
                    font-size: 16px !important;
                }
                .aggregated-scores-row .gr-accordion summary {
                    font-size: 14px !important;
                }
            }
        </style>
        """)
        with gr.Row(elem_classes=["aggregated-scores-row"]):
            with gr.Column():
                with gr.Accordion("Even Money Trends", open=False):
                    even_money_output = gr.HTML(label="Even Money Bets")
            with gr.Column():
                with gr.Accordion("Dozen Trends", open=False):
                    dozens_output = gr.HTML(label="Dozens")
        with gr.Row(elem_classes=["aggregated-scores-row"]):
            with gr.Column():
                with gr.Accordion("Column Trends", open=False):
                    columns_output = gr.HTML(label="Columns")
            with gr.Column():
                with gr.Accordion("Street Hits", open=False):
                    streets_output = gr.HTML(label="Streets")
        with gr.Row(elem_classes=["aggregated-scores-row"]):
            with gr.Column():
                with gr.Accordion("Corner Hits", open=False):
                    corners_output = gr.HTML(label="Corners")
            with gr.Column():
                with gr.Accordion("Double Street Trends", open=False):
                    six_lines_output = gr.HTML(label="Double Streets")
        with gr.Row(elem_classes=["aggregated-scores-row"]):
            with gr.Column():
                with gr.Accordion("Split Hits", open=False):
                    splits_output = gr.HTML(label="Splits")
            with gr.Column():
                with gr.Accordion("Wheel Side Reactor", open=False):
                    sides_output = gr.HTML(label="Sides of Zero")

    # In the "Save/Load Session" accordion
    with gr.Accordion("Save/Load Session", open=False, elem_id="save-load-session"):
        with gr.Row(elem_classes=["save-load-row"]):
            # Text input for the file name
            session_name_input = gr.Textbox(
                label="Session File Name",
                placeholder="Enter session name (e.g., MySession)",
                value="WheelPulse_Session",
                interactive=True,
                elem_id="session-name-input"
            )
            save_button = gr.Button("Save Session", elem_id="save-session-btn")
            load_input = gr.File(label="Upload Session", file_types=[".json"], elem_id="upload-session")
            save_output = gr.File(label="Download Session", elem_id="download-session")
        gr.HTML(
            '''
            <style>
                #save-load-session {
                    background-color: #fff3e0 !important;
                    border: 2px solid #ff9800 !important;
                    border-radius: 5px !important;
                    padding: 10px !important;
                }
                #save-load-session summary {
                    background-color: #ff9800 !important;
                    color: white !important;
                    padding: 10px !important;
                    border-radius: 5px !important;
                }
                .save-load-row {
                    background-color: #f5f5f5 !important;
                    padding: 8px !important;
                    border-radius: 3px !important;
                    display: flex !important;
                    flex-wrap: wrap !important;
                    gap: 10px !important;
                    align-items: center !important;
                }
                #save-session-btn {
                    background-color: #4caf50 !important;
                    color: white !important;
                }
                #session-name-input {
                    width: 100% !important;
                    max-width: 300px !important;
                }
                #session-name-input input {
                    border: 1px solid #ff9800 !important;
                    border-radius: 4px !important;
                    padding: 5px !important;
                    font-size: 14px !important;
                }
                #save-load-session summary::after {
                    filter: invert(100%) !important;
                }
                #download-session {
                    display: block !important;
                    visibility: visible !important;
                    margin-top: 8px !important;
                    width: auto !important;
                }
                #download-session .file-container {
                    background-color: #ffffff !important;
                    border: 1px solid #ccc !important;
                    padding: 5px !important;
                    border-radius: 3px !important;
                }
            </style>
            '''
        )

    # NEW: Session File Combiner Section
    with gr.Accordion("🔗 Session File Combiner", open=False, elem_id="session-combiner"):
        gr.HTML("""
        <style>
            #session-combiner summary {
                background-color: #1565c0 !important;
                color: white !important;
                padding: 12px !important;
                border-radius: 6px !important;
                font-weight: bold !important;
                font-size: 18px !important;
            }
            #session-combiner summary:hover { background-color: #0d47a1 !important; }
            #session-combiner summary::after { filter: invert(100%) !important; }
            #session-combiner {
                background-color: #e3f2fd !important;
                border: 2px solid #1565c0 !important;
                border-radius: 8px !important;
                padding: 12px !important;
                margin-bottom: 15px !important;
            }
        </style>
        <p style="font-family:Arial,sans-serif; color:#333; margin:0 0 10px 0;">
            Upload 2 or 3 saved session files. They will be merged <b>in the order you upload them</b>
            — File 1 spins first, File 2 after, File 3 last. The combined session is downloaded
            and automatically loaded into the app.
        </p>
        """)
        with gr.Row():
            combine_file1 = gr.File(label="📁 File 1 (First)", file_types=[".json"], scale=1)
            combine_file2 = gr.File(label="📁 File 2 (Second)", file_types=[".json"], scale=1)
            combine_file3 = gr.File(label="📁 File 3 (Third — Optional)", file_types=[".json"], scale=1)
        with gr.Row():
            combine_button = gr.Button("🔗 Combine Sessions", variant="primary", scale=2)
        with gr.Row():
            combine_status = gr.HTML(value="<p style='color:#888;'>Upload at least 2 files and click Combine.</p>")
        with gr.Row():
            combine_output = gr.File(label="⬇️ Download Combined Session", elem_id="combine-download")

    # 11. Row 11: Top Strategies with WheelPulse by S.T.Y.W (Moved to be Independent)
    with gr.Row():
        with gr.Column():
            with gr.Accordion("Top Strategies with WheelPulse by S.T.Y.W 📈🎥", open=False, elem_id="top-strategies"):
                gr.HTML("""
                <style>
                    #top-strategies {
                        background-color: #e0f2e9 !important;
                        border: 2px solid #26a69a !important;
                        border-radius: 8px !important;
                        padding: 12px !important;
                        margin-bottom: 15px !important;
                        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15) !important;
                        animation: fadeInAccordion 0.5s ease-in-out !important;
                    }
    
                    @keyframes fadeInAccordion {
                        0% { opacity: 0; transform: translateY(5px); }
                        100% { opacity: 1; transform: translateY(0); }
                    }
    
                    #top-strategies summary {
                        background-color: #26a69a !important;
                        color: white !important;
                        padding: 12px !important;
                        border-radius: 6px !important;
                        font-weight: bold !important;
                        font-size: 18px !important;
                        cursor: pointer !important;
                        transition: background-color 0.3s ease !important;
                    }
    
                    #top-strategies summary:hover {
                        background-color: #00897b !important;
                    }
    
                    #top-strategies summary::after {
                        filter: invert(100%) !important;
                    }
    
                    #top-strategies .gr-row {
                        background-color: #e0f2e9 !important;
                        padding: 5px !important;
                        border-radius: 6px !important;
                        margin: 5px 0 !important;
                    }
    
                    @media (max-width: 768px) {
                        #top-strategies {
                            padding: 8px !important;
                        }
                        #top-strategies summary {
                            font-size: 16px !important;
                        }
                    }
                </style>
                """)
                gr.Markdown("### Explore Strategies Through Videos")
                video_category_dropdown = gr.Dropdown(
                    label="Select Video Category",
                    choices=sorted(video_categories.keys()),
                    value="Dozen Strategies",
                    allow_custom_value=False,
                    elem_id="video-category-dropdown"
                )
                video_dropdown = gr.Dropdown(
                    label="Select Video",
                    choices=[video["title"] for video in video_categories["Dozen Strategies"]],
                    value=video_categories["Dozen Strategies"][0]["title"] if video_categories["Dozen Strategies"] else None,
                    allow_custom_value=False,
                    elem_id="video-dropdown"
                )
                video_output = gr.HTML(
                    label="Video",
                    value=f'<iframe width="100%" height="315" src="https://www.youtube.com/embed/{video_categories["Dozen Strategies"][0]["link"].split("/")[-1]}" frameborder="0" allowfullscreen></iframe>' if video_categories["Dozen Strategies"] else "<p>Select a category and video to watch.</p>"
                )
    
    # Feedback & Suggestions section removed
    
    # CSS (end of the previous section, for context)
    gr.HTML("""
        <style>
            /* General Layout */
            .gr-row { margin: 0 !important; padding: 5px 0 !important; }
            .gr-column { margin: 0 !important; padding: 5px !important; display: flex !important; flex-direction: column !important; align-items: stretch !important; }
            .gr-box { border-radius: 5px !important; }
            
            /* Style for Dealer’s Spin Tracker accordion */
            #sides-of-zero-accordion {
                background-color: #f3e5f5 !important;
                border: 2px solid #8e24aa !important;
                border-radius: 8px !important;
                padding: 12px !important;
                margin-bottom: 15px !important;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15) !important;
                animation: fadeInAccordion 0.5s ease-in-out !important;
            }
            
            @keyframes fadeInAccordion {
                0% { opacity: 0; transform: translateY(5px); }
                100% { opacity: 1; transform: translateY(0); }
            }
            
            #sides-of-zero-accordion > div {
                background-color: transparent !important;
            }
            
            #sides-of-zero-accordion summary {
                background-color: #8e24aa !important;
                color: #fff !important;
                padding: 12px !important;
                border-radius: 6px !important;
                font-weight: bold !important;
                font-size: 18px !important;
                cursor: pointer !important;
                transition: background-color 0.3s ease !important;
            }
            
            #sides-of-zero-accordion summary:hover {
                background-color: #6a1b9a !important;
            }
            
            #sides-of-zero-accordion summary::after {
                filter: invert(100%) !important;
            }
            
            @media (max-width: 768px) {
                #sides-of-zero-accordion {
                    padding: 8px !important;
                }
                #sides-of-zero-accordion summary {
                    font-size: 16px !important;
                }
            }
            
            /* Hide stray labels in the Sides of Zero section */
            .sides-of-zero-container + label, .last-spins-container + label:not(.long-slider label) {
                display: none !important;
            }
            
            /* Header Styling */
            #header-row {
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                flex-wrap: wrap !important;
                background-color: white !important;
                padding: 10px 0 !important;
                width: 100% !important;
                margin: 0 auto !important;
                margin-bottom: 20px !important;
            }
            
            .header-title { text-align: center !important; font-size: 2.5em !important; margin: 0 !important; color: #333 !important; } 
            
            /* Selected Spins — full-width container, pill label, wide input */
            #selected-spins-row {
                width: 100% !important;
                max-width: 100% !important;
                overflow: visible !important;
                padding: 0 !important;
                margin: 0 !important;
            }
            #selected-spins-row > .wrap,
            #selected-spins-row > div {
                width: 100% !important;
                max-width: 100% !important;
            }
            #selected-spins {
                width: 100% !important;
                max-width: 100% !important;
            }
            /* Keep label as a small pill — do NOT override width or display here */
            #selected-spins label {
                white-space: nowrap !important;
                width: fit-content !important;
                max-width: fit-content !important;
                overflow: visible !important;
                display: inline-flex !important;
            }
            /* Make the textarea (Gradio 5) fill the full row width */
            #selected-spins textarea,
            #selected-spins input {
                width: 100% !important;
                min-width: 0 !important;
                max-width: 100% !important;
                box-sizing: border-box !important;
            }
            
            /* Roulette Table */
            .roulette-button.green { background-color: green !important; color: white !important; border: 1px solid white !important; text-align: center !important; font-weight: bold !important; }
            .roulette-button.red { background-color: red !important; color: white !important; border: 1px solid white !important; text-align: center !important; font-weight: bold !important; }
            .roulette-button.black { background-color: black !important; color: white !important; border: 1px solid white !important; text-align: center !important; font-weight: bold !important; }
            .roulette-button:hover { opacity: 0.8; }
            .roulette-button.selected { border: 3px solid yellow !important; opacity: 0.9; }
            .roulette-button { margin: 0 !important; padding: 0 !important; width: 40px !important; height: 40px !important; font-size: 14px !important; display: flex !important; align-items: center !important; justify-content: center !important; border: 1px solid white !important; box-sizing: border-box !important; }
            .empty-button { margin: 0 !important; padding: 0 !important; width: 40px !important; height: 40px !important; border: 1px solid white !important; box-sizing: border-box !important; }
            .roulette-table { 
                display: flex !important; 
                flex-direction: column !important; 
                gap: 0 !important; 
                margin: 0 !important; 
                padding: 5px !important; 
                background-color: #2e7d32 !important;
                border: 2px solid #d3d3d3 !important; 
                border-radius: 5px !important; 
                width: 100% !important; 
                max-width: 600px !important; 
                margin: 0 auto !important; 
                overflow-x: auto !important;
                overflow-y: hidden !important;
            }
            .table-row { 
                display: flex !important; 
                gap: 0 !important; 
                margin: 0 !important; 
                padding: 0 !important; 
                flex-wrap: nowrap !important; 
                line-height: 0 !important; 
                min-width: 580px !important;
                white-space: nowrap !important;
            }
            
            /* Responsive adjustments for desktop */
            @media (min-width: 768px) {
                .roulette-table {
                    max-width: 800px !important;
                }
                .table-row {
                    min-width: 754px !important;
                }
                .roulette-button, .empty-button {
                    width: 48px !important;
                    height: 48px !important;
                    font-size: 16px !important;
                }
            }
            
            /* Buttons */    
            .action-button { min-width: 120px !important; padding: 5px 10px !important; font-size: 14px !important; width: 100% !important; box-sizing: border-box !important; }
            button.green-btn { background-color: #28a745 !important; color: white !important; border: 1px solid #000 !important; padding: 8px 16px !important; transition: transform 0.2s ease, box-shadow 0.2s ease !important; box-sizing: border-box !important; }
            button.green-btn:hover { background-color: #218838 !important; transform: scale(1.05) !important; box-shadow: 0 4px 8px rgba(0,0,0,0.3) !important; }
            
            button.green-btn {
                background-color: #28a745 !important;
                color: white !important;
                border: 1px solid #000 !important;
                padding: 8px 16px !important;
                transition: transform 0.2s ease, box-shadow 0.2s ease !important;
                box-sizing: border-box !important;
            }
            button.green-btn:hover {
                background-color: #218838 !important;
                transform: scale(1.05) !important;
                box-shadow: 0 4px 8px rgba(0,0,0,0.3) !important;
            }
            
            button.clear-spins-btn {
                background-color: #ff4444 !important;
                color: white !important;
                border: 1px solid #000 !important;
                box-sizing: border-box !important;
                display: inline-block !important;
            }
            button.clear-spins-btn:hover {
                background-color: #cc0000 !important;
            }
            button.generate-spins-btn { background-color: #007bff !important; color: white !important; border: 1px solid #000 !important; }
            button.generate-spins-btn:hover { background-color: #0056b3 !important; }
            
            /* NEW CODE: Add glow effect for buttons */
            .action-button, .green-btn, .roulette-button {
                transition: box-shadow 0.3s ease, transform 0.2s ease !important;
            }
            
            .action-button:active, .green-btn:active, .roulette-button:active {
                box-shadow: 0 0 10px 5px rgba(255, 215, 0, 0.7) !important; /* Yellow glow */
                transform: scale(1.05) !important; /* Slight scale for emphasis */
            }
            
            /* Ensure glow works on mobile touch */
            @media (max-width: 600px) {
                .action-button:active, .green-btn:active, .roulette-button:active {
                    box-shadow: 0 0 8px 4px rgba(255, 215, 0, 0.7) !important; /* Slightly smaller glow for mobile */
                }
            }
            
            /* Optional: Glow for specific buttons like Analyze Spins */
            .green-btn:active {
                box-shadow: 0 0 10px 5px rgba(40, 167, 69, 0.7) !important; /* Green glow for Analyze button */
            }
            
            /* Ensure columns have appropriate spacing */
            .gr-column { margin: 0 !important; padding: 5px !important; display: flex !important; flex-direction: column !important; align-items: stretch !important; }
            
            /* Compact Components */
            .long-slider { width: 100% !important; margin: 0 !important; padding: 0 !important; }
            .long-slider .gr-box { width: 100% !important; }
            
            /* Target the Accordion and its children */
            .gr-accordion { background-color: #ffffff !important; }
            .gr-accordion * { background-color: #ffffff !important; }
            .gr-accordion .gr-column { background-color: #ffffff !important; }
            .gr-accordion .gr-row { background-color: #ffffff !important; }
            
            /* Section Labels */
            #selected-spins label {
                background-color: #87CEEB;
                color: black;
                padding: 5px;
                border-radius: 3px;
            }
            #spin-analysis label {
                background-color: #90EE90 !important;
                color: black !important;
                padding: 5px;
                border-radius: 3px;
            }
            #strongest-numbers-table label {
                background-color: #E6E6FA !important;
                color: black !important;
                padding: 5px;
                border-radius: 3px;
            }
            #number-of-random-spins label {
                background-color: #FFDAB9 !important;
                color: black !important;
                padding: 5px;
                border-radius: 3px;
            }
            #aggregated-scores label {
                background-color: #FFB6C1 !important;
                color: black !important;
                padding: 5px;
                border-radius: 3px;
            }
            
            /* Compact dropdown styling for Select Category and Select Strategy */
            #select-category select, #strategy-dropdown select {
                max-height: 150px !important;
                overflow-y: auto !important;
                scrollbar-width: thin !important;
            }
            #select-category select::-webkit-scrollbar, #strategy-dropdown select::-webkit-scrollbar {
                width: 6px;
            }
            #select-category select::-webkit-scrollbar-thumb, #strategy-dropdown select::-webkit-scrollbar-thumb {
                background-color: #888;
                border-radius: 3px;
            }
            
            /* Scrollable Tables */
            .scrollable-table {
                max-height: 300px;
                overflow-y: auto;
                display: block;
                width: 100%;
            }
            
            /* Updated styling for the Dynamic Roulette Table */
            .large-table {
                max-height: 800px !important;
                max-width: 1000px !important;
                margin: 0 auto !important;
                display: block !important;
                background: linear-gradient(135deg, #f0f0f0, #e0e0e0) !important;
                border: 2px solid #3b82f6 !important;
                border-radius: 10px !important;
                box-shadow: 0 0 15px rgba(59, 130, 246, 0.5) !important;
                padding: 10px !important;
            }
            /* Dynamic Table Container */
            .dynamic-table-container {
                width: 100% !important;
                max-width: 1200px !important;
                margin: 0 auto !important;
                padding: 20px 10px !important;
                display: flex !important;
                flex-direction: column !important; /* Ensure children stack vertically */
                justify-content: center !important;
                align-items: center !important;
                box-sizing: border-box !important;
            }
            
            /* Ensure all children of the container are centered */
            .dynamic-table-container > * {
                width: 100% !important;
                max-width: 900px !important; /* Match the large-table max-width */
                margin: 0 auto !important;
            }
            
            /* Large Table */
            .large-table {
                max-height: 800px !important;
                max-width: 900px !important;
                width: 100% !important;
                margin: 0 auto !important;
                display: block !important;
                background: linear-gradient(135deg, #f0f0f0, #e0e0e0) !important;
                border: 2px solid #3b82f6 !important;
                border-radius: 12px !important;
                box-shadow: 0 0 20px rgba(59, 130, 246, 0.6) !important;
                padding: 15px !important;
                box-sizing: border-box !important;
                overflow: visible !important;
                text-align: center !important; /* Center table content */
                animation: tableFadeIn 0.5s ease-in-out !important; /* Add load animation */
                /* Add gradient border */
                background-clip: padding-box !important;
                border-image: linear-gradient(45deg, #3b82f6, #1e90ff) 1 !important;
            }
            
            /* Define the load animation */
            @keyframes tableFadeIn {
                0% {
                    opacity: 0;
                    transform: scale(0.95);
                }
                100% {
                    opacity: 1;
                    transform: scale(1);
                }
            }
            
            .large-table table {
                width: 100% !important;
                max-width: 100% !important;
                margin: 0 auto !important;
                text-align: center !important;
            }
            
            .large-table th {
                font-weight: bold !important;
                color: #000000 !important;
                text-shadow: 0 0 5px rgba(0, 0, 0, 0.3) !important;
                background: rgba(59, 130, 246, 0.1) !important;
                padding: 10px !important;
            }
            
            .large-table td {
                padding: 8px !important;
                text-align: center !important;
                position: relative !important;
                overflow: visible !important;
            }
            
            /* Glowing Hover Effects for Hot Numbers (specific to Dynamic Roulette Table) */
            .dynamic-roulette-table td.hot-number:hover {
                box-shadow: 0 0 12px 4px #ffd700 !important;
                transform: scale(1.1) !important;
                transition: all 0.3s ease !important;
            }
            
            /* NEW: Enhanced Hot Number Corner Flash Effect */
            .dynamic-roulette-table td.hot-number {
                position: relative !important;
                overflow: visible !important;
            }
            
            /* Top-left corner highlight */
            .dynamic-roulette-table td.hot-number::before {
                content: '' !important;
                position: absolute !important;
                top: -3px !important;
                left: -3px !important;
                width: 10px !important;
                height: 10px !important;
                background-color: #ffd700 !important; /* Yellow to match existing glow */
                border: 1px solid #ffffff !important; /* White border for contrast */
                animation: flashCorner 1.5s ease-in-out infinite !important;
                z-index: 5 !important;
            }
            
            /* Bottom-right corner highlight */
            .dynamic-roulette-table td.hot-number::after {
                content: '' !important;
                position: absolute !important;
                bottom: -3px !important;
                right: -3px !important;
                width: 10px !important;
                height: 10px !important;
                background-color: #ffd700 !important;
                border: 1px solid #ffffff !important;
                animation: flashCorner 1.5s ease-in-out infinite !important;
                z-index: 5 !important;
            }
            
            /* Flashing animation for corners */
            @keyframes flashCorner {
                0%, 100% {
                    opacity: 1 !important;
                    transform: scale(1) !important;
                }
                50% {
                    opacity: 0.5 !important;
                    transform: scale(1.2) !important;
                }
            }
            
            /* Ensure hover effect remains intact and complements corner flash */
            .dynamic-roulette-table td.hot-number:hover {
                box-shadow: 0 0 12px 4px #ffd700 !important;
                transform: scale(1.1) !important;
                transition: all 0.3s ease !important;
                z-index: 10 !important; /* Ensure hover effect is above corners */
            }
            
            /* Responsive adjustments for smaller screens */
            @media (max-width: 768px) {
                .dynamic-roulette-table td.hot-number::before,
                .dynamic-roulette-table td.hot-number::after {
                    width: 8px !important;
                    height: 8px !important;
                    top: -2px !important;
                    left: -2px !important;
                    bottom: -2px !important;
                    right: -2px !important;
                }
            }
            
            /* Tooltip Styles for Number Cells */
            .dynamic-roulette-table td.has-tooltip:hover::after {
                content: attr(data-tooltip) !important;
                position: absolute !important;
                background: #333 !important;
                color: #fff !important;
                padding: 5px 10px !important;
                border-radius: 4px !important;
                border: 1px solid #8c6bb1 !important;
                bottom: 100% !important;
                left: 50% !important;
                transform: translateX(-50%) !important;
                white-space: nowrap !important;
                z-index: 10 !important;
                font-size: 12px !important;
                font-family: Arial, sans-serif !important;
                animation: fadeIn 0.3s ease !important;
            }
            
            @keyframes fadeIn {
                0% { opacity: 0; transform: translateX(-50%) translateY(5px); }
                100% { opacity: 1; transform: translateX(-50%) translateY(0); }
            }
            
            /* Bet Tier Icons with Bounce Animation */
            .dynamic-roulette-table td.top-tier::before {
                content: "🔥" !important;
                margin-right: 5px !important;
                display: inline-block !important;
                animation: bounce 0.5s ease-in-out !important;
            }
            
            .dynamic-roulette-table td.middle-tier::before {
                content: "⭐" !important;
                margin-right: 5px !important;
                display: inline-block !important;
                animation: bounce 0.5s ease-in-out !important;
            }
            
            .dynamic-roulette-table td.lower-tier::before {
                content: "🌟" !important;
                margin-right: 5px !important;
                display: inline-block !important;
                animation: bounce 0.5s ease-in-out !important;
            }
            
            @keyframes bounce {
                0%, 100% { transform: translateY(0); }
                50% { transform: translateY(-5px); }
            }
            
            /* Progress Bar Styles for Bet Strength */
            .dynamic-roulette-table .progress-bar {
                width: 100% !important;
                height: 5px !important;
                background: #d3d3d3 !important;
                border-radius: 3px !important;
                margin-top: 3px !important;
                position: relative !important;
                display: block !important;
            }
            
            .dynamic-roulette-table .progress-fill.top-tier {
                height: 100% !important;
                background: #ffd700 !important; /* Yellow for top-tier */
                border-radius: 3px !important;
                position: absolute !important;
                top: 0 !important;
                left: 0 !important;
            }
            
            .dynamic-roulette-table .progress-fill.middle-tier {
                height: 100% !important;
                background: #00ffff !important; /* Cyan for middle-tier */
                border-radius: 3px !important;
                position: absolute !important;
                top: 0 !important;
                left: 0 !important;
            }
            
            .dynamic-roulette-table .progress-fill.lower-tier {
                height: 100% !important;
                background: #00ff00 !important; /* Green for lower-tier */
                border-radius: 3px !important;
                position: absolute !important;
                top: 0 !important;
                left: 0 !important;
            }
            
            /* Responsive adjustments */
            @media (max-width: 1200px) {
                .dynamic-table-container {
                    max-width: 90vw !important;
                    padding: 15px 5px !important;
                }
            
                .dynamic-table-container > * {
                    max-width: 95% !important;
                }
            
                .large-table {
                    max-width: 95% !important;
                    padding: 12px !important;
                }
            }
            
            @media (max-width: 768px) {
                .dynamic-table-container {
                    max-width: 100vw !important;
                    padding: 10px 5px !important;
                }
            
                .dynamic-table-container > * {
                    max-width: 100% !important;
                }
            
                .large-table {
                    max-width: 100% !important;
                    padding: 10px !important;
                }
            }
            
            /* Strategy Card Container */
            .strategy-card {
                max-width: 1000px !important;
                margin: 0 auto !important;
                padding: 20px !important;
                background: linear-gradient(135deg, #2a2a72, #4682b4) !important; /* Match the aesthetic of other sections */
                border: 2px solid #3b82f6 !important;
                border-radius: 12px !important;
                box-shadow: 0 0 15px rgba(59, 130, 246, 0.5) !important;
                display: flex !important;
                flex-direction: column !important;
                gap: 10px !important;
                animation: cardFadeIn 0.5s ease-in-out !important; /* Add load animation */
            }
            
            /* Load animation for the strategy card */
            @keyframes cardFadeIn {
                0% {
                    opacity: 0;
                    transform: translateY(10px);
                }
                100% {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            /* Style for dropdowns within the strategy card */
            .strategy-card .gr-dropdown {
                background: rgba(59, 130, 246, 0.1) !important;
                border: 1px solid #3b82f6 !important;
                border-radius: 5px !important;
                margin: 5px 0 !important;
            }
            
            .strategy-card .gr-dropdown select {
                background: transparent !important;
                color: #ffffff !important;
                border: none !important;
                font-size: 14px !important;
                padding: 5px !important;
            }
            
            .strategy-card .gr-dropdown label {
                background: transparent !important;
                color: #ffffff !important;
                text-shadow: 0 0 5px rgba(59, 130, 246, 0.5) !important;
                padding: 5px !important;
            }
            
            /* Style for the reset button */
            .strategy-card .gr-button {
                background: #3b82f6 !important;
                color: #ffffff !important;
                border: 1px solid #3b82f6 !important;
                border-radius: 5px !important;
                box-shadow: 0 0 5px rgba(59, 130, 246, 0.5) !important;
                transition: background 0.3s ease, transform 0.2s ease !important;
            }
            
            .strategy-card .gr-button:hover {
                background: #1e90ff !important;
                transform: scale(1.05) !important;
            }
            
            /* Style for sliders */
            .strategy-card .gr-slider {
                background: rgba(59, 130, 246, 0.1) !important;
                border: 1px solid #3b82f6 !important;
                border-radius: 5px !important;
                color: #ffffff !important;
                text-shadow: 0 0 5px rgba(59, 130, 246, 0.5) !important;
            }
            
            /* Style for the strategy recommendations output */
            .strategy-card .strategy-box {
                max-height: 300px !important;
                overflow-y: auto !important;
                padding: 10px !important;
                background: rgba(255, 255, 255, 0.05) !important; /* Slightly lighter background for contrast */
                border-radius: 8px !important;
                box-shadow: inset 0 0 5px rgba(59, 130, 246, 0.3) !important;
                animation: outputFadeIn 0.5s ease-in-out !important; /* Add load animation for the output */
            }
            
            .strategy-card .strategy-box p, .strategy-card .strategy-box span, .strategy-card .strategy-box ul, .strategy-card .strategy-box li {
                color: #ffffff !important;
                text-shadow: 0 0 5px rgba(59, 130, 246, 0.3) !important;
                font-size: 14px !important;
            }
            
            /* Load animation for the strategy output */
            @keyframes outputFadeIn {
                0% {
                    opacity: 0;
                    transform: scale(0.98);
                }
                100% {
                    opacity: 1;
                    transform: scale(1);
                }
            }
            
            /* Ensure the row inside the card layouts dropdowns properly */
            .strategy-card .gr-row {
                display: flex !important;
                gap: 10px !important;
                flex-wrap: wrap !important;
                justify-content: center !important;
            }
            
            /* Responsive adjustments */
            @media (max-width: 768px) {
                .strategy-card {
                    padding: 15px !important;
                }
            
                .strategy-card .gr-row {
                    flex-direction: column !important;
                    align-items: center !important;
                }
            
                .strategy-card .gr-dropdown {
                    width: 100% !important;
                    max-width: 300px !important;
                }
            
                .strategy-card .gr-button {
                    width: 100% !important;
                    max-width: 300px !important;
                }
            }
            
            .strongest-numbers-table {
                width: 100% !important;
                max-width: 100% !important;
                background: linear-gradient(135deg, #2a2a72, #4682b4) !important;
                border-collapse: collapse !important;
                border: 1px solid #3b82f6 !important;
                box-shadow: 0 0 10px rgba(59, 130, 246, 0.5) !important;
                margin: 10px 0 !important;
            }
            
            .strongest-numbers-table th, .strongest-numbers-table td {
                padding: 8px 12px !important;
                border: 1px solid #3b82f6 !important;
                text-align: center !important;
                color: #ffffff !important;
                text-shadow: 0 0 5px rgba(59, 130, 246, 0.7) !important;
            }
            
            .strongest-numbers-table th {
                background: rgba(59, 130, 246, 0.2) !important;
                font-weight: bold !important;
            }
            
            .strongest-numbers-table td:nth-child(3), 
            .strongest-numbers-table td:nth-child(6), 
            .strongest-numbers-table td:nth-child(9) {
                white-space: normal !important;
                word-wrap: break-word !important;
                max-width: 150px !important;
            }
            
            /* Last Spins Container */
            .last-spins-container {
                background-color: #f5f5f5 !important;
                border: 1px solid #d3d3d3 !important;
                padding: 10px !important;
                border-radius: 5px !important;
                margin-top: 10px !important;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1) !important;
            }
            
            /* Fade-in animation for Last Spins */
            .fade-in {
                animation: fadeIn 0.5s ease-in;
            }
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            
            /* Pattern Badge for Spin Patterns */
            .pattern-badge {
                background-color: #ffd700 !important;
                color: #333 !important;
                padding: 2px 5px !important;
                border-radius: 3px !important;
                font-size: 10px !important;
                margin-left: 5px !important;
                cursor: pointer !important;
                transition: transform 0.2s ease !important;
            }
            .pattern-badge:hover {
                transform: scale(1.1) !important;
                box-shadow: 0 0 8px #ffd700 !important;
            }
            
            /* Quick Trends Section for SpinTrend Radar */
            .quick-trends {
                background: linear-gradient(135deg, #d8bfd8 0%, #e6e6fa 100%) !important;
                padding: 12px !important;
                border-radius: 6px !important;
                margin-bottom: 12px !important;
                border: 1px solid #8c6bb1 !important;
                box-shadow: 0 0 8px rgba(140, 107, 177, 0.3) !important;
            }
            
            .quick-trends h4 {
                margin: 0 0 8px 0 !important;
                font-size: 16px !important;
                color: #ff66cc !important;
                text-shadow: 0 0 4px rgba(255, 102, 204, 0.5) !important;
                font-weight: bold !important;
            }
            
            .quick-trends ul {
                margin: 0 !important;
                padding-left: 15px !important;
            }
            
            .quick-trends ul li {
                color: #3e2723 !important;
                font-size: 14px !important;
                margin: 4px 0 !important;
                font-weight: 500 !important;
            }
            
            /* Spin animation for roulette table buttons */
            .roulette-button:active {
                animation: spin 0.5s ease-in-out !important;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            /* Flash animation for new spins */
            .flash.red {
                animation: flashRed 0.3s ease-in-out;
            }
            .flash.green {
                animation: flashGreen 0.3s ease-in-out;
            }
            .flash.black {
                animation: flashBlack 0.3s ease-in-out;
            }
            @keyframes flashRed {
                0%, 100% { background-color: red; }
                50% { background-color: #ff3333; }
            }
            @keyframes flashGreen {
                0%, 100% { background-color: green; }
                50% { background-color: #33cc33; }
            }
            @keyframes flashBlack {
                0%, 100% { background-color: black; }
                50% { background-color: #333333; }
            }
            
            /* Bounce animation for Dealer's Spin Tracker numbers */
            .bounce {
                animation: bounce 0.4s ease-in-out;
            }
            @keyframes bounce {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.2); }
            }
            
            /* New: Flip animation for Last Spins new numbers */
            .flip {
                animation: flip 0.5s ease-in-out;
            }
            @keyframes flip {
                0% { transform: rotateY(0deg); }
                100% { transform: rotateY(360deg); }
            }
            
            /* New Spin Highlight Effect */
            .new-spin {
                position: relative !important;
                animation: pulse-highlight 1s ease-in-out !important;
            }
            
            @keyframes pulse-highlight {
                0%, 100% { box-shadow: none; }
                50% { box-shadow: 0 0 10px 5px var(--highlight-color); }
            }
            
            /* Color-coded highlights for new spins */
            .new-spin.spin-red {
                --highlight-color: rgba(255, 0, 0, 0.8) !important;
            }
            .new-spin.spin-black {
                --highlight-color: rgba(255, 255, 255, 0.8) !important;
            }
            .new-spin.spin-green {
                --highlight-color: rgba(0, 255, 0, 0.8) !important;
            }
            
            /* Spin Counter Styling */
            .spin-counter {
                font-size: 14px !important; /* Smaller text */
                font-weight: bold !important;
                color: #ffffff !important;
                background: linear-gradient(135deg, #2e7d32, #1b5e20) !important;
                padding: 6px 12px !important; /* Reduced padding */
                border: 1px solid #ffffff !important; /* Thinner border */
                border-radius: 8px !important; /* Slightly smaller radius */
                margin: 5px auto !important; /* Less margin */
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3) !important; /* Smaller shadow */
                text-shadow: 0 1px 1px rgba(0, 0, 0, 0.5) !important;
                transition: transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease !important;
                position: relative !important;
            }
            .spin-counter:hover {
                transform: scale(1.1) !important;
                box-shadow: 0 0 10px 3px rgba(255, 215, 0, 0.7) !important; /* Smaller glow */
                border-color: #ffd700 !important;
                animation: sparkle-and-pulse 0.6s ease-in-out !important;
            }
            .spin-counter:hover::after {
                content: attr(data-tip);
                position: absolute !important;
                top: -45px !important; /* Adjusted for smaller counter */
                left: 50% !important;
                transform: translateX(-50%) !important;
                background: #333 !important;
                color: #fff !important;
                padding: 3px 6px !important; /* Smaller padding */
                border-radius: 3px !important;
                font-size: 9px !important; /* Smaller font */
                max-width: 120px !important; /* Smaller width */
                white-space: normal !important;
                text-align: center !important;
                z-index: 10 !important;
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3) !important;
            }
            .spin-counter.glow {
                animation: casino-flicker 1.8s ease-in-out infinite, color-shift 1.8s ease-in-out infinite !important;
            }
            .spin-counter.milestone {
                animation: milestone-glow 1s ease-out !important;
            }
            @keyframes sparkle-and-pulse {
                0% {
                    transform: scale(1);
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
                    border-color: #ffffff;
                }
                50% {
                    transform: scale(1.15);
                    box-shadow: 0 0 15px 5px rgba(255, 215, 0, 0.8);
                    border-color: #ffd700;
                }
                100% {
                    transform: scale(1.1);
                    box-shadow: 0 0 10px 3px rgba(255, 215, 0, 0.7);
                    border-color: #ffd700;
                }
            }
            @keyframes casino-flicker {
                0% {
                    transform: scale(1);
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
                    border-color: #ffffff;
                }
                33% {
                    transform: scale(1.05);
                    box-shadow: 0 0 8px 4px rgba(255, 0, 0, 0.6);
                    border-color: #ff0000;
                }
                66% {
                    transform: scale(1.03);
                    box-shadow: 0 0 8px 4px rgba(0, 128, 0, 0.6);
                    border-color: #008000;
                }
                100% {
                    transform: scale(1);
                    box-shadow: 0 0 8px 4px rgba(255, 255, 255, 0.6);
                    border-color: #ffffff;
                }
            }
            @keyframes color-shift {
                0% { color: #ffffff; }
                33% { color: #ff0000; }
                66% { color: #008000; }
                100% { color: #ffffff; }
            }
            @keyframes milestone-glow {
                0% {
                    border-color: #ffffff;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
                }
                50% {
                    border-color: #ffd700;
                    box-shadow: 0 0 15px 7px rgba(255, 215, 0, 0.8);
                }
                100% {
                    border-color: #ffffff;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
                }
            }
            
            /* Pattern Alert Icons for Quick Trends */
            .trend-icon {
                display: inline-block;
                font-size: 16px;
                margin-right: 5px;
                animation: subtle-rotate 2s linear infinite;
            }
            .trend-icon.hot { color: #ff4500; }
            .trend-icon.cold { color: #00b7eb; }
            .trend-icon.streak { color: #ffd700; }
            @keyframes subtle-rotate {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            .quick-trends li {
                display: flex;
                align-items: center;
                padding: 5px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 5px;
                margin-bottom: 5px;
            }
            
            /* Quick Bet Suggestions for Quick Trends */
            .bet-suggestion {
                color: #ff4500;
                font-style: italic;
                background: rgba(255, 69, 0, 0.1);
                padding: 5px;
                border-radius: 5px;
                display: flex;
                align-items: center;
                font-weight: bold;
                box-shadow: 0 0 5px rgba(255, 69, 0, 0.3);
            }
            
            /* Debug Highlight for SpinTrend Radar */
            .traits-overview.debug-highlight {
                background: rgba(200, 200, 200, 0.2);
                padding: 10px;
                border: 1px solid #999;
            }
            
            /* Ensure Traits Wrapper is Visible */
            .traits-wrapper {
                position: relative;
                overflow: visible;
                padding-bottom: 20px;
            }
            
            /* Red/Black Switch Alert */
            .switch-alert {
                display: flex;
                gap: 4px;
                padding: 10px;
                background: rgba(255, 255, 255, 0.5);
                border: 2px solid #666;
                border-radius: 6px;
                margin-top: 15px;
                justify-content: center;
                min-height: 40px;
                align-items: center;
                position: relative;
                z-index: 100;
            }
            .switch-dot {
                width: 14px;
                height: 14px;
                border-radius: 50%;
            }
            .switch-dot.red { background: #ff4444; }
            .switch-dot.black { background: #000000; }
            .switch-dot.green { background: #388e3c; }
            .switch-alert.high-switches {
                border: 2px solid #ffd700;
                animation: flash-border 1s infinite ease-in-out;
            }
            @keyframes flash-border {
                0%, 100% { border-color: #ffd700; }
                50% { border-color: #ffa500; }
            }
            .switch-alert:hover::after {
                content: attr(data-tooltip);
                position: absolute;
                background: #333;
                color: #fff;
                padding: 5px;
                border-radius: 3px;
                top: -35px;
                left: 50%;
                transform: translateX(-50%);
                font-size: 12px;
                z-index: 101;
            }
            
            /* Dozen Shift Indicator */
            .dozen-shift-indicator {
                display: flex;
                align-items: center;
                padding: 8px;
                background: rgba(255, 255, 255, 0.3);
                border-radius: 6px;
                margin-top: 10px;
                justify-content: center;
                position: relative;
                z-index: 100;
            }
            .dozen-badge {
                display: inline-block;
                font-size: 12px;
                color: #fff;
                background: #388e3c;
                border-radius: 3px;
                padding: 2px 4px;
                animation: bounce 1s infinite ease-in-out;
            }
            .dozen-badge.d1 { background: #388e3c; }
            .dozen-badge.d2 { background: #ff9800; }
            .dozen-badge.d3 { background: #8e24aa; }
            @keyframes bounce {
                0%, 100% { transform: translateY(0); }
                50% { transform: translateY(-3px); }
            }
            .dozen-shift-indicator:hover::after {
                content: attr(data-tooltip);
                position: absolute;
                background: #333;
                color: #fff;
                padding: 5px;
                border-radius: 3px;
                top: -30px;
                left: 50%;
                transform: translateX(-50%);
                font-size: 12px;
                z-index: 101;
            }
            
            /* Enhanced Red/Black Chopping Alert within Quick Trends */
            .quick-trends .switch-alert {
                display: flex !important;
                flex-direction: column !important;
                align-items: flex-start !important;
                gap: 6px !important;
                padding: 8px !important;
                background: rgba(255, 255, 255, 0.2) !important;
                border: 1px solid #999 !important;
                border-radius: 5px !important;
                margin: 5px 0 !important;
                width: 100% !important;
                box-sizing: border-box !important;
                position: relative !important;
                z-index: 10 !important;
                transition: all 0.3s ease !important;
            }
            
            .quick-trends .switch-dots-container {
                display: flex !important;
                gap: 5px !important;
            }
            
            .quick-trends .switch-dot {
                width: 14px !important;
                height: 14px !important;
                border-radius: 50% !important;
                border: 1px solid #fff !important;
                box-shadow: 0 0 3px rgba(0, 0, 0, 0.2) !important;
            }
            
            .quick-trends .switch-dot.red { background: #ff4444 !important; }
            .quick-trends .switch-dot.black { background: #000000 !important; }
            .quick-trends .switch-dot.green { background: #388e3c !important; }
            
            .quick-trends .switch-alert.high-switches {
                border: 2px solid #ffd700 !important;
                background: rgba(255, 215, 0, 0.15) !important;
                animation: chopping-glow 1.5s ease-in-out infinite !important;
            }
            
            .quick-trends .chopping-alert {
                display: flex !important;
                align-items: center !important;
                gap: 6px !important;
                padding: 8px !important;
                color: #ff4500 !important;
                font-weight: bold !important;
                font-size: 13px !important;
                text-align: left !important;
                text-shadow: 0 0 3px rgba(255, 69, 0, 0.4) !important;
                border-radius: 5px !important;
                z-index: 11 !important;
            }
            
            @keyframes chopping-glow {
                0%, 100% {
                    box-shadow: 0 0 8px rgba(255, 215, 0, 0.4) !important;
                    border-color: #ffd700 !important;
                }
                50% {
                    box-shadow: 0 0 15px rgba(255, 215, 0, 0.7) !important;
                    border-color: #ffa500 !important;
                }
            }
            
            .quick-trends .switch-alert:hover::after {
                content: attr(data-tooltip) !important;
                position: absolute !important;
                background: #333 !important;
                color: #fff !important;
                padding: 5px 10px !important;
                border-radius: 4px !important;
                top: -35px !important;
                left: 50% !important;
                transform: translateX(-50%) !important;
                font-size: 11px !important;
                z-index: 11 !important;
                white-space: nowrap !important;
            }
            
            .quick-trends .red-badge {
                display: inline-block !important;
                width: 14px !important;
                height: 14px !important;
                background: #ff4444 !important;
                border-radius: 50% !important;
                border: 1px solid #fff !important;
                box-shadow: 0 0 3px rgba(0, 0, 0, 0.2) !important;
                z-index: 11 !important;
            }
            
            .quick-trends .black-badge {
                display: inline-block !important;
                width: 14px !important;
                height: 14px !important;
                background: #000000 !important;
                border-radius: 50% !important;
                border: 1px solid #fff !important;
                box-shadow: 0 0 3px rgba(0, 0, 0, 0.2) !important;
                z-index: 11 !important;
            }
            
            .quick-trends .dozen-alert.d1 {
                background: #FF6347 !important; /* Tomato red for 1st Dozen */
                padding: 8px !important;
                border-radius: 5px !important;
                z-index: 10 !important;
            }
            
            .quick-trends .dozen-alert.d2 {
                background: #4682B4 !important; /* Steel blue for 2nd Dozen */
                padding: 8px !important;
                border-radius: 5px !important;
                z-index: 10 !important;
            }
            
            .quick-trends .dozen-alert.d3 {
                background: #32CD32 !important; /* Lime green for 3rd Dozen */
                padding: 8px !important;
                border-radius: 5px !important;
                z-index: 10 !important;
            }
            
            /* Dozen Shift Indicator within Quick Trends */
            .quick-trends .dozen-shift-indicator {
                display: flex !important;
                align-items: center !important;
                gap: 5px !important;
                padding: 8px !important;
                background: rgba(255, 255, 255, 0.2) !important;
                border: 1px solid #999 !important;
                border-radius: 5px !important;
                margin: 5px 0 !important;
                width: 100% !important;
                box-sizing: border-box !important;
                position: relative !important;
                z-index: 10 !important;
                transition: all 0.3s ease !important;
            }
            
            .quick-trends .dozen-badge {
                display: inline-block !important;
                font-size: 12px !important;
                color: #fff !important;
                border-radius: 3px !important;
                padding: 2px 4px !important;
                animation: bounce 1s infinite ease-in-out !important;
            }
            
            .quick-trends .dozen-badge.d1 { background: #388e3c !important; }
            .quick-trends .dozen-badge.d2 { background: #ff9800 !important; }
            .quick-trends .dozen-badge.d3 { background: #8e24aa !important; }
            
            @keyframes bounce {
                0%, 100% { transform: translateY(0) !important; }
                50% { transform: translateY(-3px) !important; }
            }
            
            .quick-trends .dozen-shift-indicator:hover::after {
                content: attr(data-tooltip) !important;
                position: absolute !important;
                background: #333 !important;
                color: #fff !important;
                padding: 5px 10px !important;
                border-radius: 4px !important;
                top: -35px !important;
                left: 50% !important;
                transform: translateX(-50%) !important;
                font-size: 11px !important;
                z-index: 11 !important;
                white-space: nowrap !important;
            }
            
            /* Responsive adjustments */
            @media (max-width: 600px) {
                .quick-trends .switch-alert,
                .quick-trends .dozen-shift-indicator {
                    padding: 6px !important;
                }
                .quick-trends .switch-dot {
                    width: 12px !important;
                    height: 12px !important;
                }
                .quick-trends .chopping-alert {
                    font-size: 12px !important;
                }
                .quick-trends .dozen-badge {
                    font-size: 11px !important;
                    padding: 1px 3px !important;
                }
                .quick-trends .dozen-shift-indicator span:not(.dozen-badge) {
                    font-size: 11px !important;
                }
            }
        </style>
        <script>
            function debounce(func, wait) {
                let timeout;
                return function executedFunction(...args) {
                    const later = () => {
                        clearTimeout(timeout);
                        func(...args);
                    };
                    clearTimeout(timeout);
                    timeout = setTimeout(later, wait);
                };
            }
            
            const rouletteTips = [
                "Bet on neighbors of hot numbers for better odds!",
                "Red and black have equal chances, but zero is green!",
                "Try the Martingale strategy for even-money bets.",
                "Dozens cover 12 numbers for a balanced risk.",
                "Watch for dealer biases in the Spin Tracker!",
                "Fibonacci betting can manage your bankroll.",
                "Columns offer a 2:1 payout—worth a try!",
                "Zero’s neighbors are hot in European roulette."
            ];
            
            function setRandomTip() {
                const counter = document.querySelector('.spin-counter');
                if (counter) {
                    const randomTip = rouletteTips[Math.floor(Math.random() * rouletteTips.length)];
                    counter.setAttribute('data-tip', randomTip);
                }
            }
            
            function playChipSound() {
                const audio = new Audio('https://example.com/chip_clink.mp3'); // Replace with your sound file URL
                audio.play().catch(error => console.log('Audio play failed:', error));
            }

            function updateSpinCounter() {
                const counter = document.querySelector('.spin-counter');
                if (counter) {
                    // Temporarily disconnect the observer to prevent infinite loops
                    if (window.spinObserver) {
                        window.spinObserver.disconnect();
                    }

                    const match = counter.textContent.match(/\\d+/);
                    const currentCount = match ? parseInt(match[0]) : 0;
                    
                    // Add visual and audio feedback
                    counter.classList.add('glow');
                    playChipSound();
                    if (currentCount === 10 || currentCount === 50 || currentCount === 100) {
                        counter.classList.add('milestone');
                        setTimeout(() => counter.classList.remove('milestone'), 1000);
                    }

                    // Reconnect observer
                    if (window.spinObserver) {
                        window.spinObserver.observe(counter, { childList: true, characterData: true, subtree: true });
                    }
                }
            }

            document.addEventListener('DOMContentLoaded', () => {
                const counter = document.querySelector('.spin-counter');
                if (counter) {
                    // Bind to global window variable so we can disconnect/reconnect it
                    window.spinObserver = new MutationObserver(() => updateSpinCounter());
                    window.spinObserver.observe(counter, { childList: true, characterData: true, subtree: true });
                    counter.addEventListener('mouseenter', setRandomTip);
                    setRandomTip(); // Set initial tip
                }
            });
        </script>
    """)
    logger.debug("CSS Updated")
    
    
    # Shepherd.js Tour Script
    gr.HTML("""
    <link rel="stylesheet" href="https://unpkg.com/shepherd.js@10.0.1/dist/css/shepherd.css">
    <script src="https://unpkg.com/shepherd.js@10.0.1/dist/js/shepherd.min.js" onerror="loadShepherdFallback()"></script>
    <script>
      function loadShepherdFallback() {
        console.warn('Shepherd.js CDN failed to load. Attempting to load from fallback...');
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/shepherd.js@10.0.1/dist/js/shepherd.min.js';
        script.onerror = () => {
          console.error('Shepherd.js fallback also failed. Tour will be unavailable.');
          alert('Tour unavailable: Shepherd.js failed to load from both sources. Please try again later.');
        };
        document.head.appendChild(script);
    
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = 'https://cdn.jsdelivr.net/npm/shepherd.js@10.0.1/dist/css/shepherd.css';
        document.head.appendChild(link);
      }
    
      const tour = new Shepherd.Tour({
        defaultStepOptions: {
          cancelIcon: { enabled: true },
          scrollTo: { behavior: 'smooth', block: 'center' },
          classes: 'shepherd-theme-arrows',
          buttons: [
            { text: 'Back', action: function() { return this.back(); } },
            { text: 'Next', action: function() { return this.next(); } },
            { text: 'Skip', action: function() { return this.cancel(); } }
          ]
        },
        useModalOverlay: true
      });
    
      function logStep(stepId, nextStepId) {
        return () => {
          console.log(`Moving from ${stepId} to ${nextStepId}`);
          tour.next();
        };
      }
    
      function forceAccordionOpen(accordionSelector) {
        console.log(`Attempting to open accordion: ${accordionSelector}`);
        return new Promise(resolve => {
          const accordion = document.querySelector(accordionSelector);
          if (!accordion) {
            console.warn(`Accordion ${accordionSelector} not found`);
            resolve();
            return;
          }
          console.log(`Accordion DOM structure:`, accordion.outerHTML.slice(0, 200));
          const toggle = accordion.querySelector('input.accordion-toggle');
          const content = accordion.querySelector('.accordion-content');
          if (toggle && content && window.getComputedStyle(content).display === 'none') {
            console.log(`Opening ${accordionSelector} via toggle`);
            toggle.checked = true;
            content.style.display = 'block !important';
            accordion.setAttribute('open', '');
            setTimeout(() => {
              if (window.getComputedStyle(content).display === 'none') {
                console.warn(`Fallback: Forcing visibility for ${accordionSelector}`);
                content.style.display = 'block !important';
              }
              resolve();
            }, 500);
          } else {
            console.log(`${accordionSelector} already open or no toggle/content found`);
            resolve();
          }
        });
      }
    
      tour.addStep({
        id: 'part1',
        title: 'Your Roulette Adventure Begins!',
        text: 'Welcome to the Roulette Spin Analyzer! This tour will guide you through the key features to master your game.<br><iframe width="280" height="158" src="https://www.youtube.com/embed/H7TLQr1HnY0?fs=0" frameborder="0"></iframe>',
        attachTo: { element: '#header-row', on: 'bottom' },
        buttons: [
          { text: 'Next', action: logStep('Part 1', 'Part 2') },
          { text: 'Skip', action: tour.cancel }
        ]
      });
    
      tour.addStep({
        id: 'part2',
        title: 'Spin the Wheel, Start the Thrill!',
        text: 'Click numbers on the European Roulette Table to record spins and track your game.<br><iframe width="280" height="158" src="https://www.youtube.com/embed/ja454kZwndo?fs=0" frameborder="0"></iframe>',
        attachTo: { element: '.roulette-table', on: 'right' },
        buttons: [
          { text: 'Back', action: tour.back },
          { text: 'Next', action: logStep('Part 2', 'Part 3') },
          { text: 'Skip', action: tour.cancel }
        ]
      });
    
      tour.addStep({
        id: 'part3',
        title: 'Peek at Your Spin Streak!',
        text: 'View your recent spins here, color-coded for easy tracking.<br><iframe width="280" height="158" src="https://www.youtube.com/embed/a9brOFMy9sA?fs=0" frameborder="0"></iframe>',
        attachTo: { element: '.last-spins-container', on: 'bottom' },
        buttons: [
          { text: 'Back', action: tour.back },
          { text: 'Next', action: logStep('Part 3', 'Part 4') },
          { text: 'Skip', action: tour.cancel }
        ]
      });
    
      tour.addStep({
        id: 'part4',
        title: 'Master Your Spin Moves!',
        text: 'Use these buttons to undo spins, generate random spins, or clear the display.<br><iframe width="280" height="158" src="https://www.youtube.com/embed/xG8z1S4HJK4?fs=0" frameborder="0"></iframe>',
        attachTo: { element: '#undo-spins-btn', on: 'bottom' },
        buttons: [
          { text: 'Back', action: tour.back },
          { text: 'Next', action: logStep('Part 4', 'Part 5') },
          { text: 'Skip', action: tour.cancel }
        ]
      });
    
      tour.addStep({
        id: 'part5',
        title: 'Jot Spins, Count Wins!',
        text: 'Manually enter spins here (e.g., 5, 12, 0) to analyze your game.<br><iframe width="280" height="158" src="https://www.youtube.com/embed/2-k1EyKUM8U?fs=0" frameborder="0"></iframe>',
        attachTo: { element: '#selected-spins', on: 'bottom' },
        buttons: [
          { text: 'Back', action: tour.back },
          { text: 'Next', action: logStep('Part 5', 'Part 6') },
          { text: 'Skip', action: tour.cancel }
        ]
      });
    
      tour.addStep({
        id: 'part6',
        title: 'Analyze and Reset Like a Pro!',
        text: 'Click "Analyze Spins" to break down your spins and get insights.<br><iframe width="280" height="158" src="https://www.youtube.com/embed/8plHP2RIR3o?fs=0" frameborder="0"></iframe>',
        attachTo: { element: '.green-btn', on: 'bottom' },
        buttons: [
          { text: 'Back', action: tour.back },
          { text: 'Next', action: logStep('Part 6', 'Part 7') },
          { text: 'Skip', action: tour.cancel }
        ]
      });
    
      tour.addStep({
        id: 'part7',
        title: 'Light Up Your Lucky Spots!',
        text: 'The Dynamic Roulette Table highlights trending numbers and bets based on your strategy.<br><iframe width="280" height="158" src="https://www.youtube.com/embed/zT9d06sn07E?fs=0" frameborder="0"></iframe>',
        attachTo: { element: '#dynamic-table-heading', on: 'bottom' },
        buttons: [
          { text: 'Back', action: tour.back },
          { text: 'Next', action: logStep('Part 7', 'Part 8') },
          { text: 'Skip', action: tour.cancel }
        ]
      });
    
      tour.addStep({
        id: 'part8',
        title: 'Bet Smart, Track the Art!',
        text: 'Track your betting progression (e.g., Martingale, Fibonacci) to manage your bankroll.<br><iframe width="280" height="158" src="https://www.youtube.com/embed/jkE-w2MOJ0o?fs=0" frameborder="0"></iframe>',
        attachTo: { element: '.betting-progression', on: 'top' },
        beforeShowPromise: function() {
          return forceAccordionOpen('.betting-progression');
        },
        buttons: [
          { text: 'Back', action: tour.back },
          { text: 'Next', action: logStep('Part 8', 'Part 9') },
          { text: 'Skip', action: tour.cancel }
        ]
      });
    
      tour.addStep({
        id: 'part9',
        title: 'Paint Your Winning Hue!',
        text: 'Customize colors for the Dynamic Table to highlight hot and cold bets.<br><iframe width="280" height="158" src="https://www.youtube.com/embed/pUtW2HnWVL8?fs=0" frameborder="0"></iframe>',
        attachTo: { element: '#color-code-key', on: 'top' },
        beforeShowPromise: function() {
          return forceAccordionOpen('#color-code-key');
        },
        buttons: [
          { text: 'Back', action: tour.back },
          { text: 'Next', action: logStep('Part 9', 'Part 10') },
          { text: 'Skip', action: tour.cancel }
        ]
      });
    
      tour.addStep({
        id: 'part10',
        title: 'Decode the Color Clue!',
        text: 'Understand the color coding to make informed betting decisions.<br><iframe width="280" height="158" src="https://www.youtube.com/embed/PGBEoOOh9Gk?fs=0" frameborder="0"></iframe>',
        attachTo: { element: '#color-code-key', on: 'top' },
        beforeShowPromise: function() {
          return forceAccordionOpen('#color-code-key');
        },
        buttons: [
          { text: 'Back', action: tour.back },
          { text: 'Next', action: logStep('Part 10', 'Part 11') },
          { text: 'Skip', action: tour.cancel }
        ]
      });
    
      tour.addStep({
        id: 'part11',
        title: 'Unleash the Spin Secrets!',
        text: 'Dive into detailed spin analysis to uncover patterns and trends.<br><iframe width="280" height="158" src="https://www.youtube.com/embed/MpcuwWnMdrg?fs=0" frameborder="0"></iframe>',
        attachTo: { element: '#spin-analysis', on: 'top' },
        beforeShowPromise: function() {
          return forceAccordionOpen('#spin-analysis');
        },
        buttons: [
          { text: 'Back', action: tour.back },
          { text: 'Next', action: logStep('Part 11', 'Part 12') },
          { text: 'Skip', action: tour.cancel }
        ]
      });
    
      tour.addStep({
        id: 'part12',
        title: 'Save Your Spin Glory!',
        text: 'Save your session or load a previous one to continue your analysis.<br><iframe width="280" height="158" src="https://www.youtube.com/embed/pHLEa2I0jjE?fs=0" frameborder="0"></iframe>',
        attachTo: { element: '#save-load-session', on: 'top' },
        beforeShowPromise: function() {
          return forceAccordionOpen('#save-load-session');
        },
        buttons: [
          { text: 'Back', action: tour.back },
          { text: 'Next', action: logStep('Part 12', 'Part 13') },
          { text: 'Skip', action: tour.cancel }
        ]
      });
    
      tour.addStep({
        id: 'part13',
        title: 'Pick Your Strategy Groove!',
        text: 'Choose a betting strategy to optimize your game plan.<br><iframe width="280" height="158" src="https://www.youtube.com/embed/iuGEltUVbqc?fs=0" frameborder="0"></iframe>',
        attachTo: { element: '#select-category', on: 'left' },
        buttons: [
          { text: 'Back', action: tour.back },
          { text: 'Next', action: logStep('Part 13', 'Part 14') },
          { text: 'Skip', action: tour.cancel }
        ]
      });
    
      tour.addStep({
        id: 'part14',
        title: 'Boost Wins with Casino Intel!',
        text: 'Enter casino data to highlight winning trends and make smarter bets.<br><iframe width="280" height="158" src="https://www.youtube.com/embed/FJIczwv9_Ss?fs=0" frameborder="0"></iframe>',
        attachTo: { element: '#casino-data-insights', on: 'bottom' },
        beforeShowPromise: function() {
          console.log('Starting Step 14: Casino Data Insights');
          return forceAccordionOpen('#casino-data-insights');
        },
        buttons: [
          { text: 'Back', action: tour.back },
          { text: 'Finish', action: function() {
            console.log('Tour completed at Step 14');
            tour.complete();
            document.querySelector('.shepherd-modal-overlay-container')?.classList.remove('shepherd-modal-is-visible');
          } }
        ]
      });
    
      function tryStartTour(attempts = 3, delay = 2000) {
        if (attempts <= 0) {
          console.error('Max attempts reached. Tour failed.');
          alert('Tour unavailable: Components not loaded after multiple attempts. Please refresh.');
          return;
        }
        setTimeout(() => {
          console.log(`Checking DOM elements for tour (attempt ${4 - attempts}/3)...`);
          const criticalElements = [
            '#header-row',
            '.roulette-table',
            '#selected-spins',
            '#undo-spins-btn',
            '.last-spins-container',
            '.green-btn',
            '#dynamic-table-heading',
            '.betting-progression',
            '#color-code-key',
            '#spin-analysis',
            '#save-load-session',
            '#select-category',
            '#casino-data-insights'
          ];
          const missingElements = criticalElements.filter(el => !document.querySelector(el));
          if (missingElements.length > 0) {
            console.warn(`Retrying (${attempts} attempts left)... Missing: ${missingElements.join(', ')}`);
            tryStartTour(attempts - 1, delay);
          } else {
            console.log('All critical elements found. Starting tour.');
            try {
              tour.start();
              console.log('Tour started successfully.');
            } catch (error) {
              console.error('Error starting tour:', error);
              alert('Tour failed to start due to an unexpected error. Please check the console for details.');
            }
          }
        }, delay);
      }
    
      function startTour() {
        console.log('Tour starting... Attempting to initialize Shepherd.js tour.');
        const btn = document.querySelector('#start-tour-btn');
        if (btn) {
          btn.innerHTML = 'Loading Tour...';
        }
        if (typeof Shepherd === 'undefined') {
          console.error('Shepherd.js is not loaded. Check CDN or network connectivity.');
          alert('Tour unavailable: Shepherd.js failed to load. Please refresh the page or check your internet connection.');
          if (btn) btn.innerHTML = '🚀 Take the Tour!';
          return;
        }
        tryStartTour(3, 5000);
        setTimeout(() => {
          if (btn) btn.innerHTML = '🚀 Take the Tour!';
        }, 10000);
      }
    
      document.addEventListener('DOMContentLoaded', () => {
        console.log('DOM Loaded, #header-row exists:', !!document.querySelector('#header-row'));
        console.log('DOM Loaded, .betting-progression exists:', !!document.querySelector('.betting-progression'));
        console.log('DOM Loaded, #casino-data-insights exists:', !!document.querySelector('#casino-data-insights'));
        console.log('Shepherd.js available:', typeof Shepherd !== 'undefined');
        const tourButton = document.querySelector('#start-tour-btn');
        if (tourButton) {
          tourButton.addEventListener('click', (e) => {
            console.log('Tour button clicked');
            startTour();
          });
        } else {
          console.error('Tour button (#start-tour-btn) not found');
        }
      });
    </script>
    """)
    
    # -------------------------------------------------------------------------
    # HELPER FUNCTIONS (Consolidated)
    # -------------------------------------------------------------------------

    def toggle_trends(show_trends, current_label):
        new_state = not show_trends
        new_label = "Hide Trends" if new_state else "Show Trends"
        return new_state, new_label, gr.update(value=new_label)

    def update_strategy_dropdown(category):
        if category == "None":
            return gr.update(choices=["None"], value="None")
        return gr.update(choices=strategy_categories[category], value=strategy_categories[category][0])

    def toggle_neighbours_slider(strategy_name):
        """Show the count slider for both Neighbours and Top Pick strategies."""
        is_neighbours = strategy_name == "Neighbours of Strong Number"
        is_top_pick = strategy_name in [
            "Top Pick 18 Numbers without Neighbours", 
            "Best Even Money Bets + Top Pick 18 Numbers", 
            "Best Dozens + Top Pick 18 Numbers", 
            "Best Columns + Top Pick 18 Numbers", 
            "Best Dozens + Best Even Money Bets + Top Pick 18 Numbers", 
            "Best Columns + Best Even Money Bets + Top Pick 18 Numbers"
        ]
        
        return (
            gr.update(visible=is_neighbours),
            gr.update(visible=is_neighbours or is_top_pick)
        )
    def auto_manage_aidea_toggles(strategy_text, current_auto, current_shield):
        """
        Permanent Logic:
        Bypassed forceful toggling to prevent interference with uploaded JSON Auto-Pilot files.
        Returns the user's manual checkbox state unchanged.
        """
        return current_auto, current_shield

    # -------------------------------------------------------------------------------------------
    # 16. CENTRALIZED EVENT LISTENERS (FIXED & UNIFIED)
    # --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    # --- 1. Define the Master Input List for DE2D Logic ---
    # This list guarantees that EVERY update sends the correct Ramp/Grind/X-19 settings.
    de2d_inputs_list = [
        miss_slider, even_slider, streak_slider, pattern_slider,
        voisins_slider, tiers_slider, left_side_slider, right_side_slider,
        ds_strategy_slider, d17_strategy_slider, corner_strategy_slider,
        grind_active_checkbox, grind_target_dropdown,
        ramp_active_checkbox, x19_active_checkbox, x19_start_slider,
        sniper_trigger_slider, # <--- NEW: Sniper Trigger
        hidden_pinned_trigger, # <--- CRITICAL FIX: Include pins in main update loop
        hud_visibility_filters, # <--- NEW: HUD Visibility Control
        non_repeater_slider, nr_target_slider,
        # --- 🔥 Trend Reversal (Overheated) sliders ---
        tr_short_window_slider, tr_short_hits_slider,
        tr_long_window_slider, tr_long_hits_slider,
        tr_min_streak_slider, tr_density_window_slider,
        tr_density_hits_slider, tr_active_lifetime_slider,
    ]

    # Combine Sessions Button Event
    combine_button.click(
        fn=combine_sessions,
        inputs=[combine_file1, combine_file2, combine_file3],
        outputs=[combine_output, combine_status]
    ).then(
        fn=lambda: ", ".join(state.last_spins),
        inputs=[],
        outputs=[spins_display]
    ).then(
        fn=lambda: ", ".join(state.last_spins),
        inputs=[],
        outputs=[spins_textbox]
    ).then(
        fn=update_spin_counter,
        inputs=[],
        outputs=[spin_counter]
    ).then(
        fn=lambda spins, count, show: format_spins_as_html(spins, count, show),
        inputs=[spins_display, last_spin_count, show_trends_state],
        outputs=[last_spin_display]
    ).then(
        fn=analyze_spins,
        inputs=[spins_display, strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider],
        outputs=[
            spin_analysis_output, even_money_output, dozens_output, columns_output,
            streets_output, corners_output, six_lines_output, splits_output,
            sides_output, straight_up_html, top_18_html, strongest_numbers_output,
            dynamic_table_output, strategy_output, sides_of_zero_display
        ]
    ).then(
        fn=de2d_tracker_logic,
        inputs=de2d_inputs_list,
        outputs=[de2d_output]
    ).then(
        fn=lambda: (render_smart_decision_summary_html(), render_sigma_analysis_html(), render_drought_table_html()),
        inputs=[],
        outputs=[smart_decision_output, sigma_analysis_output, drought_table_output]
    ).then(
        fn=render_final_brain_html,
        inputs=[],
        outputs=[final_brain_output]
    )

    def reset_grind_step_logic(*args):
        state.grind_step_index = 0
        state.grind_last_spin_count = len(state.last_spins)
        return de2d_tracker_logic(*args)

    def reset_ramp_step_logic(*args):
        state.ramp_step_index = 0
        state.ramp_last_spin_count = len(state.last_spins)
        return de2d_tracker_logic(*args)

    def set_all_sliders_min():
        """Return the minimum bound for every DE2D slider (sourced from _DE2D_SLIDER_CFG)."""
        return tuple(cfg[1] for cfg in _DE2D_SLIDER_CFG)

    def set_all_sliders_max():
        """Return the maximum bound for every DE2D slider (sourced from _DE2D_SLIDER_CFG)."""
        return tuple(cfg[2] for cfg in _DE2D_SLIDER_CFG)

    def set_all_sliders_default():
        """Return the tuned 'best overall' defaults for every DE2D slider.

        Values are sourced directly from _DE2D_SLIDER_CFG (single source of
        truth), which already guarantees each default is within [min, max].
        """
        return tuple(cfg[0] for cfg in _DE2D_SLIDER_CFG)

    def set_all_sliders_minus(miss, even, streak, pattern, voisins, tiers, left, right,
                               ds, d17, corner, x19_start, sniper, nr_spins, nr_target,
                               tr_sw, tr_sh, tr_lw, tr_lh, tr_ms, tr_dw, tr_dh, tr_al):
        """Decrement every DE2D slider by 1, clamped to its minimum.

        Input values are coerced to int before arithmetic so that None / NaN
        (which Gradio can pass for non-interactive or uninitialised sliders)
        does not cause a TypeError that would leave all sliders in "Error"
        state for that render cycle.
        """
        raw = [miss, even, streak, pattern, voisins, tiers, left, right,
               ds, d17, corner, x19_start, sniper, nr_spins, nr_target,
               tr_sw, tr_sh, tr_lw, tr_lh, tr_ms, tr_dw, tr_dh, tr_al]
        return tuple(
            _safe_slider_val(_coerce_int(v, _DE2D_SLIDER_CFG[i][0]) - 1, i)
            for i, v in enumerate(raw)
        )

    def set_all_sliders_plus(miss, even, streak, pattern, voisins, tiers, left, right,
                              ds, d17, corner, x19_start, sniper, nr_spins, nr_target,
                              tr_sw, tr_sh, tr_lw, tr_lh, tr_ms, tr_dw, tr_dh, tr_al):
        """Increment every DE2D slider by 1, clamped to its maximum.

        Same defensive coercion as set_all_sliders_minus — guards against
        Gradio passing None for the non-interactive sniper slider or any
        other slider that has not yet been initialised in the session.
        """
        raw = [miss, even, streak, pattern, voisins, tiers, left, right,
               ds, d17, corner, x19_start, sniper, nr_spins, nr_target,
               tr_sw, tr_sh, tr_lw, tr_lh, tr_ms, tr_dw, tr_dh, tr_al]
        return tuple(
            _safe_slider_val(_coerce_int(v, _DE2D_SLIDER_CFG[i][0]) + 1, i)
            for i, v in enumerate(raw)
        )

    # --- 3. EVENT LISTENERS ---

    # Ordered list of the 10 slider components that _sync_auto_sliders() updates
    # (matches the return-value order of _sync_auto_sliders: indices 0,1,2,4,5,6,7,8,9,10)
    _auto_slider_sync_outputs = [
        miss_slider, even_slider, streak_slider,
        voisins_slider, tiers_slider,
        left_side_slider, right_side_slider,
        ds_strategy_slider, d17_strategy_slider, corner_strategy_slider,
    ]

    # A. Spins Textbox (Live Input Validation & Update)
    try:
        spins_textbox.change(
            fn=validate_spins_input,
            inputs=[spins_textbox],
            outputs=[spins_display, last_spin_display]
        )
    except Exception as e:
        logger.error(f"Error binding spins_textbox change event: {str(e)}")

    # --- LABOUCHERE BINDINGS ---
    lab_start_btn.click(fn=start_lab_session, inputs=[lab_base_bet, lab_target_profit, lab_mode_dropdown, lab_split_limit], outputs=[labouchere_view, lab_accordion])
    lab_reset_btn.click(fn=reset_lab_session, inputs=[lab_mode_dropdown], outputs=[labouchere_view, lab_accordion])

    # B. Spins Display Change (The Main Chain)
    try:
        spins_display.change(
            fn=update_spin_counter,
            inputs=[],
            outputs=[spin_counter]
        ).then(
            fn=lambda spins_display, count, show_trends: format_spins_as_html(spins_display, count, show_trends),
            inputs=[spins_display, last_spin_count, show_trends_state],
            outputs=[last_spin_display]
        ).then(
            fn=analyze_spins,
            inputs=[spins_display, strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider],
            outputs=[
                spin_analysis_output, even_money_output, dozens_output, columns_output,
                streets_output, corners_output, six_lines_output, splits_output,
                sides_output, straight_up_html, top_18_html, strongest_numbers_output,
                dynamic_table_output, strategy_output, sides_of_zero_display
            ]
        ).then(  # <--- THIS WAS MISSING
            fn=update_casino_data,
            inputs=[
                spins_count_dropdown, even_percent, odd_percent, red_percent, black_percent,
                low_percent, high_percent, dozen1_percent, dozen2_percent, dozen3_percent,
                col1_percent, col2_percent, col3_percent, use_winners_checkbox
            ],
            outputs=[casino_data_output]
        ).then(
            fn=lambda strategy, neighbours, strong, dozens, top, mid, low, tiers: create_dynamic_table(
                strategy if strategy != "None" else None, neighbours, strong, dozens, top, mid, low, tiers
            ),
            inputs=[strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider, dozen_tracker_spins_dropdown, top_color_picker, middle_color_picker, lower_color_picker, tracked_tiers_checkbox],
            outputs=[dynamic_table_output]
        ).then(
            fn=create_color_code_table, inputs=[], outputs=[color_code_output]
        ).then(
            fn=dozen_tracker,
            inputs=[
                dozen_tracker_spins_dropdown, dozen_tracker_consecutive_hits_dropdown, dozen_tracker_alert_checkbox,
                dozen_tracker_sequence_length_dropdown, dozen_tracker_follow_up_spins_dropdown, dozen_tracker_sequence_alert_checkbox
            ],
            outputs=[dummy_dozen_text, dozen_tracker_output, dozen_tracker_sequence_output]
        ).then(
            fn=even_money_tracker,
            inputs=[
                even_money_tracker_spins_dropdown,
                even_money_tracker_consecutive_hits_dropdown,
                even_money_tracker_alert_checkbox,
                even_money_tracker_combination_mode_dropdown,
                even_money_tracker_red_checkbox,
                even_money_tracker_black_checkbox,
                even_money_tracker_even_checkbox,
                even_money_tracker_odd_checkbox,
                even_money_tracker_low_checkbox,
                even_money_tracker_high_checkbox,
                even_money_tracker_identical_traits_checkbox,
                even_money_tracker_consecutive_identical_dropdown
            ],
            outputs=[dummy_even_text, even_money_tracker_output]
        ).then(
            fn=summarize_spin_traits, inputs=[last_spin_count], outputs=[traits_display]
        ).then(
            fn=calculate_hit_percentages, inputs=[last_spin_count], outputs=[hit_percentage_display]
        ).then(
            fn=select_next_spin_top_pick, inputs=[top_pick_spin_count], outputs=[top_pick_display]
        ).then(
            fn=lambda: calculate_top_pick_movement(state.current_top_picks, state.previous_top_picks),
            inputs=[],
            outputs=[movement_radar_display]
        ).then(
            fn=de2d_tracker_logic,
            inputs=de2d_inputs_list,
            outputs=[de2d_output]
        ).then(
            fn=_sync_auto_sliders,
            inputs=[],
            outputs=_auto_slider_sync_outputs
        ).then(
            fn=auto_manage_aidea_toggles,
            inputs=[strategy_output, aidea_auto_checkbox, shield_down_checkbox],
            outputs=[aidea_auto_checkbox, shield_down_checkbox]
        ).then(
            fn=_labouchere_update,
            inputs=[],
            outputs=[labouchere_view, lab_accordion]
        ).then(
            fn=lambda: logger.debug(f"After spins_display change: state.last_spins = {state.last_spins}"),
            inputs=[],
            outputs=[]
        )
    except Exception as e:
        logger.error(f"Error in spins_display.change handler: {str(e)}")
        gr.Warning(f"Error updating display: {str(e)}")

    # C. Analyze Button
    try:
        analyze_button.click(
            fn=validate_spins_input,
            inputs=[spins_textbox],
            outputs=[spins_display, last_spin_display]
        ).then(
            fn=lambda spins_display, count, show_trends: format_spins_as_html(spins_display, count, show_trends),
            inputs=[spins_display, last_spin_count, show_trends_state],
            outputs=[last_spin_display]
        ).then(
            fn=update_spin_counter,
            inputs=[],
            outputs=[spin_counter]
        ).then(
            fn=analyze_spins,
            inputs=[spins_display, strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider],
            outputs=[
                spin_analysis_output, even_money_output, dozens_output, columns_output,
                streets_output, corners_output, six_lines_output, splits_output,
                sides_output, straight_up_html, top_18_html, strongest_numbers_output,
                dynamic_table_output, strategy_output, sides_of_zero_display
            ]
        ).then(
            fn=lambda: calculate_top_pick_movement(state.current_top_picks, state.previous_top_picks),
            inputs=[],
            outputs=[movement_radar_display]
        ).then(
            fn=update_casino_data,
            inputs=[
                spins_count_dropdown, even_percent, odd_percent, red_percent, black_percent,
                low_percent, high_percent, dozen1_percent, dozen2_percent, dozen3_percent,
                col1_percent, col2_percent, col3_percent, use_winners_checkbox
            ],
            outputs=[casino_data_output]
        ).then(
            fn=lambda strategy, neighbours, strong, dozens, top, mid, low: create_dynamic_table(
                strategy if strategy != "None" else None, neighbours, strong, dozens, top, mid, low
            ),
            inputs=[strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider, dozen_tracker_spins_dropdown, top_color_picker, middle_color_picker, lower_color_picker],
            outputs=[dynamic_table_output]
        ).then(
            fn=create_color_code_table, inputs=[], outputs=[color_code_output]
        ).then(
            fn=dozen_tracker,
            inputs=[
                dozen_tracker_spins_dropdown, dozen_tracker_consecutive_hits_dropdown, dozen_tracker_alert_checkbox,
                dozen_tracker_sequence_length_dropdown, dozen_tracker_follow_up_spins_dropdown, dozen_tracker_sequence_alert_checkbox
            ],
            outputs=[dummy_dozen_text, dozen_tracker_output, dozen_tracker_sequence_output]
        ).then(
            fn=even_money_tracker,
            inputs=[
                even_money_tracker_spins_dropdown, even_money_tracker_consecutive_hits_dropdown, even_money_tracker_alert_checkbox,
                even_money_tracker_combination_mode_dropdown, even_money_tracker_red_checkbox, even_money_tracker_black_checkbox,
                even_money_tracker_even_checkbox, even_money_tracker_odd_checkbox, even_money_tracker_low_checkbox,
                even_money_tracker_high_checkbox, even_money_tracker_identical_traits_checkbox, even_money_tracker_consecutive_identical_dropdown
            ],
            outputs=[dummy_even_text, even_money_tracker_output]
        ).then(
            fn=summarize_spin_traits, inputs=[last_spin_count], outputs=[traits_display]
        ).then(
            fn=calculate_hit_percentages, inputs=[last_spin_count], outputs=[hit_percentage_display]
        ).then(
            fn=select_next_spin_top_pick, inputs=[top_pick_spin_count], outputs=[top_pick_display]
        ).then(
            fn=de2d_tracker_logic,
            inputs=de2d_inputs_list, 
            outputs=[de2d_output]
        ).then(
            fn=_sync_auto_sliders,
            inputs=[],
            outputs=_auto_slider_sync_outputs
        ).then(
            fn=auto_manage_aidea_toggles,
            inputs=[strategy_output, aidea_auto_checkbox, shield_down_checkbox],
            outputs=[aidea_auto_checkbox, shield_down_checkbox]
        ).then(
            fn=render_master_info_both,
            inputs=[hidden_pinned_trigger],
            outputs=[master_info_summary_output, master_info_output, ai_coach_output]
        ).then(
            fn=lambda: logger.debug(f"After analyze_button click: state.last_spins = {state.last_spins}"),
            inputs=[],
            outputs=[]
        )
    except Exception as e:
        logger.error(f"Error in analyze_button.click: {str(e)}")
        gr.Warning(f"Error during analysis: {str(e)}")

    # 2. Save Session Button
    try:
        save_button.click(
            fn=save_session,
            inputs=[session_name_input],
            outputs=[save_output]
        )
    except Exception as e:
        logger.error(f"Error in save_button.click handler: {str(e)}")

    # 3. Load Session Input
    try:
        load_input.change(
            fn=load_session,
            inputs=[load_input, strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider],
            outputs=[
                spins_display, spins_textbox, spin_analysis_output, even_money_output,
                dozens_output, columns_output, streets_output, corners_output, six_lines_output,
                splits_output, sides_output, straight_up_html, top_18_html, strongest_numbers_output,
                dynamic_table_output, strategy_output
            ]
        ).then(
            fn=lambda strategy, neighbours, strong, dozens, top, mid, low: create_dynamic_table(
                strategy if strategy != "None" else None, neighbours, strong, dozens, top, mid, low
            ),
            inputs=[strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider, dozen_tracker_spins_dropdown, top_color_picker, middle_color_picker, lower_color_picker],
            outputs=[dynamic_table_output]
        ).then(
            fn=lambda spins_display, count, show_trends: format_spins_as_html(spins_display, count, show_trends),
            inputs=[spins_display, last_spin_count, show_trends_state],
            outputs=[last_spin_display]
        ).then(
            fn=create_color_code_table, inputs=[], outputs=[color_code_output]
        ).then(
            fn=dozen_tracker,
            inputs=[dozen_tracker_spins_dropdown, dozen_tracker_consecutive_hits_dropdown, dozen_tracker_alert_checkbox, dozen_tracker_sequence_length_dropdown, dozen_tracker_follow_up_spins_dropdown, dozen_tracker_sequence_alert_checkbox],
            outputs=[dummy_dozen_text, dozen_tracker_output, dozen_tracker_sequence_output]
        ).then(
            fn=even_money_tracker,
            inputs=[even_money_tracker_spins_dropdown, even_money_tracker_consecutive_hits_dropdown, even_money_tracker_alert_checkbox, even_money_tracker_combination_mode_dropdown, even_money_tracker_red_checkbox, even_money_tracker_black_checkbox, even_money_tracker_even_checkbox, even_money_tracker_odd_checkbox, even_money_tracker_low_checkbox, even_money_tracker_high_checkbox, even_money_tracker_identical_traits_checkbox, even_money_tracker_consecutive_identical_dropdown],
            outputs=[dummy_even_text, even_money_tracker_output]
        ).then(
            fn=summarize_spin_traits, inputs=[last_spin_count], outputs=[traits_display]
        ).then(
            fn=calculate_hit_percentages, inputs=[last_spin_count], outputs=[hit_percentage_display]
        ).then(
            fn=select_next_spin_top_pick, inputs=[top_pick_spin_count], outputs=[top_pick_display]
        ).then(
            fn=de2d_tracker_logic,
            inputs=[miss_slider, even_slider, streak_slider, pattern_slider, voisins_slider, tiers_slider, left_side_slider, right_side_slider, ds_strategy_slider, d17_strategy_slider, corner_strategy_slider, grind_active_checkbox, grind_target_dropdown, ramp_active_checkbox, x19_active_checkbox, x19_start_slider],
            outputs=[de2d_output]
        ).then(
            fn=lambda: logger.debug(f"After load_input change: state.last_spins = {state.last_spins}"),
            inputs=[],
            outputs=[]
        )
    except Exception as e:
        logger.error(f"Error in load_input.change handler: {str(e)}")

    # D. Undo Button
    try:
        undo_button.click(
            fn=undo_last_spin,
            inputs=[spins_display, gr.State(value=1), strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider],
            outputs=[
                spin_analysis_output, even_money_output, dozens_output, columns_output,
                streets_output, corners_output, six_lines_output, splits_output, sides_output,
                straight_up_html, top_18_html, strongest_numbers_output, spins_textbox, spins_display,
                dynamic_table_output, strategy_output, color_code_output, spin_counter, sides_of_zero_display
            ]
        ).then(
            fn=lambda spins, count, show: format_spins_as_html(spins, count, show),
            inputs=[spins_display, last_spin_count, show_trends_state],
            outputs=[last_spin_display]
        ).then(
            fn=de2d_tracker_logic,
            inputs=de2d_inputs_list, 
            outputs=[de2d_output]
        ).then(
            fn=auto_manage_aidea_toggles,
            inputs=[strategy_output, aidea_auto_checkbox, shield_down_checkbox],
            outputs=[aidea_auto_checkbox, shield_down_checkbox]
        ).then(
            fn=render_master_info_both,
            inputs=[hidden_pinned_trigger],
            outputs=[master_info_summary_output, master_info_output, ai_coach_output]
        )
    except Exception as e:
        logger.error(f"Error in undo_button.click: {str(e)}")

    # E. Generate Random Spins
    try:
        generate_spins_button.click(
            fn=generate_random_spins,
            inputs=[gr.State(value="5"), spins_display, last_spin_count],
            outputs=[spins_display, spins_textbox, spin_analysis_output, spin_counter, sides_of_zero_display]
        ).then(
            fn=lambda spins_display, count, show_trends: format_spins_as_html(spins_display, count, show_trends),
            inputs=[spins_display, last_spin_count, show_trends_state],
            outputs=[last_spin_display]
        ).then(
            fn=analyze_spins,
            inputs=[spins_display, strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider],
            outputs=[
                spin_analysis_output, even_money_output, dozens_output, columns_output,
                streets_output, corners_output, six_lines_output, splits_output,
                sides_output, straight_up_html, top_18_html, strongest_numbers_output,
                dynamic_table_output, strategy_output, sides_of_zero_display
            ]
        ).then(
            fn=de2d_tracker_logic,
            inputs=de2d_inputs_list, 
            outputs=[de2d_output]
        ).then(
            fn=lambda: (render_smart_decision_summary_html(), render_sigma_analysis_html(), render_drought_table_html()),
            inputs=[],
            outputs=[smart_decision_output, sigma_analysis_output, drought_table_output]
        ).then(
            fn=render_cards_and_alerts, inputs=de2d_inputs_list, outputs=[strategy_cards_area, alerts_bar_output]
        ).then(
            fn=render_final_brain_html, inputs=[], outputs=[final_brain_output]
        ).then(
            fn=render_master_info_both, inputs=[hidden_pinned_trigger], outputs=[master_info_summary_output, master_info_output, ai_coach_output]
        )
    except Exception as e:
        logger.error(f"Error in generate_spins_button.click: {str(e)}")

    try:
        clear_spins_button.click(
            fn=clear_spins,
            inputs=[],
            outputs=[spins_display, spins_textbox, spin_analysis_output, last_spin_display, spin_counter, sides_of_zero_display, js_trigger_box]
        ).then(
            fn=de2d_tracker_logic,
            inputs=de2d_inputs_list, 
            outputs=[de2d_output]
        ).then(
            fn=render_cards_and_alerts, inputs=de2d_inputs_list, outputs=[strategy_cards_area, alerts_bar_output]
        ).then(
            fn=render_master_info_both, inputs=[hidden_pinned_trigger], outputs=[master_info_summary_output, master_info_output, ai_coach_output]
        )

        clear_all_button.click(
            fn=clear_all,
            inputs=[],
            outputs=[
                spins_display, spins_textbox, spin_analysis_output, last_spin_display,
                even_money_output, dozens_output, columns_output, streets_output,
                corners_output, six_lines_output, splits_output, sides_output,
                straight_up_html, top_18_html, strongest_numbers_output, spin_counter, sides_of_zero_display,
                js_trigger_box
            ]
        ).then(
            fn=clear_outputs, inputs=[], outputs=[
                spin_analysis_output, even_money_output, dozens_output, columns_output,
                streets_output, corners_output, six_lines_output, splits_output,
                sides_output, straight_up_html, top_18_html, strongest_numbers_output,
                dynamic_table_output, strategy_output, color_code_output
            ]
        ).then(
            fn=de2d_tracker_logic,
            inputs=de2d_inputs_list, 
            outputs=[de2d_output]
        ).then(
            fn=render_cards_and_alerts, inputs=de2d_inputs_list, outputs=[strategy_cards_area, alerts_bar_output]
        ).then(
            fn=render_master_info_both, inputs=[hidden_pinned_trigger], outputs=[master_info_summary_output, master_info_output, ai_coach_output]
        )

        master_reset_button.click(
            fn=master_reset,
            inputs=[],
            outputs=[
                spins_display, spins_textbox, spin_analysis_output, last_spin_display,
                even_money_output, dozens_output, columns_output, streets_output,
                corners_output, six_lines_output, splits_output, sides_output,
                straight_up_html, top_18_html, strongest_numbers_output,
                spin_counter, sides_of_zero_display, js_trigger_box
            ]
        ).then(
            fn=clear_outputs, inputs=[], outputs=[
                spin_analysis_output, even_money_output, dozens_output, columns_output,
                streets_output, corners_output, six_lines_output, splits_output,
                sides_output, straight_up_html, top_18_html, strongest_numbers_output,
                dynamic_table_output, strategy_output, color_code_output
            ]
        ).then(
            fn=_labouchere_update, inputs=[], outputs=[labouchere_view, lab_accordion]
        ).then(
            fn=render_aidea_roadmap_html, inputs=[], outputs=[aidea_roadmap_view, aidea_status_banner]
        ).then(
            fn=de2d_tracker_logic, inputs=de2d_inputs_list, outputs=[de2d_output]
        ).then(
            fn=render_cards_and_alerts, inputs=de2d_inputs_list, outputs=[strategy_cards_area, alerts_bar_output]
        ).then(
            fn=render_master_info_both, inputs=[hidden_pinned_trigger], outputs=[master_info_summary_output, master_info_output, ai_coach_output]
        )
    except Exception as e:
        logger.error(f"Error in clear buttons: {str(e)}")
    # G. Play Hot/Cold
    try:
        play_hot_button.click(
            fn=play_specific_numbers,
            inputs=[hot_numbers_input, gr.State(value="Hot"), spins_display, last_spin_count],
            outputs=[spins_display, spins_textbox, casino_data_output, spin_counter, sides_of_zero_display]
        ).then(
            fn=sync_spins_display,
            inputs=[spins_display],
            outputs=[spins_display]
        ).then(
            fn=lambda spins_display, count, show_trends: format_spins_as_html(spins_display, count, show_trends),
            inputs=[spins_display, last_spin_count, show_trends_state],
            outputs=[last_spin_display]
        ).then(
            fn=analyze_spins,
            inputs=[spins_display, strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider],
            outputs=[
                spin_analysis_output, even_money_output, dozens_output, columns_output,
                streets_output, corners_output, six_lines_output, splits_output,
                sides_output, straight_up_html, top_18_html, strongest_numbers_output,
                dynamic_table_output, strategy_output, sides_of_zero_display
            ]
        ).then(
            fn=summarize_spin_traits,
            inputs=[last_spin_count],
            outputs=[traits_display]
        ).then(
            fn=calculate_hit_percentages,
            inputs=[last_spin_count],
            outputs=[hit_percentage_display]
        ).then(
            fn=suggest_hot_cold_numbers,
            inputs=[],
            outputs=[hot_suggestions, cold_suggestions]
        ).then(
            fn=select_next_spin_top_pick,
            inputs=[top_pick_spin_count],
            outputs=[top_pick_display]
        ).then(
            fn=de2d_tracker_logic,
            inputs=de2d_inputs_list,
            outputs=[de2d_output]
        ).then(
            fn=lambda: logger.debug(f"After play_hot_button click: state.last_spins = {state.last_spins}"),
            inputs=[],
            outputs=[]
        )
    except Exception as e:
        logger.error(f"Error in play_hot_button.click handler: {str(e)}")

    try:
        play_cold_button.click(
            fn=play_specific_numbers,
            inputs=[cold_numbers_input, gr.State(value="Cold"), spins_display, last_spin_count],
            outputs=[spins_display, spins_textbox, casino_data_output, spin_counter, sides_of_zero_display]
        ).then(
            fn=sync_spins_display,
            inputs=[spins_display],
            outputs=[spins_display]
        ).then(
            fn=lambda spins_display, count, show_trends: format_spins_as_html(spins_display, count, show_trends),
            inputs=[spins_display, last_spin_count, show_trends_state],
            outputs=[last_spin_display]
        ).then(
            fn=analyze_spins,
            inputs=[spins_display, strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider],
            outputs=[
                spin_analysis_output, even_money_output, dozens_output, columns_output,
                streets_output, corners_output, six_lines_output, splits_output,
                sides_output, straight_up_html, top_18_html, strongest_numbers_output,
                dynamic_table_output, strategy_output, sides_of_zero_display
            ]
        ).then(
            fn=summarize_spin_traits,
            inputs=[last_spin_count],
            outputs=[traits_display]
        ).then(
            fn=calculate_hit_percentages,
            inputs=[last_spin_count],
            outputs=[hit_percentage_display]
        ).then(
            fn=select_next_spin_top_pick,
            inputs=[top_pick_spin_count],
            outputs=[top_pick_display]
        ).then(
            fn=de2d_tracker_logic,
            inputs=de2d_inputs_list,
            outputs=[de2d_output]
        ).then(
            fn=lambda: logger.debug(f"After play_cold_button click: state.last_spins = {state.last_spins}"),
            inputs=[],
            outputs=[]
        )
    except Exception as e:
        logger.error(f"Error in play_cold_button.click handler: {str(e)}")

    # 15. Clear Hot/Cold Buttons
    try:
        clear_hot_button.click(
            fn=clear_hot_cold_picks,
            inputs=[gr.State(value="Hot"), spins_display],
            outputs=[hot_numbers_input, casino_data_output, spin_counter, sides_of_zero_display, spins_display]
        ).then(
            fn=select_next_spin_top_pick,
            inputs=[top_pick_spin_count],
            outputs=[top_pick_display]
        ).then(
            fn=de2d_tracker_logic,
            inputs=de2d_inputs_list,
            outputs=[de2d_output]
        ).then(
            fn=lambda: logger.debug(f"After clear_hot_button click: state.last_spins = {state.last_spins}"),
            inputs=[],
            outputs=[]
        )
    except Exception as e:
        logger.error(f"Error in clear_hot_button.click handler: {str(e)}")

    try:
        clear_cold_button.click(
            fn=clear_hot_cold_picks,
            inputs=[gr.State(value="Cold"), spins_display],
            outputs=[cold_numbers_input, casino_data_output, spin_counter, sides_of_zero_display, spins_display]
        ).then(
            fn=select_next_spin_top_pick,
            inputs=[top_pick_spin_count],
            outputs=[top_pick_display]
        ).then(
            fn=de2d_tracker_logic,
            inputs=de2d_inputs_list,
            outputs=[de2d_output]
        ).then(
            fn=lambda: logger.debug(f"After clear_cold_button click: state.last_spins = {state.last_spins}"),
            inputs=[],
            outputs=[]
        )
    except Exception as e:
        logger.error(f"Error in clear_cold_button.click handler: {str(e)}")

    # H. Sliders (Live Update for DE2D)
    try:
        # Loop through all sliders and update logic on change.
        # In AUTO mode, _sync_auto_sliders() reasserts override values so AUTO
        # always has control even when the user manually drags a slider.
        for slider in [miss_slider, even_slider, streak_slider, pattern_slider, voisins_slider, tiers_slider, left_side_slider, right_side_slider, ds_strategy_slider, d17_strategy_slider, corner_strategy_slider, x19_start_slider, non_repeater_slider, nr_target_slider,
                       tr_short_window_slider, tr_short_hits_slider, tr_long_window_slider, tr_long_hits_slider,
                       tr_min_streak_slider, tr_density_window_slider, tr_density_hits_slider, tr_active_lifetime_slider]:
            slider.change(fn=de2d_tracker_logic, inputs=de2d_inputs_list, outputs=[de2d_output]
            ).then(fn=_sync_auto_sliders, inputs=[], outputs=_auto_slider_sync_outputs)
            
        # Checkboxes for Live Update
        grind_active_checkbox.change(fn=de2d_tracker_logic, inputs=de2d_inputs_list, outputs=[de2d_output])
        grind_target_dropdown.change(fn=de2d_tracker_logic, inputs=de2d_inputs_list, outputs=[de2d_output])
        ramp_active_checkbox.change(fn=de2d_tracker_logic, inputs=de2d_inputs_list, outputs=[de2d_output])
        x19_active_checkbox.change(fn=de2d_tracker_logic, inputs=de2d_inputs_list, outputs=[de2d_output])
        hud_visibility_filters.change(
            fn=lambda filters: _sync_strategy_flags_from_hud_filters(filters),
            inputs=[hud_visibility_filters],
            outputs=[]
        ).then(
            fn=de2d_tracker_logic, inputs=de2d_inputs_list, outputs=[de2d_output]
        ).then(
            fn=render_cards_and_alerts, inputs=de2d_inputs_list, outputs=[strategy_cards_area, alerts_bar_output]
        ).then(
            fn=render_final_brain_html, inputs=[], outputs=[final_brain_output]
        )
    except Exception as e:
        logger.error(f"Error in slider/checkbox handlers: {str(e)}")

    # J. Reset Buttons (Grind, Ramp, Sniper)
    def reset_sniper_latch_logic(*args):
        state.sniper_locked = False
        state.sniper_locked_misses = 0
        return de2d_tracker_logic(*args)

    # J. Reset Buttons (Grind & Ramp)
    try:
        reset_grind_button.click(fn=reset_grind_step_logic, inputs=de2d_inputs_list, outputs=[de2d_output])
        reset_ramp_button.click(fn=reset_ramp_step_logic, inputs=de2d_inputs_list, outputs=[de2d_output])
    except Exception as e:
        logger.error(f"Error in reset buttons: {str(e)}")

    # Slider Mass Update Buttons
    de2d_sliders = [
        miss_slider, even_slider, streak_slider, pattern_slider,
        voisins_slider, tiers_slider, left_side_slider, right_side_slider, 
        ds_strategy_slider, d17_strategy_slider, corner_strategy_slider, x19_start_slider, sniper_trigger_slider, non_repeater_slider, nr_target_slider,
        # --- 🔥 Trend Reversal sliders (indices 15–22 in _DE2D_SLIDER_CFG) ---
        tr_short_window_slider, tr_short_hits_slider,
        tr_long_window_slider, tr_long_hits_slider,
        tr_min_streak_slider, tr_density_window_slider,
        tr_density_hits_slider, tr_active_lifetime_slider,
    ]

    btn_min_all.click(fn=set_all_sliders_min, inputs=[], outputs=de2d_sliders
    ).then(fn=de2d_tracker_logic, inputs=de2d_inputs_list, outputs=[de2d_output]
    ).then(fn=render_cards_and_alerts, inputs=de2d_inputs_list, outputs=[strategy_cards_area, alerts_bar_output])
    btn_max_all.click(fn=set_all_sliders_max, inputs=[], outputs=de2d_sliders
    ).then(fn=de2d_tracker_logic, inputs=de2d_inputs_list, outputs=[de2d_output]
    ).then(fn=render_cards_and_alerts, inputs=de2d_inputs_list, outputs=[strategy_cards_area, alerts_bar_output])
    btn_default_all.click(fn=set_all_sliders_default, inputs=[], outputs=de2d_sliders
    ).then(fn=de2d_tracker_logic, inputs=de2d_inputs_list, outputs=[de2d_output]
    ).then(fn=render_cards_and_alerts, inputs=de2d_inputs_list, outputs=[strategy_cards_area, alerts_bar_output])
    btn_minus_all.click(fn=set_all_sliders_minus, inputs=de2d_sliders, outputs=de2d_sliders
    ).then(fn=de2d_tracker_logic, inputs=de2d_inputs_list, outputs=[de2d_output]
    ).then(fn=render_cards_and_alerts, inputs=de2d_inputs_list, outputs=[strategy_cards_area, alerts_bar_output])
    btn_plus_all.click(fn=set_all_sliders_plus, inputs=de2d_sliders, outputs=de2d_sliders
    ).then(fn=de2d_tracker_logic, inputs=de2d_inputs_list, outputs=[de2d_output]
    ).then(fn=render_cards_and_alerts, inputs=de2d_inputs_list, outputs=[strategy_cards_area, alerts_bar_output])

    btn_hud_check_all.click(
        fn=lambda: _HUD_ALL_CHOICES, inputs=[], outputs=[hud_visibility_filters]
    ).then(
        fn=lambda: _sync_strategy_flags_from_hud_filters(_HUD_ALL_CHOICES),
        inputs=[], outputs=[]
    ).then(fn=de2d_tracker_logic, inputs=de2d_inputs_list, outputs=[de2d_output]
    ).then(fn=render_cards_and_alerts, inputs=de2d_inputs_list, outputs=[strategy_cards_area, alerts_bar_output]
    ).then(fn=render_final_brain_html, inputs=[], outputs=[final_brain_output])

    btn_hud_uncheck_all.click(
        fn=lambda: [], inputs=[], outputs=[hud_visibility_filters]
    ).then(
        fn=lambda: _sync_strategy_flags_from_hud_filters([]),
        inputs=[], outputs=[]
    ).then(fn=de2d_tracker_logic, inputs=de2d_inputs_list, outputs=[de2d_output]
    ).then(fn=render_cards_and_alerts, inputs=de2d_inputs_list, outputs=[strategy_cards_area, alerts_bar_output]
    ).then(fn=render_final_brain_html, inputs=[], outputs=[final_brain_output])

    # L. Bind Roulette Table Buttons (Delayed to ensure all inputs exist)
    try:
        for btn, num in roulette_buttons:
            btn.click(
                fn=add_spin,
                inputs=[gr.State(value=num), spins_display, last_spin_count],
                outputs=[spins_display, spins_textbox, last_spin_display, spin_counter, sides_of_zero_display]
            ).then(
                fn=format_spins_as_html,
                inputs=[spins_display, last_spin_count, show_trends_state],
                outputs=[last_spin_display]
            ).then(
                fn=analyze_spins,
                inputs=[spins_display, strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider],
                outputs=[
                    spin_analysis_output, even_money_output, dozens_output, columns_output,
                    streets_output, corners_output, six_lines_output, splits_output,
                    sides_output, straight_up_html, top_18_html, strongest_numbers_output,
                    dynamic_table_output, strategy_output, sides_of_zero_display
                ]
            ).then(
                fn=update_casino_data,
                inputs=[
                    spins_count_dropdown, even_percent, odd_percent, red_percent, black_percent,
                    low_percent, high_percent, dozen1_percent, dozen2_percent, dozen3_percent,
                    col1_percent, col2_percent, col3_percent, use_winners_checkbox
                ],
                outputs=[casino_data_output]
            ).then(
                fn=lambda strategy, neighbours, strong, dozens, top, mid, low, tiers: create_dynamic_table(
                    strategy if strategy != "None" else None, neighbours, strong, dozens, top, mid, low, tiers
                ),
                inputs=[strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider, dozen_tracker_spins_dropdown, top_color_picker, middle_color_picker, lower_color_picker, tracked_tiers_checkbox],
                outputs=[dynamic_table_output]
            ).then(
                fn=create_color_code_table, inputs=[], outputs=[color_code_output]
            ).then(
                fn=dozen_tracker,
                inputs=[dozen_tracker_spins_dropdown, dozen_tracker_consecutive_hits_dropdown, dozen_tracker_alert_checkbox, dozen_tracker_sequence_length_dropdown, dozen_tracker_follow_up_spins_dropdown, dozen_tracker_sequence_alert_checkbox],
                outputs=[dummy_dozen_text, dozen_tracker_output, dozen_tracker_sequence_output]
            ).then(
                fn=even_money_tracker,
                inputs=[even_money_tracker_spins_dropdown, even_money_tracker_consecutive_hits_dropdown, even_money_tracker_alert_checkbox, even_money_tracker_combination_mode_dropdown, even_money_tracker_red_checkbox, even_money_tracker_black_checkbox, even_money_tracker_even_checkbox, even_money_tracker_odd_checkbox, even_money_tracker_low_checkbox, even_money_tracker_high_checkbox, even_money_tracker_identical_traits_checkbox, even_money_tracker_consecutive_identical_dropdown],
                outputs=[dummy_even_text, even_money_tracker_output]
            ).then(
                fn=summarize_spin_traits, inputs=[last_spin_count], outputs=[traits_display]
            ).then(
                fn=calculate_hit_percentages, inputs=[last_spin_count], outputs=[hit_percentage_display]
            ).then(
                fn=select_next_spin_top_pick, inputs=[top_pick_spin_count], outputs=[top_pick_display]
            ).then(
                fn=lambda: calculate_top_pick_movement(state.current_top_picks, state.previous_top_picks),
                inputs=[],
                outputs=[movement_radar_display]
            ).then(
                fn=de2d_tracker_logic,
                inputs=de2d_inputs_list,
                outputs=[de2d_output]
            ).then(
                fn=_sync_auto_sliders,
                inputs=[],
                outputs=_auto_slider_sync_outputs
            ).then(
                fn=lambda: (render_smart_decision_summary_html(), render_sigma_analysis_html(), render_drought_table_html()),
                inputs=[],
                outputs=[smart_decision_output, sigma_analysis_output, drought_table_output]
            ).then(
                fn=auto_manage_aidea_toggles,
                inputs=[strategy_output, aidea_auto_checkbox, shield_down_checkbox],
                outputs=[aidea_auto_checkbox, shield_down_checkbox]
            ).then(
                fn=lambda auto, shield_opt, agg_opt: nav_aidea_toggle(
                    auto_trigger=True,
                    result=state.aidea_last_result,
                    auto_enabled=auto,
                    shield_down_mode=shield_opt,
                    aggressor_reset_mode=agg_opt
                ),
                inputs=[aidea_auto_checkbox, shield_down_checkbox, aggressor_reset_checkbox],
                outputs=[aidea_roadmap_view, aidea_status_banner]
            ).then(
                fn=render_cards_and_alerts, inputs=de2d_inputs_list, outputs=[strategy_cards_area, alerts_bar_output]
            ).then(
                fn=render_final_brain_html, inputs=[], outputs=[final_brain_output]
            ).then(
                fn=render_master_info_both, inputs=[hidden_pinned_trigger], outputs=[master_info_summary_output, master_info_output, ai_coach_output]
            ).then(
                fn=_labouchere_update, inputs=[], outputs=[labouchere_view, lab_accordion]
            ).then(
                fn=lambda: logger.debug(f"Spin cycle complete."), inputs=[], outputs=[]
            )
    except Exception as e:
        logger.error(f"Error binding roulette buttons: {str(e)}")

    # --- DYNAMIC AIDEA ROADMAP EVENTS (FIXED) ---
    # This fixes the issue where the upload button would vanish.
    aidea_upload.change(
        fn=process_aidea_upload,
        inputs=[aidea_upload],
        outputs=[aidea_upload, aidea_roadmap_view, aidea_status_banner]
    )
    
    aidea_hard_reset.click(
        fn=reset_aidea_progress,
        inputs=[],
        outputs=[aidea_roadmap_view, aidea_status_banner]
    )
    
    aidea_unit_dropdown.change(
        fn=set_aidea_multiplier,
        inputs=[aidea_unit_dropdown],
        outputs=[aidea_roadmap_view, aidea_status_banner]
    )

    # --- Bet Sizing Discipline / Auto-Nudge mode selector ---
    def _set_nudge_mode(mode):
        """Store the selected mode and re-render the strategy cards area."""
        try:
            _nudge_state["mode"] = mode if mode in ("MANUAL", "SUGGEST", "AUTO") else "MANUAL"
            if mode == "MANUAL":
                # Clear any accumulated overrides and log when returning to manual
                _nudge_state["overrides"] = {}
                _nudge_state["cooldown"] = {}
                _nudge_state["nudge_log"] = []
        except Exception:
            pass
        return render_cards_and_alerts(*[cfg[0] for cfg in _DE2D_SLIDER_CFG[:11]])

    nudge_mode_radio.change(
        fn=_set_nudge_mode,
        inputs=[nudge_mode_radio],
        outputs=[strategy_cards_area],
    ).then(
        fn=_sync_auto_sliders,
        inputs=[],
        outputs=_auto_slider_sync_outputs,
    )


    aidea_prev_btn.click(fn=nav_aidea_prev, inputs=[], outputs=[aidea_roadmap_view, aidea_status_banner])
    aidea_next_btn.click(fn=nav_aidea_next, inputs=[], outputs=[aidea_roadmap_view, aidea_status_banner])
    aidea_toggle_btn.click(fn=nav_aidea_toggle, inputs=[], outputs=[aidea_roadmap_view, aidea_status_banner])

    # Tracker Tier Checkbox
    tracked_tiers_checkbox.change(
        fn=lambda strategy, neighbours, strong, dozens, top, mid, low, tiers: create_dynamic_table(
            strategy if strategy != "None" else None, neighbours, strong, dozens, top, mid, low, tiers
        ),
        inputs=[strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider, dozen_tracker_spins_dropdown, top_color_picker, middle_color_picker, lower_color_picker, tracked_tiers_checkbox],
        outputs=[dynamic_table_output]
    )

    # Other Strategy Inputs (Dropdowns)
    try:
        strategy_dropdown.change(
            fn=toggle_neighbours_slider, inputs=[strategy_dropdown], outputs=[neighbours_count_slider, strong_numbers_count_slider]
        ).then(
            fn=show_strategy_recommendations, inputs=[strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider], outputs=[strategy_output]
        ).then(
            fn=create_dynamic_table,
            inputs=[strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider, dozen_tracker_spins_dropdown, top_color_picker, middle_color_picker, lower_color_picker],
            outputs=[dynamic_table_output]
        )
        
        category_dropdown.change(
            fn=update_strategy_dropdown, inputs=category_dropdown, outputs=strategy_dropdown
        )
        
        reset_strategy_button.click(
            fn=reset_strategy_dropdowns, inputs=[], outputs=[category_dropdown, strategy_dropdown, strategy_dropdown]
        )
        # Update text box and table when the Strong Numbers count slider is moved
        strong_numbers_count_slider.change(
            fn=show_strategy_recommendations, 
            inputs=[strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider], 
            outputs=[strategy_output]
        ).then(
            fn=lambda: calculate_top_pick_movement(state.current_top_picks, state.previous_top_picks),
            inputs=[],
            outputs=[movement_radar_display]
        ).then(
            fn=create_dynamic_table,
            inputs=[strategy_dropdown, neighbours_count_slider, strong_numbers_count_slider, dozen_tracker_spins_dropdown, top_color_picker, middle_color_picker, lower_color_picker, tracked_tiers_checkbox],
            outputs=[dynamic_table_output]
        )
    except Exception as e:
        logger.error(f"Error in strategy inputs: {str(e)}")

    # K. Toggle Trends Button
    try:
        toggle_trends_button.click(
            fn=toggle_trends,
            inputs=[show_trends_state, toggle_trends_label],
            outputs=[show_trends_state, toggle_trends_label, toggle_trends_button]
        ).then(
            fn=format_spins_as_html,
            inputs=[spins_display, last_spin_count, show_trends_state],
            outputs=[last_spin_display]
        )
    except Exception as e:
        logger.error(f"Error in toggle_trends_button.click: {str(e)}")

    # Trigger DE2D update when a star is clicked in the browser
    hidden_pinned_trigger.change(
        fn=de2d_tracker_logic,
        inputs=de2d_inputs_list, # Already contains hidden_pinned_trigger
        outputs=[de2d_output]
    ).then(
        fn=render_master_info_both,
        inputs=[hidden_pinned_trigger],
        outputs=[master_info_summary_output, master_info_output, ai_coach_output]
    )

    # Sync strategy flags from the HUD checkbox initial values on page load.
    # Without this, the flags stay at their state.py defaults and the Final
    # Brain strategy cards would not respect the HUD checkbox state until the
    # user manually changes a checkbox.
    def _on_page_load(filters):
        _sync_strategy_flags_from_hud_filters(filters)

    def _populate_deferred_outputs():
        """Compute initial HTML values for components left empty at build time.

        These are components whose initial values depend on the heavy modules
        (rendering, trackers, analysis, strategies, sessions).  The modules are
        already loaded by module-level init() calls above, so this function is
        fast – it only runs the rendering logic, not the import machinery.
        """
        de2d_val = de2d_tracker_logic(*[cfg[0] for cfg in _DE2D_SLIDER_CFG[:11]])
        smart_val = render_smart_decision_summary_html()
        sigma_val = render_sigma_analysis_html()
        drought_val = render_drought_table_html()
        ai_coach_val = _rendering.render_ai_coach_prompt_html(state)
        sides_val = render_sides_of_zero_display()
        cards_val = render_strategy_cards_area_html()
        master_summary_val = render_master_information_summary_html()
        master_val = render_master_information_html()
        hit_pct_val = calculate_hit_percentages(36)
        traits_val = summarize_spin_traits(36)
        movement_val = calculate_top_pick_movement([], [])
        strategy_val = show_strategy_recommendations("Best Even Money Bets", 2, 1)
        dynamic_table_val = create_dynamic_table(strategy_name="Best Even Money Bets")
        top_pick_val = select_next_spin_top_pick(
            18, ["Red/Black", "Even/Odd", "Low/High", "Dozens",
                 "Columns", "Wheel Sections", "Neighbors"])
        return (de2d_val, smart_val, sigma_val, drought_val, ai_coach_val,
                sides_val, cards_val, master_summary_val, master_val,
                hit_pct_val, traits_val, movement_val,
                strategy_val, dynamic_table_val, top_pick_val)

    demo.load(
        fn=_on_page_load,
        inputs=[hud_visibility_filters],
        outputs=[]
    ).then(
        fn=_populate_deferred_outputs,
        inputs=[],
        outputs=[de2d_output, smart_decision_output, sigma_analysis_output,
                 drought_table_output, ai_coach_output,
                 sides_of_zero_display, strategy_cards_area,
                 master_info_summary_output, master_info_output,
                 hit_percentage_display, traits_display, movement_radar_display,
                 strategy_output, dynamic_table_output, top_pick_display]
    ).then(
        fn=render_final_brain_html,
        inputs=[],
        outputs=[final_brain_output]
    )

demo.queue()
demo.launch(ssr_mode=False)