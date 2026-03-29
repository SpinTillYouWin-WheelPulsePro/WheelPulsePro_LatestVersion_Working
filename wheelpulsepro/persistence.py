"""Auto-save / auto-restore helpers for WheelPulsePro state.

Persistence strategy
--------------------
* Primary path  : ``/data/autosave.json``  (HF Spaces persistent storage)
* Fallback path : ``data/autosave.json``   (local ``data/`` directory)

Both ``autosave`` and ``autorestore`` are fully fault-tolerant — they never
raise exceptions so they cannot interrupt the main application flow.
"""

import json
import logging
import os

logger = logging.getLogger("wheelPulsePro.persistence")

_HF_PATH = "/data/autosave.json"
_LOCAL_PATH = "data/autosave.json"


def _get_autosave_path() -> str:
    """Return the path to use for the auto-save file.

    Prefers HF Spaces persistent storage (``/data/``) when that directory
    exists and is writable; falls back to a local ``data/`` subdirectory.
    """
    if os.path.isdir("/data") and os.access("/data", os.W_OK):
        return _HF_PATH
    os.makedirs("data", exist_ok=True)
    return _LOCAL_PATH


def autosave(state) -> None:
    """Serialize *state* and write it to the auto-save file.

    Uses an atomic write (write to ``<path>.tmp`` then rename) so a crash
    mid-write cannot corrupt the previous good save.  All errors are caught
    and logged at WARNING level so the main app is never disrupted.
    """
    try:
        path = _get_autosave_path()
        data = state.to_dict()
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp_path, path)
        logger.debug("Auto-saved state to %s (%d spins)", path, len(state.last_spins))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Auto-save failed (state not persisted): %s", exc)


def autorestore(state) -> bool:
    """Try to restore *state* from the auto-save file.

    Searches the HF path first, then the local fallback.  If a valid save is
    found, all attributes on *state* are updated in-place (preserving the
    same object reference used by the rest of the app).

    Returns ``True`` on success, ``False`` when no file was found or loading
    failed.
    """
    from wheelpulsepro.state import RouletteState  # local import avoids circular dependency

    for path in (_HF_PATH, _LOCAL_PATH):
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            restored = RouletteState.from_dict(data)
            state.__dict__.update(restored.__dict__)
            logger.info(
                "Auto-restored state from %s (%d spins)",
                path,
                len(state.last_spins),
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-restore failed (starting with fresh state): %s", exc)
            return False

    logger.info("No auto-save file found; starting with fresh state.")
    return False
