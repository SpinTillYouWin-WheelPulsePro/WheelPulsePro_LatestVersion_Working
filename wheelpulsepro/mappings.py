"""Betting category mappings and roulette-data validation utilities.

Exports:
  BETTING_MAPPINGS              – dict mapping each number 0-36 to its bet categories.
  initialize_betting_mappings() – populates BETTING_MAPPINGS in-place at startup.
  validate_roulette_data()      – returns a list of errors (or None) for the constants
                                   imported from roulette_data.py.
"""

from typing import List, Optional

from roulette_data import (
    EVEN_MONEY, DOZENS, COLUMNS, STREETS, CORNERS, SIX_LINES, SPLITS,
    NEIGHBORS_EUROPEAN, LEFT_OF_ZERO_EUROPEAN, RIGHT_OF_ZERO_EUROPEAN,
)

# Populated by initialize_betting_mappings(); mutated in-place so that any
# import of this name (e.g. ``from wheelpulsepro.mappings import BETTING_MAPPINGS``)
# always sees the fully-initialised dict.
BETTING_MAPPINGS: dict = {}


def initialize_betting_mappings() -> None:
    """Populate BETTING_MAPPINGS in-place with pre-computed bet-category lists.

    Must be called once at application startup before any scoring takes place.
    """
    new: dict = {
        i: {
            "even_money": [],
            "dozens": [],
            "columns": [],
            "streets": [],
            "corners": [],
            "six_lines": [],
            "splits": [],
        }
        for i in range(37)
    }

    # Convert lists to sets and map numbers to categories
    for name, numbers in EVEN_MONEY.items():
        numbers_set = set(numbers)
        for num in numbers_set:
            new[num]["even_money"].append(name)

    for name, numbers in DOZENS.items():
        numbers_set = set(numbers)
        for num in numbers_set:
            new[num]["dozens"].append(name)

    for name, numbers in COLUMNS.items():
        numbers_set = set(numbers)
        for num in numbers_set:
            new[num]["columns"].append(name)

    for name, numbers in STREETS.items():
        numbers_set = set(numbers)
        for num in numbers_set:
            new[num]["streets"].append(name)

    for name, numbers in CORNERS.items():
        numbers_set = set(numbers)
        for num in numbers_set:
            new[num]["corners"].append(name)

    for name, numbers in SIX_LINES.items():
        numbers_set = set(numbers)
        for num in numbers_set:
            new[num]["six_lines"].append(name)

    for name, numbers in SPLITS.items():
        numbers_set = set(numbers)
        for num in numbers_set:
            new[num]["splits"].append(name)

    # Mutate in-place so all existing references remain valid
    BETTING_MAPPINGS.clear()
    BETTING_MAPPINGS.update(new)


def validate_roulette_data() -> Optional[List[str]]:
    """Validate that all required constants from roulette_data.py are present and correctly formatted.

    Returns a list of error strings if validation fails, or None if everything is OK.
    """
    required_dicts = {
        "EVEN_MONEY": EVEN_MONEY,
        "DOZENS": DOZENS,
        "COLUMNS": COLUMNS,
        "STREETS": STREETS,
        "CORNERS": CORNERS,
        "SIX_LINES": SIX_LINES,
        "SPLITS": SPLITS
    }
    required_neighbors = {
        "NEIGHBORS_EUROPEAN": NEIGHBORS_EUROPEAN,
        "LEFT_OF_ZERO_EUROPEAN": LEFT_OF_ZERO_EUROPEAN,
        "RIGHT_OF_ZERO_EUROPEAN": RIGHT_OF_ZERO_EUROPEAN
    }
    errors = []
    for name, data in required_dicts.items():
        if not isinstance(data, dict):
            errors.append(f"{name} must be a dictionary.")
            continue
        for key, value in data.items():
            if not isinstance(key, str) or not isinstance(value, (list, set, tuple)) or not all(isinstance(n, int) for n in value):
                errors.append(f"{name}['{key}'] must map to a list/set/tuple of integers.")
    for name, data in required_neighbors.items():
        if name == "NEIGHBORS_EUROPEAN":
            if not isinstance(data, dict):
                errors.append(f"{name} must be a dictionary.")
                continue
            for key, value in data.items():
                if not isinstance(key, int) or not isinstance(value, tuple) or len(value) != 2 or not all(isinstance(n, (int, type(None))) for n in value):
                    errors.append(f"{name}[{key}] must map to a tuple of two integers or None.")
        else:
            if not isinstance(data, (list, set, tuple)) or not all(isinstance(n, int) for n in data):
                errors.append(f"{name} must be a list/set/tuple of integers.")
    return errors if errors else None
