"""WheelPulsePro – core logic package.

This package contains the non-UI, reusable components of WheelPulsePro:
  - state      : RouletteState session state object
  - mappings   : BETTING_MAPPINGS, initialize_betting_mappings, validate_roulette_data
  - scoring    : update_scores_batch (core implementation with explicit parameters);
                 _update_drought_counters / _update_drought_counters_inner (migrated from app.py)
  - strategies : All betting/strategy functions extracted from app.py (Step 1)
  - trackers   : DE2D, Dozen, and Even-Money tracker functions extracted from app.py (Step 2)
  - analysis   : Analysis & statistical functions extracted from app.py (Step 3)
  - sessions   : Session management, file I/O, and spin manipulation extracted from app.py (Step 4)
  - rendering  : HTML rendering helpers; also hosts migrated highlight_*, render_dynamic_table_html,
                 create_dynamic_table, render_alerts_bar_html, and render_master_info helpers
  - ui_logic   : UI/state helper functions (validate_spins_input, add_spin, reset_scores,
                 clear_all, master_reset, update_spin_counter, etc.) migrated from app.py

app.py remains the Gradio entrypoint and imports from this package.
"""
