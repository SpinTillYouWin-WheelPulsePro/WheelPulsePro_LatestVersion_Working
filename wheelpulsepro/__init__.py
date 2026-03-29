"""WheelPulsePro – core logic package.

This package contains the non-UI, reusable components of WheelPulsePro:
  - state      : RouletteState session state object
  - mappings   : BETTING_MAPPINGS, initialize_betting_mappings, validate_roulette_data
  - scoring    : update_scores_batch (core implementation with explicit parameters)
  - strategies : All betting/strategy functions extracted from app.py (Step 1)
  - trackers   : DE2D, Dozen, and Even-Money tracker functions extracted from app.py (Step 2)
  - analysis   : Analysis & statistical functions extracted from app.py (Step 3)
  - sessions   : Session management, file I/O, and spin manipulation extracted from app.py (Step 4)

app.py remains the Gradio entrypoint and imports from this package.
"""
