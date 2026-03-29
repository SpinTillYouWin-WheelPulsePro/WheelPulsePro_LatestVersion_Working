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
