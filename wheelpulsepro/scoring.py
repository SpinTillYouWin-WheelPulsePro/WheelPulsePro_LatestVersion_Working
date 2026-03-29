"""Batch score update logic for WheelPulsePro.

Exports:
  update_scores_batch() – update a RouletteState's score dictionaries for a
                          list of spins and return an action-log for undo.

The function accepts the mutable state and lookup structures as explicit
parameters so that it has no hidden global dependencies and is straightforward
to unit-test.  app.py provides a thin wrapper that passes the application-level
globals so that all existing call sites remain unchanged.
"""

import logging
from typing import Any, Dict, List, Set

_logger = logging.getLogger("wheel_pulse_pro.scoring")


def update_scores_batch(
    spins: list,
    roulette_state: Any,
    left_of_zero: Set[int],
    right_of_zero: Set[int],
    betting_mappings: Dict[int, Dict[str, list]],
) -> List[dict]:
    """Update scores for a batch of spins and return an action-log for undo.

    Parameters
    ----------
    spins:
        Iterable of spin values (str or int in range 0-36).
    roulette_state:
        A ``RouletteState`` instance whose score dicts will be updated in-place.
    left_of_zero:
        Set of numbers that belong to the Left Side of Zero.
    right_of_zero:
        Set of numbers that belong to the Right Side of Zero.
    betting_mappings:
        Pre-computed mapping from number -> {category: [names]}.
        Must be initialised before calling this function.

    Returns
    -------
    list[dict]
        One entry per spin; each entry records the spin value and the
        increments applied so that callers can undo them.  Invalid spin
        values are skipped and logged rather than raising an exception.
    """
    action_log: List[dict] = []

    for spin in spins:
        # Defensive int() conversion — skip non-integer spin values.
        try:
            spin_value = int(spin)
        except (ValueError, TypeError):
            _logger.warning(
                "update_scores_batch: skipping non-integer spin value %r", spin
            )
            continue

        # Guard against spin values outside the valid European roulette range.
        if spin_value not in betting_mappings:
            _logger.warning(
                "update_scores_batch: spin value %d not in betting_mappings "
                "(valid range 0-36); skipping",
                spin_value,
            )
            continue

        action: dict = {"spin": spin_value, "increments": {}}

        # Get all betting categories for this number from precomputed mappings
        categories = betting_mappings[spin_value]

        # Update even money scores
        for name in categories["even_money"]:
            roulette_state.even_money_scores[name] += 1
            action["increments"].setdefault("even_money_scores", {})[name] = 1

        # Update dozens scores
        for name in categories["dozens"]:
            roulette_state.dozen_scores[name] += 1
            action["increments"].setdefault("dozen_scores", {})[name] = 1

        # Update columns scores
        for name in categories["columns"]:
            roulette_state.column_scores[name] += 1
            action["increments"].setdefault("column_scores", {})[name] = 1

        # Update streets scores
        for name in categories["streets"]:
            roulette_state.street_scores[name] += 1
            action["increments"].setdefault("street_scores", {})[name] = 1

        # Update corners scores
        for name in categories["corners"]:
            roulette_state.corner_scores[name] += 1
            action["increments"].setdefault("corner_scores", {})[name] = 1

        # Update six lines scores
        for name in categories["six_lines"]:
            roulette_state.six_line_scores[name] += 1
            action["increments"].setdefault("six_line_scores", {})[name] = 1

        # Update splits scores
        for name in categories["splits"]:
            roulette_state.split_scores[name] += 1
            action["increments"].setdefault("split_scores", {})[name] = 1

        # Update straight-up scores
        roulette_state.scores[spin_value] += 1
        action["increments"].setdefault("scores", {})[spin_value] = 1

        # Update side scores
        if spin_value in left_of_zero:
            roulette_state.side_scores["Left Side of Zero"] += 1
            action["increments"].setdefault("side_scores", {})["Left Side of Zero"] = 1
        if spin_value in right_of_zero:
            roulette_state.side_scores["Right Side of Zero"] += 1
            action["increments"].setdefault("side_scores", {})["Right Side of Zero"] = 1

        action_log.append(action)

    return action_log


# ---------------------------------------------------------------------------
# Drought counter logic (migrated from app.py)
# ---------------------------------------------------------------------------

_drought_state = None


def init_drought(state_obj) -> None:
    """Inject the shared RouletteState instance for drought counter updates."""
    global _drought_state
    _drought_state = state_obj


def _update_drought_counters() -> None:
    """Recompute state.drought_counters from state.last_spins.

    Scans spins in reverse order to find how many spins have elapsed since
    each tracked category (dozens, columns, even-money) last hit.  O(N) where
    N = len(state.last_spins).
    """
    try:
        _update_drought_counters_inner()
    except Exception:
        _logger.exception("Failed to update drought counters")


def _update_drought_counters_inner() -> None:
    state = _drought_state
    if state is None:
        return
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
