"""WheelPulsePro – casino data management.

Extracted from app.py.
"""

import logging

import gradio as gr

logger = logging.getLogger("wheelPulsePro")

_state = None


def init(state_obj):
    """Inject the shared RouletteState instance."""
    global _state
    _state = state_obj


def update_casino_data(spins_count, even_percent, odd_percent, red_percent, black_percent, low_percent, high_percent, dozen1_percent, dozen2_percent, dozen3_percent, col1_percent, col2_percent, col3_percent, use_winners):
    """Parse casino data inputs, update state, and generate HTML output."""
    try:
        _state.casino_data["spins_count"] = int(spins_count)
        _state.use_casino_winners = use_winners

        # Remove Hot/Cold Numbers parsing
        _state.casino_data["hot_numbers"] = {}
        _state.casino_data["cold_numbers"] = {}

        # Parse percentages from dropdowns
        def parse_percent(value, category, key):
            try:
                return float(value) if value != "00" else 0.0
            except ValueError:
                raise ValueError(f"Invalid {category} percentage for {key}: {value}")

        # Even/Odd
        even_val = parse_percent(even_percent, "Even vs Odd", "Even")
        odd_val = parse_percent(odd_percent, "Even vs Odd", "Odd")
        _state.casino_data["even_odd"] = {"Even": even_val, "Odd": odd_val}
        has_even_odd = even_val > 0 or odd_val > 0

        # Red/Black
        red_val = parse_percent(red_percent, "Red vs Black", "Red")
        black_val = parse_percent(black_percent, "Red vs Black", "Black")
        _state.casino_data["red_black"] = {"Red": red_val, "Black": black_val}
        has_red_black = red_val > 0 or black_val > 0

        # Low/High
        low_val = parse_percent(low_percent, "Low vs High", "Low")
        high_val = parse_percent(high_percent, "Low vs High", "High")
        _state.casino_data["low_high"] = {"Low": low_val, "High": high_val}
        has_low_high = low_val > 0 or high_val > 0

        # Dozens
        d1_val = parse_percent(dozen1_percent, "Dozens", "1st Dozen")
        d2_val = parse_percent(dozen2_percent, "Dozens", "2nd Dozen")
        d3_val = parse_percent(dozen3_percent, "Dozens", "3rd Dozen")
        _state.casino_data["dozens"] = {"1st Dozen": d1_val, "2nd Dozen": d2_val, "3rd Dozen": d3_val}
        has_dozens = d1_val > 0 or d2_val > 0 or d3_val > 0

        # Columns
        c1_val = parse_percent(col1_percent, "Columns", "1st Column")
        c2_val = parse_percent(col2_percent, "Columns", "2nd Column")
        c3_val = parse_percent(col3_percent, "Columns", "3rd Column")
        _state.casino_data["columns"] = {"1st Column": c1_val, "2nd Column": c2_val, "3rd Column": c3_val}
        has_columns = c1_val > 0 or c2_val > 0 or c3_val > 0

        # Check for empty data when highlighting is enabled
        if use_winners and not any([has_even_odd, has_red_black, has_low_high, has_dozens, has_columns]):
            gr.Warning("Highlight Casino Winners is enabled, but no casino data is provided. Enter percentages to see highlights.")
            return "<p>Warning: No casino data provided for highlighting. Please enter percentages for Even/Odd, Red/Black, Low/High, Dozens, or Columns.</p>"

        # Generate HTML Output
        output = f"<h4>Casino Data Insights (Last {spins_count} Spins):</h4>"
        for key, name, has_data in [
            ("even_odd", "Even vs Odd", has_even_odd),
            ("red_black", "Red vs Black", has_red_black),
            ("low_high", "Low vs High", has_low_high)
        ]:
            if has_data:
                winner = max(_state.casino_data[key], key=_state.casino_data[key].get)
                output += f"<p>{name}: " + " vs ".join(
                    f"<b>{v:.1f}%</b>" if k == winner else f"{v:.1f}%" for k, v in _state.casino_data[key].items()
                ) + f" (Winner: {winner})</p>"
            else:
                output += f"<p>{name}: Not set</p>"
        for key, name, has_data in [
            ("dozens", "Dozens", has_dozens),
            ("columns", "Columns", has_columns)
        ]:
            if has_data:
                winner = max(_state.casino_data[key], key=_state.casino_data[key].get)
                output += f"<p>{name}: " + " vs ".join(
                    f"<b>{v:.1f}%</b>" if k == winner else f"{v:.1f}%" for k, v in _state.casino_data[key].items()
                ) + f" (Winner: {winner})</p>"
            else:
                output += f"<p>{name}: Not set</p>"
        logger.debug(f"Generated HTML Output: {output}")
        return output
    except ValueError as e:
        return f"<p>Error: {str(e)}</p>"
    except Exception as e:
        return f"<p>Unexpected error parsing casino data: {str(e)}</p>"


def reset_casino_data():
    """Reset casino data to defaults and clear UI inputs."""
    _state.casino_data = {
        "spins_count": 100,
        "hot_numbers": {},
        "cold_numbers": {},
        "even_odd": {"Even": 0.0, "Odd": 0.0},
        "red_black": {"Red": 0.0, "Black": 0.0},
        "low_high": {"Low": 0.0, "High": 0.0},
        "dozens": {"1st Dozen": 0.0, "2nd Dozen": 0.0, "3rd Dozen": 0.0},
        "columns": {"1st Column": 0.0, "2nd Column": 0.0, "3rd Column": 0.0}
    }
    _state.use_casino_winners = False
    return (
        "100",  # spins_count_dropdown
        "",     # hot_numbers_input
        "",     # cold_numbers_input
        "",     # even_odd_input
        "",     # red_black_input
        "",     # low_high_input
        "",     # dozens_input
        "",     # columns_input
        False,  # use_winners_checkbox
        "<p>Casino data reset to defaults.</p>"  # casino_data_output
    )
