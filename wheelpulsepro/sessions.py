"""WheelPulsePro – session management, file I/O, and spin manipulation extracted from app.py."""

import json
import logging
import os
import random
import shutil
import tempfile
import time
import traceback
from datetime import datetime

import gradio as gr
import pandas as pd

from roulette_data import (
    COLUMNS,
    CORNERS,
    DOZENS,
    EVEN_MONEY,
    SIX_LINES,
    SPLITS,
    STREETS,
)
from wheelpulsepro.analysis import (
    create_strongest_numbers_with_neighbours_table,
    render_rank_table,
)
from wheelpulsepro.state import RouletteState
from wheelpulsepro.strategies import get_strongest_numbers_with_neighbors

logger = logging.getLogger("wheelPulsePro.sessions")

# ---------------------------------------------------------------------------
# Injected module-level globals (set by init())
# ---------------------------------------------------------------------------
state = None
current_neighbors = None

# Callbacks injected from app.py
_update_scores_batch = None
_update_drought_counters = None
_get_file_path = None
_render_sides_of_zero_display = None
_update_spin_counter = None
_create_color_code_table = None
_create_dynamic_table = None
_show_strategy_recommendations = None


def init(
    state_obj,
    neighbors,
    update_scores_batch_fn,
    update_drought_counters_fn,
    get_file_path_fn,
    render_sides_of_zero_display_fn,
    update_spin_counter_fn,
    create_color_code_table_fn,
    create_dynamic_table_fn,
    show_strategy_recommendations_fn,
):
    global state, current_neighbors
    global _update_scores_batch, _update_drought_counters, _get_file_path
    global _render_sides_of_zero_display, _update_spin_counter
    global _create_color_code_table, _create_dynamic_table, _show_strategy_recommendations

    state = state_obj
    current_neighbors = neighbors
    _update_scores_batch = update_scores_batch_fn
    _update_drought_counters = update_drought_counters_fn
    _get_file_path = get_file_path_fn
    _render_sides_of_zero_display = render_sides_of_zero_display_fn
    _update_spin_counter = update_spin_counter_fn
    _create_color_code_table = create_color_code_table_fn
    _create_dynamic_table = create_dynamic_table_fn
    _show_strategy_recommendations = show_strategy_recommendations_fn


# ---------------------------------------------------------------------------
# Session save / load / combine
# ---------------------------------------------------------------------------

def save_session(session_name):
    """
    Save the current session to a JSON file with a user-specified name.
    """
    try:
        # Sanitize the session name to avoid invalid characters
        session_name = "".join(c for c in (session_name or "") if c.isalnum() or c in ('_', '-', ' ')).strip()
        if not session_name:
            session_name = "WheelPulse_Session"
        
        # Add timestamp to ensure uniqueness
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{session_name}_{timestamp}.json"
        
        # Collect full session data using the canonical serializer
        session_data = state.to_dict()
        
        # Create a temporary file
        temp_dir = tempfile.gettempdir()
        if not os.access(temp_dir, os.W_OK):
            raise PermissionError(f"No write permission in temporary directory: {temp_dir}")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8', dir=temp_dir) as temp_file:
            json.dump(session_data, temp_file, indent=4)
            temp_file_path = temp_file.name
        
        # Rename the temporary file to the desired name
        final_path = os.path.join(temp_dir, file_name)
        shutil.move(temp_file_path, final_path)
        
        logger.debug(f"save_session: Generated file at {final_path}")
        return final_path
    except (OSError, ValueError, TypeError, AttributeError) as e:
        logger.error(f"save_session: Error: {str(e)}")
        return None


def combine_sessions(file1, file2, file3=None):
    """
    Combine multiple session JSON files back-to-back in upload order.
    File1 spins come first, File2 spins come after, File3 spins last (optional).
    Scores are recalculated from the combined spin list.
    """
    files = [f for f in [file1, file2, file3] if f is not None]
    if len(files) < 2:
        return None, "<p style='color:red;'>Please upload at least 2 session files to combine.</p>"

    combined_spins = []
    file_labels = []

    for idx, file in enumerate(files, 1):
        try:
            file_path = _get_file_path(file)
            if not file_path:
                return None, f"<p style='color:red;'>File {idx}: Unable to read uploaded file path.</p>"
            with open(file_path, "r") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None, f"<p style='color:red;'>File {idx}: Invalid session file — root must be an object.</p>"
            spins = data.get("spins", [])
            if not isinstance(spins, list):
                return None, f"<p style='color:red;'>File {idx}: Invalid session file — 'spins' must be a list.</p>"
            combined_spins.extend(spins)
            file_labels.append(f"File {idx}: {len(spins)} spins")
        except json.JSONDecodeError as e:
            return None, f"<p style='color:red;'>File {idx}: Invalid JSON — {str(e)}</p>"
        except Exception as e:
            return None, f"<p style='color:red;'>Error reading File {idx}: {str(e)}</p>"

    if not combined_spins:
        return None, "<p style='color:red;'>No spins found in the uploaded files.</p>"

    # Reset state and rebuild scores from combined spins
    state.reset()
    state.last_spins = combined_spins
    action_log = _update_scores_batch(combined_spins)
    state.spin_history = action_log
    _update_drought_counters()

    # Build the combined session data
    combined_data = {
        "spins": combined_spins,
        "spin_history": state.spin_history,
        "scores": state.scores,
        "even_money_scores": state.even_money_scores,
        "dozen_scores": state.dozen_scores,
        "column_scores": state.column_scores,
        "street_scores": state.street_scores,
        "corner_scores": state.corner_scores,
        "six_line_scores": state.six_line_scores,
        "split_scores": state.split_scores,
        "side_scores": state.side_scores,
        "casino_data": state.casino_data,
        "use_casino_winners": state.use_casino_winners
    }

    # Save to temp file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"Combined_Session_{timestamp}.json"
    temp_dir = tempfile.gettempdir()
    final_path = os.path.join(temp_dir, file_name)
    with open(final_path, "w", encoding="utf-8") as f:
        json.dump(combined_data, f, indent=4)

    summary_html = f"""
    <div style="background:#e8f5e9; border:2px solid #4caf50; border-radius:8px; padding:12px; font-family:Arial,sans-serif;">
        <h4 style="color:#2e7d32; margin:0 0 8px 0;">✅ Sessions Combined Successfully!</h4>
        <ul style="margin:0; padding-left:20px; color:#333;">
            {"".join(f"<li>{label}</li>" for label in file_labels)}
        </ul>
        <p style="margin:8px 0 0 0; font-weight:bold; color:#1b5e20;">
            Total Combined Spins: {len(combined_spins)}
        </p>
        <p style="margin:4px 0 0 0; font-size:12px; color:#555;">
            Spins loaded into the app in upload order. Download the combined file below.
        </p>
    </div>
    """
    return final_path, summary_html


def load_session(file, strategy_name, neighbours_count, strong_numbers_count, *checkbox_args):
    try:
        if file is None:
            return ("", "", "Please upload a session file to load.", "", "", "", "", "", "", "", "", "", "", "", _create_dynamic_table(strategy_name, neighbours_count, strong_numbers_count), "")

        file_path = getattr(file, "name", None) or (file if isinstance(file, str) else None)
        if not file_path:
            return ("", "", "Error: Unable to read uploaded file path.", "", "", "", "", "", "", "", "", "", "", "", _create_dynamic_table(strategy_name, neighbours_count, strong_numbers_count), "")

        with open(file_path, "r") as f:
            session_data = json.load(f)

        # Restore full state via from_dict() for complete coverage; the method
        # uses .get() with sensible defaults so older partial session files
        # (that only contain scores/spins) remain fully compatible.
        # Backward-compat alias: older files used "spins" for last_spins.
        if "last_spins" not in session_data and "spins" in session_data:
            session_data["last_spins"] = session_data["spins"]
        restored = RouletteState.from_dict(session_data)
        state.__dict__.update(restored.__dict__)
        _update_drought_counters()

        new_spins = ", ".join(state.last_spins)
        spin_analysis_output = f"Session loaded successfully with {len(state.last_spins)} spins."
        
        # Updated to use the new HTML Reactor tables
        even_money_output = render_rank_table(state.even_money_scores, "Even Money Trends")
        dozens_output = render_rank_table(state.dozen_scores, "Dozen Trends")
        columns_output = render_rank_table(state.column_scores, "Column Trends")
        streets_output = render_rank_table({k:v for k,v in state.street_scores.items() if v > 0}, "Active Street Hits")
        corners_output = render_rank_table({k:v for k,v in state.corner_scores.items() if v > 0}, "Active Corner Hits")
        six_lines_output = render_rank_table({k:v for k,v in state.six_line_scores.items() if v > 0}, "Double Street Hits")
        splits_output = render_rank_table({k:v for k,v in state.split_scores.items() if v > 0}, "Active Split Hits")
        sides_output = render_rank_table(state.side_scores, "Wheel Side Trends")
        
        # Use the updated function that contains the 'star-pin' logic
        straight_up_html = create_strongest_numbers_with_neighbours_table()
        straight_up_df = pd.DataFrame(list(state.scores.items()), columns=["Number", "Score"])
        straight_up_df = straight_up_df[straight_up_df["Score"] > 0].sort_values(by="Score", ascending=False)
        top_18_df = straight_up_df.head(18)
        top_18_html = top_18_df.to_html(index=False, classes="scrollable-table")
        strongest_numbers_output = ", ".join([str(int(row["Number"])) for _, row in straight_up_df.head(3).iterrows() if row["Score"] > 0]) or "No numbers have hit yet."

        return (
            new_spins,
            new_spins,
            spin_analysis_output,
            even_money_output,
            dozens_output,
            columns_output,
            streets_output,
            corners_output,
            six_lines_output,
            splits_output,
            sides_output,
            straight_up_html,
            top_18_html,
            strongest_numbers_output,
            _create_dynamic_table(strategy_name, neighbours_count, strong_numbers_count),
            _show_strategy_recommendations(strategy_name, neighbours_count, strong_numbers_count)
        )
    except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError, AttributeError) as e:
        logger.error(f"load_session: Error loading session: {str(e)}")
        return ("", "", f"Error loading session: {str(e)}", "", "", "", "", "", "", "", "", "", "", "", _create_dynamic_table(strategy_name, neighbours_count, strong_numbers_count), "")


# ---------------------------------------------------------------------------
# Spin analysis / manipulation
# ---------------------------------------------------------------------------

def analyze_spins(spins_input, strategy_name, neighbours_count, *checkbox_args):
    """Analyze the spins and return formatted results for all sections, always resetting scores."""
    try:
        logger.debug(f"analyze_spins: Starting with spins_input='{spins_input}', strategy_name='{strategy_name}', neighbours_count={neighbours_count}, checkbox_args={checkbox_args}")

        # Preserve the active Labouchere session across score resets so the
        # sequence is not wiped on every spin.  Scores are recalculated from
        # scratch on each call but session-tracker state must survive.
        _lab_snapshot = {
            'lab_active': state.lab_active,
            'lab_sequence': list(state.lab_sequence),
            'lab_base': state.lab_base,
            'lab_target': state.lab_target,
            'lab_bankroll': state.lab_bankroll,
            'lab_status': state.lab_status,
            'lab_mode': state.lab_mode,
            'lab_split_limit': state.lab_split_limit,
            'strategy_lab_enabled': state.strategy_lab_enabled,
        }

        def _restore_lab():
            for _k, _v in _lab_snapshot.items():
                setattr(state, _k, _v)

        # Handle empty spins case
        if not spins_input or not spins_input.strip():
            logger.debug("analyze_spins: No spins input provided.")
            state.reset()  # Always reset scores
            _restore_lab()
            logger.debug("analyze_spins: Scores reset due to empty spins.")
            return ("Please enter at least one number (e.g., 5, 12, 0).", "", "", "", "", "", "", "", "", "", "", "", "", "", _render_sides_of_zero_display())

        raw_spins = [spin.strip() for spin in spins_input.split(",") if spin.strip()]
        spins = []
        errors = []

        for spin in raw_spins:
            try:
                num = int(spin)
                if not (0 <= num <= 36):
                    errors.append(f"Error: '{spin}' is out of range. Use numbers between 0 and 36.")
                    continue
                spins.append(str(num))
            except ValueError:
                errors.append(f"Error: '{spin}' is not a valid number. Use whole numbers (e.g., 5, 12, 0).")
                continue

        if errors:
            error_msg = "\n".join(errors)
            logger.debug(f"analyze_spins: Errors found - {error_msg}")
            return (error_msg, "", "", "", "", "", "", "", "", "", "", "", "", "", _render_sides_of_zero_display())

        if not spins:
            logger.debug("analyze_spins: No valid spins found.")
            state.reset()  # Always reset scores
            _restore_lab()
            logger.debug("analyze_spins: Scores reset due to no valid spins.")
            return ("No valid numbers found. Please enter numbers like '5, 12, 0'.", "", "", "", "", "", "", "", "", "", "", "", "", "", _render_sides_of_zero_display())

        # Always reset scores
        state.reset()
        _restore_lab()
        logger.debug("analyze_spins: Scores reset.")

        # Batch update scores for all spins
        logger.debug("analyze_spins: Updating scores batch")
        action_log = _update_scores_batch(spins)
        logger.debug(f"analyze_spins: action_log={action_log}")

        # Update state.last_spins and spin_history
        state.last_spins = spins  # Replace last_spins with current spins
        state.spin_history = action_log  # Replace spin_history with current action_log
        # Limit spin history to 100 spins
        if len(state.spin_history) > 100:
            state.spin_history = state.spin_history[-100:]
        logger.debug(f"analyze_spins: Updated state.last_spins={state.last_spins}, spin_history length={len(state.spin_history)}")
        _update_drought_counters()

        # Generate spin analysis output
        logger.debug("analyze_spins: Generating spin analysis output")
        spin_results = []
        state.selected_numbers.clear()  # Clear before rebuilding
        for idx, spin in enumerate(spins):
            spin_value = int(spin)
            hit_sections = []
            action = action_log[idx]

            # Reconstruct hit sections from increments
            for name, increment in action["increments"].get("even_money_scores", {}).items():
                if increment > 0:
                    hit_sections.append(name)
            for name, increment in action["increments"].get("dozen_scores", {}).items():
                if increment > 0:
                    hit_sections.append(name)
            for name, increment in action["increments"].get("column_scores", {}).items():
                if increment > 0:
                    hit_sections.append(name)
            for name, increment in action["increments"].get("street_scores", {}).items():
                if increment > 0:
                    hit_sections.append(name)
            for name, increment in action["increments"].get("corner_scores", {}).items():
                if increment > 0:
                    hit_sections.append(name)
            for name, increment in action["increments"].get("six_line_scores", {}).items():
                if increment > 0:
                    hit_sections.append(name)
            for name, increment in action["increments"].get("split_scores", {}).items():
                if increment > 0:
                    hit_sections.append(name)
            if spin_value in action["increments"].get("scores", {}):
                hit_sections.append(f"Straight Up {spin}")
            for name, increment in action["increments"].get("side_scores", {}).items():
                if increment > 0:
                    hit_sections.append(name)

            # Add neighbor information
            if spin_value in current_neighbors:
                left, right = current_neighbors[spin_value]
                hit_sections.append(f"Left Neighbor: {left}")
                hit_sections.append(f"Right Neighbor: {right}")

            spin_results.append(f"Spin {spin} hits: {', '.join(hit_sections)}\nTotal sections hit: {len(hit_sections)}")
        state.selected_numbers = set(int(s) for s in state.last_spins if s.isdigit())  # Sync with last_spins

        spin_analysis_output = "\n".join(spin_results)
        logger.debug(f"analyze_spins: spin_analysis_output='{spin_analysis_output}'")
        even_money_output = "Even Money Bets:\n" + "\n".join(f"{name}: {score}" for name, score in state.even_money_scores.items())
        logger.debug(f"analyze_spins: even_money_output='{even_money_output}'")
        dozens_output = "Dozens:\n" + "\n".join(f"{name}: {score}" for name, score in state.dozen_scores.items())
        logger.debug(f"analyze_spins: dozens_output='{dozens_output}'")
        columns_output = "Columns:\n" + "\n".join(f"{name}: {score}" for name, score in state.column_scores.items())
        logger.debug(f"analyze_spins: columns_output='{columns_output}'")
        streets_output = "Streets:\n" + "\n".join(f"{name}: {score}" for name, score in state.street_scores.items() if score > 0)
        logger.debug(f"analyze_spins: streets_output='{streets_output}'")
        corners_output = "Corners:\n" + "\n".join(f"{name}: {score}" for name, score in state.corner_scores.items() if score > 0)
        logger.debug(f"analyze_spins: corners_output='{corners_output}'")
        six_lines_output = "Double Streets:\n" + "\n".join(f"{name}: {score}" for name, score in state.six_line_scores.items() if score > 0)
        logger.debug(f"analyze_spins: six_lines_output='{six_lines_output}'")
        splits_output = "Splits:\n" if any(score > 0 for score in state.split_scores.values()) else "Splits: No hits yet.\n"
        splits_output += "\n".join(f"{name}: {score}" for name, score in state.split_scores.items() if score > 0)
        logger.debug(f"analyze_spins: splits_output='{splits_output}'")
        sides_output = "Sides of Zero:\n" + "\n".join(f"{name}: {score}" for name, score in state.side_scores.items())
        logger.debug(f"analyze_spins: sides_output='{sides_output}'")

        spin_analysis_output = "\n".join(spin_results)
        
        # Use HTML Rank Tables for Aggregated Scores
        even_money_output = render_rank_table(state.even_money_scores, "Even Money Trends")
        dozens_output = render_rank_table(state.dozen_scores, "Dozen Trends")
        columns_output = render_rank_table(state.column_scores, "Column Trends")
        
        # Filter streets/corners/six_lines/splits to show only those with hits to save space
        streets_output = render_rank_table({k:v for k,v in state.street_scores.items() if v > 0}, "Active Street Hits")
        corners_output = render_rank_table({k:v for k,v in state.corner_scores.items() if v > 0}, "Active Corner Hits")
        six_lines_output = render_rank_table({k:v for k,v in state.six_line_scores.items() if v > 0}, "Double Street Hits")
        splits_output = render_rank_table({k:v for k,v in state.split_scores.items() if v > 0}, "Active Split Hits")
        sides_output = render_rank_table(state.side_scores, "Wheel Side Trends")
        
        # Use the updated function that contains the 'star-pin' logic
        straight_up_html = create_strongest_numbers_with_neighbours_table()
        
        # Prepare the local dataframe for the undo-grid
        undo_grid_df = pd.DataFrame(list(state.scores.items()), columns=["Number", "Score"])
        undo_grid_df = undo_grid_df[undo_grid_df["Score"] > 0].sort_values(by="Score", ascending=False)

        top_18_df = undo_grid_df.head(18).sort_values(by="Number", ascending=True)
        numbers = top_18_df["Number"].tolist()
        if len(numbers) < 18:
            numbers.extend([""] * (18 - len(numbers)))
        grid_data = [numbers[i::3] for i in range(3)]

        # Updated Styling: Changed color to white and added text-shadow for maximum readability
        top_18_html = "<h3 style='color: #ffffff; text-align: center; font-weight: 900; text-shadow: 2px 2px 4px rgba(0,0,0,0.5);'>🔝 Top 18 Strongest Numbers (Sorted Low to High)</h3>"
        top_18_html += '<table border="1" style="border-collapse: collapse; text-align: center; width: 100%; background-color: #222; color: #ffffff; border: 2px solid #4caf50;">'
        for row in grid_data:
            top_18_html += "<tr>"
            for num in row:
                # Making the numbers within the grid bold and white
                top_18_html += f'<td style="padding: 12px; width: 40px; font-weight: bold; font-size: 18px; color: #ffffff; border: 1px solid #444;">{num}</td>'
            top_18_html += "</tr>"
        top_18_html += "</table>"
        logger.debug(f"analyze_spins: top_18_html generated")
        logger.debug("analyze_spins: Getting strongest numbers")
        strongest_numbers_output = get_strongest_numbers_with_neighbors(3)
        logger.debug(f"analyze_spins: strongest_numbers_output='{strongest_numbers_output}'")

        logger.debug("analyze_spins: Generating dynamic_table_html")
        dynamic_table_html = _create_dynamic_table(strategy_name, neighbours_count)
        logger.debug(f"analyze_spins: dynamic_table_html generated")

        logger.debug("analyze_spins: Generating strategy_output")
        strategy_output = _show_strategy_recommendations(strategy_name, neighbours_count, *checkbox_args)
        logger.debug(f"analyze_spins: Strategy output = {strategy_output}")

        logger.debug("analyze_spins: Returning results")
        return (spin_analysis_output, even_money_output, dozens_output, columns_output,
                streets_output, corners_output, six_lines_output, splits_output, sides_output,
                straight_up_html, top_18_html, strongest_numbers_output, dynamic_table_html, strategy_output, _render_sides_of_zero_display())
    except Exception as e:
        logger.error(
            f"analyze_spins: Unexpected error: {str(e)}\n{traceback.format_exc()}"
        )
        gr.Warning(
            f"⚠️ Analysis error (your spins are preserved — you can keep playing): "
            f"{type(e).__name__}: {str(e)}"
        )
        error_html = (
            "<div style='color:#ef4444;padding:8px;background:#1e293b;"
            "border-radius:4px;border:1px solid #ef4444;margin:4px 0;'>"
            "⚠️ Rendering error — your spins are preserved. "
            "Please enter another spin to continue.</div>"
        )
        blank = ""
        return (
            error_html, blank, blank, blank, blank, blank, blank, blank,
            blank, blank, blank, blank, blank, blank,
            _render_sides_of_zero_display(),
        )


def undo_last_spin(current_spins_display, undo_count, strategy_name, neighbours_count, strong_numbers_count, *checkbox_args):
    if not state.spin_history:
        return ("No spins to undo.", "", "", "", "", "", "", "", "", "", "", current_spins_display, current_spins_display, "", _create_dynamic_table(strategy_name, neighbours_count, strong_numbers_count), "", _create_color_code_table(), _update_spin_counter(), _render_sides_of_zero_display())

    try:
        undo_count = int(undo_count)
        if undo_count <= 0:
            return ("Please select a positive number of spins to undo.", "", "", "", "", "", "", "", "", "", "", current_spins_display, current_spins_display, "", _create_dynamic_table(strategy_name, neighbours_count, strong_numbers_count), "", _create_color_code_table(), _update_spin_counter(), _render_sides_of_zero_display())
        undo_count = min(undo_count, len(state.spin_history))  # Don't exceed history length

        # Undo the specified number of spins
        undone_spins = []
        for _ in range(undo_count):
            if not state.spin_history:
                break
            action = state.spin_history.pop()
            spin_value = action["spin"]
            undone_spins.append(str(spin_value))

            # Decrement scores based on recorded increments
            for category, increments in action["increments"].items():
                score_dict = getattr(state, category)
                for key, value in increments.items():
                    score_dict[key] -= value
                    if score_dict[key] < 0:  # Prevent negative scores
                        score_dict[key] = 0

            state.last_spins.pop()  # Remove from last_spins too

        spins_input = ", ".join(state.last_spins) if state.last_spins else ""
        spin_analysis_output = f"Undo successful: Removed {undo_count} spin(s) - {', '.join(undone_spins)}"

        # Updated to use the new HTML Reactor tables for sorting/ranking after Undo
        even_money_output = render_rank_table(state.even_money_scores, "Even Money Trends")
        dozens_output = render_rank_table(state.dozen_scores, "Dozen Trends")
        columns_output = render_rank_table(state.column_scores, "Column Trends")
        streets_output = render_rank_table({k:v for k,v in state.street_scores.items() if v > 0}, "Active Street Hits")
        corners_output = render_rank_table({k:v for k,v in state.corner_scores.items() if v > 0}, "Active Corner Hits")
        six_lines_output = render_rank_table({k:v for k,v in state.six_line_scores.items() if v > 0}, "Double Street Hits")
        splits_output = render_rank_table({k:v for k,v in state.split_scores.items() if v > 0}, "Active Split Hits")
        sides_output = render_rank_table(state.side_scores, "Wheel Side Trends")
        
        # Use the updated function that contains the 'star-pin' logic
        straight_up_html = create_strongest_numbers_with_neighbours_table()
        
        # Local DF for the head(18) logic
        load_temp_df = pd.DataFrame(list(state.scores.items()), columns=["Number", "Score"])
        load_temp_df = load_temp_df[load_temp_df["Score"] > 0].sort_values(by="Score", ascending=False)

        top_18_df = load_temp_df.head(18)
        top_18_html = top_18_df.to_html(index=False, classes="scrollable-table")
        strongest_numbers_output = ", ".join([str(int(row["Number"])) for _, row in load_temp_df.head(3).iterrows() if row["Score"] > 0]) or "No numbers have hit yet."
        dynamic_table_html = _create_dynamic_table(strategy_name, neighbours_count, strong_numbers_count)

        logger.debug(f"undo_last_spin: Generating strategy recommendations for {strategy_name}")
        strategy_output = _show_strategy_recommendations(strategy_name, neighbours_count, strong_numbers_count, *checkbox_args)

        return (spin_analysis_output, even_money_output, dozens_output, columns_output,
            streets_output, corners_output, six_lines_output, splits_output, sides_output,
            straight_up_html, top_18_html, strongest_numbers_output, spins_input, spins_input,
            dynamic_table_html, strategy_output, _create_color_code_table(), _update_spin_counter(), _render_sides_of_zero_display())
    except ValueError:
        return ("Error: Invalid undo count. Please use a positive number.", "", "", "", "", "", "", "", "", "", "", current_spins_display, current_spins_display, "", _create_dynamic_table(strategy_name, neighbours_count, strong_numbers_count), "", _create_color_code_table(), _update_spin_counter(), _render_sides_of_zero_display())
    except (TypeError, AttributeError, KeyError, IndexError) as e:
        logger.error(f"undo_last_spin: Unexpected error: {str(e)}")
        return (f"Unexpected error during undo: {str(e)}", "", "", "", "", "", "", "", "", "", "", current_spins_display, current_spins_display, "", _create_dynamic_table(strategy_name, neighbours_count, strong_numbers_count), "", _create_color_code_table(), _update_spin_counter(), _render_sides_of_zero_display())


def clear_spins():
    state.selected_numbers.clear()
    state.last_spins = []
    state.spin_history = []  # Clear spin history as well
    state.side_scores = {"Left Side of Zero": 0, "Right Side of Zero": 0}  # Reset side scores
    state.scores = {n: 0 for n in range(37)}  # Reset straight-up scores
    state.sniper_locked = False
    state.sniper_locked_misses = 0
    
    # --- Reset Non-Repeater Memory ---
    state.current_non_repeaters.clear()
    state.previous_non_repeaters.clear()
    state.nr_last_spin_count = 0
    if hasattr(state, 'nr_mem_in'): state.nr_mem_in = []
    if hasattr(state, 'nr_mem_out'): state.nr_mem_out = []
    if hasattr(state, 'nr_mem_spin_in'): state.nr_mem_spin_in = 0
    if hasattr(state, 'nr_mem_spin_out'): state.nr_mem_spin_out = 0
    
    ts = int(time.time() * 1000)
    js_clear = f'<script id="pin-clear-{ts}">localStorage.setItem("wp_rank_pins_v3","[]"); localStorage.setItem("wp_num_pins_v3","[]"); if(typeof fastUpdateWatchlist==="function") fastUpdateWatchlist();</script>'
    return "", "", "Spins cleared successfully!", "<h4>Last Spins</h4><p>No spins yet.</p>", _update_spin_counter(), _render_sides_of_zero_display(), js_clear


def generate_random_spins(num_spins, current_spins_display, last_spin_count):
    try:
        num_spins = int(num_spins)
        # Fixed: Added the missing IF statement and corrected indentation
        if num_spins <= 0:
            return current_spins_display, current_spins_display, "Please select a number of spins greater than 0.", _update_spin_counter(), _render_sides_of_zero_display()

        new_spins = [str(random.randint(0, 36)) for _ in range(num_spins)]
        # Update scores for the new spins
        _update_scores_batch(new_spins)

        if current_spins_display and current_spins_display.strip():
            current_spins = current_spins_display.split(", ")
            updated_spins = current_spins + new_spins
        else:
            updated_spins = new_spins

        # Update state.last_spins
        state.last_spins = updated_spins  # Replace the list entirely
        spins_text = ", ".join(updated_spins)
        logger.debug(f"generate_random_spins: Setting spins_textbox to '{spins_text}'")
        return spins_text, spins_text, f"Generated {num_spins} random spins: {', '.join(new_spins)}", _update_spin_counter(), _render_sides_of_zero_display()
    except ValueError:
        logger.debug("generate_random_spins: Invalid number of spins entered.")
        return current_spins_display, current_spins_display, "Please enter a valid number of spins.", _update_spin_counter(), _render_sides_of_zero_display()
    except (TypeError, AttributeError, KeyError) as e:
        logger.error(f"generate_random_spins: Unexpected error: {str(e)}")
        return current_spins_display, current_spins_display, f"Error generating spins: {str(e)}", _update_spin_counter(), _render_sides_of_zero_display()


def play_specific_numbers(numbers_input, number_type, spins_display, last_spin_count):
    """
    Add hot or cold numbers to the spins list and update the UI.
    
    Args:
        numbers_input (str): Comma-separated string of numbers (e.g., "1, 3, 5").
        number_type (str): "Hot" or "Cold" to indicate the type of numbers.
        spins_display (str): Current spins display string.
        last_spin_count (int): Number of spins to consider for display.
    
    Returns:
        tuple: Updated spins_display, spins_textbox, casino_data_output, spin_counter, sides_of_zero_display.
    """
    try:
        # Debug: Track how many times this function is called
        state.play_specific_numbers_counter += 1
        logger.debug(f"play_specific_numbers called (count: {state.play_specific_numbers_counter}) for {number_type} numbers")

        # Parse the input numbers
        if not numbers_input or not numbers_input.strip():
            return (
                spins_display,
                spins_display,
                f"<p>No {number_type.lower()} numbers provided to play.</p>",
                _update_spin_counter(),
                _render_sides_of_zero_display()
            )

        # Split and clean the input
        numbers = [num.strip() for num in numbers_input.split(",") if num.strip()]
        if not numbers:
            return (
                spins_display,
                spins_display,
                f"<p>No valid {number_type.lower()} numbers provided.</p>",
                _update_spin_counter(),
                _render_sides_of_zero_display()
            )

        # Validate numbers (must be integers between 0 and 36)
        valid_numbers = []
        for num in numbers:
            try:
                n = int(num)
                if 0 <= n <= 36:
                    valid_numbers.append(str(n))
                else:
                    logger.debug(f"Invalid {number_type.lower()} number: {num}. Must be between 0 and 36.")
            except ValueError:
                logger.debug(f"Invalid {number_type.lower()} number: {num}. Must be an integer.")
                continue

        if not valid_numbers:
            return (
                spins_display,
                spins_display,
                f"<p>No valid {number_type.lower()} numbers to play. Numbers must be between 0 and 36.</p>",
                _update_spin_counter(),
                _render_sides_of_zero_display()
            )

        # Update state.last_spins
        # Append the valid numbers to state.last_spins
        state.last_spins.extend(valid_numbers)
        
        # Update spins_display to match state.last_spins
        new_spins_display = ", ".join(state.last_spins) if state.last_spins else ""
        
        # Update casino_data_output with a confirmation message
        casino_message = f"<p>Played {number_type.lower()} numbers: {', '.join(valid_numbers)}</p>"
        
        # Update spin_counter and sides_of_zero_display
        new_spin_counter = _update_spin_counter()
        new_sides_of_zero = _render_sides_of_zero_display()

        logger.debug(f"Played {number_type.lower()} numbers: {valid_numbers}")
        logger.debug(f"Updated state.last_spins: {state.last_spins}")

        return (
            new_spins_display,  # spins_display
            new_spins_display,  # spins_textbox
            casino_message,     # casino_data_output
            new_spin_counter,   # spin_counter
            new_sides_of_zero   # sides_of_zero_display
        )

    except Exception as e:
        logger.error(f"Error in play_specific_numbers: {str(e)}")
        return (
            spins_display,
            spins_display,
            f"<p>Error playing {number_type.lower()} numbers: {str(e)}</p>",
            _update_spin_counter(),
            _render_sides_of_zero_display()
        )
