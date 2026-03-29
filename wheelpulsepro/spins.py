"""Pure spin parsing and validation helpers for WheelPulsePro.

All functions in this module are free of Gradio dependencies so they can be
imported and tested without a UI environment.

Typical usage from app.py
--------------------------
from wheelpulsepro.spins import parse_spins_input, validate_spins, MAX_SPINS

raw = parse_spins_input(user_text)
if len(raw) > MAX_SPINS:
    gr.Warning(...)
    return ...

valid, errors = validate_spins(raw)
if errors:
    gr.Warning(...)
"""

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Maximum number of spins that may be submitted at once.
MAX_SPINS: int = 1000

#: Inclusive lower bound for a valid roulette number.
SPIN_MIN: int = 0

#: Inclusive upper bound for a valid roulette number.
SPIN_MAX: int = 36


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_spins_input(spins_input: str) -> list:
    """Split a comma-separated spins string into a list of stripped tokens.

    Parameters
    ----------
    spins_input:
        Raw user input, e.g. ``"5, 12, 0"`` or ``"5,12,0"``.

    Returns
    -------
    list[str]
        Non-empty stripped tokens.  Returns an empty list for blank/None input.

    Examples
    --------
    >>> parse_spins_input("1, 2, 3")
    ['1', '2', '3']
    >>> parse_spins_input("")
    []
    """
    if not spins_input or not spins_input.strip():
        return []
    return [s.strip() for s in spins_input.split(",") if s.strip()]


def validate_spins(raw_tokens: list) -> tuple:
    """Validate a list of raw spin tokens against the European roulette range.

    Does *not* enforce the :data:`MAX_SPINS` limit — that check belongs in the
    caller so it can issue an appropriate UI warning before calling this
    function.

    Parameters
    ----------
    raw_tokens:
        List of string tokens, typically produced by :func:`parse_spins_input`.

    Returns
    -------
    valid_spins : list[str]
        Normalized string representations of all tokens that are valid
        integers in ``[SPIN_MIN, SPIN_MAX]``.
    errors : list[str]
        Human-readable error messages for every invalid token.

    Examples
    --------
    >>> validate_spins(["1", "abc", "37"])
    (['1'], ["'abc' is not a valid integer", "'37' is out of range (must be 0-36)"])
    """
    valid_spins: list = []
    errors: list = []

    for token in raw_tokens:
        try:
            num = int(token)
            if not (SPIN_MIN <= num <= SPIN_MAX):
                errors.append(
                    f"'{token}' is out of range (must be {SPIN_MIN}-{SPIN_MAX})"
                )
            else:
                valid_spins.append(str(num))
        except ValueError:
            errors.append(f"'{token}' is not a valid integer")

    return valid_spins, errors
