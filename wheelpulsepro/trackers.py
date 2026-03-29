"""WheelPulsePro – tracker logic (DE2D, Dozen, Even-Money) extracted from app.py."""

import json
import logging
import traceback

import wheelpulsepro.rendering as _rendering
from roulette_data import (
    EVEN_MONEY,
    DOZENS,
    COLUMNS,
    STREETS,
    CORNERS,
    SIX_LINES,
    SPLITS,
)
from wheelpulsepro.mappings import BETTING_MAPPINGS

logger = logging.getLogger("wheelPulsePro.trackers")

# ---------------------------------------------------------------------------
# Injected module-level globals (set by init())
# ---------------------------------------------------------------------------
state = None
colors = None
_HUD_DEFAULT_VISIBLE = None


def init(state_obj, colors_dict, hud_default_visible):
    """Inject app-level globals into this module.

    Must be called once after ``app.py`` initialises its global state,
    before any tracker function is invoked.
    """
    global state, colors, _HUD_DEFAULT_VISIBLE
    state = state_obj
    colors = colors_dict
    _HUD_DEFAULT_VISIBLE = hud_default_visible


# ---------------------------------------------------------------------------
# Constants (moved from app.py)
# ---------------------------------------------------------------------------

# Keeping all values here prevents the preset functions from drifting out of
# sync with the slider widget definitions and avoids Gradio's transient
# "Error" state that occurs when a callback returns None / an out-of-range
# integer to a slider component.
_DE2D_SLIDER_CFG = [
    # (default, min,  max )
    (14,   2,  20),   # [0]  miss            – Missing Dozen/Col (Wait)
    ( 8,   4,  30),   # [1]  even            – Even Money (Wait)
    ( 9,   2,  10),   # [2]  streak          – Streak (Wait Hits)
    ( 6,   3,   8),   # [3]  pattern         – Pattern Match (X) [UI disabled]
    (10,   3,  15),   # [4]  voisins         – Voisins Missing (Wait)
    ( 9,   2,  15),   # [5]  tiers           – Tiers+Orph Missing (Wait)
    ( 8,   2,  12),   # [6]  left            – Left Side Missing (Wait)
    ( 8,   2,  12),   # [7]  right           – Right Side Missing (Wait)
    ( 8,   1,  10),   # [8]  ds              – 5 Double Street Strategy (Wait Streak)
    ( 9,   3,  15),   # [9]  d17             – Dynamic 17-Assault (Wait Misses)
    ( 9,   1,  15),   # [10] corner          – 5-Corner Stress Shuffle (Wait Misses)
    (15,  10,  19),   # [11] x19_start       – X-19 Start Count (X) [UI disabled]
    (22,   5,  50),   # [12] sniper          – Sniper S65+C19
    (18,   4, 100),   # [13] nr_spins        – Non-Repeaters (Last Spins)
    (12,   1,  36),   # [14] nr_target       – Non-Repeaters (Target Alert)
    # --- 🔥 TREND REVERSAL (OVERHEATED) sliders — Mode 1: rare, high-confidence ---
    # Mode 1 defaults are more conservative than the original hard-coded values to
    # produce fewer, higher-quality signals.  Original values are shown in comments.
    (10,   6,  15),   # [15] tr_short_window   – Overheat short window (orig: 10)
    ( 8,   5,  10),   # [16] tr_short_hits     – Short-window hits needed (orig: 7 → Mode1: 8, 80% dominance)
    (15,  10,  20),   # [17] tr_long_window    – Overheat long window (orig: 15)
    ( 9,   5,  15),   # [18] tr_long_hits      – Long-window hits needed (orig: 8 → Mode1: 9, 60% dominance)
    ( 5,   2,  10),   # [19] tr_min_streak     – Min consecutive streak (orig: 4 → Mode1: 5)
    ( 8,   4,  12),   # [20] tr_density_window – Density window size (orig: 8)
    ( 7,   3,   8),   # [21] tr_density_hits   – Density hits needed (orig: 6 → Mode1: 7, 87.5% density)
    (11,   5,  20),   # [22] tr_active_lifetime– Active lifetime after snap in spins (orig: 11)
]

# Color used for Sniper Strike street/corner highlights in the DE2D table.
# Must differ from active_style (#FFD700 yellow) to avoid confusion.
_SNIPER_HIGHLIGHT_COLOR = "#00BFFF"

# Color used for the European roulette section highlight border.
_SECTION_HIGHLIGHT_COLOR = "#FF00FF"

# ---------------------------------------------------------------------------
# Slider Auto-Nudge / Bet Sizing Discipline State
# ---------------------------------------------------------------------------
# _nudge_state holds all mutable discipline state so the module-level dict
# is the single source of truth.  Callbacks read and write this dict; they
# never store mode/cooldown data on the RouletteState object so there is no
# cross-contamination with game state.
_nudge_state: dict = {
    "mode": "MANUAL",   # "MANUAL" | "SUGGEST" | "AUTO"
    "overrides": {},    # {cfg_index: adjusted_threshold_int}
    "cooldown": {},     # {cfg_index: spin_count_when_last_adjusted}
    "cooldown_spins": 5,  # minimum spins between adjustments for the same slider
    "nudge_log": [],    # list of dicts; last 5 nudge events, newest appended last, displayed newest-first
}

# Human-readable names for each _DE2D_SLIDER_CFG index used by AUTO nudge.
_NUDGE_SLIDER_NAMES: dict = {
    0: "Missing Dozen/Col",
    1: "Even Money",
    2: "Streak",
    4: "Voisins",
    5: "Tiers+Orph",
    6: "Left of Zero",
    7: "Right of Zero",
    8: "Double Street",
    9: "Dynamic 17",
    10: "Corner",
}


# ---------------------------------------------------------------------------
# Slider / coercion utilities (also used by de2d_tracker_logic internals)
# ---------------------------------------------------------------------------

def _coerce_int(val, default: int) -> int:
    """Return *val* as an integer, or *default* if conversion fails.

    Gradio can occasionally pass None / empty-string / NaN to a callback when
    a slider component is non-interactive or hasn't been initialised yet.
    Coercing to int before arithmetic prevents the TypeError / ValueError that
    would otherwise cause Gradio to display the transient "Error" badge on
    every output slider.
    """
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _clamp(val: int, min_val: int, max_val: int) -> int:
    """Clamp *val* to [min_val, max_val] (inclusive).

    Assumes min_val <= max_val, as guaranteed by _DE2D_SLIDER_CFG entries.
    """
    return max(min_val, min(max_val, val))


def _safe_slider_val(val, cfg_index: int) -> int:
    """Coerce *val* to int and clamp it using _DE2D_SLIDER_CFG[cfg_index].

    This is the single entry-point used by all preset handlers so that every
    value written back to a slider is guaranteed to be an in-range integer.
    """
    default, min_val, max_val = _DE2D_SLIDER_CFG[cfg_index]
    return _clamp(_coerce_int(val, default), min_val, max_val)


# ---------------------------------------------------------------------------
# Auto-Nudge and Trend Reversal helper functions (moved from app.py)
# ---------------------------------------------------------------------------

def _detect_trend_reversal_overheated(
    spins,
    even_money_map,
    short_window=10,
    short_hits=8,
    long_window=15,
    long_hits=9,
    min_streak=5,
    density_window=8,
    density_hits=7,
    active_lifetime=11,
):
    """Detect an overheated even-money reversal (🔥 TREND REVERSAL trigger).

    Scans the spin history in chronological order for one of six even-money
    pairs (Red/Black, Even/Odd, Low/High and their reverses).  The detection
    works in three phases:

    Phase A — "Overheated" qualification
        The current history ending at index *h_end* qualifies as overheated
        toward *target* when ALL of the following hold:

        1. SHORT dominance : hits(target, last short_window) >= short_hits
        2. LONG  dominance : hits(target, last long_window)  >= long_hits
        3. Intensity (OR)  :
              a. consecutive streak of target hits (zeros are ignored, they do
                 not reset the streak) >= min_streak, OR
              b. hits(target, last density_window)            >= density_hits

        When the current spin is a target (or zero) and those conditions hold,
        the pair enters "Wait for Snap" state.

    Phase B — Snap (transition to ACTIVE)
        When the *opposite* lands while the immediately preceding history was
        overheated, a snap has occurred.  The signal becomes ACTIVE and
        recommends betting the opposite.

    Phase C — Active window / cancellation
        Once ACTIVE the signal stays alive for up to *active_lifetime* spins.
        It cancels early if a second opposite hit appears (suggesting chop
        rather than a clean reversal).

    Sanity clamping
        hits thresholds are clamped to their respective window sizes to prevent
        impossible conditions (e.g. needing 10 hits in a window of 8).

    Parameters
    ----------
    spins          : list[int]  – chronological spin history
    even_money_map : dict       – mapping name → set of numbers (EVEN_MONEY)
    short_window, short_hits   – short-window dominance parameters
                                  Mode 1 defaults: 10 window, 8 hits (80% dominance)
    long_window,  long_hits    – long-window dominance parameters
                                  Mode 1 defaults: 15 window, 9 hits (60% dominance)
    min_streak                 – consecutive streak threshold (zeros ignored)
                                  Mode 1 default: 5 (original was 4)
    density_window, density_hits – density (cluster) parameters
                                  Mode 1 defaults: 8 window, 7 hits (87.5% density)
    active_lifetime            – max spins the signal stays active after snap
                                  Mode 1 default: 11 (unchanged)

    Returns
    -------
    (target, opposite, snap_occurred, misses_since_snap)
    target / opposite are None when no qualifying pair is found.
    """
    # ── Sanity-clamp hits thresholds so they never exceed window sizes ──────
    short_hits    = min(short_hits,   short_window)
    long_hits     = min(long_hits,    long_window)
    density_hits  = min(density_hits, density_window)

    em_pairs = [
        ("Red",  "Black"), ("Black", "Red"),
        ("Even", "Odd"),   ("Odd",   "Even"),
        ("Low",  "High"),  ("High",  "Low"),
    ]

    # Need at least long_window spins before the long dominance check is valid
    if len(spins) < long_window:
        return None, None, False, 0

    for target, opposite in em_pairs:
        target_nums  = set(even_money_map[target])
        opposite_nums = set(even_money_map[opposite])

        is_active           = False
        snap_idx            = -1
        is_waiting_for_snap = False

        def _is_overheated(h_end):
            """Return True when spins[:h_end+1] qualifies as overheated toward target.

            Evaluates all three conditions described in Phase A above.
            h_end must be >= long_window - 1 for the long-window slice to exist.
            """
            # 1. Short-window dominance: high recent frequency of target
            h_short_start = h_end - short_window + 1
            if h_short_start < 0:
                return False
            h_short = spins[h_short_start: h_end + 1]
            if sum(1 for n in h_short if n in target_nums) < short_hits:
                return False

            # 2. Long-window dominance: sustained frequency over a larger window
            h_long_start = h_end - long_window + 1
            if h_long_start < 0:
                return False
            h_long = spins[h_long_start: h_end + 1]
            if sum(1 for n in h_long if n in target_nums) < long_hits:
                return False

            # 3a. Intensity: consecutive streak (zeros skip-count, non-target breaks)
            streak = 0
            for n in reversed(spins[:h_end + 1]):
                if n in target_nums:
                    streak += 1
                elif n == 0:
                    continue  # zero is neutral — does not reset streak
                else:
                    break
            if streak >= min_streak:
                return True  # intensity condition satisfied via streak

            # 3b. Intensity: density — target appears very often in a tight window
            h_dens_start = h_end - density_window + 1
            h_density = spins[h_dens_start: h_end + 1] if h_dens_start >= 0 else []
            if sum(1 for n in h_density if n in target_nums) >= density_hits:
                return True  # intensity condition satisfied via density

            return False  # neither intensity condition met

        # Scan from long_window-1 onward (minimum index where both the short- and
        # long-window slices are fully populated, i.e. h_end >= long_window - 1).
        for idx in range(long_window - 1, len(spins)):
            current_spin = spins[idx]

            # ── Phase C: signal is currently ACTIVE ────────────────────────
            if is_active:
                if current_spin in opposite_nums:
                    # A second opposite hit → chop detected; cancel signal
                    is_active           = False
                    snap_idx            = -1
                    is_waiting_for_snap = False
                elif (idx - snap_idx) > active_lifetime:
                    # Active window expired without another opposite hit
                    is_active           = False
                    snap_idx            = -1
                    is_waiting_for_snap = False
                continue  # skip Phase A/B while active

            # ── Phase B: snap check — opposite just landed ─────────────────
            if current_spin in opposite_nums:
                prev_idx = idx - 1
                if prev_idx >= long_window - 1 and _is_overheated(prev_idx):
                    # Opposite printed while the trend was overheated → snap!
                    is_active           = True
                    snap_idx            = idx
                    is_waiting_for_snap = False
                    continue
                # Opposite appeared but preconditions not met — not a valid snap
                is_waiting_for_snap = False
                continue

            # ── Phase A: build / maintain the "waiting" state ─────────────
            if current_spin in target_nums or current_spin == 0:
                # Target (or zero) landed; check if overheated conditions hold
                if idx >= long_window - 1 and _is_overheated(idx):
                    is_waiting_for_snap = True
                else:
                    is_waiting_for_snap = False
            else:
                # Non-target, non-opposite, non-zero spin → clear waiting state
                is_waiting_for_snap = False

        # ── Evaluate final state for this pair after scanning all spins ────
        if is_active:
            misses_since_snap = (len(spins) - 1) - snap_idx
            return target, opposite, True, misses_since_snap
        if is_waiting_for_snap:
            return target, opposite, False, 0

    # No qualifying pair found
    return None, None, False, 0


# ---------------------------------------------------------------------------
# Auto-Nudge helper functions
# ---------------------------------------------------------------------------


def _get_active_de2d_targets_from_flags(
    status_flags,
    worst_section_name, worst_section_miss_val, miss_wait,
    worst_even_name, worst_even_miss_val, even_wait,
    best_streak_name, best_streak_val, streak_wait,
    curr_voisins_miss, voisins_wait,
    curr_tiers_miss, tiers_wait,
    curr_left_miss, left_wait,
    curr_right_miss, right_wait,
    best_ds_name, best_ds_streak, ds_wait,
    d17_miss_count, d17_wait, d17_locked,
    max_corner_miss, corner_wait, best_corner_template,
):
    """Return list of active-target dicts for nudge recommendations.

    Only includes targets whose status_flags entry is truthy so the
    recommendations list stays compact.  All parameters are passed in
    explicitly; the function has no side-effects.
    """
    targets = []
    try:
        if status_flags.get("missing"):
            section = worst_section_name or "N/A"
            label = f"Missing {section}"
            targets.append({
                "name": label,
                "miss": worst_section_miss_val,
                "threshold": miss_wait,
                "cfg_idx": 0,
            })
        if status_flags.get("even"):
            targets.append({
                "name": worst_even_name or "Even Money",
                "miss": worst_even_miss_val,
                "threshold": even_wait,
                "cfg_idx": 1,
            })
        if status_flags.get("streak"):
            targets.append({
                "name": f"Streak Attack ({best_streak_name})",
                "miss": best_streak_val,
                "threshold": streak_wait,
                "cfg_idx": 2,
            })
        if status_flags.get("voisins"):
            targets.append({
                "name": "Voisins du Zéro",
                "miss": curr_voisins_miss,
                "threshold": voisins_wait,
                "cfg_idx": 4,
            })
        if status_flags.get("tiers"):
            targets.append({
                "name": "Tiers du Cylindre",
                "miss": curr_tiers_miss,
                "threshold": tiers_wait,
                "cfg_idx": 5,
            })
        if status_flags.get("left"):
            targets.append({
                "name": "Left of Zero",
                "miss": curr_left_miss,
                "threshold": left_wait,
                "cfg_idx": 6,
            })
        if status_flags.get("right"):
            targets.append({
                "name": "Right of Zero",
                "miss": curr_right_miss,
                "threshold": right_wait,
                "cfg_idx": 7,
            })
        if status_flags.get("5ds"):
            targets.append({
                "name": f"Double Street {best_ds_name}",
                "miss": best_ds_streak,
                "threshold": ds_wait,
                "cfg_idx": 8,
            })
        if status_flags.get("d17") and d17_locked:
            targets.append({
                "name": "Dynamic 17 Assault",
                "miss": d17_miss_count,
                "threshold": d17_wait,
                "cfg_idx": 9,
            })
        if status_flags.get("corner") and best_corner_template:
            targets.append({
                "name": f"Corner Shuffle ({best_corner_template[0]})",
                "miss": max_corner_miss,
                "threshold": corner_wait,
                "cfg_idx": 10,
            })
    except Exception:
        pass
    return targets



def _compute_recommendation_tier(miss_val, threshold):
    """Return (tier, bet_size, color, reason) for a single active target.

    Tier rules:
      miss/threshold >= 1.5  → PROTECT    ($0.01) — extreme drought, protect unit
      miss/threshold >= 1.0  → HOLD       ($0.10) — at threshold, hold & monitor
      miss/threshold <  1.0  → OPPORTUNITY ($1.00) — strong signal (defensive fallback
                               for edge cases where an active flag fires below threshold)
    """
    try:
        ratio = miss_val / threshold if threshold > 0 else 1.0
    except (TypeError, ZeroDivisionError):
        return "HOLD", "$0.10", "#f59e0b", "data unavailable, hold & monitor"
    if ratio >= 1.5:
        return "PROTECT", "$0.01", "#ef4444", f"deep drought ({miss_val}/{threshold}), protect unit"
    if ratio >= 1.0:
        return "HOLD", "$0.10", "#f59e0b", f"at threshold ({miss_val}/{threshold}), hold & monitor"
    # Fallback (active but ratio < 1 — shouldn't normally occur)
    return "OPPORTUNITY", "$1.00", "#22c55e", f"strong signal ({miss_val}/{threshold} misses)"



def _render_nudge_recommendations_html(active_targets, mode, dc_context=None):
    """Render compact per-target recommendation rows for SUGGEST/AUTO modes.

    Returns an empty string for MANUAL mode or when there are no active
    targets (and no dc_context) so the Bet Sizing Guide box stays unchanged.

    dc_context (optional dict):
        active     bool  – True when Double Confirmation is present
        target     str   – DC target name (e.g. "1st Column", "Black")
        confidence int   – DC confidence percent
        has_danger bool  – True when danger flags warrant clamping to $0.10
        clamp_note str   – Short reason string like "CLAMPED (Danger: Active≥3)"

    DC-HIGH clamp rules (enforced when dc_context["active"] and confidence>=70):
        - Default bet: $1.00 OPPORTUNITY
        - Clamped bet: $0.10 HOLD  (only when has_danger is True)
        - Never:       $0.01 PROTECT  for the DC target
    """
    dc = dc_context or {}
    dc_active = bool(dc.get("active"))
    if mode == "MANUAL" or (not active_targets and not dc_active):
        return ""
    try:
        mode_badge = (
            '<span style="background:#8b5cf6;color:white;font-size:10px;'
            'font-weight:700;padding:2px 8px;border-radius:5px;margin-left:6px;">AUTO</span>'
            if mode == "AUTO" else
            '<span style="background:#06b6d4;color:white;font-size:10px;'
            'font-weight:700;padding:2px 8px;border-radius:5px;margin-left:6px;">SUGGEST</span>'
        )
        rows = []

        # --- DC-HIGH primary row (always first when DC is active) ---
        if dc_active:
            dc_target_name = dc.get("target", "")
            dc_conf = int(dc.get("confidence", 0))
            if dc_conf >= 70:
                if dc.get("has_danger"):
                    dc_tier, dc_bet, dc_color = "HOLD", "$0.10", "#f59e0b"
                    dc_reason = dc.get("clamp_note", "CLAMPED")
                else:
                    dc_tier, dc_bet, dc_color = "OPPORTUNITY", "$1.00", "#22c55e"
                    dc_reason = "Double Confirmation HIGH"
            elif dc_conf >= 50:
                dc_tier, dc_bet, dc_color = "HOLD", "$0.10", "#f59e0b"
                dc_reason = "Double Confirmation MODERATE"
            else:
                dc_tier, dc_bet, dc_color = "PROTECT", "$0.01", "#ef4444"
                dc_reason = "Double Confirmation WEAK"
            dc_tier_icon = {"PROTECT": "🛡️", "HOLD": "⚖️", "OPPORTUNITY": "🎯"}.get(dc_tier, "⚖️")
            clamp_suffix = (
                f'<span style="color:#f59e0b;font-size:10px;margin-left:4px;">'
                f'{dc.get("clamp_note","")}</span>'
                if dc.get("has_danger") and dc_conf >= 70 else ""
            )
            dc_label = f"\U0001f525 {dc_target_name}"
            rows.append(
                f'<div style="display:flex;align-items:center;gap:6px;'
                f'padding:3px 0;border-bottom:1px solid #1e293b;'
                f'background:#0f2a1a;border-radius:4px;padding-left:4px;">'
                f'<span style="color:#86efac;font-size:11px;flex:1;min-width:0;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:700;" '
                f'title="{dc_target_name}">{dc_label}</span>'
                f'<span style="color:{dc_color};font-weight:700;font-size:11px;'
                f'white-space:nowrap;">{dc_bet}</span>'
                f'<span style="color:{dc_color};font-size:11px;white-space:nowrap;">'
                f'{dc_tier_icon}&nbsp;{dc_tier}</span>'
                f'{clamp_suffix}'
                f'</div>'
            )

        # --- Secondary rows: other active targets (skip DC target to avoid duplication) ---
        dc_name_lower = dc.get("target", "").lower() if dc_active else ""
        for t in active_targets:
            try:
                # Skip if this target's name is an exact match or the DC target appears
                # as a complete phrase within it (e.g. "Missing 1st Column" when DC is
                # "1st Column").  Plain substring is avoided to prevent "Red" from
                # accidentally matching a name like "Hundred".
                t_name_lower = t.get("name", "").lower()
                if dc_active and dc_name_lower and (
                    t_name_lower == dc_name_lower
                    or t_name_lower.startswith(dc_name_lower + " ")
                    or f" {dc_name_lower}" in t_name_lower
                ):
                    continue
                tier, bet, color, reason = _compute_recommendation_tier(
                    t.get("miss", 0), t.get("threshold", 1)
                )
                tier_icon = {"PROTECT": "🛡️", "HOLD": "⚖️", "OPPORTUNITY": "🎯"}.get(tier, "⚖️")
                rows.append(
                    f'<div style="display:flex;align-items:center;gap:6px;'
                    f'padding:3px 0;border-bottom:1px solid #1e293b;">'
                    f'<span style="color:#e2e8f0;font-size:11px;flex:1;min-width:0;'
                    f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" '
                    f'title="{t.get("name","")}">{t.get("name","")}</span>'
                    f'<span style="color:{color};font-weight:700;font-size:11px;'
                    f'white-space:nowrap;">{bet}</span>'
                    f'<span style="color:{color};font-size:11px;white-space:nowrap;">'
                    f'{tier_icon}&nbsp;{tier}</span>'
                    f'</div>'
                )
            except Exception:
                continue
        if not rows:
            return ""
        rows_html = "".join(rows)
        return (
            f'<div style="margin-top:9px;padding-top:8px;border-top:1px solid #334155;">'
            f'<div style="display:flex;align-items:center;margin-bottom:5px;">'
            f'<span style="color:#94a3b8;font-size:10px;text-transform:uppercase;'
            f'letter-spacing:1px;font-weight:700;">Active Target Recommendations</span>'
            f'{mode_badge}</div>'
            f'{rows_html}'
            f'</div>'
        )
    except Exception:
        return ""



def _get_dc_danger_info(status_flags):
    """Check for danger flags that warrant clamping a DC-HIGH ($1.00) rec to $0.10.

    Danger conditions (any single true condition is sufficient):
      - Active triggers count >= 3 (too many simultaneous signals)
      - Pattern forming / Pattern Match active
      - Streak Attack active (Two-Dozens/Columns counter-bet in play)
      - Overheated detected

    Returns:
        (has_danger: bool, clamp_note: str)
        clamp_note is empty when has_danger is False.
    """
    reasons = []
    try:
        active_count = sum(1 for v in status_flags.values() if v)
        if active_count >= 3:
            reasons.append("Active\u22653")
        if status_flags.get("pattern"):
            reasons.append("Pattern")
        if status_flags.get("streak"):
            reasons.append("Streak")
        if status_flags.get("overheated"):
            reasons.append("Overheat")
    except Exception:
        pass
    has_danger = bool(reasons)
    clamp_note = ("CLAMPED (Danger: " + "+".join(reasons) + ")") if reasons else ""
    return has_danger, clamp_note



def _auto_nudge_apply(status_flags, current_spin_count):
    """Apply AUTO-mode ±1 nudge to _nudge_state['overrides'] based on active flags.

    Adjustments are bounded by _DE2D_SLIDER_CFG min/max and subject to a
    per-slider cooldown so the same slider is not adjusted more than once
    every N spins.  Fails closed: any exception leaves overrides unchanged.

    Each successful nudge appends an entry to _nudge_state['nudge_log'] (max 5
    kept, oldest discarded).
    """
    try:
        if _nudge_state.get("mode") != "AUTO":
            return
        cooldown = _nudge_state.setdefault("cooldown", {})
        overrides = _nudge_state.setdefault("overrides", {})
        cooldown_spins = int(_nudge_state.get("cooldown_spins", 5))
        nudge_log = _nudge_state.setdefault("nudge_log", [])

        # Mapping: status_flags key -> _DE2D_SLIDER_CFG index
        _FLAG_CFG_MAP = {
            "missing": 0, "even": 1, "streak": 2,
            "voisins": 4, "tiers": 5, "left": 6, "right": 7,
            "5ds": 8, "d17": 9, "corner": 10,
        }
        for flag, cfg_idx in _FLAG_CFG_MAP.items():
            last_adj = cooldown.get(cfg_idx, -(cooldown_spins + 1))
            if current_spin_count - last_adj < cooldown_spins:
                continue  # cooldown still active for this slider
            cfg = _DE2D_SLIDER_CFG[cfg_idx]
            cur_val = overrides.get(cfg_idx, cfg[0])  # default from cfg
            is_active = bool(status_flags.get(flag))
            if is_active:
                # Trigger active: lower threshold by 1 to stay sensitive
                new_val = max(cfg[1], cur_val - 1)
                reason = f"Active trigger: {_NUDGE_SLIDER_NAMES.get(cfg_idx, flag)}"
            else:
                # Trigger quiet: nudge threshold back toward the default
                default_val = cfg[0]
                if cur_val < default_val:
                    new_val = min(cfg[2], cur_val + 1)
                    reason = "No longer active; relaxing toward default"
                else:
                    continue  # already at or above default, nothing to do
            if new_val != cur_val:
                overrides[cfg_idx] = new_val
                cooldown[cfg_idx] = current_spin_count
                nudge_log.append({
                    "slider": _NUDGE_SLIDER_NAMES.get(cfg_idx, f"Slider #{cfg_idx}"),
                    "old_val": cur_val,
                    "new_val": new_val,
                    "direction": "down" if new_val < cur_val else "up",
                    "reason": reason,
                })
                # Keep only the last 5 entries (trim unconditionally after append)
                _nudge_state["nudge_log"] = nudge_log[-5:]
    except Exception:
        pass  # fail closed — leave overrides untouched on any error



def _render_nudge_log_html() -> str:
    """Return compact AUTO NUDGE LOG HTML for display under the Bet Sizing Guide.

    Only rendered when mode is AUTO and there are log entries.  Entries are
    shown newest-first (last 5 kept in _nudge_state['nudge_log']).  Styling
    is intentionally minimal to match the dark-theme Bet Sizing Guide card.
    """
    try:
        if _nudge_state.get("mode") != "AUTO":
            return ""
        log = _nudge_state.get("nudge_log", [])
        if not log:
            return ""
        rows_html = ""
        for entry in reversed(log):
            slider = entry.get("slider", "?")
            old_v = entry.get("old_val", "?")
            new_v = entry.get("new_val", "?")
            reason = entry.get("reason", "")
            is_down = entry.get("direction", "down") == "down"
            arrow = "▼" if is_down else "▲"
            arrow_color = "#22c55e" if is_down else "#94a3b8"
            rows_html += (
                f'<div style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;'
                f'border-bottom:1px solid #1e293b;">'
                f'<span style="color:#8b5cf6;font-size:11px;font-weight:700;'
                f'white-space:nowrap;min-width:110px;">{slider}</span>'
                f'<span style="color:{arrow_color};font-size:11px;font-weight:700;'
                f'white-space:nowrap;">{old_v} {arrow} {new_v}</span>'
                f'<span style="color:#94a3b8;font-size:11px;flex:1;">{reason}</span>'
                f'</div>'
            )
        return (
            '<div style="margin-top:10px;padding-top:8px;border-top:1px solid #334155;">'
            '<div style="color:#8b5cf6;font-size:10px;font-weight:700;'
            'text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">'
            '⚙ AUTO NUDGE LOG</div>'
            + rows_html +
            '</div>'
        )
    except Exception:
        return ""



# ---------------------------------------------------------------------------
# Main tracker functions (moved from app.py)
# ---------------------------------------------------------------------------

def dozen_tracker(num_spins_to_check, consecutive_hits_threshold, alert_enabled, sequence_length, follow_up_spins, sequence_alert_enabled):
    """Track and display the history of Dozen hits for the last N spins, with optional alerts for consecutive hits and sequence matching."""
    try:
        return _dozen_tracker_inner(num_spins_to_check, consecutive_hits_threshold, alert_enabled, sequence_length, follow_up_spins, sequence_alert_enabled)
    except Exception as e:
        logger.error(f"dozen_tracker: Unexpected error: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        err = "⚠️ Dozen Tracker temporarily unavailable."
        return err, f"<p>{err}</p>", "<p>Sequence matching unavailable.</p>"


def _dozen_tracker_inner(num_spins_to_check, consecutive_hits_threshold, alert_enabled, sequence_length, follow_up_spins, sequence_alert_enabled):
    recommendations = []
    sequence_recommendations = []

    # Validate inputs
    try:
        num_spins_to_check = int(num_spins_to_check)
        consecutive_hits_threshold = int(consecutive_hits_threshold)
        sequence_length = int(sequence_length)
        follow_up_spins = int(follow_up_spins)
        if num_spins_to_check < 1:
            return "Error: Number of spins to check must be at least 1.", "<p>Error: Number of spins to check must be at least 1.</p>", "<p>Error: Number of spins to check must be at least 1.</p>"
        if consecutive_hits_threshold < 1:
            return "Error: Consecutive hits threshold must be at least 1.", "<p>Error: Consecutive hits threshold must be at least 1.</p>", "<p>Error: Consecutive hits threshold must be at least 1.</p>"
        if sequence_length < 1:
            return "Error: Sequence length must be at least 1.", "<p>Error: Sequence length must be at least 1.</p>", "<p>Error: Sequence length must be at least 1.</p>"
        if follow_up_spins < 1:
            return "Error: Follow-up spins must be at least 1.", "<p>Error: Follow-up spins must be at least 1.</p>", "<p>Error: Follow-up spins must be at least 1.</p>"
    except (ValueError, TypeError):
        return "Error: Invalid inputs. Please use positive integers.", "<p>Error: Invalid inputs. Please use positive integers.</p>", "<p>Error: Invalid inputs. Please use positive integers.</p>"

    # Get the last N spins for sequence matching
    recent_spins = state.last_spins[-num_spins_to_check:] if len(state.last_spins) >= num_spins_to_check else state.last_spins
    logger.debug(f"dozen_tracker: Tracking {num_spins_to_check} spins for sequence matching, recent_spins length = {len(recent_spins)}")
    
    if not recent_spins:
        return "Dozen Tracker: No spins recorded yet.", "<p>Dozen Tracker: No spins recorded yet.</p>", "<p>Dozen Tracker: No spins recorded yet.</p>"

    # Map each spin to its Dozen for sequence matching
    dozen_pattern = []
    dozen_counts = {"1st Dozen": 0, "2nd Dozen": 0, "3rd Dozen": 0, "Not in Dozen": 0}
    for spin in recent_spins:
        try:
            spin_value = int(spin)
        except (ValueError, TypeError):
            logger.warning(f"_dozen_tracker_inner: skipping non-integer spin {spin!r}")
            dozen_pattern.append("Not in Dozen")
            dozen_counts["Not in Dozen"] += 1
            continue
        if spin_value == 0:
            dozen_pattern.append("Not in Dozen")
            dozen_counts["Not in Dozen"] += 1
        else:
            found = False
            for name, numbers in DOZENS.items():
                if spin_value in numbers:
                    dozen_pattern.append(name)
                    dozen_counts[name] += 1
                    found = True
                    break
            if not found:
                dozen_pattern.append("Not in Dozen")
                dozen_counts["Not in Dozen"] += 1

    # Map the entire spin history to Dozens for sequence matching
    full_dozen_pattern = []
    for spin in state.last_spins:
        try:
            spin_value = int(spin)
        except (ValueError, TypeError):
            full_dozen_pattern.append("Not in Dozen")
            continue
        if spin_value == 0:
            full_dozen_pattern.append("Not in Dozen")
        else:
            found = False
            for name, numbers in DOZENS.items():
                if spin_value in numbers:
                    full_dozen_pattern.append(name)
                    found = True
                    break
            if not found:
                full_dozen_pattern.append("Not in Dozen")

    # Detect consecutive Dozen hits in the LAST 3 spins only (if alert is enabled)
    if alert_enabled:
        # Take only the last 3 spins (or fewer if not enough spins)
        last_three_spins = state.last_spins[-3:] if len(state.last_spins) >= 3 else state.last_spins
        logger.debug(f"dozen_tracker: Checking last 3 spins for consecutive hits, last_three_spins = {last_three_spins}")
        
        if len(last_three_spins) < 3:
            logger.debug("dozen_tracker: Not enough spins to check for consecutive hits (need at least 3).")
            state.last_dozen_alert_index = -1
            state.last_alerted_spins = None
        else:
            # Map the last 3 spins to their Dozens
            last_three_dozens = []
            for spin in last_three_spins:
                try:
                    spin_value = int(spin)
                except (ValueError, TypeError):
                    last_three_dozens.append("Not in Dozen")
                    continue
                if spin_value == 0:
                    last_three_dozens.append("Not in Dozen")
                else:
                    found = False
                    for name, numbers in DOZENS.items():
                        if spin_value in numbers:
                            last_three_dozens.append(name)
                            found = True
                            break
                    if not found:
                        last_three_dozens.append("Not in Dozen")
            
            logger.debug(f"dozen_tracker: Last 3 spins dozens = {last_three_dozens}")

            # Check if all 3 spins are in the same Dozen and not "Not in Dozen"
            if (last_three_dozens[0] == last_three_dozens[1] == last_three_dozens[2] and 
                last_three_dozens[0] != "Not in Dozen"):
                current_dozen = last_three_dozens[0]
                # Convert last_three_spins to a tuple for comparison (immutable and hashable)
                current_spins_tuple = tuple(last_three_spins)
                # Check if this set of spins is different from the last alerted set
                if state.last_alerted_spins != current_spins_tuple:
                    # Include the spins in the alert
                    spins_str = ", ".join(map(str, last_three_spins))
                    alert_message = f"Alert: {current_dozen} has hit 3 times consecutively! (Spins: {spins_str})"
                    gr.Warning(alert_message)
                    recommendations.append(alert_message)
                    state.last_dozen_alert_index = len(state.last_spins) - 1  # Update the last alerted index
                    state.last_alerted_spins = current_spins_tuple  # Store the spins that triggered this alert
            else:
                # If the last 3 spins don't form a streak, reset the alert index and spins
                state.last_dozen_alert_index = -1
                state.last_alerted_spins = None

    # Detect sequence matches (only if sequence alert is enabled)
    sequence_matches = []
    sequence_follow_ups = []
    if sequence_alert_enabled and len(full_dozen_pattern) >= sequence_length:
        # Take the last X spins to check for a match
        last_x_spins = full_dozen_pattern[-sequence_length:] if len(full_dozen_pattern) >= sequence_length else full_dozen_pattern
        logger.debug(f"dozen_tracker: Checking last {sequence_length} spins for sequence matching, last_x_spins = {last_x_spins}")
        
        if len(last_x_spins) < sequence_length:
            logger.debug(f"dozen_tracker: Not enough spins to check for sequence of length {sequence_length}.")
        else:
            # Convert the last X spins to a tuple for comparison
            last_x_pattern = tuple(last_x_spins)
            
            # Collect all sequences of length X within the tracking window (recent_spins)
            sequences = []
            for i in range(len(dozen_pattern) - sequence_length + 1):
                seq = tuple(dozen_pattern[i:i + sequence_length])
                # Only consider sequences that end before the last X spins
                if i + sequence_length <= len(dozen_pattern) - sequence_length:
                    sequences.append((i, seq))
            
            logger.debug(f"dozen_tracker: Found {len(sequences)} sequences of length {sequence_length} in the tracking window")

            # Check if the last X spins match any previous sequence
            for start_idx, seq in sequences:
                if seq == last_x_pattern:
                    # Check if we've already alerted for this exact pattern
                    if seq not in state.alerted_patterns:
                        sequence_matches.append((start_idx, seq))
                        # Get the next Y spins after the first occurrence
                        follow_up_start = start_idx + sequence_length
                        follow_up_end = follow_up_start + follow_up_spins
                        if follow_up_end <= len(dozen_pattern):
                            follow_up = dozen_pattern[follow_up_start:follow_up_end]
                            sequence_follow_ups.append((start_idx, seq, follow_up))
                        # Mark this pattern as alerted
                        state.alerted_patterns.add(seq)

            # If a match is found, provide betting recommendations with spin context
            if sequence_matches:
                latest_match = max(sequence_matches, key=lambda x: x[0])  # Latest match by start index
                latest_start_idx, matched_sequence = latest_match
                # Find the follow-up spins for the first occurrence of this sequence
                first_occurrence = min((seq for seq in sequences if seq[1] == matched_sequence), key=lambda x: x[0])[0]
                follow_up_start = first_occurrence + sequence_length
                follow_up_end = follow_up_start + follow_up_spins
                # Adjust indices for the full spin history
                latest_start_idx_full = len(full_dozen_pattern) - sequence_length
                # Get the actual spins that triggered the sequence
                sequence_spins = recent_spins[-sequence_length:]  # Last X spins
                sequence_spins_str = ", ".join(map(str, sequence_spins))
                if follow_up_end <= len(dozen_pattern):
                    follow_up = dozen_pattern[follow_up_start:follow_up_end]
                    alert_message = f"Alert: Sequence {', '.join(matched_sequence)} has repeated at spins {sequence_spins_str}!"
                    gr.Warning(alert_message)
                    sequence_recommendations.append(alert_message)
                    sequence_recommendations.append(f"Previous follow-up spins (next {follow_up_spins}): {', '.join(follow_up)}")
                    sequence_recommendations.append("Betting Recommendations (Bet Against Historical Follow-Ups):")
                    all_dozens = ["1st Dozen", "2nd Dozen", "3rd Dozen"]
                    for idx, dozen in enumerate(follow_up):
                        if dozen == "Not in Dozen":
                            sequence_recommendations.append(f"Spin {idx + 1}: 0 (Not in Dozen) - No bet recommendation.")
                        else:
                            dozens_to_bet = [d for d in all_dozens if d != dozen]
                            sequence_recommendations.append(f"Spin {idx + 1}: Bet against {dozen} - Bet on {', '.join(dozens_to_bet)}")
            else:
                # If no match is found, reset the alerted patterns to allow future matches
                state.alerted_patterns.clear()

    # Text summary for Dozen Tracker
    recommendations.append(f"Dozen Tracker (Last {len(recent_spins)} Spins):")
    recommendations.append("Dozen History: " + ", ".join(dozen_pattern))
    recommendations.append("\nSummary of Dozen Hits:")
    for name, count in dozen_counts.items():
        recommendations.append(f"{name}: {count} hits")

    # HTML representation for Dozen Tracker
    html_output = f'<h4>Dozen Tracker (Last {len(recent_spins)} Spins):</h4>'
    html_output += '<div style="display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 10px;">'
    for dozen in dozen_pattern:
        color = {
            "1st Dozen": "#FF6347",  # Tomato red
            "2nd Dozen": "#4682B4",  # Steel blue
            "3rd Dozen": "#32CD32",  # Lime green
            "Not in Dozen": "#808080"  # Gray for 0
        }.get(dozen, "#808080")
        html_output += f'<span style="background-color: {color}; color: white; padding: 2px 5px; border-radius: 3px; display: inline-block;">{dozen}</span>'
    html_output += '</div>'
    if alert_enabled and "Alert:" in "\n".join(recommendations):
        # Extract the alert message from recommendations
        alert_message = next((line for line in recommendations if line.startswith("Alert:")), "")
        html_output += f'<p style="color: red; font-weight: bold;">{alert_message}</p>'
    html_output += '<h4>Summary of Dozen Hits:</h4>'
    html_output += '<ul style="list-style-type: none; padding-left: 0;">'
    for name, count in dozen_counts.items():
        html_output += f'<li>{name}: {count} hits</li>'
    html_output += '</ul>'

    # HTML representation for Sequence Matching
    sequence_html_output = "<h4>Sequence Matching Results:</h4>"
    if not sequence_alert_enabled:
        sequence_html_output += "<p>Sequence matching is disabled. Enable it to see results.</p>"
    elif len(dozen_pattern) < sequence_length:
        sequence_html_output += f"<p>Not enough spins to match a sequence of length {sequence_length}.</p>"
    elif not sequence_matches:
        sequence_html_output += "<p>No sequence matches found yet.</p>"
    else:
        sequence_html_output += "<ul style='list-style-type: none; padding-left: 0;'>"
        for start_idx, seq in sequence_matches:
            # Adjust the start index for display based on the full spin history
            display_start_idx = len(full_dozen_pattern) - sequence_length
            sequence_html_output += f"<li>Match found at spins {display_start_idx + 1} to {display_start_idx + sequence_length}: {', '.join(seq)}</li>"
        sequence_html_output += "</ul>"
        if sequence_recommendations:
            sequence_html_output += "<h4>Latest Match Details:</h4>"
            sequence_html_output += "<ul style='list-style-type: none; padding-left: 0;'>"
            for rec in sequence_recommendations:
                if "Alert:" in rec:
                    sequence_html_output += f"<li style='color: red; font-weight: bold;'>{rec}</li>"
                else:
                    sequence_html_output += f"<li>{rec}</li>"
            sequence_html_output += "</ul>"

    return "\n".join(recommendations), html_output, sequence_html_output


    # New: Even Money Bet Tracker Function

def even_money_tracker(spins_to_check, consecutive_hits_threshold, alert_enabled, combination_mode, track_red, track_black, track_even, track_odd, track_low, track_high, identical_traits_enabled, consecutive_identical_count):
    """Track even money bets and their combinations for consecutive hits, with optional tracking of consecutive identical trait combinations."""
    try:
        return _even_money_tracker_inner(spins_to_check, consecutive_hits_threshold, alert_enabled, combination_mode, track_red, track_black, track_even, track_odd, track_low, track_high, identical_traits_enabled, consecutive_identical_count)
    except Exception as e:
        logger.error(f"even_money_tracker: Unexpected error: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        err = "⚠️ Even Money Tracker temporarily unavailable."
        return err, f"<div class='even-money-tracker-container'><p>{err}</p></div>"


def _even_money_tracker_inner(spins_to_check, consecutive_hits_threshold, alert_enabled, combination_mode, track_red, track_black, track_even, track_odd, track_low, track_high, identical_traits_enabled, consecutive_identical_count):
    # Sanitize inputs with defaults to prevent None or invalid values
    spins_to_check = int(spins_to_check) if spins_to_check and str(spins_to_check).strip().isdigit() else 5
    consecutive_hits_threshold = int(consecutive_hits_threshold) if consecutive_hits_threshold and str(consecutive_hits_threshold).strip().isdigit() else 3
    consecutive_identical_count = int(consecutive_identical_count) if consecutive_identical_count and str(consecutive_identical_count).strip().isdigit() else 2

    # Validate inputs
    if spins_to_check < 1 or consecutive_hits_threshold < 1 or consecutive_identical_count < 1:
        return "Error: Inputs must be at least 1.", "<div class='even-money-tracker-container'><p>Error: Inputs must be at least 1.</p></div>"

    # Get recent spins
    recent_spins = state.last_spins[-spins_to_check:] if len(state.last_spins) >= spins_to_check else state.last_spins
    if not recent_spins:
        return "Even Money Tracker: No spins recorded yet.", "<div class='even-money-tracker-container'><p>Even Money Tracker: No spins recorded yet.</p></div>"

    # Determine which categories to track
    categories_to_track = []
    if track_red:
        categories_to_track.append("Red")
    if track_black:
        categories_to_track.append("Black")
    if track_even:
        categories_to_track.append("Even")
    if track_odd:
        categories_to_track.append("Odd")
    if track_low:
        categories_to_track.append("Low")
    if track_high:
        categories_to_track.append("High")

    # If no categories are explicitly selected, track all categories by default
    if not categories_to_track:
        categories_to_track = ["Red", "Black", "Even", "Odd", "Low", "High"]

    # Map spins to even money categories and track full trait combinations
    pattern = []
    category_counts = {name: 0 for name in EVEN_MONEY.keys()}
    trait_combinations = []  # Store the full trait combination for each spin (e.g., "Red, Odd, Low")
    hit_spins = []  # Track spins for each pattern element (Hit/Miss)
    for spin in recent_spins:
        try:
            spin_value = int(spin)
        except (ValueError, TypeError):
            logger.warning(f"_even_money_tracker_inner: skipping non-integer spin {spin!r}")
            pattern.append("Miss")
            hit_spins.append(str(spin))
            trait_combinations.append("None, None, None")
            continue
        spin_categories = []
        for name, numbers in EVEN_MONEY.items():
            if spin_value in numbers:
                spin_categories.append(name)
                category_counts[name] += 1

        # Determine if the spin matches the tracked combination
        if combination_mode == "And":
            if all(cat in spin_categories for cat in categories_to_track):
                pattern.append("Hit")
                hit_spins.append(str(spin_value))
            else:
                pattern.append("Miss")
                hit_spins.append(str(spin_value))
        else:  # Or mode
            if any(cat in spin_categories for cat in categories_to_track):
                pattern.append("Hit")
                hit_spins.append(str(spin_value))
            else:
                pattern.append("Miss")
                hit_spins.append(str(spin_value))

        # Build the full trait combination for this spin (Color, Parity, Range)
        color = "Red" if "Red" in spin_categories else ("Black" if "Black" in spin_categories else "None")
        parity = "Even" if "Even" in spin_categories else ("Odd" if "Odd" in spin_categories else "None")
        range_ = "Low" if "Low" in spin_categories else ("High" if "High" in spin_categories else "None")
        trait_combination = f"{color}, {parity}, {range_}"
        trait_combinations.append(trait_combination)

    # Track consecutive hits of the selected combination with spin context
    current_streak = 1 if pattern[0] == "Hit" else 0
    max_streak = current_streak
    max_streak_start = 0
    current_streak_spins = [hit_spins[0]] if pattern[0] == "Hit" else []
    max_streak_spins = current_streak_spins[:]
    for i in range(1, len(pattern)):
        if pattern[i] == "Hit" and pattern[i-1] == "Hit":
            current_streak += 1
            current_streak_spins.append(hit_spins[i])
        else:
            current_streak = 1 if pattern[i] == "Hit" else 0
            current_streak_spins = [hit_spins[i]] if pattern[i] == "Hit" else []
        if current_streak > max_streak:
            max_streak = current_streak
            max_streak_start = i - current_streak + 1
            max_streak_spins = current_streak_spins[:]

    # Track consecutive identical trait combinations with spin context
    identical_recommendations = []
    identical_html_output = ""
    betting_recommendation = None
    if identical_traits_enabled:
        # Detect consecutive identical trait combinations
        identical_streak = 1
        identical_streak_start = 0
        identical_matches = []
        identical_streak_spins = [recent_spins[0]]  # Track spins for identical streaks
        for i in range(1, len(trait_combinations)):
            if trait_combinations[i] == trait_combinations[i-1] and trait_combinations[i] != "None, None, None":
                identical_streak += 1
                identical_streak_spins.append(recent_spins[i])
                if identical_streak == consecutive_identical_count:
                    identical_matches.append((i - consecutive_identical_count + 1, trait_combinations[i], identical_streak_spins[-consecutive_identical_count:]))
                    identical_streak_start = i - consecutive_identical_count + 1
            else:
                identical_streak = 1
                identical_streak_spins = [recent_spins[i]]
        if identical_matches:
            # Process the most recent match
            latest_match_start, matched_traits, matched_spins = identical_matches[-1]
            spins_str = ", ".join(map(str, matched_spins))
            if alert_enabled:
                gr.Warning(f"Alert: Traits '{matched_traits}' appeared {consecutive_identical_count} times consecutively! (Spins: {spins_str})")
            identical_recommendations.append(f"Alert: Traits '{matched_traits}' appeared {consecutive_identical_count} times consecutively! (Spins: {spins_str})")

            # Calculate opposite traits
            traits = [t.strip() for t in matched_traits.split(",")]
            opposite_traits = []
            for trait in traits:
                if trait == "Red":
                    opposite_traits.append("Black")
                elif trait == "Black":
                    opposite_traits.append("Red")
                elif trait == "Even":
                    opposite_traits.append("Odd")
                elif trait == "Odd":
                    opposite_traits.append("Even")
                elif trait == "Low":
                    opposite_traits.append("High")
                elif trait == "High":
                    opposite_traits.append("Low")
                else:
                    opposite_traits.append("None")
            opposite_combination = ", ".join(opposite_traits)
            identical_recommendations.append(f"Opposite Traits: {opposite_combination}")

            # Get the top-tier even money bet (highest score in even_money_scores)
            sorted_even_money = sorted(state.even_money_scores.items(), key=lambda x: x[1], reverse=True)
            even_money_hits = [item for item in sorted_even_money if item[1] > 0]
            if even_money_hits:
                top_tier_bet = even_money_hits[0][0]  # e.g., "Even"
                top_tier_score = even_money_hits[0][1]
                identical_recommendations.append(f"Current Top-Tier Even Money Bet (Yellow): {top_tier_bet} (Score: {top_tier_score})")

                # Correctly compare top-tier bet to the corresponding opposite trait
                opposites_map = {
                    "Red": "Black", "Black": "Red",
                    "Even": "Odd", "Odd": "Even",
                    "Low": "High", "High": "Low"
                }
                # Determine which trait category the top-tier bet belongs to
                trait_index = None
                if top_tier_bet in ["Red", "Black"]:
                    trait_index = 0  # Color
                elif top_tier_bet in ["Even", "Odd"]:
                    trait_index = 1  # Parity
                elif top_tier_bet in ["Low", "High"]:
                    trait_index = 2  # Range

                match_found = False
                if trait_index is not None:
                    corresponding_opposite = opposite_traits[trait_index]
                    # Check if the top-tier bet matches its opposite in the correct category
                    if top_tier_bet == corresponding_opposite:
                        match_found = True

                if match_found:
                    betting_recommendation = f"<span class='betting-recommendation'>Match found! Bet on '{top_tier_bet}' for the next 3 spins.</span>"
                    if alert_enabled:
                        gr.Warning(f"Match found! Bet on '{top_tier_bet}' for the next 3 spins.")
                    identical_recommendations.append(betting_recommendation)
                else:
                    identical_recommendations.append("No match with opposite traits. No betting recommendation.")
            else:
                identical_recommendations.append("No top-tier even money bet available (no hits yet).")

            # Build HTML output for identical traits tracking
            identical_html_output = "<div class='identical-traits-section'>"
            identical_html_output += "<h4>Consecutive Identical Traits Tracking:</h4>"
            identical_html_output += "<ul style='list-style-type: none; padding-left: 0;'>"
            for rec in identical_recommendations:
                if "Alert:" in rec or "Match found!" in rec and "betting-recommendation" not in rec:
                    identical_html_output += f"<li style='color: red; font-weight: bold;'>{rec}</li>"
                else:
                    identical_html_output += f"<li>{rec}</li>"
            identical_html_output += "</ul>"
            identical_html_output += "</div>"

    # Generate text and HTML for the original even money tracking with spin context
    tracked_str = " and ".join(categories_to_track) if combination_mode == "And" else " or ".join(categories_to_track)
    recommendations = []
    html_output = "<div class='even-money-tracker-container'>"
    recommendations.append(f"Even Money Tracker (Last {len(recent_spins)} Spins):")
    recommendations.append(f"Tracking: {tracked_str} ({combination_mode})")
    recommendations.append("History: " + ", ".join(pattern))
    if alert_enabled and max_streak >= consecutive_hits_threshold:
        # Include the spins that triggered the streak
        streak_spins = ", ".join(max_streak_spins[-consecutive_hits_threshold:])
        gr.Warning(f"Alert: {tracked_str} hit {max_streak} times consecutively! (Spins: {streak_spins})")
        recommendations.append(f"\nAlert: {tracked_str} hit {max_streak} times consecutively! (Spins: {streak_spins})")
    recommendations.append("\nSummary of Hits:")
    for name, count in category_counts.items():
        if name in categories_to_track:
            recommendations.append(f"{name}: {count} hits")

    html_output += f'<h4>Even Money Tracker (Last {len(recent_spins)} Spins):</h4>'
    html_output += f'<p>Tracking: {tracked_str} ({combination_mode})</p>'
    html_output += '<div style="display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 10px;">'
    for status, spin in zip(pattern, hit_spins):
        color = "#32CD32" if status == "Hit" else "#FF6347"  # Green for Hit, Red for Miss
        html_output += f'<span style="background-color: {color}; color: white; padding: 2px 5px; border-radius: 3px; display: inline-block;" title="Spin: {spin}">{status}</span>'
    html_output += '</div>'
    if alert_enabled and max_streak >= consecutive_hits_threshold:
        html_output += f'<p style="color: red; font-weight: bold;">Alert: {tracked_str} hit {max_streak} times consecutively! (Spins: {streak_spins})</p>'
    html_output += '<h4>Summary of Hits:</h4>'
    html_output += '<ul style="list-style-type: none; padding-left: 0;">'
    for name, count in category_counts.items():
        if name in categories_to_track:
            html_output += f'<li>{name}: {count} hits</li>'
    html_output += '</ul>'

    # Append the identical traits tracking output (if enabled)
    if identical_traits_enabled and identical_html_output:
        html_output += identical_html_output

    html_output += "</div>"

    return "\n".join(recommendations), html_output


def de2d_tracker_logic(miss_threshold=14, even_threshold=8, streak_threshold=9, pattern_x=6, voisins_threshold=10, tiers_threshold=9, left_threshold=8, right_threshold=8, ds_threshold=8, d17_threshold=9, corner_threshold=9, grind_active=False, grind_target="3rd Dozen", ramp_active=False, x19_active=False, x19_start=15, sniper_threshold=22, pinned_numbers_raw=None, hud_filters=None, non_repeater_spins=18, nr_target=12,
                       tr_short_window=10, tr_short_hits=8, tr_long_window=15, tr_long_hits=9,
                       tr_min_streak=5, tr_density_window=8, tr_density_hits=7, tr_active_lifetime=11,
                       return_cards_only=False):
    """
    Logic for the DE2D Tracker section.
    When return_cards_only=True, returns only the active strategy cards HTML
    (used for the strategy_cards_area component near the roulette table).
    """
    try:
        if hud_filters is None:
            hud_filters = _HUD_DEFAULT_VISIBLE
        
        # --- STABILITY FIX: SYNC STATE WITH INPUT ---
        if pinned_numbers_raw and pinned_numbers_raw != "[]":
            try:
                data = json.loads(pinned_numbers_raw)
                state.pinned_numbers = {int(x) for x in data if str(x).isdigit()}
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        elif pinned_numbers_raw == "[]":
             state.pinned_numbers = set()
        
        pinned_set = state.pinned_numbers

        # =========================================================
        # 1. STATE & DATA INITIALIZATION
        # =========================================================
        if state.last_spins is None: state.last_spins = []

        # Store sniper threshold in state so the summary bar can display progress
        state.sniper_threshold = sniper_threshold

        config_html = ""
        spins_html = ""
        actions_section = ""
        visual_table = ""
        sequences_info_html = ""
        active_actions = []
        highlight_targets = set() 
        sniper_highlight_targets = set()
        grind_targets = set() 
        active_target_groups = []
        on_deck_triggers = []
        status_cards_html = ""
        
        inactive_style = "background-color: #34495e; color: #ecf0f1; font-size: 11px; border: 1px solid #455a64; font-weight: bold;"
        active_style = "background-color: #FFD700; color: #000000; font-weight: 900; font-size: 12px; border: 2px solid #FFC107; box-shadow: 0 0 10px #FFD700;"
        sniper_style = f"background-color: {_SNIPER_HIGHLIGHT_COLOR}; color: #000000; font-weight: 900; font-size: 12px; border: 2px solid {_SNIPER_HIGHLIGHT_COLOR}; box-shadow: 0 0 10px {_SNIPER_HIGHLIGHT_COLOR};"
        grind_style = "background-color: #2ecc71; color: white; font-weight: bold; font-size: 11px; border: 1px solid #27ae60;"
        rank1_style = "border: 3px solid #FFFF00 !important; box-shadow: 0 0 15px #FFFF00 !important; z-index: 10;"
        rank2_style = "border: 2px solid #00FFFF !important; box-shadow: 0 0 10px #00FFFF !important; z-index: 5;"
        rank3_style = "border: 2px solid #32CD32 !important; box-shadow: 0 0 8px #32CD32 !important;"

        raw_spins = state.last_spins
        spins = []
        for s in raw_spins:
            try:
                if str(s).strip().lstrip('-').isdigit(): spins.append(int(s))
            except (ValueError, TypeError): continue
        current_spin_count = len(spins)

        X19_PROGRESSIONS = {
            13: [(13, 1), (14, 1), (15, 2), (16, 3), (17, 5), (18, 8), (19, 13), (20, 60)], 
            14: [(14, 1), (15, 2), (16, 3), (17, 5), (18, 8), (19, 13), (20, 45)],
            15: [(15, 1), (16, 2), (17, 4), (18, 7), (19, 12), (20, 35)],
            16: [(16, 1), (17, 3), (18, 6), (19, 11), (20, 30)],
            17: [(17, 2), (18, 5), (19, 11), (20, 28)],
            18: [(18, 3), (19, 9), (20, 27)],
            19: [(19, 5), (20, 25), (21, 45)]
        }

        ramp_counts = {n: 0 for n in range(37)}
        ramp_last_pos = {n: -1 for n in range(37)}
        for idx, s in enumerate(spins): 
            ramp_counts[s] += 1
            ramp_last_pos[s] = idx
        sorted_ramp = sorted(range(37), key=lambda x: (-ramp_counts[x], -ramp_last_pos[x]))
        ramp_ranks = {num: i + 1 for i, num in enumerate(sorted_ramp[:12]) if ramp_counts[num] > 0}

        seq_ramp_config = [(n, 1) for n in range(4, 13)] + [(n, 2) for n in range(4, 13)] + [(n, 4) for n in range(4, 13)] + [(n, 8) for n in range(4, 13)] + [(n, 16) for n in range(4, 13)]
        seq_ramp_units = [x[1] for x in seq_ramp_config]
        curr_step_idx = min(state.ramp_step_index, len(seq_ramp_config) - 1)
        active_ramp_spots = seq_ramp_config[curr_step_idx][0] 

        def parse_arg(val, default):
            try: return int(val) if val is not None else default
            except (ValueError, TypeError): return default
        
        def get_last_unique_numbers(spin_history, count_needed):
            unique = []
            for s in reversed(spin_history):
                if s not in unique:
                    unique.insert(0, s)
                if len(unique) == count_needed:
                    return unique
            return unique 

        def get_status_style(is_active):
            if is_active: return "background: linear-gradient(135deg, #d32f2f, #ff5252); color: white; font-weight: bold; border: 2px solid #ff8a80; box-shadow: 0 0 10px rgba(255, 82, 82, 0.7); animation: pulse-red 1.5s infinite;"
            return "background: #f5f5f5; color: #777; border: 1px solid #ddd;"

        def get_counter_color(curr, thresh):
            if curr >= thresh: return "color: #fff; font-weight: bold; text-shadow: 0 0 2px black;" 
            if curr >= thresh - 1: return "color: #d32f2f; font-weight: bold;" 
            if curr >= thresh - 2: return "color: #f57c00; font-weight: bold;" 
            return "color: #333;" 

        def get_progress_bar_html(current, threshold):
            if threshold <= 0: threshold = 1
            pct = min(100, (current / threshold) * 100)
            bar_color = "#4CAF50"
            if pct >= 50: bar_color = "#FFC107"
            if pct >= 80: bar_color = "#FF5722"
            if pct >= 100: bar_color = "#D32F2F"
            return f'<div style="width: 100%; height: 4px; background-color: rgba(0,0,0,0.1); border-radius: 2px; margin-top: 4px; overflow: hidden;"><div style="width: {pct}%; height: 100%; background-color: {bar_color}; transition: width 0.3s ease;"></div></div>'

        def format_seq(data_list):
            return " ".join([f"{item[0]}" for item in data_list])

        def format_sequence_html(sequence, current_val, threshold):
            idx = current_val - threshold
            if isinstance(sequence, list) and all(isinstance(x, (int, float)) for x in sequence):
                 if threshold == 0: idx = current_val
            if idx < 0: idx = -1 
            if idx >= len(sequence): idx = len(sequence) - 1 
            html_parts = []
            for i, val in enumerate(sequence):
                if i == idx:
                    html_parts.append(f'<span style="display:inline-block; transform:scale(1.3); color:#FFD700; background:#b71c1c; border:1px solid #FFD700; padding:0 4px; border-radius:3px; font-weight:900; box-shadow:0 0 8px #FFD700;">{val}</span>')
                else:
                    html_parts.append(str(val))
            return f"[{', '.join(html_parts)}]"

        def generate_status_card(title, target, current, threshold, sequence, flag_active, cost_per_unit=1):
            step_index = max(0, current - threshold)
            total_steps = len(sequence)
            remaining_units = 0
            if step_index < total_steps: remaining_units = sum(sequence[step_index:])
            is_halfway = step_index >= (total_steps / 2)
            is_danger = step_index >= (total_steps * 0.8)
            if flag_active:
                if is_danger:
                    card_style = "background: linear-gradient(135deg, #b71c1c, #d32f2f); color: white; border: 2px solid #ff5252; animation: pulse-red 1s infinite;"
                    counter_color = "color: #fff; text-shadow: 0 0 2px black;"
                    risk_badge = "⚠️ CRITICAL"
                elif is_halfway:
                    card_style = "background: linear-gradient(135deg, #f57c00, #ff9800); color: white; border: 2px solid #ffcc80;"
                    counter_color = "color: #fff; text-shadow: 0 0 2px black;"
                    risk_badge = "🟠 HIGH RISK"
                else:
                    card_style = "background: linear-gradient(135deg, #d32f2f, #ff5252); color: white; border: 2px solid #ff8a80; box-shadow: 0 0 10px rgba(255, 82, 82, 0.7);"
                    counter_color = "color: #fff; text-shadow: 0 0 2px black;"
                    risk_badge = "ACTIVE"
                info_footer = f'<div style="margin-top:6px; font-size:9px; display:flex; justify-content:space-between; background:rgba(0,0,0,0.2); padding:3px 6px; border-radius:4px;"><span style="font-weight:bold;">Step: {step_index+1}/{total_steps}</span><span style="font-weight:bold;">Req: ${remaining_units * cost_per_unit:.0f}</span></div>'
            else:
                card_style = "background: #f5f5f5; color: #777; border: 1px solid #ddd;"
                counter_color = get_counter_color(current, threshold)
                risk_badge = "WAITING"
                info_footer = ""
            prog_bar = get_progress_bar_html(current, threshold)
            seq_display = format_sequence_html(sequence, current, threshold)
            return f'<div class="status-card" style="{card_style}"><div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:2px;"><div style="font-size:10px; font-weight:bold; text-transform:uppercase;">{title}</div><div style="font-size:9px; font-weight:bold; background:rgba(255,255,255,0.2); padding:1px 3px; border-radius:3px;">{risk_badge}</div></div><div style="font-size:13px; font-weight:800; margin-bottom:4px;">{target}</div><span class="live-count" style="{counter_color}">Current: {current}/{threshold}</span>{prog_bar}<span style="font-size:10px; opacity:0.8;">{seq_display}</span>{info_footer}</div>'

        def count_misses(target_set, spin_list, zero_is_miss=True):
            count = 0
            for s in reversed(spin_list):
                if s in target_set: return count
                if s == 0 and not zero_is_miss: return count 
                count += 1
            return count

        def count_hits(target_set, spin_list):
            count = 0
            for s in reversed(spin_list):
                if s in target_set: count += 1
                elif s == 0: return count
                else: return count
            return count
        
        def count_hits_with_zero(target_set, spin_list):
            count = 0
            for s in reversed(spin_list):
                if s in target_set or s == 0: count += 1
                else: return count
            return count

        def count_frequency(target_set, spin_list):
            return sum(1 for s in spin_list if s in target_set)

        def get_header_color(title):
            if "MISSING" in title: return "#1976D2"
            if "STREAK" in title: return "#E64A19"
            if "EVEN" in title: return "#388E3C"
            if "PATTERN" in title: return "#7B1FA2"
            if "VOISINS" in title: return "#0097A7"
            if "TIERS" in title: return "#0288D1"
            if "SIDE" in title: return "#FBC02D";
            if "5DS" in title: return "#C2185B"
            if "17" in title: return "#D32F2F"
            if "CORNER" in title: return "#FF9800"
            if "GRIND" in title: return "#2E7D32"
            if "ZERO" in title: return "#2ECC71"
            if "19" in title: return "#FFD700"
            return "#455A64"

        def get_text_color_for_header(title):
            if "SIDE" in title or "19" in title: return "#333" 
            return "#FFF"
        
        def get_hottest_sector(spins):
            if not spins: return "3rd Dozen" 
            d_counts = {d: count_frequency(set(nums), spins) for d, nums in DOZENS.items()}
            c_counts = {c: count_frequency(set(nums), spins) for c, nums in COLUMNS.items()}
            best_d = max(d_counts.items(), key=lambda x: x[1])
            best_c = max(c_counts.items(), key=lambda x: x[1])
            if best_d[1] == best_c[1]: return [best_d[0], best_c[0]]
            elif best_d[1] > best_c[1]: return best_d[0]
            else: return best_c[0]

        def calculate_nested_cold_zones(spins):
            """Identifies the coldest Dozen, the coldest DS within that dozen, and the coldest Corner within that DS."""
            if not spins:
                return "Waiting for data...", "N/A", [], []

            # 1. FIND COLDEST DOZEN (Tie-break by recency)
            dozen_stats = []
            for d_name, d_nums in DOZENS.items():
                hits = sum(1 for s in spins if int(s) in d_nums)
                last_pos = -1
                for i, s in enumerate(reversed(spins)):
                    if int(s) in d_nums:
                        last_pos = i
                        break
                if last_pos == -1: last_pos = len(spins) + 100
                dozen_stats.append({"name": d_name, "hits": hits, "recency": last_pos, "nums": d_nums})
            
            dozen_stats.sort(key=lambda x: (x['hits'], -x['recency']))
            coldest_dozen = dozen_stats[0]

            # 2. FIND COLDEST DOUBLE STREET WITHIN THAT DOZEN
            ds_stats = []
            local_ds = {
                "DS 1-6": [1, 2, 3, 4, 5, 6], "DS 4-9": [4, 5, 6, 7, 8, 9],
                "DS 7-12": [7, 8, 9, 10, 11, 12], "DS 10-15": [10, 11, 12, 13, 14, 15],
                "DS 13-18": [13, 14, 15, 16, 17, 18], "DS 16-21": [16, 17, 18, 19, 20, 21],
                "DS 19-24": [19, 20, 21, 22, 23, 24], "DS 22-27": [22, 23, 24, 25, 26, 27],
                "DS 25-30": [25, 26, 27, 28, 29, 30], "DS 28-33": [28, 29, 30, 31, 32, 33],
                "DS 31-36": [31, 32, 33, 34, 35, 36]
            }
            
            for ds_name, ds_nums in local_ds.items():
                overlap = set(ds_nums).intersection(set(coldest_dozen['nums']))
                if len(overlap) >= 3: 
                    hits = sum(1 for s in spins if int(s) in ds_nums)
                    last_pos = -1
                    for i, s in enumerate(reversed(spins)):
                        if int(s) in ds_nums:
                            last_pos = i
                            break
                    if last_pos == -1: last_pos = len(spins) + 100
                    ds_stats.append({"name": ds_name, "hits": hits, "recency": last_pos, "nums": ds_nums})
            
            ds_stats.sort(key=lambda x: (x['hits'], -x['recency']))
            coldest_ds = ds_stats[0] if ds_stats else {"name": "N/A", "nums": []}

            # 3. FIND COLDEST CORNER WITHIN THAT DOUBLE STREET
            corner_stats = []
            local_corners = {
                "Standard": [[1, 2, 4, 5], [8, 9, 11, 12], [13, 14, 16, 17], [20, 21, 23, 24], [25, 26, 28, 29]],
                "Shifted": [[2, 3, 5, 6], [7, 8, 10, 11], [14, 15, 17, 18], [19, 20, 22, 23], [26, 27, 29, 30]],
                "High-Low": [[4, 5, 7, 8], [10, 11, 13, 14], [16, 17, 19, 20], [22, 23, 25, 26], [32, 33, 35, 36]]
            }
            
            all_possible_corners = []
            for t_list in local_corners.values():
                all_possible_corners.extend(t_list)

            for c_nums in all_possible_corners:
                overlap = set(c_nums).intersection(set(coldest_ds['nums']))
                if len(overlap) >= 2: 
                    hits = sum(1 for s in spins if int(s) in c_nums)
                    last_pos = -1
                    for i, s in enumerate(reversed(spins)):
                        if int(s) in c_nums:
                            last_pos = i
                            break
                    if last_pos == -1: last_pos = len(spins) + 100
                    corner_stats.append({"nums": c_nums, "hits": hits, "recency": last_pos})
            
            corner_stats.sort(key=lambda x: (x['hits'], -x['recency']))
            coldest_corner_nums = corner_stats[0]['nums'] if corner_stats else []
            
            # --- NEW: Save to State for V9 Strategy Bridge ---
            state.trinity_dozen = coldest_dozen['name']
            state.trinity_ds = coldest_ds['name']
            state.trinity_corner_nums = coldest_corner_nums
            
            combined_path = list(set(coldest_dozen['nums']) | set(coldest_ds['nums']) | set(coldest_corner_nums))
            return coldest_dozen['name'], coldest_ds['name'], coldest_corner_nums, combined_path

        def get_grind_numbers(target):
            if isinstance(target, list):
                nums = set()
                for t in target:
                    if t in DOZENS: nums.update(DOZENS[t])
                    elif t in COLUMNS: nums.update(COLUMNS[t])
                return list(nums)
            if target in DOZENS: return DOZENS[target]
            elif target in COLUMNS: return COLUMNS[target]
            return []

        def get_pattern_alert(spin_list, type="dozen"):
            mapped_tuples = []
            for s in spin_list:
                cat = "0"
                if s == 0: cat = "0"
                elif type == "dozen":
                    if s in DOZENS["1st Dozen"]: cat = "D1"
                    elif s in DOZENS["2nd Dozen"]: cat = "D2"
                    elif s in DOZENS["3rd Dozen"]: cat = "D3"
                else:
                    if s in COLUMNS["1st Column"]: cat = "C1"
                    elif s in COLUMNS["2nd Column"]: cat = "C2"
                    elif s in COLUMNS["3rd Column"]: cat = "C3"
                mapped_tuples.append((cat, s))
            
            categories = [t[0] for t in mapped_tuples]
            if len(categories) < pat_x + 1: return None 
            target_pattern = categories[-pat_x:]
            
            search_limit = len(categories) - pat_x - 1 
            match_idx = -1
            
            for i in range(search_limit, -1, -1):
                if categories[i : i+pat_x] == target_pattern:
                    match_idx = i
                    break
            if match_idx != -1:
                return target_pattern, mapped_tuples[match_idx : match_idx+pat_x], mapped_tuples[match_idx+pat_x : match_idx+pat_x+pat_y]
            return None

        def generate_action_card(title, target, current_miss, wait_threshold, sequence, cost_per_unit, tooltip_nums=None, is_5ds=False, spots_override=None):
            step_index = current_miss - wait_threshold
            if step_index < 0: step_index = 0
            if step_index >= len(sequence): step_index = len(sequence) - 1
            unit_mult = sequence[step_index] 
            if "17-NUMBER" in title or "19" in title:
                spots = spots_override if spots_override else 17
                spot_name = "Num"
                p_unit = 0.01; d_unit = 0.10; D_unit = 1.00
                p_total = unit_mult * p_unit * spots; d_total = unit_mult * d_unit * spots; D_total = unit_mult * D_unit * spots
                p_per_spot = unit_mult * p_unit; d_per_spot = unit_mult * d_unit; D_per_spot = unit_mult * D_unit
            else:
                if spots_override:
                    spots = spots_override
                    spot_name = "Line" if is_5ds else "Spot"
                else:
                    spots = 1; spot_name = "Spot"
                    if is_5ds: spots = 5; spot_name = "Line"
                    elif "CORNER" in title: spots = 5; spot_name = "Crnr"
                    elif "STREAK" in title: spots = 2; spot_name = "Doz"
                    elif "SIDE" in title: spots = 25; spot_name = "Num"
                    elif "VOISINS" in title: spots = 17; spot_name = "Num"
                    elif "TIERS" in title: spots = 20; spot_name = "Num"
                p_unit = 0.01; p_per_spot = unit_mult * p_unit; p_total = p_per_spot * spots
                d_unit = 0.10; d_per_spot = unit_mult * d_unit; d_total = d_per_spot * spots
                D_unit = 1.00; D_per_spot = unit_mult * D_unit; D_total = D_per_spot * spots
                if "VOISINS" in title or "TIERS" in title or "SIDE" in title:
                      p_total = unit_mult * p_unit * spots; p_per_spot = unit_mult * p_unit
                      d_total = unit_mult * d_unit * spots; d_per_spot = unit_mult * d_unit
                      D_total = unit_mult * D_unit * spots; D_per_spot = unit_mult * D_unit
            mantras = ["Protect the Bankroll.", "Don't Chase Ghosts.", "Patience Pays.", "Sniper Mode On.", "Respect the Stop Loss.", "Stay Cool 🧊", "Trust the Math.", "Lock Profit Early."]
            import random
            daily_mantra = random.choice(mantras)
            header_bg = get_header_color(title)
            header_text = get_text_color_for_header(title)
            tooltip_html = ""
            if tooltip_nums:
                sorted_nums = sorted(list(tooltip_nums))
                nums_str = ", ".join(map(str, sorted_nums))
                tooltip_html = f'title="Cover: {nums_str}"'
            step_badge = f"STEP {step_index + 1}/{len(sequence)}"
            if "GRIND" in title: step_badge = f"STEP {current_miss + 1}/{len(sequence)}"
            seq_html = format_sequence_html(sequence, current_miss, wait_threshold)
            extra_html = f'<div style="margin-top: 8px; padding: 4px; background: #f5f5f5 !important; border: 1px solid #e0e0e0; border-radius: 4px; font-size: 9px; color: #555 !important; word-wrap: break-word; line-height: 1.4;"><div style="font-weight:bold; margin-bottom:2px; font-size:8px; text-transform:uppercase; color:#888 !important;">Progression Path:</div>{seq_html}</div>'
            html = f'<div class="hud-card" {tooltip_html} style="border: 2px solid {header_bg}; border-top: 5px solid {header_bg}; background: white !important;"><div class="hud-header" style="background-color: {header_bg} !important; color: {header_text} !important;"><span class="hud-title" style="color: {header_text} !important;">{title}</span><span class="hud-step-badge">{step_badge}</span></div><div class="hud-body"><div style="font-size: 13px; color: #666 !important; margin-bottom: 2px; text-transform: uppercase; font-weight: bold;">Target:</div><div style="font-weight: 800; font-size: 14px; color: #222 !important; margin-bottom: 8px; border-bottom: 1px solid #eee; padding-bottom: 5px; min-height: 20px;">{target}</div><table style="width:100%; border-collapse: collapse; font-size: 10px; text-align: center; color: #333 !important;"><tr style="background: #f0f0f0 !important; color: #555 !important;"><th style="padding: 2px; border: 1px solid #ddd; color: #555 !important;">Unit</th><th style="padding: 2px; border: 1px solid #ddd; color: #555 !important;">Per {spot_name}</th><th style="padding: 2px; border: 1px solid #ddd; color: #555 !important;">Total Bet</th></tr><tr style="background: #fff !important;"><td style="padding: 3px; border: 1px solid #eee; font-weight:bold; color:#00897b !important;">1¢</td><td style="padding: 3px; border: 1px solid #eee; color: #333 !important;">${p_per_spot:.2f}</td><td style="padding: 3px; border: 1px solid #eee; font-weight:900; color: #333 !important;">${p_total:.2f}</td></tr><tr style="background: #f9f9f9 !important;"><td style="padding: 3px; border: 1px solid #eee; font-weight:bold; color:#f57c00 !important;">10¢</td><td style="padding: 3px; border: 1px solid #eee; color: #333 !important;">${d_per_spot:.2f}</td><td style="padding: 3px; border: 1px solid #eee; font-weight:900; color: #333 !important;">${d_total:.2f}</td></tr><tr style="background: #fff !important;"><td style="padding: 3px; border: 1px solid #eee; font-weight:bold; color:#d81b60 !important;">$1</td><td style="padding: 3px; border: 1px solid #eee; color: #333 !important;">${D_per_spot:.2f}</td><td style="padding: 3px; border: 1px solid #eee; font-weight:900; color: #333 !important;">${D_total:.2f}</td></tr></table>{extra_html}</div><div class="hud-footer" style="padding-top: 5px;"><i style="color:#999 !important; font-size: 9px;">"{daily_mantra}"</i></div></div>'
            return html

        def get_label_style(target_name, highlight_targets_set, grind_targets_set, sector_ranks_dict):
            base = f"{inactive_style} opacity: 0.7;" 
            is_active = target_name in highlight_targets_set
            is_grind = target_name in grind_targets_set
            rank = sector_ranks_dict.get(target_name, 0)
            
            rank_css = ""
            if rank == 1: rank_css = rank1_style
            elif rank == 2: rank_css = rank2_style
            elif rank == 3: rank_css = rank3_style
            
            if is_active:
                if rank == 1: 
                    base = "background-color: #ffd700; color: black !important; font-weight: 900 !important; font-size: 12px !important; border: 3px solid #FFD700; box-shadow: 0 0 15px #FFD700; opacity: 1; animation: pulse-gold 0.8s infinite;"
                elif rank == 2:
                    base = "background-color: #00E5FF; color: black !important; font-weight: 900 !important; font-size: 12px !important; border: 3px solid #00FFFF; box-shadow: 0 0 12px #00FFFF; opacity: 1; animation: pulse-cyan 0.8s infinite;"
                elif rank == 3:
                    base = "background-color: #32CD32; color: white !important; font-weight: 900 !important; font-size: 12px !important; border: 3px solid #32CD32 !important; box-shadow: 0 0 10px #32CD32 !important; opacity: 1;"
                else: 
                    base = active_style + " " + rank_css
            elif is_grind:
                base = grind_style + " " + rank_css
            else:
                base = f"{inactive_style} {rank_css} opacity: 0.6;"
            return base

        def render_row_cells(num_list, highlight_targets_set, grind_targets_set, hot_subset_set, colors_dict, pinned_raw="[]", sniper_targets_set=None):
            cells = ""
            top_picks = state.current_top_picks
            if sniper_targets_set is None:
                sniper_targets_set = set()
            
            for n in num_list:
                c = colors_dict.get(str(n), "black")
                is_active = False; is_grind = False; is_hot = n in hot_subset_set; is_sniper = False
                
                is_pinned = n in pinned_set
                
                pinned_icon = ""
                if is_pinned:
                    pinned_icon = f'<span class="pinned-star-glow" style="position:absolute; top:0px; left:1px; font-size:15px; z-index:99999 !important; color:#E0B0FF !important; text-shadow: 0 0 8px #BF00FF, 0 0 3px #000; pointer-events:none; display:block !important;">★</span>'

                rank = ramp_ranks.get(n, 0)
                rank_badge = ""
                if rank > 0:
                    is_active_ramp = rank <= active_ramp_spots
                    badge_bg = "#FFD700" if is_active_ramp else "#00BFFF" 
                    badge_txt = "black" if is_active_ramp else "white"
                    border_style = "border:2px solid #FFD700;" if is_active_ramp else "border:1px solid white;"
                    rank_badge = f'<span style="position:absolute; top:-5px; left:-5px; width:14px; height:14px; background-color:{badge_bg}; color:{badge_txt}; font-size:9px; font-weight:bold; border-radius:50%; display:flex; align-items:center; justify-content:center; z-index:20; {border_style} box-shadow:0 1px 2px rgba(0,0,0,0.3);">{rank}</span>'

                target_icon = ""
                is_top_pick = n in top_picks
                top_pick_1 = top_picks[0] if len(top_picks) > 0 else None
                if n == top_pick_1:
                    target_icon = '<span style="position:absolute; bottom:-4px; right:-4px; font-size:18px; z-index:30; color:#FFFFFF; text-shadow: 0 0 5px #00FFFF, 0 0 10px #00FFFF; font-weight:900; line-height:1;">⌖</span>'
                elif n in top_picks[:5]: 
                    target_icon = '<span style="position:absolute; bottom:-2px; right:-2px; font-size:14px; z-index:25; filter: drop-shadow(0 0 2px black); color: #FFD700;">🎯</span>'
                elif n in top_picks[5:10]:
                    target_icon = '<span style="position:absolute; bottom:1px; right:1px; font-size:12px; z-index:20; color:#00FFFF; text-shadow: 0 0 2px black;">🔹</span>'

                flame_html = ""
                if is_hot:
                    flame_html = '<span style="position:absolute; top:-5px; right:-3px; font-size:9px; z-index:110; filter: drop-shadow(0 0 2px rgba(0,0,0,0.5));">🔥</span>'

                if n != 0:
                    if "1st Dozen" in highlight_targets_set and n in DOZENS["1st Dozen"]: is_active = True
                    elif "2nd Dozen" in highlight_targets_set and n in DOZENS["2nd Dozen"]: is_active = True
                    elif "3rd Dozen" in highlight_targets_set and n in DOZENS["3rd Dozen"]: is_active = True
                    if "1st Column" in highlight_targets_set and n in COLUMNS["1st Column"]: is_active = True
                    elif "2nd Column" in highlight_targets_set and n in COLUMNS["2nd Column"]: is_active = True
                    elif "3rd Column" in highlight_targets_set and n in COLUMNS["3rd Column"]: is_active = True
                    if "Red" in highlight_targets_set and n in EVEN_MONEY["Red"]: is_active = True
                    elif "Black" in highlight_targets_set and n in EVEN_MONEY["Black"]: is_active = True
                    elif "Even" in highlight_targets_set and n in EVEN_MONEY["Even"]: is_active = True
                    elif "Odd" in highlight_targets_set and n in EVEN_MONEY["Odd"]: is_active = True
                    elif "Low" in highlight_targets_set and n in EVEN_MONEY["Low"]: is_active = True
                    elif "High" in highlight_targets_set and n in EVEN_MONEY["High"]: is_active = True
                    if "Voisins" in highlight_targets_set and n in voisins_numbers: is_active = True
                    if "TiersOrph" in highlight_targets_set and n in tiers_orph_numbers: is_active = True
                    if "LeftSide" in highlight_targets_set and n in left_side_covered: is_active = True
                    if "RightSide" in highlight_targets_set and n in right_side_covered: is_active = True
                    if n in highlight_targets_set: is_active = True
                    if not is_active and n in sniper_targets_set: is_sniper = True

                    if not is_active and not is_sniper:
                         if "1st Dozen" in grind_targets_set and n in DOZENS["1st Dozen"]: is_grind = True
                         elif "2nd Dozen" in grind_targets_set and n in DOZENS["2nd Dozen"]: is_grind = True
                         elif "3rd Dozen" in grind_targets_set and n in DOZENS["3rd Dozen"]: is_grind = True
                         if "1st Column" in grind_targets_set and n in COLUMNS["1st Column"]: is_grind = True
                         elif "2nd Column" in grind_targets_set and n in COLUMNS["2nd Column"]: is_grind = True
                         elif "3rd Column" in grind_targets_set and n in COLUMNS["3rd Column"]: is_grind = True

                special_border = ""
                if is_pinned:
                    special_border = "border: 3px solid #BF00FF !important; box-shadow: 0 0 15px #BF00FF !important; z-index: 1000 !important;"
                elif n == top_pick_1:
                    special_border = "border: 3px solid #00FFFF !important; box-shadow: 0 0 15px #00FFFF !important; z-index: 90;"
                elif n in top_picks[:5]:
                    special_border = "border: 2px solid #FFFF00 !important; box-shadow: 0 0 10px #FFFF00 !important; z-index: 800 !important;"
                elif rank > 0:
                    special_border = "border: 2px solid #FFFFFF !important; box-shadow: 0 0 8px rgba(255,255,255,0.8) !important; z-index: 70;"
                elif is_hot:
                    special_border = "border: 2px solid #FF3333 !important; box-shadow: 0 0 10px #FF0000 !important; z-index: 60;"

                has_special_status = is_hot or (rank > 0) or is_top_pick or is_pinned
                in_spotlight = is_active or is_sniper or is_grind or has_special_status
                
                opacity = "1.0" if in_spotlight else "0.3"

                if is_active: base_style = active_style + (" border: 3px solid #ff3333; box-shadow: 0 0 10px #ff0000;" if is_hot else "")
                elif is_sniper: base_style = sniper_style + (" border: 3px solid #ff3333; box-shadow: 0 0 10px #ff0000;" if is_hot else "")
                elif is_grind: base_style = grind_style + (" border: 3px solid #ff3333;" if is_hot else "")
                else: base_style = f"background-color:{c}; color:white;" + (f" border: 3px solid #ff3333; box-shadow: inset 0 0 5px #ff0000;" if is_hot else "")
                
                base_style += f" opacity: {opacity}; position: relative; overflow: visible; {special_border}"
                cells += f'<div style="{base_style} height:25px; display:flex; align-items:center; justify-content:center; font-size:10px; border-radius:2px;">{n}{flame_html}{rank_badge}{target_icon}{pinned_icon}</div>'
            return cells

        # =========================================================
        # 5. STATIC DATA DEFINITIONS
        # =========================================================
        voisins_numbers = [0, 2, 3, 4, 7, 12, 15, 18, 19, 21, 22, 25, 26, 28, 29, 32, 35]
        tiers_orph_numbers = [1, 5, 6, 8, 9, 10, 11, 13, 14, 16, 17, 20, 23, 24, 27, 30, 31, 33, 34, 36]
        left_side_covered = [1, 3, 5, 7, 9, 12, 14, 16, 18, 20, 22, 24, 27, 26, 25, 28, 29, 30, 33, 32, 31, 34, 35, 36, 0]
        left_uncovered = [2, 4, 6, 8, 10, 11, 13, 15, 17, 19, 21, 23] 
        right_side_covered = [2, 4, 6, 8, 10, 11, 13, 15, 17, 19, 21, 23, 27, 26, 25, 28, 29, 30, 33, 32, 31, 34, 35, 36, 0]
        right_uncovered = [1, 3, 5, 7, 9, 12, 14, 16, 18, 20, 22, 24]
        double_streets = {
            "DS 1-6": [1, 2, 3, 4, 5, 6], "DS 4-9": [4, 5, 6, 7, 8, 9],
            "DS 7-12": [7, 8, 9, 10, 11, 12], "DS 10-15": [10, 11, 12, 13, 14, 15],
            "DS 13-18": [13, 14, 15, 16, 17, 18], "DS 16-21": [16, 17, 18, 19, 20, 21],
            "DS 19-24": [19, 20, 21, 22, 23, 24], "DS 22-27": [22, 23, 24, 25, 26, 27],
            "DS 25-30": [25, 26, 27, 28, 29, 30], "DS 28-33": [28, 29, 30, 31, 32, 33],
            "DS 31-36": [31, 32, 33, 34, 35, 36]
        }
        ghost_parents = {
            "DS 4-9": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            "DS 10-15": [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
            "DS 16-21": [13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24],
            "DS 22-27": [19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30],
            "DS 28-33": [25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36]
        }
        ds_ranges = {
            "DS 1-6": "1-6", "DS 4-9": "4-9", "DS 7-12": "7-12", "DS 10-15": "10-15",
            "DS 13-18": "13-18", "DS 16-21": "16-21", "DS 19-24": "19-24", "DS 22-27": "22-27",
            "DS 25-30": "25-30", "DS 28-33": "28-33", "DS 31-36": "31-36"
        }
        corner_templates = {
            "Standard": [[1, 2, 4, 5], [8, 9, 11, 12], [13, 14, 16, 17], [20, 21, 23, 24], [25, 26, 28, 29]],
            "Shifted": [[2, 3, 5, 6], [7, 8, 10, 11], [14, 15, 17, 18], [19, 20, 22, 23], [26, 27, 29, 30]],
            "High-Low": [[4, 5, 7, 8], [10, 11, 13, 14], [16, 17, 19, 20], [22, 23, 25, 26], [32, 33, 35, 36]]
        }
        seq_fib = [1, 1, 2, 3, 4, 6, 9, 14, 21, 31, 47, 70, 105, 158, 237]
        seq_even_money = [1, 2, 3, 5, 9, 16, 29, 54, 102, 191, 358, 671, 1302, 2524, 4894, 9491, 18404, 36839, 73740, 147606, 295463] 
        seq_manual_grind = [1, 1, 2, 3, 4, 6, 8, 11, 16, 22, 31, 44, 62, 88, 123, 174, 246] 
        seq_missing_dozen = [1, 1, 2, 3, 4, 5, 7, 9, 13, 18, 25, 36, 52, 75, 109, 156, 224, 323, 474, 697, 1024, 1505, 2212, 3251, 4777, 7020, 10536, 15812, 23731, 35615, 53451, 80219, 120393]
        seq_two_dozens = [1, 3, 6, 15, 39, 107, 295, 812, 2232, 6416, 18443, 53015, 152401, 457140, 1371238] 
        seq_17_numbers = [1, 2, 3, 5, 8, 13, 22, 39, 69, 124, 221, 393, 724, 1331, 2448, 4503, 8283, 15236, 28877, 54730, 103729, 196599]
        seq_voisins = seq_17_numbers
        seq_20_numbers = [1, 2, 4, 7, 14, 27, 57, 119, 250, 523, 1095, 2376, 5159, 11200, 24315, 52789, 118727, 267030, 600577]
        seq_tiers = seq_20_numbers
        seq_25_numbers = [1, 3, 7, 20, 59, 176, 552, 1727, 5404, 17679]
        seq_sides = seq_25_numbers
        seq_5ds = [1, 5, 22, 115, 605, 3374, 18827, 110784] 
        seq_d17 = seq_17_numbers
        seq_corners = seq_20_numbers

        cost_dozen = 1; cost_even = 1; cost_streak = 2; cost_voisins = 17 
        cost_tiers = 20; cost_sides = 25; cost_5ds = 5; cost_d17 = 1; cost_corner = 5
        cost_grind = 0.01 

        def get_cutoff_display(sequence, spots):
            """Calculates affordable steps for $100 bankroll at 0.01 base."""
            cumulative = 0
            cutoff_idx = -1
            for i, units in enumerate(sequence):
                cost = units * 0.01 * spots
                if (cumulative + cost) <= 100:
                    cumulative += cost
                else:
                    cutoff_idx = i
                    break
            html_parts = []
            for i, val in enumerate(sequence):
                if i == cutoff_idx:
                    html_parts.append(f'<span style="color:#d32f2f; font-weight:900; border:1px solid #d32f2f; padding:0 2px; background:#ffebee;">✂️{val}</span>')
                else:
                    html_parts.append(str(val))
            return f"[{', '.join(html_parts)}]"

        sequences_info_html = f"""
        <div style="margin-top: 20px; background: #ffffff; border: 4px solid #FFD700; border-radius: 12px; padding: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.4);">
            <details open>
                <summary style="color: #000000; font-weight: 900; font-size: 20px; cursor: pointer; text-transform: uppercase; letter-spacing: 1.5px; list-style: none; display: flex; align-items: center; gap: 10px; border-bottom: 2px solid #eee; padding-bottom: 10px;">
                    <span style="font-size: 24px;">📜</span> ACTIVE PROGRESSION DATA & BANKROLL HINTS (1¢ UNIT)
                </summary>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; margin-top: 20px; font-size: 15px; color: #000000; font-family: 'Consolas', 'Courier New', monospace; font-weight: 800;">
                    <div style="background:#f1f5f9; padding:12px; border-radius:8px; border-left:8px solid #1976D2;"><strong style="color:#1976D2; font-size:16px;">Missing Dozen/Col (12 #s):</strong><br>{get_cutoff_display(seq_missing_dozen, 12)}</div>
                    <div style="background:#f1f5f9; padding:12px; border-radius:8px; border-left:6px solid #388E3C;"><strong style="color:#388E3C; font-size:16px;">Even Money Drought (18 #s):</strong><br>{get_cutoff_display(seq_even_money, 18)}</div>
                    <div style="background:#f1f5f9; padding:12px; border-radius:8px; border-left:6px solid #E64A19;"><strong style="color:#E64A19; font-size:16px;">Two Dozens/Columns (24 #s):</strong><br>{get_cutoff_display(seq_two_dozens, 24)}</div>
                    <div style="background:#f1f5f9; padding:12px; border-radius:8px; border-left:6px solid #0097A7;"><strong style="color:#0097A7; font-size:16px;">Voisins (17 #s):</strong><br>{get_cutoff_display(seq_voisins, 17)}</div>
                    <div style="background:#f1f5f9; padding:12px; border-radius:8px; border-left:6px solid #0288D1;"><strong style="color:#0288D1; font-size:16px;">Tiers+Orph (20 #s):</strong><br>{get_cutoff_display(seq_tiers, 20)}</div>
                    <div style="background:#fffcf0; padding:12px; border-radius:8px; border-left:6px solid #fbc02d;"><strong style="color:#856404; font-size:16px;">Sides Left/Right (25 #s):</strong><br>{get_cutoff_display(seq_sides, 25)}</div>
                    <div style="background:#f1f5f9; padding:12px; border-radius:8px; border-left:6px solid #C2185B;"><strong style="color:#C2185B; font-size:16px;">5 Double Streets (30 #s):</strong><br>{get_cutoff_display(seq_5ds, 30)}</div>
                    <div style="background:#f1f5f9; padding:12px; border-radius:8px; border-left:6px solid #D32F2F;"><strong style="color:#D32F2F; font-size:16px;">Dynamic 17 (17 #s):</strong><br>{get_cutoff_display(seq_d17, 17)}</div>
                    <div style="background:#f1f5f9; padding:12px; border-radius:8px; border-left:6px solid #FF9800;"><strong style="color:#FF9800; font-size:16px;">Corners (20 #s):</strong><br>{get_cutoff_display(seq_corners, 20)}</div>
                    <div style="background:#f1f5f9; padding:12px; border-radius:8px; border-left:6px solid #2E7D32;"><strong style="color:#2E7D32; font-size:16px;">Manual Grind:</strong><br>{get_cutoff_display(seq_manual_grind, 12)}</div>
                </div>
                <p style="margin-top:15px; font-size:13px; color:#d32f2f; font-weight:900;">⚠️ BANKROLL ADVISORY: ✂️ marks the bet that breaks a $100 budget.</p>
            </details>
        </div>
        """

        miss_wait = parse_arg(miss_threshold, 11)
        even_wait = parse_arg(even_threshold, 10)
        streak_wait = parse_arg(streak_threshold, 9)
        pat_x = parse_arg(pattern_x, 8)
        voisins_wait = parse_arg(voisins_threshold, 8)
        tiers_wait = parse_arg(tiers_threshold, 9)
        left_wait = parse_arg(left_threshold, 7)
        right_wait = parse_arg(right_threshold, 7)
        ds_wait = parse_arg(ds_threshold, 4)
        d17_wait = parse_arg(d17_threshold, 6)
        corner_wait = parse_arg(corner_threshold, 3)
        pat_y = 12 - pat_x

        # --- AUTO-NUDGE: apply overrides when mode is AUTO ---
        # Overrides are bounded and rate-limited by _auto_nudge_apply().
        # This block is defensive: any key error / type error is silently
        # ignored so the slider defaults are used as fallback.
        if _nudge_state.get("mode") == "AUTO":
            try:
                _ov = _nudge_state.get("overrides", {})
                if 0 in _ov: miss_wait = _safe_slider_val(_ov[0], 0)
                if 1 in _ov: even_wait = _safe_slider_val(_ov[1], 1)
                if 2 in _ov: streak_wait = _safe_slider_val(_ov[2], 2)
                if 4 in _ov: voisins_wait = _safe_slider_val(_ov[4], 4)
                if 5 in _ov: tiers_wait = _safe_slider_val(_ov[5], 5)
                if 6 in _ov: left_wait = _safe_slider_val(_ov[6], 6)
                if 7 in _ov: right_wait = _safe_slider_val(_ov[7], 7)
                if 8 in _ov: ds_wait = _safe_slider_val(_ov[8], 8)
                if 9 in _ov: d17_wait = _safe_slider_val(_ov[9], 9)
                if 10 in _ov: corner_wait = _safe_slider_val(_ov[10], 10)
            except Exception:
                pass  # fail closed — use original slider values

        status_flags = {
            "missing": False, "even": False, "streak": False, "pattern": False,
            "voisins": False, "tiers": False, "left": False, "right": False, "5ds": False, "d17": False, "corner": False, "overheated": False
        }
        
        hot_subset = set()
        hot_list = []
        sorted_scores = sorted(state.scores.items(), key=lambda x: x[1], reverse=True)
        hot_subset = {num for num, score in sorted_scores[:5] if score > 0}
        hot_candidates = [(num, score) for num, score in sorted_scores if score > 0]
        hot_list = sorted(hot_candidates[:5], key=lambda x: x[0])
        
        sector_ranks = {}
        if spins:
            d_counts = {d: count_frequency(set(nums), spins) for d, nums in DOZENS.items()}
            sorted_d = sorted(d_counts.items(), key=lambda x: x[1], reverse=True)
            for i, (name, _) in enumerate(sorted_d): sector_ranks[name] = i + 1
            c_counts = {c: count_frequency(set(nums), spins) for c, nums in COLUMNS.items()}
            sorted_c = sorted(c_counts.items(), key=lambda x: x[1], reverse=True)
            for i, (name, _) in enumerate(sorted_c): sector_ranks[name] = i + 1
            em_counts = {}
            for name, nums in EVEN_MONEY.items(): em_counts[name] = count_frequency(set(nums), spins)
            sorted_em = sorted(em_counts.items(), key=lambda x: x[1], reverse=True)
            for i, (name, _) in enumerate(sorted_em): 
                if i < 3: sector_ranks[name] = i + 1

        temp_list = []
        is_locked = False
        d17_miss_count = 0
        for s in spins:
            if not is_locked:
                if s not in temp_list:
                    temp_list.append(s)
                    if len(temp_list) == 17: is_locked = True
            else:
                if s in temp_list: d17_miss_count = 0 
                else: d17_miss_count += 1 
        state.d17_list = temp_list
        state.d17_locked = is_locked

        # =========================================================
        # 5. STRATEGY EXECUTION
        # =========================================================
        
        if ramp_active:
            if current_spin_count > state.ramp_last_spin_count:
                sim_counts = {n: 0 for n in range(37)}
                sim_last_pos = {n: -1 for n in range(37)}
                history_spins = spins[:state.ramp_last_spin_count]
                for idx, s in enumerate(history_spins):
                    sim_counts[s] += 1
                    sim_last_pos[s] = idx
                new_spins_list = spins[state.ramp_last_spin_count:]
                current_total_idx = state.ramp_last_spin_count
                for s in new_spins_list:
                    sim_sorted = sorted(range(37), key=lambda x: (-sim_counts[x], -sim_last_pos[x]))
                    step_idx = min(state.ramp_step_index, len(seq_ramp_config) - 1)
                    spots_needed, _ = seq_ramp_config[step_idx]
                    potential_targets = [n for n in sim_sorted if sim_counts[n] > 0]
                    if len(potential_targets) >= 4:
                        targets = potential_targets[:spots_needed]
                        if s in targets: state.ramp_step_index = 0 
                        else:
                            state.ramp_step_index += 1 
                            if state.ramp_step_index >= len(seq_ramp_config): state.ramp_step_index = 0
                    sim_counts[s] += 1
                    sim_last_pos[s] = current_total_idx
                    current_total_idx += 1
                state.ramp_last_spin_count = current_spin_count
            elif current_spin_count < state.ramp_last_spin_count:
                state.ramp_last_spin_count = current_spin_count
                state.ramp_step_index = 0

            curr_idx = min(state.ramp_step_index, len(seq_ramp_config) - 1)
            r_spots, r_units = seq_ramp_config[curr_idx]
            r_nums_to_bet = []
            for r in range(1, r_spots + 1):
                n = next((k for k, v in ramp_ranks.items() if v == r), None)
                if n is not None: r_nums_to_bet.append(n)

            unique_hits_count = len([n for n, c in ramp_counts.items() if c > 0])
            if unique_hits_count < 4:
                r_nums_str = f"CALIBRATING ({unique_hits_count}/4)..."
                r_nums_to_bet = []
            else:
                r_nums_str = ", ".join(map(str, sorted(r_nums_to_bet))) if r_nums_to_bet else "Waiting..."
            
            active_actions.insert(0, generate_action_card("VARIABLE 4-12 RAMP", f"Bet {r_spots} #'s: {r_nums_str}", state.ramp_step_index, 0, seq_ramp_units, 0.01, set(r_nums_to_bet), spots_override=r_spots))
            
            if r_nums_to_bet:
                highlight_targets.update(r_nums_to_bet)
                active_target_groups.append(("4-12 RAMP", sorted(r_nums_to_bet), "#FFD700"))
        else:
             state.ramp_last_spin_count = current_spin_count

        if x19_active:
            sim_bucket = []
            sim_active = False
            sim_step = 0
            
            for i, s in enumerate(spins):
                if not sim_active:
                    if s not in sim_bucket:
                        sim_bucket.append(s)
                        if len(sim_bucket) == x19_start:
                            sim_active = True
                            sim_step = 0
                else:
                    if s in sim_bucket:
                        current_history = spins[:i+1]
                        sim_bucket = get_last_unique_numbers(current_history, x19_start)
                        
                        if len(sim_bucket) == x19_start:
                             sim_active = True 
                             sim_step = 0 
                        else:
                             sim_active = False 
                    else:
                        sim_bucket.append(s)
                        sim_step += 1
            
            current_count = len(sim_bucket)
            if sim_bucket: highlight_targets.update(sim_bucket)

            if sim_active:
                prog_data = X19_PROGRESSIONS.get(x19_start, [])
                display_sequence = [p[1] for p in prog_data]
                
                active_actions.append(generate_action_card(
                    f"{x19_start}-19 STRATEGY (ACTIVE)", 
                    f"Bet {current_count} #'s | Step {sim_step + 1}", 
                    sim_step, 
                    0, 
                    display_sequence, 
                    1, 
                    set(sim_bucket),
                    spots_override=current_count
                ))
                active_target_groups.append((f"{x19_start}-19 STEP {sim_step + 1}", sorted(sim_bucket), "#FFD700"))
            else:
                active_actions.append(f"""
                <div class="hud-card" style="border: 2px solid #34495e; border-top: 5px solid #34495e; opacity: 0.8; background: white !important;">
                    <div class="hud-header" style="background-color: #34495e !important; color: white !important;">
                        <span class="hud-title" style="color: white !important;">{x19_start}-19 SCANNING...</span>
                    </div>
                    <div class="hud-body">
                        <div style="font-size: 13px; color: #666 !important; margin-bottom: 2px; text-transform: uppercase; font-weight: bold;">Progress:</div>
                        <div style="font-weight: 800; font-size: 14px; color: #222 !important; margin-bottom: 8px;">
                            {current_count} / {x19_start} Unique #'s
                        </div>
                        <div style="width: 100%; height: 6px; background-color: #eee; border-radius: 3px; overflow: hidden;">
                             <div style="width: {(current_count / x19_start) * 100}%; height: 100%; background-color: #3498db;"></div>
                        </div>
                        <div style="font-size: 10px; color: #888; margin-top: 5px;">Collecting data...</div>
                    </div>
                </div>
                """)

        if grind_active:
            if current_spin_count > state.grind_last_spin_count:
                new_spins_list = spins[state.grind_last_spin_count:]
                active_target = grind_target
                if grind_target == "Auto (Hottest D/C)":
                    active_target = get_hottest_sector(spins) 
                for s in new_spins_list:
                    target_nums = get_grind_numbers(active_target) 
                    if s in target_nums: state.grind_step_index = 0
                    else:
                        state.grind_step_index += 1
                        if state.grind_step_index >= len(seq_manual_grind):
                            state.grind_step_index = len(seq_manual_grind) - 1
                state.grind_last_spin_count = current_spin_count
            elif current_spin_count < state.grind_last_spin_count:
                state.grind_last_spin_count = current_spin_count
        else:
            state.grind_last_spin_count = current_spin_count

        # =========================================================
        # 6. EXISTING TRIGGER LOGIC (Standard Alerts)
        # =========================================================
        miss_counts = {}
        for dname, nums in DOZENS.items(): miss_counts[dname] = count_misses(set(nums), spins, zero_is_miss=True)
        col_miss_counts = {}
        for cname, nums in COLUMNS.items(): col_miss_counts[cname] = count_misses(set(nums), spins, zero_is_miss=True)
        all_section_misses = {**miss_counts, **col_miss_counts}
        worst_section_miss_val = max(all_section_misses.values()) if all_section_misses else 0
        worst_section_name = max(all_section_misses, key=all_section_misses.get) if all_section_misses else "N/A"

        even_miss_counts = {}
        for ename, nums in EVEN_MONEY.items(): even_miss_counts[ename] = count_misses(set(nums), spins, zero_is_miss=True)
        worst_even_miss_val = max(even_miss_counts.values()) if even_miss_counts else 0
        worst_even_name = max(even_miss_counts, key=even_miss_counts.get) if even_miss_counts else "N/A"

        streak_counts = {}
        for dname, nums in DOZENS.items(): streak_counts[dname] = count_hits(set(nums), spins)
        for cname, nums in COLUMNS.items(): streak_counts[cname] = count_hits(set(nums), spins)
        best_streak_val = max(streak_counts.values()) if streak_counts else 0
        best_streak_name = max(streak_counts, key=streak_counts.get) if streak_counts else "N/A"
        streak_targets = {
            "1st Dozen": "2nd & 3rd Dozen", "2nd Dozen": "1st & 3rd Dozen", "3rd Dozen": "1st & 2nd Dozen",
            "1st Column": "2nd & 3rd Column", "2nd Column": "1st & 3rd Column", "3rd Column": "1st & 2nd Column"
        }
        display_streak_target = streak_targets.get(best_streak_name, best_streak_name)

        curr_voisins_miss = count_misses(set(voisins_numbers), spins, zero_is_miss=False)
        curr_tiers_miss = count_misses(set(tiers_orph_numbers), spins, zero_is_miss=True)
        curr_left_miss = count_hits(set(left_uncovered), spins) 
        curr_right_miss = count_hits(set(right_uncovered), spins)
        
        ds_streaks = {}
        for ds_name, nums in double_streets.items(): ds_streaks[ds_name] = count_hits_with_zero(set(nums), spins)
        best_ds_streak = max(ds_streaks.values()) if ds_streaks else 0
        best_ds_name = max(ds_streaks, key=ds_streaks.get) if ds_streaks else "N/A"
        
        best_corner_template = None; max_corner_miss = 0
        for template_name, corners_list in corner_templates.items():
            template_numbers = set()
            for c in corners_list: template_numbers.update(c)
            misses = count_misses(template_numbers, spins, zero_is_miss=True)
            if misses > max_corner_miss: max_corner_miss = misses; best_corner_template = (template_name, template_numbers)

        if worst_section_miss_val == miss_wait - 1: on_deck_triggers.append(f"Missing {worst_section_name}")
        if worst_even_miss_val == even_wait - 1: on_deck_triggers.append(f"Even Drought ({worst_even_name})")
        if best_streak_val == streak_wait - 1: on_deck_triggers.append(f"Streak ({best_streak_name})")
        if curr_voisins_miss == voisins_wait - 1: on_deck_triggers.append("Voisins")
        if curr_tiers_miss == tiers_wait - 1: on_deck_triggers.append("Tiers")
        if curr_left_miss == left_wait - 1: on_deck_triggers.append("Left Side")
        if curr_right_miss == right_wait - 1: on_deck_triggers.append("Right Side")
        if best_ds_streak == ds_wait - 1: on_deck_triggers.append(f"5DS ({best_ds_name})")
        if state.d17_locked and d17_miss_count == d17_wait - 1: on_deck_triggers.append("D17")
        if max_corner_miss == corner_wait - 1: on_deck_triggers.append("Corner Shuffle")

        # --- THE STANDALONE SNIPER TRACKER (NO-TRIGGER / HOTTEST FOLLOW) ---
        # S65+C19: 65 street phases (11:1) + 19 corner phases (8:1) = 84 phases
        sniper_progression = [
            # Phases 1-65: Street bet on HOTTEST STREET — Payout 11:1
            0.01, 0.01, 0.01, 0.01, 0.01, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02, 0.03, 0.03, 0.03, 0.03, 0.04, 0.04, 0.04, 0.05, 0.05,
            0.06, 0.06, 0.07, 0.07, 0.08, 0.09, 0.09, 0.10, 0.11, 0.12, 0.13, 0.14, 0.16, 0.17, 0.18, 0.20, 0.22, 0.24, 0.26, 0.28,
            0.31, 0.34, 0.37, 0.40, 0.44, 0.48, 0.52, 0.56, 0.61, 0.67, 0.73, 0.80, 0.87, 0.94, 1.03, 1.12, 1.22, 1.33, 1.45, 1.58,
            1.72, 1.88, 2.04, 2.23, 2.43,
            # Phases 66-84: Corner bet on HOTTEST CORNER — Payout 8:1
            3.68, 4.16, 4.71, 5.34, 6.04, 6.84, 7.75, 8.77, 9.93, 11.24, 12.73, 14.41, 16.31, 18.47, 20.91, 23.68, 26.81, 30.35, 34.36
        ]

        s_step = 1
        s_wins = 0
        s_busts = 0
        sniper_running_street = {name: 0 for name in STREETS}
        sniper_running_corner = {name: 0 for name in CORNERS}
        current_hot_street = list(STREETS.keys())[0]
        current_hot_corner = list(CORNERS.keys())[0]

        for s in spins:
            # Determine hottest BEFORE this spin (bet is placed before ball drops)
            if any(v > 0 for v in sniper_running_street.values()):
                current_hot_street = max(sniper_running_street, key=sniper_running_street.get)
            if any(v > 0 for v in sniper_running_corner.values()):
                current_hot_corner = max(sniper_running_corner, key=sniper_running_corner.get)

            # Evaluate win/loss
            if s_step <= 65:
                targets = set(STREETS[current_hot_street])
            else:
                targets = set(CORNERS[current_hot_corner])

            if s in targets:
                s_wins += 1
                s_step = 1
            else:
                s_step += 1
                if s_step > len(sniper_progression):
                    s_busts += 1
                    s_step = 1

            # Update running scores AFTER evaluation
            if s in BETTING_MAPPINGS:
                for street_name in BETTING_MAPPINGS[s]["streets"]:
                    sniper_running_street[street_name] += 1
                for corner_name in BETTING_MAPPINGS[s]["corners"]:
                    sniper_running_corner[corner_name] += 1

        # Final hottest for display (after all spins processed)
        if any(v > 0 for v in sniper_running_street.values()):
            current_hot_street = max(sniper_running_street, key=sniper_running_street.get)
        if any(v > 0 for v in sniper_running_corner.values()):
            current_hot_corner = max(sniper_running_corner, key=sniper_running_corner.get)
        hot_street_nums = sorted(STREETS[current_hot_street])
        hot_corner_nums = sorted(CORNERS[current_hot_corner])
        hot_street_hits = sniper_running_street[current_hot_street]
        hot_corner_hits = sniper_running_corner[current_hot_corner]
        # Extract short name for display
        hot_street_short = current_hot_street.split(" – ")[0] if " – " in current_hot_street else current_hot_street
        hot_corner_short = current_hot_corner.split(" – ")[0] if " – " in current_hot_corner else current_hot_corner

        status_flags["sniper"] = s_step > 1  # Active when in progression

        if s_step <= 65:
            stage_name = "🛡️ STREET PHASE"
            target_disp = f"{', '.join(str(n) for n in hot_street_nums)} ({hot_street_short})"
            prog_color = _SNIPER_HIGHLIGHT_COLOR
            if "Sniper Strike" in hud_filters:
                sniper_highlight_targets.update(set(hot_street_nums))
            active_target_groups.append(("SNIPER STREET", hot_street_nums, prog_color))
        else:
            stage_name = "⚔️ CORNER RESCUE"
            target_disp = f"{', '.join(str(n) for n in hot_corner_nums)} ({hot_corner_short})"
            prog_color = _SNIPER_HIGHLIGHT_COLOR
            if "Sniper Strike" in hud_filters:
                sniper_highlight_targets.update(set(hot_corner_nums))
            active_target_groups.append(("SNIPER CORNER", hot_corner_nums, prog_color))

        bet_amt = sniper_progression[min(s_step, len(sniper_progression)) - 1]
        pct = min(100, int((s_step / 84) * 100))

        # Top 3 streets and corners for recommendation display
        sorted_streets = sorted(sniper_running_street.items(), key=lambda x: x[1], reverse=True)[:3]
        sorted_corners = sorted(sniper_running_corner.items(), key=lambda x: x[1], reverse=True)[:3]

        street_recs_html = ""
        for i, (sname, shits) in enumerate(sorted_streets):
            s_short = sname.split(" – ")[0] if " – " in sname else sname
            s_nums = sorted(STREETS[sname])
            is_top = (i == 0)
            row_bg = "rgba(0, 191, 255, 0.15)" if is_top else "transparent"
            row_border = "1px solid #00BFFF" if is_top else "1px solid #334155"
            street_recs_html += f'<div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 6px; background: {row_bg}; border: {row_border}; border-radius: 4px; margin-bottom: 3px;"><span style="color: {"#00BFFF" if is_top else "#94a3b8"} !important; font-weight: {"900" if is_top else "normal"}; font-size: 12px;">{"→ " if is_top else ""}{s_short}</span><span style="color: #cbd5e1 !important; font-size: 11px;">[{", ".join(str(n) for n in s_nums)}]</span><span style="color: #4ade80 !important; font-weight: bold; font-size: 12px;">{shits}x</span></div>'

        corner_recs_html = ""
        for i, (cname, chits) in enumerate(sorted_corners):
            c_short = cname.split(" – ")[0] if " – " in cname else cname
            c_nums_display = cname.split(" – ")[1] if " – " in cname else str(sorted(CORNERS[cname]))
            is_top = (i == 0)
            row_bg = "rgba(255, 215, 0, 0.15)" if is_top else "transparent"
            row_border = "1px solid #FFD700" if is_top else "1px solid #334155"
            corner_recs_html += f'<div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 6px; background: {row_bg}; border: {row_border}; border-radius: 4px; margin-bottom: 3px;"><span style="color: {"#FFD700" if is_top else "#94a3b8"} !important; font-weight: {"900" if is_top else "normal"}; font-size: 12px;">{"→ " if is_top else ""}{c_short}</span><span style="color: #cbd5e1 !important; font-size: 11px;">[{c_nums_display}]</span><span style="color: #4ade80 !important; font-weight: bold; font-size: 12px;">{chits}x</span></div>'

        sniper_status_html = f"""
        <div style="background: #1a1a2e !important; background-color: #1a1a2e !important; padding: 10px; border-radius: 6px; margin-top: 8px; border: 1px solid {prog_color}; box-shadow: inset 0 0 10px rgba(0,0,0,0.5);">
            <div style="font-size: 11px; color: {prog_color} !important; font-weight: bold; text-transform: uppercase; margin-bottom: 4px;">{stage_name}</div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                <span style="color: white !important; font-weight: 900; font-size: 15px;">Phase {s_step}</span>
                <span style="color: #4ade80 !important; font-weight: bold; font-size: 16px;">${bet_amt:.2f}</span>
            </div>
            <div style="font-size: 12px; color: #cbd5e1 !important; margin-bottom: 6px;">Target: <b style="color: #cbd5e1 !important;">{target_disp}</b></div>
            <div style="width: 100%; height: 6px; background: #334155 !important; border-radius: 3px; overflow: hidden;">
                <div style="width: {pct}%; height: 100%; background: {prog_color} !important;"></div>
            </div>
            <div style="font-size: 16px; color: #00FFFF !important; font-weight: 900; text-align: center; margin-top: 8px; padding: 4px; background: rgba(0, 255, 255, 0.1) !important; border-radius: 4px; border: 1px solid #00FFFF;">
                PROGRESSION: {s_step} / 84
            </div>
            <div style="display: flex; justify-content: space-around; margin-top: 8px; font-size: 11px;">
                <span style="color: #4ade80 !important;">Wins: {s_wins}</span>
                <span style="color: #f87171 !important;">Busts: {s_busts}</span>
            </div>
            <div style="margin-top: 10px; border-top: 1px solid #334155; padding-top: 8px;">
                <div style="font-size: 11px; color: #00BFFF !important; font-weight: bold; margin-bottom: 4px;">BEST STREETS</div>
                {street_recs_html}
                <div style="font-size: 11px; color: #FFD700 !important; font-weight: bold; margin-top: 8px; margin-bottom: 4px;">BEST CORNERS</div>
                {corner_recs_html}
            </div>
        </div>
        """

        active_actions.insert(0, f"""
        <div class="hud-card" style="border: 3px solid #ff00ff; border-top: 6px solid #ff00ff; background: #ffe6ff !important; animation: pulse 1.5s infinite; transform: scale(1.05); margin-bottom: 10px; box-shadow: 0 0 15px #ff00ff; min-width: 280px !important;">
            <div class="hud-header" style="background-color: #ff00ff !important; color: white !important;">
                <span class="hud-title" style="color: white !important;">🎯 SNIPER STRIKE</span>
                <span class="hud-step-badge" style="background: #d32f2f; color: white !important;">NO TRIGGER</span>
            </div>
            <div class="hud-body">
                <div style="font-size: 13px; color: #d32f2f !important; font-weight: 900; text-transform: uppercase; border-bottom: 1px solid rgba(255,0,255,0.3); padding-bottom: 5px;">
                    Follow Hottest | S65 + C19 | P75 Stop Loss
                </div>
                {sniper_status_html}
            </div>
            <div class="hud-footer" style="padding-top: 5px; color: #ff00ff; font-weight: bold; display: flex; justify-content: space-between; align-items: center;">
                <i>"No Trigger. No Waiting."</i>
                <span style="font-size: 9px; background: rgba(255,0,255,0.1); padding: 2px 5px; border-radius: 3px;">Standalone Engine</span>
            </div>
        </div>
        """)

        status_cards_html += generate_status_card("SNIPER", target_disp, s_step, 84, [1]*10, status_flags["sniper"], 1)

        # --- TREND REVERSAL (OVERHEATED) DETECTION ---
        # Delegates to _detect_trend_reversal_overheated() which uses the
        # slider-controlled parameters (tr_*) for all thresholds.
        overheated_target, overheated_opposite, snap_occurred, misses_since_snap = (
            _detect_trend_reversal_overheated(
                spins,
                EVEN_MONEY,
                short_window=_coerce_int(tr_short_window, 10),
                short_hits=_coerce_int(tr_short_hits, 8),
                long_window=_coerce_int(tr_long_window, 15),
                long_hits=_coerce_int(tr_long_hits, 9),
                min_streak=_coerce_int(tr_min_streak, 5),
                density_window=_coerce_int(tr_density_window, 8),
                density_hits=_coerce_int(tr_density_hits, 7),
                active_lifetime=_coerce_int(tr_active_lifetime, 11),
            )
        )

        if overheated_target and not snap_occurred:
            on_deck_triggers.append(f"Overheated {overheated_target} (Wait for Snap)")
        
        if overheated_target and snap_occurred:
            status_flags["overheated"] = True
            highlight_targets.update(EVEN_MONEY[overheated_opposite])
            active_actions.insert(0, generate_action_card("🔥 TREND REVERSAL", f"Bet {overheated_opposite}", misses_since_snap, 0, seq_even_money, cost_even))
            active_target_groups.append((f"REVERSAL: {overheated_opposite.upper()}", sorted(EVEN_MONEY[overheated_opposite]), get_header_color("EVEN")))
            status_cards_html = generate_status_card("TREND REVERSAL", overheated_opposite, misses_since_snap, 0, seq_even_money, True, 1) + status_cards_html
        
        # --- NEW: NESTED COLD TRINITY DETECTOR ---
        cold_doz, cold_ds, cold_crnr, combined_cold_nums = calculate_nested_cold_zones(spins)
        
        # Build the HUD Card for the Cold Trinity
        crnr_str = ", ".join(map(str, sorted(cold_crnr))) if cold_crnr else "N/A"
        
        active_actions.append(f"""
        <div class="hud-card" style="border: 2px solid #1e3a8a; border-top: 5px solid #1e3a8a; background: #f0f9ff !important;">
            <div class="hud-header" style="background-color: #1e3a8a !important; color: white !important;">
                <span class="hud-title" style="color: white !important;">❄️ COLD TRINITY SENSOR</span>
                <span class="hud-step-badge">NESTED</span>
            </div>
            <div class="hud-body">
                <div style="font-size: 11px; color: #1e40af !important; font-weight: bold; text-transform: uppercase;">The Nested Path:</div>
                <div style="margin: 8px 0; text-align: left; font-size: 12px; color: #333 !important;">
                    <div style="padding: 2px 0; color: #333 !important;">📉 <b>Dozen:</b> {cold_doz}</div>
                    <div style="padding: 2px 0; color: #333 !important;">🧊 <b>D.Street:</b> {cold_ds}</div>
                    <div style="padding: 2px 0; color: #b91c1c !important;">🎯 <b>Corner:</b> {crnr_str}</div>
                </div>
                <div style="font-size: 10px; color: #64748b !important; font-style: italic; border-top: 1px solid #e2e8f0; padding-top: 5px;">
                    Tie-broken by Recency.
                </div>
            </div>
        </div>
        """)
        # -------------------------------------------------------------
        
        on_deck_html = ""
        if on_deck_triggers:
            on_deck_html = f'<div style="margin-bottom:10px; padding:8px; background:#fff3cd !important; border:1px solid #ffecb5; border-radius:6px; color:#856404 !important; font-size:12px; font-weight:bold; display:flex; align-items:center; gap:8px;">📡 ON DECK (1 Spin Away): <span style="font-weight:normal; color:#555 !important;">{", ".join(on_deck_triggers)}</span></div>'

        grind_card_title = "MANUAL GRIND TRACKER"
        display_target = "PAUSED / INACTIVE"
        hottest_sector = get_hottest_sector(spins)
        if isinstance(hottest_sector, list): hottest_sector_str = " / ".join(hottest_sector)
        else: hottest_sector_str = hottest_sector
        grind_rec_html = f'<span style="font-size:11px; color:#e65100; margin-left:10px; background:#fff3e0; padding:2px 6px; border-radius:4px; border:1px solid #ff9800;">🔥 Grind Rec: {hottest_sector_str}</span>'

        if grind_active:
            if grind_target == "Auto (Hottest D/C)":
                current_hottest = hottest_sector
                if isinstance(current_hottest, list):
                    display_target = f"Bet {' & '.join(current_hottest)} (Auto Tie)"
                    for t in current_hottest: grind_targets.add(t) 
                else:
                    display_target = f"Bet {current_hottest} (Auto)"
                    grind_targets.add(current_hottest) 
            else:
                display_target = f"Bet {grind_target}"
                grind_targets.add(grind_target) 
            active_actions.append(generate_action_card(grind_card_title, display_target, state.grind_step_index, 0, seq_manual_grind, cost_grind))
        
        status_flags["corner"] = best_corner_template and max_corner_miss >= corner_wait
        if status_flags["corner"]:
            t_name, t_nums = best_corner_template
            highlight_targets.update(t_nums)
            active_actions.append(generate_action_card("5-CORNER STRESS SHUFFLE", f"Bet {t_name} Corners", max_corner_miss, corner_wait, seq_corners, cost_corner))
            active_target_groups.append((f"BET {t_name.upper()} CORNERS", sorted(list(t_nums)), get_header_color("CORNER")))
        status_cards_html += generate_status_card("5-CORNER SHUFFLE", best_corner_template[0] if best_corner_template else "Scanning...", max_corner_miss, corner_wait, seq_corners, status_flags["corner"], 5)

        status_flags["d17"] = state.d17_locked and d17_miss_count >= d17_wait
        if status_flags["d17"]:
            highlight_targets.update(state.d17_list)
            active_actions.append(generate_action_card("17-NUMBER ASSAULT", "Bet Captured 17", d17_miss_count, d17_wait, seq_d17, cost_d17, set(state.d17_list)))
        status_cards_html += generate_status_card("DYNAMIC 17", f"{len(state.d17_list)}/17 #s", d17_miss_count if state.d17_locked else len(state.d17_list), d17_wait if state.d17_locked else 17, seq_d17, status_flags["d17"], 17)

        for ds_name, streak_val in ds_streaks.items():
            if streak_val >= ds_wait:
                status_flags["5ds"] = True
                is_ghost = ds_name in ghost_parents
                hot_numbers_set = set()
                range_to_skip = "N/A"
                if is_ghost:
                    hot_numbers_set.update(ghost_parents[ds_name])
                    range_to_skip = f"{ds_name} & Parents"
                    target_display = f"SAFETY: Skip {range_to_skip} & 0"
                    active_actions.append(generate_action_card("5DS SAFETY MODE", target_display, streak_val, ds_wait, seq_5ds, cost_5ds, is_5ds=True, spots_override=4))
                else:
                    hot_numbers_set.update(double_streets[ds_name])
                    range_to_skip = ds_ranges.get(ds_name, ds_name)
                    target_display = f"Skip: {range_to_skip} & 0"
                    active_actions.append(generate_action_card("5DS STRATEGY ALERT", target_display, streak_val, ds_wait, seq_5ds, cost_5ds, is_5ds=True, spots_override=5))

                all_numbers_set = set(range(1, 37))
                safe_numbers = all_numbers_set - hot_numbers_set
                highlight_targets.update(safe_numbers)
                active_target_groups.append(("BET 5DS (Excl. " + range_to_skip + ")", sorted(list(safe_numbers)), get_header_color("5DS")))
        
        status_flags["5ds"] = best_ds_streak >= ds_wait 
        status_cards_html += generate_status_card("5 DOUBLE STREETS", best_ds_name, best_ds_streak, ds_wait, seq_5ds, status_flags["5ds"], 5)

        if curr_left_miss >= left_wait:
            status_flags["left"] = True 
            highlight_targets.add("LeftSide")
            active_actions.append(generate_action_card("LEFT SIDE ATTACK", "Left + Zero", curr_left_miss, left_wait, seq_sides, cost_sides, set(left_side_covered), spots_override=25))
            active_target_groups.append(("LEFT SIDE", sorted(left_side_covered), get_header_color("SIDE")))
        status_cards_html += generate_status_card("LEFT SIDE ZERO", "LeftSide", curr_left_miss, left_wait, seq_sides, status_flags["left"], 25)

        if curr_right_miss >= right_wait:
            status_flags["right"] = True
            highlight_targets.add("RightSide")
            active_actions.append(generate_action_card("RIGHT SIDE ATTACK", "Right + Zero", curr_right_miss, right_wait, seq_sides, cost_sides, set(right_side_covered), spots_override=25))
            active_target_groups.append(("RIGHT SIDE", sorted(right_side_covered), get_header_color("SIDE")))
        status_cards_html += generate_status_card("RIGHT SIDE ZERO", "RightSide", curr_right_miss, right_wait, seq_sides, status_flags["right"], 25)

        if curr_voisins_miss >= voisins_wait:
            status_flags["voisins"] = True
            highlight_targets.add("Voisins")
            active_actions.append(generate_action_card("VOISINS ATTACK", "Voisins (0/2/3)", curr_voisins_miss, voisins_wait, seq_voisins, cost_voisins, set(voisins_numbers)))
            active_target_groups.append(("VOISINS", sorted(voisins_numbers), get_header_color("VOISINS")))
        status_cards_html += generate_status_card("VOISINS DU ZERO", "Voisins", curr_voisins_miss, voisins_wait, seq_voisins, status_flags["voisins"], 17)

        if curr_tiers_miss >= tiers_wait:
            status_flags["tiers"] = True
            highlight_targets.add("TiersOrph")
            active_actions.append(generate_action_card("TIERS+ORPH ATTACK", "Tiers + Orph", curr_tiers_miss, tiers_wait, seq_tiers, cost_tiers, set(tiers_orph_numbers)))
            active_target_groups.append(("TIERS+ORPH", sorted(tiers_orph_numbers), get_header_color("TIERS")))
        status_cards_html += generate_status_card("TIERS + ORPH", "TiersOrph", curr_tiers_miss, tiers_wait, seq_tiers, status_flags["tiers"], 20)

        ramp_display_list = []
        for r in range(1, 13):
            n = next((k for k, v in ramp_ranks.items() if v == r), None)
            if n is not None:
                if r <= active_ramp_spots:
                    style = "color:#FFD700; font-weight:900; font-size:13px; text-shadow: 0 0 5px rgba(255, 215, 0, 0.5); border-bottom: 2px solid #FFD700;"
                else:
                    style = "color:#00BFFF; font-weight:bold; font-size:11px;"
                ramp_display_list.append(f"<span style='{style}'>{n}</span>")
        
        ramp_str = " <span style='color:#ccc;'>|</span> ".join(ramp_display_list) if ramp_display_list else "<span style='color:#777;'>Waiting for hits...</span>"
        
        status_cards_html = f"""
        <div class="status-card" style="background: #2c3e50; color: #ecf0f1; border: 1px solid #34495e; width: 100%; max-width: 100%; margin-bottom: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #34495e; padding-bottom:3px; margin-bottom:3px;">
                <div style="font-size:10px; font-weight:bold; text-transform:uppercase; color: #bdc3c7;">🚀 VARIABLE 4-12 RAMP (Hit+Recency)</div>
                <div style="font-size:9px; color:#95a5a6;">GOLD(1-4) &rarr; BLUE(5-12)</div>
            </div>
            <div style="font-size:12px; line-height:1.4; letter-spacing:0.5px; text-align:center; padding:2px;">{ramp_str}</div>
        </div>
        """ + status_cards_html

        status_flags["missing"] = worst_section_miss_val >= miss_wait
        if status_flags["missing"]:
            highlight_targets.add(worst_section_name)
            active_actions.append(generate_action_card("MISSING DOZEN", worst_section_name, worst_section_miss_val, miss_wait, seq_missing_dozen, cost_dozen))
            active_target_groups.append((worst_section_name.upper(), sorted(DOZENS.get(worst_section_name, COLUMNS.get(worst_section_name, []))), get_header_color("MISSING")))
        status_cards_html += generate_status_card("MISSING DOZEN/COL", worst_section_name, worst_section_miss_val, miss_wait, seq_missing_dozen, status_flags["missing"], 1)

        status_flags["even"] = worst_even_miss_val >= even_wait
        if status_flags["even"]:
            highlight_targets.add(worst_even_name)
            active_actions.append(generate_action_card("EVEN MONEY DROUGHT", worst_even_name, worst_even_miss_val, even_wait, seq_even_money, cost_even))
            active_target_groups.append((worst_even_name.upper(), sorted(EVEN_MONEY[worst_even_name]), get_header_color("EVEN")))
        status_cards_html += generate_status_card("EVEN MONEY DROUGHT", worst_even_name, worst_even_miss_val, even_wait, seq_even_money, status_flags["even"], 1)        

        status_flags["streak"] = best_streak_val >= streak_wait
        if status_flags["streak"]:
            target_str = streak_targets.get(best_streak_name, "Others")
            if "1st" in target_str: highlight_targets.add("1st " + best_streak_name.split()[1])
            if "2nd" in target_str: highlight_targets.add("2nd " + best_streak_name.split()[1])
            if "3rd" in target_str: highlight_targets.add("3rd " + best_streak_name.split()[1])
            active_actions.append(generate_action_card("TWO DOZENS STREAK ATTACK", f"Bet {target_str}", best_streak_val, streak_wait, seq_two_dozens, cost_streak))
        status_cards_html += generate_status_card("TWO DOZENS STREAK ATTACK", display_streak_target, best_streak_val, streak_wait, seq_two_dozens, status_flags["streak"], 2)

        d_data = get_pattern_alert(spins, "dozen")
        if d_data:
            status_flags["pattern"] = True
            d_pat, d_match_data, d_follow_data = d_data
            bet_list_html = ""
            # Apply Strategy_1 Two Dozen Progression
            p_seq = seq_two_dozens
            
            for i, (cat, val) in enumerate(d_follow_data):
                spin_num = i + 1
                # Select unit based on current phase index
                u = p_seq[i] if i < len(p_seq) else "MAX"
                suggestion = "Skip (0)"
                if cat == "D1": suggestion = f"Bet D2 + D3 ({u}u each)";
                elif cat == "D2": suggestion = f"Bet D1 + D3 ({u}u each)";
                elif cat == "D3": suggestion = f"Bet D1 + D2 ({u}u each)";
                if i == 0:
                    if cat == "D1": highlight_targets.update(["2nd Dozen", "3rd Dozen"])
                    elif cat == "D2": highlight_targets.update(["1st Dozen", "3rd Dozen"])
                    elif cat == "D3": highlight_targets.update(["1st Dozen", "2nd Dozen"])
                bet_list_html += f"<div style='font-size:12px; margin-top:4px; border-bottom:1px dashed #eee; display:flex; justify-content:space-between;'><span>Spin {spin_num}:</span> <span style='color:#d32f2f; font-weight:800;'>{suggestion}</span></div>"
            active_actions.append(f"""
            <div class="hud-card green-card" style="min-width:260px; border-left-color:#3f51b5; border: 2px solid #3f51b5; background: white !important;">
                <div class="hud-header" style="background:#3f51b5 !important; color:#fff !important;"><span class="hud-title" style="color: white !important;">PATTERN MATCH (X={pat_x})</span></div>
                <div class="hud-body" style="text-align:left;">
                    <div style="font-size:11px; color:#555 !important; margin-bottom:6px;"><b>Found:</b> {format_seq(d_match_data)}</div>
                    <div style="background:#e8eaf6 !important; padding:8px; border-radius:4px; border:1px solid #c5cae9;">
                        <div style="font-weight:bold; font-size:11px; color:#1a237e !important; margin-bottom:4px; text-transform:uppercase;">Anti-Betting Plan:</div>
                        {bet_list_html}
                    </div>
                </div>
            </div>
            """)
        
        status_cards_html += f"""
        <div class="status-card" style="{get_status_style(status_flags['pattern'])}">
            <div style="font-size:10px; font-weight:bold; text-transform:uppercase;">2 DOZENS PATTERN</div>
            <div style="font-size:13px; font-weight:800; margin-bottom:4px;">Target: Auto-Detect</div>
            <span class="live-count">Match Length: X{pat_x}</span>
            <span style="font-size:10px; color:#666;">Dynamic Anti-Bet</span>
        </div>
        """

        zero_miss_count = count_misses({0}, spins, zero_is_miss=False)
        if len(active_actions) > 1 and zero_miss_count > 30: 
             active_actions.append(f"""
            <div class="hud-card" style="border: 2px solid #2ecc71; border-top: 5px solid #2ecc71; animation: pulse 2s infinite; background: white !important;">
                <div class="hud-header" style="background-color: #2ecc71 !important; color: white !important;">
                    <span class="hud-title" style="color: white !important;">🛡️ ZERO GUARD</span>
                </div>
                <div class="hud-body">
                    <div style="font-size: 12px; color: #555 !important; font-weight: bold;">INSURANCE ALERT</div>
                    <div style="font-size: 14px; font-weight: 800; color: #27ae60 !important; margin: 5px 0;">Cover Zero (0)</div>
                    <div style="font-size: 11px; color: #333 !important;">Zero Missed: {zero_miss_count} Spins</div>
                    <div style="font-size: 10px; color: #666 !important; margin-top: 5px;">Place small unit on 0 to hedge bets.</div>
                </div>
            </div>
            """)

        # =========================================================
        # NEW: NON-REPEATERS TRACKER
        # =========================================================
        if len(spins) > 0:
            track_count = int(non_repeater_spins)
            target_count = int(nr_target)
            recent_nr_spins = spins[-track_count:] if len(spins) >= track_count else spins
            
            counts = {}
            for s in recent_nr_spins:
                val = int(s)
                counts[val] = counts.get(val, 0) + 1
                
            non_repeaters = sorted([num for num, c in counts.items() if c == 1])
            current_nr_set = set(non_repeaters)
            
            # --- In/Out Radar Logic (With Casino Persistent Memory) ---
            if current_spin_count > getattr(state, 'nr_last_spin_count', 0):
                # Forcing a hard copy with set() prevents memory reference bugs
                state.previous_non_repeaters = set(getattr(state, 'current_non_repeaters', set()))
                state.nr_last_spin_count = current_spin_count
                
            state.current_non_repeaters = set(current_nr_set)
            
            # Calculate raw movement for the exact current spin
            entries = sorted(list(state.current_non_repeaters - state.previous_non_repeaters))
            exits = sorted(list(state.previous_non_repeaters - state.current_non_repeaters))
            
            # Save to persistent memory INDEPENDENTLY so a new IN doesn't erase an old OUT
            if entries:
                state.nr_mem_in = entries
                state.nr_mem_spin_in = current_spin_count
            if exits:
                state.nr_mem_out = exits
                state.nr_mem_spin_out = current_spin_count
                
            # Retrieve display values (stays on screen even if current spin had no movement)
            disp_in = getattr(state, 'nr_mem_in', [])
            disp_out = getattr(state, 'nr_mem_out', [])
            disp_spin_in = getattr(state, 'nr_mem_spin_in', current_spin_count)
            disp_spin_out = getattr(state, 'nr_mem_spin_out', current_spin_count)
            
            in_str = ", ".join(map(str, disp_in)) if disp_in else "--"
            out_str = ", ".join(map(str, disp_out)) if disp_out else "--"
            
            # Dim the IN/OUT radar individually if it's showing data from a past spin
            is_stale_in = current_spin_count > disp_spin_in
            stale_text_in = f"<span style='color:#999; font-weight:normal;'> (Spin {disp_spin_in})</span>" if is_stale_in and disp_spin_in > 0 else ""
            opacity_css_in = "opacity: 0.5;" if is_stale_in else "opacity: 1.0;"

            is_stale_out = current_spin_count > disp_spin_out
            stale_text_out = f"<span style='color:#999; font-weight:normal;'> (Spin {disp_spin_out})</span>" if is_stale_out and disp_spin_out > 0 else ""
            opacity_css_out = "opacity: 0.5;" if is_stale_out else "opacity: 1.0;"
            # ----------------------------------------------------------
            
            nr_str = ", ".join(map(str, non_repeaters)) if non_repeaters else "None"
            
            # --- Target Alert Logic ---
            is_target_hit = len(non_repeaters) >= target_count
            alert_style = "border: 3px solid #ff00ff; box-shadow: 0 0 15px #ff00ff; animation: pulse 1.5s infinite;" if is_target_hit else "border: 2px solid #8e44ad; border-top: 5px solid #8e44ad;"
            header_bg = "#ff00ff" if is_target_hit else "#8e44ad"
            target_badge = f'<div style="background: #ff00ff; color: white; font-weight: bold; font-size: 12px; padding: 4px; border-radius: 4px; margin-bottom: 8px;">🔥 TARGET REACHED: {len(non_repeaters)}/{target_count}</div>' if is_target_hit else f'<div style="font-size: 10px; color: #888; margin-bottom: 5px; font-weight: bold; background: #eee; padding: 3px; border-radius: 3px;">Target: {len(non_repeaters)} / {target_count}</div>'
            
            active_actions.append(f"""
            <div class="hud-card" style="{alert_style} background: white !important;">
                <div class="hud-header" style="background-color: {header_bg} !important; color: white !important;">
                    <span class="hud-title" style="color: white !important;">🎯 NON-REPEATERS</span>
                    <span class="hud-step-badge">LAST {len(recent_nr_spins)} SPINS</span>
                </div>
                <div class="hud-body">
                    {target_badge}
                    <div style="font-size: 11px; color: #555 !important; font-weight: bold; text-transform: uppercase;">Hit Exactly Once:</div>
                    <div style="margin: 6px 0; font-size: 15px; font-weight: 900; color: #8e44ad !important; word-wrap: break-word; line-height: 1.4;">
                        {nr_str}
                    </div>
                    <div style="display: flex; gap: 5px; margin-top: 8px; border-top: 1px solid #eee; padding-top: 8px; font-size: 12px; transition: opacity 0.3s ease;">
                        <div style="flex: 1; text-align: center; border-right: 1px solid #eee; {opacity_css_in}"><span style="color:#2ecc71; font-weight:900; display:block; font-size:10px; text-transform:uppercase;">➕ In{stale_text_in}</span> <span style="font-weight:bold;">{in_str}</span></div>
                        <div style="flex: 1; text-align: center; {opacity_css_out}"><span style="color:#e74c3c; font-weight:900; display:block; font-size:10px; text-transform:uppercase;">➖ Out{stale_text_out}</span> <span style="font-weight:bold;">{out_str}</span></div>
                    </div>
                </div>
            </div>
            """)

        # --- NEW: HUD CARD VISIBILITY FILTER INTERCEPTOR ---
        filtered_actions = []
        filtered_groups = []
        
        for html_str in active_actions:
            if "VARIABLE 4-12 RAMP" in html_str or "-19 STRATEGY" in html_str or "MANUAL GRIND" in html_str:
                if "Ramp/Grind/X-19" in hud_filters: filtered_actions.append(html_str)
            elif "ZERO-LOSS SNIPER" in html_str or "SNIPER STRIKE" in html_str:
                if "Sniper Strike" in hud_filters: filtered_actions.append(html_str)
            elif "COLD TRINITY SENSOR" in html_str:
                if "Cold Trinity" in hud_filters: filtered_actions.append(html_str)
            elif "MISSING DOZEN" in html_str:
                if "Missing Dozen/Col" in hud_filters: filtered_actions.append(html_str)
            elif "EVEN MONEY DROUGHT" in html_str:
                if "Even Money Drought" in hud_filters: filtered_actions.append(html_str)
            elif "TREND REVERSAL" in html_str:
                if "Trend Reversal" in hud_filters: filtered_actions.append(html_str)
            elif "STREAK ATTACK" in html_str:
                if "Streak Attack" in hud_filters: filtered_actions.append(html_str)
            elif "PATTERN MATCH" in html_str:
                if "Pattern Match" in hud_filters: filtered_actions.append(html_str)
            elif "VOISINS ATTACK" in html_str or "TIERS+ORPH ATTACK" in html_str:
                if "Voisins/Tiers" in hud_filters: filtered_actions.append(html_str)
            elif "LEFT SIDE ATTACK" in html_str or "RIGHT SIDE ATTACK" in html_str:
                if "Left/Right Sides" in hud_filters: filtered_actions.append(html_str)
            elif "5-CORNER" in html_str or "17-NUMBER ASSAULT" in html_str or "5DS" in html_str:
                if "5DS/Corners/D17" in hud_filters: filtered_actions.append(html_str)
            elif "ZERO GUARD" in html_str:
                if "Zero Guard" in hud_filters: filtered_actions.append(html_str)
            elif "NON-REPEATERS" in html_str:
                if "Non-Repeaters" in hud_filters: filtered_actions.append(html_str)
            else:
                filtered_actions.append(html_str) # Safety fallback
                
        for group in active_target_groups:
            title, nums, color = group
            t = title.upper()
            if "RAMP" in t or "-19" in t or "GRIND" in t:
                if "Ramp/Grind/X-19" in hud_filters: filtered_groups.append(group)
            elif "SNIPER" in t:
                if "Sniper Strike" in hud_filters: filtered_groups.append(group)
            elif "TRINITY" in t:
                if "Cold Trinity" in hud_filters: filtered_groups.append(group)
            elif "DOZEN" in t or "COLUMN" in t:
                # Catch Missing Dozen/Col, but avoid Streak Attack and Pattern Match
                if "STREAK" not in t and "PATTERN" not in t:
                    if "Missing Dozen/Col" in hud_filters: filtered_groups.append(group)
                elif "STREAK" in t:
                    if "Streak Attack" in hud_filters: filtered_groups.append(group)
                elif "PATTERN" in t:
                    if "Pattern Match" in hud_filters: filtered_groups.append(group)
            elif "EVEN" in t or "ODD" in t or "RED" in t or "BLACK" in t or "LOW" in t or "HIGH" in t:
                if "REVERSAL" in t:
                    if "Trend Reversal" in hud_filters: filtered_groups.append(group)
                else:
                    if "Even Money Drought" in hud_filters: filtered_groups.append(group)
            elif "VOISINS" in t or "TIERS" in t:
                if "Voisins/Tiers" in hud_filters: filtered_groups.append(group)
            elif "SIDE" in t:
                if "Left/Right Sides" in hud_filters: filtered_groups.append(group)
            elif "CORNER" in t or "17" in t or "5DS" in t:
                if "5DS/Corners/D17" in hud_filters: filtered_groups.append(group)
            elif "ZERO" in t:
                if "Zero Guard" in hud_filters: filtered_groups.append(group)
            else:
                filtered_groups.append(group)
                
        active_actions = filtered_actions
        active_target_groups = filtered_groups

        # --- GENERATE BOTTOM ROW ---
        hot_numbers_html = '<div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee; display: flex; flex-wrap: wrap; align-items: flex-start; gap: 15px; padding-bottom: 5px;">'
        if hot_list:
            hot_numbers_html += '<div style="display: flex; align-items: center; border-right: 2px solid #eee; padding-right: 15px; margin-bottom: 10px;">'
            hot_numbers_html += '<span style="font-size: 11px; font-weight: bold; color: #d32f2f; text-transform: uppercase; margin-right: 10px;">🔥 Top 5 Hot:</span>'
            for num, score in hot_list:
                c = colors.get(str(num), "black")
                hot_numbers_html += f'<span style="display: inline-block; background-color: {c}; color: white; border-radius: 50%; width: 28px; height: 28px; text-align: center; line-height: 28px; font-size: 13px; font-weight: bold; margin-right: 4px; box-shadow: 0 2px 3px rgba(0,0,0,0.1);">{num}</span>'
            hot_numbers_html += '</div>'
        else:
             hot_numbers_html += '<div style="color: #888; font-size: 11px; padding-right: 15px; margin-bottom: 10px;">Waiting for spin data...</div>'

        master_coverage_set = set()
        if active_target_groups:
            for title, nums, color in active_target_groups:
                master_coverage_set.update(nums)
                hot_numbers_html += f'<div style="display: flex; align-items: center; border-right: 1px solid #eee; padding-right: 15px; margin-bottom: 10px;">'
                hot_numbers_html += f'<span style="font-size: 11px; font-weight: bold; color: {color}; text-transform: uppercase; margin-right: 10px;">{title}:</span>'
                for num in nums:
                    if num == 0: c = "#27ae60" 
                    else: c = colors.get(str(num), "black")
                    hot_numbers_html += f'<span style="display: inline-block; background-color: {c}; color: white; border: 2px solid {color}; border-radius: 50%; width: 24px; height: 24px; text-align: center; line-height: 20px; font-size: 11px; font-weight: bold; margin-right: 3px;">{num}</span>'
                hot_numbers_html += '</div>'
        hot_numbers_html += '</div>' 

        if master_coverage_set or hot_subset:
            master_coverage_set.update(hot_subset)
            sorted_master = sorted(list(master_coverage_set))
            
            risk_pct = int((len(sorted_master) / 37) * 100)
            risk_color = "#4CAF50" # Safe
            if risk_pct > 40: risk_color = "#FFC107" # Moderate
            if risk_pct > 65: risk_color = "#D32F2F" # High Risk
            risk_meter_html = f'<span style="font-size:11px; color:{risk_color}; margin-left:auto; background:#fff; padding:2px 6px; border-radius:4px; border:1px solid {risk_color}; font-weight:bold;">🛡️ Coverage: {risk_pct}% ({len(sorted_master)} #s)</span>'
            
            zeros_list = [n for n in sorted_master if n == 0]
            d1_list = [n for n in sorted_master if 1 <= n <= 12]
            d2_list = [n for n in sorted_master if 13 <= n <= 24]
            d3_list = [n for n in sorted_master if 25 <= n <= 36]
            
            hot_numbers_html += f'<div style="margin-top: 5px; padding: 10px; background: #f1f8e9; border: 1px dashed #7cb342; border-radius: 8px;">'
            hot_numbers_html += f'<div style="font-size: 11px; font-weight: 900; color: #33691e; text-transform: uppercase; margin-bottom: 8px; display:flex; align-items:center;">🎯 TOTAL UNIQUE COVERAGE: {risk_meter_html}</div>'
            hot_numbers_html += '<div style="display: flex; flex-wrap: wrap; gap: 15px;">'
            
            def render_group(nums):
                html_out = '<div style="display: flex; gap: 4px; align-items: center; border-right: 1px solid #ccc; padding-right: 10px; margin-right: 5px;">'
                for num in nums:
                    if num == 0: c = "#27ae60"
                    else: c = colors.get(str(num), "black")
                    
                    flame = ""
                    if num in hot_subset:
                        flame = '<span style="position:absolute; top:-6px; right:-6px; font-size:10px; z-index:10; filter: drop-shadow(0 0 2px white);">🔥</span>'
                    
                    html_out += f'<span style="display: inline-block; position: relative; background-color: {c}; color: white; border-radius: 4px; padding: 3px 8px; font-size: 12px; font-weight: bold; box-shadow: 0 1px 2px rgba(0,0,0,0.2);">{num}{flame}</span>'
                html_out += '</div>'
                return html_out

            if zeros_list: hot_numbers_html += render_group(zeros_list)
            if d1_list: hot_numbers_html += render_group(d1_list)
            if d2_list: hot_numbers_html += render_group(d2_list)
            if d3_list: hot_numbers_html += render_group(d3_list)
            hot_numbers_html += '</div></div>'

        # --- BUILD ACTIVE ACTIONS UI ---
        if active_actions:
            actions_section = f"""
            <style>
                .hud-container {{
                    display: flex !important;
                    flex-direction: row !important;
                    flex-wrap: wrap !important;
                    gap: 15px !important;
                    justify-content: center !important;
                    align-items: flex-start !important;
                    width: 100% !important;
                    margin-bottom: 20px !important;
                    color-scheme: light !important;
                }}
                .hud-card {{
                    background: white !important;
                    background-color: white !important;
                    color: #333 !important;
                    color-scheme: light !important;
                    border-radius: 12px !important;
                    padding: 15px !important;
                    width: 240px !important;
                    flex: 0 0 auto !important;
                    box-shadow: 0 6px 12px rgba(0,0,0,0.15) !important;
                    display: flex !important;
                    flex-direction: column !important;
                    transition: transform 0.2s !important;
                    box-sizing: border-box !important;
                    overflow: hidden !important;
                }}
                .hud-card:hover {{ transform: translateY(-3px) !important; }}
                .hud-card * {{ box-sizing: border-box; }}
                /* Force light mode on all card internals - override Gradio dark mode */
                .dark .hud-card {{ background: white !important; background-color: white !important; color: #333 !important; }}
                .dark .hud-card .hud-body {{ color: #333 !important; }}
                .dark .hud-card .hud-body > div {{ color: #333 !important; }}
                .dark .hud-card .hud-header {{ color: white !important; }}
                .dark .hud-card .hud-title {{ color: white !important; }}
                .dark .hud-card .hud-footer, .dark .hud-card .hud-footer * {{ color: #888 !important; }}
                .dark .hud-card table td, .dark .hud-card table th {{ color: #333 !important; background-color: transparent !important; }}
                .dark .hud-card table tr {{ background-color: #fff !important; }}
                .hud-header {{
                    display: flex !important;
                    justify-content: space-between !important;
                    align-items: center !important;
                    font-size: 11px !important;
                    margin: -15px -15px 10px -15px !important;
                    padding: 8px 15px !important;
                    border-bottom: 1px solid rgba(0,0,0,0.1) !important;
                }}
                .hud-title {{ font-weight: 900 !important; text-transform: uppercase !important; letter-spacing: 0.5px !important; color: inherit !important; }}
                .hud-step-badge {{ background: rgba(0,0,0,0.2) !important; background-color: rgba(0,0,0,0.2) !important; padding: 2px 6px !important; border-radius: 4px !important; font-size: 10px !important; color: white !important; }}
                .hud-body {{ text-align: center !important; margin: 5px 0 !important; width: 100% !important; color: #333 !important; }}
                .hud-body > div {{ color: #333 !important; }}
                .hud-body table {{ color: #333 !important; background: transparent !important; }}
                .hud-body table td, .hud-body table th {{ color: #333 !important; }}
                .hud-body table tr {{ background-color: #fff !important; }}
                .hud-body table tr:nth-child(odd) {{ background-color: #f9f9f9 !important; }}
                .hud-body table tr:first-child {{ background-color: #f0f0f0 !important; }}
                .hud-body table tr:first-child th {{ color: #555 !important; }}
                .hud-footer {{ margin-top: auto !important; font-size: 10px !important; color: #888 !important; text-align: center !important; border-top: 1px solid #eee !important; padding-top: 8px !important; }}
                .hud-footer * {{ color: #999 !important; }}
            </style>
            <div class="hud-container">
                {"".join(active_actions)}
            </div>
            """
        else:
            actions_section = "<div style='text-align:center; padding:15px; color:#888; font-style:italic; margin-bottom: 20px;'>No Active Triggers. Waiting for patterns...</div>"

        # --- AUTO-NUDGE: update overrides after all status_flags are set ---
        # Only runs in AUTO mode; fails closed if status_flags is unavailable.
        _auto_nudge_apply(status_flags, current_spin_count)

        # When only the strategy cards are needed (e.g. near-table duplicate area)
        if return_cards_only:
            # --- Brain Confidence + Advisory Strip ---
            # Rendered FIRST so _brain_target and _confidence are available for both
            # the Double Confirmation context and the DC-aware Bet Sizing Guide.
            _rendering.render_final_brain_html(state)
            _suggestion = getattr(state, 'live_brain_last_suggestion', '')
            _confidence = int(getattr(state, 'live_brain_last_confidence', 0))
            # Extract brain's target category from the suggestion string.
            # Formats (from rendering.py):
            #   "Target {name} (confidence X%)" → _brain_target = name
            #   "SNIPER: play 87-phase on ..."  → _brain_target = "SNIPER"
            #   "No strong signal — ..."        → _brain_target = ""
            _brain_target = ""
            if _suggestion.startswith("Target "):
                _brain_target = _suggestion[len("Target "):].split(" (")[0].strip()
            elif _suggestion.startswith("SNIPER"):
                _brain_target = "SNIPER"

            brain_strip_html = ""
            if _suggestion and _confidence > 0:
                if _confidence >= 70:
                    _strip_color = "#22c55e"
                    _strip_level = "HIGH CONFIDENCE"
                elif _confidence >= 50:
                    _strip_color = "#f59e0b"
                    _strip_level = "MODERATE SIGNAL"
                elif _confidence >= 25:
                    _strip_color = "#06b6d4"
                    _strip_level = "WEAK SIGNAL"
                else:
                    _strip_color = "#94a3b8"
                    _strip_level = "ALL CLEAR"
                if _brain_target and _brain_target != "SNIPER":
                    _advisory_short = f"👉 If I were you, right now I would target <b style='color:#fbbf24;'>{_brain_target}</b>"
                elif _brain_target == "SNIPER":
                    _advisory_short = "⚡ SNIPER ACTIVE — play the 87-phase progression"
                else:
                    _advisory_short = "⚖️ No strong signal right now — be patient"
                brain_strip_html = f"""<div style="background:linear-gradient(135deg,#0a0a1a,#1a0a2e);border:1px solid {_strip_color}55;border-radius:10px;padding:10px 16px;margin-bottom:14px;font-family:'Segoe UI',system-ui,sans-serif;">
  <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
    <span style="background:{_strip_color}22;border:2px solid {_strip_color};border-radius:6px;padding:4px 12px;color:{_strip_color};font-size:12px;font-weight:800;white-space:nowrap;">🧠 {_confidence}% {_strip_level}</span>
    <span style="color:#e2e8f0;font-size:13px;line-height:1.4;">{_advisory_short}</span>
  </div>
</div>"""

            # --- Double Confirmation context (computed before Bet Sizing Guide) ---
            # Scenario test cases for manual verification:
            #   DC-HIGH (expect $1.00 unless danger flags clamp to $0.10):
            #     Spins: 2,5,8,11,14,17,20,23,26,29,32,35,5,11,17,23,29,35
            #     MANUAL  → no rec rows shown at all
            #     SUGGEST → DC target row first: "$1.00 OPPORTUNITY" (no danger)
            #                                or "$0.10 HOLD CLAMPED (...)" (danger)
            #     AUTO    → same as SUGGEST + bounded ±1 threshold nudges
            #   Chaos/mixed (expect mostly $0.10 and some $0.01):
            #     Spins: 0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30
            #   Overheat/pattern heavy (DC-HIGH still min $0.10, never $0.01):
            #     Spins: 1,3,5,7,9,12,14,16,18,19,21,23,3,5,7,9,14,16
            _matches = []  # list of (strategy_name, display_target)
            if _suggestion and _brain_target:
                # 1. Missing Dozen/Col: brain matches the most-missing dozen or column
                if (status_flags.get("missing", False) and
                        "Missing Dozen/Col" in (hud_filters or []) and
                        _brain_target == worst_section_name):
                    _matches.append(("Missing Dozen/Col", worst_section_name))

                # 2. Even Money Drought: brain matches the most drought even-money bet
                if (status_flags.get("even", False) and
                        "Even Money Drought" in (hud_filters or []) and
                        _brain_target == worst_even_name):
                    _matches.append(("Even Money Drought", worst_even_name))

                # 3. Streak Attack: brain targets one of the two anti-streak dozens/columns
                if (status_flags.get("streak", False) and
                        "Streak Attack" in (hud_filters or []) and
                        best_streak_name not in ("N/A", "")):
                    _streak_anti = set()
                    if best_streak_name == "1st Dozen":
                        _streak_anti = {"2nd Dozen", "3rd Dozen"}
                    elif best_streak_name == "2nd Dozen":
                        _streak_anti = {"1st Dozen", "3rd Dozen"}
                    elif best_streak_name == "3rd Dozen":
                        _streak_anti = {"1st Dozen", "2nd Dozen"}
                    elif best_streak_name == "1st Column":
                        _streak_anti = {"2nd Column", "3rd Column"}
                    elif best_streak_name == "2nd Column":
                        _streak_anti = {"1st Column", "3rd Column"}
                    elif best_streak_name == "3rd Column":
                        _streak_anti = {"1st Column", "2nd Column"}
                    if _brain_target in _streak_anti:
                        _matches.append(("Streak Attack", f"{streak_targets.get(best_streak_name, _brain_target)}"))

                # 4. Pattern Match: brain targets one of the two anti-pattern dozens
                if (status_flags.get("pattern", False) and
                        "Pattern Match" in (hud_filters or []) and
                        d_data):
                    try:
                        _, _, _d_follow = d_data
                        if _d_follow:
                            _d_cat = _d_follow[0][0]  # "D1", "D2", or "D3"
                            _pat_anti = set()
                            if _d_cat == "D1":
                                _pat_anti = {"2nd Dozen", "3rd Dozen"}
                            elif _d_cat == "D2":
                                _pat_anti = {"1st Dozen", "3rd Dozen"}
                            elif _d_cat == "D3":
                                _pat_anti = {"1st Dozen", "2nd Dozen"}
                            if _brain_target in _pat_anti:
                                _matches.append(("Pattern Match", _brain_target))
                    except (TypeError, IndexError, ValueError):
                        pass

            # Build dc_context for the Bet Sizing Guide recommendation row.
            # DC clamp rules (applied inside _render_nudge_recommendations_html):
            #   confidence >= 70 + no danger  → $1.00 OPPORTUNITY
            #   confidence >= 70 + danger      → $0.10 HOLD  (CLAMPED note shown)
            #   never $0.01 when DC is HIGH (>= 70%)
            _dc_active = bool(_matches)
            _dc_context: dict = {}
            if _dc_active:
                _has_danger, _clamp_note = _get_dc_danger_info(status_flags)
                _dc_context = {
                    "active": True,
                    "target": _brain_target,
                    "confidence": _confidence,
                    "has_danger": _has_danger,
                    "clamp_note": _clamp_note,
                }

            # --- Bet Sizing Guide (always visible reference card) ---
            # Build the nudge recommendations HTML if SUGGEST or AUTO mode is on.
            _nudge_active_targets = _get_active_de2d_targets_from_flags(
                status_flags,
                worst_section_name, worst_section_miss_val, miss_wait,
                worst_even_name, worst_even_miss_val, even_wait,
                best_streak_name, best_streak_val, streak_wait,
                curr_voisins_miss, voisins_wait,
                curr_tiers_miss, tiers_wait,
                curr_left_miss, left_wait,
                curr_right_miss, right_wait,
                best_ds_name, best_ds_streak, ds_wait,
                d17_miss_count, d17_wait, getattr(state, 'd17_locked', False),
                max_corner_miss, corner_wait, best_corner_template,
            )
            _nudge_recs_html = _render_nudge_recommendations_html(
                _nudge_active_targets, _nudge_state.get("mode", "MANUAL"),
                dc_context=_dc_context,
            )
            bet_sizing_html = (
                """<div style="background:#0f172a;border:1px solid #334155;border-radius:10px;padding:14px 18px;margin-bottom:14px;font-family:'Segoe UI',system-ui,sans-serif;">"""
                """  <div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;font-weight:700;">📊 BET SIZING GUIDE</div>"""
                """  <div style="display:flex;flex-direction:column;gap:7px;">"""
                """    <div style="display:flex;align-items:center;gap:10px;">"""
                """      <span style="background:#22c55e;color:white;font-size:11px;font-weight:700;padding:3px 10px;border-radius:6px;min-width:90px;text-align:center;">≥70% HIGH</span>"""
                """      <span style="color:#e2e8f0;font-size:13px;">→ Bet <b style="color:#22c55e;">$1.00</b> (1 unit)</span>"""
                """    </div>"""
                """    <div style="display:flex;align-items:center;gap:10px;">"""
                """      <span style="background:#f59e0b;color:white;font-size:11px;font-weight:700;padding:3px 10px;border-radius:6px;min-width:90px;text-align:center;">50-69% MOD</span>"""
                """      <span style="color:#e2e8f0;font-size:13px;">→ Bet <b style="color:#f59e0b;">$0.10</b></span>"""
                """    </div>"""
                """    <div style="display:flex;align-items:center;gap:10px;">"""
                """      <span style="background:#ef4444;color:white;font-size:11px;font-weight:700;padding:3px 10px;border-radius:6px;min-width:90px;text-align:center;">&lt;50% WEAK</span>"""
                """      <span style="color:#e2e8f0;font-size:13px;">→ Bet <b style="color:#ef4444;">$0.01</b> (minimum)</span>"""
                """    </div>"""
                """  </div>"""
                + _nudge_recs_html
                + _render_nudge_log_html()
                + """</div>"""
            )

            # --- Double Confirmation Alert (built from already-computed _matches) ---
            double_conf_html = ""
            if _matches:
                if _confidence >= 70:
                    _border = "#22c55e"
                    _bet_text = "$1.00 (1 unit)"
                    _level = "HIGH"
                elif _confidence >= 50:
                    _border = "#f59e0b"
                    _bet_text = "$0.10"
                    _level = "MODERATE"
                else:
                    _border = "#ef4444"
                    _bet_text = "$0.01 (minimum)"
                    _level = "WEAK"

                if len(_matches) == 1:
                    _match_label = f"Brain + {_matches[0][0]} BOTH recommend"
                else:
                    _strat_names = " + ".join(s for s, _ in _matches)
                    _match_label = f"Brain + {_strat_names} ALL recommend"

                double_conf_html = f"""<div style="background:linear-gradient(135deg,#1a0a2e,#0f172a);border:3px solid {_border};border-radius:12px;padding:16px 20px;margin-bottom:14px;font-family:'Segoe UI',system-ui,sans-serif;box-shadow:0 0 20px {_border}55;animation:final-brain-glow 2.5s ease-in-out infinite;">
  <div style="color:{_border};font-size:16px;font-weight:900;text-align:center;margin-bottom:10px;letter-spacing:1px;">🔥🔥 DOUBLE CONFIRMATION 🔥🔥</div>
  <div style="color:#e2e8f0;font-size:14px;font-weight:700;text-align:center;margin-bottom:10px;">
    {_match_label}: <span style="color:{_border};font-size:15px;font-weight:900;">{_brain_target}</span>
  </div>
  <div style="display:flex;justify-content:center;gap:12px;flex-wrap:wrap;">
    <span style="background:{_border}22;border:1px solid {_border};border-radius:6px;padding:5px 12px;color:{_border};font-size:13px;font-weight:700;">Confidence: {_confidence}% — {_level}</span>
    <span style="background:{_border}22;border:1px solid {_border};border-radius:6px;padding:5px 12px;color:#e2e8f0;font-size:13px;font-weight:700;">Recommended Bet: {_bet_text}</span>
  </div>
</div>"""

            return brain_strip_html + bet_sizing_html + double_conf_html + actions_section

        # --- VISUAL TABLE ---
        zero_active = (0 in highlight_targets) or ("Voisins" in highlight_targets and 0 in voisins_numbers) or ("LeftSide" in highlight_targets and 0 in left_side_covered)
        zero_hot = 0 in hot_subset
        
        zero_flame = ""
        if zero_hot:
            zero_flame = '<span style="position:absolute; top:2px; right:2px; font-size:10px; z-index:10; filter: drop-shadow(0 0 2px rgba(0,0,0,0.5));">🔥</span>'
        
        zero_rank = ramp_ranks.get(0, 0)
        zero_rank_badge = ""
        if zero_rank > 0:
            is_active_zero = zero_rank <= active_ramp_spots
            badge_bg = "#FFD700" if is_active_zero else "#00BFFF"
            badge_txt = "black" if is_active_zero else "white"
            border_style = "border:2px solid #FFD700;" if is_active_zero else "border:1px solid white;"
            zero_rank_badge = f'<span style="position:absolute; top:2px; left:2px; width:14px; height:14px; background-color:{badge_bg}; color:{badge_txt}; font-size:9px; font-weight:bold; border-radius:50%; display:flex; align-items:center; justify-content:center; z-index:20; {border_style} box-shadow:0 1px 2px rgba(0,0,0,0.3);">{zero_rank}</span>'

        in_spotlight_zero = zero_active or zero_hot
        zero_opacity = "1.0" if in_spotlight_zero else "0.3"
        
        zero_style = "background-color: #27ae60; color: white;"
        if zero_active:
            zero_style = active_style
            if zero_hot: zero_style += " border: 3px solid #ff3333; box-shadow: 0 0 10px #ff0000;"
        elif zero_hot:
             zero_style += " opacity:0.9; border: 3px solid #ff3333; box-shadow: inset 0 0 5px #ff0000;"
        
        top_picks = state.current_top_picks
        top_pick_1 = top_picks[0] if len(top_picks) > 0 else None
        
        zero_target = ""
        if 0 == top_pick_1:
             zero_target = '<span style="position:absolute; bottom:-2px; right:-2px; font-size:18px; z-index:30; color:#FFFFFF; text-shadow: 0 0 5px #00FFFF, 0 0 10px #00FFFF; font-weight:900; line-height:1;">⌖</span>'
        elif 0 in top_picks[:5]:
             zero_target = '<span style="position:absolute; bottom:0px; right:0px; font-size:14px; z-index:25; filter: drop-shadow(0 0 2px black); color: #FFD700;">🎯</span>'
        elif 0 in top_picks[5:10]:
             zero_target = '<span style="position:absolute; bottom:1px; right:1px; font-size:12px; z-index:20; color:#00FFFF; text-shadow: 0 0 2px black;">🔹</span>'
        
        in_spotlight_zero = zero_active or zero_hot or (0 in top_picks)
        zero_opacity = "1.0" if in_spotlight_zero else "0.3"

        zero_style += f" position: relative; overflow: visible; opacity: {zero_opacity};"

        row3 = render_row_cells([3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36], highlight_targets, grind_targets, hot_subset, colors, pinned_numbers_raw, sniper_highlight_targets)
        row2 = render_row_cells([2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35], highlight_targets, grind_targets, hot_subset, colors, pinned_numbers_raw, sniper_highlight_targets)
        row1 = render_row_cells([1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34], highlight_targets, grind_targets, hot_subset, colors, pinned_numbers_raw, sniper_highlight_targets)

        dashboard_html = f"""
        <div id="de2d-dashboard" style="margin-bottom: 20px;">
            <h3 style="color: #d32f2f; margin-bottom: 10px; border-bottom: 2px solid #d32f2f; padding-bottom: 5px;">📊 Live Trigger Status Dashboard</h3>
            {on_deck_html}
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px;">
                {status_cards_html}
            </div>
        </div>
        """

        # --- NEW: SPLIT VIEW (NEXT TOP 10 vs PINNED) ---
        # 1. Generate Top 10 Badges
        top_10_html = ""
        current_picks = state.current_top_picks
        if current_picks:
            for i, num in enumerate(current_picks[:10], 1):
                c = colors.get(str(num), "black")
                rank_color = "#FFD700" if i <= 5 else "#00BFFF" # Gold for 1-5, Blue for 6-10
                top_10_html += f"""
                <div style="display:flex; flex-direction:column; align-items:center; margin:3px;">
                    <div style="color:{rank_color}; font-size:9px; font-weight:bold;">#{i}</div>
                    <span style="display:inline-block; background-color:{c}; color:white; border:1px solid {rank_color}; width:28px; height:28px; line-height:28px; text-align:center; border-radius:50%; font-weight:bold; font-size:12px; box-shadow:0 0 5px {rank_color}40;">{num}</span>
                </div>
                """
        else:
            top_10_html = "<span style='color:#777; font-style:italic; font-size:11px;'>Waiting for analysis...</span>"

        # 2. Generate Pinned Badges
        pinned_html = ""
        # Use the persistent state we fixed in the last step
        current_pins = sorted(list(state.pinned_numbers))
        if current_pins:
            for num in current_pins:
                c = colors.get(str(num), "black")
                pinned_html += f"""
                <div style="display:flex; flex-direction:column; align-items:center; margin:3px;">
                    <div style="color:#E0B0FF; font-size:9px; font-weight:bold;">★</div>
                    <span style="display:inline-block; background-color:{c}; color:white; border:2px solid #BF00FF; width:28px; height:28px; line-height:24px; text-align:center; border-radius:50%; font-weight:bold; font-size:12px; box-shadow:0 0 8px #BF00FF;">{num}</span>
                </div>
                """
        else:
            pinned_html = "<span style='color:#777; font-style:italic; font-size:11px;'>No numbers pinned yet. Click a star on the visual table.</span>"

        split_view_html = f"""
        <div style="display: flex; flex-wrap: wrap; gap: 15px; margin-top: 15px; margin-bottom: 15px;">
            <div style="flex: 1; min-width: 300px; background: #1a252f; border: 2px solid #34495e; border-radius: 8px; padding: 10px;">
                <h4 style="color: #00BFFF; margin: 0 0 10px 0; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px solid #34495e; padding-bottom: 5px; display:flex; align-items:center; justify-content:space-between;">
                    <span>🚀 Next Top 10 Picks</span>
                    <span style="font-size:9px; color:#95a5a6; background:#2c3e50; padding:2px 6px; border-radius:4px;">AI Calculated</span>
                </h4>
                <div style="display: flex; flex-wrap: wrap; gap: 5px; justify-content: center;">
                    {top_10_html}
                </div>
            </div>

            <div style="flex: 1; min-width: 300px; background: #1a252f; border: 2px solid #BF00FF; border-radius: 8px; padding: 10px; box-shadow: 0 0 10px rgba(191, 0, 255, 0.1);">
                <h4 style="color: #E0B0FF; margin: 0 0 10px 0; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px solid #34495e; padding-bottom: 5px; display:flex; align-items:center; justify-content:space-between;">
                    <span>🎯 Pinned Strong Numbers</span>
                    <span style="font-size:9px; color:#E0B0FF; background:#2c3e50; padding:2px 6px; border-radius:4px;">User Watchlist</span>
                </h4>
                <div style="display: flex; flex-wrap: wrap; gap: 5px; justify-content: center;">
                    {pinned_html}
                </div>
            </div>
        </div>
        """

        # --- NEW: COMBINED MASTER BETTING LINE (FULL WIDTH) ---
        combined_html_content = ""
        
        # 1. Get raw lists
        raw_top_10 = state.current_top_picks[:10]
        raw_pins = list(state.pinned_numbers)
        
        # 2. Merge and Sort
        combined_set = set(raw_top_10) | set(raw_pins)
        sorted_combined = sorted(list(combined_set))
        
        # --- NEW: SMART STATS HEADER LOGIC ---
        stats_html = ""
        if sorted_combined:
            c_red = sum(1 for n in sorted_combined if n in EVEN_MONEY["Red"])
            c_black = sum(1 for n in sorted_combined if n in EVEN_MONEY["Black"])
            c_c1 = sum(1 for n in sorted_combined if n in COLUMNS["1st Column"])
            c_c2 = sum(1 for n in sorted_combined if n in COLUMNS["2nd Column"])
            c_c3 = sum(1 for n in sorted_combined if n in COLUMNS["3rd Column"])
            c_d1 = sum(1 for n in sorted_combined if n in DOZENS["1st Dozen"])
            c_d2 = sum(1 for n in sorted_combined if n in DOZENS["2nd Dozen"])
            c_d3 = sum(1 for n in sorted_combined if n in DOZENS["3rd Dozen"])
            total = len(sorted_combined)

            # Build Badges
            badges = []
            
            # Color
            if c_red > c_black and c_red/total >= 0.5: badges.append(f"<span style='color:#ff4444;'>🔥 RED ({int(c_red/total*100)}%)</span>")
            # Changed color to #FFFFFF (White) for visibility against dark background
            elif c_black > c_red and c_black/total >= 0.5: badges.append(f"<span style='color:#FFFFFF; font-weight:900;'>⚫ BLK ({int(c_black/total*100)}%)</span>")
            
            # Columns
            col_max = max(c_c1, c_c2, c_c3)
            if col_max/total >= 0.4:
                c_name = "C1" if col_max == c_c1 else "C2" if col_max == c_c2 else "C3"
                badges.append(f"<span style='color:#00BFFF;'>🏛️ {c_name} ({int(col_max/total*100)}%)</span>")

            # Dozens
            doz_max = max(c_d1, c_d2, c_d3)
            if doz_max/total >= 0.4:
                d_name = "D1" if doz_max == c_d1 else "D2" if doz_max == c_d2 else "D3"
                badges.append(f"<span style='color:#2ecc71;'>📦 {d_name} ({int(doz_max/total*100)}%)</span>")

            stats_html = " | ".join(badges)
            if not stats_html: stats_html = "<span style='color:#777;'>Balanced Distribution</span>"
        # -------------------------------------
        
        if sorted_combined:
            for num in sorted_combined:
                c = colors.get(str(num), "black")
                
                # Check overlaps for special highlighting
                is_ai = num in raw_top_10
                is_pin = num in raw_pins
                
                # Border Logic: Gold if BOTH, Blue if AI, Purple if Pin
                if is_ai and is_pin:
                    border = "3px solid #FFD700" # GOLD for SUPER STRONG
                    shadow = "0 0 10px #FFD700"
                    tag = "⚡"
                elif is_ai:
                    border = "1px solid #00BFFF"
                    shadow = "none"
                    tag = ""
                else: # is_pin
                    border = "1px solid #E0B0FF"
                    shadow = "none"
                    tag = ""

                combined_html_content += f"""
                <div style="display:flex; flex-direction:column; align-items:center; margin:2px;">
                    <div style="background-color:{c}; color:white; border:{border}; width:32px; height:32px; line-height:28px; text-align:center; border-radius:50%; font-weight:900; font-size:14px; box-shadow:{shadow}; position:relative;">
                        {num}
                        <span style="position:absolute; top:-6px; right:-6px; font-size:10px;">{tag}</span>
                    </div>
                </div>
                """
        else:
            combined_html_content = "<span style='color:#777; font-style:italic;'>No active targets.</span>"

        combined_view_html = f"""
        <div style="background: #0f172a; border: 2px solid #27ae60; border-radius: 8px; padding: 10px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.3);">
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #334155; padding-bottom:5px; margin-bottom:10px;">
                <div style="display:flex; flex-direction:column;">
                    <h4 style="color: #2ecc71; margin: 0; font-size: 14px; font-weight: 900; text-transform: uppercase; letter-spacing: 1px;">
                        🏁 MASTER BETTING LINE
                    </h4>
                    <div style="font-size:10px; font-weight:bold; margin-top:2px;">{stats_html}</div>
                </div>
                <div style="font-size:10px; color:#94a3b8; text-align:right;">
                    <span style="color:#FFD700;">⚡ = Match</span> | Count: {len(sorted_combined)}
                </div>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 6px; justify-content: center;">
                {combined_html_content}
            </div>
        </div>
        """
        
        # --- PINNED RANKS HTML (Moved Inside Logic) ---
        pinned_ranks_html = """
        <div id="hot-trend-watchlist" style="background: #0f172a; border: 2px solid #FFD700; border-radius: 8px; padding: 10px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.3);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <h4 style="color: #FFD700; margin: 0; font-family: sans-serif; font-size: 13px; font-weight: 900; text-transform: uppercase; letter-spacing: 1px;">📡 Pinned Ranks (Live Leaderboard)</h4>
                <button onclick="clearAllPins('wp_rank_pins_v3')" style="background:#ef4444; color:white; border:none; padding:3px 10px; border-radius:4px; font-size:9px; cursor:pointer; font-weight:bold;">CLEAR ALL</button>
            </div>
            <div id="pinned-container" style="display: flex; flex-wrap: wrap; gap: 10px; color: white; min-height: 45px; align-items: center;">
                <i style="color: #475569; font-size: 12px;">Star a Rank (e.g. Rank #1) below to lock it here...</i>
            </div>
        </div>
        """
        # -----------------------------------------------

        visual_table = f"""
        <style>
            /* STATIC HIGHLIGHTS FOR OUTSIDE BETS (NO PULSE) */
            .rank-top-highlight {{
                box-shadow: 0 0 10px 2px rgba(255, 215, 0, 0.6);
                border: 2px solid #FFD700 !important;
            }}
            .rank-mid-highlight {{
                box-shadow: 0 0 10px 2px rgba(0, 255, 255, 0.6);
                border: 2px solid #00FFFF !important;
            }}
            
            /* PINNED STAR GLOW (STAYING STATIC) */
            .pinned-star-glow {{
                opacity: 1;
                transform: scale(1);
            }}
            .de2d-legend {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 8px;
                margin-top: 15px;
                padding: 10px;
                background: rgba(0,0,0,0.3);
                border-radius: 8px;
                border: 1px solid #34495e;
            }}
            .legend-item {{
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 10px;
                color: #ffffff !important;
            }}
            .legend-item b {{ color: white !important; }}
            .legend-swatch {{
                width: 12px;
                height: 12px;
                border-radius: 2px;
                flex-shrink: 0;
            }}
        </style>
        <div style="margin-top: 15px; background: #1a252f; padding: 10px; border-radius: 8px; border: 2px solid #34495e;">
            <div style="display: grid; grid-template-columns: 30px 1fr 40px; grid-template-rows: repeat(3, 25px) 30px 35px; gap: 4px;">
                <div style="grid-column: 1; grid-row: 1 / 4; {zero_style} display:flex; align-items:center; justify-content:center; border-radius: 4px; font-weight: bold; writing-mode: vertical-rl; transform: rotate(180deg);">0{zero_flame}{zero_rank_badge}{zero_target}</div>
                
                <div style="grid-column: 2; grid-row: 1; display: grid; grid-template-columns: repeat(12, 1fr); gap: 2px;">{row3}</div>
                <div style="grid-column: 2; grid-row: 2; display: grid; grid-template-columns: repeat(12, 1fr); gap: 2px;">{row2}</div>
                <div style="grid-column: 2; grid-row: 3; display: grid; grid-template-columns: repeat(12, 1fr); gap: 2px;">{row1}</div>
                
                <div style="{get_label_style('3rd Column', highlight_targets, grind_targets, sector_ranks)} grid-column: 3; grid-row: 1; display:flex; align-items:center; justify-content:center; border-radius: 4px; font-size:10px;">C3</div>
                <div style="{get_label_style('2nd Column', highlight_targets, grind_targets, sector_ranks)} grid-column: 3; grid-row: 2; display:flex; align-items:center; justify-content:center; border-radius: 4px; font-size:10px;">C2</div>
                <div style="{get_label_style('1st Column', highlight_targets, grind_targets, sector_ranks)} grid-column: 3; grid-row: 3; display:flex; align-items:center; justify-content:center; border-radius: 4px; font-size:10px;">C1</div>
                
                <div style="grid-column: 2; grid-row: 4; display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 4px;">
                    <div style="{get_label_style('1st Dozen', highlight_targets, grind_targets, sector_ranks)} display:flex; align-items:center; justify-content:center; border-radius: 4px; font-size:11px;">1st 12</div>
                    <div style="{get_label_style('2nd Dozen', highlight_targets, grind_targets, sector_ranks)} display:flex; align-items:center; justify-content:center; border-radius: 4px; font-size:11px;">2nd 12</div>
                    <div style="{get_label_style('3rd Dozen', highlight_targets, grind_targets, sector_ranks)} display:flex; align-items:center; justify-content:center; border-radius: 4px; font-size:11px;">3rd 12</div>
                </div>
                
                <div style="grid-column: 2; grid-row: 5; display: grid; grid-template-columns: repeat(6, 1fr); gap: 4px;">
                    <div style="{get_label_style('Low', highlight_targets, grind_targets, sector_ranks)} display:flex; align-items:center; justify-content:center; border-radius: 4px; font-size:10px;">1-18</div>
                    <div style="{get_label_style('Even', highlight_targets, grind_targets, sector_ranks)} display:flex; align-items:center; justify-content:center; border-radius: 4px; font-size:10px;">EVEN</div>
                    <div style="{get_label_style('Red', highlight_targets, grind_targets, sector_ranks)} display:flex; align-items:center; justify-content:center; border-radius: 4px; font-size:10px; border-bottom: 3px solid #c0392b;">RED</div>
                    <div style="{get_label_style('Black', highlight_targets, grind_targets, sector_ranks)} display:flex; align-items:center; justify-content:center; border-radius: 4px; font-size:10px; border-bottom: 3px solid #000;">BLK</div>
                    <div style="{get_label_style('Odd', highlight_targets, grind_targets, sector_ranks)} display:flex; align-items:center; justify-content:center; border-radius: 4px; font-size:10px;">ODD</div>
                    <div style="{get_label_style('High', highlight_targets, grind_targets, sector_ranks)} display:flex; align-items:center; justify-content:center; border-radius: 4px; font-size:10px;">19-36</div>
                </div>
            </div>
            
            <div class="de2d-legend">
                <div class="legend-item"><span style="color:#E0B0FF; font-size:14px;">★</span> <span style="color:white !important; font-weight:bold;">Star:</span> <span style="color:white;">Pinned Pick</span></div>
                <div class="legend-item"><span style="font-size:14px;">🔥</span> <span style="color:white !important; font-weight:bold;">Flame:</span> <span style="color:white;">Hot Number</span></div>
                <div class="legend-item"><span style="color:#FFFFFF; font-size:14px;">⌖</span> <span style="color:white !important; font-weight:bold;">Cross:</span> <span style="color:white;">AI Top 1</span></div>
                <div class="legend-item"><span style="color:#FFD700; font-size:14px;">🎯</span> <span style="color:white !important; font-weight:bold;">Target:</span> <span style="color:white;">AI Top 2-5</span></div>
                <div class="legend-item"><span style="color:#00FFFF; font-size:14px;">🔹</span> <span style="color:white !important; font-weight:bold;">Diam:</span> <span style="color:white;">AI Top 6-10</span></div>
                <div class="legend-item"><span class="legend-swatch" style="border:2px solid #BF00FF; box-shadow: 0 0 5px #BF00FF;"></span> <span style="color:white !important; font-weight:bold;">Purple:</span> <span style="color:white;">Pinned Glow</span></div>
            </div>
        </div>
        """


        # --- TRIGGER GRID: 8 mini tiles, green=inactive, red=active ---
        _trigger_defs = [
            ("sniper",  "Sniper",       "🎯", status_flags.get("sniper", False)),
            ("missing", "Miss Doz/Col", "📉", status_flags.get("missing", False)),
            ("even",    "EM Drought",   "💧", status_flags.get("even", False)),
            ("streak",  "Streak Atk",   "⚡", status_flags.get("streak", False)),
            ("pattern", "Pattern X",    "🔄", status_flags.get("pattern", False)),
            ("vt",      "Voisins/Tiers","🌐", status_flags.get("voisins", False) or status_flags.get("tiers", False)),
            ("sides",   "L/R Sides",    "↔️", status_flags.get("left", False) or status_flags.get("right", False)),
            ("misc",    "DS/Cor/D17",   "🃏", status_flags.get("5ds", False) or status_flags.get("d17", False) or status_flags.get("corner", False)),
        ]
        _active_count = sum(1 for _, _, _, active in _trigger_defs if active)
        _trigger_tiles = ""
        for _key, _label, _icon, _active in _trigger_defs:
            if _active:
                _tile_style = ("background:linear-gradient(135deg,#b71c1c,#ef5350);"
                               "color:#fff; border:2px solid #ff8a80;"
                               "box-shadow:0 0 10px rgba(239,83,80,0.6);"
                               "animation:pulse-red 1.4s infinite;")
                _status_dot = '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#ff8a80;margin-right:4px;vertical-align:middle;"></span>'
                _status_txt = "ACTIVE"
            else:
                _tile_style = ("background:linear-gradient(135deg,#1b5e20,#2e7d32);"
                               "color:#c8e6c9; border:1px solid #388e3c;")
                _status_dot = '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#66bb6a;margin-right:4px;vertical-align:middle;"></span>'
                _status_txt = "OK"
            _trigger_tiles += f'''<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
                                    padding:8px 6px; border-radius:10px; min-width:80px; flex:1;
                                    {_tile_style} text-align:center; transition:all 0.3s;">
                <div style="font-size:20px;line-height:1.2;">{_icon}</div>
                <div style="font-size:10px;font-weight:900;text-transform:uppercase;letter-spacing:0.5px;margin-top:3px;">{_label}</div>
                <div style="font-size:9px;margin-top:2px;opacity:0.9;">{_status_dot}{_status_txt}</div>
            </div>'''

        _grid_html = f'''<div style="margin-bottom:16px; padding:12px; background:#1a252f;
                            border-radius:10px; border:2px solid #34495e;">
            <div style="font-size:11px;font-weight:900;color:#bdc3c7;text-transform:uppercase;
                        letter-spacing:1px;margin-bottom:10px;display:flex;align-items:center;gap:8px;">
                💀 TRIGGER STATUS
                <span style="background:{"#d32f2f" if _active_count > 0 else "#2e7d32"};color:#fff;
                             font-size:10px;padding:2px 8px;border-radius:10px;font-weight:900;">
                    {_active_count}/8 ACTIVE
                </span>
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:6px;">
                {_trigger_tiles}
            </div>
        </div>'''

        return _grid_html + config_html + spins_html + dashboard_html + actions_section + visual_table + split_view_html + combined_view_html + pinned_ranks_html + sequences_info_html
    except Exception as e:
        import traceback
        logger.error(f"Error in DE2D Tracker: {str(e)}")
        logger.error(traceback.format_exc())
        return f"<div style='padding:10px; color:red;'>Error loading DE2D tracker: {str(e)}</div>"
        
# Lines after (context, unchanged from Part 2)

