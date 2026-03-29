"""WheelPulsePro – HTML rendering helpers.

Pure rendering functions extracted from app.py.  Each function receives all
required data as explicit parameters so that this module can be imported
without Gradio.
"""

import heapq
import json
import math
import re

from wheelpulsepro.state import CUSTOM_PROGRESSIONS, get_custom_progression_for_bet


def format_spins_as_html(spins, num_to_show, show_trends, colors, DOZENS, COLUMNS, EVEN_MONEY):
    """Format the spins as HTML with color-coded display, animations, and pattern badges."""
    if not spins:
        return "<h4>Last Spins</h4><p>No spins yet.</p>"
    
    # Split the spins string into a list and reverse to get the most recent first
    spin_list = spins.split(", ") if spins else []
    spin_list = spin_list[-int(num_to_show):] if spin_list else []  # Take the last N spins
    
    if not spin_list:
        return "<h4>Last Spins</h4><p>No spins yet.</p>"
    
    # Pattern detection for consecutive colors, dozens, columns, even/odd, and high/low (only if show_trends is True)
    patterns_by_index = {}  # Dictionary to store all patterns starting at each index
    if show_trends:
        for i in range(len(spin_list) - 2):
            if i >= len(spin_list):
                break
            window = spin_list[i:i+3]
            # Convert window spins to ints; skip this window on non-numeric values
            try:
                window_nums = [int(s) for s in window]
            except (ValueError, TypeError):
                continue
            # Skip pattern detection for windows containing zero (0 is neither a dozen, column, even/odd, nor high/low)
            if 0 in window_nums:
                continue
            # Check for consecutive colors
            if colors.get(window[0], "") == colors.get(window[1], "") == colors.get(window[2], ""):
                color_name = colors.get(window[0], '').capitalize()
                if color_name:  # Ensure color_name is not empty
                    if i not in patterns_by_index:
                        patterns_by_index[i] = []
                    patterns_by_index[i].append(f"3 {color_name}s in a Row")
            # Check for consecutive dozens
            dozen_hits = [next((name for name, nums in DOZENS.items() if n in nums), None) for n in window_nums]
            if None not in dozen_hits and len(set(dozen_hits)) == 1:
                if i not in patterns_by_index:
                    patterns_by_index[i] = []
                patterns_by_index[i].append(f"{dozen_hits[0]} Streak")
            # Check for consecutive columns
            column_hits = [next((name for name, nums in COLUMNS.items() if n in nums), None) for n in window_nums]
            if None not in column_hits and len(set(column_hits)) == 1:
                if i not in patterns_by_index:
                    patterns_by_index[i] = []
                patterns_by_index[i].append(f"{column_hits[0]} Streak")
            # Check for consecutive even/odd
            even_odd_hits = [next((name for name, nums in EVEN_MONEY.items() if name in ["Even", "Odd"] and n in nums), None) for n in window_nums]
            if None not in even_odd_hits and len(set(even_odd_hits)) == 1:
                if i not in patterns_by_index:
                    patterns_by_index[i] = []
                patterns_by_index[i].append(f"3 {even_odd_hits[0]}s in a Row")
            # Check for consecutive high/low
            high_low_hits = [next((name for name, nums in EVEN_MONEY.items() if name in ["High", "Low"] and n in nums), None) for n in window_nums]
            if None not in high_low_hits and len(set(high_low_hits)) == 1:
                if i not in patterns_by_index:
                    patterns_by_index[i] = []
                patterns_by_index[i].append(f"3 {high_low_hits[0]}s in a Row")
    
    # Format each spin as a colored span
    html_spins = []
    for i, spin in enumerate(spin_list):
        color = colors.get(spin.strip(), "black")  # Default to black if not found
        # Apply flip, flash, and new-spin classes to the newest spin (last in the list)
        if i == len(spin_list) - 1:
            class_attr = f'fade-in flip flash new-spin spin-{color} {color}'
        else:
            class_attr = f'fade-in {color}'
        # Add all pattern badges for this spin if show_trends is True
        pattern_badges = ""
        if show_trends and i in patterns_by_index:
            for pattern_text in patterns_by_index[i]:
                pattern_badges += f'<span class="pattern-badge" title="{pattern_text}" style="background-color: #ffd700; color: #333; padding: 2px 5px; border-radius: 3px; font-size: 10px; margin-left: 5px;">{pattern_text}</span>'
        html_spins.append(f'<span class="{class_attr}" style="background-color: {color}; color: white; padding: 2px 5px; margin: 2px; border-radius: 3px; display: inline-block;">{spin}{pattern_badges}</span>')
    
    # Wrap the spins in a div with flexbox to enable wrapping, and add a title
    html_output = f'<h4 style="margin-bottom: 5px;">Last Spins</h4><div style="display: flex; flex-wrap: wrap; gap: 5px;">{"".join(html_spins)}</div>'
    
    # Add JavaScript to remove fade-in, flash, flip, and new-spin classes after animations
    html_output += '''
    <script>
        document.querySelectorAll('.fade-in').forEach(element => {
            setTimeout(() => {
                element.classList.remove('fade-in');
            }, 500);
        });
        document.querySelectorAll('.flash').forEach(element => {
            setTimeout(() => {
                element.classList.remove('flash');
            }, 300);
        });
        document.querySelectorAll('.flip').forEach(element => {
            setTimeout(() => {
                element.classList.remove('flip');
            }, 500);
        });
        document.querySelectorAll('.new-spin').forEach(element => {
            setTimeout(() => {
                element.classList.remove('new-spin');
            }, 1000);
        });
    </script>
    '''
    
    return html_output


def render_sides_of_zero_display(state, colors, current_neighbors, has_active_cards=False):
    left_hits = state.side_scores["Left Side of Zero"]
    zero_hits = state.scores[0]
    right_hits = state.side_scores["Right Side of Zero"]
    
    # Calculate the maximum hit count for scaling
    max_hits = max(left_hits, zero_hits, right_hits, 1)  # Avoid division by zero
    
    # Calculate progress percentages (0 to 100)
    left_progress = (left_hits / max_hits) * 100 if max_hits > 0 else 0
    zero_progress = (zero_hits / max_hits) * 100 if max_hits > 0 else 0
    right_progress = (right_hits / max_hits) * 100 if max_hits > 0 else 0
    
    # Define the order of numbers for the European roulette wheel
    original_order = [5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26, 0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10]
    left_side = original_order[:18]  # 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26
    zero = [0]
    right_side = original_order[19:]  # 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10
    wheel_order = left_side + zero + right_side  # Used for wheel SVG, now 5, ..., 26, 0, 32, ..., 10
    
    # Define betting sections
    jeu_0 = [12, 35, 3, 26, 0, 32, 15]
    voisins_du_zero = [22, 18, 29, 7, 28, 12, 35, 3, 26, 0, 32, 15, 19, 4, 21, 2, 25]
    orphelins = [17, 34, 6, 1, 20, 14, 31, 9]
    tiers_du_cylindre = [27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33]
    
    # Calculate hit counts for each betting section
    jeu_0_hits = sum(state.scores.get(num, 0) for num in jeu_0)
    voisins_du_zero_hits = sum(state.scores.get(num, 0) for num in voisins_du_zero)
    orphelins_hits = sum(state.scores.get(num, 0) for num in orphelins)
    tiers_du_cylindre_hits = sum(state.scores.get(num, 0) for num in tiers_du_cylindre)
    
    # Determine the winning section for Left/Right Side
    winning_section = "Left Side" if left_hits > right_hits else "Right Side" if right_hits > left_hits else None
    
    # Get the latest spin for bounce effect and wheel rotation
    latest_spin = int(state.last_spins[-1]) if state.last_spins else None
    latest_spin_angle = 0
    has_latest_spin = latest_spin is not None
    if latest_spin is not None:
        index = original_order.index(latest_spin) if latest_spin in original_order else 0
        latest_spin_angle = (index * (360 / 37)) + 90  # Adjust for zero at bottom
    
    # Prepare numbers with hit counts
    wheel_numbers = [(num, state.scores.get(num, 0)) for num in wheel_order]
    
    # Calculate maximum hits for scaling highlights
    max_segment_hits = max(state.scores.values(), default=1)
    
    # Hot & Cold Numbers Display with Ties Handling and Cap
    hot_cold_html = '<div class="hot-cold-numbers" style="margin-top: 10px; padding: 8px; background-color: #f9f9f9; border: 1px solid #d3d3d3; border-radius: 5px; display: flex; flex-wrap: wrap; gap: 5px; justify-content: center;">'
    if state.last_spins and len(state.last_spins) >= 1:
        # Use state.scores for consistency with Strongest Numbers Tables
        hit_counts = {n: state.scores.get(n, 0) for n in range(37)}
        
        # Hot numbers: Sort by score descending, number ascending
        sorted_hot = sorted(hit_counts.items(), key=lambda x: (-x[1], x[0]))
        # Take top 5, but include all tied numbers at the 5th position, capped at 28
        hot_numbers = []
        if len(sorted_hot) >= 5:
            fifth_score = sorted_hot[4][1]  # Score of the 5th number
            for num, score in sorted_hot:
                if len(hot_numbers) < 5 or score == fifth_score:
                    if score > 0:  # Only include numbers with hits
                        hot_numbers.append((num, score))
                else:
                    break
        else:
            hot_numbers = [(num, score) for num, score in sorted_hot if score > 0]
        hot_numbers = hot_numbers[:28]  # Cap at 28 to keep display compact
        
        # Cold numbers: Sort by score ascending, number ascending
        sorted_cold = sorted(hit_counts.items(), key=lambda x: (x[1], x[0]))
        # Take top 5, but include all tied numbers at the 5th position, capped at 15
        cold_numbers = []
        if len(sorted_cold) >= 5:
            fifth_score = sorted_cold[4][1]  # Score of the 5th number
            for num, score in sorted_cold:
                if len(cold_numbers) < 5 or score == fifth_score:
                    cold_numbers.append((num, score))
                else:
                    break
        else:
            cold_numbers = [(num, score) for num, score in sorted_cold]
        cold_numbers = cold_numbers[:15]  # Cap at 15 to prevent overflow
        
        # Hot numbers display
        hot_cold_html += '<div style="flex: 1; min-width: 150px;">'
        hot_cold_html += '<span style="display: block; font-weight: bold; font-size: 14px; background: linear-gradient(to right, #ff0000, #ff4500); color: white; padding: 2px 8px; border-radius: 3px; margin-bottom: 5px;">🔥 Hot</span>'
        hot_display = []
        for num, hits in hot_numbers:
            hot_display.append(
                f'<span class="number-badge hot-badge" style="display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; background-color: #ff4444; color: white; border-radius: 50%; font-size: 10px; font-weight: bold; margin: 0 1px; position: relative; box-shadow: 0 2px 4px rgba(0,0,0,0.3); transition: transform 0.2s ease;">{num}<span class="hit-badge" style="position: absolute; top: -6px; right: -6px; background-color: #ff0000; color: white; border-radius: 50%; width: 16px; height: 16px; line-height: 16px; font-size: 8px; text-align: center;">{hits}</span></span>'
            )
        hot_cold_html += "".join(hot_display) if hot_display else '<span style="color: #666;">None</span>'
        hot_cold_html += '</div>'
        
        # Cold numbers display
        hot_cold_html += '<div style="flex: 1; min-width: 150px;">'
        hot_cold_html += '<span style="display: block; font-weight: bold; font-size: 14px; background: linear-gradient(to right, #1e90ff, #87cefa); color: white; padding: 2px 8px; border-radius: 3px; margin-bottom: 5px;">🧊 Cold</span>'
        cold_display = []
        for num, hits in cold_numbers:
            cold_display.append(
                f'<span class="number-badge cold-badge" style="display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; background-color: #87cefa; color: white; border-radius: 50%; font-size: 10px; font-weight: bold; margin: 0 1px; position: relative; box-shadow: 0 2px 4px rgba(0,0,0,0.3); transition: transform 0.2s ease;">{num}<span class="hit-badge" style="position: absolute; top: -6px; right: -6px; background-color: #4682b4; color: white; border-radius: 50%; width: 16px; height: 16px; line-height: 16px; font-size: 8px; text-align: center;">{hits}</span></span>'
            )
        hot_cold_html += "".join(cold_display) if cold_display else '<span style="color: #666;">None</span>'
        hot_cold_html += '</div>'
    else:
        hot_cold_html += '<p style="color: #666; font-size: 12px;">No spins yet to analyze.</p>'
    hot_cold_html += '</div>'
    
    # Generate HTML for the number list
    def generate_number_list(numbers):
        if not numbers:
            return '<div class="number-list">No numbers</div>'
        
        number_html = []
        # Use left_side as is for display
        display_left_side = left_side  # Already 5, 24, 16, ..., 26
        display_wheel_order = display_left_side + zero + right_side  # 5, ..., 26, 0, 32, ..., 10
        display_numbers = [(num, state.scores.get(num, 0)) for num in display_wheel_order]
        
        for num, hits in display_numbers:
            color = colors.get(str(num), "black")
            badge = f'<span class="hit-badge">{hits}</span>' if hits > 0 else ''
            class_name = "number-item" + (" zero-number" if num == 0 else "") + (" bounce" if num == latest_spin else "")
            number_html.append(
                f'<span class="{class_name}" style="background-color: {color}; color: white;" data-hits="{hits}" data-number="{num}">{num}{badge}</span>'
            )
        
        return f'<div class="number-list">{"".join(number_html)}</div>'
    
    number_list = generate_number_list(wheel_numbers)
    
    # Generate SVG for the roulette wheel
    wheel_svg = '<div class="roulette-wheel-container">'
    wheel_svg += '<svg id="roulette-wheel" width="340" height="340" viewBox="0 0 340 340" style="transform: rotate(90deg);">'  # Size unchanged
    
    # Add background arcs for Left Side and Right Side
    left_start_angle = 0
    left_end_angle = 180
    left_start_rad = left_start_angle * (math.pi / 180)
    left_end_rad = left_end_angle * (math.pi / 180)
    left_x1 = 170 + 145 * math.cos(left_start_rad)
    left_y1 = 170 + 145 * math.sin(left_start_rad)
    left_x2 = 170 + 145 * math.cos(left_end_rad)
    left_y2 = 170 + 145 * math.sin(left_end_rad)
    left_path_d = f"M 170,170 L {left_x1},{left_y1} A 145,145 0 0,1 {left_x2},{left_y2} L 170,170 Z"
    left_fill = "rgba(106, 27, 154, 0.5)" if winning_section == "Left Side" else "rgba(128, 128, 128, 0.3)"
    left_stroke = "#4A148C" if winning_section == "Left Side" else "#808080"
    wheel_svg += f'<path d="{left_path_d}" fill="{left_fill}" stroke="{left_stroke}" stroke-width="3"/>'
    
    right_start_angle = 180
    right_end_angle = 360
    right_start_rad = right_start_angle * (math.pi / 180)
    right_end_rad = right_end_angle * (math.pi / 180)
    right_x1 = 170 + 145 * math.cos(right_start_rad)
    right_y1 = 170 + 145 * math.sin(right_start_rad)
    right_x2 = 170 + 145 * math.cos(right_end_rad)
    right_y2 = 170 + 145 * math.sin(right_end_rad)
    right_path_d = f"M 170,170 L {right_x1},{right_y1} A 145,145 0 0,1 {right_x2},{right_y2} L 170,170 Z"
    right_fill = "rgba(244, 81, 30, 0.5)" if winning_section == "Right Side" else "rgba(128, 128, 128, 0.3)"
    right_stroke = "#D84315" if winning_section == "Right Side" else "#808080"
    wheel_svg += f'<path d="{right_path_d}" fill="{right_fill}" stroke="{right_stroke}" stroke-width="3"/>'
    
    # Add the wheel background
    wheel_svg += '<circle cx="170" cy="170" r="135" fill="#2e7d32"/>'
    
    # Draw the wheel segments
    angle_per_number = 360 / 37
    for i, num in enumerate(original_order):
        angle = i * angle_per_number
        color = colors.get(str(num), "black")
        hits = state.scores.get(num, 0)
        stroke_width = 2 + (hits / max_segment_hits * 3) if max_segment_hits > 0 else 2
        opacity = 0.5 + (hits / max_segment_hits * 0.5) if max_segment_hits > 0 else 0.5
        stroke_color = "#FF00FF" if hits > 0 else "#FFF"
        is_winning_segment = (winning_section == "Left Side" and num in left_side) or (winning_section == "Right Side" and num in right_side)
        class_name = "wheel-segment" + (" pulse" if hits > 0 else "") + (" winning-segment" if is_winning_segment else "")
        rad = angle * (math.pi / 180)
        next_rad = (angle + angle_per_number) * (math.pi / 180)
        x1 = 170 + 135 * math.cos(rad)
        y1 = 170 + 135 * math.sin(rad)
        x2 = 170 + 135 * math.cos(next_rad)
        y2 = 170 + 135 * math.sin(next_rad)
        x3 = 170 + 105 * math.cos(next_rad)
        y3 = 170 + 105 * math.sin(next_rad)
        x4 = 170 + 105 * math.cos(rad)
        y4 = 170 + 105 * math.sin(rad)
        path_d = f"M 170,170 L {x1},{y1} A 135,135 0 0,1 {x2},{y2} L {x3},{y3} A 105,105 0 0,0 {x4},{y4} Z"
        wheel_svg += f'<path class="{class_name}" data-number="{num}" data-hits="{hits}" d="{path_d}" fill="{color}" stroke="{stroke_color}" stroke-width="{stroke_width}" fill-opacity="{opacity}" style="cursor: pointer;"/>'
        text_angle = angle + (angle_per_number / 2)
        text_rad = text_angle * (math.pi / 180)
        text_x = 170 + 120 * math.cos(text_rad)
        text_y = 170 + 120 * math.sin(text_rad)
        wheel_svg += f'<text x="{text_x}" y="{text_y}" font-size="8" fill="white" text-anchor="middle" transform="rotate({text_angle + 90} {text_x},{text_y})">{num}</text>'
        hit_text_x = 170 + 90 * math.cos(text_rad)
        hit_text_y = 170 + 90 * math.sin(text_rad)
        wheel_svg += f'<text x="{hit_text_x}" y="{hit_text_y}" font-size="6" fill="#FFD700" text-anchor="middle" transform="rotate({text_angle + 90} {hit_text_x},{hit_text_y})">{hits if hits > 0 else ""}</text>'
    
    # Add labels for Left Side and Right Side
    left_label_angle = 90
    left_label_rad = left_label_angle * (math.pi / 180)
    left_label_x = 170 + 155 * math.cos(left_label_rad)
    left_label_y = 170 + 155 * math.sin(left_label_rad)
    wheel_svg += f'<rect x="{left_label_x - 25}" y="{left_label_y - 8}" width="50" height="16" fill="#FFF" stroke="#6A1B9A" stroke-width="1" rx="3"/>'
    wheel_svg += f'<text x="{left_label_x}" y="{left_label_y}" font-size="10" fill="#6A1B9A" text-anchor="middle" dy="3">Left: {left_hits}</text>'
    
    right_label_angle = 270
    right_label_rad = right_label_angle * (math.pi / 180)
    right_label_x = 170 + 155 * math.cos(right_label_rad)
    right_label_y = 170 + 155 * math.sin(right_label_rad)
    wheel_svg += f'<rect x="{right_label_x - 25}" y="{right_label_y - 8}" width="50" height="16" fill="#FFF" stroke="#F4511E" stroke-width="1" rx="3"/>'
    wheel_svg += f'<text x="{right_label_x}" y="{right_label_y}" font-size="10" fill="#F4511E" text-anchor="middle" dy="3">Right: {right_hits}</text>'
    
    wheel_svg += '<circle cx="170" cy="170" r="15" fill="#FFD700"/>'  # Gold center
    wheel_svg += '</svg>'
    wheel_svg += f'<div id="wheel-pointer" style="position: absolute; top: -10px; left: 168.5px; width: 3px; height: 170px; background-color: #00695C; transform-origin: bottom center;"></div>'
    wheel_svg += f'<div id="spinning-ball" style="position: absolute; width: 12px; height: 12px; background-color: #fff; border-radius: 50%; transform-origin: center center;"></div>'
    wheel_svg += f'<div id="wheel-fallback" style="display: none;">Latest Spin: {latest_spin if latest_spin is not None else "None"}</div>'
    wheel_svg += '</div>'
    
    # Add static betting sections display below the wheel with enhanced effects
    betting_sections_html = '<div class="betting-sections-container">'
    sections = [
        ("jeu_0", "Jeu 0", jeu_0, "#228B22", jeu_0_hits),
        ("voisins_du_zero", "Voisins du Zero", voisins_du_zero, "#008080", voisins_du_zero_hits),
        ("orphelins", "Orphelins", orphelins, "#800080", orphelins_hits),
        ("tiers_du_cylindre", "Tiers du Cylindre", tiers_du_cylindre, "#FFA500", tiers_du_cylindre_hits)
    ]

    # Determine the hottest section (most hits; first wins on tie)
    max_section_hits = max(jeu_0_hits, voisins_du_zero_hits, orphelins_hits, tiers_du_cylindre_hits)
    hottest_id = None
    for section_id, _, _, _, hits in sections:
        if hits == max_section_hits and max_section_hits > 0:
            hottest_id = section_id
            break

    for section_id, section_name, numbers, color, hits in sections:
        is_hottest = (section_id == hottest_id)
        # Generate the numbers list with colors and enhanced effects for numbers with hits
        numbers_html = []
        for num in numbers:
            num_color = colors.get(str(num), "black")
            hit_count = state.scores.get(num, 0)
            is_hot = hit_count > 0
            class_name = "section-number" + (" hot-number" if is_hot else "")
            if is_hottest and is_hot:
                class_name += " hottest-number"
            badge = f'<span class="number-hit-badge">{hit_count}</span>' if is_hot else ''
            numbers_html.append(f'<span class="{class_name}" style="background-color: {num_color}; color: white;" data-hits="{hit_count}" data-number="{num}">{num}{badge}</span>')
        numbers_display = "".join(numbers_html)

        # Create a static section instead of an accordion
        section_class = "betting-section hottest-section" if is_hottest else "betting-section"
        hottest_label = ' <span class="hottest-label">🔥 HOTTEST</span>' if is_hottest else ''
        hits_badge_class = "hit-badge betting-section-hits hottest-hits-badge" if is_hottest else "hit-badge betting-section-hits"
        badge = f'<span class="{hits_badge_class}">{hits}</span>' if hits > 0 else ''
        betting_sections_html += f'''
        <div class="{section_class}">
            <div class="betting-section-header" style="background-color: {color};">
                {section_name}{hottest_label}{badge}
            </div>
            <div class="betting-section-numbers">{numbers_display}</div>
        </div>
        '''
    
    betting_sections_html += '</div>'

    # L/R/Z Sequence Trail — last 20 spins classified as Left / Right / Zero
    trail_spins = [int(s) for s in state.last_spins[-20:]] if state.last_spins else []
    trail_pills_list = []
    for _spin in trail_spins:
        if _spin in left_side:
            trail_pills_list.append(("L", "#6a1b9a", _spin))
        elif _spin in right_side:
            trail_pills_list.append(("R", "#f4511e", _spin))
        else:
            trail_pills_list.append(("Z", "#00695c", _spin))

    # Current streak (consecutive same label at the end)
    _streak_label_html = ""
    if trail_pills_list:
        _last_lbl = trail_pills_list[-1][0]
        _streak_cnt = 0
        for _pill in reversed(trail_pills_list):
            if _pill[0] == _last_lbl:
                _streak_cnt += 1
            else:
                break
        _streak_clr = {"L": "#6a1b9a", "R": "#f4511e", "Z": "#00695c"}[_last_lbl]
        _streak_label_html = (
            f'<span style="display:inline-block;background:{_streak_clr};color:white;'
            f'padding:2px 9px;border-radius:12px;font-size:11px;font-weight:bold;'
            f'margin-left:8px;">Run: {_last_lbl}×{_streak_cnt}</span>'
        )

    _trail_pills_html = "".join(
        f'<span title="#{sp}" style="display:inline-flex;align-items:center;justify-content:center;'
        f'background:{clr};color:white;border-radius:12px;padding:2px 7px;'
        f'font-size:11px;font-weight:bold;margin:2px;cursor:default;">{lbl}</span>'
        for lbl, clr, sp in trail_pills_list
    )

    if _trail_pills_html:
        lrz_trail_html = (
            f'<div style="margin-top:10px;padding:8px 10px;background:#f9f9f9;'
            f'border:1px solid #d3d3d3;border-radius:6px;">'
            f'<div style="font-weight:bold;font-size:12px;margin-bottom:6px;color:#333;">'
            f'🧭 L/R/Z Sequence Trail (last {len(trail_pills_list)} spins){_streak_label_html}</div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:2px;">{_trail_pills_html}</div>'
            f'</div>'
        )
    else:
        lrz_trail_html = (
            '<div style="margin-top:10px;padding:8px 10px;background:#f9f9f9;'
            'border:1px solid #d3d3d3;border-radius:6px;color:#999;font-size:12px;">'
            '🧭 L/R/Z Sequence Trail — spin some numbers to see the trail</div>'
        )

    # Convert Python boolean to JavaScript lowercase boolean
    js_has_latest_spin = "true" if has_latest_spin else "false"

    # ── Widget a: L/R Bet Suggestion Strip ──────────────────────────────────
    # Cold side = fewer hits = overdue = suggested bet
    if left_hits < right_hits:
        _bet_suggestion = "BET LEFT"
        _cold_side = "left"
        _bet_color = "#6a1b9a"
        _bet_emoji = "⬅️"
    elif right_hits < left_hits:
        _bet_suggestion = "BET RIGHT"
        _cold_side = "right"
        _bet_color = "#f4511e"
        _bet_emoji = "➡️"
    else:
        _bet_suggestion = "⚖️ BALANCED"
        _cold_side = "both"
        _bet_color = "#555"
        _bet_emoji = "⚖️"

    _lr_left_nums = ""
    for _n in left_side:
        _pulse_cls = " lr-pulse" if _cold_side == "left" else ""
        _lr_left_nums += (
            f'<span class="lr-num{_pulse_cls}" '
            f'style="background:#6a1b9a;">{_n}</span>'
        )
    _lr_zero_num = (
        '<span class="lr-num" style="background:#00695c;">0</span>'
    )
    _lr_right_nums = ""
    for _n in right_side:
        _pulse_cls = " lr-pulse" if _cold_side == "right" else ""
        _lr_right_nums += (
            f'<span class="lr-num{_pulse_cls}" '
            f'style="background:#f4511e;">{_n}</span>'
        )

    lr_bet_strip_html = (
        f'<div style="margin-top:10px;padding:10px;background:#fff;'
        f'border:1px solid #d3d3d3;border-radius:6px;">'
        f'<div style="font-weight:bold;font-size:13px;margin-bottom:6px;color:#333;">🎲 Left/Right Bet Suggestion</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:1px;justify-content:center;margin-bottom:8px;">'
        f'{_lr_left_nums}{_lr_zero_num}{_lr_right_nums}</div>'
        f'<div style="text-align:center;font-size:18px;font-weight:900;color:{_bet_color};">'
        f'{_bet_emoji} {_bet_suggestion}</div>'
        f'<div style="text-align:center;font-size:10px;color:#888;margin-top:3px;">'
        f'Left: {left_hits} hits · Right: {right_hits} hits — cold side = overdue</div>'
        f'</div>'
    )

    # ── Widget b: L/R Momentum Indicator ────────────────────────────────────
    if trail_pills_list:
        if _last_lbl == "L" and _streak_cnt >= 3:
            _mom_label = "LEFT MOMENTUM 🔥"
            _mom_color = "#6a1b9a"
            _mom_bg = "rgba(106,27,154,0.08)"
            _mom_border = "#6a1b9a"
        elif _last_lbl == "R" and _streak_cnt >= 3:
            _mom_label = "RIGHT MOMENTUM 🔥"
            _mom_color = "#f4511e"
            _mom_bg = "rgba(244,81,30,0.08)"
            _mom_border = "#f4511e"
        else:
            _mom_label = "⚖️ BALANCED"
            _mom_color = "#555"
            _mom_bg = "#f9f9f9"
            _mom_border = "#d3d3d3"
        _mom_info = f"Current run: {_last_lbl}×{_streak_cnt}"
    else:
        _mom_label = "⚖️ BALANCED"
        _mom_color = "#555"
        _mom_bg = "#f9f9f9"
        _mom_border = "#d3d3d3"
        _mom_info = "No spins yet"

    lr_momentum_html = (
        f'<div style="margin-top:10px;padding:10px;background:{_mom_bg};'
        f'border:1px solid {_mom_border};border-radius:6px;text-align:center;">'
        f'<div style="font-weight:bold;font-size:13px;margin-bottom:4px;color:#333;">📈 L/R Momentum Indicator</div>'
        f'<div style="font-size:20px;font-weight:900;color:{_mom_color};">{_mom_label}</div>'
        f'<div style="font-size:10px;color:#888;margin-top:3px;">{_mom_info}</div>'
        f'</div>'
    )

    # ── Widget c: Last 10 Spins Mini Wheel (200×200 SVG) ────────────────────
    _last10 = [int(s) for s in state.last_spins[-10:]] if state.last_spins else []
    _last10_set = set(_last10)
    _mini_cx = 100
    _mini_r_outer = 90
    _mini_r_inner = 65
    _mini_apn = 360 / 37
    _mini_svg_parts = [
        f'<svg width="200" height="200" viewBox="0 0 200 200" style="transform:rotate(90deg);">',
        f'<circle cx="{_mini_cx}" cy="{_mini_cx}" r="{_mini_r_outer}" fill="#2e7d32"/>',
    ]
    for _mi, _mnum in enumerate(original_order):
        _ma = _mi * _mini_apn
        _mnc = colors.get(str(_mnum), "black")
        _is_hit = _mnum in _last10_set
        _mr = _ma * (math.pi / 180)
        _mnr = (_ma + _mini_apn) * (math.pi / 180)
        _mx1 = _mini_cx + _mini_r_outer * math.cos(_mr)
        _my1 = _mini_cx + _mini_r_outer * math.sin(_mr)
        _mx2 = _mini_cx + _mini_r_outer * math.cos(_mnr)
        _my2 = _mini_cx + _mini_r_outer * math.sin(_mnr)
        _mx3 = _mini_cx + _mini_r_inner * math.cos(_mnr)
        _my3 = _mini_cx + _mini_r_inner * math.sin(_mnr)
        _mx4 = _mini_cx + _mini_r_inner * math.cos(_mr)
        _my4 = _mini_cx + _mini_r_inner * math.sin(_mr)
        _mp = (
            f"M {_mini_cx},{_mini_cx} "
            f"L {_mx1:.1f},{_my1:.1f} "
            f"A {_mini_r_outer},{_mini_r_outer} 0 0,1 {_mx2:.1f},{_my2:.1f} "
            f"L {_mx3:.1f},{_my3:.1f} "
            f"A {_mini_r_inner},{_mini_r_inner} 0 0,0 {_mx4:.1f},{_my4:.1f} Z"
        )
        if _is_hit:
            _mini_svg_parts.append(
                f'<path d="{_mp}" fill="{_mnc}" fill-opacity="1" stroke="#FFD700" stroke-width="2"/>'
            )
            _mta = _ma + _mini_apn / 2
            _mtr = _mta * (math.pi / 180)
            _mtr_mid = (_mini_r_inner + _mini_r_outer) / 2
            _mtx = _mini_cx + _mtr_mid * math.cos(_mtr)
            _mty = _mini_cx + _mtr_mid * math.sin(_mtr)
            _mini_svg_parts.append(
                f'<text x="{_mtx:.1f}" y="{_mty:.1f}" font-size="7" fill="white" '
                f'text-anchor="middle" '
                f'transform="rotate({_mta + 90:.1f} {_mtx:.1f},{_mty:.1f})">{_mnum}</text>'
            )
        else:
            _mini_svg_parts.append(
                f'<path d="{_mp}" fill="#444" fill-opacity="0.35" stroke="#666" stroke-width="0.5"/>'
            )
    _mini_svg_parts.append(f'<circle cx="{_mini_cx}" cy="{_mini_cx}" r="12" fill="#FFD700"/>')
    _mini_svg_parts.append('</svg>')
    _mini_svg = "".join(_mini_svg_parts)
    _last10_label = ", ".join(str(n) for n in _last10) if _last10 else "No spins yet"
    mini_wheel_html = (
        f'<div style="margin-top:10px;padding:10px;background:#fff;'
        f'border:1px solid #d3d3d3;border-radius:6px;text-align:center;">'
        f'<div style="font-weight:bold;font-size:13px;margin-bottom:4px;color:#333;">🕐 Last 10 Spins Mini Wheel</div>'
        f'<div style="display:inline-block;">{_mini_svg}</div>'
        f'<div style="font-size:10px;color:#888;margin-top:4px;">Last 10: {_last10_label}</div>'
        f'</div>'
    )

    # ── Widget d: Neighbor Hit Cluster (last 15 spins) ──────────────────────
    _last15 = [int(s) for s in state.last_spins[-15:]] if state.last_spins else []
    _last15_set = set(_last15)
    _best_cluster = None
    _best_score = 0
    if state.last_spins:
        _checked_nums = set()
        for _cs in reversed(state.last_spins[-10:]):
            try:
                _cn = int(_cs)
            except (ValueError, TypeError):
                continue
            if _cn in _checked_nums:
                continue
            _checked_nums.add(_cn)
            if _cn not in original_order:
                continue
            _cidx = original_order.index(_cn)
            _cneighbors = [
                original_order[(_cidx - 2) % 37],
                original_order[(_cidx - 1) % 37],
                _cn,
                original_order[(_cidx + 1) % 37],
                original_order[(_cidx + 2) % 37],
            ]
            _cscore = sum(1 for _nn in _cneighbors if _nn in _last15_set)
            if _cscore > _best_score:
                _best_score = _cscore
                _best_cluster = _cneighbors

    if _best_cluster and _best_score >= 3:
        _cluster_sector = "-".join(str(n) for n in _best_cluster)
        _cnums_html = ""
        for _cn in _best_cluster:
            _cn_color = colors.get(str(_cn), "black")
            _cn_border = "3px solid #FFD700" if _cn in _last15_set else "1px solid #ccc"
            _cn_opacity = "1" if _cn in _last15_set else "0.4"
            _cnums_html += (
                f'<span style="display:inline-flex;align-items:center;justify-content:center;'
                f'width:28px;height:28px;border-radius:50%;font-size:12px;font-weight:bold;'
                f'background:{_cn_color};color:white;border:{_cn_border};'
                f'opacity:{_cn_opacity};margin:2px;">{_cn}</span>'
            )
        _cluster_content = (
            f'<div style="font-size:14px;font-weight:900;color:#c62828;margin-bottom:6px;">'
            f'🔥 Sector {_cluster_sector} is HOT ({_best_score}/5 hit)</div>'
            f'<div>{_cnums_html}</div>'
        )
    elif _best_cluster:
        _cluster_sector = "-".join(str(n) for n in _best_cluster)
        _cluster_content = (
            f'<div style="color:#666;font-size:12px;">'
            f'Best sector: {_cluster_sector} ({_best_score}/5 hit) — no strong cluster yet</div>'
        )
    else:
        _cluster_content = (
            '<div style="color:#999;font-size:12px;">No spins yet to detect clusters</div>'
        )

    neighbor_cluster_html = (
        f'<div style="margin-top:10px;padding:10px;background:#fff;'
        f'border:1px solid #d3d3d3;border-radius:6px;">'
        f'<div style="font-weight:bold;font-size:13px;margin-bottom:6px;color:#333;">🎯 Neighbor Hit Cluster (last 15 spins)</div>'
        f'<div style="text-align:center;">{_cluster_content}</div>'
        f'</div>'
    )

    new_widgets_html = (
        lr_bet_strip_html + lr_momentum_html + mini_wheel_html + neighbor_cluster_html
    )

    # HTML output with JavaScript to handle animations and interactivity
    return f"""
    <style>
        .circular-progress {{
            position: relative;
            width: 80px;
            height: 80px;
            background: conic-gradient(#d3d3d3 0% 100%);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            transition: all 0.5s ease;
        }}
        .circular-progress::before {{
            content: '';
            position: absolute;
            width: 60px;
            height: 60px;
            background: #e0e0e0;
            border-radius: 50%;
            z-index: 1;
        }}
        .circular-progress span {{
            position: relative;
            z-index: 2;
            font-size: 12px;
            font-weight: bold;
            color: #333;
            text-align: center;
        }}
        #left-progress {{
            background: conic-gradient(#6a1b9a {left_progress}% , #d3d3d3 {left_progress}% 100%);
        }}
        #zero-progress {{
            background: conic-gradient(#00695c {zero_progress}% , #d3d3d3 {zero_progress}% 100%);
        }}
        #right-progress {{
            background: conic-gradient(#f4511e {right_progress}% , #d3d3d3 {right_progress}% 100%);
        }}
        .circular-progress:hover {{
            transform: scale(1.05);
            box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        }}
        .number-list {{
            display: flex;
            flex-wrap: nowrap;
            gap: 3px;
            justify-content: center;
            margin-top: 10px;
            overflow-x: auto;
            width: 100%;
            padding: 5px 0;
        }}
        .number-item {{
            width: 20px;
            height: 20px;
            line-height: 20px;
            text-align: center;
            font-size: 10px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            position: relative;
            flex-shrink: 0;
        }}
        .number-item.zero-number {{
            width: 60px;
            height: 60px;
            line-height: 60px;
            font-size: 30px;
        }}
        .hit-badge {{
            position: absolute;
            top: -4px;
            right: -4px;
            background: #ffffff;
            color: #000000;
            border: 1px solid #000000;
            font-size: 8px;
            width: 12px;
            height: 12px;
            line-height: 12px;
            border-radius: 50%;
            z-index: 2;
        }}
        .number-item.zero-number .hit-badge {{
            top: -6px;
            right: -6px;
            width: 20px;
            height: 20px;
            line-height: 20px;
            font-size: 10px;
        }}
        .number-badge:hover {{
            transform: scale(1.15);
            box-shadow: 0 0 10px rgba(255, 255, 255, 0.7);
        }}
        .hot-badge {{
            animation: hot-glow 1.5s infinite ease-in-out, flame-effect 2s infinite ease-in-out;
        }}
        @keyframes hot-glow {{
            0% {{ box-shadow: 0 0 5px #ff0000; }}
            50% {{ box-shadow: 0 0 15px #ff4500; }}
            100% {{ box-shadow: 0 0 5px #ff0000; }}
        }}
        @keyframes flame-effect {{
            0% {{ background-color: #ff4444; }}
            50% {{ background-color: #ff6347; }}
            100% {{ background-color: #ff4444; }}
        }}
        .cold-badge {{
            animation: cold-glow 1.5s infinite ease-in-out, snowflake-effect 2s infinite ease-in-out;
        }}
        @keyframes cold-glow {{
            0% {{ box-shadow: 0 0 5px #1e90ff; }}
            50% {{ box-shadow: 0 0 15px #87cefa; }}
            100% {{ box-shadow: 0 0 5px #1e90ff; }}
        }}
        @keyframes snowflake-effect {{
            0% {{ background-color: #87cefa; }}
            50% {{ background-color: #add8e6; }}
            100% {{ background-color: #87cefa; }}
        }}
        .tooltip {{
            position: absolute;
            background: #000;
            color: white;
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 14px;
            font-weight: bold;
            z-index: 10;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.2s ease;
            white-space: pre-wrap;
            border: 1px solid #FF00FF;
            box-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }}
        .tracker-column {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 5px;
        }}
        .tracker-container {{
            display: flex;
            flex-direction: row;
            justify-content: space-around;
            gap: 15px;
            width: 100%;
            max-width: 600px;
            margin: 0 auto;
            font-family: Arial, sans-serif;
        }}
        .roulette-wheel-container {{
            position: relative;
            width: 340px;
            height: 340px;
            margin: 20px auto;
            display: flex;
            justify-content: center;
            align-items: center;
        }}
        .wheel-segment:hover {{
            filter: brightness(1.2);
        }}
        .pulse {{
            animation: pulse 1.5s infinite ease-in-out;
        }}
        @keyframes pulse {{
            0% {{ stroke-opacity: 1; }}
            50% {{ stroke-opacity: 0.5; }}
            100% {{ stroke-opacity: 1; }}
        }}
        .winning-segment {{
            filter: drop-shadow(0 0 5px rgba(255, 255, 255, 0.8));
        }}
        #wheel-pointer {{
            z-index: 3;
        }}
        @media (max-width: 600px) {{
            .tracker-container {{
                flex-direction: column;
                align-items: center;
            }}
            .number-list {{
                flex-wrap: nowrap;
                overflow-x: auto;
            }}
            .number-item {{
                width: 16px;
                height: 16px;
                line-height: 16px;
                font-size: 8px;
            }}
            .number-item.zero-number {{
                width: 64px;
                height: 64px;
                line-height: 64px;
                font-size: 32px;
            }}
            .hit-badge {{
                width: 10px;
                height: 10px;
                line-height: 10px;
                font-size: 6px;
                top: -3px;
                right: -3px;
            }}
            .number-item.zero-number .hit-badge {{
                width: 20px;
                height: 20px;
                line-height: 20px;
                font-size: 10px;
                top: -6px;
                right: -6px;
            }}
            .roulette-wheel-container {{
                width: 290px;
                height: 290px;
            }}
            #roulette-wheel {{
                width: 290px;
                height: 290px;
            }}
            #wheel-pointer {{
                top: -24px;
                left: 143.5px;
                width: 3px;
                height: 150px;
                background-color: #00695C;
            }}
            #spinning-ball {{
                width: 10px;
                height: 10px;
            }}
        }}
        /* Updated styles for static betting sections with enhanced effects */
        .betting-sections-container {{
            display: flex;
            flex-direction: column;
            gap: 10px;
            margin-top: 20px;
            padding: 10px;
        }}
        .betting-section {{
            background-color: #fff;
            border: 1px solid #d3d3d3;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: box-shadow 0.2s ease;
        }}
        .betting-section:hover {{
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }}
        .betting-section-header {{
            color: white;
            padding: 8px 12px;
            border-radius: 5px 5px 0 0; /* Adjusted for static section */
            font-weight: bold;
            font-size: 14px;
            position: relative;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .betting-section-numbers {{
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            padding: 10px;
            justify-content: center;
            background-color: #f9f9f9;
            border-top: 1px solid #d3d3d3;
            border-radius: 0 0 5px 5px;
        }}
        .section-number {{
            padding: 0;
            margin: 2px;
            border-radius: 50%;
            width: 28px;
            height: 28px;
            line-height: 28px;
            text-align: center;
            font-size: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        .section-number:not(.hot-number) {{
            margin-left: 4px;
            margin-right: 4px;
        }}
        .hot-number {{
            width: 34px;
            height: 34px;
            line-height: 34px;
            font-size: 16px;
            border: 2px solid #FF00FF;
            box-shadow: 0 0 8px #FF00FF;
            text-shadow: 0 0 5px #FF00FF;
            animation: glow 1.5s infinite ease-in-out, border-flash 1.5s infinite ease-in-out, bounce 0.4s ease-in-out;
        }}
        @keyframes glow {{
            0% {{ box-shadow: 0 0 8px #FF00FF; text-shadow: 0 0 5px #FF00FF; }}
            50% {{ box-shadow: 0 0 12px #FF00FF; text-shadow: 0 0 8px #FF00FF; }}
            100% {{ box-shadow: 0 0 8px #FF00FF; text-shadow: 0 0 5px #FF00FF; }}
        }}
        @keyframes border-flash {{
            0% {{ border-color: #FF00FF; }}
            50% {{ border-color: #FFFFFF; }}
            100% {{ border-color: #FF00FF; }}
        }}
        @keyframes bounce {{
            0%, 100% {{ transform: scale(1); }}
            50% {{ transform: scale(1.2); }}
        }}
        /* Dynamic color pulse for red numbers */
        .hot-number[style*="background-color: red"] {{
            animation: glow 1.5s infinite ease-in-out, border-flash 1.5s infinite ease-in-out, bounce 0.4s ease-in-out, red-pulse 1.5s infinite ease-in-out;
        }}
        @keyframes red-pulse {{
            0% {{ background-color: red; }}
            50% {{ background-color: #ff3333; }}
            100% {{ background-color: red; }}
        }}
        /* Dynamic color pulse for black numbers */
        .hot-number[style*="background-color: black"] {{
            animation: glow 1.5s infinite ease-in-out, border-flash 1.5s infinite ease-in-out, bounce 0.4s ease-in-out, black-pulse 1.5s infinite ease-in-out;
        }}
        @keyframes black-pulse {{
            0% {{ background-color: black; }}
            50% {{ background-color: #333333; }}
            100% {{ background-color: black; }}
        }}
        /* Dynamic color pulse for green numbers */
        .hot-number[style*="background-color: green"] {{
            animation: glow 1.5s infinite ease-in-out, border-flash 1.5s infinite ease-in-out, bounce 0.4s ease-in-out, green-pulse 1.5s infinite ease-in-out;
        }}
        @keyframes green-pulse {{
            0% {{ background-color: green; }}
            50% {{ background-color: #33cc33; }}
            100% {{ background-color: green; }}
        }}
        .number-hit-badge {{
            position: absolute;
            top: -8px;
            right: -8px;
            background-color: #ffffff;
            color: #000000;
            border: 1px solid #ff4444;
            font-size: 8px;
            width: 16px;
            height: 16px;
            line-height: 16px;
            border-radius: 50%;
            z-index: 3;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .betting-section-hits {{
            background-color: #ff4444;
            color: white;
            border: none;
            font-size: 10px;
            width: 20px;
            height: 20px;
            line-height: 20px;
            border-radius: 50%;
            z-index: 3;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        /* Hottest section pulsing highlight */
        @keyframes hottest-glow {{
            0%   {{ box-shadow: 0 0 8px 2px rgba(255,80,0,0.6); }}
            50%  {{ box-shadow: 0 0 22px 8px rgba(255,160,0,0.9); }}
            100% {{ box-shadow: 0 0 8px 2px rgba(255,80,0,0.6); }}
        }}
        .hottest-section {{
            animation: hottest-glow 1.4s ease-in-out infinite;
            border: 2px solid #ff8c00 !important;
        }}
        .hottest-hits-badge {{
            width: 28px !important;
            height: 28px !important;
            line-height: 28px !important;
            font-size: 14px !important;
        }}
        .hottest-number {{
            width: 34px !important;
            height: 34px !important;
            line-height: 34px !important;
            font-size: 14px !important;
        }}
        .hottest-label {{
            font-size: 11px;
            font-weight: 900;
            background: rgba(255,255,255,0.25);
            padding: 1px 7px;
            border-radius: 10px;
            margin-left: 6px;
            letter-spacing: 0.5px;
        }}
        /* L/R bet suggestion number chips */
        .lr-num {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 22px;
            height: 22px;
            border-radius: 50%;
            font-size: 9px;
            font-weight: bold;
            color: white;
            margin: 1px;
            flex-shrink: 0;
        }}
        @keyframes lr-pulse-anim {{
            0%   {{ box-shadow: 0 0 4px 1px rgba(255,215,0,0.6); }}
            50%  {{ box-shadow: 0 0 14px 5px rgba(255,215,0,1.0); }}
            100% {{ box-shadow: 0 0 4px 1px rgba(255,215,0,0.6); }}
        }}
        .lr-pulse {{
            animation: lr-pulse-anim 1.2s ease-in-out infinite;
        }}
    </style>
    <div class="{'roulette-table-pulse' if has_active_cards else ''}" style="position: relative; background-color: #f5c6cb; border: 2px solid #d3d3d3; border-radius: 5px; padding: 10px;">
        {'<span class="siren-indicator">🚨</span>' if has_active_cards else ''}
        <h4 style="text-align: center; margin: 0 0 10px 0; font-family: Arial, sans-serif;">Dealer's Spin Tracker (Can you spot Bias???) 🔍</h4>
        <div class="tracker-container">
            <div class="tracker-column">
                <div class="circular-progress" id="left-progress">
                    <span>{left_hits}</span>
                </div>
                <span style="display: block; font-weight: bold; font-size: 10px; background-color: #6a1b9a; color: white; padding: 2px 5px; border-radius: 3px;">Left Side</span>
            </div>
            <div class="tracker-column">
                <div class="circular-progress" id="zero-progress">
                    <span>{zero_hits}</span>
                </div>
                <span style="display: block; font-weight: bold; font-size: 10px; background-color: #00695c; color: white; padding: 2px 5px; border-radius: 3px;">Zero</span>
            </div>
            <div class="tracker-column">
                <div class="circular-progress" id="right-progress">
                    <span>{right_hits}</span>
                </div>
                <span style="display: block; font-weight: bold; font-size: 10px; background-color: #f4511e; color: white; padding: 2px 5px; border-radius: 3px;">Right Side</span>
            </div>
        </div>
        {lrz_trail_html}
        {hot_cold_html}
        {number_list}
        {wheel_svg}
        {betting_sections_html}
        {new_widgets_html}
    </div>
    <script>
        function updateCircularProgress(id, progress) {{
            const element = document.getElementById(id);
            if (!element) {{
                console.error('Element not found: ' + id);
                return;
            }}
            const colors = {{
                'left-progress': '#6a1b9a',
                'zero-progress': '#00695c',
                'right-progress': '#f4511e'
            }};
            const color = colors[id] || '#d3d3d3';
            element.style.background = "conic-gradient(" + color + " " + progress + "%, #d3d3d3 " + progress + "% 100%)";
            // Progress update handled by conic-gradient above
        }}
        updateCircularProgress('left-progress', {left_progress});
        updateCircularProgress('zero-progress', {zero_progress});
        updateCircularProgress('right-progress', {right_progress});

        // Tooltip functionality for numbers
        document.querySelectorAll('.number-item').forEach(element => {{
            element.addEventListener('mouseover', (e) => {{
                const hits = element.getAttribute('data-hits');
                const num = element.getAttribute('data-number');
                const tooltipText = "Number " + num + ": " + hits + " hits";
                
                const tooltip = document.createElement('div');
                tooltip.className = 'tooltip';
                tooltip.textContent = tooltipText;
                
                document.body.appendChild(tooltip);
                
                const rect = element.getBoundingClientRect();
                const tooltipRect = tooltip.getBoundingClientRect();
                tooltip.style.left = (rect.left + window.scrollX + (rect.width / 2) - (tooltipRect.width / 2)) + 'px';
                tooltip.style.top = (rect.top + window.scrollY - tooltipRect.height - 5) + 'px';
                tooltip.style.opacity = '1';
            }});
            
            element.addEventListener('mouseout', () => {{
                const tooltip = document.querySelector('.tooltip');
                if (tooltip) {{
                    tooltip.remove();
                }}
            }});
        }});

        // Tooltip functionality for wheel segments
        document.querySelectorAll('.wheel-segment').forEach(segment => {{
            segment.addEventListener('click', (e) => {{
                const hits = segment.getAttribute('data-hits');
                const num = segment.getAttribute('data-number');
                const neighbors = {json.dumps(dict(current_neighbors))};
                const leftNeighbor = neighbors[num] ? neighbors[num][0] : 'None';
                const rightNeighbor = neighbors[num] ? neighbors[num][1] : 'None';
                const tooltipText = "Number " + num + ": " + hits + " hits\\nLeft Neighbor: " + leftNeighbor + "\\nRight Neighbor: " + rightNeighbor;
                
                // Remove any existing tooltips
                const existingTooltip = document.querySelector('.tooltip');
                if (existingTooltip) existingTooltip.remove();
                
                const tooltip = document.createElement('div');
                tooltip.className = 'tooltip';
                tooltip.textContent = tooltipText;
                
                document.body.appendChild(tooltip);
                
                const rect = segment.getBoundingClientRect();
                const tooltipRect = tooltip.getBoundingClientRect();
                tooltip.style.left = (rect.left + window.scrollX + (rect.width / 2) - (tooltipRect.width / 2)) + 'px';
                tooltip.style.top = (rect.top + window.scrollY - tooltipRect.height - 5) + 'px';
                tooltip.style.opacity = '1';
                
                // Remove tooltip after 3 seconds or on click
                setTimeout(() => {{
                    tooltip.remove();
                }}, 3000);
                segment.addEventListener('click', () => {{
                    tooltip.remove();
                }}, {{ once: true }});
            }});
            
            segment.addEventListener('mouseout', () => {{
                const tooltip = document.querySelector('.tooltip');
                if (tooltip) {{
                    tooltip.style.opacity = '0';
                }}
            }});
        }});

        // Remove bounce class after animation
        document.querySelectorAll('.bounce').forEach(element => {{
            setTimeout(() => {{
                element.classList.remove('bounce');
            }}, 400);
        }});

        // JavaScript animation function
        function animateElement(element, startAngle, endAngle, duration, isBall = false) {{
            console.log("animateElement called for element: " + element.id + ", startAngle: " + startAngle + ", endAngle: " + endAngle + ", duration: " + duration + ", isBall: " + isBall);
            const startTime = performance.now();
            const radius = isBall ? 135 : 0;
            
            function step(currentTime) {{
                const elapsed = currentTime - startTime;
                const progress = Math.min(elapsed / duration, 1);
                const easeOut = 1 - Math.pow(1 - progress, 3);
                const currentAngle = startAngle + (endAngle - startAngle) * easeOut;
                
                if (isBall) {{
                    element.style.transform = "rotate(" + currentAngle + "deg) translateX(" + radius + "px)";
                }} else {{
                    element.style.transform = "rotate(" + currentAngle + "deg)";
                }}
                console.log("Animation step - element: " + element.id + ", progress: " + progress.toFixed(2) + ", currentAngle: " + currentAngle.toFixed(2));
                
                if (progress < 1) {{
                    requestAnimationFrame(step);
                }} else {{
                    console.log("Animation completed for element: " + element.id);
                }}
            }}
            
            requestAnimationFrame(step);
        }}

        // Trigger wheel and ball spin animations with JavaScript
        setTimeout(() => {{
            console.log('Attempting to trigger animations...');
            const wheel = document.getElementById('roulette-wheel');
            const ball = document.getElementById('spinning-ball');
            const hasSpin = {js_has_latest_spin};
            console.log('Wheel element:', wheel);
            console.log('Ball element:', ball);
            console.log('Has latest spin:', hasSpin);
            console.log('Latest spin angle:', {latest_spin_angle});
            
            if (wheel && ball && hasSpin) {{
                console.log('Starting animations for wheel and ball using JavaScript...');
                
                // Force visibility toggle to ensure rendering
                wheel.style.visibility = 'hidden';
                ball.style.visibility = 'hidden';
                setTimeout(() => {{
                    wheel.style.visibility = 'visible';
                    ball.style.visibility = 'visible';
                    console.log('Visibility toggled to visible for wheel and ball');
                    
                    // Directly use JavaScript animation
                    animateElement(wheel, 90, {latest_spin_angle}, 2000);
                    animateElement(ball, 0, {-latest_spin_angle}, 2000, true);
                    console.log('JavaScript animations triggered for wheel and ball');
                    
                    // Finalize position after animation
                    setTimeout(() => {{
                        console.log('Finalizing animation positions...');
                        wheel.style.transform = "rotate(" + {latest_spin_angle} + "deg)";
                        ball.style.transform = "rotate(" + {-latest_spin_angle} + "deg) translateX(135px)";
                        console.log('Animation positions finalized');
                    }}, 2000);
                }}, 10);
            }} else {{
                console.warn('Animation not triggered: Elements or latest spin missing');
                if (!wheel) console.warn('Wheel element not found');
                if (!ball) console.warn('Ball element not found');
                if (!hasSpin) console.warn('No latest spin to animate');
            }}
        }}, 2000);

        // Add tooltips to section numbers
        document.querySelectorAll('.section-number').forEach(element => {{
            element.addEventListener('mouseover', (e) => {{
                const hits = element.getAttribute('data-hits');
                const num = element.getAttribute('data-number');
                const tooltipText = "Number " + num + ": " + hits + " hits";
                
                const tooltip = document.createElement('div');
                tooltip.className = 'tooltip';
                tooltip.textContent = tooltipText;
                
                document.body.appendChild(tooltip);
                
                const rect = element.getBoundingClientRect();
                const tooltipRect = tooltip.getBoundingClientRect();
                tooltip.style.left = (rect.left + window.scrollX + (rect.width / 2) - (tooltipRect.width / 2)) + 'px';
                tooltip.style.top = (rect.top + window.scrollY - tooltipRect.height - 5) + 'px';
                tooltip.style.opacity = '1';
            }});
            
            element.addEventListener('mouseout', () => {{
                const tooltip = document.querySelector('.tooltip');
                if (tooltip) {{
                    tooltip.remove();
                }}
            }});
        }});
    </script>
    """


def render_aidea_roadmap_html(state, DOZENS, multiplier):
    # Helper to generate empty states
    empty_banner = "<div style='padding:10px; background:#333; color:#fff; border-radius:4px; text-align:center;'><b>NO ACTIVE STRATEGY</b></div>"
    empty_roadmap = "<div style='text-align:center; padding:20px; color:#ccc;'><h4>Waiting for Strategy...</h4><p>Please upload a valid AIDEA JSON file.</p></div>"

    if not state.aidea_phases:
        return empty_roadmap, empty_banner
    
    groups = {}
    order = []
    
    mult = multiplier
    
    # Define colors
    stage_colors = {
        "SHIELD": "#2ecc71", "CRUISE": "#00fbff", "AGGRESSOR": "#f1c40f", "SETTLEMENT": "#9b59b6", "UNCATEGORIZED": "#bdc3c7"
    }
    
    current_phase_obj = None
    current_phase_num = 0
    
    # --- 1. SMART GROUPING LOGIC ---
    for idx, p in enumerate(state.aidea_phases):
        # Identify current phase object for the banner
        if p['id'] == state.aidea_current_id:
            current_phase_obj = p
            current_phase_num = idx + 1
            
        name_str = p.get("name", "").upper()
        
        # Detect Stage Name using Keywords (Works with "P1 SHIELD" OR "Phase 1 (SHIELD)")
        if "SHIELD" in name_str: stage_name = "SHIELD"
        elif "CRUISE" in name_str: stage_name = "CRUISE"
        elif "AGGRESSOR" in name_str: stage_name = "AGGRESSOR"
        elif "SETTLEMENT" in name_str: stage_name = "SETTLEMENT"
        else:
            # Fallback: Look for text in parentheses
            match = re.search(r'\((.*?)\)', name_str)
            stage_name = match.group(1).strip() if match else "UNCATEGORIZED"
        
        if stage_name not in groups:
            groups[stage_name] = []
            order.append(stage_name)
        groups[stage_name].append(p)
        
    # --- 2. BUILD STATUS BANNER ---
    if current_phase_obj:
        # Extract Stage Name for Banner
        name_str = current_phase_obj.get("name", "").upper()
        if "SHIELD" in name_str: stage_name = "SHIELD"
        elif "CRUISE" in name_str: stage_name = "CRUISE"
        elif "AGGRESSOR" in name_str: stage_name = "AGGRESSOR"
        elif "SETTLEMENT" in name_str: stage_name = "SETTLEMENT"
        else: stage_name = "UNKNOWN"
            
        stage_color = stage_colors.get(stage_name, "#fff")

        # Extract Instructions
        raw_inst = current_phase_obj.get("instructions", "")
        
        if "WIN:" in raw_inst:
            instruction = raw_inst.split('|')[0].replace("WIN:", "").strip()
        else:
            instruction = raw_inst

        # --- FIX: DYNAMIC TARGETING FROM JSON ---
        json_positions = []
        if 'bets' in current_phase_obj and len(current_phase_obj['bets']) > 0:
            if 'positions' in current_phase_obj['bets'][0]:
                json_positions = current_phase_obj['bets'][0]['positions']
        
        if json_positions:
            # If the JSON file provides exact numbers to cover, use them!
            state.aidea_active_targets = json_positions
            ident = current_phase_obj['bets'][0].get('identifier', '')
            if ident: 
                instruction = f"<b style='color: #FFD700;'>Target: {ident}</b>"
        else:
            # --- FALLBACK: V9 THE BEST DYNAMIC TARGETING ---
            v9_numbers = []
            
            local_double_streets = {
                "DS 1-6": [1, 2, 3, 4, 5, 6], "DS 4-9": [4, 5, 6, 7, 8, 9],
                "DS 7-12": [7, 8, 9, 10, 11, 12], "DS 10-15": [10, 11, 12, 13, 14, 15],
                "DS 13-18": [13, 14, 15, 16, 17, 18], "DS 16-21": [16, 17, 18, 19, 20, 21],
                "DS 19-24": [19, 20, 21, 22, 23, 24], "DS 22-27": [22, 23, 24, 25, 26, 27],
                "DS 25-30": [25, 26, 27, 28, 29, 30], "DS 28-33": [28, 29, 30, 31, 32, 33],
                "DS 31-36": [31, 32, 33, 34, 35, 36]
            }
            
            if current_phase_num <= 13:
                crnr_str = ", ".join(map(str, sorted(state.trinity_corner_nums))) if state.trinity_corner_nums else "N/A"
                instruction = f"<b style='color: #FFD700;'>❄️ COLD CORNER: {crnr_str}</b>"
                v9_numbers = state.trinity_corner_nums
            elif current_phase_num <= 25:
                instruction = f"<b style='color: #FFD700;'>🧊 COLD D.STREET: {state.trinity_ds}</b>"
                v9_numbers = local_double_streets.get(state.trinity_ds, [])
            elif current_phase_num <= 31:
                instruction = f"<b style='color: #FFD700;'>📉 COLD DOZEN: {state.trinity_dozen}</b>"
                v9_numbers = DOZENS.get(state.trinity_dozen, [])
            else: # Phase 32-33
                all_doz = sorted(DOZENS.keys(), key=lambda d: sum(1 for s in state.last_spins if int(s) in DOZENS[d]))
                if len(all_doz) >= 2:
                    d1, d2 = all_doz[0], all_doz[1]
                    instruction = f"<b style='color: #FFD700;'>🌊 2 COLD DOZENS: {d1} + {d2}</b>"
                    v9_numbers = list(set(DOZENS[d1]) | set(DOZENS[d2]))

            state.active_strategy_targets = v9_numbers
            # ------------------------------------------

        # --- SNIPER HARDCODE OVERRIDE FOR ROADMAP ---
        if getattr(state, 'sniper_locked', False):
            if current_phase_num <= 85:
                state.aidea_active_targets = [1, 2, 3]
                instruction = "<b style='color: #00BFFF;'>Target: 1, 2, 3 Street</b>"
            else:
                state.aidea_active_targets = [2, 3, 5, 6]
                instruction = "<b style='color: #FFD700;'>Target: 2, 3, 5, 6 Corner</b>"

        # Extract Bet
        base_bet = current_phase_obj['bets'][0]['amount']
        final_bet = base_bet * mult
        
        banner_html = f"""
        <div style="background: linear-gradient(90deg, #1e1e1e, #2c2c2c); border: 2px solid {stage_color}; border-radius: 6px; padding: 10px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 0 15px {stage_color}40;">
            <div style="font-size: 16px; font-weight: 900; color: {stage_color}; text-transform: uppercase; letter-spacing: 1px;">
                {stage_name} <span style="font-size:12px; color:#ddd; font-weight:normal;">({instruction})</span>
            </div>
            <div style="font-size: 16px; font-weight: bold; color: white;">
                PHASE {current_phase_num}
            </div>
            <div style="font-size: 20px; font-weight: 900; color: #fff; background: {stage_color}; padding: 2px 10px; border-radius: 4px; text-shadow: 0 1px 2px rgba(0,0,0,0.5);">
                ${final_bet:.2f}
            </div>
        </div>
        """
    else:
        banner_html = empty_banner

    # --- 3. BUILD ROADMAP HTML (Horizontal) ---
    html = """
    <style>
        .aidea-col { 
            display: flex; flex-direction: row; gap: 15px; overflow-x: auto; padding: 15px; 
            background: #121212; border-radius: 8px; border: 1px solid #333; 
        }
        .stage-column {
            flex: 1; min-width: 250px; display: flex; flex-direction: column; gap: 8px;
            background: #1a1a1a; padding: 8px; border-radius: 6px; border: 1px solid #333;
        }
        .stage-header { 
            font-size: 12px; font-weight: 900; color: #000000 !important; 
            padding: 8px 10px; border-radius: 4px; text-align: center; letter-spacing: 2px; 
            text-transform: uppercase; box-shadow: 0 2px 5px rgba(0,0,0,0.5); margin-bottom: 5px;
        }
        .phase-row { 
            display: flex; align-items: center; gap: 10px; padding: 10px; 
            background: #1e1e1e; border: 1px solid #444; border-radius: 6px; 
            transition: all 0.2s ease; position: relative;
        }
        .phase-row.active { 
            border: 3px solid #FFD700 !important; background: #2c2c2c; 
            box-shadow: 0 0 15px rgba(255, 215, 0, 0.3); 
        }
        .phase-row.completed { opacity: 0.5; filter: grayscale(0.5); border-color: #27ae60; }
        .status-indicator {
            width: 20px; height: 20px; border: 2px solid #777; border-radius: 4px; background: #000;
            display: flex; align-items: center; justify-content: center; font-size: 14px; color: transparent;
        }
        .completed .status-indicator { background: #27ae60; border-color: #27ae60; color: white !important; }
        .phase-content { flex-grow: 1; overflow: hidden; }
        .phase-title { font-size: 13px; font-weight: bold; color: #ffffff !important; display: block; margin-bottom: 3px; }
        .phase-cost { font-size: 11px; color: #dddddd !important; font-family: monospace; }
        .action-hint { 
            font-size: 10px; color: #00fbff !important; font-weight: bold; 
            background: rgba(0, 251, 255, 0.1); padding: 4px 6px; border-radius: 4px; 
            border: 1px solid rgba(0, 251, 255, 0.3); text-align: center; white-space: nowrap;
        }
    </style>
    <div class="aidea-col">
    """
    
    phase_counter = 1
    for stage_name in order:
        p_list = groups[stage_name]
        bg_color = stage_colors.get(stage_name, "#bdc3c7")
        html += f'<div class="stage-column"><div class="stage-header" style="background: {bg_color};">{stage_name}</div>'
        
        for p in p_list:
            p_id = p['id']
            is_active = state.aidea_current_id == p_id
            is_done = p_id in state.aidea_completed_ids
            
            raw_inst = p.get("instructions", "")
            hint = raw_inst.split('|')[0].replace("WIN:", "").strip() if "WIN:" in raw_inst else "Follow"
            
            # Apply multiplier
            bet_amt = p['bets'][0]['amount'] * mult
            
            classes = "phase-row" + (" active" if is_active else "") + (" completed" if is_done else "")
            check_mark = "✔" if is_done else ""
            
            html += f"""<div class="{classes}" id="phase-{p_id}"><div class="status-indicator">{check_mark}</div><div class="phase-content"><span class="phase-title">PH {phase_counter}</span><span class="phase-cost">${bet_amt:.2f}</span></div><div class="action-hint">{hint}</div></div>"""
            phase_counter += 1
        html += "</div>"
            
    html += "</div>"
    return html, banner_html


def generate_labouchere_html(state):
    """Render the Labouchere Sequence Tracker panel as an HTML string.

    Shows a placeholder when no session is active, or the live sequence badges,
    next-bet amounts, total table risk and session P/L when a session is running.
    """
    lab_active = state.lab_active
    lab_sequence = list(state.lab_sequence)
    lab_status = state.lab_status
    lab_bankroll = state.lab_bankroll

    # Placeholder — no session started yet
    if not lab_active and not lab_sequence and "Complete" not in lab_status:
        return (
            "<div style='padding:20px; background:#1a1040; color:#a78bfa; "
            "text-align:center; border-radius:8px; border:2px dashed #6d28d9;'>"
            "Set Base Unit and Target Profit, then click ▶️ Start Session.</div>"
        )

    # Build sequence badges
    seq_html = "".join(
        f'<span style="display:inline-block; background:#e9d5ff; color:#1a1040; '
        f'padding:4px 8px; margin:2px; border-radius:4px; font-weight:bold; '
        f'font-family:monospace; box-shadow:0 2px 4px rgba(0,0,0,0.3);">'
        f'${val:.2f}</span>'
        for val in lab_sequence
    )
    if not lab_sequence:
        seq_html = (
            '<span style="color:#4ade80; font-weight:bold; font-size:16px;">'
            '🎉 Sequence Cleared! Target Profit Reached!</span>'
        )

    mode = state.lab_mode
    is_single = "1 Target" in mode

    next_bet_per = 0.0
    total_bet = 0.0
    if lab_sequence:
        next_bet_per = (lab_sequence[0] + lab_sequence[-1]
                        if len(lab_sequence) > 1 else lab_sequence[0])
        total_bet = next_bet_per if is_single else next_bet_per * 2

    bet_label = "Bet Amount" if is_single else "Bet Per Target"
    if lab_status == "ACTIVE":
        status_color = "#c084fc"
    elif "Complete" in lab_status:
        status_color = "#4ade80"
    else:
        status_color = "#f87171"

    pl_color = "#4ade80" if lab_bankroll >= 0 else "#f87171"

    return f"""
    <div style="background: linear-gradient(135deg, #1a1040, #2d1b6e); border: 2px solid #7c3aed; border-radius: 10px; padding: 15px; color: white; box-shadow: 0 4px 20px rgba(109,40,217,0.4);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; border-bottom:1px solid rgba(167,139,250,0.3); padding-bottom:10px;">
            <h3 style="margin:0; color:#c084fc; text-transform:uppercase; font-size:16px; letter-spacing:1px;">📊 Labouchere Sequence Tracker</h3>
            <span style="background:rgba(0,0,0,0.5); padding:4px 10px; border-radius:12px; font-size:11px; font-weight:bold; color:{status_color};">{lab_status}</span>
        </div>

        <div style="margin-bottom:15px;">
            <div style="font-size:11px; color:#a78bfa; text-transform:uppercase; margin-bottom:5px; font-weight:bold; letter-spacing:0.5px;">Current Sequence:</div>
            <div style="display:flex; flex-wrap:wrap; gap:4px; min-height:30px;">
                {seq_html}
            </div>
        </div>

        <div style="display:flex; gap:10px;">
            <div style="flex:1; background:rgba(0,0,0,0.4); border-radius:8px; padding:10px; text-align:center; border:1px solid rgba(124,58,237,0.4);">
                <div style="font-size:10px; color:#a78bfa; text-transform:uppercase; margin-bottom:2px; letter-spacing:0.5px;">{bet_label}</div>
                <div style="font-size:24px; font-weight:900; color:#c084fc;">${next_bet_per:.2f}</div>
            </div>
            <div style="flex:1; background:rgba(0,0,0,0.4); border-radius:8px; padding:10px; text-align:center; border:1px solid rgba(124,58,237,0.4);">
                <div style="font-size:10px; color:#a78bfa; text-transform:uppercase; margin-bottom:2px; letter-spacing:0.5px;">Total Table Risk</div>
                <div style="font-size:24px; font-weight:900; color:#f87171;">${total_bet:.2f}</div>
            </div>
            <div style="flex:1; background:rgba(0,0,0,0.4); border-radius:8px; padding:10px; text-align:center; border:1px solid rgba(124,58,237,0.4);">
                <div style="font-size:10px; color:#a78bfa; text-transform:uppercase; margin-bottom:2px; letter-spacing:0.5px;">Session P/L</div>
                <div style="font-size:24px; font-weight:900; color:{pl_color};">${lab_bankroll:.2f}</div>
            </div>
        </div>
    </div>
    """


def render_strategy_alert_html(state):
    """Render a floating overlay alert card when a strategy trigger is active.

    Returns an animated HTML card when a strategy trigger is active (Sniper,
    AIDEA, or Labouchere), or a hidden placeholder div when no trigger is active.
    The card uses ``position: fixed`` CSS so it floats on the right side of the
    viewport without affecting the roulette table layout.
    """
    _STAGE_COLORS = {
        "SHIELD": "#2ecc71",
        "CRUISE": "#00fbff",
        "AGGRESSOR": "#f1c40f",
        "SETTLEMENT": "#9b59b6",
    }
    _STAGE_ICONS = {
        "SHIELD": "🛡️",
        "CRUISE": "🚀",
        "AGGRESSOR": "⚔️",
        "SETTLEMENT": "🏁",
    }

    # ------------------------------------------------------------------
    # 1. Detect which trigger (if any) is active
    # ------------------------------------------------------------------
    sniper_active = getattr(state, 'sniper_locked', False)
    aidea_active = bool(getattr(state, 'aidea_current_id', None)) and bool(getattr(state, 'aidea_phases', []))
    lab_active = getattr(state, 'lab_active', False)

    if not sniper_active and not aidea_active and not lab_active:
        # No trigger — return a hidden placeholder that takes no space
        return "<div id='strategy-alert-overlay-inner' style='display:none;'></div>"

    # ------------------------------------------------------------------
    # 2. Gather alert details from the active trigger
    # ------------------------------------------------------------------
    strategy_name = ""
    strategy_icon = "🎯"
    target_line = ""
    bet_line = ""
    phase_line = ""
    stage_name = ""
    stage_color = "#FFD700"

    if sniper_active:
        strategy_name = "Sniper"
        strategy_icon = "🎯"
        # Determine current phase index (same logic as add_spin / render_aidea_roadmap_html)
        current_idx = 0
        if getattr(state, 'aidea_phases', []) and getattr(state, 'aidea_current_id', None):
            for i, p in enumerate(state.aidea_phases):
                if p['id'] == state.aidea_current_id:
                    current_idx = i
                    break
        phase_num = current_idx + 1
        total_phases = len(getattr(state, 'aidea_phases', [])) or 87

        if phase_num <= 85:
            target_line = "1, 2, 3 Street"
            stage_name = "SHIELD"
        else:
            target_line = "2, 3, 5, 6 Corner"
            stage_name = "AGGRESSOR"

        stage_color = _STAGE_COLORS.get(stage_name, "#FFD700")
        phase_line = f"Phase: {phase_num} / {total_phases}"

        # Bet from AIDEA phases if available, otherwise leave blank
        if getattr(state, 'aidea_phases', []) and current_idx < len(state.aidea_phases):
            phase_obj = state.aidea_phases[current_idx]
            mult = getattr(state, 'aidea_unit_multiplier', 1)
            base_bet = phase_obj['bets'][0]['amount'] if phase_obj.get('bets') else 0.0
            bet_line = f"${base_bet * mult:.2f}"

    elif aidea_active:
        strategy_name = "AIDEA"
        strategy_icon = "🧠"
        # Find current phase object
        current_phase_obj = None
        current_idx = 0
        for i, p in enumerate(state.aidea_phases):
            if p['id'] == state.aidea_current_id:
                current_phase_obj = p
                current_idx = i
                break

        total_phases = len(state.aidea_phases)
        phase_num = current_idx + 1

        if current_phase_obj:
            name_str = current_phase_obj.get("name", "").upper()
            if "SHIELD" in name_str:
                stage_name = "SHIELD"
            elif "CRUISE" in name_str:
                stage_name = "CRUISE"
            elif "AGGRESSOR" in name_str:
                stage_name = "AGGRESSOR"
            elif "SETTLEMENT" in name_str:
                stage_name = "SETTLEMENT"
            else:
                stage_name = "ACTIVE"

            stage_color = _STAGE_COLORS.get(stage_name, "#FFD700")

            # Instruction / target from phase
            raw_inst = current_phase_obj.get("instructions", "")
            if "WIN:" in raw_inst:
                target_line = raw_inst.split('|')[0].replace("WIN:", "").strip()
            else:
                target_line = raw_inst[:60] if raw_inst else "—"

            # Bet amount
            mult = getattr(state, 'aidea_unit_multiplier', 1)
            base_bet = current_phase_obj['bets'][0]['amount'] if current_phase_obj.get('bets') else 0.0
            bet_line = f"${base_bet * mult:.2f}"

        phase_line = f"Phase: {phase_num} / {total_phases}"

    elif lab_active:
        strategy_name = "Labouchere"
        strategy_icon = "📋"
        stage_name = "ACTIVE"
        stage_color = "#00fbff"

        seq = getattr(state, 'lab_sequence', [])
        if len(seq) >= 2:
            next_bet = seq[0] + seq[-1]
        elif len(seq) == 1:
            next_bet = seq[0]
        else:
            next_bet = 0.0

        bet_line = f"${next_bet:.2f}"
        target_line = getattr(state, 'lab_status', 'Active')
        phase_line = f"Sequence length: {len(seq)}"

    # ------------------------------------------------------------------
    # 3. Build the HTML card
    # ------------------------------------------------------------------
    stage_icon = _STAGE_ICONS.get(stage_name, "⚡")
    phase_html = (
        f'<span style="font-size:13px; color:#e2e8f0;">🎯 {phase_line}</span>'
        if phase_line else ""
    )

    bet_html = (
        f'<span style="font-size:14px; font-weight:700; color:#FFD700;">💰 {bet_line}</span>'
        if bet_line else ""
    )

    return f"""
<style>
@keyframes alertFadeIn {{
    from {{ opacity: 0; transform: translateX(12px); }}
    to   {{ opacity: 1; transform: translateX(0); }}
}}
@keyframes alertGlow {{
    0%, 100% {{ box-shadow: 0 0 10px {stage_color}55, 0 2px 16px rgba(0,0,0,0.5); }}
    50%       {{ box-shadow: 0 0 20px {stage_color}99, 0 2px 20px rgba(0,0,0,0.7); }}
}}
#strategy-alert-overlay-inner {{
    animation: alertFadeIn 0.3s ease-out, alertGlow 2.5s ease-in-out infinite;
}}
</style>
<div id="strategy-alert-overlay-inner"
     style="display:block;
            background: linear-gradient(145deg, #1a0000, #1e293b);
            border: 2px solid {stage_color};
            border-left: 3px solid #ef4444;
            border-radius: 8px;
            padding: 10px 16px;
            color: #f1f5f9;
            margin-top: 6px;
            box-shadow: 0 0 12px rgba(239,68,68,0.2);
            transition: background 0.5s ease, border-color 0.5s ease, box-shadow 0.5s ease;
            font-family: 'Segoe UI', system-ui, sans-serif;">
    <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
        <span style="font-size:13px; font-weight:900; color:{stage_color};
                     text-transform:uppercase; letter-spacing:1px;">🚨 STRATEGY TRIGGERED</span>
        <span style="font-size:13px; font-weight:700; color:#f8fafc;">📌 {strategy_icon} {strategy_name}: {target_line}</span>
        {bet_html}
        {phase_html}
        <span style="font-size:12px; font-weight:900; color:{stage_color};
                     text-transform:uppercase; letter-spacing:1.5px;">{stage_icon} {stage_name} Stage</span>
    </div>
</div>"""


def render_strategy_summary_html(state):
    """Render a compact always-visible summary bar for all active strategy cards.

    Returns a horizontal flex bar with pill-style badges showing the current
    status of Trend Reversal/Labouchere, Sniper Strike, Cold Trinity Sensor,
    and Non-Repeaters.  Unlike ``render_strategy_alert_html``, this function
    **always** returns visible HTML — even when no trigger has fired yet.
    """

    _SEP = "<span style='border-left:1px solid #334155; height:16px; display:inline-block;'></span>"

    badges = []

    # ------------------------------------------------------------------
    # 1. Trend Reversal / Labouchere
    # ------------------------------------------------------------------
    lab_active = getattr(state, 'lab_active', False)
    lab_sequence = getattr(state, 'lab_sequence', [])
    if lab_active or lab_sequence:
        seq_len = len(lab_sequence)
        if seq_len >= 2:
            next_bet = lab_sequence[0] + lab_sequence[-1]
            next_bet_str = f" · Next: ${next_bet:.2f}"
        elif seq_len == 1:
            next_bet_str = f" · Next: ${lab_sequence[0]:.2f}"
        else:
            next_bet_str = ""
        lab_status = getattr(state, 'lab_status', 'Active')
        pulsing = "<span style='display:inline-block;width:7px;height:7px;border-radius:50%;background:#f97316;animation:pulse-dot 1s ease-in-out infinite;margin-right:3px;'></span>" if lab_active else ""
        tr_text = f"{pulsing}🔥 TR: {seq_len} steps left{next_bet_str} · {lab_status}"
        badges.append(
            f"<span style='color:#f97316; font-size:14px; font-weight:700;'>{tr_text}</span>"
        )

    # ------------------------------------------------------------------
    # 2. Sniper Strike
    # ------------------------------------------------------------------
    sniper_active = getattr(state, 'sniper_locked', False)
    aidea_active = bool(getattr(state, 'aidea_current_id', None)) and bool(getattr(state, 'aidea_phases', []))

    if sniper_active or aidea_active:
        # Determine phase index
        current_idx = 0
        if getattr(state, 'aidea_phases', []) and getattr(state, 'aidea_current_id', None):
            for i, p in enumerate(state.aidea_phases):
                if p['id'] == state.aidea_current_id:
                    current_idx = i
                    break
        phase_num = current_idx + 1
        total_phases = len(getattr(state, 'aidea_phases', [])) or 87

        if sniper_active:
            target_short = "1,2,3 St" if phase_num < 86 else "2,3,5,6 Crn"
            bet_str = ""
            if getattr(state, 'aidea_phases', []) and current_idx < len(state.aidea_phases):
                phase_obj = state.aidea_phases[current_idx]
                mult = getattr(state, 'aidea_unit_multiplier', 1)
                base_bet = phase_obj['bets'][0]['amount'] if phase_obj.get('bets') else 0.0
                bet_str = f" · ${base_bet * mult:.2f}"
            pulsing = "<span style='display:inline-block;width:7px;height:7px;border-radius:50%;background:#00BFFF;animation:pulse-dot 1s ease-in-out infinite;margin-right:3px;'></span>"
            sniper_text = f"{pulsing}⚙️ Sniper: Ph{phase_num}/{total_phases}{bet_str} · {target_short}"
        else:
            # AIDEA active (no sniper lock)
            current_phase_obj = None
            if getattr(state, 'aidea_phases', []):
                for p in state.aidea_phases:
                    if p['id'] == state.aidea_current_id:
                        current_phase_obj = p
                        break
            bet_str = ""
            if current_phase_obj and current_phase_obj.get('bets'):
                mult = getattr(state, 'aidea_unit_multiplier', 1)
                base_bet = current_phase_obj['bets'][0]['amount']
                bet_str = f" · ${base_bet * mult:.2f}"
            pulsing = "<span style='display:inline-block;width:7px;height:7px;border-radius:50%;background:#00BFFF;animation:pulse-dot 1s ease-in-out infinite;margin-right:3px;'></span>"
            sniper_text = f"{pulsing}🧠 AIDEA: Ph{phase_num}/{total_phases}{bet_str}"

        badges.append(
            f"<span style='color:#00BFFF; font-size:14px; font-weight:700;'>{sniper_text}</span>"
        )
    else:
        misses = getattr(state, 'sniper_locked_misses', 0)
        sniper_threshold = getattr(state, 'sniper_threshold', 22)
        miss_word = "miss" if misses == 1 else "misses"
        badges.append(
            f"<span style='color:#64748b; font-size:14px; font-weight:700;'>⚙️ Sniper: Scanning ({misses} {miss_word})</span>"
        )

    # ------------------------------------------------------------------
    # 3. Cold Trinity Sensor
    # ------------------------------------------------------------------
    trinity_corner = getattr(state, 'trinity_corner_nums', [])
    trinity_ds = getattr(state, 'trinity_ds', '')
    trinity_dozen = getattr(state, 'trinity_dozen', '')
    trinity_parts = []
    if trinity_corner:
        crn_str = ",".join(str(n) for n in sorted(trinity_corner))
        trinity_parts.append(f"Corner {crn_str}")
    if trinity_ds:
        trinity_parts.append(f"DS {trinity_ds}")
    if trinity_dozen:
        trinity_parts.append(f"{trinity_dozen}")
    if trinity_parts:
        trinity_text = f"❄️ Trinity: {' → '.join(trinity_parts)}"
    else:
        trinity_text = "❄️ Trinity: Scanning"
    badges.append(
        f"<span style='color:#FFD700; font-size:14px; font-weight:700;'>{trinity_text}</span>"
    )

    # ------------------------------------------------------------------
    # 4. Non-Repeaters
    # ------------------------------------------------------------------
    current_nr = getattr(state, 'current_non_repeaters', set())
    nr_count = len(current_nr)
    nr_target = getattr(state, 'nr_target', 12)
    _MAX_NR_DISPLAY = 5
    at_target = nr_count >= nr_target
    near_target = nr_count >= nr_target * 0.7
    nr_color = "#2ecc71" if at_target else ("#f1c40f" if near_target else "#95a5a6")
    if current_nr:
        nr_sorted = sorted(list(current_nr))
        nr_nums_str = ",".join(str(n) for n in nr_sorted[:_MAX_NR_DISPLAY])
        if nr_count > _MAX_NR_DISPLAY:
            nr_nums_str += "…"
        nr_extra = f" IN ({nr_nums_str}{' 🔥' if at_target else ''})"
    else:
        nr_extra = " IN (none)"
    nr_text = f"🎯 NR: {nr_count}/{nr_target}{nr_extra}"
    badges.append(
        f"<span style='color:{nr_color}; font-size:14px; font-weight:700;'>{nr_text}</span>"
    )

    # ------------------------------------------------------------------
    # Build output (includes keyframe for pulsing dot animation)
    # ------------------------------------------------------------------
    inner = _SEP.join(badges)

    # Determine whether any alert/trigger is currently active so the bar can
    # light up with a coloured glow instead of staying dark.
    any_alert_active = lab_active or sniper_active or aidea_active

    if any_alert_active:
        bar_bg = "linear-gradient(90deg,#1a0000,#0f172a)"
        bar_border_left = "3px solid #ef4444"
        bar_box_shadow = "0 0 12px rgba(239,68,68,0.15)"
    else:
        bar_bg = "linear-gradient(145deg,#0f172a,#1e293b)"
        bar_border_left = "3px solid transparent"
        bar_box_shadow = "none"

    return (
        "<style>@keyframes pulse-dot{0%,100%{opacity:1;transform:scale(1);}50%{opacity:0.4;transform:scale(1.4);}}</style>"
        f'<div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;'
        f'background:{bar_bg};'
        f'border-left:{bar_border_left};'
        f'box-shadow:{bar_box_shadow};'
        f'transition:background 0.5s ease,border-color 0.5s ease,box-shadow 0.5s ease;'
        f'border-radius:6px; padding:6px 12px; margin-top:4px;">{inner}</div>'
    )


# ---------------------------------------------------------------------------
# Statistical Intelligence Layer — Feature 1 + 4: σ Sigma Analysis
# ---------------------------------------------------------------------------

def _norm_cdf(z):
    """Approximate standard-normal CDF (Abramowitz & Stegun 26.2.17)."""
    t = 1.0 / (1.0 + 0.2316419 * abs(z))
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    base = 1.0 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * z * z) * poly
    return base if z >= 0 else 1.0 - base


_FALLBACK_SIGMA_HTML = ('<div style="background:#0f172a;border-radius:8px;padding:14px;'
                        'color:#94a3b8;text-align:center;font-size:13px;">'
                        '📊 σ Analysis — refreshing...</div>')
_FALLBACK_DROUGHT_HTML = ('<div style="background:#0f172a;border-radius:8px;padding:14px;'
                          'color:#94a3b8;text-align:center;font-size:13px;">'
                          '⏱️ Drought Counter — refreshing...</div>')
_FALLBACK_SUMMARY_HTML = ('<div style="background:#0f172a;border-radius:8px;padding:14px;'
                          'color:#94a3b8;text-align:center;font-size:13px;">'
                          '🧠 Smart Decision Summary — refreshing...</div>')


def render_sigma_analysis_html(state):
    """Render sigma (standard deviation) deviation badges for dozens, columns, and
    even-money categories, plus a recency-window comparison (last N spins).

    Uses state.dozen_scores, state.column_scores, state.even_money_scores,
    state.last_spins, and state.analysis_window.

    Returns an HTML string.
    """
    try:
        return _render_sigma_analysis_html_inner(state)
    except Exception:
        return _FALLBACK_SIGMA_HTML


def _render_sigma_analysis_html_inner(state):
    if not hasattr(state, 'last_spins'):
        return _FALLBACK_SIGMA_HTML

    n_spins = len(getattr(state, 'last_spins', []))
    analysis_window = getattr(state, 'analysis_window', 50)

    # Category definitions (size = how many numbers win out of 37)
    _CATEGORIES = {
        "1st Dozen": ("dozen_scores", 12),
        "2nd Dozen": ("dozen_scores", 12),
        "3rd Dozen": ("dozen_scores", 12),
        "1st Column": ("column_scores", 12),
        "2nd Column": ("column_scores", 12),
        "3rd Column": ("column_scores", 12),
        "Red": ("even_money_scores", 18),
        "Black": ("even_money_scores", 18),
        "Even": ("even_money_scores", 18),
        "Odd": ("even_money_scores", 18),
        "Low": ("even_money_scores", 18),
        "High": ("even_money_scores", 18),
    }

    def _sigma_calc(actual, n, cat_size):
        """Return (sigma, expected, std) or (None, None, None) when n < 10."""
        if n < 10:
            return None, None, None
        p = cat_size / 37.0
        expected = n * p
        std = math.sqrt(n * p * (1.0 - p))
        if std == 0:
            return None, None, None
        return (actual - expected) / std, expected, std

    def _sigma_badge(sigma):
        """Return (color, emoji, label) for a sigma value."""
        if sigma is None:
            return "#6b7280", "⚪", "?"
        if sigma >= 1.5:
            return "#22c55e", "🟢", f"+{sigma:.1f}σ"
        if sigma <= -1.5:
            return "#ef4444", "🔴", f"{sigma:.1f}σ"
        sign = "+" if sigma >= 0 else ""
        return "#9ca3af", "⚪", f"{sign}{sigma:.1f}σ"

    def _sigma_tooltip(name, sigma, actual, expected, n):
        """Return a plain-English explanation string."""
        if sigma is None:
            return f"Need at least 10 spins for analysis. ({n} so far)"
        diff = actual - expected
        diff_sign = "+" if diff >= 0 else ""
        if sigma >= 1.5:
            pct = (1.0 - _norm_cdf(sigma)) * 100
            return (
                f"🟢 +{sigma:.1f}σ — <b style='color:#86efac;'>{name} is on a hot streak!</b> "
                f"Got <b style='color:#e2e8f0;'>{actual}</b> hits vs expected <b style='color:#e2e8f0;'>{expected:.1f}</b> in {n} spins "
                f"(difference: <b style='color:#86efac;'>{diff_sign}{diff:.1f}</b>). "
                f"Only ~{pct:.1f}% chance this is random. This means it's <b style='color:#86efac;'>running hot</b> — avoid betting on it."
            )
        if sigma <= -1.5:
            pct = _norm_cdf(sigma) * 100
            return (
                f"🔴 {sigma:.1f}σ — <b style='color:#fca5a5;'>{name} is overdue!</b> "
                f"Got <b style='color:#e2e8f0;'>{actual}</b> hits vs expected <b style='color:#e2e8f0;'>{expected:.1f}</b> in {n} spins "
                f"(difference: <b style='color:#fca5a5;'>{diff_sign}{diff:.1f}</b>). "
                f"Only ~{pct:.1f}% chance this happens on a fair wheel. This means it's <b style='color:#fca5a5;'>running cold</b> — worth targeting."
            )
        sign = "+" if diff >= 0 else ""
        return (
            f"⚪ {sigma:+.1f}σ — Normal. Nothing to see here, move along. "
            f"Got <b style='color:#e2e8f0;'>{actual}</b> hits vs expected <b style='color:#e2e8f0;'>{expected:.1f}</b> in {n} spins "
            f"(difference: <b style='color:#e2e8f0;'>{sign}{diff:.1f}</b>). This means it's <b style='color:#e2e8f0;'>running normal</b> — ignore."
        )

    # Build windowed scores for recency comparison
    def _windowed_scores(window):
        last_spins = getattr(state, 'last_spins', [])
        window_spins = last_spins[-window:] if len(last_spins) >= window else last_spins
        w_dozen = {"1st Dozen": 0, "2nd Dozen": 0, "3rd Dozen": 0}
        w_col = {"1st Column": 0, "2nd Column": 0, "3rd Column": 0}
        w_em = {"Red": 0, "Black": 0, "Even": 0, "Odd": 0, "Low": 0, "High": 0}
        _DOZEN_RANGES = {"1st Dozen": range(1, 13), "2nd Dozen": range(13, 25), "3rd Dozen": range(25, 37)}
        _COL_NUMS = {
            "1st Column": {1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34},
            "2nd Column": {2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35},
            "3rd Column": {3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36},
        }
        _RED = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
        _BLACK = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}
        for spin_str in window_spins:
            try:
                n = int(spin_str)
            except (ValueError, TypeError):
                continue
            if n == 0:
                continue
            for dname, r in _DOZEN_RANGES.items():
                if n in r:
                    w_dozen[dname] += 1
            for cname, nums in _COL_NUMS.items():
                if n in nums:
                    w_col[cname] += 1
            if n in _RED:
                w_em["Red"] += 1
            elif n in _BLACK:
                w_em["Black"] += 1
            if n % 2 == 0:
                w_em["Even"] += 1
            else:
                w_em["Odd"] += 1
            if 1 <= n <= 18:
                w_em["Low"] += 1
            elif 19 <= n <= 36:
                w_em["High"] += 1
        return w_dozen, w_col, w_em, len(window_spins)

    w_dozen, w_col, w_em, w_n = _windowed_scores(analysis_window)

    def _windowed_score(category_key, name):
        if category_key == "dozen_scores":
            return w_dozen.get(name, 0)
        if category_key == "column_scores":
            return w_col.get(name, 0)
        return w_em.get(name, 0)

    def _render_group(title, names, group_icon):
        rows = []
        for name in names:
            cat_key, cat_size = _CATEGORIES[name]
            actual = getattr(state, cat_key, {}).get(name, 0)
            sigma, expected, std = _sigma_calc(actual, n_spins, cat_size)
            color, emoji, label = _sigma_badge(sigma)
            tooltip = _sigma_tooltip(name, sigma, actual, expected if expected is not None else 0, n_spins)

            w_actual = _windowed_score(cat_key, name)
            w_sigma, _, _ = _sigma_calc(w_actual, w_n, cat_size)
            w_color, w_emoji, w_label = _sigma_badge(w_sigma)
            fire = ""
            if w_n >= 10 and w_sigma is not None and abs(w_sigma) >= 1.5:
                fire = " 🔥" if w_sigma >= 1.5 else " 🥶"
            window_note = f"Last {w_n}: {w_actual} hits ({w_emoji} {w_label}){fire}"

            rows.append(f"""
<div style="display:flex;align-items:center;flex-wrap:wrap;gap:6px;
            background:#1e293b;border-radius:6px;padding:8px 10px;margin-bottom:4px;">
  <span style="flex:1;min-width:100px;color:#e2e8f0;font-size:13px;font-weight:600;">{name}</span>
  <span title="{tooltip}" style="background:{color}22;border:1px solid {color};color:{color};
       font-size:12px;font-weight:700;padding:2px 8px;border-radius:12px;cursor:help;">{emoji} {label}</span>
  <span style="color:#cbd5e1;font-size:11px;flex:2;min-width:180px;">All-time: {actual} hits &middot; {window_note}</span>
</div>
<div style="background:#0f172a;border-left:3px solid {color};padding:6px 10px;
            border-radius:0 4px 4px 0;margin-bottom:8px;color:#cbd5e1;font-size:11px;line-height:1.5;">{tooltip}</div>""")

        return f"""<div style="margin-bottom:14px;">
  <h4 style="color:#cbd5e1;font-size:11px;text-transform:uppercase;letter-spacing:1px;
             margin:0 0 8px 0;border-bottom:1px solid #334155;padding-bottom:4px;">{group_icon} {title}</h4>
  {"".join(rows)}
</div>"""

    if n_spins < 10:
        body = f"""<div style="text-align:center;padding:20px;color:#94a3b8;font-size:13px;">
  📊 Enter at least 10 spins to see sigma analysis.<br>
  <small style="color:#94a3b8;">({n_spins} spins entered so far)</small>
</div>"""
    else:
        body = (
            _render_group("Dozens", ["1st Dozen", "2nd Dozen", "3rd Dozen"], "📦")
            + _render_group("Columns", ["1st Column", "2nd Column", "3rd Column"], "🏛️")
            + _render_group("Even-Money Bets", ["Red", "Black", "Even", "Odd", "Low", "High"], "⚖️")
        )

    sigma_explainer = """<style>
.sig-html b, .sig-html strong { color: #e2e8f0 !important; }
</style>
<div class="sig-html" style="background:#1e1b4b;border:1px solid #4338ca;border-radius:6px;
  padding:10px 12px;margin-bottom:12px;color:#c7d2fe;font-size:12px;line-height:1.6;">
  <div style="margin-bottom:8px;">
    📖 <b style="color:#e2e8f0;">What is σ (sigma)?</b>
    σ measures how far each bet category is from where it <b style="color:#e2e8f0;">SHOULD</b> be mathematically.
    It does <b style="color:#e2e8f0;">NOT</b> compare categories against each other — it compares each one against
    its <b style="color:#e2e8f0;">own expected performance</b>.
    Black at <b style="color:#fca5a5;">−2.1σ</b> means Black is hitting much LESS than math predicts.
    Even at <b style="color:#e2e8f0;">−0.3σ</b> means Even is performing almost exactly as expected.
    <b style="color:#fbbf24;">Target the ones with the biggest NEGATIVE sigma — they are the most statistically overdue.</b>
  </div>
  <div style="border-top:1px solid #4338ca44;padding-top:8px;">
    🎯 <b style="color:#e2e8f0;">How to read this:</b>
    <b style="color:#ef4444;">🔴 RED badges = statistically overdue = worth targeting.</b>
    <b style="color:#9ca3af;">⚪ GRAY = normal, ignore.</b>
    <b style="color:#22c55e;">🟢 GREEN = running hot, avoid betting on these.</b>
  </div>
</div>"""

    return f"""<div style="background:linear-gradient(145deg,#0f172a,#1e293b);
  border-radius:8px;padding:14px;margin-bottom:12px;border:1px solid #334155;">
  <h3 style="color:#f1f5f9;margin:0 0 6px 0;font-size:15px;">
    📊 σ Sigma Deviation Analysis
    <span style="font-size:11px;font-weight:normal;color:#94a3b8;margin-left:8px;">
      ({n_spins} total spins · window: last {min(analysis_window, n_spins)})
    </span>
  </h3>
  {sigma_explainer}
  {body}
</div>"""


# ---------------------------------------------------------------------------
# Statistical Intelligence Layer — Feature 2 + 3: Drought Counter Table
# ---------------------------------------------------------------------------

def render_drought_table_html(state):
    """Render a drought counter table showing spins-since-last-hit for every
    tracked betting category, plus convergence probabilities for each drought.

    Uses state.drought_counters, state.last_spins, state.sniper_threshold.

    Returns an HTML string.
    """
    try:
        return _render_drought_table_html_inner(state)
    except Exception:
        return _FALLBACK_DROUGHT_HTML


def _render_drought_table_html_inner(state):
    if not hasattr(state, 'drought_counters'):
        return _FALLBACK_DROUGHT_HTML

    drought_counters = getattr(state, 'drought_counters', {})
    n_spins = len(getattr(state, 'last_spins', []))
    sniper_threshold = getattr(state, 'sniper_threshold', 22)

    _CAT_INFO = {
        "1st Dozen": (12 / 37, "Every ~3 spins"),
        "2nd Dozen": (12 / 37, "Every ~3 spins"),
        "3rd Dozen": (12 / 37, "Every ~3 spins"),
        "1st Column": (12 / 37, "Every ~3 spins"),
        "2nd Column": (12 / 37, "Every ~3 spins"),
        "3rd Column": (12 / 37, "Every ~3 spins"),
        "Red": (18 / 37, "Every ~2 spins"),
        "Black": (18 / 37, "Every ~2 spins"),
        "Even": (18 / 37, "Every ~2 spins"),
        "Odd": (18 / 37, "Every ~2 spins"),
        "Low": (18 / 37, "Every ~2 spins"),
        "High": (18 / 37, "Every ~2 spins"),
    }

    def _drought_prob(drought, p):
        return (1.0 - p) ** drought if drought > 0 else 1.0

    def _convergence_prob(p, n):
        return 1.0 - (1.0 - p) ** n

    def _explanation(name, drought, p, freq_label):
        if drought == 0:
            return f"✅ {name} just hit! Drought reset to 0. No action needed here."
        drought_pct = _drought_prob(drought, p) * 100
        conv5 = _convergence_prob(p, 5) * 100
        conv10 = _convergence_prob(p, 10) * 100
        if drought_pct < 1.0:
            urgency = "This is VERY unusual — the wheel owes you one!"
            action = " ⚡ <b style='color:#fca5a5;'>ACTION: This is one to watch closely. Consider targeting it.</b>"
        elif drought_pct < 5.0:
            urgency = "Uncommon drought — keep a close eye on this one."
            action = " ⚡ <b style='color:#fca5a5;'>ACTION: This is one to watch closely. Consider targeting it.</b>"
        elif drought_pct < 15.0:
            urgency = "A bit dry but still within the range of normal variance."
            action = " 👀 <b style='color:#fde68a;'>Getting interesting. Keep an eye on it — it may turn red soon.</b>"
        else:
            urgency = "Normal range — nothing unusual here."
            action = " Nothing unusual. Normal variance."
        return (
            f"{name} hasn't hit in {drought} spins. Normally hits {freq_label}. "
            f"Chance of a drought this long: {drought_pct:.1f}%. {urgency} "
            f"Probability to hit in next 5 spins: {conv5:.0f}% · next 10 spins: {conv10:.0f}%.{action}"
        )

    sorted_items = sorted(
        [(n, d) for n, d in drought_counters.items() if n in _CAT_INFO],
        key=lambda x: x[1], reverse=True,
    )

    if not sorted_items:
        return """<div style="background:linear-gradient(145deg,#0f172a,#1e293b);border-radius:8px;
  padding:14px;border:1px solid #334155;color:#94a3b8;text-align:center;font-size:13px;">
  ⏱️ Drought Tracker — No data yet. Start entering spins!
</div>"""

    rows_html = ""
    for name, drought in sorted_items:
        p, freq_label = _CAT_INFO[name]
        drought_pct = _drought_prob(drought, p) * 100
        conv5 = _convergence_prob(p, 5) * 100
        conv10 = _convergence_prob(p, 10) * 100
        explanation = _explanation(name, drought, p, freq_label)

        if drought == 0:
            bar_color, level_emoji, text_color = "#22c55e", "✅", "#22c55e"
        elif drought_pct < 5.0:
            bar_color, level_emoji, text_color = "#ef4444", "🔴", "#ef4444"
        elif drought_pct < 15.0:
            bar_color, level_emoji, text_color = "#f59e0b", "🟡", "#f59e0b"
        else:
            bar_color, level_emoji, text_color = "#6b7280", "⚪", "#94a3b8"

        bar_width = min(100, int(conv10))
        rows_html += f"""<div style="background:#1e293b;border-radius:6px;padding:8px 10px;
  margin-bottom:8px;border-left:4px solid {bar_color};">
  <div style="display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:4px;">
    <span style="flex:1;min-width:100px;color:#e2e8f0;font-size:13px;font-weight:600;">{level_emoji} {name}</span>
    <span style="color:{text_color};font-size:13px;font-weight:700;">{drought} spins dry</span>
    <span style="color:#94a3b8;font-size:11px;">
      Next 5: <b style="color:#e2e8f0;">{conv5:.0f}%</b> &middot;
      Next 10: <b style="color:#e2e8f0;">{conv10:.0f}%</b>
    </span>
  </div>
  <div style="background:#0f172a;height:5px;border-radius:3px;margin-bottom:5px;">
    <div style="background:{bar_color};height:100%;width:{bar_width}%;border-radius:3px;"></div>
  </div>
  <div style="color:#cbd5e1;font-size:11px;line-height:1.5;">{explanation}</div>
</div>"""

    sniper_note = f"""<div style="background:#1e1b4b;border:1px solid #4338ca;border-radius:6px;
  padding:8px 10px;margin-top:10px;color:#a5b4fc;font-size:11px;">
  💡 <b style="color:#e2e8f0;">Why the Sniper waits {sniper_threshold} misses:</b>
  After {sniper_threshold} straight misses on a street (p=3/37≈8.1%),
  the convergence probability says there is a
  <b style="color:#e2e8f0;">{(1.0 - (34.0/37.0)**87)*100:.2f}%</b> chance it hits within the next 87 spins —
  that is why the 87-phase progression is built exactly that length.
</div>"""

    drought_how_to = """<div style="background:#1e3a1e;border:1px solid #22c55e44;border-radius:6px;
  padding:10px 12px;margin-bottom:12px;color:#bbf7d0;font-size:12px;line-height:1.6;">
  🎯 <b style="color:#e2e8f0;">How to read this:</b> The items at the TOP with 🔴 red badges are the ones that have gone the LONGEST
  without hitting. The deeper the red, the more unusual the drought. Focus your attention on 🔴 items — those are
  statistically overdue. ✅ Green means it just hit — no action needed there.
</div>"""

    return f"""<div style="background:linear-gradient(145deg,#0f172a,#1e293b);
  border-radius:8px;padding:14px;margin-bottom:12px;border:1px solid #334155;">
  <h3 style="color:#f1f5f9;margin:0 0 6px 0;font-size:15px;">
    ⏱️ Drought Counter — Spins Since Last Hit
    <span style="font-size:11px;font-weight:normal;color:#94a3b8;margin-left:8px;">({n_spins} total spins)</span>
  </h3>
  <p style="color:#94a3b8;font-size:11px;margin:0 0 10px 0;">
    Sorted longest drought first. The bar shows the probability of hitting within the next 10 spins.<br>
    <b style="color:#ef4444;">🔴 &lt;5% chance this drought is random</b> &middot;
    <b style="color:#f59e0b;">🟡 5–15% unusual</b> &middot;
    <b style="color:#94a3b8;">⚪ Normal range</b>
  </p>
  {drought_how_to}
  {rows_html}
  {sniper_note}
</div>"""


# ---------------------------------------------------------------------------
# Statistical Intelligence Layer — Feature 5: Smart Decision Summary
# ---------------------------------------------------------------------------

def render_smart_decision_summary_html(state):
    """Render a plain-English 'What Should I Do?' summary card.

    Reads sigma deviations, drought counters, convergence probabilities, and
    active strategy states to generate actionable, human-readable advice.

    Returns an HTML string.
    """
    try:
        return _render_smart_decision_summary_html_inner(state)
    except Exception:
        return _FALLBACK_SUMMARY_HTML


def _render_smart_decision_summary_html_inner(state):
    if not hasattr(state, 'last_spins'):
        return _FALLBACK_SUMMARY_HTML

    n_spins = len(getattr(state, 'last_spins', []))
    drought_counters = getattr(state, 'drought_counters', {})
    sniper_threshold = getattr(state, 'sniper_threshold', 22)
    sniper_locked = getattr(state, 'sniper_locked', False)

    def _sigma_calc(actual, n, cat_size):
        if n < 10:
            return None
        p = cat_size / 37.0
        expected = n * p
        std = math.sqrt(n * p * (1.0 - p))
        return (actual - expected) / std if std > 0 else None

    def _drought_prob(drought, p):
        return (1.0 - p) ** drought if drought > 0 else 1.0

    def _conv_prob(p, n):
        return 1.0 - (1.0 - p) ** n

    signals = []  # (priority, label, html_text, color)

    # 1. Sniper state
    if sniper_locked:
        misses = getattr(state, 'sniper_locked_misses', sniper_threshold)
        signals.append((0, "SNIPER ACTIVE",
            f"⚡ <b style='color:#e2e8f0;'>SNIPER ACTIVE!</b> A street has missed <b style='color:#e2e8f0;'>{misses}</b> times in a row. "
            f"The 87-phase progression is running. Conviction: 99.97% hit rate within 87 phases. "
            f"Trust the system and play it through.",
            "#7c3aed"))
    else:
        # Check if approaching sniper threshold on street 1-2-3
        last_spins = getattr(state, 'last_spins', [])
        _STREET_1_2_3 = {1, 2, 3}
        consec_miss = 0
        for sp in reversed(last_spins):
            try:
                num = int(sp)
            except (ValueError, TypeError):
                break
            if num in _STREET_1_2_3:
                break
            consec_miss += 1
        if consec_miss >= sniper_threshold - 3:
            remaining = sniper_threshold - consec_miss
            if remaining > 0:
                signals.append((1, "SNIPER ALERT",
                    f"⚡ <b style='color:#e2e8f0;'>SNIPER ALERT:</b> Street 1-2-3 has missed <b style='color:#e2e8f0;'>{consec_miss}</b> times. "
                    f"Only <b style='color:#e2e8f0;'>{remaining}</b> more miss(es) until the Sniper activates. Get ready!",
                    "#f59e0b"))

    # 2. Category signals (dozens, columns, even-money)
    _CAT_DEFS = {
        "1st Dozen": ("dozen_scores", 12, 12 / 37),
        "2nd Dozen": ("dozen_scores", 12, 12 / 37),
        "3rd Dozen": ("dozen_scores", 12, 12 / 37),
        "1st Column": ("column_scores", 12, 12 / 37),
        "2nd Column": ("column_scores", 12, 12 / 37),
        "3rd Column": ("column_scores", 12, 12 / 37),
        "Red": ("even_money_scores", 18, 18 / 37),
        "Black": ("even_money_scores", 18, 18 / 37),
        "Even": ("even_money_scores", 18, 18 / 37),
        "Odd": ("even_money_scores", 18, 18 / 37),
        "Low": ("even_money_scores", 18, 18 / 37),
        "High": ("even_money_scores", 18, 18 / 37),
    }

    for name, (cat_key, cat_size, p) in _CAT_DEFS.items():
        actual = getattr(state, cat_key, {}).get(name, 0)
        sigma = _sigma_calc(actual, n_spins, cat_size)
        drought = drought_counters.get(name, 0)
        drought_pct = _drought_prob(drought, p) * 100
        conv5 = _conv_prob(p, 5) * 100
        conv10 = _conv_prob(p, 10) * 100

        if sigma is not None and sigma <= -2.0 and drought_pct < 5.0:
            signals.append((0, f"STRONG SIGNAL: {name}",
                f"🔴 <b style='color:#fca5a5;'>STRONG SIGNAL — {name}</b>: "
                f"<b style='color:#f1f5f9;'>{sigma:.1f}σ</b> below expected AND "
                f"<b style='color:#f1f5f9;'>{drought} spins dry</b> "
                f"(only {drought_pct:.1f}% chance this is random). "
                f"Convergence: <b style='color:#f1f5f9;'>{conv5:.0f}%</b> chance to hit in next 5 spins, "
                f"<b style='color:#f1f5f9;'>{conv10:.0f}%</b> in next 10. "
                f"<div style='margin-top:10px;background:linear-gradient(135deg,#7f1d1d,#991b1b);border:2px solid #ef4444;"
                f"border-radius:8px;padding:14px 18px;animation:pulse-glow 2s ease-in-out infinite;'>"
                f"<span style='font-size:17px;font-weight:900;color:#fff;line-height:1.5;display:block;'>"
                f"👉 If I were you, right now I would target "
                f"<span style='color:#fbbf24;text-decoration:underline;'>{name}</span>. "
                f"It's been cold for too long — the math says it's statistically due. The numbers don't lie."
                f"</span></div>",
                "#ef4444"))
        elif sigma is not None and sigma <= -1.5:
            signals.append((2, f"COLD: {name}",
                f"👀 Keep your eye on <b style='color:#f1f5f9;'>{name}</b> — it's running cold at "
                f"<b style='color:#f1f5f9;'>{sigma:.1f}σ</b>. "
                f"<b style='color:#f1f5f9;'>{conv5:.0f}%</b> chance it hits in next 5 spins. "
                f"Not a STRONG signal yet, but it's getting there. Be ready.",
                "#f97316"))
        elif sigma is not None and sigma >= 2.0 and drought == 0:
            signals.append((3, f"HOT: {name}",
                f"🔥 <b style='color:#f1f5f9;'>{name}</b> is on fire right now! "
                f"It just hit and it's been running hot at "
                f"<b style='color:#f1f5f9;'>+{sigma:.1f}σ</b>. "
                f"Ride the wave or step back — momentum players, this is your call.",
                "#22c55e"))

    # 3. Labouchere / Trend Reversal
    lab_active = getattr(state, 'lab_active', False)
    lab_sequence = getattr(state, 'lab_sequence', [])
    if lab_active and lab_sequence:
        next_bet = lab_sequence[0] + lab_sequence[-1] if len(lab_sequence) >= 2 else lab_sequence[0]
        signals.append((2, "TR/LABOUCHERE ACTIVE",
            f"🔥 <b style='color:#fdba74;'>Trend Reversal / Labouchere is running</b>. "
            f"Sequence has <b style='color:#f1f5f9;'>{len(lab_sequence)}</b> steps left. "
            f"Next bet: <b style='color:#f1f5f9;'>${next_bet:.2f}</b>. Keep following the sequence to completion.",
            "#f97316"))

    # 4. Trinity sensor
    trinity_dozen = getattr(state, 'trinity_dozen', '')
    if trinity_dozen:
        trinity_ds = getattr(state, 'trinity_ds', '')
        trinity_corners = getattr(state, 'trinity_corner_nums', [])
        signals.append((3, "TRINITY SENSOR",
            f"🔺 <b style='color:#c4b5fd;'>Cold Trinity Sensor</b> picked up the 3 coldest bets across "
            f"different tiers: Dozen=<b style='color:#f1f5f9;'>{trinity_dozen}</b>, "
            f"DS=<b style='color:#f1f5f9;'>{trinity_ds}</b>, "
            f"Corner=<b style='color:#f1f5f9;'>{trinity_corners}</b>. "
            f"These are the bets that have hit the LEAST. "
            f"If you're looking for value, this is where the math says to look.",
            "#8b5cf6"))

    # 5. Non-repeaters
    current_nr = getattr(state, 'current_non_repeaters', set())
    nr_target = 12
    if current_nr and len(current_nr) >= int(nr_target * 0.8):
        signals.append((2, "NON-REPEATER RADAR",
            f"🎯 <b style='color:#67e8f9;'>Non-Repeater Radar</b>: <b style='color:#f1f5f9;'>{len(current_nr)}</b> numbers are IN. "
            f"Approaching the target of <b style='color:#f1f5f9;'>{nr_target}</b>.",
            "#06b6d4"))

    # Compose output
    if not signals and n_spins < 10:
        summary_html = """<div style="text-align:center;padding:20px;color:#94a3b8;font-size:13px;">
  🧠 Smart Decision Summary will appear after 10+ spins are entered.<br>
  <small style="color:#94a3b8;">Enter your spins above and the app will guide you.</small>
</div>"""
    elif not signals:
        summary_html = """<div style="background:#0f172a;border-radius:6px;padding:12px;
  border:1px solid #1e3a5f;color:#cbd5e1;font-size:13px;">
  ⚖️ <b style="color:#e2e8f0;">ALL CLEAR</b> — Everything is in normal range right now. No strong signals
  anywhere. This means: <b style="color:#e2e8f0;">be patient</b>. Don't force bets when the numbers aren't
  screaming at you. Wait for a 🔴 signal to appear — that's when you strike.
</div>"""
    else:
        signals.sort(key=lambda x: x[0])
        items_html = ""
        for _, _label, text, color in signals:
            items_html += f"""<div style="background:#0f172a;border-left:4px solid {color};
  border-radius:0 6px 6px 0;padding:10px 12px;margin-bottom:8px;
  color:#e2e8f0;font-size:12px;line-height:1.6;">{text}</div>"""
        summary_html = items_html

    return f"""<div style="background:linear-gradient(145deg,#0f172a,#1e293b);
  border-radius:8px;padding:14px;margin-bottom:12px;
  border:2px solid #4338ca;box-shadow:0 0 20px rgba(99,102,241,0.15);">
  <h3 style="color:#a5b4fc;margin:0 0 6px 0;font-size:16px;">
    🧠 Smart Decision Summary
    <span style="font-size:11px;font-weight:normal;color:#cbd5e1;margin-left:8px;">What should I do right now?</span>
  </h3>
  <p style="color:#94a3b8;font-size:11px;margin:0 0 10px 0;">
    This card reads ALL the data — sigma scores, drought counters, convergence probabilities,
    and active strategies — and gives you plain-English guidance.
  </p>
  {summary_html}
</div>"""


# ---------------------------------------------------------------------------
# Final Brain — The Unified Decision Engine
# ---------------------------------------------------------------------------

_FALLBACK_FINAL_BRAIN_HTML = """<div style="background:linear-gradient(135deg,#0a0a1a,#0d1117,#0a0a1a);
  border:2px solid #6366f1;border-radius:12px;padding:20px;color:#e2e8f0;
  font-family:'Segoe UI',system-ui,sans-serif;">
  <p style="color:#94a3b8;font-size:14px;text-align:center;">
    🧠 Final Brain loading... Enter your spins to activate.
  </p>
</div>"""


def render_final_brain_html(state):
    """Render the Final Brain — the always-visible unified decision engine.

    Aggregates ALL available signals (sigma, drought, sniper, trinity, L/R/Z
    momentum, non-repeater, labouchere) and produces a single high-conviction
    recommendation with an explanation.

    Returns an HTML string.
    """
    try:
        return _render_final_brain_html_inner(state)
    except Exception:
        return _FALLBACK_FINAL_BRAIN_HTML


def _render_final_brain_html_inner(state):  # noqa: C901
    n_spins = len(getattr(state, 'last_spins', []))

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------
    def _sigma_calc(actual, n, cat_size):
        if n < 6:
            return None
        p = cat_size / 37.0
        expected = n * p
        std = math.sqrt(n * p * (1.0 - p))
        return (actual - expected) / std if std > 0 else None

    def _drought_prob(drought, p):
        return (1.0 - p) ** drought if drought > 0 else 1.0

    def _conv_prob(p, n):
        return 1.0 - (1.0 - p) ** n

    # -----------------------------------------------------------------------
    # Compute a unified confidence score for each category.
    # Score = weighted combination of:
    #   40% sigma signal strength  (scale: -3σ→0, -2σ→50, -1.5σ→30, etc.)
    #   35% drought convergence    (probability of hitting in next 5 spins)
    #   15% drought rarity         (how unusual the drought is — inverted %)
    #   10% recency momentum       (last-10 sigma compared to all-time sigma)
    # -----------------------------------------------------------------------
    _CAT_DEFS = {
        "1st Dozen":  ("dozen_scores",      12, 12 / 37),
        "2nd Dozen":  ("dozen_scores",      12, 12 / 37),
        "3rd Dozen":  ("dozen_scores",      12, 12 / 37),
        "1st Column": ("column_scores",     12, 12 / 37),
        "2nd Column": ("column_scores",     12, 12 / 37),
        "3rd Column": ("column_scores",     12, 12 / 37),
        "Red":        ("even_money_scores", 18, 18 / 37),
        "Black":      ("even_money_scores", 18, 18 / 37),
        "Even":       ("even_money_scores", 18, 18 / 37),
        "Odd":        ("even_money_scores", 18, 18 / 37),
        "Low":        ("even_money_scores", 18, 18 / 37),
        "High":       ("even_money_scores", 18, 18 / 37),
    }

    drought_counters = getattr(state, 'drought_counters', {})

    # Build windowed (last-10) scores for recency
    last_spins = getattr(state, 'last_spins', [])
    recent = last_spins[-10:] if len(last_spins) >= 10 else last_spins
    _DOZEN_R = {"1st Dozen": range(1, 13), "2nd Dozen": range(13, 25), "3rd Dozen": range(25, 37)}
    _COL_N = {
        "1st Column": {1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34},
        "2nd Column": {2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35},
        "3rd Column": {3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36},
    }
    _RED = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
    r_dozen = {"1st Dozen": 0, "2nd Dozen": 0, "3rd Dozen": 0}
    r_col = {"1st Column": 0, "2nd Column": 0, "3rd Column": 0}
    r_em = {"Red": 0, "Black": 0, "Even": 0, "Odd": 0, "Low": 0, "High": 0}
    for sp in recent:
        try:
            v = int(sp)
        except (ValueError, TypeError):
            continue
        if v == 0:
            continue
        for dn, r in _DOZEN_R.items():
            if v in r:
                r_dozen[dn] += 1
        for cn, ns in _COL_N.items():
            if v in ns:
                r_col[cn] += 1
        r_em["Red" if v in _RED else "Black"] += 1
        r_em["Even" if v % 2 == 0 else "Odd"] += 1
        r_em["Low" if 1 <= v <= 18 else "High"] += 1
    r_n = len(recent)

    def _recent_score(cat_key, name):
        if cat_key == "dozen_scores":
            return r_dozen.get(name, 0)
        if cat_key == "column_scores":
            return r_col.get(name, 0)
        return r_em.get(name, 0)

    scores_by_cat = {}
    for name, (cat_key, cat_size, p) in _CAT_DEFS.items():
        actual = getattr(state, cat_key, {}).get(name, 0)
        sigma = _sigma_calc(actual, n_spins, cat_size)
        drought = drought_counters.get(name, 0)
        drought_pct = _drought_prob(drought, p) * 100    # prob of this drought being random
        conv5 = _conv_prob(p, 5) * 100                   # prob hit in next 5

        # sigma component: cold = positive score, hot = negative, None = 0
        if sigma is None:
            sig_score = 0.0
        elif sigma <= -2.5:
            sig_score = 100.0
        elif sigma <= -2.0:
            sig_score = 80.0
        elif sigma <= -1.5:
            sig_score = 55.0
        elif sigma <= -1.0:
            sig_score = 30.0
        elif sigma >= 2.0:
            sig_score = -20.0  # hot = slight negative (may continue hot)
        else:
            sig_score = max(0.0, -sigma * 15)

        # drought rarity component: rarer = higher score
        drought_rarity = max(0.0, min(100.0, 100.0 - drought_pct))

        # recency component: recent sigma
        r_actual = _recent_score(cat_key, name)
        r_sigma = _sigma_calc(r_actual, r_n, cat_size)
        if r_sigma is None or sigma is None:
            recency_score = 0.0
        elif r_sigma <= sigma:          # getting colder recently → extra signal
            recency_score = min(40.0, abs(r_sigma - sigma) * 15)
        else:
            recency_score = -10.0       # getting warmer recently → reduce confidence

        confidence = (
            sig_score * 0.40
            + conv5 * 0.35
            + drought_rarity * 0.15
            + recency_score * 0.10
        )
        confidence = max(0.0, min(99.0, confidence))

        scores_by_cat[name] = {
            "confidence": confidence,
            "sigma": sigma,
            "drought": drought,
            "conv5": conv5,
            "conv10": _conv_prob(p, 10) * 100,
            "drought_pct": drought_pct,
            "cat_size": cat_size,
        }

    # -----------------------------------------------------------------------
    # Special signals that boost confidence
    # -----------------------------------------------------------------------
    sniper_locked = getattr(state, 'sniper_locked', False)
    sniper_locked_misses = getattr(state, 'sniper_locked_misses', 0)
    sniper_threshold = getattr(state, 'sniper_threshold', 22)
    lab_active = getattr(state, 'lab_active', False)
    lab_sequence = getattr(state, 'lab_sequence', [])
    trinity_dozen = getattr(state, 'trinity_dozen', '')
    current_nr = getattr(state, 'current_non_repeaters', set())
    nr_target = 12

    # L/R momentum from last_spins
    _RIGHT = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18}
    lr_recent = []
    for sp in last_spins[-8:]:
        try:
            v = int(sp)
        except (ValueError, TypeError):
            continue
        if v == 0:
            lr_recent.append('Z')
        elif v in _RIGHT:
            lr_recent.append('R')
        else:
            lr_recent.append('L')
    # Count consecutive identical side from the most recent spin backwards
    lr_side = lr_recent[-1] if lr_recent else 'Z'
    lr_run = 0
    for side in reversed(lr_recent):
        if side == lr_side:
            lr_run += 1
        else:
            break
    lr_signal = lr_run >= 4 and lr_side != 'Z'

    # -----------------------------------------------------------------------
    # Sort by confidence and get top recommendation
    # -----------------------------------------------------------------------
    sorted_cats = sorted(scores_by_cat.items(), key=lambda x: x[1]["confidence"], reverse=True)

    # -----------------------------------------------------------------------
    # Build the output
    # -----------------------------------------------------------------------

    # Top-level header
    if n_spins < 6:
        return f"""<style>
#final-brain-display b, #final-brain-display strong {{ color: #e2e8f0 !important; }}
</style>
<div id="final-brain-display" style="
  background:linear-gradient(135deg,#0a0a1a,#0d1117,#0a0a1a);
  border:2px solid #6366f1;border-radius:12px;padding:22px;
  font-family:'Segoe UI',system-ui,sans-serif;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
    <span style="font-size:28px;">🧠</span>
    <div>
      <div style="color:#a5b4fc;font-size:20px;font-weight:800;letter-spacing:1px;">🧠 WheelPulse Pro Max's Recommendation</div>
    </div>
    <div style="margin-left:auto;background:#1e293b;border:1px solid #334155;
         border-radius:8px;padding:6px 12px;color:#94a3b8;font-size:12px;">
      {n_spins} spin{'s' if n_spins != 1 else ''} entered
    </div>
  </div>
  <div style="background:#0f172a;border:1px dashed #334155;border-radius:8px;
       padding:16px;text-align:center;color:#94a3b8;font-size:14px;">
    Waiting for data... Keep entering spins and the Recommendation Engine will guide you.
  </div>
</div>"""

    top_name, top_data = sorted_cats[0]
    confidence = top_data["confidence"]
    sigma = top_data["sigma"]
    drought = top_data["drought"]
    conv5 = top_data["conv5"]
    conv10 = top_data["conv10"]

    # Store confidence score in state for auto-size bet logic
    state.live_brain_last_confidence = int(confidence)

    # Update custom progression name based on current recommendation type.
    # Only set/update when the name changes so the step index is preserved.
    _recommended_prog = get_custom_progression_for_bet(top_name)
    # Reset step when the progression type changes (different bet category)
    if getattr(state, 'live_brain_custom_progression_name', '') != _recommended_prog:
        state.live_brain_custom_progression_name = _recommended_prog
        state.live_brain_custom_progression_step = 0

    # Determine alert level
    if sniper_locked:
        alert_level = "SNIPER"
        alert_color = "#7c3aed"
        alert_border = "#8b5cf6"
    elif confidence >= 70:
        alert_level = "HIGH CONFIDENCE"
        alert_color = "#dc2626"
        alert_border = "#ef4444"
    elif confidence >= 45:
        alert_level = "MODERATE SIGNAL"
        alert_color = "#d97706"
        alert_border = "#f59e0b"
    elif confidence >= 25:
        alert_level = "WEAK SIGNAL"
        alert_color = "#0891b2"
        alert_border = "#06b6d4"
    else:
        alert_level = "ALL CLEAR"
        alert_color = "#16a34a"
        alert_border = "#22c55e"

    # Build reason list
    reasons = []
    if sigma is not None and sigma <= -1.5:
        reasons.append(f"📉 Sigma: <b style='color:#e2e8f0;'>{sigma:.1f}σ</b> — running cold vs expected")
    if drought > 0:
        reasons.append(f"⏱️ Drought: <b style='color:#e2e8f0;'>{drought} spins</b> since last hit (conv. {conv5:.0f}% in 5 / {conv10:.0f}% in 10)")
    if top_data["drought_pct"] < 10:
        reasons.append(f"🚨 Only <b style='color:#e2e8f0;'>{top_data['drought_pct']:.1f}%</b> chance this drought is random")
    if getattr(state, 'strategy_trinity_enabled', False) and trinity_dozen and top_name == trinity_dozen:
        reasons.append("🔺 Trinity Sensor confirms — coldest dozen")
    if lr_signal:
        side_name = "Low (1-18)" if lr_side == 'R' else "High (19-36)"
        reasons.append(f"🧭 L/R momentum: <b style='color:#e2e8f0;'>{lr_side}×{lr_run}</b> consecutive → {side_name} on a run")
    if getattr(state, 'strategy_sniper_enabled', False) and sniper_locked:
        reasons.append(f"⚡ SNIPER ACTIVE — {sniper_locked_misses} misses on a street — 87-phase progression engaged")
    if getattr(state, 'strategy_lab_enabled', False) and lab_active and lab_sequence:
        next_bet = lab_sequence[0] + lab_sequence[-1] if len(lab_sequence) >= 2 else lab_sequence[0]
        reasons.append(f"🔥 Labouchere running — {len(lab_sequence)} steps left, next bet ${next_bet:.2f}")
    if getattr(state, 'strategy_nr_enabled', False) and current_nr and len(current_nr) >= int(nr_target * 0.8):
        reasons.append(f"🎯 Non-Repeater Radar: {len(current_nr)} numbers IN — approaching target of {nr_target}")

    if not reasons:
        reasons.append("📊 Normal variance — no extreme signals, but this is the strongest available bet")

    reasons_html = "".join(
        f'<li style="color:#cbd5e1;font-size:13px;padding:3px 0;">{r}</li>'
        for r in reasons
    )

    # Confidence bar
    bar_color = alert_color
    bar_width = int(confidence)

    # Top 3 signals mini-table
    top3_html = ""
    for i, (cat_name, cat_data) in enumerate(sorted_cats[:4]):
        c = cat_data["confidence"]
        s = cat_data["sigma"]
        sigma_str = f"{s:+.1f}σ" if s is not None else "—"
        d = cat_data["drought"]
        if i == 0:
            bg = "#1e1b3b"
            border = alert_border
            text = "#e2e8f0"
            rank = "🥇"
        elif i == 1:
            bg = "#1e293b"
            border = "#334155"
            text = "#cbd5e1"
            rank = "🥈"
        elif i == 2:
            bg = "#1e293b"
            border = "#334155"
            text = "#94a3b8"
            rank = "🥉"
        else:
            bg = "#131a2a"
            border = "#1e293b"
            text = "#94a3b8"
            rank = "  "
        top3_html += f"""<div style="display:flex;align-items:center;gap:8px;
  background:{bg};border-left:3px solid {border};border-radius:4px;
  padding:6px 10px;margin-bottom:4px;">
  <span style="font-size:14px;">{rank}</span>
  <span style="flex:1;color:{text};font-size:13px;font-weight:600;">{cat_name}</span>
  <span style="color:{text};font-size:12px;">{sigma_str}</span>
  <span style="color:#94a3b8;font-size:11px;">{d}dr</span>
  <span style="background:{bar_color if i == 0 else '#334155'};color:white;
       font-size:11px;font-weight:700;padding:2px 7px;border-radius:10px;">{c:.0f}%</span>
</div>"""

    # Main "If I were you" advisory — only show when signal is meaningful
    if alert_level in ("HIGH CONFIDENCE", "SNIPER", "MODERATE SIGNAL"):
        if sniper_locked:
            advisory_text = (
                f"⚡ SNIPER IS ACTIVE! Play the 87-phase progression system on the street that missed "
                f"{sniper_locked_misses} times. Trust the math — 99.97% hit rate within 87 phases."
            )
            # Plain-text version for state storage — includes "Street 1-2-3" so
            # auto-detection can match if the user bets on that street.
            _suggestion_plain = f"SNIPER: play 87-phase on Street 1-2-3 ({sniper_locked_misses} misses)"
        else:
            advisory_text = (
                f"👉 If I were you, right now I would "
                f"<span style='color:#fbbf24;font-weight:900;text-decoration:underline;'>target {top_name}</span>. "
                f"It's been cold for <span style='color:#fca5a5;'>{drought} spins</span> and sigma is at "
                f"<span style='color:#fca5a5;'>{f'{sigma:.1f}' if sigma is not None else '?'}σ</span>. "
                f"There is a <span style='color:#86efac;'>{conv5:.0f}%</span> chance it hits in the next 5 spins. "
                f"The math favours this bet right now."
            )
            _suggestion_plain = f"Target {top_name} (confidence {confidence:.0f}%)"
        # Store the current suggestion in state for Live Brain tracking
        state.live_brain_last_suggestion = _suggestion_plain
        advisory_html = f"""<div style="margin-top:16px;
  background:linear-gradient(135deg,#1a0a2e,#2d1b69,#1e1b4b);
  border:2px solid {alert_border};border-radius:12px;padding:20px 24px;
  animation:final-brain-glow 2.5s ease-in-out infinite;
  box-shadow:0 0 30px {alert_color}55;">
  <div style="color:#fff;font-size:20px;font-weight:900;line-height:1.6;
    text-shadow:0 0 10px {alert_color}88;">
    {advisory_text}
  </div>
</div>"""
    else:
        _suggestion_plain = f"No strong signal — best option: {top_name} ({confidence:.0f}%)"
        state.live_brain_last_suggestion = _suggestion_plain
        advisory_html = f"""<div style="margin-top:16px;background:#0f172a;
  border:1px solid #334155;border-radius:10px;padding:14px 18px;">
  <div style="color:#94a3b8;font-size:15px;font-weight:600;line-height:1.5;">
    ⚖️ No strong signal right now. The wheel is in normal variance — be patient and wait for a 🔴 signal.
    If you must bet, <b style="color:#e2e8f0;">{top_name}</b> is the statistically best option available.
  </div>
</div>"""

    return f"""<style>
#final-brain-display b, #final-brain-display strong, #final-brain-display li {{ color: #e2e8f0 !important; }}
</style>
<div id="final-brain-display" style="
  background:linear-gradient(135deg,#0a0a1a,#0d1117,#0a0a1a);
  border:2px solid {alert_border};border-radius:12px;padding:22px;
  font-family:'Segoe UI',system-ui,sans-serif;
  box-shadow:0 0 30px {alert_color}33;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap;">
    <span style="font-size:28px;">🧠</span>
    <div style="flex:1;min-width:200px;">
      <div style="color:#a5b4fc;font-size:20px;font-weight:800;letter-spacing:1px;">🧠 WheelPulse Pro Max's Recommendation</div>
      <div style="color:#94a3b8;font-size:11px;">Live Decision Engine · {n_spins} spins analysed</div>
    </div>
    <div style="background:{alert_color}22;border:2px solid {alert_border};
         border-radius:8px;padding:8px 16px;text-align:center;">
      <div style="color:{alert_border};font-size:11px;font-weight:700;letter-spacing:2px;">{alert_level}</div>
      <div style="color:#fff;font-size:24px;font-weight:900;">{confidence:.0f}%</div>
      <div style="color:#94a3b8;font-size:10px;">confidence</div>
    </div>
  </div>

  <div style="background:#0f172a;height:8px;border-radius:4px;margin-bottom:16px;">
    <div style="background:linear-gradient(90deg,{alert_color},{alert_border});
         height:100%;width:{bar_width}%;border-radius:4px;
         transition:width 0.5s ease;"></div>
  </div>

  <div style="margin-bottom:16px;">
    <div style="color:#94a3b8;font-size:11px;text-transform:uppercase;
         letter-spacing:1px;margin-bottom:8px;">📊 Signal Rankings</div>
    {top3_html}
  </div>

  <div style="margin-bottom:14px;">
    <div style="color:#94a3b8;font-size:11px;text-transform:uppercase;
         letter-spacing:1px;margin-bottom:6px;">🔍 Why {top_name}?</div>
    <ul style="margin:0;padding-left:18px;">{reasons_html}</ul>
  </div>

  {advisory_html}
</div>"""


# ===========================================================================
# Master Information — LAST MONEY BET (1 unit, Survival mode)
# ===========================================================================

_FALLBACK_MASTER_INFO_HTML = (
    '<div style="background:#0f172a;border-radius:8px;padding:14px;'
    'color:#94a3b8;text-align:center;font-size:13px;">'
    '🎯 Master Information — refreshing...</div>'
)

# Roulette number sets used by the engine (European, 0-36).
_MI_EVEN_MONEY = {
    "Red":   frozenset([1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]),
    "Black": frozenset([2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35]),
    "Even":  frozenset(range(2, 37, 2)),
    "Odd":   frozenset(range(1, 37, 2)),
    "Low":   frozenset(range(1, 19)),
    "High":  frozenset(range(19, 37)),
}
_MI_DOZENS = {
    "1st Dozen": frozenset(range(1, 13)),
    "2nd Dozen": frozenset(range(13, 25)),
    "3rd Dozen": frozenset(range(25, 37)),
}
_MI_COLUMNS = {
    "1st Column": frozenset([1,4,7,10,13,16,19,22,25,28,31,34]),
    "2nd Column": frozenset([2,5,8,11,14,17,20,23,26,29,32,35]),
    "3rd Column": frozenset([3,6,9,12,15,18,21,24,27,30,33,36]),
}
_MI_SIX_LINES = {
    "Six-Line 1-6":   frozenset([1,2,3,4,5,6]),
    "Six-Line 4-9":   frozenset([4,5,6,7,8,9]),
    "Six-Line 7-12":  frozenset([7,8,9,10,11,12]),
    "Six-Line 10-15": frozenset([10,11,12,13,14,15]),
    "Six-Line 13-18": frozenset([13,14,15,16,17,18]),
    "Six-Line 16-21": frozenset([16,17,18,19,20,21]),
    "Six-Line 19-24": frozenset([19,20,21,22,23,24]),
    "Six-Line 22-27": frozenset([22,23,24,25,26,27]),
    "Six-Line 25-30": frozenset([25,26,27,28,29,30]),
    "Six-Line 28-33": frozenset([28,29,30,31,32,33]),
    "Six-Line 31-36": frozenset([31,32,33,34,35,36]),
}
_MI_STREETS = {
    "Street 1-3":   frozenset([1,2,3]),
    "Street 4-6":   frozenset([4,5,6]),
    "Street 7-9":   frozenset([7,8,9]),
    "Street 10-12": frozenset([10,11,12]),
    "Street 13-15": frozenset([13,14,15]),
    "Street 16-18": frozenset([16,17,18]),
    "Street 19-21": frozenset([19,20,21]),
    "Street 22-24": frozenset([22,23,24]),
    "Street 25-27": frozenset([25,26,27]),
    "Street 28-30": frozenset([28,29,30]),
    "Street 31-33": frozenset([31,32,33]),
    "Street 34-36": frozenset([34,35,36]),
}
_MI_CORNERS = {
    "Corner 1-5":   frozenset([1,2,4,5]),
    "Corner 2-6":   frozenset([2,3,5,6]),
    "Corner 4-8":   frozenset([4,5,7,8]),
    "Corner 5-9":   frozenset([5,6,8,9]),
    "Corner 7-11":  frozenset([7,8,10,11]),
    "Corner 8-12":  frozenset([8,9,11,12]),
    "Corner 10-14": frozenset([10,11,13,14]),
    "Corner 11-15": frozenset([11,12,14,15]),
    "Corner 13-17": frozenset([13,14,16,17]),
    "Corner 14-18": frozenset([14,15,17,18]),
    "Corner 16-20": frozenset([16,17,19,20]),
    "Corner 17-21": frozenset([17,18,20,21]),
    "Corner 19-23": frozenset([19,20,22,23]),
    "Corner 20-24": frozenset([20,21,23,24]),
    "Corner 22-26": frozenset([22,23,25,26]),
    "Corner 23-27": frozenset([23,24,26,27]),
    "Corner 25-29": frozenset([25,26,28,29]),
    "Corner 26-30": frozenset([26,27,29,30]),
    "Corner 28-32": frozenset([28,29,31,32]),
    "Corner 29-33": frozenset([29,30,32,33]),
    "Corner 31-35": frozenset([31,32,34,35]),
    "Corner 32-36": frozenset([32,33,35,36]),
}

# Payout multipliers for each coverage size (net profit on 1 unit staked)
_MI_PAYOUT = {
    18: 1,   # even money
    12: 2,   # dozen / column
    6:  5,   # six-line
    4:  8,   # corner
    3:  11,  # street
    2:  17,  # split
    1:  35,  # straight-up
}

# Window size for hit-rate calculation (aligned with existing brain HUD default)
_MI_WINDOW = 36


def _mi_compute_drought(numbers: frozenset, last_spins: list) -> int:
    """Return spins since any number in *numbers* last appeared in *last_spins*.

    Returns len(last_spins) if none of the numbers appear (worst-case drought).
    """
    for i, sp in enumerate(reversed(last_spins)):
        try:
            v = int(sp)
        except (ValueError, TypeError):
            continue
        if v in numbers:
            return i  # i == 0 means last spin was a hit
    return len(last_spins)


def _mi_compute_hits(numbers: frozenset, spins_window: list) -> int:
    """Count how many spins in *spins_window* landed on a number in *numbers*."""
    count = 0
    for sp in spins_window:
        try:
            v = int(sp)
        except (ValueError, TypeError):
            continue
        if v in numbers:
            count += 1
    return count


def compute_last_money_recommendation(state):
    """Compute and return the LAST MONEY BET recommendation.

    Objective: **Survival** — maximise the probability of winning *something*
    on the next spin from a single 1-unit stake.

    Scoring model (weights documented here and reflected in the explanation):
      - Coverage component   (w=0.35): p = |numbers|/37 — base win probability
      - Cold factor          (w=0.40): how far below expected hit-rate in last W spins
      - Drought factor       (w=0.20): spins since last hit / (2 × expected interval)
      - Recency momentum     (w=0.05): short micro-window cold signal (last 10 spins)

    Returns a list of dicts sorted by score (descending), each containing:
        label, bet_type, numbers, coverage, payout,
        hits_W, expected_W, hit_rate, drought, score, signals (list of str)
    """
    last_spins = getattr(state, 'last_spins', [])
    n = len(last_spins)

    # Build candidate universe
    candidates = []

    # Even money (coverage=18, payout=1)
    for label, nums in _MI_EVEN_MONEY.items():
        candidates.append(("even_money", label, nums))
    # Dozens (coverage=12, payout=2)
    for label, nums in _MI_DOZENS.items():
        candidates.append(("dozen", label, nums))
    # Columns (coverage=12, payout=2)
    for label, nums in _MI_COLUMNS.items():
        candidates.append(("column", label, nums))
    # Six-lines (coverage=6, payout=5)
    for label, nums in _MI_SIX_LINES.items():
        candidates.append(("six_line", label, nums))
    # Streets (coverage=3, payout=11)
    for label, nums in _MI_STREETS.items():
        candidates.append(("street", label, nums))
    # Corners (coverage=4, payout=8)
    for label, nums in _MI_CORNERS.items():
        candidates.append(("corner", label, nums))

    # Straight-ups: top 12 by score + extreme drought numbers (capped at 18 total)
    scores_dict = getattr(state, 'scores', {})
    # Select top-12 by hit frequency (hottest numbers by all-time score)
    top_su = sorted(
        ((num, sc) for num, sc in scores_dict.items() if num != 0),
        key=lambda x: x[1], reverse=True
    )[:12]
    su_candidates = set(num for num, _ in top_su)
    # Add up to 6 extreme-drought straight-ups (never/rarely hit)
    if n > 0:
        drought_su = sorted(
            ((num, _mi_compute_drought(frozenset([num]), last_spins))
             for num in range(1, 37) if num not in su_candidates),
            key=lambda x: x[1], reverse=True
        )[:6]
        su_candidates |= set(num for num, _ in drought_su)
    for num in su_candidates:
        label = f"Straight Up {num}"
        candidates.append(("straight_up", label, frozenset([num])))

    # Score every candidate
    W = min(_MI_WINDOW, n) if n > 0 else _MI_WINDOW
    spins_window = last_spins[-W:] if W > 0 else []
    micro_window = last_spins[-10:] if len(last_spins) >= 10 else last_spins

    scored = []
    for bet_type, label, numbers in candidates:
        coverage = len(numbers)
        p = coverage / 37.0
        payout = _MI_PAYOUT.get(coverage, 1)

        # --- Component 1: Coverage (base survival probability, normalized 0..1)
        cov_component = p  # 18/37 ≈ 0.486 for even money

        if n < 3:
            # Not enough data — rank purely by coverage (survival first)
            score = round(cov_component, 6)
            scored.append({
                "label": label,
                "bet_type": bet_type,
                "numbers": numbers,
                "coverage": coverage,
                "payout": payout,
                "hits_W": 0,
                "expected_W": 0.0,
                "hit_rate": 0.0,
                "drought": 0,
                "score": score,
                "signals": ["Coverage: {}/{} = {:.1%}".format(coverage, 37, p)],
            })
            continue

        # --- Component 2: Cold factor in last W spins (mean reversion signal)
        hits_W = _mi_compute_hits(numbers, spins_window)
        expected_W = W * p
        if expected_W > 0:
            cold_factor = max(0.0, min(1.0,
                (expected_W - hits_W) / expected_W
            ))
        else:
            cold_factor = 0.0

        # --- Component 3: Drought pressure
        drought = _mi_compute_drought(numbers, last_spins)
        expected_interval = 37.0 / coverage  # avg spins between hits
        drought_factor = min(1.0, drought / max(1.0, 2.0 * expected_interval))

        # --- Component 4: Micro-window recency (last 10 spins cold signal)
        micro_hits = _mi_compute_hits(numbers, micro_window)
        micro_w = len(micro_window)
        micro_expected = micro_w * p if micro_w > 0 else 0.0
        if micro_expected > 0:
            recency_cold = max(0.0, min(1.0,
                (micro_expected - micro_hits) / micro_expected
            ))
        else:
            recency_cold = 0.0

        # --- Final score (deterministic weights, sum = 1.0)
        score = (
            0.35 * cov_component
            + 0.40 * cold_factor
            + 0.20 * drought_factor
            + 0.05 * recency_cold
        )
        # Round to 6 dp for stability / avoid float noise
        score = round(score, 6)

        # --- Build explainable signals for this candidate
        hit_rate_pct = (hits_W / W * 100) if W > 0 else 0.0
        expected_pct = p * 100
        signals = [
            "Coverage: {}/{} = {:.1f}%  (win prob)".format(coverage, 37, p * 100),
            "Hit rate last {} spins: {}/{} = {:.1f}%  (expected {:.1f}%)".format(
                W, hits_W, W, hit_rate_pct, expected_pct),
            "Drought: {} spins since last hit  (expected ≈{:.0f})".format(
                drought, expected_interval),
        ]

        scored.append({
            "label": label,
            "bet_type": bet_type,
            "numbers": numbers,
            "coverage": coverage,
            "payout": payout,
            "hits_W": hits_W,
            "expected_W": round(expected_W, 1),
            "hit_rate": round(hit_rate_pct, 1),
            "drought": drought,
            "score": score,
            "signals": signals,
        })

    # Sort descending by score; tie-breaks: coverage (higher = safer), then
    # min number in set (deterministic numeric key, avoids string sort instability)
    scored.sort(key=lambda x: (-x["score"], -x["coverage"], min(x["numbers"])))
    return scored


def render_master_information_html(state, precomputed_recommendation=None):
    """Render the Master Information card for the 📊 Strategy Dashboard.

    Shows the LAST MONEY BET (1 unit, Survival mode) and runners-up with
    transparent scoring signals so users can verify the recommendation.

    Returns an HTML string.
    """
    try:
        return _render_master_information_html_inner(state, precomputed_recommendation)
    except Exception:
        return _FALLBACK_MASTER_INFO_HTML


def _render_master_information_html_inner(state, precomputed_recommendation=None):  # noqa: C901
    last_spins = getattr(state, 'last_spins', [])
    n = len(last_spins)

    # Minimum-data gate
    if n < 3:
        return """<div style="background:linear-gradient(135deg,#0a0a1a,#0d1117);
  border:2px solid #7c3aed;border-radius:12px;padding:20px;
  font-family:'Segoe UI',system-ui,sans-serif;">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
    <span style="font-size:22px;">🎯</span>
    <span style="color:#a78bfa;font-size:17px;font-weight:800;letter-spacing:1px;">
      MASTER INFORMATION — LAST MONEY BET
    </span>
  </div>
  <div style="background:#0f172a;border:1px dashed #4c1d95;border-radius:8px;
       padding:14px;text-align:center;color:#94a3b8;font-size:13px;">
    🎯 Enter at least 3 spins to activate the Last Money Bet engine.
  </div>
</div>"""

    ranked = (
        precomputed_recommendation
        if precomputed_recommendation is not None
        else compute_last_money_recommendation(state)
    )
    if not ranked:
        return _FALLBACK_MASTER_INFO_HTML

    best = ranked[0]
    W = min(_MI_WINDOW, n)

    # --- Colour theme based on bet type ---
    _TYPE_COLOUR = {
        "even_money": "#22c55e",
        "dozen":      "#3b82f6",
        "column":     "#06b6d4",
        "six_line":   "#f59e0b",
        "street":     "#f97316",
        "corner":     "#ec4899",
        "straight_up":"#a78bfa",
    }
    accent = _TYPE_COLOUR.get(best["bet_type"], "#7c3aed")
    accent_dim = accent + "33"

    # --- Bet type display label ---
    _TYPE_LABEL = {
        "even_money": "Even Money",
        "dozen":      "Dozen",
        "column":     "Column",
        "six_line":   "Six-Line (Double Street)",
        "street":     "Street",
        "corner":     "Corner",
        "straight_up":"Straight Up",
    }
    type_label = _TYPE_LABEL.get(best["bet_type"], best["bet_type"].replace("_", " ").title())

    # --- Score bar (0..1 → 0..100 px) ---
    bar_pct = int(best["score"] * 100)

    # --- Build bullet-list reason HTML ---
    reasons_html = "".join(
        f'<li style="color:#cbd5e1;font-size:12px;padding:2px 0;">{sig}</li>'
        for sig in best["signals"]
    )
    # Why it beats #2 / #3
    beat_parts = []
    for rival in ranked[1:3]:
        diff = best["score"] - rival["score"]
        beat_parts.append(
            f"<b style='color:#e2e8f0;'>{rival['label']}</b> "
            f"(score {rival['score']:.4f}, {diff:.4f} lower)"
        )
    if beat_parts:
        beat_line = (
            f'<li style="color:#94a3b8;font-size:12px;padding:2px 0;">'
            f'▲ Beats: {" · ".join(beat_parts)}</li>'
        )
    else:
        beat_line = ""

    # --- Runners-up mini-cards ---
    runners_html = ""
    for rank_i, rival in enumerate(ranked[1:3], start=2):
        rival_accent = _TYPE_COLOUR.get(rival["bet_type"], "#7c3aed")
        rival_type = _TYPE_LABEL.get(rival["bet_type"], rival["bet_type"].replace("_", " ").title())
        medal = "🥈" if rank_i == 2 else "🥉"
        runners_html += f"""<div style="background:#1e293b;border-left:3px solid {rival_accent};
  border-radius:6px;padding:8px 12px;margin-bottom:6px;display:flex;
  align-items:flex-start;gap:8px;flex-wrap:wrap;">
  <span style="font-size:15px;flex-shrink:0;">{medal}</span>
  <div style="flex:1;min-width:0;">
    <div style="color:{rival_accent};font-size:13px;font-weight:700;">
      {rival['label']}
      <span style="color:#94a3b8;font-size:11px;font-weight:400;margin-left:6px;">
        {rival_type} · {rival['coverage']}/37 · payout {rival['payout']}:1
      </span>
    </div>
    <div style="color:#94a3b8;font-size:11px;margin-top:2px;">
      Score {rival['score']:.4f} · Hit rate {rival['hit_rate']:.1f}% · Drought {rival['drought']} spins
    </div>
  </div>
</div>"""

    return f"""<style>
#master-info-card b, #master-info-card strong {{ color: #e2e8f0 !important; }}
@keyframes mi-glow {{
  0%,100% {{ box-shadow: 0 0 18px {accent}55; }}
  50%      {{ box-shadow: 0 0 32px {accent}88; }}
}}
</style>
<div id="master-info-card" style="
  background:linear-gradient(135deg,#0a0a1a,#0d1117,#0a0a1a);
  border:2px solid {accent};border-radius:12px;padding:20px;
  font-family:'Segoe UI',system-ui,sans-serif;
  animation:mi-glow 3s ease-in-out infinite;">

  <!-- Header -->
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap;">
    <span style="font-size:24px;">🎯</span>
    <div style="flex:1;min-width:160px;">
      <div style="color:#a78bfa;font-size:16px;font-weight:800;letter-spacing:1px;">
        MASTER INFORMATION — LAST MONEY BET
      </div>
      <div style="color:#94a3b8;font-size:11px;">
        Survival Mode · 1 unit stake · {n} spins analysed (window W={W})
      </div>
    </div>
    <div style="background:{accent_dim};border:2px solid {accent};
         border-radius:8px;padding:6px 12px;text-align:center;flex-shrink:0;">
      <div style="color:{accent};font-size:10px;font-weight:700;
           letter-spacing:2px;text-transform:uppercase;">Master Score</div>
      <div style="color:#fff;font-size:20px;font-weight:900;">{best['score']:.4f}</div>
    </div>
  </div>

  <!-- Score bar -->
  <div style="background:#0f172a;height:6px;border-radius:3px;margin-bottom:14px;">
    <div style="background:linear-gradient(90deg,{accent},{accent}cc);
         height:100%;width:{bar_pct}%;border-radius:3px;transition:width 0.4s ease;"></div>
  </div>

  <!-- Primary recommendation card -->
  <div style="background:linear-gradient(135deg,{accent}22,{accent}11);
       border:2px solid {accent};border-radius:10px;padding:14px 18px;
       margin-bottom:14px;">
    <div style="color:#94a3b8;font-size:10px;text-transform:uppercase;
         letter-spacing:2px;margin-bottom:6px;">🏆 LAST MONEY BET (1 unit)</div>
    <div style="color:#fff;font-size:22px;font-weight:900;margin-bottom:4px;">
      {best['label']}
    </div>
    <div style="color:{accent};font-size:12px;font-weight:600;margin-bottom:10px;">
      {type_label} · Covers {best['coverage']}/37 numbers · Payout {best['payout']}:1
    </div>
    <div style="color:#94a3b8;font-size:11px;text-transform:uppercase;
         letter-spacing:1px;margin-bottom:4px;">📋 Reason (why this bet beats all others)</div>
    <ul style="margin:0;padding-left:16px;">
      {reasons_html}
      {beat_line}
    </ul>
  </div>

  <!-- Runners-up -->
  <div style="margin-bottom:4px;">
    <div style="color:#94a3b8;font-size:11px;text-transform:uppercase;
         letter-spacing:1px;margin-bottom:6px;">📊 Runners-up (trust / verification)</div>
    {runners_html}
  </div>

  <div style="color:#475569;font-size:10px;text-align:right;margin-top:8px;">
    ⚠ Statistical model only — roulette outcomes are independent events.
    Score = 0.35×coverage + 0.40×cold-factor + 0.20×drought + 0.05×recency
  </div>
</div>"""


# ---------------------------------------------------------------------------
# AI Coach Prompt Reference Panel — module-level helpers & constants
# ---------------------------------------------------------------------------

# Sector definitions (European single-zero wheel) — defined once at import time
_AI_COACH_JEU_0     = frozenset({0, 3, 12, 15, 26, 32, 35})
_AI_COACH_VOISINS   = frozenset({0, 2, 3, 4, 7, 12, 15, 18, 19, 21, 22, 25, 26, 28, 29, 32, 35})
_AI_COACH_ORPHELINS = frozenset({1, 6, 9, 14, 17, 20, 31, 34})
_AI_COACH_TIERS     = frozenset({5, 8, 10, 11, 13, 16, 23, 24, 27, 30, 33, 36})

_AI_COACH_SECTOR_NUMBERS = {
    "Jeu 0":              sorted(_AI_COACH_JEU_0),
    "Voisins du Zéro":    sorted(_AI_COACH_VOISINS),
    "Orphelins":          sorted(_AI_COACH_ORPHELINS),
    "Tiers du Cylindre":  sorted(_AI_COACH_TIERS),
}
_AI_COACH_SECTOR_SETS = {
    "Jeu 0":              _AI_COACH_JEU_0,
    "Voisins du Zéro":    _AI_COACH_VOISINS,
    "Orphelins":          _AI_COACH_ORPHELINS,
    "Tiers du Cylindre":  _AI_COACH_TIERS,
}

_AI_COACH_RED_NUMS   = frozenset({1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36})
_AI_COACH_BLACK_NUMS = frozenset({2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35})

# Cache: keyed on (n_spins, hash_of_spins_tuple) → cached HTML string.
# The hash is process-scoped: Python's hash randomisation is fixed once per process start
# (PYTHONHASHSEED), so within a single server process the same spin list always produces
# the same key.  The cache is intentionally reset on every restart, which is what we want.
_ai_coach_cache: dict[str, object] = {"key": None, "html": None}


def _aco_js(text: str) -> str:
    """Escape *text* for use inside a JavaScript template literal."""
    return (
        text
        .replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("$", "\\$")
        .replace("\r\n", "\\n")
        .replace("\r", "\\n")
        .replace("\n", "\\n")
    )


def _aco_section(icon: str, title: str, body_html: str, copy_text: str) -> str:
    """Return a collapsible ``<details>`` section with a copy-to-clipboard button."""
    js_text = _aco_js(copy_text)
    section_key = re.sub(r'[^a-z0-9]+', '_',
                         re.sub(r'&[a-z]+;', '_', title.lower())).strip('_')
    return f"""<details data-section-key="{section_key}" style="margin-bottom:10px;">
  <summary style="cursor:pointer;padding:10px 14px;
    border-radius:8px;border:1px solid #d1d5db;
    background:#f8fafc;color:#1f2937;
    display:flex;align-items:center;gap:8px;
    font-family:'Segoe UI',system-ui,sans-serif;
    font-size:14px;font-weight:700;
    list-style:none;user-select:none;
    transition:box-shadow 0.2s;">
    <span style="font-size:16px;">{icon}</span>
    <span style="flex:1;color:#1f2937;">{title}</span>
    <button onclick="event.preventDefault();event.stopPropagation();
      navigator.clipboard.writeText(`{js_text}`).then(function(){{
        var b=this;b.textContent='✅ Copied!';
        setTimeout(function(){{b.textContent='📋 Copy';}},1800);
      }}.bind(this),function(){{this.textContent='❌ Failed';}}.bind(this));"
      aria-label="Copy analysis to clipboard"
      role="button"
      tabindex="0"
      onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();this.click();}}"
      style="font-size:11px;padding:3px 10px;border-radius:20px;border:1px solid #6366f1;
        color:#6366f1;background:#ffffff;cursor:pointer;flex-shrink:0;
        font-family:'Segoe UI',system-ui,sans-serif;">
      📋 Copy
    </button>
  </summary>
  <div style="padding:14px 16px;border-radius:0 0 8px 8px;
    border:1px solid #d1d5db;border-top:none;
    background:#ffffff;color:#1f2937;">
    {body_html}
  </div>
</details>"""


def _aco_sigma(actual, total_n, cat_size):
    """Return the binomial sigma score, or *None* if fewer than 10 observations."""
    if total_n < 10:
        return None
    p = cat_size / 37.0
    expected = total_n * p
    std = math.sqrt(total_n * p * (1.0 - p))
    return (actual - expected) / std if std > 0 else None


def _aco_sigma_label(s):
    """Convert a sigma score to a human-readable emoji + label string."""
    if s is None:
        return "⚪ n/a"
    if s >= 2.0:
        return f"🟢 +{s:.1f}σ (HOT)"
    if s >= 1.0:
        return f"🟡 +{s:.1f}σ (warm)"
    if s <= -2.0:
        return f"🔴 {s:.1f}σ (COLD)"
    if s <= -1.0:
        return f"🟠 {s:.1f}σ (cool)"
    sign = "+" if s >= 0 else ""
    return f"⚪ {sign}{s:.1f}σ (normal)"


def _aco_num_badge(num: int) -> str:
    """Return an inline-styled circular colour badge for a roulette number."""
    if num == 0:
        bg = "#16a34a"
    elif num in _AI_COACH_RED_NUMS:
        bg = "#dc2626"
    else:
        bg = "#1a1a1a"
    return (
        f'<span style="display:inline-flex;align-items:center;justify-content:center;'
        f'background:{bg};color:white;width:26px;height:26px;border-radius:50%;'
        f'font-weight:700;font-size:12px;flex-shrink:0;">{num}</span>'
    )


def _aco_em_sequence(spin_list, pred):
    """Build a binary sequence (1 = hit, 0 = miss) for an even-money predicate,
    excluding zeros from the sequence."""
    seq = []
    for s in spin_list:
        try:
            num = int(s)
        except (ValueError, TypeError):
            continue
        if num == 0:
            seq.append(None)
        else:
            seq.append(1 if pred(num) else 0)
    return [x for x in seq if x is not None]


def _aco_detect_pattern(seq, min_streak=3, min_chop=4):
    """Detect a STREAK or CHOP pattern in a binary sequence."""
    if not seq:
        return None, 0
    last = seq[-1]
    streak = 0
    for v in reversed(seq):
        if v == last:
            streak += 1
        else:
            break
    if streak >= min_streak:
        return "STREAK", streak
    chop = 1
    for i in range(len(seq) - 1, 0, -1):
        if seq[i] != seq[i - 1]:
            chop += 1
        else:
            break
    if chop >= min_chop:
        return "CHOP", chop
    return "NEUTRAL", 0


def _aco_sector_momentum(sname, last_spins):
    """Compare last-20 vs prior-20 hits for *sname* and return a momentum label."""
    snums = _AI_COACH_SECTOR_SETS[sname]
    recent = [int(s) for s in last_spins[-20:] if s.isdigit()]
    prior  = [int(s) for s in last_spins[-40:-20] if s.isdigit()]
    r_hits = sum(1 for x in recent if x in snums)
    p_hits = sum(1 for x in prior  if x in snums)
    exp_r  = len(recent) * len(snums) / 37.0 if recent else 0
    if not prior:
        return "➡️ Stable (insufficient history)"
    if r_hits > p_hits + 1 and r_hits > exp_r:
        return "↗️ Heating Up"
    if r_hits < p_hits - 1 and r_hits < exp_r:
        return "↘️ Cooling Down"
    return "➡️ Stable"


def render_ai_coach_prompt_html(state=None, precomputed_recommendation=None, pinned_numbers_raw=None) -> str:
    """Return a styled, collapsible HTML block with live Pulse AI Coach analysis.

    Reads state.last_spins, state.scores, state.even_money_scores,
    state.dozen_scores, state.column_scores, and state.drought_counters
    to generate real-time coaching output.  Falls back to a friendly
    waiting message when there are fewer than 5 spins.
    """
    try:
        return _render_ai_coach_prompt_html_inner(state, precomputed_recommendation, pinned_numbers_raw)
    except Exception:
        return _FALLBACK_AI_COACH_HTML


_FALLBACK_AI_COACH_HTML = """<div id="ai-coach-prompt-panel"
  style="border:2px solid #7c3aed;border-radius:12px;padding:20px;
  font-family:'Segoe UI',system-ui,sans-serif;margin-bottom:12px;">
  <div style="display:flex;align-items:center;gap:10px;">
    <span style="font-size:22px;">🤖</span>
    <span style="font-size:15px;font-weight:700;">Pulse AI Coach</span>
  </div>
  <p style="color:#6b7280;font-size:13px;margin-top:8px;">
    Coach is loading&hellip; Add spins to activate.
  </p>
</div>"""


def _render_ai_coach_prompt_html_inner(state, precomputed_recommendation=None, pinned_numbers_raw=None) -> str:  # noqa: C901
    # ---------------------------------------------------------------
    # Pull state data
    # ---------------------------------------------------------------
    last_spins      = getattr(state, 'last_spins', [])       if state else []
    scores          = getattr(state, 'scores', {})            if state else {}
    even_money      = getattr(state, 'even_money_scores', {}) if state else {}
    dozen_scores    = getattr(state, 'dozen_scores', {})      if state else {}
    column_scores   = getattr(state, 'column_scores', {})     if state else {}
    drought_counters = getattr(state, 'drought_counters', {}) if state else {}

    n = len(last_spins)
    pinned_numbers = getattr(state, 'pinned_numbers', set()) if state else set()

    # Sync pinned numbers from raw JSON if provided (mirrors de2d_tracker_logic logic)
    if pinned_numbers_raw and pinned_numbers_raw != "[]":
        try:
            import json as _json
            _pin_data = _json.loads(pinned_numbers_raw)
            pinned_numbers = {int(x) for x in _pin_data if str(x).isdigit()}
        except (ValueError, TypeError):
            pass
    elif pinned_numbers_raw == "[]":
        pinned_numbers = set()

    # Bug 2a fix: write synced pins back so downstream state reads stay consistent
    if state is not None:
        state.pinned_numbers = pinned_numbers

    # ---------------------------------------------------------------
    # Waiting message when not enough data
    # ---------------------------------------------------------------
    if n < 5:
        waiting_body = (
            '<div style="text-align:center;padding:20px 10px;">'
            '<span style="font-size:32px;">⏳</span>'
            '<p style="font-size:14px;font-weight:600;margin:10px 0 4px;">'
            'Waiting for spin data…</p>'
            '<p style="font-size:12px;color:#6b7280;margin:0;">'
            f'Add spins to activate the Pulse AI Coach. ({n}/5 spins entered)'
            '</p>'
            '</div>'
        )
        return _ai_coach_outer_html(waiting_body, n, live=False)

    # ---------------------------------------------------------------
    # Early-return: serve cached HTML when spin list + pins haven't changed
    # ---------------------------------------------------------------
    # Bug 2b fix: include scores hash so cache invalidates when scores change
    _scores_hash = hash(tuple(sorted(scores.items())))
    _spin_key = (n, hash(tuple(last_spins)), frozenset(pinned_numbers), _scores_hash)
    if (
        precomputed_recommendation is None
        and _ai_coach_cache["key"] == _spin_key
        and _ai_coach_cache["html"] is not None
    ):
        return _ai_coach_cache["html"]

    # Build rank map: number → rank position (1 = highest score)
    _all_nums_sorted = sorted(range(37), key=lambda x: scores.get(x, 0), reverse=True)
    _rank_map = {num: i + 1 for i, num in enumerate(_all_nums_sorted)}

    recent20 = last_spins[-20:]
    radar_lines = []

    _EM_PREDS = [
        ("Red/Black",  lambda num: num in _AI_COACH_RED_NUMS, "Red",   "Black"),
        ("Odd/Even",   lambda num: num % 2 == 1,               "Odd",   "Even"),
        ("Low/High",   lambda num: 1 <= num <= 18,             "Low",   "High"),
    ]

    # ---------------------------------------------------------------
    # Section A: PINNED STRONG NUMBERS
    # ---------------------------------------------------------------
    if pinned_numbers:
        _pinned_items = []
        for _pnum in sorted(pinned_numbers):
            _pbadge = _aco_num_badge(_pnum)
            _pscore = scores.get(_pnum, 0)
            _prank = _rank_map.get(_pnum, len(_rank_map))
            _pinned_items.append(
                f'<div style="display:inline-flex;align-items:center;gap:6px;'
                f'margin:3px;padding:4px 10px;border:1px solid #e5e7eb;border-radius:8px;">'
                f'{_pbadge}'
                f'<span style="font-size:13px;"><b>Rank #{_prank}</b>'
                f' &nbsp;·&nbsp; {_pscore} hits</span>'
                f'</div>'
            )
        pinned_strong_body = (
            '<div style="display:flex;flex-wrap:wrap;gap:4px;">'
            + "".join(_pinned_items)
            + '</div>'
        )
        pinned_strong_copy = (
            "PINNED STRONG NUMBERS:\n"
            + "\n".join(
                f"· {num} — Rank #{_rank_map[num]} · {scores.get(num, 0)} hits"
                for num in sorted(pinned_numbers)
            )
        )
    else:
        pinned_strong_body = (
            '<p style="font-size:13px;color:#6b7280;font-style:italic;margin:0;">'
            'No numbers pinned yet — star a number in the Strongest Numbers table.'
            '</p>'
        )
        pinned_strong_copy = "Pinned Strong Numbers: none pinned."

    # ---------------------------------------------------------------
    # Section B: PINNED RANKS — LIVE LEADERBOARD (category cards)
    # Matches the DE2D zone style: ranked cards for betting categories
    # (1st Dozen, 2nd Dozen, 3rd Dozen, 1st Column, 2nd Column, 3rd Column,
    #  Red, Black, Even, Odd, Low, High) with hit count, sigma, drought, conf.
    # ---------------------------------------------------------------
    _CAT_DEFS_RANKS = {
        "1st Dozen":  ("dozen_scores",      12, 12 / 37),
        "2nd Dozen":  ("dozen_scores",      12, 12 / 37),
        "3rd Dozen":  ("dozen_scores",      12, 12 / 37),
        "1st Column": ("column_scores",     12, 12 / 37),
        "2nd Column": ("column_scores",     12, 12 / 37),
        "3rd Column": ("column_scores",     12, 12 / 37),
        "Red":        ("even_money_scores", 18, 18 / 37),
        "Black":      ("even_money_scores", 18, 18 / 37),
        "Even":       ("even_money_scores", 18, 18 / 37),
        "Odd":        ("even_money_scores", 18, 18 / 37),
        "Low":        ("even_money_scores", 18, 18 / 37),
        "High":       ("even_money_scores", 18, 18 / 37),
    }
    # Build windowed (last-10) scores for recency component
    _recent10 = last_spins[-10:] if len(last_spins) >= 10 else last_spins
    _r10_dozen  = {"1st Dozen": 0, "2nd Dozen": 0, "3rd Dozen": 0}
    _r10_col    = {"1st Column": 0, "2nd Column": 0, "3rd Column": 0}
    _r10_em     = {"Red": 0, "Black": 0, "Even": 0, "Odd": 0, "Low": 0, "High": 0}
    _COL_SETS_R = {
        "1st Column": frozenset([1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34]),
        "2nd Column": frozenset([2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35]),
        "3rd Column": frozenset([3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36]),
    }
    for _sp10 in _recent10:
        try:
            _v10 = int(_sp10)
        except (ValueError, TypeError):
            continue
        if _v10 == 0:
            continue
        if 1 <= _v10 <= 12:
            _r10_dozen["1st Dozen"] += 1
        elif 13 <= _v10 <= 24:
            _r10_dozen["2nd Dozen"] += 1
        elif 25 <= _v10 <= 36:
            _r10_dozen["3rd Dozen"] += 1
        for _cn, _ns in _COL_SETS_R.items():
            if _v10 in _ns:
                _r10_col[_cn] += 1
        _r10_em["Red" if _v10 in _AI_COACH_RED_NUMS else "Black"] += 1
        _r10_em["Even" if _v10 % 2 == 0 else "Odd"] += 1
        _r10_em["Low" if 1 <= _v10 <= 18 else "High"] += 1
    _r10_n = len(_recent10)

    def _r10_score(cat_key, name):
        if cat_key == "dozen_scores":
            return _r10_dozen.get(name, 0)
        if cat_key == "column_scores":
            return _r10_col.get(name, 0)
        return _r10_em.get(name, 0)

    def _cat_confidence(actual, sigma, drought, p, cat_key, name, cat_size):
        """Confidence formula for the Pinned Ranks leaderboard - ranks HOT first."""
        # HOT (positive sigma) scores highest; COLD (negative sigma) is penalized.
        if sigma is None:
            _sig_score = 0.0
        elif sigma >= 2.5:
            _sig_score = 100.0   # HOT = highest confidence
        elif sigma >= 2.0:
            _sig_score = 80.0
        elif sigma >= 1.5:
            _sig_score = 55.0
        elif sigma >= 1.0:
            _sig_score = 30.0
        elif sigma <= -2.0:
            _sig_score = -20.0   # COLD = penalized
        else:
            _sig_score = max(0.0, sigma * 15)   # positive sigma only
        _drought_pct = ((1 - p) ** drought * 100) if drought > 0 else 100.0
        _drought_rarity = max(0.0, min(100.0, 100.0 - _drought_pct))
        _conv5 = (1 - (1 - p) ** 5) * 100
        _r_actual = _r10_score(cat_key, name)
        _r_sigma = _aco_sigma(_r_actual, _r10_n, cat_size)  # cat_size = 12 or 18
        if _r_sigma is None or sigma is None:
            _recency = 0.0
        elif _r_sigma >= sigma:   # heating up -> boost
            _recency = min(40.0, abs(_r_sigma - sigma) * 15)
        else:                     # cooling down -> penalize
            _recency = -10.0
        _conf = (_sig_score * 0.40 + _conv5 * 0.35
                 + _drought_rarity * 0.15 + _recency * 0.10)
        return max(0.0, min(99.0, _conf)), _conv5

    _rank_cats = []
    for _cname, (_ckey, _csize, _cp) in _CAT_DEFS_RANKS.items():
        _cactual  = getattr(state, _ckey, {}).get(_cname, 0) if state else 0
        _csigma   = _aco_sigma(_cactual, n, _csize)
        _cdrought = drought_counters.get(_cname, 0)
        _cconf, _cconv5 = _cat_confidence(_cactual, _csigma, _cdrought, _cp, _ckey, _cname, _csize)
        _rank_cats.append((_cname, _cactual, _csigma, _cdrought, _cconf, _cconv5))

    # Sort by confidence (same as Final Brain)
    _rank_cats.sort(key=lambda x: x[4], reverse=True)

    if n >= 5:
        _pr_items = []
        for _pr_rank, (_pr_name, _pr_hits, _pr_sig, _pr_dr, _pr_conf, _pr_conv5) in enumerate(_rank_cats, 1):
            _pr_sigma_str = _aco_sigma_label(_pr_sig)
            _pr_medal = (
                "🥇" if _pr_rank == 1 else
                "🥈" if _pr_rank == 2 else
                "🥉" if _pr_rank == 3 else
                f"#{_pr_rank}"
            )
            # Border color: gold=1st, silver=2nd, bronze=3rd, grey=rest
            _pr_border = (
                "#f59e0b" if _pr_rank == 1 else
                "#9ca3af" if _pr_rank == 2 else
                "#b45309" if _pr_rank == 3 else
                "#e5e7eb"
            )
            # Confidence badge: green ≥60% (strong signal), amber ≥35% (moderate), grey <35%
            _pr_conf_col = (
                "#16a34a" if _pr_conf >= 60 else
                "#d97706" if _pr_conf >= 35 else
                "#6b7280"
            )
            _pr_items.append(
                f'<div style="border-left:3px solid {_pr_border};padding:6px 10px;'
                f'border-radius:4px;border:1px solid {_pr_border};margin-bottom:5px;'
                f'display:flex;align-items:center;gap:6px;flex-wrap:wrap;">'
                f'<span style="font-size:13px;min-width:22px;">{_pr_medal}</span>'
                f'<span style="flex:1;font-size:13px;font-weight:700;">{_pr_name}</span>'
                f'<span style="font-size:11px;color:#374151;">{_pr_hits} hits</span>'
                f'<span style="font-size:11px;color:#374151;">{_pr_sigma_str}</span>'
                f'<span style="font-size:11px;color:#6b7280;">{_pr_dr} dr</span>'
                f'<span style="background:{_pr_conf_col};color:white;font-size:11px;'
                f'font-weight:700;padding:2px 7px;border-radius:10px;">{_pr_conf:.0f}%</span>'
                f'</div>'
            )
        pinned_ranks_body = (
            f'<div style="font-size:11px;color:#6b7280;margin-bottom:8px;">'
            f'Categories ranked by confidence · {n} spins · '
            f'<em>Hot sector</em> = above expected · <em>Cold</em> = due to hit</div>'
            + "".join(_pr_items)
        )
        pinned_ranks_copy = (
            "PINNED RANKS (LIVE LEADERBOARD):\n"
            + "\n".join(
                f"#{r} | {nm} | {hits} hits | {_aco_sigma_label(sig)} | {dr} dr | {conf:.0f}%"
                for r, (nm, hits, sig, dr, conf, _) in enumerate(_rank_cats, 1)
            )
        )
    else:
        pinned_ranks_body = (
            '<p style="font-size:13px;color:#6b7280;font-style:italic;margin:0;">'
            'No data yet — add more spins to see category rankings.</p>'
        )
        pinned_ranks_copy = "Live Leaderboard: no data yet."

    radar_copy_parts = []
    for em_name, pred, hit_label, miss_label in _EM_PREDS:
        seq = _aco_em_sequence(recent20, pred)
        pattern, length = _aco_detect_pattern(seq)
        hit_cnt = even_money.get(hit_label, 0)
        miss_cnt = even_money.get(miss_label, 0)
        hit_sigma = _aco_sigma(hit_cnt, n, 18)
        miss_sigma = _aco_sigma(miss_cnt, n, 18)
        best_em = hit_label if (hit_cnt >= miss_cnt) else miss_label
        best_sigma = hit_sigma if (hit_cnt >= miss_cnt) else miss_sigma
        sigma_str = _aco_sigma_label(best_sigma)

        if pattern == "STREAK":
            direction = hit_label if seq and seq[-1] == 1 else miss_label
            line = (
                f"<b>{em_name}</b>: "
                f"<span style='color:#ef4444;font-weight:700;'>🔥 {direction} STREAK</span> "
                f"({length} consecutive) · {sigma_str}"
            )
            copy_line = f"{em_name}: {direction} STREAK ({length} consecutive) · {sigma_str}"
        elif pattern == "CHOP":
            line = (
                f"<b>{em_name}</b>: "
                f"<span style='color:#f59e0b;font-weight:700;'>〰️ CHOPPING</span> "
                f"({length} alternations) · {sigma_str}"
            )
            copy_line = f"{em_name}: CHOPPING ({length} alternations) · {sigma_str}"
        else:
            line = (
                f"<b>{em_name}</b>: Neutral · "
                f"<b>{best_em}</b>: {sigma_str}"
            )
            copy_line = f"{em_name}: Neutral · {best_em}: {sigma_str}"
        radar_lines.append(f'<div style="margin-bottom:5px;">{line}</div>')
        radar_copy_parts.append(copy_line)

    # Top sigma categories (dozens + columns)
    _DOZEN_DEFS = {
        "1st Dozen": (dozen_scores.get("1st Dozen", 0), 12),
        "2nd Dozen": (dozen_scores.get("2nd Dozen", 0), 12),
        "3rd Dozen": (dozen_scores.get("3rd Dozen", 0), 12),
    }
    _COL_DEFS = {
        "1st Column": (column_scores.get("1st Column", 0), 12),
        "2nd Column": (column_scores.get("2nd Column", 0), 12),
        "3rd Column": (column_scores.get("3rd Column", 0), 12),
    }
    all_cats = {}
    all_cats.update(_DOZEN_DEFS)
    all_cats.update(_COL_DEFS)
    cat_sigmas = {nm: _aco_sigma(v, n, sz) for nm, (v, sz) in all_cats.items()}
    top_sigma = sorted(
        [(nm, s) for nm, s in cat_sigmas.items() if s is not None],
        key=lambda x: abs(x[1]), reverse=True
    )[:3]
    if top_sigma:
        radar_lines.append('<div style="margin-top:8px;font-size:12px;font-weight:700;">Top σ Signals:</div>')
        for nm, s in top_sigma:
            radar_lines.append(
                f'<div style="margin-bottom:3px;padding-left:8px;">'
                f'→ <b>{nm}</b>: {_aco_sigma_label(s)}'
                f'</div>'
            )
            radar_copy_parts.append(f"→ {nm}: {_aco_sigma_label(s)}")

    radar_body = "".join(radar_lines)
    radar_copy = "\n".join(radar_copy_parts)

    # ---------------------------------------------------------------
    # Section 2: HOT SECTOR
    # ---------------------------------------------------------------
    sector_hits = {}
    sector_expected = {}
    for sname, snums in _AI_COACH_SECTOR_SETS.items():
        hits = sum(scores.get(num, 0) for num in snums)
        sector_hits[sname] = hits
        p = len(snums) / 37.0
        sector_expected[sname] = n * p

    # Sigma per sector
    sector_sigma = {}
    for sname, snums in _AI_COACH_SECTOR_SETS.items():
        hits = sector_hits[sname]
        sz = len(snums)
        sector_sigma[sname] = _aco_sigma(hits, n, sz)

    hottest = max(sector_hits, key=lambda k: sector_hits[k])

    hot_sector_lines = []
    hot_sector_copy = []
    sector_order = sorted(
        _AI_COACH_SECTOR_SETS.keys(),
        key=lambda k: sector_hits[k], reverse=True
    )
    for rank, sname in enumerate(sector_order):
        hits = sector_hits[sname]
        exp = sector_expected[sname]
        sig = sector_sigma[sname]
        mom = _aco_sector_momentum(sname, last_spins)
        crown = "🔥 HOTTEST" if rank == 0 else ("❄️ COLDEST" if rank == 3 else "")
        crown_html = (
            f' <span style="color:#ef4444;font-weight:700;">{crown}</span>'
            if crown else ""
        )
        hot_sector_lines.append(
            f'<div style="margin-bottom:6px;">'
            f'<b>{sname}</b>{crown_html}: '
            f'{hits} hits (exp {exp:.1f}) · {_aco_sigma_label(sig)} · {mom}'
            f'</div>'
        )
        hot_sector_copy.append(
            f"{sname}{(' [' + crown + ']') if crown else ''}: "
            f"{hits} hits (exp {exp:.1f}) · {_aco_sigma_label(sig)} · {mom}"
        )

    hot_sector_body = "".join(hot_sector_lines)
    hot_sector_text = "\n".join(hot_sector_copy)

    # ---------------------------------------------------------------
    # Section 3: MASTER SIGNAL
    # ---------------------------------------------------------------
    ranked = (
        precomputed_recommendation
        if precomputed_recommendation is not None
        else (compute_last_money_recommendation(state) if state else [])
    )
    if ranked:
        best = ranked[0]
        master_label = best["label"]
        master_score = best["score"]
        master_signals_html = "".join(
            f'<div style="margin-bottom:3px;padding-left:8px;font-size:12px;">'
            f'· {sig}</div>'
            for sig in best["signals"]
        )
        score_color = "#22c55e" if master_score >= 0.60 else "#f59e0b"
        master_body = (
            f'<div style="margin-bottom:8px;">'
            f'<span style="font-size:18px;font-weight:900;">{master_label}</span>'
            f' &nbsp;'
            f'<span style="border-radius:6px;padding:3px 10px;border:1px solid {score_color};'
            f'color:{score_color};font-size:13px;font-weight:700;">'
            f'Score {master_score:.4f}</span>'
            f'</div>'
            f'<div style="font-size:12px;font-weight:700;margin-bottom:4px;">Why this bet:</div>'
            f'{master_signals_html}'
        )
        master_copy = (
            f"LAST MONEY BET: {master_label} (Score {master_score:.4f})\n"
            + "\n".join(f"· {s}" for s in best["signals"])
        )
    else:
        master_body = '<p style="font-size:13px;color:#6b7280;">Not enough data yet.</p>'
        master_copy = "Master Signal: not enough data."
        master_label = None
        master_score = 0.0

    # ---------------------------------------------------------------
    # Section 4: DOUBLE CONFIRMATION
    # ---------------------------------------------------------------
    # `hottest` is derived from _AI_COACH_SECTOR_SETS keys, so it is always valid.
    hot_sector_nums = _AI_COACH_SECTOR_SETS[hottest]
    master_nums = set(ranked[0]["numbers"]) if ranked else set()
    overlap = hot_sector_nums & master_nums

    if overlap:
        conf_pct = min(95, 60 + len(overlap) * 5)
        conf_color = "#22c55e"
        conf_label = "✅ CONFIRMED"
        conf_detail = (
            f"Hot sector ({hottest}) and Master Signal ({master_label}) "
            f"share {len(overlap)} number(s): {', '.join(str(x) for x in sorted(overlap))}. "
            f"This is a Double Confirmation — both signals point to the same zone."
        )
    elif ranked and sector_sigma.get(hottest) is not None and sector_sigma[hottest] >= 1.0:
        conf_pct = 55
        conf_color = "#f59e0b"
        conf_label = "⚠️ PARTIAL"
        conf_detail = (
            f"Hot sector ({hottest}) shows positive sigma "
            f"({_aco_sigma_label(sector_sigma[hottest])}) but the Master Signal "
            f"({master_label}) targets a different zone. Partial alignment only."
        )
    else:
        conf_pct = 30
        conf_color = "#ef4444"
        conf_label = "❌ LOW CONFIDENCE"
        conf_detail = (
            "Hot sector and Master Signal are not aligned. "
            "Hold and Observe — wait for clearer data before betting."
        )

    confirm_body = (
        f'<div style="margin-bottom:8px;">'
        f'<span style="font-size:16px;font-weight:900;color:{conf_color};">'
        f'{conf_label} — {conf_pct}% Confidence</span>'
        f'</div>'
        f'<div style="background:#f3f4f6;border-radius:6px;height:8px;margin-bottom:10px;">'
        f'<div style="background:{conf_color};height:100%;width:{conf_pct}%;'
        f'border-radius:6px;"></div></div>'
        f'<div style="font-size:13px;">{conf_detail}</div>'
    )
    confirm_copy = f"DOUBLE CONFIRMATION: {conf_label} — {conf_pct}% Confidence\n{conf_detail}"

    # ---------------------------------------------------------------
    # Section 5: DE2D VETO (coldest numbers) — partial sort via heapq
    # ---------------------------------------------------------------
    all_num_hits = heapq.nsmallest(
        8,
        ((num, scores.get(num, 0)) for num in range(1, 37)),
        key=lambda x: (x[1], x[0]),
    )
    veto_nums = [num for num, _ in all_num_hits]
    veto_nums_str = ", ".join(str(x) for x in sorted(veto_nums))

    de2d_lines = []
    for num, hits in all_num_hits:
        drought = drought_counters.get(str(num), 0) if drought_counters else 0
        drought_str = f", {drought} spins dry" if drought > 0 else ""
        de2d_lines.append(
            f'<span style="display:inline-block;background:#fee2e2;border:1px solid #fca5a5;'
            f'border-radius:4px;padding:2px 7px;margin:2px;font-size:12px;font-weight:700;">'
            f'{num} <span style="font-size:10px;color:#6b7280;">({hits} hits{drought_str})</span>'
            f'</span>'
        )

    de2d_body = (
        f'<div style="margin-bottom:8px;font-size:13px;">'
        f'<b>VETO these numbers</b> — coldest/dead zone ({n} spins analysed):'
        f'</div>'
        f'<div>{"".join(de2d_lines)}</div>'
        f'<div style="margin-top:10px;font-size:12px;color:#6b7280;">'
        f'Do NOT bet on these even if they overlap with a hot sector.</div>'
    )
    de2d_copy = f"DE2D VETO — avoid these numbers: {veto_nums_str}"

    # ---------------------------------------------------------------
    # Section 6: THE $0.01 MOVE
    # ---------------------------------------------------------------
    # Pick ALL numbers (0-36) where individual sigma >= 1.0, excluding vetoed numbers
    hot_nums_clean = []
    if n >= 10:
        _p_num = 1 / 37.0
        _exp_num = n * _p_num
        _std_num = math.sqrt(n * _p_num * (36 / 37.0))
        if _std_num > 0:
            for _num in range(37):
                if _num in veto_nums:
                    continue
                _act = scores.get(_num, 0)
                if (_act - _exp_num) / _std_num >= 1.0:
                    hot_nums_clean.append(_num)

    # 5-spin coverage probability: chance at least one of the hot numbers hits in 5 spins
    _n_hot = len(hot_nums_clean)
    coverage_prob = (1 - ((37 - _n_hot) / 37) ** 5) * 100 if _n_hot > 0 else 0.0

    hot_nums_str = ", ".join(str(x) for x in hot_nums_clean) if hot_nums_clean else "—"
    hot_cost = len(hot_nums_clean) * 0.01

    move_lines = [
        f'<div style="margin-bottom:6px;"><b>1. Statistically Hot Straight-Ups (σ ≥ +1.0)</b><br>'
        f'Numbers: {hot_nums_str} · {len(hot_nums_clean)} numbers = '
        f'<b style="color:#16a34a;">${hot_cost:.2f}</b><br>'
        f'<span style="font-size:11px;color:#6b7280;">'
        f'5-spin coverage: <b>{coverage_prob:.1f}%</b> chance of hitting in 5 spins'
        f'</span></div>',
    ]
    move_copy_parts = [
        f"1. Statistically Hot Straight-Ups (σ≥+1.0): {hot_nums_str} "
        f"({len(hot_nums_clean)} numbers = ${hot_cost:.2f}) "
        f"[5-spin coverage: {coverage_prob:.1f}%]"
    ]

    total_cost = hot_cost

    if ranked:
        b = ranked[0]
        master_cost = 0.01
        # If the master bet numbers overlap with veto, warn; otherwise include
        master_nums_clean = [x for x in sorted(b["numbers"]) if x not in veto_nums]
        if master_nums_clean or b["bet_type"] in ("even_money", "dozen", "column"):
            move_lines.append(
                f'<div style="margin-bottom:6px;"><b>2. Master Signal — {b["label"]}</b><br>'
                f'1 unit = <b style="color:#16a34a;">${master_cost:.2f}</b>'
                f'</div>'
            )
            move_copy_parts.append(
                f"2. Master Signal — {b['label']}: 1 unit = ${master_cost:.2f}"
            )
            total_cost += master_cost

    move_lines.append(
        f'<div style="margin-top:10px;font-size:14px;font-weight:900;'
        f'border-top:1px solid #e5e7eb;padding-top:8px;">'
        f'Total Risk This Spin: <b style="color:#16a34a;">${total_cost:.2f}</b>'
        f' ({int(total_cost / 0.01)} units × $0.01)</div>'
    )
    move_copy_parts.append(
        f"\nTotal Risk: ${total_cost:.2f} "
        f"({int(total_cost / 0.01)} units × $0.01)"
    )

    move_body = "".join(move_lines)
    move_copy = "\n".join(move_copy_parts)

    # ---------------------------------------------------------------
    # Section 7: STRATEGIC HEATMAP
    # ---------------------------------------------------------------
    _SECTOR_SUPPORT = {
        "Voisins du Zéro": "Splits: 4/7, 12/15, 18/21, 19/22, 25/29",
        "Tiers du Cylindre": "Double Streets: 25–30, 31–36",
        "Orphelins": "Corner: 16/17/19/20",
        "Jeu 0": "Even Money: Red / Low (1–18)",
    }
    heatmap_rows = ""
    heatmap_copy_rows = []
    for sname in sector_order:
        snums = _AI_COACH_SECTOR_NUMBERS[sname]
        hits = sector_hits[sname]
        exp = sector_expected[sname]
        sig = sector_sigma[sname]
        mom = _aco_sector_momentum(sname, last_spins)
        support = _SECTOR_SUPPORT.get(sname, "—")
        # Pick top 6 hot numbers in this sector (by score, exclude veto)
        sector_top = sorted(
            [(x, scores.get(x, 0)) for x in snums if x not in veto_nums],
            key=lambda t: t[1], reverse=True
        )[:6]
        target_str = ", ".join(str(x) for x in [t[0] for t in sector_top]) or "—"
        is_hottest = sname == hottest
        row_style = "background:#fef9c3;" if is_hottest else ""
        heatmap_rows += (
            f'<tr style="{row_style}">'
            f'<td style="padding:7px 10px;border:1px solid #e5e7eb;font-weight:{"700" if is_hottest else "400"};">'
            f'{"🔥 " if is_hottest else ""}{sname}</td>'
            f'<td style="padding:7px 10px;border:1px solid #e5e7eb;">{hits} / exp {exp:.1f}</td>'
            f'<td style="padding:7px 10px;border:1px solid #e5e7eb;">{_aco_sigma_label(sig)}</td>'
            f'<td style="padding:7px 10px;border:1px solid #e5e7eb;">{target_str}</td>'
            f'<td style="padding:7px 10px;border:1px solid #e5e7eb;">{support}</td>'
            f'<td style="padding:7px 10px;border:1px solid #e5e7eb;">{mom}</td>'
            f'</tr>'
        )
        heatmap_copy_rows.append(
            f"| {sname} | {hits}/{exp:.1f} | {_aco_sigma_label(sig)} "
            f"| {target_str} | {support} | {mom} |"
        )

    heatmap_table = (
        '<div style="overflow-x:auto;">'
        '<table style="width:100%;border-collapse:collapse;font-family:\'Segoe UI\','
        'system-ui,sans-serif;font-size:12px;">'
        '<thead><tr>'
        '<th style="padding:8px 10px;border:1px solid #e5e7eb;text-align:left;">Sector</th>'
        '<th style="padding:8px 10px;border:1px solid #e5e7eb;text-align:left;">Hits / Expected</th>'
        '<th style="padding:8px 10px;border:1px solid #e5e7eb;text-align:left;">Sigma</th>'
        '<th style="padding:8px 10px;border:1px solid #e5e7eb;text-align:left;">Top Targets</th>'
        '<th style="padding:8px 10px;border:1px solid #e5e7eb;text-align:left;">Support Bets</th>'
        '<th style="padding:8px 10px;border:1px solid #e5e7eb;text-align:left;">Momentum</th>'
        '</tr></thead>'
        f'<tbody>{heatmap_rows}</tbody>'
        '</table></div>'
    )
    heatmap_copy = (
        "STRATEGIC HEATMAP\n"
        "| Sector | Hits/Expected | Sigma | Top Targets | Support Bets | Momentum |\n"
        + "\n".join(heatmap_copy_rows)
    )

    # ---------------------------------------------------------------
    # Section C: HOT SECTOR INTELLIGENCE
    # (computed after all data is ready; placed above RADAR & SIGMA)
    # ---------------------------------------------------------------
    _hot_sig = sector_sigma.get(hottest)
    _hot_hits_cnt = sector_hits.get(hottest, 0)
    _hot_exp = sector_expected.get(hottest, 0.0)

    # Actual numbers in hottest sector with hit counts
    _hot_num_list = _AI_COACH_SECTOR_NUMBERS.get(hottest, [])
    _hot_num_badges = []
    for _hn in _hot_num_list:
        _hn_badge = _aco_num_badge(_hn)
        _hn_hits = scores.get(_hn, 0)
        _hot_num_badges.append(
            f'<div style="display:inline-flex;align-items:center;gap:3px;'
            f'margin:2px;padding:2px 6px;border:1px solid #e5e7eb;border-radius:6px;">'
            f'{_hn_badge}'
            f'<span style="font-size:11px;color:#6b7280;">{_hn_hits}×</span>'
            f'</div>'
        )

    # Hottest even money / dozen / column
    _em_by_score = sorted(
        [(nm, even_money.get(nm, 0)) for nm in ["Red", "Black", "Odd", "Even", "Low", "High"]],
        key=lambda x: x[1], reverse=True,
    )
    _hot_em_name, _hot_em_score = _em_by_score[0]
    _hot_em_sigma = _aco_sigma(_hot_em_score, n, 18)

    _doz_by_score = sorted(
        [(nm, dozen_scores.get(nm, 0)) for nm in ["1st Dozen", "2nd Dozen", "3rd Dozen"]],
        key=lambda x: x[1], reverse=True,
    )
    _hot_doz_name, _hot_doz_score = _doz_by_score[0]
    _hot_doz_sigma = _aco_sigma(_hot_doz_score, n, 12)

    _col_by_score = sorted(
        [(nm, column_scores.get(nm, 0)) for nm in ["1st Column", "2nd Column", "3rd Column"]],
        key=lambda x: x[1], reverse=True,
    )
    _hot_col_name, _hot_col_score = _col_by_score[0]
    _hot_col_sigma = _aco_sigma(_hot_col_score, n, 12)

    # Quick Trends — last 10 spins (exclude zero for even-money calcs)
    _last10 = [_n for s in last_spins[-10:] if s.isdigit() and (_n := int(s)) != 0]
    _qt_n = len(_last10)
    if _qt_n > 0:
        _qt_red   = sum(1 for x in _last10 if x in _AI_COACH_RED_NUMS)
        _qt_black = _qt_n - _qt_red
        _qt_odd   = sum(1 for x in _last10 if x % 2 == 1)
        _qt_even  = _qt_n - _qt_odd
        _qt_low   = sum(1 for x in _last10 if 1 <= x <= 18)
        _qt_high  = _qt_n - _qt_low

        def _qt_dom(a, b, al, bl):
            total = a + b
            if total == 0:
                return f"{al}/{bl}: n/a"
            if a > b:
                return f"<b>{al}</b> {a/total*100:.0f}% vs {b/total*100:.0f}%"
            if b > a:
                return f"<b>{bl}</b> {b/total*100:.0f}% vs {a/total*100:.0f}%"
            return f"{al}/{bl}: 50/50"

        _qt_rb = _qt_dom(_qt_red,   _qt_black, "Red",   "Black")
        _qt_oe = _qt_dom(_qt_odd,   _qt_even,  "Odd",   "Even")
        _qt_lh = _qt_dom(_qt_low,   _qt_high,  "Low",   "High")
    else:
        _qt_rb = _qt_oe = _qt_lh = "n/a"

    # Alignment: does hottest EM/dozen/column overlap with the hot sector?
    _EM_SETS = {
        "Red":   _AI_COACH_RED_NUMS,
        "Black": _AI_COACH_BLACK_NUMS,
        "Odd":   frozenset(x for x in range(1, 37) if x % 2 == 1),
        "Even":  frozenset(x for x in range(1, 37) if x % 2 == 0),
        "Low":   frozenset(range(1, 19)),
        "High":  frozenset(range(19, 37)),
    }
    _DOZ_SETS = {
        "1st Dozen": frozenset(range(1, 13)),
        "2nd Dozen": frozenset(range(13, 25)),
        "3rd Dozen": frozenset(range(25, 37)),
    }
    _COL_SETS = {
        "1st Column": frozenset([1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34]),
        "2nd Column": frozenset([2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35]),
        "3rd Column": frozenset([3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36]),
    }
    _hot_set = _AI_COACH_SECTOR_SETS[hottest]
    _sz = len(_hot_set) or 1
    _em_aligns  = len(_hot_set & _EM_SETS.get(_hot_em_name,  frozenset())) / _sz >= 0.45
    _doz_aligns = len(_hot_set & _DOZ_SETS.get(_hot_doz_name, frozenset())) / _sz >= 0.35
    _col_aligns = len(_hot_set & _COL_SETS.get(_hot_col_name,  frozenset())) / _sz >= 0.30
    _aligns_count = sum([_em_aligns, _doz_aligns, _col_aligns])

    if _aligns_count >= 2:
        _align_icon = "🟢"
        _align_str  = "Strong multi-category alignment"
    elif _aligns_count == 1:
        _align_icon = "🟡"
        _align_str  = "Partial alignment — one supporting trend"
    else:
        _align_icon = "🔴"
        _align_str  = "Low alignment — trends diverge"

    # Analytical paragraph (plain text inside, no nested bold tags in _qt_ vars)
    _hot_str_plain = f"{hottest}: {_hot_hits_cnt} hits (exp {_hot_exp:.1f}) · {_aco_sigma_label(_hot_sig)}"
    _para = (
        f"<b>{hottest}</b> is the dominant sector this session with "
        f"<b>{_hot_hits_cnt} hits</b> (expected {_hot_exp:.1f}) and a sigma of "
        f"<b>{_aco_sigma_label(_hot_sig)}</b>. "
    )
    if _hot_sig is not None and _hot_sig >= 1.0:
        _para += (
            "This positive sigma indicates a statistically above-average frequency — "
            "the wheel shows a clear bias toward this zone. "
        )
    elif _hot_sig is not None and _hot_sig >= 0:
        _para += "The sector leads the session but is not yet statistically significant. "
    else:
        _para += "The sector is at or below expectation — monitor for pattern development. "

    if _aligns_count >= 2:
        _para += (
            f"Both the even money ({_hot_em_name}: {_hot_em_score} hits, "
            f"{_aco_sigma_label(_hot_em_sigma)}) and the {_hot_doz_name} "
            f"({_hot_doz_score} hits, {_aco_sigma_label(_hot_doz_sigma)}) "
            f"ALIGN with {hottest}, suggesting broad wheel bias toward this zone. "
        )
    elif _aligns_count == 1:
        _supporting = (
            f"{_hot_em_name}" if _em_aligns else
            (f"{_hot_doz_name}" if _doz_aligns else f"{_hot_col_name}")
        )
        _para += (
            f"The {_supporting} trend partially supports this sector; "
            "other categories diverge. "
        )
    else:
        _para += (
            f"The hottest even money ({_hot_em_name}), dozen ({_hot_doz_name}), "
            f"and column ({_hot_col_name}) do not strongly align with {hottest}. "
        )

    if _qt_n > 0:
        def _strip_tags(s):
            return re.sub(r'<[^>]+>', '', s)
        _para += (
            f"Recent 10-spin Quick Trends: "
            f"{_strip_tags(_qt_rb)}; {_strip_tags(_qt_oe)}; {_strip_tags(_qt_lh)}. "
        )

    _total_rec_cost = len(hot_nums_clean) * 0.01
    if hot_nums_clean:
        _bets_str = ", ".join(str(x) for x in hot_nums_clean)
        _para += (
            f"<b>Statistically hot numbers (σ≥+1.0, DE2D vetoes excluded): "
            f"{_bets_str}.</b> "
            f"Bet $0.01 on each ({len(hot_nums_clean)} numbers · ${_total_rec_cost:.2f} total). "
            f"5-spin coverage: <b>{coverage_prob:.1f}%</b> chance of hitting in 5 spins. "
        )
        if _em_aligns and _hot_em_score > 0:
            _para += f"Support with {_hot_em_name} for extra coverage. "
        elif _doz_aligns and _hot_doz_score > 0:
            _para += f"Support with {_hot_doz_name} as a confirming bet. "
        _para += (
            f"Total straight-up risk: <b>${_total_rec_cost:.2f}</b>. "
            f"These bets follow the wheel bias toward {hottest}. "
        )
        _why_parts = []
        if _em_aligns:
            _why_parts.append(f"even money ({_hot_em_name})")
        if _doz_aligns:
            _why_parts.append(f"dozen ({_hot_doz_name})")
        if _col_aligns:
            _why_parts.append(f"column ({_hot_col_name})")
        if _why_parts:
            _para += f"The {' and '.join(_why_parts)} trends confirm this momentum."
        else:
            _para += f"Monitor the sector momentum for further confirmation."

    # Hottest heatmap row summary
    _hot_heatmap_support = _SECTOR_SUPPORT.get(hottest, "—")
    _hot_heatmap_mom = _aco_sector_momentum(hottest, last_spins)

    # ---------------------------------------------------------------
    # Mini roulette heat-map table for Analysis & Recommendation
    # ---------------------------------------------------------------
    _RED_NUMS_SET = _AI_COACH_RED_NUMS  # frozenset of red numbers

    def _num_heat_style(num):
        """Return inline CSS background/color for a number cell based on sigma."""
        if n < 10:
            # Not enough data — use standard roulette colour
            if num == 0:
                return "background:#16a34a;color:white;"
            return ("background:#dc2626;color:white;" if num in _RED_NUMS_SET
                    else "background:#1f2937;color:white;")
        _p = 1 / 37.0
        _act = scores.get(num, 0)
        _exp = n * _p
        _std = math.sqrt(n * _p * (1 - _p))
        _sig = (_act - _exp) / _std if _std > 0 else 0.0
        if _sig >= 2.0:
            return "background:linear-gradient(135deg,#b8860b,#f59e0b);color:white;"
        if _sig >= 1.0:
            return "background:linear-gradient(135deg,#d97706,#fbbf24);color:#1f2937;"
        if _sig >= 0.3:
            return "background:#fde68a;color:#92400e;"
        if _sig <= -2.0:
            return "background:#1d4ed8;color:white;"
        if _sig <= -1.0:
            return "background:#93c5fd;color:#1e3a8a;"
        if _sig <= -0.3:
            return "background:#dbeafe;color:#1e40af;"
        # Neutral — keep standard roulette colouring for quick visual reference
        if num == 0:
            return "background:#16a34a;color:white;"
        return ("background:#dc2626;color:white;" if num in _RED_NUMS_SET
                else "background:#1f2937;color:white;")

    def _outside_heat_style(sigma):
        """Return inline CSS for an outside-bet cell based on sigma."""
        if sigma is None:
            return "background:#f3f4f6;color:#374151;"
        if sigma >= 1.5:
            return "background:linear-gradient(135deg,#d97706,#fbbf24);color:#1f2937;"
        if sigma >= 0.5:
            return "background:#fde68a;color:#92400e;"
        if sigma <= -1.5:
            return "background:#93c5fd;color:#1e3a8a;"
        if sigma <= -0.5:
            return "background:#dbeafe;color:#1e40af;"
        return "background:#f3f4f6;color:#374151;"

    _mini_cell = (
        "width:26px;height:26px;text-align:center;vertical-align:middle;"
        "font-size:11px;font-weight:700;border-radius:3px;"
        "border:1px solid rgba(0,0,0,0.12);"
    )
    _mini_out = (
        "text-align:center;vertical-align:middle;font-size:10px;"
        "font-weight:700;padding:2px 3px;border-radius:3px;"
        "border:1px solid rgba(0,0,0,0.12);height:26px;"
    )

    # European layout rows
    _row3 = [3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36]
    _row2 = [2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35]
    _row1 = [1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34]

    _veto_set = set(veto_nums)
    _hot_nums_set = set(hot_nums_clean)

    def _num_td(num):
        base_style = f'{_mini_cell}{_num_heat_style(num)}'
        if num in _veto_set:
            return (
                f'<td style="{base_style}position:relative;" title="DE2D Vetoed — do not bet">'
                f'<span style="position:absolute;inset:0;display:flex;align-items:center;'
                f'justify-content:center;font-size:12px;z-index:1;pointer-events:none;" '
                f'aria-hidden="true">❌</span>'
                f'<span style="opacity:0.25;" aria-label="vetoed number {num}">{num}</span></td>'
            )
        if num in _hot_nums_set:
            return (
                f'<td style="{base_style}outline:2px solid #d97706;outline-offset:-2px;" '
                f'title="Hot — recommended bet">{num}</td>'
            )
        return f'<td style="{base_style}">{num}</td>'

    # Column sigmas
    _cs3 = _aco_sigma(column_scores.get("3rd Column", 0), n, 12)
    _cs2 = _aco_sigma(column_scores.get("2nd Column", 0), n, 12)
    _cs1 = _aco_sigma(column_scores.get("1st Column", 0), n, 12)
    # Dozen sigmas
    _ds1 = _aco_sigma(dozen_scores.get("1st Dozen", 0), n, 12)
    _ds2 = _aco_sigma(dozen_scores.get("2nd Dozen", 0), n, 12)
    _ds3 = _aco_sigma(dozen_scores.get("3rd Dozen", 0), n, 12)
    # Even money sigmas
    _es_low  = _aco_sigma(even_money.get("Low",   0), n, 18)
    _es_even = _aco_sigma(even_money.get("Even",  0), n, 18)
    _es_red  = _aco_sigma(even_money.get("Red",   0), n, 18)
    _es_blk  = _aco_sigma(even_money.get("Black", 0), n, 18)
    _es_odd  = _aco_sigma(even_money.get("Odd",   0), n, 18)
    _es_high = _aco_sigma(even_money.get("High",  0), n, 18)

    _mini_tbl = (
        '<div style="overflow-x:auto;margin-top:10px;">'
        '<table style="border-collapse:separate;border-spacing:2px;table-layout:fixed;">'
        # Number rows
        f'<tr>'
        f'<td rowspan="3" style="{_mini_cell}background:#16a34a;color:white;'
        f'vertical-align:middle;writing-mode:vertical-rl;'
        f'transform:rotate(180deg);padding:2px;min-width:26px;">0</td>'
        + "".join(_num_td(x) for x in _row3)
        + f'<td style="{_mini_out}{_outside_heat_style(_cs3)}">C3</td>'
        f'</tr><tr>'
        + "".join(_num_td(x) for x in _row2)
        + f'<td style="{_mini_out}{_outside_heat_style(_cs2)}">C2</td>'
        f'</tr><tr>'
        + "".join(_num_td(x) for x in _row1)
        + f'<td style="{_mini_out}{_outside_heat_style(_cs1)}">C1</td>'
        # Dozens row (blank for 0 col, span 4 each, blank for column label col)
        f'</tr><tr>'
        f'<td style="background:transparent;border:none;"></td>'
        f'<td colspan="4" style="{_mini_out}{_outside_heat_style(_ds1)}">1st 12</td>'
        f'<td colspan="4" style="{_mini_out}{_outside_heat_style(_ds2)}">2nd 12</td>'
        f'<td colspan="4" style="{_mini_out}{_outside_heat_style(_ds3)}">3rd 12</td>'
        f'<td style="background:transparent;border:none;"></td>'
        # Even-money row
        f'</tr><tr>'
        f'<td style="background:transparent;border:none;"></td>'
        f'<td colspan="2" style="{_mini_out}{_outside_heat_style(_es_low)}">1-18</td>'
        f'<td colspan="2" style="{_mini_out}{_outside_heat_style(_es_even)}">Even</td>'
        f'<td colspan="2" style="{_mini_out}{_outside_heat_style(_es_red)}">Red</td>'
        f'<td colspan="2" style="{_mini_out}{_outside_heat_style(_es_blk)}">Blk</td>'
        f'<td colspan="2" style="{_mini_out}{_outside_heat_style(_es_odd)}">Odd</td>'
        f'<td colspan="2" style="{_mini_out}{_outside_heat_style(_es_high)}">19-36</td>'
        f'<td style="background:transparent;border:none;"></td>'
        f'</tr>'
        '</table>'
        '<div style="display:flex;gap:10px;margin-top:6px;flex-wrap:wrap;">'
        '<span style="font-size:10px;display:inline-flex;align-items:center;gap:3px;">'
        '<span style="display:inline-block;width:12px;height:12px;border-radius:2px;'
        'background:linear-gradient(135deg,#b8860b,#f59e0b);"></span>⭐ Very Hot (σ≥2)</span>'
        '<span style="font-size:10px;display:inline-flex;align-items:center;gap:3px;">'
        '<span style="display:inline-block;width:12px;height:12px;border-radius:2px;'
        'background:linear-gradient(135deg,#d97706,#fbbf24);"></span>🟡 Hot (σ≥1)</span>'
        '<span style="font-size:10px;display:inline-flex;align-items:center;gap:3px;">'
        '<span style="display:inline-block;width:12px;height:12px;border-radius:2px;'
        'background:#fde68a;"></span>Warm (σ≥0.3)</span>'
        '<span style="font-size:10px;display:inline-flex;align-items:center;gap:3px;">'
        '<span style="display:inline-block;width:12px;height:12px;border-radius:2px;'
        'background:#93c5fd;"></span>Cold (σ≤-1)</span>'
        '<span style="font-size:10px;display:inline-flex;align-items:center;gap:3px;">'
        '<span style="display:inline-block;width:12px;height:12px;border-radius:2px;'
        'background:#1d4ed8;"></span>Very Cold (σ≤-2)</span>'
        '<span style="font-size:10px;display:inline-flex;align-items:center;gap:3px;">'
        '<span style="display:inline-block;width:12px;height:12px;border-radius:2px;'
        'outline:2px solid #d97706;outline-offset:-2px;"></span>🟡 Bet This (σ≥+1)</span>'
        '<span style="font-size:10px;display:inline-flex;align-items:center;gap:3px;">'
        '❌ DE2D Vetoed — do not bet</span>'
        '</div>'
        '</div>'
    )

    # ---------------------------------------------------------------
    # Top 18 Numbers to Bet — sorted by sigma, excluding DE2D veto
    # ---------------------------------------------------------------
    _top18_rows = []
    if n >= 10:
        _p18 = 1 / 37.0
        _exp18 = n * _p18
        _std18 = math.sqrt(n * _p18 * (36 / 37.0))
        if _std18 > 0:
            _num_sigmas = []
            for _num18 in range(37):
                if _num18 in veto_nums:
                    continue
                _sig18 = (scores.get(_num18, 0) - _exp18) / _std18
                _num_sigmas.append((_num18, _sig18))
            _num_sigmas.sort(key=lambda x: x[1], reverse=True)
            _top18 = _num_sigmas[:18]
            for _rank18, (_num18, _sig18) in enumerate(_top18, 1):
                if _sig18 >= 2.0:
                    _tier_emoji = "🔥"
                    _tier_label = "Very Hot"
                    _cell_bg = "background:linear-gradient(135deg,#b8860b,#f59e0b);color:white;"
                elif _sig18 >= 1.0:
                    _tier_emoji = "🟠"
                    _tier_label = "Hot"
                    _cell_bg = "background:linear-gradient(135deg,#d97706,#fbbf24);color:#1f2937;"
                elif _sig18 >= 0.3:
                    _tier_emoji = "🟡"
                    _tier_label = "Warm"
                    _cell_bg = "background:#fde68a;color:#92400e;"
                else:
                    _tier_emoji = "⚪"
                    _tier_label = "Neutral"
                    _cell_bg = "background:#f3f4f6;color:#374151;"
                _sig_str = f"+{_sig18:.2f}σ" if _sig18 >= 0 else f"{_sig18:.2f}σ"
                _top18_rows.append(
                    f'<div style="display:flex;align-items:center;gap:6px;padding:4px 8px;'
                    f'border:1px solid #e5e7eb;border-radius:6px;margin-bottom:3px;">'
                    f'<span style="font-size:11px;color:#6b7280;min-width:20px;">#{_rank18}</span>'
                    f'<span style="display:inline-flex;align-items:center;justify-content:center;'
                    f'width:28px;height:28px;border-radius:4px;font-size:13px;font-weight:700;'
                    f'{_cell_bg}">{_num18}</span>'
                    f'<span style="font-size:12px;">{_tier_emoji} {_tier_label}</span>'
                    f'<span style="font-size:11px;color:#6b7280;margin-left:auto;">{_sig_str}</span>'
                    f'</div>'
                )
    _top18_cost = len(_top18_rows) * 0.01
    _top18_coverage = (1 - ((37 - len(_top18_rows)) / 37) ** 5) * 100 if _top18_rows else 0.0
    _top18_html = (
        f'<div style="margin-top:12px;border-top:1px solid #e5e7eb;padding-top:10px;">'
        f'<div style="font-size:13px;font-weight:700;color:#374151;margin-bottom:6px;">'
        f'🎯 Top {len(_top18_rows)} Numbers to Bet</div>'
        f'<div style="font-size:11px;color:#6b7280;margin-bottom:8px;">'
        f'{len(_top18_rows)} Numbers · Total risk: '
        f'<b style="color:#16a34a;">${_top18_cost:.2f}</b> at $0.01/unit'
        f' · 5-spin coverage: <b>{_top18_coverage:.1f}%</b></div>'
        + "".join(_top18_rows)
        + (
            f'<div style="margin-top:6px;font-size:11px;color:#6b7280;font-style:italic;">'
            f'Numbers sorted hottest → lowest-hot · DE2D vetoed numbers excluded</div>'
            if _top18_rows else
            f'<div style="font-size:12px;color:#6b7280;font-style:italic;">'
            f'Not enough data yet — add more spins to generate rankings.</div>'
        )
        + f'</div>'
    )

    # Build HTML for Hot Sector Intelligence section
    hsi_body = (
        # Row 1: Hottest sector headline
        f'<div style="margin-bottom:10px;">'
        f'<div style="font-size:12px;font-weight:700;color:#374151;margin-bottom:4px;">'
        f'🔥 Hottest Sector (RADAR &amp; SIGMA)</div>'
        f'<div style="padding:6px 10px;border:1px solid #e5e7eb;border-radius:6px;">'
        f'<b>{hottest}</b> · {_hot_hits_cnt} hits (exp {_hot_exp:.1f}) '
        f'· {_aco_sigma_label(_hot_sig)} · {_hot_heatmap_mom}'
        f'</div></div>'
        # Row 2: Actual numbers in hottest sector
        f'<div style="margin-bottom:10px;">'
        f'<div style="font-size:12px;font-weight:700;color:#374151;margin-bottom:4px;">'
        f'🎯 Numbers in {hottest}</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:2px;">'
        + "".join(_hot_num_badges)
        + '</div></div>'
        # Row 3: Hottest EM / dozen / column
        f'<div style="margin-bottom:10px;">'
        f'<div style="font-size:12px;font-weight:700;color:#374151;margin-bottom:4px;">'
        f'📊 Hottest Hit % Overview</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:8px;font-size:12px;">'
        f'<div style="padding:4px 8px;border:1px solid #e5e7eb;border-radius:6px;">'
        f'<b>Even Money:</b> {_hot_em_name} ({_hot_em_score} hits)'
        f' · 📉 {_aco_sigma_label(_hot_em_sigma)}</div>'
        f'<div style="padding:4px 8px;border:1px solid #e5e7eb;border-radius:6px;">'
        f'<b>Dozen:</b> {_hot_doz_name} ({_hot_doz_score} hits)'
        f' · 📉 {_aco_sigma_label(_hot_doz_sigma)}</div>'
        f'<div style="padding:4px 8px;border:1px solid #e5e7eb;border-radius:6px;">'
        f'<b>Column:</b> {_hot_col_name} ({_hot_col_score} hits)'
        f' · 📉 {_aco_sigma_label(_hot_col_sigma)}</div>'
        f'</div></div>'
        # Row 4: Quick Trends (last 10)
        f'<div style="margin-bottom:10px;">'
        f'<div style="font-size:12px;font-weight:700;color:#374151;margin-bottom:4px;">'
        f'⚡ Quick Trends (last 10 spins)</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:8px;font-size:12px;">'
        f'<span style="padding:3px 8px;border:1px solid #e5e7eb;border-radius:6px;">'
        f'R/B: {_qt_rb}</span>'
        f'<span style="padding:3px 8px;border:1px solid #e5e7eb;border-radius:6px;">'
        f'O/E: {_qt_oe}</span>'
        f'<span style="padding:3px 8px;border:1px solid #e5e7eb;border-radius:6px;">'
        f'L/H: {_qt_lh}</span>'
        f'</div></div>'
        # Row 5: $0.01 Move straight-ups
        f'<div style="margin-bottom:10px;">'
        f'<div style="font-size:12px;font-weight:700;color:#374151;margin-bottom:4px;">'
        f'💰 $0.01 Move — Statistically Hot Straight-Ups (σ≥+1.0)</div>'
        f'<div style="font-size:12px;padding:4px 8px;border:1px solid #e5e7eb;border-radius:6px;">'
        f'{", ".join(str(x) for x in hot_nums_clean) if hot_nums_clean else "—"} '
        f'({len(hot_nums_clean)} numbers · '
        f'<b style="color:#16a34a;">${_total_rec_cost:.2f} total</b> · '
        f'5-spin coverage: <b>{coverage_prob:.1f}%</b>)</div></div>'
        # Row 6: Heatmap hottest row
        f'<div style="margin-bottom:10px;">'
        f'<div style="font-size:12px;font-weight:700;color:#374151;margin-bottom:4px;">'
        f'📈 Heatmap: Hottest Row</div>'
        f'<div style="font-size:12px;padding:4px 8px;border:1px solid #e5e7eb;border-radius:6px;">'
        f'🔥 <b>{hottest}</b> · support: {_hot_heatmap_support}</div></div>'
        # Row 7: Alignment status
        f'<div style="margin-bottom:10px;">'
        f'<div style="font-size:12px;padding:4px 8px;border:1px solid #e5e7eb;border-radius:6px;">'
        f'{_align_icon} <b>Trend Alignment:</b> {_align_str}</div></div>'
        # Row 8: Analytical paragraph + mini roulette table
        f'<div style="border-top:1px solid #e5e7eb;padding-top:10px;">'
        f'<div style="font-size:14px;font-weight:700;color:#374151;margin-bottom:8px;">'
        f'📝 Analysis &amp; Recommendation</div>'
        f'<div style="font-size:14px;color:#374151;line-height:1.7;">{_para}</div>'
        f'<div style="font-size:13px;font-weight:700;color:#374151;margin-top:12px;margin-bottom:4px;">'
        f'🎰 Visual Heat Map — Inside &amp; Outside Bets</div>'
        f'<div style="font-size:11px;color:#6b7280;margin-bottom:6px;">'
        f'Gold/amber = hot (above expected) · Light blue = cold (below expected)</div>'
        + _mini_tbl
        + _top18_html
        + f'</div>'
    )
    hsi_copy = (
        f"HOT SECTOR INTELLIGENCE\n"
        f"Hottest Sector: {_hot_str_plain}\n"
        f"Sector Numbers: {', '.join(str(x) for x in _hot_num_list)}\n"
        f"Hottest EM: {_hot_em_name} ({_hot_em_score} hits) {_aco_sigma_label(_hot_em_sigma)}\n"
        f"Hottest Dozen: {_hot_doz_name} ({_hot_doz_score} hits) {_aco_sigma_label(_hot_doz_sigma)}\n"
        f"Hottest Column: {_hot_col_name} ({_hot_col_score} hits) {_aco_sigma_label(_hot_col_sigma)}\n"
        f"Quick Trends (10): {re.sub(r'<[^>]+>', '', _qt_rb)} | "
        f"{re.sub(r'<[^>]+>', '', _qt_oe)} | {re.sub(r'<[^>]+>', '', _qt_lh)}\n"
        f"$0.01 Straight-Ups (σ≥+1.0): {', '.join(str(x) for x in hot_nums_clean)} "
        f"= ${_total_rec_cost:.2f} ({len(hot_nums_clean)} numbers · 5-spin coverage: {coverage_prob:.1f}%)\n"
        f"Alignment: {_align_str}"
    )

    # ---------------------------------------------------------------
    # Assemble all sections
    # ---------------------------------------------------------------
    sections_html = "".join([
        _aco_section("🎯", "PINNED STRONG NUMBERS", pinned_strong_body, pinned_strong_copy),
        _aco_section("📡", "PINNED RANKS", pinned_ranks_body, pinned_ranks_copy),
        _aco_section("🔥", "HOT SECTOR INTELLIGENCE", hsi_body, hsi_copy),
        _aco_section("📡", "RADAR &amp; SIGMA", radar_body, radar_copy),
        _aco_section("🔥", "HOT SECTOR", hot_sector_body, hot_sector_text),
        _aco_section("🎯", "MASTER SIGNAL", master_body, master_copy),
        _aco_section("🛡️", "DOUBLE CONFIRMATION", confirm_body, confirm_copy),
        _aco_section("💀", "DE2D VETO", de2d_body, de2d_copy),
        _aco_section("💰", "THE $0.01 MOVE", move_body, move_copy),
        _aco_section("📊", "STRATEGIC HEATMAP", heatmap_table, heatmap_copy),
    ])

    result = _ai_coach_outer_html(sections_html, n, live=True)

    # Update the process-scoped cache.  When `precomputed_recommendation` was
    # supplied it is always compute_last_money_recommendation(state) for the
    # same state, so the resulting HTML is identical to what a standalone call
    # would produce.  Caching it here means the next standalone call (without
    # a precomputed recommendation) can skip the full recompute.
    _ai_coach_cache["key"] = _spin_key
    _ai_coach_cache["html"] = result
    return result


def _ai_coach_outer_html(inner_html: str, n_spins: int, live: bool) -> str:
    """Wrap the AI coach content in the standard outer container."""
    subtitle = (
        f"Live analysis · {n_spins} spins · updates with each new spin"
        if live else
        "Add spins to activate"
    )
    return f"""<style>
#ai-coach-prompt-panel details > summary::-webkit-details-marker {{display:none;}}
#ai-coach-prompt-panel details > summary::marker {{display:none;}}
#ai-coach-prompt-panel details > summary:hover {{
  box-shadow:0 0 12px rgba(99,102,241,0.25);
}}
</style>
<div id="ai-coach-prompt-panel" style="
  border:2px solid #7c3aed;border-radius:12px;padding:20px;
  font-family:'Segoe UI',system-ui,sans-serif;margin-bottom:12px;">

  <details id="ai-coach-outer-details">
    <summary style="cursor:pointer;list-style:none;display:flex;align-items:center;
      gap:10px;user-select:none;padding:4px 0 12px;">
      <span style="font-size:22px;">🤖</span>
      <div style="flex:1;">
        <div style="font-size:16px;font-weight:800;letter-spacing:1px;">
          Pulse AI Coach
        </div>
        <div style="font-size:11px;margin-top:2px;color:#6b7280;">
          {subtitle}
        </div>
      </div>
      <span style="font-size:12px;font-weight:600;color:#7c3aed;">▼ expand</span>
    </summary>

    <div style="padding-top:4px;">
      {inner_html}
    </div>
  </details>

</div>"""


