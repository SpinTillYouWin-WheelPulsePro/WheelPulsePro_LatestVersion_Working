"""Tests for the Slider Auto-Nudge / Bet Sizing Discipline helpers.

These tests are self-contained: the pure helper functions are defined locally
so that the test suite runs without Gradio (which app.py imports at module
level and which is not installed in the test environment).

The local copies mirror the exact logic committed in app.py; any change to the
helper logic there should be reflected here.
"""

import pytest


# ---------------------------------------------------------------------------
# Local copies of the helper functions (no Gradio / no app.py import needed)
# These must stay in sync with the implementations in app.py.
# ---------------------------------------------------------------------------

# Minimal _DE2D_SLIDER_CFG subset (indices 0-10 used by helpers)
_DE2D_SLIDER_CFG = [
    (14,  2, 20),   # [0]  miss
    ( 8,  4, 30),   # [1]  even
    ( 9,  2, 10),   # [2]  streak
    ( 6,  3,  8),   # [3]  pattern (unused by nudge)
    (10,  3, 15),   # [4]  voisins
    ( 9,  2, 15),   # [5]  tiers
    ( 8,  2, 12),   # [6]  left
    ( 8,  2, 12),   # [7]  right
    ( 8,  1, 10),   # [8]  ds
    ( 9,  3, 15),   # [9]  d17
    ( 9,  1, 15),   # [10] corner
]

_nudge_state: dict = {
    "mode": "MANUAL",
    "overrides": {},
    "cooldown": {},
    "cooldown_spins": 5,
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


def _clamp(val, min_val, max_val):
    return max(min_val, min(max_val, val))


def _coerce_int(val, default):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _safe_slider_val(val, cfg_index):
    default, min_val, max_val = _DE2D_SLIDER_CFG[cfg_index]
    return _clamp(_coerce_int(val, default), min_val, max_val)


def _compute_recommendation_tier(miss_val, threshold):
    try:
        ratio = miss_val / threshold if threshold > 0 else 1.0
    except (TypeError, ZeroDivisionError):
        return "HOLD", "$0.10", "#f59e0b", "data unavailable, hold & monitor"
    if ratio >= 1.5:
        return "PROTECT", "$0.01", "#ef4444", f"deep drought ({miss_val}/{threshold}), protect unit"
    if ratio >= 1.0:
        return "HOLD", "$0.10", "#f59e0b", f"at threshold ({miss_val}/{threshold}), hold & monitor"
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
    targets = []
    try:
        if status_flags.get("missing"):
            section = worst_section_name or "N/A"
            label = f"Missing {section}"
            targets.append({"name": label, "miss": worst_section_miss_val,
                            "threshold": miss_wait, "cfg_idx": 0})
        if status_flags.get("even"):
            targets.append({"name": worst_even_name or "Even Money",
                            "miss": worst_even_miss_val, "threshold": even_wait, "cfg_idx": 1})
        if status_flags.get("streak"):
            targets.append({"name": f"Streak Attack ({best_streak_name})",
                            "miss": best_streak_val, "threshold": streak_wait, "cfg_idx": 2})
        if status_flags.get("voisins"):
            targets.append({"name": "Voisins du Zéro", "miss": curr_voisins_miss,
                            "threshold": voisins_wait, "cfg_idx": 4})
        if status_flags.get("tiers"):
            targets.append({"name": "Tiers du Cylindre", "miss": curr_tiers_miss,
                            "threshold": tiers_wait, "cfg_idx": 5})
        if status_flags.get("left"):
            targets.append({"name": "Left of Zero", "miss": curr_left_miss,
                            "threshold": left_wait, "cfg_idx": 6})
        if status_flags.get("right"):
            targets.append({"name": "Right of Zero", "miss": curr_right_miss,
                            "threshold": right_wait, "cfg_idx": 7})
        if status_flags.get("5ds"):
            targets.append({"name": f"Double Street {best_ds_name}", "miss": best_ds_streak,
                            "threshold": ds_wait, "cfg_idx": 8})
        if status_flags.get("d17") and d17_locked:
            targets.append({"name": "Dynamic 17 Assault", "miss": d17_miss_count,
                            "threshold": d17_wait, "cfg_idx": 9})
        if status_flags.get("corner") and best_corner_template:
            targets.append({"name": f"Corner Shuffle ({best_corner_template[0]})",
                            "miss": max_corner_miss, "threshold": corner_wait, "cfg_idx": 10})
    except Exception:
        pass
    return targets


def _auto_nudge_apply(status_flags, current_spin_count, state=None):
    """Local test copy of _auto_nudge_apply using module-level _nudge_state."""
    try:
        if _nudge_state.get("mode") != "AUTO":
            return
        cooldown = _nudge_state.setdefault("cooldown", {})
        overrides = _nudge_state.setdefault("overrides", {})
        cooldown_spins = int(_nudge_state.get("cooldown_spins", 5))
        nudge_log = _nudge_state.setdefault("nudge_log", [])
        _FLAG_CFG_MAP = {
            "missing": 0, "even": 1, "streak": 2,
            "voisins": 4, "tiers": 5, "left": 6, "right": 7,
            "5ds": 8, "d17": 9, "corner": 10,
        }
        for flag, cfg_idx in _FLAG_CFG_MAP.items():
            last_adj = cooldown.get(cfg_idx, -(cooldown_spins + 1))
            if current_spin_count - last_adj < cooldown_spins:
                continue
            cfg = _DE2D_SLIDER_CFG[cfg_idx]
            cur_val = overrides.get(cfg_idx, cfg[0])
            is_active = bool(status_flags.get(flag))
            if is_active:
                new_val = max(cfg[1], cur_val - 1)
                reason = f"Active trigger: {_NUDGE_SLIDER_NAMES.get(cfg_idx, flag)}"
            else:
                default_val = cfg[0]
                if cur_val < default_val:
                    new_val = min(cfg[2], cur_val + 1)
                    reason = "No longer active; relaxing toward default"
                else:
                    continue
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
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blank_status_flags():
    return {
        "missing": False, "even": False, "streak": False, "pattern": False,
        "voisins": False, "tiers": False, "left": False, "right": False,
        "5ds": False, "d17": False, "corner": False, "overheated": False,
    }


def _reset_nudge_state():
    _nudge_state["mode"] = "MANUAL"
    _nudge_state["overrides"] = {}
    _nudge_state["cooldown"] = {}
    _nudge_state["cooldown_spins"] = 5
    _nudge_state["nudge_log"] = []


# ---------------------------------------------------------------------------
# 1–2.  _compute_recommendation_tier
# ---------------------------------------------------------------------------

class TestComputeRecommendationTier:
    def test_protect_tier_at_1_5x(self):
        tier, bet, color, reason = _compute_recommendation_tier(15, 10)
        assert tier == "PROTECT"
        assert bet == "$0.01"
        assert "#ef4444" in color

    def test_protect_tier_above_1_5x(self):
        tier, bet, _, _ = _compute_recommendation_tier(20, 10)
        assert tier == "PROTECT"
        assert bet == "$0.01"

    def test_hold_tier_at_1_0x(self):
        tier, bet, color, reason = _compute_recommendation_tier(10, 10)
        assert tier == "HOLD"
        assert bet == "$0.10"
        assert "#f59e0b" in color

    def test_hold_tier_just_above_1_0x(self):
        tier, bet, _, _ = _compute_recommendation_tier(11, 10)
        assert tier == "HOLD"
        assert bet == "$0.10"

    def test_opportunity_below_threshold(self):
        tier, bet, color, _ = _compute_recommendation_tier(5, 10)
        assert tier == "OPPORTUNITY"
        assert bet == "$1.00"
        assert "#22c55e" in color

    def test_zero_threshold_returns_hold(self):
        """Zero threshold → ratio defaults to 1.0 → HOLD tier."""
        tier, bet, _, _ = _compute_recommendation_tier(5, 0)
        assert tier == "HOLD"
        assert bet == "$0.10"

    def test_none_values_return_hold(self):
        tier, bet, _, _ = _compute_recommendation_tier(None, None)
        assert tier == "HOLD"
        assert bet == "$0.10"

    def test_reason_contains_miss_and_threshold(self):
        _, _, _, reason = _compute_recommendation_tier(12, 10)
        assert "12" in reason and "10" in reason


# ---------------------------------------------------------------------------
# 3–5.  _render_nudge_recommendations_html
# ---------------------------------------------------------------------------

class TestRenderNudgeRecommendationsHtml:
    def _sample_targets(self):
        return [
            {"name": "Missing 2nd Dozen", "miss": 15, "threshold": 10, "cfg_idx": 0},
            {"name": "Voisins du Zéro", "miss": 12, "threshold": 10, "cfg_idx": 4},
        ]

    def test_manual_returns_empty_string(self):
        assert _render_nudge_recommendations_html(self._sample_targets(), "MANUAL") == ""

    def test_suggest_returns_nonempty_html(self):
        result = _render_nudge_recommendations_html(self._sample_targets(), "SUGGEST")
        assert isinstance(result, str) and len(result) > 0

    def test_suggest_badge_color(self):
        result = _render_nudge_recommendations_html(self._sample_targets(), "SUGGEST")
        assert "06b6d4" in result  # cyan badge

    def test_auto_badge_color(self):
        result = _render_nudge_recommendations_html(self._sample_targets(), "AUTO")
        assert "8b5cf6" in result  # purple badge

    def test_empty_targets_returns_empty(self):
        assert _render_nudge_recommendations_html([], "SUGGEST") == ""

    def test_target_name_appears_in_html(self):
        targets = [{"name": "Missing 2nd Dozen", "miss": 15, "threshold": 10, "cfg_idx": 0}]
        result = _render_nudge_recommendations_html(targets, "SUGGEST")
        assert "Missing 2nd Dozen" in result

    def test_no_crash_on_malformed_target(self):
        bad = [{"name": "Bad"}, {}, {"miss": "x", "threshold": None}]
        result = _render_nudge_recommendations_html(bad, "SUGGEST")
        assert isinstance(result, str)

    def test_protect_tier_shown_for_extreme_drought(self):
        targets = [{"name": "Test", "miss": 20, "threshold": 10, "cfg_idx": 0}]
        result = _render_nudge_recommendations_html(targets, "SUGGEST")
        assert "PROTECT" in result

    def test_hold_tier_shown_at_threshold(self):
        targets = [{"name": "Test", "miss": 10, "threshold": 10, "cfg_idx": 0}]
        result = _render_nudge_recommendations_html(targets, "SUGGEST")
        assert "HOLD" in result


# ---------------------------------------------------------------------------
# 6.  _get_active_de2d_targets_from_flags
# ---------------------------------------------------------------------------

class TestGetActiveDE2DTargetsFromFlags:
    def _call(self, flags, **kwargs):
        defaults = dict(
            worst_section_name="2nd Dozen", worst_section_miss_val=15, miss_wait=10,
            worst_even_name="Red", worst_even_miss_val=10, even_wait=8,
            best_streak_name="1st Dozen", best_streak_val=10, streak_wait=9,
            curr_voisins_miss=11, voisins_wait=10,
            curr_tiers_miss=10, tiers_wait=9,
            curr_left_miss=9, left_wait=8,
            curr_right_miss=9, right_wait=8,
            best_ds_name="DS 1-6", best_ds_streak=9, ds_wait=8,
            d17_miss_count=10, d17_wait=9, d17_locked=True,
            max_corner_miss=10, corner_wait=9,
            best_corner_template=("Standard", {1, 2, 4, 5}),
        )
        defaults.update(kwargs)
        return _get_active_de2d_targets_from_flags(flags, **defaults)

    def test_no_flags_returns_empty(self):
        assert self._call(_blank_status_flags()) == []

    def test_missing_flag_includes_section_name(self):
        flags = _blank_status_flags(); flags["missing"] = True
        result = self._call(flags)
        assert len(result) == 1
        assert "2nd Dozen" in result[0]["name"]

    def test_voisins_uses_full_name(self):
        flags = _blank_status_flags(); flags["voisins"] = True
        result = self._call(flags)
        assert any("Voisins" in t["name"] for t in result)

    def test_tiers_uses_full_name(self):
        flags = _blank_status_flags(); flags["tiers"] = True
        result = self._call(flags)
        assert any("Tiers" in t["name"] for t in result)

    def test_left_uses_full_name(self):
        flags = _blank_status_flags(); flags["left"] = True
        result = self._call(flags)
        assert any("Left of Zero" in t["name"] for t in result)

    def test_right_uses_full_name(self):
        flags = _blank_status_flags(); flags["right"] = True
        result = self._call(flags)
        assert any("Right of Zero" in t["name"] for t in result)

    def test_multiple_flags(self):
        flags = _blank_status_flags()
        flags["missing"] = flags["even"] = flags["voisins"] = True
        assert len(self._call(flags)) == 3

    def test_d17_requires_d17_locked(self):
        flags = _blank_status_flags(); flags["d17"] = True
        assert len(self._call(flags, d17_locked=True)) == 1
        assert len(self._call(flags, d17_locked=False)) == 0

    def test_target_dict_has_required_keys(self):
        flags = _blank_status_flags(); flags["missing"] = True
        t = self._call(flags)[0]
        for key in ("name", "miss", "threshold", "cfg_idx"):
            assert key in t

    def test_corner_requires_best_corner_template(self):
        flags = _blank_status_flags(); flags["corner"] = True
        assert len(self._call(flags, best_corner_template=None)) == 0
        assert len(self._call(flags, best_corner_template=("Standard", {1, 2}))) == 1


# ---------------------------------------------------------------------------
# 7–9.  _auto_nudge_apply
# ---------------------------------------------------------------------------

class TestAutoNudgeApply:
    def setup_method(self):
        _reset_nudge_state()

    def teardown_method(self):
        _reset_nudge_state()

    def test_manual_mode_no_change(self):
        _nudge_state["mode"] = "MANUAL"
        _auto_nudge_apply(_blank_status_flags(), 100)
        assert _nudge_state["overrides"] == {}

    def test_auto_lowers_threshold_for_active_flag(self):
        _nudge_state["mode"] = "AUTO"
        default_val = _DE2D_SLIDER_CFG[0][0]  # 14 for missing
        flags = _blank_status_flags(); flags["missing"] = True
        _auto_nudge_apply(flags, 100)
        assert _nudge_state["overrides"].get(0, default_val) < default_val

    def test_auto_respects_cooldown(self):
        _nudge_state["mode"] = "AUTO"
        _nudge_state["cooldown"] = {0: 98}  # adjusted 2 spins ago
        _nudge_state["cooldown_spins"] = 5
        flags = _blank_status_flags(); flags["missing"] = True
        _auto_nudge_apply(flags, 100)  # 100-98=2 < 5, still in cooldown
        assert 0 not in _nudge_state["overrides"]

    def test_auto_nudges_back_when_flag_cleared(self):
        _nudge_state["mode"] = "AUTO"
        default_val = _DE2D_SLIDER_CFG[0][0]
        _nudge_state["overrides"] = {0: default_val - 2}
        flags = _blank_status_flags()  # missing=False
        _auto_nudge_apply(flags, 100)
        assert _nudge_state["overrides"].get(0, default_val) > default_val - 2

    def test_auto_does_not_go_below_minimum(self):
        _nudge_state["mode"] = "AUTO"
        min_val = _DE2D_SLIDER_CFG[0][1]
        _nudge_state["overrides"] = {0: min_val}
        flags = _blank_status_flags(); flags["missing"] = True
        _auto_nudge_apply(flags, 200)
        assert _nudge_state["overrides"].get(0, min_val) >= min_val

    def test_fails_closed_on_none_flags(self):
        _nudge_state["mode"] = "AUTO"
        _auto_nudge_apply(None, 100)  # must not raise

    def test_cooldown_records_spin_count(self):
        _nudge_state["mode"] = "AUTO"
        flags = _blank_status_flags(); flags["missing"] = True
        _auto_nudge_apply(flags, 42)
        assert _nudge_state["cooldown"].get(0) == 42

    def test_suggest_mode_no_change(self):
        """SUGGEST mode must NOT change overrides (only MANUAL and AUTO are handled)."""
        _nudge_state["mode"] = "SUGGEST"
        flags = _blank_status_flags(); flags["missing"] = True
        _auto_nudge_apply(flags, 100)
        assert _nudge_state["overrides"] == {}


# ---------------------------------------------------------------------------
# 10.  _nudge_state structure
# ---------------------------------------------------------------------------

class TestNudgeStateStructure:
    def test_mode_is_string(self):
        assert isinstance(_nudge_state["mode"], str)

    def test_valid_modes_accepted(self):
        for mode in ("MANUAL", "SUGGEST", "AUTO"):
            _nudge_state["mode"] = mode
            assert _nudge_state["mode"] == mode

    def test_overrides_is_dict(self):
        assert isinstance(_nudge_state["overrides"], dict)

    def test_cooldown_is_dict(self):
        assert isinstance(_nudge_state["cooldown"], dict)

    def test_cooldown_spins_is_positive_int(self):
        assert isinstance(_nudge_state["cooldown_spins"], int)
        assert _nudge_state["cooldown_spins"] > 0

    def test_nudge_log_is_list(self):
        assert isinstance(_nudge_state["nudge_log"], list)


# ---------------------------------------------------------------------------
# 11.  _get_dc_danger_info
# ---------------------------------------------------------------------------

class TestGetDcDangerInfo:
    def test_no_flags_no_danger(self):
        flags = _blank_status_flags()
        has_danger, note = _get_dc_danger_info(flags)
        assert not has_danger
        assert note == ""

    def test_pattern_flag_is_danger(self):
        flags = _blank_status_flags()
        flags["pattern"] = True
        has_danger, note = _get_dc_danger_info(flags)
        assert has_danger
        assert "Pattern" in note

    def test_streak_flag_is_danger(self):
        flags = _blank_status_flags()
        flags["streak"] = True
        has_danger, note = _get_dc_danger_info(flags)
        assert has_danger
        assert "Streak" in note

    def test_overheated_flag_is_danger(self):
        flags = _blank_status_flags()
        flags["overheated"] = True
        has_danger, note = _get_dc_danger_info(flags)
        assert has_danger
        assert "Overheat" in note

    def test_three_active_flags_is_danger(self):
        flags = _blank_status_flags()
        flags["missing"] = flags["even"] = flags["voisins"] = True  # 3 active
        has_danger, note = _get_dc_danger_info(flags)
        assert has_danger
        assert "Active" in note

    def test_two_active_flags_not_danger(self):
        flags = _blank_status_flags()
        flags["missing"] = flags["even"] = True  # only 2
        has_danger, note = _get_dc_danger_info(flags)
        # 2 active < 3, and no pattern/streak/overheated → no danger
        assert not has_danger

    def test_clamp_note_format(self):
        flags = _blank_status_flags()
        flags["pattern"] = True
        _, note = _get_dc_danger_info(flags)
        assert note.startswith("CLAMPED (Danger:")
        assert note.endswith(")")

    def test_multiple_danger_reasons_joined(self):
        flags = _blank_status_flags()
        flags["pattern"] = flags["streak"] = True
        _, note = _get_dc_danger_info(flags)
        assert "Pattern" in note and "Streak" in note

    def test_fails_closed_on_none_input(self):
        has_danger, note = _get_dc_danger_info(None)
        assert not has_danger
        assert note == ""


# ---------------------------------------------------------------------------
# 12.  _render_nudge_recommendations_html with dc_context
# ---------------------------------------------------------------------------

class TestRenderNudgeRecommendationsHtmlWithDC:
    def _make_dc_context(self, target="1st Column", confidence=75,
                         has_danger=False, clamp_note=""):
        return {
            "active": True,
            "target": target,
            "confidence": confidence,
            "has_danger": has_danger,
            "clamp_note": clamp_note,
        }

    # 1) DC-HIGH with no danger → $1.00 OPPORTUNITY, never $0.01
    def test_dc_high_no_danger_shows_one_dollar(self):
        dc = self._make_dc_context(confidence=75, has_danger=False)
        result = _render_nudge_recommendations_html([], "SUGGEST", dc_context=dc)
        assert "$1.00" in result
        assert "$0.01" not in result

    def test_dc_high_no_danger_shows_opportunity(self):
        dc = self._make_dc_context(confidence=80, has_danger=False)
        result = _render_nudge_recommendations_html([], "SUGGEST", dc_context=dc)
        assert "OPPORTUNITY" in result

    # 2) DC-HIGH with danger flags → $0.10 HOLD + CLAMPED text
    def test_dc_high_with_danger_shows_zero_ten(self):
        dc = self._make_dc_context(confidence=75, has_danger=True,
                                   clamp_note="CLAMPED (Danger: Active≥3)")
        result = _render_nudge_recommendations_html([], "SUGGEST", dc_context=dc)
        assert "$0.10" in result
        assert "$0.01" not in result

    def test_dc_high_with_danger_shows_clamped(self):
        dc = self._make_dc_context(confidence=75, has_danger=True,
                                   clamp_note="CLAMPED (Danger: Pattern)")
        result = _render_nudge_recommendations_html([], "SUGGEST", dc_context=dc)
        assert "CLAMPED" in result

    # 3) DC-HIGH never returns $0.01 even if base tier logic would have returned PROTECT
    def test_dc_high_with_deep_drought_target_still_no_protect(self):
        """DC target in active_targets with ratio >= 1.5 (would be PROTECT).
        The DC row must override it and show $1.00 (no danger) not $0.01."""
        dc = self._make_dc_context(target="1st Column", confidence=75, has_danger=False)
        # Active target for same name with extreme drought miss/threshold
        targets = [{"name": "Missing 1st Column", "miss": 20, "threshold": 10, "cfg_idx": 0}]
        result = _render_nudge_recommendations_html(targets, "SUGGEST", dc_context=dc)
        # DC row must show $1.00; the target row should be skipped (overlaps dc target)
        assert "$1.00" in result
        assert "$0.01" not in result

    def test_dc_high_bet_never_zero_one_regardless_of_active_targets(self):
        dc = self._make_dc_context(confidence=70, has_danger=False)
        # extreme drought targets
        targets = [{"name": "Voisins du Zéro", "miss": 30, "threshold": 10, "cfg_idx": 4}]
        result = _render_nudge_recommendations_html(targets, "SUGGEST", dc_context=dc)
        assert "$1.00" in result  # DC row is $1.00

    # 4) Target alignment: DC target row appears first
    def test_dc_target_name_appears_first_in_html(self):
        dc = self._make_dc_context(target="Black", confidence=75, has_danger=False)
        targets = [{"name": "Voisins du Zéro", "miss": 12, "threshold": 10, "cfg_idx": 4}]
        result = _render_nudge_recommendations_html(targets, "SUGGEST", dc_context=dc)
        dc_pos = result.find("Black")
        other_pos = result.find("Voisins")
        assert dc_pos != -1
        assert other_pos != -1
        assert dc_pos < other_pos, "DC target row must appear before other targets"

    def test_dc_target_row_has_fire_emoji(self):
        dc = self._make_dc_context(target="Red", confidence=75)
        result = _render_nudge_recommendations_html([], "SUGGEST", dc_context=dc)
        assert "\U0001f525" in result  # 🔥

    # 5) MANUAL mode: no DC row shown
    def test_manual_mode_with_dc_returns_empty(self):
        dc = self._make_dc_context(confidence=75)
        result = _render_nudge_recommendations_html([], "MANUAL", dc_context=dc)
        assert result == ""

    # 6) DC-MODERATE (50-69%) → $0.10 HOLD
    def test_dc_moderate_shows_zero_ten(self):
        dc = self._make_dc_context(confidence=60, has_danger=False)
        result = _render_nudge_recommendations_html([], "SUGGEST", dc_context=dc)
        assert "$0.10" in result
        assert "HOLD" in result

    # 7) DC-WEAK (<50%) → $0.01 PROTECT  (this is the only case DC can be $0.01)
    def test_dc_weak_shows_zero_one(self):
        dc = self._make_dc_context(confidence=40, has_danger=False)
        result = _render_nudge_recommendations_html([], "SUGGEST", dc_context=dc)
        assert "$0.01" in result
        assert "PROTECT" in result

    # 8) DC inactive → falls back to existing behaviour
    def test_no_dc_context_falls_back_to_normal(self):
        targets = [{"name": "Test Target", "miss": 20, "threshold": 10, "cfg_idx": 0}]
        result = _render_nudge_recommendations_html(targets, "SUGGEST")
        assert "PROTECT" in result  # would be PROTECT via base tier
        assert "Test Target" in result

    # 9) DC target is deduplicated from secondary rows
    def test_dc_target_not_duplicated_in_secondary_rows(self):
        dc = self._make_dc_context(target="Red", confidence=75)
        # Active targets list also contains "Red" (same name as DC target)
        targets = [{"name": "Red", "miss": 15, "threshold": 8, "cfg_idx": 1}]
        result = _render_nudge_recommendations_html(targets, "SUGGEST", dc_context=dc)
        # The secondary row for "Red" must be suppressed; only the DC row (🔥 Red) remains.
        # The DC label is prefixed with 🔥, so "Red" as a bare span title should appear
        # only in the DC row's title attribute – not as a bare secondary row name.
        assert "Red" in result  # DC row is present
        # Secondary row would add ">Red<" without the 🔥 prefix; must not be present.
        assert result.count(">Red<") == 0

    # 10) AUTO mode with DC shows purple badge
    def test_auto_mode_dc_shows_purple_badge(self):
        dc = self._make_dc_context(confidence=75)
        result = _render_nudge_recommendations_html([], "AUTO", dc_context=dc)
        assert "8b5cf6" in result  # purple badge for AUTO


# ---------------------------------------------------------------------------
# 13.  nudge_log (new in AUTO mode: visual sync feature)
# ---------------------------------------------------------------------------

class TestNudgeLog:
    def setup_method(self):
        _reset_nudge_state()

    def teardown_method(self):
        _reset_nudge_state()

    # 1) AUTO mode creates a log entry when a nudge is applied
    def test_auto_creates_log_entry_on_nudge(self):
        _nudge_state["mode"] = "AUTO"
        flags = _blank_status_flags()
        flags["missing"] = True
        _auto_nudge_apply(flags, 100)
        log = _nudge_state.get("nudge_log", [])
        assert len(log) == 1
        entry = log[0]
        assert entry["slider"] == "Missing Dozen/Col"
        assert entry["old_val"] == _DE2D_SLIDER_CFG[0][0]       # default (14)
        assert entry["new_val"] == _DE2D_SLIDER_CFG[0][0] - 1   # lowered by 1
        assert "Active trigger" in entry["reason"]

    # 2) Relaxing nudge creates a log entry with correct reason
    def test_auto_relaxing_nudge_creates_log_entry(self):
        _nudge_state["mode"] = "AUTO"
        default_val = _DE2D_SLIDER_CFG[0][0]
        _nudge_state["overrides"] = {0: default_val - 1}
        flags = _blank_status_flags()  # missing=False → relax toward default
        _auto_nudge_apply(flags, 100)
        log = _nudge_state.get("nudge_log", [])
        assert len(log) == 1
        assert "relaxing" in log[0]["reason"].lower()
        assert log[0]["new_val"] == default_val

    # 3) nudge_log retains only the last 5 entries
    def test_nudge_log_capped_at_five(self):
        _nudge_state["mode"] = "AUTO"
        _nudge_state["overrides"] = {}
        # Trigger 6 distinct nudges by using large spin-count gaps to bypass cooldown
        flags = _blank_status_flags()
        flags["missing"] = True
        for i in range(6):
            # reset to default each time so there's always something to nudge
            _nudge_state["overrides"][0] = _DE2D_SLIDER_CFG[0][0]
            _nudge_state["cooldown"] = {}  # clear cooldown
            _auto_nudge_apply(flags, 100 + i * 10)
        log = _nudge_state.get("nudge_log", [])
        assert len(log) <= 5

    # 4) SUGGEST mode does NOT update nudge_log
    def test_suggest_mode_does_not_update_log(self):
        _nudge_state["mode"] = "SUGGEST"
        flags = _blank_status_flags()
        flags["missing"] = True
        _auto_nudge_apply(flags, 100)
        assert _nudge_state.get("nudge_log", []) == []

    # 5) MANUAL mode does NOT update nudge_log
    def test_manual_mode_does_not_update_log(self):
        _nudge_state["mode"] = "MANUAL"
        flags = _blank_status_flags()
        flags["missing"] = True
        _auto_nudge_apply(flags, 100)
        assert _nudge_state.get("nudge_log", []) == []

    # 6) nudge_log entry has all required keys
    def test_nudge_log_entry_has_required_keys(self):
        _nudge_state["mode"] = "AUTO"
        flags = _blank_status_flags()
        flags["even"] = True
        _auto_nudge_apply(flags, 100)
        log = _nudge_state.get("nudge_log", [])
        assert len(log) >= 1
        entry = log[0]
        for key in ("slider", "old_val", "new_val", "direction", "reason"):
            assert key in entry, f"Missing key: {key}"

    # 7) nudge_log entry direction: active flag lowers value (old > new)
    def test_active_flag_lowers_value_in_log(self):
        _nudge_state["mode"] = "AUTO"
        # Set override above minimum to guarantee a downward nudge is possible
        _nudge_state["overrides"] = {2: _DE2D_SLIDER_CFG[2][0]}  # streak at default (9)
        flags = _blank_status_flags()
        flags["streak"] = True
        _auto_nudge_apply(flags, 100)
        log = _nudge_state.get("nudge_log", [])
        assert len(log) >= 1, "Expected a log entry but log is empty"
        entry = log[0]
        assert entry["old_val"] > entry["new_val"], "Active flag should lower threshold"
        assert entry["direction"] == "down"

    # 8) cooldown prevents duplicate log entries within cooldown window
    def test_cooldown_prevents_log_entry(self):
        _nudge_state["mode"] = "AUTO"
        _nudge_state["cooldown"] = {0: 98}
        _nudge_state["cooldown_spins"] = 5
        flags = _blank_status_flags()
        flags["missing"] = True
        _auto_nudge_apply(flags, 100)  # 100-98=2 < 5; still in cooldown
        assert _nudge_state.get("nudge_log", []) == []
