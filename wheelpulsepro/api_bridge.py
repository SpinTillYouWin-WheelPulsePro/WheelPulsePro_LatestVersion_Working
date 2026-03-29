"""API bridge: exports current RouletteState as a JSON-serializable dict for AIDEA consumption.

This module is a pure-Python, Gradio-free read-only view of the analysis state.
AIDEA polls the ``/api/get_aidea_feed`` Gradio endpoint which calls
:func:`export_state_for_aidea` and returns the result.
"""

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("wheelPulsePro.api_bridge")


def export_state_for_aidea(
    state: Any,
    current_neighbors: Dict[int, tuple],
    strategy_name: str = "hot",
) -> Dict[str, Any]:
    """Package the current :class:`~wheelpulsepro.state.RouletteState` into a
    JSON-serializable dictionary suitable for consumption by WheelPulse AIDEA.

    Parameters
    ----------
    state:
        The live ``RouletteState`` instance.
    current_neighbors:
        Neighbor lookup dict in the same format as ``NEIGHBORS_EUROPEAN`` from
        ``roulette_data.py`` — maps ``int`` → ``(left: int | None, right: int | None)``.
    strategy_name:
        Human-readable strategy label included in the payload (default ``"hot"``).

    Returns
    -------
    dict
        Fully JSON-serializable dictionary.  All integer keys have been
        converted to plain Python ``int``/``str`` so that ``json.dumps``
        succeeds without a custom encoder.
    """
    try:
        # ------------------------------------------------------------------
        # STRAIGHT-UP BETS — top 18 numbers by score
        # ------------------------------------------------------------------
        sorted_numbers = sorted(
            state.scores.items(), key=lambda x: x[1], reverse=True
        )
        straight_up = [
            {"number": int(n), "score": int(s)}
            for n, s in sorted_numbers
            if s > 0
        ][:18]

        # ------------------------------------------------------------------
        # EVEN MONEY
        # ------------------------------------------------------------------
        even_money_scores = {k: int(v) for k, v in state.even_money_scores.items() if v > 0}
        best_even: Optional[Dict[str, Any]] = None
        if even_money_scores:
            best_name = max(even_money_scores, key=lambda k: even_money_scores[k])
            best_even = {"name": best_name, "score": even_money_scores[best_name]}

        # ------------------------------------------------------------------
        # DOZENS
        # ------------------------------------------------------------------
        dozen_scores = {k: int(v) for k, v in state.dozen_scores.items() if v > 0}
        best_dozen: Optional[Dict[str, Any]] = None
        if dozen_scores:
            best_name = max(dozen_scores, key=lambda k: dozen_scores[k])
            best_dozen = {"name": best_name, "score": dozen_scores[best_name]}

        # ------------------------------------------------------------------
        # COLUMNS
        # ------------------------------------------------------------------
        column_scores = {k: int(v) for k, v in state.column_scores.items() if v > 0}
        best_column: Optional[Dict[str, Any]] = None
        if column_scores:
            best_name = max(column_scores, key=lambda k: column_scores[k])
            best_column = {"name": best_name, "score": column_scores[best_name]}

        # ------------------------------------------------------------------
        # INSIDE BETS
        # ------------------------------------------------------------------
        streets = sorted(state.street_scores.items(), key=lambda x: x[1], reverse=True)
        top_streets = [
            {"name": str(n), "score": int(s)} for n, s in streets if s > 0
        ][:3]

        corners = sorted(state.corner_scores.items(), key=lambda x: x[1], reverse=True)
        top_corners = [
            {"name": str(n), "score": int(s)} for n, s in corners if s > 0
        ][:3]

        splits = sorted(state.split_scores.items(), key=lambda x: x[1], reverse=True)
        top_splits = [
            {"name": str(n), "score": int(s)} for n, s in splits if s > 0
        ][:5]

        # ------------------------------------------------------------------
        # WHEEL SECTORS — sides of zero
        # ------------------------------------------------------------------
        sides_of_zero = {str(k): int(v) for k, v in state.side_scores.items()}

        # ------------------------------------------------------------------
        # STRONGEST NUMBERS WITH NEIGHBORS — top 5
        # ------------------------------------------------------------------
        top5 = [
            (int(n), int(s)) for n, s in sorted_numbers if s > 0
        ][:5]
        strongest_with_neighbors = []
        for number, score in top5:
            left_n, right_n = current_neighbors.get(number, (None, None))
            strongest_with_neighbors.append(
                {
                    "number": number,
                    "score": score,
                    "left": int(left_n) if left_n is not None else None,
                    "right": int(right_n) if right_n is not None else None,
                }
            )

        # ------------------------------------------------------------------
        # LAST SPINS — last 10 as list of strings
        # ------------------------------------------------------------------
        last_spins = [str(s) for s in state.last_spins[-10:]]

        return {
            "connected": True,
            "timestamp": float(time.time()),
            "total_spins": int(len(state.last_spins)),
            "last_spins": last_spins,
            # Straight-up bets
            "straight_up": straight_up,
            # Even money
            "even_money": {
                "scores": even_money_scores,
                "best": best_even,
            },
            # Dozens
            "dozens": {
                "scores": dozen_scores,
                "best": best_dozen,
            },
            # Columns
            "columns": {
                "scores": column_scores,
                "best": best_column,
            },
            # Inside bets
            "streets": top_streets,
            "corners": top_corners,
            "splits": top_splits,
            # Wheel sectors
            "sides_of_zero": sides_of_zero,
            # Strongest numbers with their wheel neighbors
            "strongest_with_neighbors": strongest_with_neighbors,
            # Meta
            "strategy": str(strategy_name),
        }
    except Exception:
        logger.exception("export_state_for_aidea failed")
        # Return a safe, connected-but-empty payload so AIDEA can keep polling
        return {
            "connected": True,
            "timestamp": float(time.time()),
            "total_spins": 0,
            "last_spins": [],
            "straight_up": [],
            "even_money": {"scores": {}, "best": None},
            "dozens": {"scores": {}, "best": None},
            "columns": {"scores": {}, "best": None},
            "streets": [],
            "corners": [],
            "splits": [],
            "sides_of_zero": {},
            "strongest_with_neighbors": [],
            "strategy": str(strategy_name),
        }
