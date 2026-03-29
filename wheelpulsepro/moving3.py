"""Moving 3 at a Time — a phase-escalation roulette strategy for WheelPulse Pro Max.

Core concept:
  - Start with the Top-18 strongest numbers that have missed >= trigger_threshold spins.
  - Add 3 numbers per phase across 12 phases, escalating the bet multiplier each phase
    to guarantee positive recovery on a win at 36:1 payout (phases 1-9; phases 10-12
    are flagged as the Gambling / Safest zones where full recovery is not guaranteed).
  - Hybrid Lock (Option C): phases 1-3 lock all selected numbers; phase 4+ add 3 new
    dynamic numbers but keep all previously locked groups unchanged.
"""

import logging
import traceback

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase configuration (12 phases, 3 numbers added per phase)
# Multipliers for phases 1-9 are chosen so that a win at 36:1 covers all
# previous losses (recovery guarantee).  Phases 10-12 use a ×4.5 extrapolation
# and are flagged as high-risk territory.
# ---------------------------------------------------------------------------
M3_PHASE_CONFIG = [
    {"phase": 1,  "numbers": 3,  "multiplier": 1,       "label": "Entry"},
    {"phase": 2,  "numbers": 6,  "multiplier": 2,       "label": ""},
    {"phase": 3,  "numbers": 9,  "multiplier": 4,       "label": ""},
    {"phase": 4,  "numbers": 12, "multiplier": 9,       "label": ""},
    {"phase": 5,  "numbers": 15, "multiplier": 27,      "label": ""},
    {"phase": 6,  "numbers": 18, "multiplier": 108,     "label": ""},
    {"phase": 7,  "numbers": 21, "multiplier": 486,     "label": ""},
    {"phase": 8,  "numbers": 24, "multiplier": 2187,    "label": ""},
    {"phase": 9,  "numbers": 27, "multiplier": 9842,    "label": ""},
    {"phase": 10, "numbers": 30, "multiplier": 44217,   "label": "⚠️ Gambling Point"},
    {"phase": 11, "numbers": 33, "multiplier": 198975,  "label": ""},
    {"phase": 12, "numbers": 36, "multiplier": 895388,  "label": "🛡️ Safest Point"},
]

BASE_UNIT_MAP = {
    "$0.01 (1¢)": 0.01,
    "$0.10 (10¢)": 0.10,
    "$1.00 ($1)": 1.00,
}

# European roulette red numbers
_RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}


# ---------------------------------------------------------------------------
# Core strategy functions
# ---------------------------------------------------------------------------

def get_m3_triggered_numbers(state, trigger_threshold):
    """Return a sorted list of numbers from the Top 18 (state.scores) that have
    missed >= *trigger_threshold* consecutive spins.

    A number's miss count is determined by scanning *state.last_spins* from the
    end backwards and counting how many spins have elapsed since it last appeared.
    If the number has never appeared in the recorded history its miss count equals
    the total number of recorded spins.
    """
    try:
        if not getattr(state, "last_spins", None):
            return []

        # Top-18 by score (highest first)
        sorted_numbers = sorted(
            state.scores.keys(), key=lambda n: state.scores[n], reverse=True
        )
        top_18 = sorted_numbers[:18]

        # Convert spin history to ints (skip any unparseable entries)
        last_spins_int = []
        for s in state.last_spins:
            try:
                last_spins_int.append(int(s))
            except (ValueError, TypeError):
                pass

        triggered = []
        near_triggered = []  # Numbers within 2 of threshold (fallback)
        for num in top_18:
            miss_count = 0
            found = False
            for i in range(len(last_spins_int) - 1, -1, -1):
                if last_spins_int[i] == num:
                    found = True
                    break
                miss_count += 1
            if not found:
                miss_count = len(last_spins_int)
            if miss_count >= trigger_threshold:
                triggered.append(num)
            elif miss_count >= max(1, trigger_threshold - 2):
                near_triggered.append(num)

        # If strict threshold yields fewer than 3, include near-misses
        if len(triggered) < 3:
            for n in near_triggered:
                if n not in triggered:
                    triggered.append(n)
                if len(triggered) >= 3:
                    break

        return sorted(triggered)
    except Exception as e:
        logger.error(
            f"get_m3_triggered_numbers error: {str(e)}\n{traceback.format_exc()}"
        )
        return []


def m3_advance_phase(state):
    """Advance to the next phase and add 3 new numbers using hybrid lock logic.

    - Phases 1-3: all numbers selected so far are locked (never replaced).
    - Phase 4+: the 3 numbers added this phase are chosen dynamically from the
      current Top-18 miss-filtered list; all previously locked groups are kept.

    Falls back to Top-18 by score when not enough triggered numbers are available.
    """
    try:
        new_phase = state.m3_phase + 1
        if new_phase > 12:
            new_phase = 12  # cap at phase 12

        state.m3_phase = new_phase

        # Flat list of all currently covered numbers
        covered_flat = [n for grp in state.m3_locked_numbers for n in grp]

        # Candidate pool: triggered numbers not yet covered, then Top-18 fallback
        triggered = get_m3_triggered_numbers(state, state.m3_trigger_threshold)
        candidates = [n for n in triggered if n not in covered_flat]

        if len(candidates) < 3:
            all_by_score = sorted(
                state.scores.keys(),
                key=lambda x: state.scores[x],
                reverse=True,
            )
            for n in all_by_score:
                if n not in covered_flat and n not in candidates:
                    candidates.append(n)
                if len(candidates) >= 3:
                    break

        # If STILL not enough (very early session), pad with any uncovered number 0-36
        if len(candidates) < 3:
            for n in range(37):
                if n not in covered_flat and n not in candidates:
                    candidates.append(n)
                if len(candidates) >= 3:
                    break

        new_group = candidates[:3]
        if new_group:
            state.m3_locked_numbers.append(new_group)
        else:
            # Safety: revert phase increment if we couldn't add any numbers
            state.m3_phase = max(0, state.m3_phase - 1)
    except Exception as e:
        logger.error(
            f"m3_advance_phase error: {str(e)}\n{traceback.format_exc()}"
        )


def m3_check_spin(state, spin_number):
    """Process a new spin against the active M3 strategy.

    Called from *add_spin()* in app.py after the spin has been recorded.

    - WIN  (spin_number is in covered numbers): add payout, reset to phase 1.
    - LOSS (spin_number is NOT in covered numbers): deduct bet cost, advance phase.
    """
    try:
        if not getattr(state, "m3_active", False) or state.m3_phase == 0:
            return

        info = m3_get_current_bets(state)
        covered = info["covered_numbers"]
        bet_per = info["bet_per_number"]
        total_risk = info["total_risk"]

        # Always deduct the cost of this spin's bets
        state.m3_cumulative_spent += total_risk
        state.m3_session_pl -= total_risk

        if spin_number in covered:
            # WIN — straight-up roulette pays 36× (35 profit + 1 stake returned)
            payout = 36.0 * bet_per
            state.m3_session_pl += payout
            state.m3_wins += 1
            state.m3_history.append({
                "phase": state.m3_phase,
                "spin": spin_number,
                "result": "WIN",
                "payout": round(payout, 4),
                "cost": round(total_risk, 4),
                "net": round(payout - total_risk, 4),
            })
            # Reset and auto-start phase 1
            state.m3_phase = 0
            state.m3_locked_numbers = []
            m3_advance_phase(state)  # sets m3_phase = 1 and selects first 3 numbers
        else:
            # LOSS — advance to next phase (unless already at 12)
            state.m3_losses += 1
            state.m3_history.append({
                "phase": state.m3_phase,
                "spin": spin_number,
                "result": "LOSS",
                "cost": round(total_risk, 4),
                "net": round(-total_risk, 4),
            })
            if state.m3_phase < 12:
                prev_phase = state.m3_phase
                prev_groups = len(state.m3_locked_numbers)
                m3_advance_phase(state)
                # Safety: if advance failed (no new group added), revert phase
                if len(state.m3_locked_numbers) == prev_groups and state.m3_phase > prev_phase:
                    state.m3_phase = prev_phase
    except Exception as e:
        logger.error(
            f"m3_check_spin error: {str(e)}\n{traceback.format_exc()}"
        )


def m3_reset(state):
    """Reset all M3 state variables to their defaults."""
    try:
        state.m3_active = False
        state.m3_phase = 0
        state.m3_locked_numbers = []
        state.m3_trigger_threshold = 12
        state.m3_base_unit = 0.01
        state.m3_cumulative_spent = 0.0
        state.m3_session_pl = 0.0
        state.m3_wins = 0
        state.m3_losses = 0
        state.m3_history = []
    except Exception as e:
        logger.error(
            f"m3_reset error: {str(e)}\n{traceback.format_exc()}"
        )


def m3_get_current_bets(state):
    """Return a dict describing the current M3 betting position.

    Returns
    -------
    dict with keys: phase, covered_numbers, bet_per_number, total_risk,
                    multiplier, label
    """
    try:
        phase = getattr(state, "m3_phase", 0)
        if phase == 0 or phase > 12:
            return {
                "phase": 0,
                "covered_numbers": [],
                "bet_per_number": 0.0,
                "total_risk": 0.0,
                "multiplier": 0,
                "label": "",
            }

        cfg = M3_PHASE_CONFIG[phase - 1]
        multiplier = cfg["multiplier"]
        base_unit = getattr(state, "m3_base_unit", 0.01)
        bet_per_number = base_unit * multiplier
        covered = [n for grp in getattr(state, "m3_locked_numbers", []) for n in grp]
        total_risk = bet_per_number * len(covered)

        return {
            "phase": phase,
            "covered_numbers": covered,
            "bet_per_number": round(bet_per_number, 6),
            "total_risk": round(total_risk, 6),
            "multiplier": multiplier,
            "label": cfg["label"],
        }
    except Exception as e:
        logger.error(
            f"m3_get_current_bets error: {str(e)}\n{traceback.format_exc()}"
        )
        return {
            "phase": 0,
            "covered_numbers": [],
            "bet_per_number": 0.0,
            "total_risk": 0.0,
            "multiplier": 0,
            "label": "",
        }


# ---------------------------------------------------------------------------
# HTML panel renderer
# ---------------------------------------------------------------------------

def render_moving3_panel_html(state):
    """Return a dark-themed HTML string for the Moving 3 at a Time strategy panel.

    Displays:
      - Current phase with progress bar
      - Covered numbers as colour-coded badges (red/black/green)
      - Current bet per number and total exposure
      - Session P/L with green/red colouring
      - Win/Loss counters
      - Phase status indicator (Entry / Mid / Gambling Point / Safest Point)
      - Lock vs dynamic indicators (🔒 phases 1-3, 🔄 phases 4+)
    """
    try:
        phase = getattr(state, "m3_phase", 0)
        active = getattr(state, "m3_active", False)
        wins = getattr(state, "m3_wins", 0)
        losses = getattr(state, "m3_losses", 0)
        session_pl = getattr(state, "m3_session_pl", 0.0)
        locked_numbers = getattr(state, "m3_locked_numbers", [])
        base_unit = getattr(state, "m3_base_unit", 0.01)

        info = m3_get_current_bets(state)
        covered = info["covered_numbers"]
        bet_per = info["bet_per_number"]
        total_risk = info["total_risk"]
        multiplier = info["multiplier"]
        phase_label = info["label"]

        # --- Status text & colour ---
        if not active:
            status_text = "⏸ Inactive"
            status_color = "#64748b"
        elif phase == 0:
            status_text = "⏸ Waiting"
            status_color = "#64748b"
        elif "Gambling" in phase_label:
            status_text = "⚠️ High Risk"
            status_color = "#ef4444"
        elif "Safest" in phase_label:
            status_text = "🛡️ Max Coverage"
            status_color = "#22c55e"
        elif phase <= 3:
            status_text = "🔒 Lock Phase"
            status_color = "#8b5cf6"
        else:
            status_text = "🔄 Dynamic Phase"
            status_color = "#3b82f6"

        # --- P/L styling ---
        pl_color = "#22c55e" if session_pl >= 0 else "#ef4444"
        pl_sign = "+" if session_pl >= 0 else ""

        # --- Progress bar ---
        progress_pct = (phase / 12 * 100) if phase > 0 else 0
        if phase >= 10:
            progress_color = "#ef4444"
        elif phase >= 7:
            progress_color = "#f59e0b"
        else:
            progress_color = "#8b5cf6"

        # --- Number badges ---
        badges_parts = []
        for i, group in enumerate(locked_numbers):
            phase_num = i + 1
            is_lock_phase = phase_num <= 3
            badge_border = "#8b5cf6" if is_lock_phase else "#3b82f6"
            badge_bg = "rgba(139,92,246,0.15)" if is_lock_phase else "rgba(59,130,246,0.15)"
            lock_icon = "🔒" if is_lock_phase else "🔄"
            for num in group:
                if num == 0:
                    num_color = "#22c55e"
                    num_bg = "rgba(34,197,94,0.2)"
                elif num in _RED_NUMBERS:
                    num_color = "#ef4444"
                    num_bg = "rgba(239,68,68,0.2)"
                else:
                    num_color = "#e2e8f0"
                    num_bg = "rgba(30,27,75,0.5)"
                badges_parts.append(
                    f'<span title="Phase {phase_num} {lock_icon}" style="'
                    f'display:inline-block;margin:2px;padding:4px 8px;'
                    f'background:{num_bg};border:1px solid {badge_border};'
                    f'border-radius:6px;color:{num_color};font-weight:bold;'
                    f'font-size:13px;cursor:default;">{num}</span>'
                )

        badges_html = (
            "".join(badges_parts)
            if badges_parts
            else '<span style="color:#64748b;font-style:italic;">No numbers selected yet</span>'
        )

        # --- Phase info line ---
        if phase > 0:
            phase_info = f"Phase {phase}/12"
            if phase_label:
                phase_info += f" — {phase_label}"
            mult_display = f"&times;{multiplier:,}"
            bet_display = f"${bet_per:.4f}/number"
            risk_display = f"${total_risk:.4f} total"
        else:
            phase_info = "Not started"
            mult_display = "&mdash;"
            bet_display = "&mdash;"
            risk_display = "&mdash;"

        html = f"""<div style="background:linear-gradient(160deg,#0f172a,#1e1b4b);
     border:2px solid #7c3aed;border-radius:12px;padding:16px;
     font-family:Arial,sans-serif;color:#e2e8f0;">
  <!-- Header row -->
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
    <div style="font-size:15px;font-weight:bold;color:#FFD700;">Moving 3 at a Time 🎯</div>
    <div style="padding:3px 10px;border-radius:20px;background:rgba(0,0,0,0.3);
         border:1px solid {status_color};color:{status_color};font-size:12px;">{status_text}</div>
  </div>
  <!-- Phase progress bar -->
  <div style="margin-bottom:12px;">
    <div style="display:flex;justify-content:space-between;font-size:12px;color:#94a3b8;margin-bottom:4px;">
      <span>{phase_info}</span>
      <span style="color:{progress_color};">{progress_pct:.0f}%</span>
    </div>
    <div style="background:#1e293b;border-radius:4px;height:8px;overflow:hidden;">
      <div style="width:{progress_pct}%;height:100%;background:{progress_color};
           border-radius:4px;"></div>
    </div>
  </div>
  <!-- Bet info grid -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;">
    <div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:8px;text-align:center;">
      <div style="font-size:11px;color:#94a3b8;">Multiplier</div>
      <div style="font-size:16px;font-weight:bold;color:#FFD700;">{mult_display}</div>
    </div>
    <div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:8px;text-align:center;">
      <div style="font-size:11px;color:#94a3b8;">Bet / Number</div>
      <div style="font-size:13px;font-weight:bold;color:#e2e8f0;">{bet_display}</div>
    </div>
    <div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:8px;text-align:center;">
      <div style="font-size:11px;color:#94a3b8;">Total Risk</div>
      <div style="font-size:13px;font-weight:bold;color:#f59e0b;">{risk_display}</div>
    </div>
    <div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:8px;text-align:center;">
      <div style="font-size:11px;color:#94a3b8;">Base Unit</div>
      <div style="font-size:13px;font-weight:bold;color:#e2e8f0;">${base_unit:.2f}</div>
    </div>
  </div>
  <!-- Covered numbers -->
  <div style="margin-bottom:12px;">
    <div style="font-size:12px;color:#94a3b8;margin-bottom:6px;">
      Covered Numbers ({len(covered)})
      &nbsp;<span style="color:#8b5cf6;">🔒 locked</span>
      &nbsp;<span style="color:#3b82f6;">🔄 dynamic</span>
    </div>
    <div style="background:rgba(0,0,0,0.2);border-radius:8px;padding:8px;min-height:40px;
         line-height:1.8;">{badges_html}</div>
  </div>
  <!-- Session stats -->
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;">
    <div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:6px;text-align:center;">
      <div style="font-size:11px;color:#94a3b8;">Session P/L</div>
      <div style="font-size:14px;font-weight:bold;color:{pl_color};">
        {pl_sign}${abs(session_pl):.2f}
      </div>
    </div>
    <div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:6px;text-align:center;">
      <div style="font-size:11px;color:#94a3b8;">Wins</div>
      <div style="font-size:16px;font-weight:bold;color:#22c55e;">{wins}</div>
    </div>
    <div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:6px;text-align:center;">
      <div style="font-size:11px;color:#94a3b8;">Losses</div>
      <div style="font-size:16px;font-weight:bold;color:#ef4444;">{losses}</div>
    </div>
  </div>
</div>"""
        return html
    except Exception as e:
        logger.error(
            f"render_moving3_panel_html error: {str(e)}\n{traceback.format_exc()}"
        )
        return '<div style="color:#ef4444;padding:10px;">Error rendering M3 panel</div>'
