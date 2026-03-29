"""WheelPulsePro – Labouchere session management.

Extracted from app.py.
"""

import logging

import wheelpulsepro.rendering as _rendering

logger = logging.getLogger("wheelPulsePro")

_state = None


def init(state_obj):
    """Inject the shared RouletteState instance."""
    global _state
    _state = state_obj


def generate_labouchere_html():
    """Thin wrapper – delegates to wheelpulsepro.rendering."""
    try:
        return _rendering.generate_labouchere_html(_state)
    except Exception as e:
        logger.error(f"generate_labouchere_html error: {e}")
        return "<div style='padding:10px;color:#ef4444;'>⚠️ Error rendering Labouchere view.</div>"


def start_lab_session(base, target, mode, split_limit):
    try:
        base = float(base)
    except (TypeError, ValueError):
        base = 1.0
    try:
        target = float(target)
    except (TypeError, ValueError):
        target = 1.0

    # FIX: Prevent floating-point inaccuracies
    division_result = round(target / base, 6)
    count = int(division_result)
    rem = round(target - (count * base), 2)

    seq = [base] * count
    if rem > 0:
        seq.append(rem)

    _state.lab_sequence = seq
    _state.lab_active = True
    _state.lab_base = base
    _state.lab_target = target
    _state.lab_mode = mode
    try:
        _state.lab_split_limit = float(split_limit)
    except (TypeError, ValueError):
        _state.lab_split_limit = 0.0
    _state.lab_bankroll = 0.0
    _state.lab_status = "ACTIVE"
    _state.strategy_lab_enabled = True
    return generate_labouchere_html()


def reset_lab_session(mode):
    _state.lab_active = False
    _state.lab_sequence = []
    _state.lab_status = "Waiting to Start"
    _state.lab_mode = mode
    _state.lab_split_limit = 0.0
    _state.lab_bankroll = 0.0
    _state.strategy_lab_enabled = False
    return generate_labouchere_html()
