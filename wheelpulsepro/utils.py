"""WheelPulsePro – utility helpers."""

import logging

logger = logging.getLogger("wheelPulsePro")

# Module-level state reference (set via init())
_state = None


def init(state_obj):
    """Inject the shared RouletteState instance."""
    global _state
    _state = state_obj


def _get_file_path(file):
    """Return the filesystem path for a Gradio file object or plain string.

    Gradio file objects expose a ``.name`` attribute containing the path to
    the temporary file on disk.  Plain strings are accepted as-is so that
    callers can also pass a path directly.  Returns ``None`` when *file* does
    not expose a usable path.
    """
    return getattr(file, "name", None) or (file if isinstance(file, str) else None)


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
