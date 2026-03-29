"""WheelPulsePro – AIDEA (AI-Driven Execution Algorithm) strategy management.

Extracted from app.py.  All functions that previously used the app-level
``state`` global now obtain the state object through :func:`init`.
"""

import json
import logging

import gradio as gr

import wheelpulsepro.rendering as _rendering
from wheelpulsepro.utils import _get_file_path
from roulette_data import DOZENS

logger = logging.getLogger("wheelPulsePro")

# ---------------------------------------------------------------------------
# Module-level state (injected via init())
# ---------------------------------------------------------------------------
_state = None


def init(state_obj):
    """Inject the shared RouletteState instance."""
    global _state
    _state = state_obj


# ---------------------------------------------------------------------------
# AIDEA helpers
# ---------------------------------------------------------------------------

def get_aidea_multiplier():
    """Helper to get the current multiplier, defaulting to 1."""
    return _state.aidea_unit_multiplier


def render_aidea_roadmap_html():
    """Thin wrapper – delegates to wheelpulsepro.rendering."""
    try:
        return _rendering.render_aidea_roadmap_html(_state, DOZENS, get_aidea_multiplier())
    except Exception as e:
        logger.error(f"render_aidea_roadmap_html error: {e}")
        empty_roadmap = "<div style='text-align:center;padding:20px;color:#ccc;'><h4>Waiting for Strategy...</h4></div>"
        empty_banner = "<div style='padding:10px;background:#333;color:#fff;border-radius:4px;text-align:center;'><b>NO ACTIVE STRATEGY</b></div>"
        return empty_roadmap, empty_banner


def process_aidea_upload(file):
    if file is None:
        return gr.update(visible=False), "", ""
    try:
        file_path = _get_file_path(file)
        if not file_path:
            return gr.update(visible=False), "Error: Unable to read uploaded file path.", ""
        with open(file_path, 'r') as f:
            data = json.load(f)
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
        for i, phase in enumerate(phases):
            if not isinstance(phase, dict) or "id" not in phase:
                return gr.update(visible=False), f"Invalid Strategy JSON: Phase {i} is missing required 'id' field.", ""
        _state.aidea_phases = phases
        _state.aidea_rules = rules
        _state.aidea_current_id = _state.aidea_phases[0]["id"]
        _state.aidea_completed_ids = set()
        roadmap_html, banner_html = render_aidea_roadmap_html()
        return gr.update(visible=True), roadmap_html, banner_html
    except json.JSONDecodeError as e:
        return gr.update(visible=False), f"Invalid JSON file: {str(e)}", ""
    except Exception as e:
        return gr.update(visible=False), f"Error parsing strategy: {str(e)}", ""


def set_aidea_multiplier(value_str):
    """Update the multiplier state based on dropdown value."""
    try:
        if "x100" in value_str: val = 100
        elif "x10" in value_str: val = 10
        else: val = 1
        _state.aidea_unit_multiplier = val
    except Exception as e:
        logger.error(f"set_aidea_multiplier error: {e}")
    return render_aidea_roadmap_html()


def reset_aidea_progress():
    try:
        if _state.aidea_phases:
            _state.aidea_current_id = _state.aidea_phases[0]["id"]
            _state.aidea_completed_ids = set()
    except Exception as e:
        logger.error(f"reset_aidea_progress error: {e}")
    return render_aidea_roadmap_html()


def nav_aidea_prev():
    """Move selection to the previous phase."""
    try:
        if not _state.aidea_phases: return render_aidea_roadmap_html()

        current_idx = 0
        for i, p in enumerate(_state.aidea_phases):
            if p['id'] == _state.aidea_current_id:
                current_idx = i
                break

        new_idx = max(0, current_idx - 1)
        _state.aidea_current_id = _state.aidea_phases[new_idx]['id']
        return render_aidea_roadmap_html()
    except Exception as e:
        logger.error(f"nav_aidea_prev error: {e}")
        return render_aidea_roadmap_html()


def nav_aidea_next():
    """Move selection to the next phase."""
    try:
        if not _state.aidea_phases: return render_aidea_roadmap_html()

        current_idx = 0
        for i, p in enumerate(_state.aidea_phases):
            if p['id'] == _state.aidea_current_id:
                current_idx = i
                break

        new_idx = min(len(_state.aidea_phases) - 1, current_idx + 1)
        _state.aidea_current_id = _state.aidea_phases[new_idx]['id']
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
        if not _state.aidea_phases or _state.aidea_current_id is None:
            return render_aidea_roadmap_html()

        pid = _state.aidea_current_id

        # --- MANUAL CLICK (Just Toggle Checkmark) ---
        if not auto_trigger:
            if pid in _state.aidea_completed_ids:
                _state.aidea_completed_ids.remove(pid)
            else:
                _state.aidea_completed_ids.add(pid)
                nav_aidea_next()
            return render_aidea_roadmap_html()

        # --- AUTO-PILOT LOGIC (STRICT JSON READER) ---
        if not auto_enabled:
            return render_aidea_roadmap_html()

        current_idx = -1
        for i, p in enumerate(_state.aidea_phases):
            if p['id'] == pid:
                current_idx = i
                break

        if current_idx == -1: return render_aidea_roadmap_html()

        total_phases = len(_state.aidea_phases)
        next_idx = current_idx

        if pid not in _state.aidea_phase_repeats:
            _state.aidea_phase_repeats[pid] = 0

        str_pid = str(pid)
        # Normalise float-formatted IDs (e.g. JS may pass "123.0") to plain integer strings.
        try:
            str_pid = str(int(float(str_pid)))
        except (ValueError, TypeError):
            pass

        phase_rules = _state.aidea_rules.get(str_pid, {})

        if result == "LOSS":
            _state.aidea_phase_repeats[pid] = 0

            rule = phase_rules.get("onLose", {"action": "next"})
            action = rule.get("action", "next")

            if action == "goto":
                target_id = rule.get("targetPhaseId")
                target_idx = next((i for i, p in enumerate(_state.aidea_phases) if p['id'] == target_id), -1)
                next_idx = target_idx if target_idx != -1 else min(current_idx + 1, total_phases - 1)
            elif action == "reset":
                next_idx = 0
            elif action == "repeat":
                next_idx = current_idx
            else:
                next_idx = min(current_idx + 1, total_phases - 1)

        elif result == "WIN":
            _state.aidea_completed_ids.add(pid)

            rule = phase_rules.get("onWin", {"action": "reset"})
            action = rule.get("action", "reset")

            if action == "repeat":
                max_repeats = rule.get("repeatCount", 1)
                if _state.aidea_phase_repeats[pid] < max_repeats:
                    _state.aidea_phase_repeats[pid] += 1
                    next_idx = current_idx
                else:
                    _state.aidea_phase_repeats[pid] = 0
                    next_idx = 0
            elif action == "goto":
                _state.aidea_phase_repeats[pid] = 0
                target_id = rule.get("targetPhaseId")
                target_idx = next((i for i, p in enumerate(_state.aidea_phases) if p['id'] == target_id), -1)
                next_idx = target_idx if target_idx != -1 else 0
            elif action == "next":
                _state.aidea_phase_repeats[pid] = 0
                next_idx = min(current_idx + 1, total_phases - 1)
            else:
                _state.aidea_phase_repeats[pid] = 0
                next_idx = 0

        if 0 <= next_idx < total_phases:
            _state.aidea_current_id = _state.aidea_phases[next_idx]['id']

        return render_aidea_roadmap_html()
    except Exception as e:
        logger.error(f"nav_aidea_toggle error: {e}")
        return render_aidea_roadmap_html()
