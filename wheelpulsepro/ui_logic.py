"""WheelPulsePro – UI/_state helper functions.

Extracted from app.py.  All functions that previously used the app-level
``_state`` global and other app-level globals now obtain them through
:func:`init`.
"""

import logging
import time
import traceback

import gradio as gr

from roulette_data import CORNERS, STREETS
from wheelpulsepro.persistence import autosave
from wheelpulsepro.spins import MAX_SPINS, parse_spins_input, validate_spins

logger = logging.getLogger("wheelPulsePro.ui_logic")

# ---------------------------------------------------------------------------
# Module-level injected globals (set by init())
# ---------------------------------------------------------------------------
_state = None
_update_scores_batch_fn = None   # callable: update_scores_batch(spins)
_update_drought_fn = None        # callable: _update_drought_counters()
_format_spins_fn = None          # callable: format_spins_as_html(spins, num, show_trends)
_render_sides_fn = None          # callable: render_sides_of_zero_display()
_resolve_lab_targets_fn = None   # callable: _resolve_lab_targets()
_strategy_categories: dict = {}  # strategy_categories dict from app.py


def init(
    state_obj,
    update_scores_batch_fn,
    update_drought_fn,
    format_spins_fn,
    render_sides_fn,
    resolve_lab_targets_fn,
    strategy_categories_dict,
) -> None:
    """Inject all shared dependencies from app.py."""
    global _state, _update_scores_batch_fn, _update_drought_fn
    global _format_spins_fn, _render_sides_fn, _resolve_lab_targets_fn
    global _strategy_categories
    _state = state_obj
    _update_scores_batch_fn = update_scores_batch_fn
    _update_drought_fn = update_drought_fn
    _format_spins_fn = format_spins_fn
    _render_sides_fn = render_sides_fn
    _resolve_lab_targets_fn = resolve_lab_targets_fn
    _strategy_categories = strategy_categories_dict


# ---------------------------------------------------------------------------
# Migrated functions (bodies preserved from app.py, globals replaced)
# ---------------------------------------------------------------------------

def validate_spins_input(spins_input):
    """Validate manually entered spins and update _state."""
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

        # Update _state and scores
        _state.last_spins = valid_spins
        _state.selected_numbers = set(int(s) for s in valid_spins)
        action_log = _update_scores_batch_fn(valid_spins)
        for i, spin in enumerate(valid_spins):
            _state.spin_history.append(action_log[i])
            if len(_state.spin_history) > 100:
                _state.spin_history.pop(0)
        _update_drought_fn()

        spins_display_value = ", ".join(valid_spins)
        formatted_html = _format_spins_fn(spins_display_value, 36)

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
        safe_spins = ", ".join(str(s) for s in _state.last_spins) if _state.last_spins else (spins_input or "")
        return safe_spins, f"<h4>Last Spins</h4><p>⚠️ Error processing input — please try again.</p>"


def add_spin(number, current_spins, num_to_show):
    start_time = time.time()

    logger.debug(f"add_spin: Processing number='{number}', current_spins='{current_spins}', num_to_show={num_to_show}")
    try:
        numbers = [n.strip() for n in number.split(",") if n.strip()]
        unique_numbers = list(dict.fromkeys(numbers))
        
        if not unique_numbers:
            gr.Warning("No valid input provided. Please enter numbers between 0 and 36.")
            logger.debug("add_spin: No valid numbers provided.")
            return current_spins, current_spins, "<h4>Last Spins</h4><p>Error: No valid numbers provided.</p>", update_spin_counter(), _render_sides_fn()
        
        current_spins_list = current_spins.split(", ") if current_spins and current_spins.strip() else []
        if current_spins_list == [""]:
            current_spins_list = []
        
        new_spins = current_spins_list + unique_numbers
        new_spins_str = ", ".join(new_spins)

        # CHANGED: Directly update the _state history here so the counter reads the exact total before the UI updates.
        # Removed the destructive validate_spins_input call that was wiping out the history array.
        _state.last_spins = new_spins

        # --- NEW: Auto-Pilot Logic (The "Brain") ---
        # Prioritize AIDEA JSON targets if a sequence is loaded
        if _state.aidea_phases and _state.aidea_active_targets:
            eval_targets = _state.aidea_active_targets
        else:
            eval_targets = _state.active_strategy_targets

        # --- SNIPER HARDCODE OVERRIDE (Hottest Street/Corner) ---
        if getattr(_state, 'sniper_locked', False):
            current_idx = next((i for i, p in enumerate(getattr(_state, 'aidea_phases', [])) if p['id'] == getattr(_state, 'aidea_current_id', None)), 0)
            phase_num = current_idx + 1
            # Use hottest street/corner from current scores
            street_active = {k: v for k, v in _state.street_scores.items() if v > 0}
            corner_active = {k: v for k, v in _state.corner_scores.items() if v > 0}
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
                    _state.aidea_last_result = "WIN"
                    coverage = len(eval_targets)
                    multiplier = (36 / coverage) - 1 if coverage > 0 else 0
                    _state.aidea_bankroll += multiplier 
                else:
                    _state.aidea_last_result = "LOSS"
                    _state.aidea_bankroll -= 1 
                    
                logger.debug(f"AUTO-PILOT: Spin {latest_spin_int} vs Targets {eval_targets} -> {_state.aidea_last_result}")

        # --- LABOUCHERE SEQUENCE TRACKER INTEGRATION ---
        # Runs independently of eval_targets so the sequence updates on every spin.
        # Targets are resolved from pre-spin scores (correct betting behaviour —
        # you decide what to back before the wheel spins).
        if _state.lab_active and _state.lab_sequence and unique_numbers:
            try:
                lab_spin_int = int(unique_numbers[-1])
            except (ValueError, TypeError):
                lab_spin_int = None

            if lab_spin_int is not None:
                bet_calc = (_state.lab_sequence[0] + _state.lab_sequence[-1]
                            if len(_state.lab_sequence) > 1 else _state.lab_sequence[0])

                is_single_target = "1 Target" in _state.lab_mode
                total_risk = bet_calc if is_single_target else bet_calc * 2
                profit_on_win = bet_calc

                # Resolve which numbers count as a win for this spin.
                # Prefer active strategy targets; fall back to score-based resolution.
                lab_targets = (_state.active_strategy_targets
                               if _state.active_strategy_targets
                               else _resolve_lab_targets_fn())

                if lab_targets and lab_spin_int in lab_targets:
                    # WIN — cancel first and last elements of the sequence.
                    _state.lab_bankroll += profit_on_win
                    _state.lab_sequence = (_state.lab_sequence[1:-1]
                                          if len(_state.lab_sequence) >= 2 else [])
                    if not _state.lab_sequence:
                        _state.lab_status = "Complete: Profit Secured!"
                        _state.lab_active = False
                else:
                    # LOSS — append the risk to the sequence.
                    _state.lab_bankroll -= total_risk
                    if _state.lab_split_limit > 0 and total_risk >= _state.lab_split_limit:
                        half1 = round(total_risk / 2.0, 2)
                        half2 = round(total_risk - half1, 2)
                        _state.lab_sequence.extend([half1, half2])
                    else:
                        _state.lab_sequence.append(total_risk)
        # -----------------------------------------------
        if len(unique_numbers) < len(numbers):
            duplicates = [n for n in numbers if numbers.count(n) > 1]
            logger.debug(f"add_spin: Removed duplicates: {', '.join(set(duplicates))}")
        
        logger.debug(f"add_spin: Added {len(unique_numbers)} spins, new_spins_str='{new_spins_str}', time={time.time() - start_time:.3f}s")
        
        _update_drought_fn()
        formatted_html = _format_spins_fn(new_spins_str, num_to_show)
        autosave(_state)
        return new_spins_str, new_spins_str, formatted_html, update_spin_counter(), _render_sides_fn()

    except Exception as e:
        logger.error(
            f"add_spin: Unexpected error: {str(e)}\n{traceback.format_exc()}"
        )
        gr.Warning(
            f"⚠️ Spin processing error (spins preserved): "
            f"{type(e).__name__}: {str(e)}"
        )
        # Return last known _state so the user can continue entering spins
        safe_spins_str = ", ".join(str(s) for s in _state.last_spins) if _state.last_spins else (current_spins or "")
        try:
            safe_html = _format_spins_fn(safe_spins_str, num_to_show)
        except Exception:
            logger.error(f"add_spin: Failed to render fallback spins HTML\n{traceback.format_exc()}")
            safe_html = "<h4>Last Spins</h4><p>⚠️ Error rendering spins — please enter another spin.</p>"
        return safe_spins_str, safe_spins_str, safe_html, update_spin_counter(), _render_sides_fn()


def _sync_strategy_flags_from_hud_filters(hud_filters):
    """Sync strategy_enabled _state flags from HUD visibility filter selections.

    Called whenever the hud_visibility_filters CheckboxGroup changes so that
    _render_final_brain_html_inner can gate Active Strategy Cards correctly.
    """
    try:
        filters = hud_filters or []
        _state.strategy_sniper_enabled = "Sniper Strike" in filters
        _state.strategy_trinity_enabled = "Cold Trinity" in filters
        _state.strategy_nr_enabled = "Non-Repeaters" in filters
        _state.strategy_ramp_enabled = "Ramp/Grind/X-19" in filters
        _state.strategy_grind_enabled = "Ramp/Grind/X-19" in filters
        # Labouchere is controlled by starting a Lab session, not the HUD filter
    except Exception as e:
        logger.error(f"_sync_strategy_flags_from_hud_filters error: {e}")


def reset_scores():
    _state.reset()
    return "Scores reset!"


def clear_all():
    _state.selected_numbers.clear()
    _state.last_spins = []
    
    # Hard reset Labouchere & AIDEA memory safely
    _state.lab_active = False
    _state.lab_sequence = []
    _state.lab_status = "Waiting to Start"
    _state.lab_bankroll = 0.0
    _state.aidea_bankroll = 0.0
    _state.aidea_last_result = None
    _state.aidea_phase_repeats = {}
    
    _state.sniper_locked = False
    _state.sniper_locked_misses = 0
    
    # --- Reset Non-Repeater Memory ---
    _state.current_non_repeaters.clear()
    _state.previous_non_repeaters.clear()
    _state.nr_last_spin_count = 0
    if hasattr(_state, 'nr_mem_in'): _state.nr_mem_in = []
    if hasattr(_state, 'nr_mem_out'): _state.nr_mem_out = []
    if hasattr(_state, 'nr_mem_spin_in'): _state.nr_mem_spin_in = 0
    if hasattr(_state, 'nr_mem_spin_out'): _state.nr_mem_spin_out = 0
    
    _state.reset()
    ts = int(time.time() * 1000)
    js_clear = f'<script id="pin-clear-{ts}">localStorage.setItem("wp_rank_pins_v3","[]"); localStorage.setItem("wp_num_pins_v3","[]"); if(typeof fastUpdateWatchlist==="function") fastUpdateWatchlist();</script>'
    return "", "", "All spins and scores cleared successfully!", "<h4>Last Spins</h4><p>No spins yet.</p>", "", "", "", "", "", "", "", "", "", "", "", update_spin_counter(), _render_sides_fn(), js_clear


def master_reset():
    """Full app reset — clears spins, scores, pins, Labouchere, AIDEA, and all watchlists."""
    _state.selected_numbers.clear()
    _state.last_spins = []
    _state.spin_history = []
    _state.side_scores = {"Left Side of Zero": 0, "Right Side of Zero": 0}
    _state.scores = {n: 0 for n in range(37)}
    _state.pinned_numbers = set()
    _state.analysis_cache = {}
    _state.current_top_picks = []
    _state.previous_top_picks = []
    _state.stability_counter = 0

    # Reset Labouchere
    _state.lab_active = False
    _state.lab_sequence = []
    _state.lab_status = "Waiting to Start"
    _state.lab_bankroll = 0.0

    # Reset AIDEA
    _state.aidea_bankroll = 0.0
    _state.aidea_last_result = None
    _state.aidea_phase_repeats = {}
    _state.aidea_phases = []
    _state.aidea_rules = {}
    _state.aidea_current_id = None
    _state.aidea_completed_ids = set()
    _state.aidea_active_targets = []
    _state.active_strategy_targets = []

    # Reset Sniper & D17
    _state.sniper_locked = False
    _state.sniper_locked_misses = 0
    _state.d17_list = []
    _state.d17_locked = False

    # Reset Grind/Ramp
    _state.grind_step_index = 0
    _state.grind_last_spin_count = 0
    _state.ramp_step_index = 0
    _state.ramp_last_spin_count = 0
    
    # --- Reset Non-Repeater Memory ---
    _state.current_non_repeaters.clear()
    _state.previous_non_repeaters.clear()
    _state.nr_last_spin_count = 0
    if hasattr(_state, 'nr_mem_in'): _state.nr_mem_in = []
    if hasattr(_state, 'nr_mem_out'): _state.nr_mem_out = []
    if hasattr(_state, 'nr_mem_spin_in'): _state.nr_mem_spin_in = 0
    if hasattr(_state, 'nr_mem_spin_out'): _state.nr_mem_spin_out = 0

    _state.reset()

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
        _render_sides_fn(),                                  # sides_of_zero_display
        js_full_reset                                                    # js trigger
    )


def reset_strategy_dropdowns():
    default_category = "Even Money Strategies"
    default_strategy = "Best Even Money Bets"
    strategy_choices = _strategy_categories[default_category]
    return default_category, default_strategy, strategy_choices


def update_spin_counter():
    """Update the spin counter HTML with total spins and phase indicator."""
    try:
        current_list = getattr(_state, 'last_spins', [])
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
    """Passthrough to sync spins display _state after hot/cold play."""
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
    _state.casino_data[f"{type_label.lower()}_numbers"] = []
    success_msg = f"Cleared {type_label} Picks successfully"
    logger.debug(f"clear_hot_cold_picks: {success_msg}")
    return "", success_msg, update_spin_counter(), _render_sides_fn(), current_spins_display
