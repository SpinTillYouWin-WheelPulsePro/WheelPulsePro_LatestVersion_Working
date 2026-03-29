"""
Strategy and betting logic extracted from app.py for the WheelPulsePro roulette analysis tool.

This module contains all strategy functions that compute betting recommendations
based on spin history scores maintained in a shared state object.
Call `init(state_obj, neighbors)` before invoking any strategy function.
"""

import logging

import pandas as pd

from roulette_data import DOZENS, SIX_LINES, STREETS, CORNERS

logger = logging.getLogger("wheelPulsePro.strategies")

state = None
current_neighbors = None


def init(state_obj, neighbors):
    global state, current_neighbors
    state = state_obj
    current_neighbors = neighbors


def calculate_top_pick_movement(current_picks, previous_picks):
    """Compare current and previous top picks to identify entries, exits, and stability."""
    try:
        current_set = set(current_picks)
        previous_set = set(previous_picks)
        
        entries = sorted(list(current_set - previous_set))
        exits = sorted(list(previous_set - current_set))
        stable = sorted(list(current_set & previous_set))
        
        # Update stability counter
        if not exits and not entries and current_picks:
            state.stability_counter += 1
        else:
            state.stability_counter = 0
            
        # Generate HTML for the HUD
        stability_color = "#2ecc71" if state.stability_counter > 2 else "#f1c40f" if state.stability_counter > 0 else "#e74c3c"
        
        hud_html = f"""
        <div style="background: #1a1a1a; border: 2px solid #333; border-radius: 8px; padding: 10px; margin-bottom: 15px; font-family: 'Poppins', sans-serif;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; border-bottom: 1px solid #444; padding-bottom: 5px;">
                <span style="color: #FFD700; font-weight: bold; font-size: 14px;">📡 MOVEMENT RADAR</span>
                <span style="background: {stability_color}; color: #000; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 900;">
                    STABILITY: {state.stability_counter} SPINS
                </span>
            </div>
            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <div style="flex: 1; min-width: 100px;">
                    <div style="color: #2ecc71; font-size: 10px; font-weight: bold; text-transform: uppercase;">➕ IN</div>
                    <div style="font-size: 16px; font-weight: 800; color: #fff;">{", ".join(map(str, entries)) if entries else "--"}</div>
                </div>
                <div style="flex: 1; min-width: 100px;">
                    <div style="color: #e74c3c; font-size: 10px; font-weight: bold; text-transform: uppercase;">➖ OUT</div>
                    <div style="font-size: 16px; font-weight: 800; color: #fff; opacity: 0.6;">{", ".join(map(str, exits)) if exits else "--"}</div>
                </div>
            </div>
            {f'<div style="margin-top: 8px; font-size: 11px; color: #f1c40f; animation: flash 1s infinite;">⚠️ SWITCH DETECTED: Adjust your bets!</div>' if entries else ''}
        </div>
        <style>
            @keyframes flash {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} }}
        </style>
        """
        return hud_html
    except Exception as e:
        logger.error(f"calculate_top_pick_movement: Unexpected error: {type(e).__name__}: {e}")
        return "<div style='padding:8px;color:#ef4444;'>⚠️ Movement radar unavailable.</div>"

def calculate_trending_sections():
    """Calculate trending sections based on current scores."""
    if not any(state.scores.values()) and not any(state.even_money_scores.values()):
        return None  # Indicates no data to process

    return {
        "even_money": sorted(state.even_money_scores.items(), key=lambda x: x[1], reverse=True),
        "dozens": sorted(state.dozen_scores.items(), key=lambda x: x[1], reverse=True),
        "columns": sorted(state.column_scores.items(), key=lambda x: x[1], reverse=True),
        "streets": sorted(state.street_scores.items(), key=lambda x: x[1], reverse=True),
        "six_lines": sorted(state.six_line_scores.items(), key=lambda x: x[1], reverse=True),
        "corners": sorted(state.corner_scores.items(), key=lambda x: x[1], reverse=True),
        "splits": sorted(state.split_scores.items(), key=lambda x: x[1], reverse=True)
    }

def get_strongest_numbers_with_neighbors(num_count):
    num_count = int(num_count)
    straight_up_df = pd.DataFrame(list(state.scores.items()), columns=["Number", "Score"])
    straight_up_df = straight_up_df[straight_up_df["Score"] > 0].sort_values(by="Score", ascending=False)

    if straight_up_df.empty:
        return "No numbers have hit yet."

    num_to_take = max(1, num_count // 3)
    top_numbers = straight_up_df["Number"].head(num_to_take).tolist()

    if not top_numbers:
        return "No strong numbers available to display."

    all_numbers = set()
    for num in top_numbers:
        neighbors = current_neighbors.get(num, (None, None))
        left, right = neighbors
        all_numbers.add(num)
        if left is not None:
            all_numbers.add(left)
        if right is not None:
            all_numbers.add(right)

    sorted_numbers = sorted(list(all_numbers))
    return f"Strongest {len(sorted_numbers)} Numbers (Sorted Lowest to Highest): {', '.join(map(str, sorted_numbers))}"

def best_even_money_bets():
    recommendations = []
    sorted_even_money = sorted(state.even_money_scores.items(), key=lambda x: x[1], reverse=True)
    even_money_hits = [item for item in sorted_even_money if item[1] > 0]
    
    if not even_money_hits:
        recommendations.append("Best Even Money Bets: No hits yet.")
        return "\n".join(recommendations)

    # Collect the top 3 bets, including ties
    top_bets = []
    scores_seen = set()
    for name, score in sorted_even_money:
        if len(top_bets) < 3 or score in scores_seen:
            top_bets.append((name, score))
            scores_seen.add(score)
        else:
            break

    # Display the top 3 bets
    recommendations.append("Best Even Money Bets (Top 3):")
    for i, (name, score) in enumerate(top_bets[:3], 1):
        recommendations.append(f"{i}. {name}: {score}")

    # Check for ties among the top 3 positions
    if len(top_bets) > 1:
        # Check for ties at the 1st position
        first_score = top_bets[0][1]
        tied_first = [name for name, score in top_bets if score == first_score]
        if len(tied_first) > 1:
            recommendations.append(f"Note: Tie for 1st place among {', '.join(tied_first)} with score {first_score}")

        # Check for ties at the 2nd position
        if len(top_bets) > 1:
            second_score = top_bets[1][1]
            tied_second = [name for name, score in top_bets if score == second_score]
            if len(tied_second) > 1:
                recommendations.append(f"Note: Tie for 2nd place among {', '.join(tied_second)} with score {second_score}")

        # Check for ties at the 3rd position
        if len(top_bets) > 2:
            third_score = top_bets[2][1]
            tied_third = [name for name, score in top_bets if score == third_score]
            if len(tied_third) > 1:
                recommendations.append(f"Note: Tie for 3rd place among {', '.join(tied_third)} with score {third_score}")

    return "\n".join(recommendations)

def hot_bet_strategy():
    recommendations = []
    sorted_even_money = sorted(state.even_money_scores.items(), key=lambda x: x[1], reverse=True)
    even_money_hits = [item for item in sorted_even_money if item[1] > 0]
    if even_money_hits:
        recommendations.append("Even Money (Top 2):")
        for i, (name, score) in enumerate(even_money_hits[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")
    else:
        recommendations.append("Even Money: No hits yet.")

    sorted_dozens = sorted(state.dozen_scores.items(), key=lambda x: x[1], reverse=True)
    dozens_hits = [item for item in sorted_dozens if item[1] > 0]
    if dozens_hits:
        recommendations.append("\nDozens (Top 2):")
        for i, (name, score) in enumerate(dozens_hits[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")
    else:
        recommendations.append("\nDozens: No hits yet.")

    sorted_columns = sorted(state.column_scores.items(), key=lambda x: x[1], reverse=True)
    columns_hits = [item for item in sorted_columns if item[1] > 0]
    if columns_hits:
        recommendations.append("\nColumns (Top 2):")
        for i, (name, score) in enumerate(columns_hits[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")
    else:
        recommendations.append("\nColumns: No hits yet.")

    sorted_streets = sorted(state.street_scores.items(), key=lambda x: x[1], reverse=True)
    streets_hits = [item for item in sorted_streets if item[1] > 0]
    if streets_hits:
        recommendations.append("\nStreets (Ranked):")
        for i, (name, score) in enumerate(streets_hits, 1):
            recommendations.append(f"{i}. {name}: {score}")
    else:
        recommendations.append("\nStreets: No hits yet.")

    sorted_corners = sorted(state.corner_scores.items(), key=lambda x: x[1], reverse=True)
    corners_hits = [item for item in sorted_corners if item[1] > 0]
    if corners_hits:
        recommendations.append("\nCorners (Ranked):")
        for i, (name, score) in enumerate(corners_hits, 1):
            recommendations.append(f"{i}. {name}: {score}")
    else:
        recommendations.append("\nCorners: No hits yet.")

    sorted_six_lines = sorted(state.six_line_scores.items(), key=lambda x: x[1], reverse=True)
    six_lines_hits = [item for item in sorted_six_lines if item[1] > 0]
    if six_lines_hits:
        recommendations.append("\nDouble Streets (Ranked):")
        for i, (name, score) in enumerate(six_lines_hits, 1):
            recommendations.append(f"{i}. {name}: {score}")
    else:
        recommendations.append("\nDouble Streets: No hits yet.")

    sorted_splits = sorted(state.split_scores.items(), key=lambda x: x[1], reverse=True)
    splits_hits = [item for item in sorted_splits if item[1] > 0]
    if splits_hits:
        recommendations.append("\nSplits (Ranked):")
        for i, (name, score) in enumerate(splits_hits, 1):
            recommendations.append(f"{i}. {name}: {score}")
    else:
        recommendations.append("\nSplits: No hits yet.")

    sorted_sides = sorted(state.side_scores.items(), key=lambda x: x[1], reverse=True)
    sides_hits = [item for item in sorted_sides if item[1] > 0]
    if sides_hits:
        recommendations.append("\nSides of Zero:")
        recommendations.append(f"1. {sides_hits[0][0]}: {sides_hits[0][1]}")
    else:
        recommendations.append("\nSides of Zero: No hits yet.")

    sorted_numbers = sorted(state.scores.items(), key=lambda x: x[1], reverse=True)
    numbers_hits = [item for item in sorted_numbers if item[1] > 0]
    if numbers_hits:
        number_best = numbers_hits[0]
        left_neighbor, right_neighbor = current_neighbors[number_best[0]]
        recommendations.append(f"\nStrongest Number: {number_best[0]} (Score: {number_best[1]}) with neighbors {left_neighbor} and {right_neighbor}")
    else:
        recommendations.append("\nStrongest Number: No hits yet.")

    return "\n".join(recommendations)

# Function for Cold Bet Strategy
def cold_bet_strategy():
    recommendations = []
    sorted_even_money = sorted(state.even_money_scores.items(), key=lambda x: x[1])
    even_money_non_hits = [item for item in sorted_even_money if item[1] == 0]
    even_money_hits = [item for item in sorted_even_money if item[1] > 0]
    if even_money_non_hits:
        recommendations.append("Even Money (Not Hit):")
        recommendations.append(", ".join(item[0] for item in even_money_non_hits))
    if even_money_hits:
        recommendations.append("\nEven Money (Lowest Scores):")
        for i, (name, score) in enumerate(even_money_hits[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")

    sorted_dozens = sorted(state.dozen_scores.items(), key=lambda x: x[1])
    dozens_non_hits = [item for item in sorted_dozens if item[1] == 0]
    dozens_hits = [item for item in sorted_dozens if item[1] > 0]
    if dozens_non_hits:
        recommendations.append("\nDozens (Not Hit):")
        recommendations.append(", ".join(item[0] for item in dozens_non_hits))
    if dozens_hits:
        recommendations.append("\nDozens (Lowest Scores):")
        for i, (name, score) in enumerate(dozens_hits[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")

    sorted_columns = sorted(state.column_scores.items(), key=lambda x: x[1])
    columns_non_hits = [item for item in sorted_columns if item[1] == 0]
    columns_hits = [item for item in sorted_columns if item[1] > 0]
    if columns_non_hits:
        recommendations.append("\nColumns (Not Hit):")
        recommendations.append(", ".join(item[0] for item in columns_non_hits))
    if columns_hits:
        recommendations.append("\nColumns (Lowest Scores):")
        for i, (name, score) in enumerate(columns_hits[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")

    sorted_streets = sorted(state.street_scores.items(), key=lambda x: x[1])
    streets_non_hits = [item for item in sorted_streets if item[1] == 0]
    streets_hits = [item for item in sorted_streets if item[1] > 0]
    if streets_non_hits:
        recommendations.append("\nStreets (Not Hit):")
        recommendations.append(", ".join(item[0] for item in streets_non_hits))
    if streets_hits:
        recommendations.append("\nStreets (Lowest Scores):")
        for i, (name, score) in enumerate(streets_hits[:3], 1):
            recommendations.append(f"{i}. {name}: {score}")

    sorted_corners = sorted(state.corner_scores.items(), key=lambda x: x[1])
    corners_non_hits = [item for item in sorted_corners if item[1] == 0]
    corners_hits = [item for item in sorted_corners if item[1] > 0]
    if corners_non_hits:
        recommendations.append("\nCorners (Not Hit):")
        recommendations.append(", ".join(item[0] for item in corners_non_hits))
    if corners_hits:
        recommendations.append("\nCorners (Lowest Scores):")
        for i, (name, score) in enumerate(corners_hits[:3], 1):
            recommendations.append(f"{i}. {name}: {score}")

    sorted_six_lines = sorted(state.six_line_scores.items(), key=lambda x: x[1])
    six_lines_non_hits = [item for item in sorted_six_lines if item[1] == 0]
    six_lines_hits = [item for item in sorted_six_lines if item[1] > 0]
    if six_lines_non_hits:
        recommendations.append("\nDouble Streets (Not Hit):")
        recommendations.append(", ".join(item[0] for item in six_lines_non_hits))
    if six_lines_hits:
        recommendations.append("\nDouble Streets (Lowest Scores):")
        for i, (name, score) in enumerate(six_lines_hits[:3], 1):
            recommendations.append(f"{i}. {name}: {score}")

    sorted_splits = sorted(state.split_scores.items(), key=lambda x: x[1])
    splits_non_hits = [item for item in sorted_splits if item[1] == 0]
    splits_hits = [item for item in sorted_splits if item[1] > 0]
    if splits_non_hits:
        recommendations.append("\nSplits (Not Hit):")
        recommendations.append(", ".join(item[0] for item in splits_non_hits))
    if splits_hits:
        recommendations.append("\nSplits (Lowest Scores):")
        for i, (name, score) in enumerate(splits_hits[:3], 1):
            recommendations.append(f"{i}. {name}: {score}")

    sorted_sides = sorted(state.side_scores.items(), key=lambda x: x[1])
    sides_non_hits = [item for item in sorted_sides if item[1] == 0]
    sides_hits = [item for item in sorted_sides if item[1] > 0]
    if sides_non_hits:
        recommendations.append("\nSides of Zero (Not Hit):")
        recommendations.append(", ".join(item[0] for item in sides_non_hits))
    if sides_hits:
        recommendations.append("\nSides of Zero (Lowest Score):")
        recommendations.append(f"1. {sides_hits[0][0]}: {sides_hits[0][1]}")

    sorted_numbers = sorted(state.scores.items(), key=lambda x: x[1])
    numbers_non_hits = [item for item in sorted_numbers if item[1] == 0]
    numbers_hits = [item for item in sorted_numbers if item[1] > 0]
    if numbers_non_hits:
        recommendations.append("\nNumbers (Not Hit):")
        recommendations.append(", ".join(str(item[0]) for item in numbers_non_hits))
    if numbers_hits:
        number_worst = numbers_hits[0]
        left_neighbor, right_neighbor = current_neighbors[number_worst[0]]
        recommendations.append(f"\nColdest Number: {number_worst[0]} (Score: {number_worst[1]}) with neighbors {left_neighbor} and {right_neighbor}")

    return "\n".join(recommendations)

def best_dozens():
    recommendations = []
    sorted_dozens = sorted(state.dozen_scores.items(), key=lambda x: x[1], reverse=True)
    dozens_hits = [item for item in sorted_dozens if item[1] > 0]
    if dozens_hits:
        recommendations.append("Best Dozens (Top 2):")
        for i, (name, score) in enumerate(dozens_hits[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")
    else:
        recommendations.append("Best Dozens: No hits yet.")
    return "\n".join(recommendations)

def best_columns():
    recommendations = []
    sorted_columns = sorted(state.column_scores.items(), key=lambda x: x[1], reverse=True)
    columns_hits = [item for item in sorted_columns if item[1] > 0]
    if columns_hits:
        recommendations.append("Best Columns (Top 2):")
        for i, (name, score) in enumerate(columns_hits[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")
    else:
        recommendations.append("Best Columns: No hits yet.")
    return "\n".join(recommendations)

def fibonacci_strategy():
    recommendations = []
    sorted_dozens = sorted(state.dozen_scores.items(), key=lambda x: x[1], reverse=True)
    dozens_hits = [item for item in sorted_dozens if item[1] > 0]
    sorted_columns = sorted(state.column_scores.items(), key=lambda x: x[1], reverse=True)
    columns_hits = [item for item in sorted_columns if item[1] > 0]

    if not dozens_hits and not columns_hits:
        recommendations.append("Fibonacci Strategy: No hits in Dozens or Columns yet.")
        return "\n".join(recommendations)

    best_dozen_score = dozens_hits[0][1] if dozens_hits else 0
    best_column_score = columns_hits[0][1] if columns_hits else 0

    if best_dozen_score > best_column_score:
        # Dozens wins: show top two dozens
        recommendations.append("Best Category: Dozens")
        top_dozens = []
        scores_seen = set()
        for name, score in sorted_dozens:
            if len(top_dozens) < 2 or score in scores_seen:
                top_dozens.append((name, score))
                scores_seen.add(score)
            else:
                break
        for i, (name, score) in enumerate(top_dozens[:2], 1):
            recommendations.append(f"Best Dozen {i}: {name} (Score: {score})")
        # Check for ties among the top two
        if len(top_dozens) > 1 and top_dozens[0][1] == top_dozens[1][1]:
            tied_dozens = [name for name, score in top_dozens if score == top_dozens[0][1]]
            recommendations.append(f"Note: Tie for 1st place among {', '.join(tied_dozens)} with score {top_dozens[0][1]}")
    elif best_column_score > best_dozen_score:
        # Columns wins: show top two columns
        recommendations.append("Best Category: Columns")
        top_columns = []
        scores_seen = set()
        for name, score in sorted_columns:
            if len(top_columns) < 2 or score in scores_seen:
                top_columns.append((name, score))
                scores_seen.add(score)
            else:
                break
        for i, (name, score) in enumerate(top_columns[:2], 1):
            recommendations.append(f"Best Column {i}: {name} (Score: {score})")
        # Check for ties among the top two
        if len(top_columns) > 1 and top_columns[0][1] == top_columns[1][1]:
            tied_columns = [name for name, score in top_columns if score == top_columns[0][1]]
            recommendations.append(f"Note: Tie for 1st place among {', '.join(tied_columns)} with score {top_columns[0][1]}")
    else:
        # Tie between Dozens and Columns: show both top options
        recommendations.append(f"Best Category (Tied): Dozens and Columns (Score: {best_dozen_score})")
        if dozens_hits:
            top_dozens = []
            scores_seen = set()
            for name, score in sorted_dozens:
                if len(top_dozens) < 2 or score in scores_seen:
                    top_dozens.append((name, score))
                    scores_seen.add(score)
                else:
                    break
            for i, (name, score) in enumerate(top_dozens[:2], 1):
                recommendations.append(f"Best Dozen {i}: {name} (Score: {score})")
            if len(top_dozens) > 1 and top_dozens[0][1] == top_dozens[1][1]:
                tied_dozens = [name for name, score in top_dozens if score == top_dozens[0][1]]
                recommendations.append(f"Note: Tie for 1st place among {', '.join(tied_dozens)} with score {top_dozens[0][1]}")
        if columns_hits:
            top_columns = []
            scores_seen = set()
            for name, score in sorted_columns:
                if len(top_columns) < 2 or score in scores_seen:
                    top_columns.append((name, score))
                    scores_seen.add(score)
                else:
                    break
            for i, (name, score) in enumerate(top_columns[:2], 1):
                recommendations.append(f"Best Column {i}: {name} (Score: {score})")
            if len(top_columns) > 1 and top_columns[0][1] == top_columns[1][1]:
                tied_columns = [name for name, score in top_columns if score == top_columns[0][1]]
                recommendations.append(f"Note: Tie for 1st place among {', '.join(tied_columns)} with score {top_columns[0][1]}")

    return "\n".join(recommendations)

def best_streets():
    recommendations = []
    sorted_streets = sorted(state.street_scores.items(), key=lambda x: x[1], reverse=True)
    streets_hits = [item for item in sorted_streets if item[1] > 0]

    if not streets_hits:
        recommendations.append("Best Streets: No hits yet.")
        return "\n".join(recommendations)

    recommendations.append("Top 3 Streets:")
    for i, (name, score) in enumerate(streets_hits[:3], 1):
        recommendations.append(f"{i}. {name}: {score}")

    recommendations.append("\nTop 6 Streets:")
    for i, (name, score) in enumerate(streets_hits[:6], 1):
        recommendations.append(f"{i}. {name}: {score}")

    return "\n".join(recommendations)

def sniper_best_street_corner():
    """Sniper Recommendations: Top street (11:1) + Top corner (8:1) for the no-trigger S65+C19 strategy."""
    recommendations = []
    sorted_streets = sorted(state.street_scores.items(), key=lambda x: x[1], reverse=True)
    sorted_corners = sorted(state.corner_scores.items(), key=lambda x: x[1], reverse=True)
    streets_hits = [item for item in sorted_streets if item[1] > 0]
    corners_hits = [item for item in sorted_corners if item[1] > 0]

    if not streets_hits and not corners_hits:
        recommendations.append("Sniper: No hits yet.")
        return "\n".join(recommendations)

    recommendations.append("🎯 SNIPER S65+C19 — Follow the Hottest")
    recommendations.append("")
    recommendations.append("BEST STREET (Phases 1-65, 11:1):")
    for i, (name, score) in enumerate(streets_hits[:3], 1):
        nums = sorted(STREETS[name])
        prefix = "→ " if i == 1 else "  "
        recommendations.append(f"{prefix}{i}. {name} [{', '.join(str(n) for n in nums)}]: {score} hits")

    recommendations.append("")
    recommendations.append("BEST CORNER (Phases 66-84, 8:1):")
    for i, (name, score) in enumerate(corners_hits[:3], 1):
        prefix = "→ " if i == 1 else "  "
        recommendations.append(f"{prefix}{i}. {name}: {score} hits")

    return "\n".join(recommendations)

def best_double_streets():
    recommendations = []
    sorted_six_lines = sorted(state.six_line_scores.items(), key=lambda x: x[1], reverse=True)
    six_lines_hits = [item for item in sorted_six_lines if item[1] > 0]

    if not six_lines_hits:
        recommendations.append("Best Double Streets: No hits yet.")
        return "\n".join(recommendations)

    recommendations.append("Double Streets (Ranked):")
    for i, (name, score) in enumerate(six_lines_hits, 1):
        recommendations.append(f"{i}. {name}: {score}")

    return "\n".join(recommendations)

def best_corners():
    recommendations = []
    sorted_corners = sorted(state.corner_scores.items(), key=lambda x: x[1], reverse=True)
    corners_hits = [item for item in sorted_corners if item[1] > 0]

    if not corners_hits:
        recommendations.append("Best Corners: No hits yet.")
        return "\n".join(recommendations)

    recommendations.append("Corners (Ranked):")
    for i, (name, score) in enumerate(corners_hits, 1):
        recommendations.append(f"{i}. {name}: {score}")

    return "\n".join(recommendations)

def best_splits():
    recommendations = []
    sorted_splits = sorted(state.split_scores.items(), key=lambda x: x[1], reverse=True)
    splits_hits = [item for item in sorted_splits if item[1] > 0]

    if not splits_hits:
        recommendations.append("Best Splits: No hits yet.")
        return "\n".join(recommendations)

    recommendations.append("Splits (Ranked):")
    for i, (name, score) in enumerate(splits_hits, 1):
        recommendations.append(f"{i}. {name}: {score}")

    return "\n".join(recommendations)

def best_dozens_and_streets():
    recommendations = []
    sorted_dozens = sorted(state.dozen_scores.items(), key=lambda x: x[1], reverse=True)
    dozens_hits = [item for item in sorted_dozens if item[1] > 0]
    if dozens_hits:
        recommendations.append("Best Dozens (Top 2):")
        for i, (name, score) in enumerate(dozens_hits[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")
    else:
        recommendations.append("Best Dozens: No hits yet.")

    sorted_streets = sorted(state.street_scores.items(), key=lambda x: x[1], reverse=True)
    streets_hits = [item for item in sorted_streets if item[1] > 0]
    if streets_hits:
        recommendations.append("\nTop 3 Streets (Yellow):")
        for i, (name, score) in enumerate(streets_hits[:3], 1):
            recommendations.append(f"{i}. {name}: {score}")
        recommendations.append("\nMiddle 3 Streets (Cyan):")
        for i, (name, score) in enumerate(streets_hits[3:6], 1):
            recommendations.append(f"{i}. {name}: {score}")
        recommendations.append("\nBottom 3 Streets (Green):")
        for i, (name, score) in enumerate(streets_hits[6:9], 1):
            recommendations.append(f"{i}. {name}: {score}")
    else:
        recommendations.append("\nBest Streets: No hits yet.")

    return "\n".join(recommendations)

def best_columns_and_streets():
    recommendations = []
    sorted_columns = sorted(state.column_scores.items(), key=lambda x: x[1], reverse=True)
    columns_hits = [item for item in sorted_columns if item[1] > 0]
    if columns_hits:
        recommendations.append("Best Columns (Top 2):")
        for i, (name, score) in enumerate(columns_hits[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")
    else:
        recommendations.append("Best Columns: No hits yet.")

    sorted_streets = sorted(state.street_scores.items(), key=lambda x: x[1], reverse=True)
    streets_hits = [item for item in sorted_streets if item[1] > 0]
    if streets_hits:
        recommendations.append("\nTop 3 Streets (Yellow):")
        for i, (name, score) in enumerate(streets_hits[:3], 1):
            recommendations.append(f"{i}. {name}: {score}")
        recommendations.append("\nMiddle 3 Streets (Cyan):")
        for i, (name, score) in enumerate(streets_hits[3:6], 1):
            recommendations.append(f"{i}. {name}: {score}")
        recommendations.append("\nBottom 3 Streets (Green):")
        for i, (name, score) in enumerate(streets_hits[6:9], 1):
            recommendations.append(f"{i}. {name}: {score}")
    else:
        recommendations.append("\nBest Streets: No hits yet.")

    return "\n".join(recommendations)

def non_overlapping_double_street_strategy():
    non_overlapping_sets = [
        ["1ST D.STREET – 1, 4", "3RD D.STREET – 7, 10", "5TH D.STREET – 13, 16", "7TH D.STREET – 19, 22", "9TH D.STREET – 25, 28"],
        ["2ND D.STREET – 4, 7", "4TH D.STREET – 10, 13", "6TH D.STREET – 16, 19", "8TH D.STREET – 22, 25", "10TH D.STREET – 28, 31"]
    ]

    set_scores = []
    for idx, non_overlapping_set in enumerate(non_overlapping_sets):
        total_score = sum(state.six_line_scores[name] for name in non_overlapping_set)
        set_scores.append((idx, total_score, non_overlapping_set))

    best_set = max(set_scores, key=lambda x: x[1])
    best_set_idx, best_set_score, best_set_streets = best_set

    sorted_streets = sorted(best_set_streets, key=lambda name: state.six_line_scores[name], reverse=True)

    recommendations = []
    recommendations.append(f"Non-Overlapping Double Streets Strategy (Set {best_set_idx + 1} with Total Score: {best_set_score})")
    recommendations.append("Hottest Non-Overlapping Double Streets (Sorted by Hotness):")
    for i, name in enumerate(sorted_streets, 1):
        score = state.six_line_scores[name]
        recommendations.append(f"{i}. {name}: {score}")

    return "\n".join(recommendations)

def non_overlapping_corner_strategy():
    non_overlapping_sets = [
        ["1ST CORNER – 1, 2, 4, 5", "5TH CORNER – 7, 8, 10, 11", "9TH CORNER – 13, 14, 16, 17", "13TH CORNER – 19, 20, 22, 23", "17TH CORNER – 25, 26, 28, 29", "21ST CORNER – 31, 32, 34, 35"],
        ["2ND CORNER – 2, 3, 5, 6", "6TH CORNER – 8, 9, 11, 12", "10TH CORNER – 14, 15, 17, 18", "14TH CORNER – 20, 21, 23, 24", "18TH CORNER – 26, 27, 29, 30", "22ND CORNER – 32, 33, 35, 36"]
    ]

    set_scores = []
    for idx, non_overlapping_set in enumerate(non_overlapping_sets):
        total_score = sum(state.corner_scores[name] for name in non_overlapping_set)
        set_scores.append((idx, total_score, non_overlapping_set))

    best_set = max(set_scores, key=lambda x: x[1])
    best_set_idx, best_set_score, best_set_corners = best_set

    sorted_corners = sorted(best_set_corners, key=lambda name: state.corner_scores[name], reverse=True)

    recommendations = []
    recommendations.append(f"Non-Overlapping Corner Strategy (Set {best_set_idx + 1} with Total Score: {best_set_score})")
    recommendations.append("Hottest Non-Overlapping Corners (Sorted by Hotness):")
    for i, name in enumerate(sorted_corners, 1):
        score = state.corner_scores[name]
        recommendations.append(f"{i}. {name}: {score}")

    return "\n".join(recommendations)

def romanowksy_missing_dozen_strategy():
    recommendations = []
    sorted_dozens = sorted(state.dozen_scores.items(), key=lambda x: x[1], reverse=True)
    dozens_hits = [item for item in sorted_dozens if item[1] > 0]
    dozens_no_hits = [item for item in sorted_dozens if item[1] == 0]

    if not dozens_hits and not dozens_no_hits:
        recommendations.append("Romanowksy Missing Dozen Strategy: No spins recorded yet.")
        return "\n".join(recommendations)

    if len(dozens_hits) < 2:
        recommendations.append("Romanowksy Missing Dozen Strategy: Not enough dozens have hit yet.")
        if dozens_hits:
            recommendations.append(f"Hottest Dozen: {dozens_hits[0][0]} (Score: {dozens_hits[0][1]})")
        return "\n".join(recommendations)

    top_dozens = []
    scores_seen = set()
    for name, score in sorted_dozens:
        if len(top_dozens) < 2 or score in scores_seen:
            top_dozens.append((name, score))
            scores_seen.add(score)
        else:
            break

    recommendations.append("Hottest Dozens (Top 2):")
    for i, (name, score) in enumerate(top_dozens[:2], 1):
        recommendations.append(f"{i}. {name}: {score}")
    if len(top_dozens) > 2 and top_dozens[1][1] == top_dozens[2][1]:
        tied_dozens = [name for name, score in top_dozens if score == top_dozens[1][1]]
        recommendations.append(f"Note: Tie detected among {', '.join(tied_dozens)} with score {top_dozens[1][1]}")

    weakest_dozen = sorted_dozens[-1]
    weakest_dozen_name, weakest_dozen_score = weakest_dozen
    recommendations.append(f"\nWeakest Dozen: {weakest_dozen_name} (Score: {weakest_dozen_score})")

    weakest_dozen_numbers = set(DOZENS[weakest_dozen_name])
    straight_up_df = pd.DataFrame(list(state.scores.items()), columns=["Number", "Score"])
    straight_up_df = straight_up_df[straight_up_df["Score"] > 0].sort_values(by="Score", ascending=False)

    if straight_up_df.empty:
        recommendations.append("No strong numbers have hit yet in any dozen.")
        return "\n".join(recommendations)

    strong_numbers_in_weakest = []
    neighbors_in_weakest = []
    for _, row in straight_up_df.iterrows():
        number = row["Number"]
        score = row["Score"]
        if number in weakest_dozen_numbers:
            strong_numbers_in_weakest.append((number, score))
        else:
            if number in current_neighbors:
                left, right = current_neighbors[number]
                if left in weakest_dozen_numbers:
                    neighbors_in_weakest.append((left, number, score))
                if right in weakest_dozen_numbers:
                    neighbors_in_weakest.append((right, number, score))

    if strong_numbers_in_weakest:
        recommendations.append("\nStrongest Numbers in Weakest Dozen:")
        for number, score in strong_numbers_in_weakest:
            recommendations.append(f"Number {number} (Score: {score})")
    else:
        recommendations.append("\nNo strong numbers directly in the Weakest Dozen.")

    if neighbors_in_weakest:
        recommendations.append("\nNeighbors of Strong Numbers in Weakest Dozen:")
        for neighbor, strong_number, score in neighbors_in_weakest:
            recommendations.append(f"Number {neighbor} (Neighbor of {strong_number}, Score: {score})")
    else:
        if not strong_numbers_in_weakest:
            recommendations.append("No neighbors of strong numbers in the Weakest Dozen.")

    return "\n".join(recommendations)

def fibonacci_to_fortune_strategy():
    recommendations = []

    # Debug: Print scores to verify state
    logger.debug(f"fibonacci_to_fortune_strategy: Dozen scores = {dict(state.dozen_scores)}")
    logger.debug(f"fibonacci_to_fortune_strategy: Column scores = {dict(state.column_scores)}")
    logger.debug(f"fibonacci_to_fortune_strategy: Even money scores = {dict(state.even_money_scores)}")

    # Part 1: Fibonacci Strategy (Best Category: Dozens or Columns)
    sorted_dozens = sorted(state.dozen_scores.items(), key=lambda x: x[1], reverse=True)
    dozens_hits = [item for item in sorted_dozens if item[1] > 0]
    sorted_columns = sorted(state.column_scores.items(), key=lambda x: x[1], reverse=True)
    columns_hits = [item for item in sorted_columns if item[1] > 0]

    best_dozen_score = dozens_hits[0][1] if dozens_hits else 0
    best_column_score = columns_hits[0][1] if columns_hits else 0

    recommendations.append("Fibonacci Strategy:")
    if not dozens_hits and not columns_hits:
        recommendations.append("No hits in Dozens or Columns yet.")
    elif best_dozen_score > best_column_score:
        recommendations.append(f"Best Category: Dozens (Score: {best_dozen_score})")
        recommendations.append(f"Best Dozen: {dozens_hits[0][0]}")
    elif best_column_score > best_dozen_score:
        recommendations.append(f"Best Category: Columns (Score: {best_column_score})")
        recommendations.append(f"Best Column: {columns_hits[0][0]}")
    else:
        recommendations.append(f"Best Category (Tied): Dozens and Columns (Score: {best_dozen_score})")
        if dozens_hits:
            recommendations.append(f"Best Dozen: {dozens_hits[0][0]}")
        if columns_hits:
            recommendations.append(f"Best Column: {columns_hits[0][0]}")

    # Part 2: Dozens (Top 2)
    recommendations.append("\nDozens (Top 2):")
    logger.debug(f"fibonacci_to_fortune_strategy: Sorted dozens = {sorted_dozens}")
    if len(sorted_dozens) >= 2:
        for i, (name, score) in enumerate(sorted_dozens[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")
    elif sorted_dozens:
        name, score = sorted_dozens[0]
        recommendations.append(f"1. {name}: {score}")
        recommendations.append("2. No other dozens available.")
    else:
        recommendations.append("No hits yet.")

    # Part 3: Columns (Top 2)
    recommendations.append("\nColumns (Top 2):")
    logger.debug(f"fibonacci_to_fortune_strategy: Sorted columns = {sorted_columns}")
    if len(sorted_columns) >= 2:
        for i, (name, score) in enumerate(sorted_columns[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")
    elif sorted_columns:
        name, score = sorted_columns[0]
        recommendations.append(f"1. {name}: {score}")
        recommendations.append("2. No other columns available.")
    else:
        recommendations.append("No hits yet.")

    # Part 4: Best Even Money Bet
    sorted_even_money = sorted(state.even_money_scores.items(), key=lambda x: x[1], reverse=True)
    logger.debug(f"fibonacci_to_fortune_strategy: Sorted even money = {sorted_even_money}")
    even_money_hits = [item for item in sorted_even_money if item[1] > 0]
    recommendations.append("\nEven Money (Top 1):")
    if even_money_hits:
        best_even_money = even_money_hits[0]
        name, score = best_even_money
        recommendations.append(f"1. {name}: {score}")
    else:
        recommendations.append("No hits yet.")

    # Part 5: Best Double Street in Weakest Dozen (Excluding Top Two Dozens)
    weakest_dozen = min(state.dozen_scores.items(), key=lambda x: x[1], default=("1st Dozen", 0))
    weakest_dozen_name, weakest_dozen_score = weakest_dozen
    weakest_dozen_numbers = set(DOZENS[weakest_dozen_name])

    top_two_dozens = [item[0] for item in sorted_dozens[:2]]
    top_two_dozen_numbers = set()
    for dozen_name in top_two_dozens:
        top_two_dozen_numbers.update(DOZENS[dozen_name])

    double_streets_in_weakest = []
    for name, numbers in SIX_LINES.items():
        numbers_set = set(numbers)
        if numbers_set.issubset(weakest_dozen_numbers) and not numbers_set.intersection(top_two_dozen_numbers):
            score = state.six_line_scores.get(name, 0)
            double_streets_in_weakest.append((name, score))

    logger.debug(f"fibonacci_to_fortune_strategy: Double streets in weakest dozen ({weakest_dozen_name}) = {double_streets_in_weakest}")
    recommendations.append(f"\nDouble Streets (Top 1 in Weakest Dozen: {weakest_dozen_name}, Score: {weakest_dozen_score}):")
    if double_streets_in_weakest:
        double_streets_sorted = sorted(double_streets_in_weakest, key=lambda x: x[1], reverse=True)
        best_double_street = double_streets_sorted[0]
        name, score = best_double_street
        numbers = ', '.join(map(str, sorted(SIX_LINES[name])))
        recommendations.append(f"1. {name} (Numbers: {numbers}, Score: {score})")
    else:
        recommendations.append("No suitable double street available (all overlap with top two dozens or no hits).")

    return "\n".join(recommendations)
    
def three_eight_six_rising_martingale():
    recommendations = []
    sorted_streets = sorted(state.street_scores.items(), key=lambda x: x[1], reverse=True)
    streets_hits = [item for item in sorted_streets if item[1] > 0]

    if not streets_hits:
        recommendations.append("3-8-6 Rising Martingale: No streets have hit yet.")
        return "\n".join(recommendations)

    recommendations.append("Top 3 Streets (Yellow):")
    for i, (name, score) in enumerate(streets_hits[:3], 1):
        recommendations.append(f"{i}. {name}: {score}")

    recommendations.append("\nMiddle 3 Streets (Cyan):")
    for i, (name, score) in enumerate(streets_hits[3:6], 1):
        recommendations.append(f"{i}. {name}: {score}")

    recommendations.append("\nBottom 2 Streets (Green):")
    for i, (name, score) in enumerate(streets_hits[6:8], 1):
        recommendations.append(f"{i}. {name}: {score}")

    return "\n".join(recommendations)

def one_dozen_one_column_strategy():
    recommendations = []
    sorted_dozens = sorted(state.dozen_scores.items(), key=lambda x: x[1], reverse=True)
    dozens_hits = [item for item in sorted_dozens if item[1] > 0]

    if not dozens_hits:
        recommendations.append("Best Dozen: No dozens have hit yet.")
    else:
        top_score = dozens_hits[0][1]
        top_dozens = [item for item in sorted_dozens if item[1] == top_score]
        if len(top_dozens) == 1:
            recommendations.append(f"Best Dozen: {top_dozens[0][0]}")
        else:
            recommendations.append("Best Dozens (Tied):")
            for name, _ in top_dozens:
                recommendations.append(f"- {name}")

    sorted_columns = sorted(state.column_scores.items(), key=lambda x: x[1], reverse=True)
    columns_hits = [item for item in sorted_columns if item[1] > 0]

    if not columns_hits:
        recommendations.append("Best Column: No columns have hit yet.")
    else:
        top_score = columns_hits[0][1]
        top_columns = [item for item in sorted_columns if item[1] == top_score]
        if len(top_columns) == 1:
            recommendations.append(f"Best Column: {top_columns[0][0]}")
        else:
            recommendations.append("Best Columns (Tied):")
            for name, _ in top_columns:
                recommendations.append(f"- {name}")

    return "\n".join(recommendations)

def top_pick_18_numbers_without_neighbours(strong_numbers_count=18):
    """Generate dynamic text list for the top N strong numbers based on slider input."""
    recommendations = []
    count = max(1, min(int(strong_numbers_count), 34))
    
    straight_up_df = pd.DataFrame(list(state.scores.items()), columns=["Number", "Score"])
    straight_up_df = straight_up_df[straight_up_df["Score"] > 0].sort_values(by="Score", ascending=False)

    if straight_up_df.empty:
        return f"Top Pick Strong Numbers: No numbers have hit yet."

    top_numbers_df = straight_up_df.head(count)
    top_numbers_list = top_numbers_df["Number"].tolist()

    # Dynamic Tiering for the Text Output
    tier_size = count // 3
    remainder = count % 3
    size1 = tier_size + remainder
    size2 = tier_size

    recommendations.append(f"Top Pick {count} Strong Numbers (Based on Slider):")
    
    sections = [
        ("Top Tier (Yellow)", top_numbers_list[:size1]),
        ("Middle Tier (Blue)", top_numbers_list[size1:size1+size2]),
        ("Lower Tier (Green)", top_numbers_list[size1+size2:])
    ]

    for title, nums in sections:
        if nums:
            recommendations.append(f"\n{title}:")
            for i, num in enumerate(nums, 1):
                score = top_numbers_df[top_numbers_df["Number"] == num]["Score"].iloc[0]
                recommendations.append(f"{i}. Number {num} (Score: {score})")

    return "\n".join(recommendations)

def best_column_till_tie_break():
    recommendations = []
    sorted_columns = sorted(state.column_scores.items(), key=lambda x: x[1], reverse=True)
    
    if not sorted_columns or sorted_columns[0][1] == 0:
        return "No hits yet."
        
    top_bet = sorted_columns[0]
    second_bet = sorted_columns[1]
    
    if top_bet[1] == second_bet[1]:
        tied = [name for name, score in sorted_columns if score == top_bet[1]]
        recommendations.append(f"⚠️ TIE BREAK IN PROGRESS: {', '.join(tied)} ({top_bet[1]} hits)")
        recommendations.append("Waiting for a clear single winner...")
    else:
        recommendations.append(f"✅ CLEAR WINNER: {top_bet[0]} ({top_bet[1]} hits)")
        
    return "\n".join(recommendations)

def best_dozen_till_tie_break():
    recommendations = []
    sorted_dozens = sorted(state.dozen_scores.items(), key=lambda x: x[1], reverse=True)
    
    if not sorted_dozens or sorted_dozens[0][1] == 0:
        return "No hits yet."
        
    top_bet = sorted_dozens[0]
    second_bet = sorted_dozens[1]
    
    if top_bet[1] == second_bet[1]:
        tied = [name for name, score in sorted_dozens if score == top_bet[1]]
        recommendations.append(f"⚠️ TIE BREAK IN PROGRESS: {', '.join(tied)} ({top_bet[1]} hits)")
        recommendations.append("Waiting for a clear single winner...")
    else:
        recommendations.append(f"✅ CLEAR WINNER: {top_bet[0]} ({top_bet[1]} hits)")
        
    return "\n".join(recommendations)

def best_even_money_bet_till_tie_break():
    recommendations = []
    sorted_even_money = sorted(state.even_money_scores.items(), key=lambda x: x[1], reverse=True)
    
    # Check if we have data
    if not sorted_even_money or sorted_even_money[0][1] == 0:
        return "No hits yet."
        
    top_bet = sorted_even_money[0]
    second_bet = sorted_even_money[1]
    
    # Check for tie
    if top_bet[1] == second_bet[1]:
        # Find all tied
        tied = [name for name, score in sorted_even_money if score == top_bet[1]]
        recommendations.append(f"⚠️ TIE BREAK IN PROGRESS: {', '.join(tied)} ({top_bet[1]} hits)")
        recommendations.append("Waiting for a clear single winner...")
    else:
        # Clear winner
        recommendations.append(f"✅ CLEAR WINNER: {top_bet[0]} ({top_bet[1]} hits)")
        
    return "\n".join(recommendations)

def best_even_money_and_top_18():
    recommendations = []

    # Best Even Money Bets (Top 3 with tie handling, same as best_even_money_bets)
    sorted_even_money = sorted(state.even_money_scores.items(), key=lambda x: x[1], reverse=True)
    even_money_hits = [item for item in sorted_even_money if item[1] > 0]
    
    if even_money_hits:
        # Collect the top 3 bets, including ties
        top_bets = []
        scores_seen = set()
        for name, score in sorted_even_money:
            if len(top_bets) < 3 or score in scores_seen:
                top_bets.append((name, score))
                scores_seen.add(score)
            else:
                break

        # Display the top 3 bets
        recommendations.append("Best Even Money Bets (Top 3):")
        for i, (name, score) in enumerate(top_bets[:3], 1):
            recommendations.append(f"{i}. {name}: {score}")

        # Check for ties among the top 3 positions
        if len(top_bets) > 1:
            first_score = top_bets[0][1]
            tied_first = [name for name, score in top_bets if score == first_score]
            if len(tied_first) > 1:
                recommendations.append(f"Note: Tie for 1st place among {', '.join(tied_first)} with score {first_score}")

            if len(top_bets) > 1:
                second_score = top_bets[1][1]
                tied_second = [name for name, score in top_bets if score == second_score]
                if len(tied_second) > 1:
                    recommendations.append(f"Note: Tie for 2nd place among {', '.join(tied_second)} with score {second_score}")

            if len(top_bets) > 2:
                third_score = top_bets[2][1]
                tied_third = [name for name, score in top_bets if score == third_score]
                if len(tied_third) > 1:
                    recommendations.append(f"Note: Tie for 3rd place among {', '.join(tied_third)} with score {third_score}")
    else:
        recommendations.append("Best Even Money Bets: No hits yet.")

    # Top Pick 18 Numbers without Neighbours (same as top_pick_18_numbers_without_neighbours)
    recommendations.append("")  # Add a blank line for separation
    straight_up_df = pd.DataFrame(list(state.scores.items()), columns=["Number", "Score"])
    straight_up_df = straight_up_df[straight_up_df["Score"] > 0].sort_values(by="Score", ascending=False)

    if straight_up_df.empty or len(straight_up_df) < 18:
        recommendations.append("Top Pick 18 Numbers without Neighbours: Not enough numbers have hit yet (need at least 18).")
        return "\n".join(recommendations)

    top_18_df = straight_up_df.head(18)
    top_18_numbers = top_18_df["Number"].tolist()
    scores_dict = dict(zip(top_18_df["Number"], top_18_df["Score"]))

    top_6 = top_18_numbers[:6]
    next_6 = top_18_numbers[6:12]
    last_6 = top_18_numbers[12:18]

    recommendations.append("Top Pick 18 Numbers without Neighbours:")
    recommendations.append("\nTop 6 Numbers (Yellow):")
    for i, num in enumerate(top_6, 1):
        score = scores_dict[num]
        recommendations.append(f"{i}. Number {num} (Score: {score})")

    recommendations.append("\nNext 6 Numbers (Blue):")
    for i, num in enumerate(next_6, 1):
        score = scores_dict[num]
        recommendations.append(f"{i}. Number {num} (Score: {score})")

    recommendations.append("\nLast 6 Numbers (Green):")
    for i, num in enumerate(last_6, 1):
        score = scores_dict[num]
        recommendations.append(f"{i}. Number {num} (Score: {score})")

    return "\n".join(recommendations)

def best_dozens_and_top_18():
    recommendations = []

    # Best Dozens (Top 2 with tie handling, same as best_dozens)
    sorted_dozens = sorted(state.dozen_scores.items(), key=lambda x: x[1], reverse=True)
    dozens_hits = [item for item in sorted_dozens if item[1] > 0]
    if dozens_hits:
        # Collect the top 2 dozens, including ties
        top_dozens = []
        scores_seen = set()
        for name, score in sorted_dozens:
            if len(top_dozens) < 2 or score in scores_seen:
                top_dozens.append((name, score))
                scores_seen.add(score)
            else:
                break

        # Display the top 2 dozens
        recommendations.append("Best Dozens (Top 2):")
        for i, (name, score) in enumerate(top_dozens[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")

        # Check for ties among the top 2 positions
        if len(top_dozens) > 1:
            first_score = top_dozens[0][1]
            tied_first = [name for name, score in top_dozens if score == first_score]
            if len(tied_first) > 1:
                recommendations.append(f"Note: Tie for 1st place among {', '.join(tied_first)} with score {first_score}")

            if len(top_dozens) > 1:
                second_score = top_dozens[1][1]
                tied_second = [name for name, score in top_dozens if score == second_score]
                if len(tied_second) > 1:
                    recommendations.append(f"Note: Tie for 2nd place among {', '.join(tied_second)} with score {second_score}")
    else:
        recommendations.append("Best Dozens: No hits yet.")

    # Top Pick 18 Numbers without Neighbours (same as top_pick_18_numbers_without_neighbours)
    recommendations.append("")  # Add a blank line for separation
    straight_up_df = pd.DataFrame(list(state.scores.items()), columns=["Number", "Score"])
    straight_up_df = straight_up_df[straight_up_df["Score"] > 0].sort_values(by="Score", ascending=False)

    if straight_up_df.empty or len(straight_up_df) < 18:
        recommendations.append("Top Pick 18 Numbers without Neighbours: Not enough numbers have hit yet (need at least 18).")
        return "\n".join(recommendations)

    top_18_df = straight_up_df.head(18)
    top_18_numbers = top_18_df["Number"].tolist()
    scores_dict = dict(zip(top_18_df["Number"], top_18_df["Score"]))

    top_6 = top_18_numbers[:6]
    next_6 = top_18_numbers[6:12]
    last_6 = top_18_numbers[12:18]

    recommendations.append("Top Pick 18 Numbers without Neighbours:")
    recommendations.append("\nTop 6 Numbers (Yellow):")
    for i, num in enumerate(top_6, 1):
        score = scores_dict[num]
        recommendations.append(f"{i}. Number {num} (Score: {score})")

    recommendations.append("\nNext 6 Numbers (Blue):")
    for i, num in enumerate(next_6, 1):
        score = scores_dict[num]
        recommendations.append(f"{i}. Number {num} (Score: {score})")

    recommendations.append("\nLast 6 Numbers (Green):")
    for i, num in enumerate(last_6, 1):
        score = scores_dict[num]
        recommendations.append(f"{i}. Number {num} (Score: {score})")

    return "\n".join(recommendations)

def best_columns_and_top_18():
    recommendations = []

    # Best Columns (Top 2 with tie handling, same as best_columns)
    sorted_columns = sorted(state.column_scores.items(), key=lambda x: x[1], reverse=True)
    columns_hits = [item for item in sorted_columns if item[1] > 0]
    if columns_hits:
        # Collect the top 2 columns, including ties
        top_columns = []
        scores_seen = set()
        for name, score in sorted_columns:
            if len(top_columns) < 2 or score in scores_seen:
                top_columns.append((name, score))
                scores_seen.add(score)
            else:
                break

        # Display the top 2 columns
        recommendations.append("Best Columns (Top 2):")
        for i, (name, score) in enumerate(top_columns[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")

        # Check for ties among the top 2 positions
        if len(top_columns) > 1:
            first_score = top_columns[0][1]
            tied_first = [name for name, score in top_columns if score == first_score]
            if len(tied_first) > 1:
                recommendations.append(f"Note: Tie for 1st place among {', '.join(tied_first)} with score {first_score}")

            if len(top_columns) > 1:
                second_score = top_columns[1][1]
                tied_second = [name for name, score in top_columns if score == second_score]
                if len(tied_second) > 1:
                    recommendations.append(f"Note: Tie for 2nd place among {', '.join(tied_second)} with score {second_score}")
    else:
        recommendations.append("Best Columns: No hits yet.")

    # Top Pick 18 Numbers without Neighbours (same as top_pick_18_numbers_without_neighbours)
    recommendations.append("")  # Add a blank line for separation
    straight_up_df = pd.DataFrame(list(state.scores.items()), columns=["Number", "Score"])
    straight_up_df = straight_up_df[straight_up_df["Score"] > 0].sort_values(by="Score", ascending=False)

    if straight_up_df.empty or len(straight_up_df) < 18:
        recommendations.append("Top Pick 18 Numbers without Neighbours: Not enough numbers have hit yet (need at least 18).")
        return "\n".join(recommendations)

    top_18_df = straight_up_df.head(18)
    top_18_numbers = top_18_df["Number"].tolist()
    scores_dict = dict(zip(top_18_df["Number"], top_18_df["Score"]))

    top_6 = top_18_numbers[:6]
    next_6 = top_18_numbers[6:12]
    last_6 = top_18_numbers[12:18]

    recommendations.append("Top Pick 18 Numbers without Neighbours:")
    recommendations.append("\nTop 6 Numbers (Yellow):")
    for i, num in enumerate(top_6, 1):
        score = scores_dict[num]
        recommendations.append(f"{i}. Number {num} (Score: {score})")

    recommendations.append("\nNext 6 Numbers (Blue):")
    for i, num in enumerate(next_6, 1):
        score = scores_dict[num]
        recommendations.append(f"{i}. Number {num} (Score: {score})")

    recommendations.append("\nLast 6 Numbers (Green):")
    for i, num in enumerate(last_6, 1):
        score = scores_dict[num]
        recommendations.append(f"{i}. Number {num} (Score: {score})")

    return "\n".join(recommendations)

def best_dozens_even_money_and_top_18():
    recommendations = []

    # Best Dozens (Top 2 with tie handling, same as best_dozens)
    sorted_dozens = sorted(state.dozen_scores.items(), key=lambda x: x[1], reverse=True)
    dozens_hits = [item for item in sorted_dozens if item[1] > 0]
    if dozens_hits:
        # Collect the top 2 dozens, including ties
        top_dozens = []
        scores_seen = set()
        for name, score in sorted_dozens:
            if len(top_dozens) < 2 or score in scores_seen:
                top_dozens.append((name, score))
                scores_seen.add(score)
            else:
                break

        # Display the top 2 dozens
        recommendations.append("Best Dozens (Top 2):")
        for i, (name, score) in enumerate(top_dozens[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")

        # Check for ties among the top 2 positions
        if len(top_dozens) > 1:
            first_score = top_dozens[0][1]
            tied_first = [name for name, score in top_dozens if score == first_score]
            if len(tied_first) > 1:
                recommendations.append(f"Note: Tie for 1st place among {', '.join(tied_first)} with score {first_score}")

            if len(top_dozens) > 1:
                second_score = top_dozens[1][1]
                tied_second = [name for name, score in top_dozens if score == second_score]
                if len(tied_second) > 1:
                    recommendations.append(f"Note: Tie for 2nd place among {', '.join(tied_second)} with score {second_score}")
    else:
        recommendations.append("Best Dozens: No hits yet.")

    # Best Even Money Bets (Top 3 with tie handling, same as best_even_money_bets)
    recommendations.append("")  # Add a blank line for separation
    sorted_even_money = sorted(state.even_money_scores.items(), key=lambda x: x[1], reverse=True)
    even_money_hits = [item for item in sorted_even_money if item[1] > 0]
    
    if even_money_hits:
        # Collect the top 3 bets, including ties
        top_bets = []
        scores_seen = set()
        for name, score in sorted_even_money:
            if len(top_bets) < 3 or score in scores_seen:
                top_bets.append((name, score))
                scores_seen.add(score)
            else:
                break

        # Display the top 3 bets
        recommendations.append("Best Even Money Bets (Top 3):")
        for i, (name, score) in enumerate(top_bets[:3], 1):
            recommendations.append(f"{i}. {name}: {score}")

        # Check for ties among the top 3 positions
        if len(top_bets) > 1:
            first_score = top_bets[0][1]
            tied_first = [name for name, score in top_bets if score == first_score]
            if len(tied_first) > 1:
                recommendations.append(f"Note: Tie for 1st place among {', '.join(tied_first)} with score {first_score}")

            if len(top_bets) > 1:
                second_score = top_bets[1][1]
                tied_second = [name for name, score in top_bets if score == second_score]
                if len(tied_second) > 1:
                    recommendations.append(f"Note: Tie for 2nd place among {', '.join(tied_second)} with score {second_score}")

            if len(top_bets) > 2:
                third_score = top_bets[2][1]
                tied_third = [name for name, score in top_bets if score == third_score]
                if len(tied_third) > 1:
                    recommendations.append(f"Note: Tie for 3rd place among {', '.join(tied_third)} with score {third_score}")
    else:
        recommendations.append("Best Even Money Bets: No hits yet.")

    # Top Pick 18 Numbers without Neighbours (same as top_pick_18_numbers_without_neighbours)
    recommendations.append("")  # Add a blank line for separation
    straight_up_df = pd.DataFrame(list(state.scores.items()), columns=["Number", "Score"])
    straight_up_df = straight_up_df[straight_up_df["Score"] > 0].sort_values(by="Score", ascending=False)

    if straight_up_df.empty or len(straight_up_df) < 18:
        recommendations.append("Top Pick 18 Numbers without Neighbours: Not enough numbers have hit yet (need at least 18).")
        return "\n".join(recommendations)

    top_18_df = straight_up_df.head(18)
    top_18_numbers = top_18_df["Number"].tolist()
    scores_dict = dict(zip(top_18_df["Number"], top_18_df["Score"]))

    top_6 = top_18_numbers[:6]
    next_6 = top_18_numbers[6:12]
    last_6 = top_18_numbers[12:18]

    recommendations.append("Top Pick 18 Numbers without Neighbours:")
    recommendations.append("\nTop 6 Numbers (Yellow):")
    for i, num in enumerate(top_6, 1):
        score = scores_dict[num]
        recommendations.append(f"{i}. Number {num} (Score: {score})")

    recommendations.append("\nNext 6 Numbers (Blue):")
    for i, num in enumerate(next_6, 1):
        score = scores_dict[num]
        recommendations.append(f"{i}. Number {num} (Score: {score})")

    recommendations.append("\nLast 6 Numbers (Green):")
    for i, num in enumerate(last_6, 1):
        score = scores_dict[num]
        recommendations.append(f"{i}. Number {num} (Score: {score})")

    return "\n".join(recommendations)

def best_columns_even_money_and_top_18():
    recommendations = []

    # Best Columns (Top 2 with tie handling, same as best_columns)
    sorted_columns = sorted(state.column_scores.items(), key=lambda x: x[1], reverse=True)
    columns_hits = [item for item in sorted_columns if item[1] > 0]
    if columns_hits:
        # Collect the top 2 columns, including ties
        top_columns = []
        scores_seen = set()
        for name, score in sorted_columns:
            if len(top_columns) < 2 or score in scores_seen:
                top_columns.append((name, score))
                scores_seen.add(score)
            else:
                break

        # Display the top 2 columns
        recommendations.append("Best Columns (Top 2):")
        for i, (name, score) in enumerate(top_columns[:2], 1):
            recommendations.append(f"{i}. {name}: {score}")

        # Check for ties among the top 2 positions
        if len(top_columns) > 1:
            first_score = top_columns[0][1]
            tied_first = [name for name, score in top_columns if score == first_score]
            if len(tied_first) > 1:
                recommendations.append(f"Note: Tie for 1st place among {', '.join(tied_first)} with score {first_score}")

            if len(top_columns) > 1:
                second_score = top_columns[1][1]
                tied_second = [name for name, score in top_columns if score == second_score]
                if len(tied_second) > 1:
                    recommendations.append(f"Note: Tie for 2nd place among {', '.join(tied_second)} with score {second_score}")
    else:
        recommendations.append("Best Columns: No hits yet.")

    # Best Even Money Bets (Top 3 with tie handling, same as best_even_money_bets)
    recommendations.append("")  # Add a blank line for separation
    sorted_even_money = sorted(state.even_money_scores.items(), key=lambda x: x[1], reverse=True)
    even_money_hits = [item for item in sorted_even_money if item[1] > 0]
    
    if even_money_hits:
        # Collect the top 3 bets, including ties
        top_bets = []
        scores_seen = set()
        for name, score in sorted_even_money:
            if len(top_bets) < 3 or score in scores_seen:
                top_bets.append((name, score))
                scores_seen.add(score)
            else:
                break

        # Display the top 3 bets
        recommendations.append("Best Even Money Bets (Top 3):")
        for i, (name, score) in enumerate(top_bets[:3], 1):
            recommendations.append(f"{i}. {name}: {score}")

        # Check for ties among the top 3 positions
        if len(top_bets) > 1:
            first_score = top_bets[0][1]
            tied_first = [name for name, score in top_bets if score == first_score]
            if len(tied_first) > 1:
                recommendations.append(f"Note: Tie for 1st place among {', '.join(tied_first)} with score {first_score}")

            if len(top_bets) > 1:
                second_score = top_bets[1][1]
                tied_second = [name for name, score in top_bets if score == second_score]
                if len(tied_second) > 1:
                    recommendations.append(f"Note: Tie for 2nd place among {', '.join(tied_second)} with score {second_score}")

            if len(top_bets) > 2:
                third_score = top_bets[2][1]
                tied_third = [name for name, score in top_bets if score == third_score]
                if len(tied_third) > 1:
                    recommendations.append(f"Note: Tie for 3rd place among {', '.join(tied_third)} with score {third_score}")
    else:
        recommendations.append("Best Even Money Bets: No hits yet.")

    # Top Pick 18 Numbers without Neighbours (same as top_pick_18_numbers_without_neighbours)
    recommendations.append("")  # Add a blank line for separation
    straight_up_df = pd.DataFrame(list(state.scores.items()), columns=["Number", "Score"])
    straight_up_df = straight_up_df[straight_up_df["Score"] > 0].sort_values(by="Score", ascending=False)

    if straight_up_df.empty or len(straight_up_df) < 18:
        recommendations.append("Top Pick 18 Numbers without Neighbours: Not enough numbers have hit yet (need at least 18).")
        return "\n".join(recommendations)

    top_18_df = straight_up_df.head(18)
    top_18_numbers = top_18_df["Number"].tolist()
    scores_dict = dict(zip(top_18_df["Number"], top_18_df["Score"]))

    top_6 = top_18_numbers[:6]
    next_6 = top_18_numbers[6:12]
    last_6 = top_18_numbers[12:18]

    recommendations.append("Top Pick 18 Numbers without Neighbours:")
    recommendations.append("\nTop 6 Numbers (Yellow):")
    for i, num in enumerate(top_6, 1):
        score = scores_dict[num]
        recommendations.append(f"{i}. Number {num} (Score: {score})")

    recommendations.append("\nNext 6 Numbers (Blue):")
    for i, num in enumerate(next_6, 1):
        score = scores_dict[num]
        recommendations.append(f"{i}. Number {num} (Score: {score})")

    recommendations.append("\nLast 6 Numbers (Green):")
    for i, num in enumerate(last_6, 1):
        score = scores_dict[num]
        recommendations.append(f"{i}. Number {num} (Score: {score})")

    return "\n".join(recommendations)

def top_numbers_with_neighbours_tiered():
    recommendations = []
    straight_up_df = pd.DataFrame(list(state.scores.items()), columns=["Number", "Score"])
    straight_up_df = straight_up_df[straight_up_df["Score"] > 0].sort_values(by="Score", ascending=False)

    if straight_up_df.empty:
        return "<p>Top Numbers with Neighbours (Tiered): No numbers have hit yet.</p>"

    # Start with the HTML table for Strongest Numbers
    table_html = '<table border="1" style="border-collapse: collapse; text-align: center; font-family: Arial, sans-serif;">'
    table_html += "<tr><th>Hit</th><th>Left N.</th><th>Right N.</th></tr>"  # Table header
    for _, row in straight_up_df.iterrows():
        num = str(row["Number"])
        left, right = current_neighbors.get(row["Number"], ("", ""))
        left = str(left) if left is not None else ""
        right = str(right) if right is not None else ""
        table_html += f"<tr><td>{num}</td><td>{left}</td><td>{right}</td></tr>"
    table_html += "</table>"

    # Wrap the table in a div with a heading
    recommendations.append("<h3>Strongest Numbers:</h3>")
    recommendations.append(table_html)

    num_to_take = min(8, len(straight_up_df))
    top_numbers = straight_up_df["Number"].head(num_to_take).tolist()

    all_numbers = set()
    number_scores = {}
    for num in top_numbers:
        neighbors = current_neighbors.get(num, (None, None))
        left, right = neighbors
        all_numbers.add(num)
        number_scores[num] = state.scores[num]
        if left is not None:
            all_numbers.add(left)
        if right is not None:
            all_numbers.add(right)

    number_groups = []
    for num in top_numbers:
        left, right = current_neighbors.get(num, (None, None))
        group = [num]
        if left is not None:
            group.append(left)
        if right is not None:
            group.append(right)
        number_groups.append((state.scores[num], group))

    number_groups.sort(key=lambda x: x[0], reverse=True)
    ordered_numbers = []
    for _, group in number_groups:
        ordered_numbers.extend(group)

    ordered_numbers = ordered_numbers[:24]
    top_8 = ordered_numbers[:8]
    next_8 = ordered_numbers[8:16]
    last_8 = ordered_numbers[16:24]

    recommendations.append("<h3>Top Numbers with Neighbours (Tiered):</h3>")
    recommendations.append("<p><strong>Top Tier (Yellow):</strong></p>")
    for i, num in enumerate(top_8, 1):
        score = number_scores.get(num, 0)
        recommendations.append(f"<p>{i}. Number {num} (Score: {score})</p>")

    recommendations.append("<p><strong>Second Tier (Blue):</strong></p>")
    for i, num in enumerate(next_8, 1):
        score = number_scores.get(num, 0)
        recommendations.append(f"<p>{i}. Number {num} (Score: {score})</p>")

    recommendations.append("<p><strong>Third Tier (Green):</strong></p>")
    for i, num in enumerate(last_8, 1):
        score = number_scores.get(num, 0)
        recommendations.append(f"<p>{i}. Number {num} (Score: {score})</p>")

    return "\n".join(recommendations)


# Line 1: Start of neighbours_of_strong_number function (updated)
def neighbours_of_strong_number(neighbours_count, strong_numbers_count):
    """Recommend numbers and their neighbors based on hit frequency, including strategy recommendations with tie information."""
    recommendations = []
    
    # Validate inputs
    try:
        neighbours_count = int(neighbours_count)
        strong_numbers_count = int(strong_numbers_count)
        if neighbours_count < 0 or strong_numbers_count < 0:
            raise ValueError("Neighbours count and strong numbers count must be non-negative.")
        if strong_numbers_count == 0:
            raise ValueError("Strong numbers count must be at least 1.")
    except (ValueError, TypeError) as e:
        return f"Error: Invalid input - {str(e)}. Please use positive integers for neighbours and strong numbers.", {}

    # Check if current_neighbors is valid
    if not isinstance(current_neighbors, dict):
        return "Error: Neighbor data is not properly configured. Contact support.", {}
    for key, value in current_neighbors.items():
        if not isinstance(key, int) or not isinstance(value, tuple) or len(value) != 2:
            return "Error: Neighbor data is malformed. Contact support.", {}

    try:
        logger.debug(f"neighbours_of_strong_number: Starting with neighbours_count = {neighbours_count}, strong_numbers_count = {strong_numbers_count}")
        sorted_numbers = sorted(state.scores.items(), key=lambda x: (-x[1], x[0]))
        numbers_hits = [item for item in sorted_numbers if item[1] > 0]
        
        if not numbers_hits:
            recommendations.append("Neighbours of Strong Number: No numbers have hit yet.")
            return "\n".join(recommendations), {}

        # Limit strong_numbers_count to available hits
        strong_numbers_count = min(strong_numbers_count, len(numbers_hits))
        top_numbers = [item[0] for item in numbers_hits[:strong_numbers_count]]
        top_scores = {item[0]: item[1] for item in numbers_hits[:strong_numbers_count]}
        selected_numbers = set(top_numbers)
        neighbors_set = set()

        # Calculate neighbors for each strong number
        for strong_number in top_numbers:
            if strong_number not in current_neighbors:
                recommendations.append(f"Warning: No neighbor data for number {strong_number}. Skipping its neighbors.")
                continue
            current_number = strong_number
            # Left neighbors
            for i in range(neighbours_count):
                left, _ = current_neighbors.get(current_number, (None, None))
                if left is not None:
                    neighbors_set.add(left)
                    current_number = left
                else:
                    break
            # Right neighbors
            current_number = strong_number
            for i in range(neighbours_count):
                _, right = current_neighbors.get(current_number, (None, None))
                if right is not None:
                    neighbors_set.add(right)
                    current_number = right
                else:
                    break

        # Remove overlap (strong numbers take precedence)
        neighbors_set = neighbors_set - selected_numbers
        logger.debug(f"neighbours_of_strong_number: Strong numbers = {sorted(list(selected_numbers))}")
        logger.debug(f"neighbours_of_strong_number: Neighbors = {sorted(list(neighbors_set))}")

        # Combine all bet numbers (strong numbers + neighbors) for aggregated scoring
        bet_numbers = list(selected_numbers) + list(neighbors_set)

        # Calculate Aggregated Scores for the bet numbers (needed for Suggestions)
        even_money_scores, dozen_scores, column_scores = state.calculate_aggregated_scores_for_spins(bet_numbers)

        # Determine the best even money bet and check for ties
        sorted_even_money = sorted(even_money_scores.items(), key=lambda x: (-x[1], x[0]))
        best_even_money = sorted_even_money[0] if sorted_even_money else ("None", 0)
        best_even_money_name, best_even_money_hits = best_even_money
        # Check for ties in even money bets
        even_money_ties = []
        if sorted_even_money and best_even_money_hits > 0:
            even_money_ties = [f"{name}: {score}" for name, score in sorted_even_money if score == best_even_money_hits and name != best_even_money_name]
        even_money_tie_text = f" (Tied with {', '.join(even_money_ties)})" if even_money_ties else ""

        # Determine the best dozen and best column
        best_dozen = max(dozen_scores.items(), key=lambda x: x[1], default=("None", 0))
        best_dozen_name, best_dozen_hits = best_dozen
        best_column = max(column_scores.items(), key=lambda x: x[1], default=("None", 0))
        best_column_name, best_column_hits = best_column

        # Compare dozens vs. columns for the stronger section and check for ties
        suggestion = ""
        winner_category = ""
        best_bet_tie_text = ""
        if best_dozen_hits > best_column_hits:
            suggestion = f"{best_dozen_name}: {best_dozen_hits}"
            winner_category = "dozen"
            # Check if the best dozen ties with others
            sorted_dozens = sorted(dozen_scores.items(), key=lambda x: (-x[1], x[0]))
            dozen_ties = [f"{name}: {score}" for name, score in sorted_dozens if score == best_dozen_hits and name != best_dozen_name]
            if dozen_ties:
                best_bet_tie_text = f" (Tied with {', '.join(dozen_ties)})"
        elif best_column_hits > best_dozen_hits:
            suggestion = f"{best_column_name}: {best_column_hits}"
            winner_category = "column"
            # Check if the best column ties with others
            sorted_columns = sorted(column_scores.items(), key=lambda x: (-x[1], x[0]))
            column_ties = [f"{name}: {score}" for name, score in sorted_columns if score == best_column_hits and name != best_column_name]
            if column_ties:
                best_bet_tie_text = f" (Tied with {', '.join(column_ties)})"
        else:
            # Check for ties between dozens and columns at the top level
            sorted_dozens = sorted(dozen_scores.items(), key=lambda x: (-x[1], x[0]))
            sorted_columns = sorted(column_scores.items(), key=lambda x: (-x[1], x[0]))
            if len(sorted_dozens) >= 2 and sorted_dozens[0][1] == sorted_dozens[1][1] and sorted_dozens[0][1] > 0:
                # Two dozens tie at the highest hit count
                suggestion = f"{sorted_dozens[0][0]} and {sorted_dozens[1][0]}: {sorted_dozens[0][1]}"
                winner_category = "dozen"
                # Check for additional dozen ties
                dozen_ties = [f"{name}: {score}" for name, score in sorted_dozens[2:] if score == sorted_dozens[0][1]]
                if dozen_ties:
                    best_bet_tie_text = f" (Tied with {', '.join(dozen_ties)})"
            elif len(sorted_columns) >= 2 and sorted_columns[0][1] == sorted_columns[1][1] and sorted_columns[0][1] > 0:
                # Two columns tie at the highest hit count
                suggestion = f"{sorted_columns[0][0]} and {sorted_columns[1][0]}: {sorted_columns[0][1]}"
                winner_category = "column"
                # Check for additional column ties
                column_ties = [f"{name}: {score}" for name, score in sorted_columns[2:] if score == sorted_columns[0][1]]
                if column_ties:
                    best_bet_tie_text = f" (Tied with {', '.join(column_ties)})"
            else:
                # Default to the best dozen (alphabetically if tied), check for ties with columns
                suggestion = f"{best_dozen_name}: {best_dozen_hits}"
                winner_category = "dozen"
                if best_dozen_hits == best_column_hits and best_column_hits > 0:
                    best_bet_tie_text = f" (Tied with {best_column_name}: {best_column_hits})"

        # Determine the top two winners in the winning category (dozens or columns) and check for ties
        two_winners_suggestion = ""
        two_winners_tie_text = ""
        if winner_category == "dozen":
            sorted_dozens = sorted(dozen_scores.items(), key=lambda x: (-x[1], x[0]))
            top_two_dozens = sorted_dozens[:2]  # Take top two dozens
            if top_two_dozens[0][1] > 0:  # Only suggest if there are hits
                two_winners_suggestion = f"Play Two Dozens: {top_two_dozens[0][0]} ({top_two_dozens[0][1]}) and {top_two_dozens[1][0]} ({top_two_dozens[1][1]})"
                # Check if the second dozen ties with others
                if len(sorted_dozens) > 2:
                    second_score = top_two_dozens[1][1]
                    ties = [f"{name}: {score}" for name, score in sorted_dozens[2:] if score == second_score]
                    if ties:
                        two_winners_tie_text = f" (Tied with {', '.join(ties)})"
            else:
                two_winners_suggestion = "Play Two Dozens: Not enough hits to suggest two dozens."
        elif winner_category == "column":
            sorted_columns = sorted(column_scores.items(), key=lambda x: (-x[1], x[0]))
            top_two_columns = sorted_columns[:2]  # Take top two columns
            if top_two_columns[0][1] > 0:  # Only suggest if there are hits
                two_winners_suggestion = f"Play Two Columns: {top_two_columns[0][0]} ({top_two_columns[0][1]}) and {top_two_columns[1][0]} ({top_two_columns[1][1]})"
                # Check if the second column ties with others
                if len(sorted_columns) > 2:
                    second_score = top_two_columns[1][1]
                    ties = [f"{name}: {score}" for name, score in sorted_columns[2:] if score == second_score]
                    if ties:
                        two_winners_tie_text = f" (Tied with {', '.join(ties)})"
            else:
                two_winners_suggestion = "Play Two Columns: Not enough hits to suggest two columns."

        # Create the suggestions dictionary
        suggestions = {
            "best_even_money": f"{best_even_money_name}: {best_even_money_hits}{even_money_tie_text}",
            "best_bet": f"{suggestion}{best_bet_tie_text}",
            "play_two": f"{two_winners_suggestion}{two_winners_tie_text}"
        }

        # Append the Suggestions section first
        recommendations.append("Suggestions:")
        recommendations.append(f"Best Even Money Bet: {best_even_money_name}: {best_even_money_hits}{even_money_tie_text}")
        recommendations.append(f"Best Bet: {suggestion}{best_bet_tie_text}")
        recommendations.append(f"{two_winners_suggestion}{two_winners_tie_text}")

        # Now append the Strongest Numbers and Neighbours section
        recommendations.append(f"\nTop {strong_numbers_count} Strongest Numbers and Their Neighbours:")
        recommendations.append("\nStrongest Numbers (Yellow):")
        for i, num in enumerate(sorted(top_numbers), 1):
            score = top_scores[num]
            recommendations.append(f"{i}. Number {num} (Score: {score})")
        
        if neighbors_set:
            recommendations.append(f"\nNeighbours ({neighbours_count} Left + {neighbours_count} Right, Cyan):")
            for i, num in enumerate(sorted(list(neighbors_set)), 1):
                recommendations.append(f"{i}. Number {num}")
        else:
            recommendations.append(f"\nNeighbours ({neighbours_count} Left + {neighbours_count} Right, Cyan): None")

        return "\n".join(recommendations), suggestions

    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as e:
        logger.error(f"neighbours_of_strong_number: Unexpected error: {str(e)}")
        return f"Error in Neighbours of Strong Number: Unexpected issue - {str(e)}. Please try again or contact support.", {}
