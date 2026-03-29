"""WheelPulsePro – analysis & statistical functions extracted from app.py."""

import logging
import traceback

import pandas as pd

from roulette_data import (
    EVEN_MONEY,
    DOZENS,
    COLUMNS,
    NEIGHBORS_EUROPEAN,
    LEFT_OF_ZERO_EUROPEAN,
    RIGHT_OF_ZERO_EUROPEAN,
)

logger = logging.getLogger("wheelPulsePro.analysis")

# ---------------------------------------------------------------------------
# Injected module-level globals (set by init())
# ---------------------------------------------------------------------------
state = None
colors = None
current_neighbors = None

DEBUG = False  # Disable debug logging for production


def init(state_obj, colors_dict, neighbors):
    """Inject app-level globals into this module.

    Must be called once after ``app.py`` initialises its global state,
    before any analysis function is invoked.
    """
    global state, colors, current_neighbors
    state = state_obj
    colors = colors_dict
    current_neighbors = neighbors


def statistical_insights():
    if not state.last_spins:
        return "No spins to analyze yet—click some numbers first!"
    total_spins = len(state.last_spins)
    number_freq = {num: state.scores[num] for num in state.scores if state.scores[num] > 0}
    top_numbers = sorted(number_freq.items(), key=lambda x: x[1], reverse=True)[:5]
    output = [f"Total Spins: {total_spins}"]
    output.append("Top 5 Numbers by Hits:")
    for num, hits in top_numbers:
        output.append(f"Number {num}: {hits} hits")
    return "\n".join(output)

def create_html_table(df, title):
    if df.empty:
        return f"<h3>{title}</h3><p>No data to display.</p>"
    html = f"<h3>{title}</h3>"
    html += '<table border="1" style="border-collapse: collapse; text-align: center;">'
    html += "<tr>" + "".join(f"<th>{col}</th>" for col in df.columns) + "</tr>"
    for _, row in df.iterrows():
        html += "<tr>" + "".join(f"<td>{val}</td>" for val in row) + "</tr>"
    html += "</table>"
    return html

def render_rank_table(scores_dict, title, max_items=None):
    """Generates a sorted, ranked HTML table with visual progress bars for betting categories."""
    if not any(scores_dict.values()):
        return f"<div style='padding:10px; color:#888;'>Waiting for data analysis...</div>"
    
    # Sort by score (descending), then name (ascending)
    sorted_items = sorted(scores_dict.items(), key=lambda x: (-x[1], x[0]))
    if max_items:
        sorted_items = sorted_items[:max_items]
        
    max_score = max(scores_dict.values()) if scores_dict.values() else 1
    if max_score == 0: max_score = 1

    html = f"""
    <div class='reactor-table-wrapper'>
        <table style='width:100%; border-collapse: collapse; font-family: sans-serif; font-size: 13px;'>
            <tr style='background: rgba(0,0,0,0.05); text-align: left;'>
                <th style='padding: 8px; border-bottom: 2px solid #ddd; width: 40px; text-align: center;'>Pin</th>
                <th style='padding: 8px; border-bottom: 2px solid #ddd; width: 45px; text-align: center;'>Rank</th>
                <th style='padding: 8px; border-bottom: 2px solid #ddd;'>Category</th>
                <th style='padding: 8px; border-bottom: 2px solid #ddd; text-align: center; width: 60px;'>Hits</th>
                <th style='padding: 8px; border-bottom: 2px solid #ddd;'>Intensity</th>
            </tr>
    """
    
    for i, (name, score) in enumerate(sorted_items, 1):
        pct = (score / max_score) * 100
        # Style for winners
        is_winner = (score == max_score and score > 0)
        row_bg = "rgba(255, 215, 0, 0.15)" if is_winner else "transparent"
        rank_color = "#D4AF37" if i == 1 else "#999"
        bar_color = "#8e24aa" if is_winner else "#2196f3"
        opacity = "1.0" if score > 0 else "0.4"
        
        # KEY CHANGE: item_id is now Rank-based (e.g., Even_Money_Rank_1)
        # This makes the watchlist follow the RANK position, not the specific name.
        item_id = f"{title.replace(' ', '_')}_Rank_{i}"

        html += f"""
        <tr style='background: {row_bg}; opacity: {opacity}; transition: background 0.2s;'>
            <td style='padding: 6px 8px; text-align: center;'>
                <span class="star-pin" 
                      style="cursor:pointer; font-size:22px; color:#ccc; user-select:none; display:inline-block;" 
                      data-id="{item_id}" data-name="{name}" data-score="{score}" data-cat="{title}" data-rank="{i}"
                      onclick="togglePin(this)">★</span>
            </td>
            <td style='padding: 6px 8px; font-weight: bold; color: {rank_color}; text-align: center;'>#{i}</td>
            <td style='padding: 6px 8px; font-weight: {"bold" if is_winner else "normal"};' class="live-name-val">{name}</td>
            <td style='padding: 6px 8px; text-align: center; font-weight: bold;' class="live-score-val">{score}</td>
            <td style='padding: 6px 8px; width: 100px;'>
                <div style='width: 100%; height: 8px; background: #eee; border-radius: 4px; overflow: hidden;'>
                    <div style='width: {pct}%; height: 100%; background: {bar_color}; border-radius: 4px;'></div>
                </div>
            </td>
        </tr>
        """
    
    html += "</table></div>"
    return html

def create_strongest_numbers_with_neighbours_table():
    straight_up_df = pd.DataFrame(list(state.scores.items()), columns=["Number", "Score"])
    straight_up_df = straight_up_df[straight_up_df["Score"] > 0].sort_values(by="Score", ascending=False)
    if straight_up_df.empty:
        return "<h3>Strongest Numbers with Neighbours</h3><p>No numbers have hit yet.</p>"
    table_html = '<table id="strongest-numbers-live-table" border="1" style="border-collapse: collapse; text-align: center; font-family: Arial, sans-serif; width:100%; background-color: #1a1a1a;">'
    table_html += """
        <tr style='background:#333; color: white;'>
            <th style='padding: 10px;'>Pin</th>
            <th style='padding: 10px;'>Rank</th>
            <th style='padding: 10px;'>Hit</th>
            <th style='padding: 10px; color: #00FFFF;'>Left N.</th>
            <th style='padding: 10px; color: #00FFFF;'>Right N.</th>
            <th style='padding: 10px;'>Score</th>
        </tr>""" 
    for i, (_, row) in enumerate(straight_up_df.iterrows(), 1):
        num = int(row["Number"])
        left, right = current_neighbors.get(num, (None, None))
        bg_color = colors.get(str(num), "green")
        
        # Logic Shift: item_id is now Rank-based so the pinned box "chases" the rank, not the number.
        item_id = f"StrongNum_Rank_{i}"
        rank_color = "#FFD700" if i == 1 else "#00FFFF"

        table_html += f"""
        <tr style='border-bottom: 1px solid #444;'>
            <td style='padding: 10px; text-align: center;'>
                <span class="star-pin" 
                      style="cursor:pointer; font-size:28px; color:#ccc; user-select:none; display:inline-block;" 
                      data-id="{item_id}" data-type="number" data-rank="{i}" data-cat="Strong Number" onclick="togglePin(this)">★</span>
            </td>
            <td style='padding: 10px; font-weight: bold; color: {rank_color}; font-size: 18px;'>#{i}</td>
            <td style='padding: 5px; vertical-align: middle;'>
                <div style='background-color: {bg_color}; color: white; font-weight: 900; font-size: 24px; width: 50px; height: 50px; line-height: 46px; border-radius: 50%; margin: auto; border: 2px solid white; display: flex; align-items: center; justify-content: center; text-align: center;'>
                    {num}
                </div>
            </td>
            <td style='font-weight:bold; color: #00FFFF; font-size: 20px;' class="live-left-val">{left if left is not None else ""}</td>
            <td style='font-weight:bold; color: #00FFFF; font-size: 20px;' class="live-right-val">{right if right is not None else ""}</td>
            <td style='font-weight:900; color: white; font-size: 20px;' class="live-score-val">{int(row["Score"])}</td>
        </tr>
        """
    table_html += "</table>"
    return f"<h3 style='color: white; text-align: center;'>🎯 Strongest Numbers & Neighbours</h3>{table_html}"

def calculate_hit_percentages(last_spin_count):
    """Calculate hit percentages and generate BOTH Old Badges and New Charts."""
    try:
        # --- 1. Data Collection ---
        last_spin_count = int(last_spin_count) if last_spin_count is not None else 36
        last_spin_count = max(1, min(last_spin_count, 36))
        last_spins = state.last_spins[-last_spin_count:] if state.last_spins else []
        if not last_spins:
            return "<p>No spins available for analysis.</p>"

        total_spins = len(last_spins)
        even_money_counts = {"Red": 0, "Black": 0, "Even": 0, "Odd": 0, "Low": 0, "High": 0}
        column_counts = {"1st Column": 0, "2nd Column": 0, "3rd Column": 0}
        dozen_counts = {"1st Dozen": 0, "2nd Dozen": 0, "3rd Dozen": 0}

        for spin in last_spins:
            try:
                num = int(spin)
                for name, numbers in EVEN_MONEY.items():
                    if num in numbers: even_money_counts[name] += 1
                for name, numbers in COLUMNS.items():
                    if num in numbers: column_counts[name] += 1
                for name, numbers in DOZENS.items():
                    if num in numbers: dozen_counts[name] += 1
            except ValueError:
                continue

        max_even_money = max(even_money_counts.values()) if even_money_counts else 0
        max_columns = max(column_counts.values()) if column_counts else 0
        max_dozens = max(dozen_counts.values()) if dozen_counts else 0

        # --- Feature 2: ALL-TIME counts (Last 36 vs All comparison) ---
        all_spins_list = state.last_spins
        all_total = len(all_spins_list)
        all_even_money = {"Red": 0, "Black": 0, "Even": 0, "Odd": 0, "Low": 0, "High": 0}
        all_column_counts = {"1st Column": 0, "2nd Column": 0, "3rd Column": 0}
        all_dozen_counts = {"1st Dozen": 0, "2nd Dozen": 0, "3rd Dozen": 0}
        for _sp in all_spins_list:
            try:
                _n = int(_sp)
                for _name, _nums in EVEN_MONEY.items():
                    if _n in _nums: all_even_money[_name] += 1
                for _name, _nums in COLUMNS.items():
                    if _n in _nums: all_column_counts[_name] += 1
                for _name, _nums in DOZENS.items():
                    if _n in _nums: all_dozen_counts[_name] += 1
            except ValueError:
                pass

        # --- Feature 2: LAST-36 counts ---
        last36_list = state.last_spins[-36:] if state.last_spins else []
        last36_total = len(last36_list)
        last36_even_money = {"Red": 0, "Black": 0, "Even": 0, "Odd": 0, "Low": 0, "High": 0}
        last36_column_counts = {"1st Column": 0, "2nd Column": 0, "3rd Column": 0}
        last36_dozen_counts = {"1st Dozen": 0, "2nd Dozen": 0, "3rd Dozen": 0}
        for _sp in last36_list:
            try:
                _n = int(_sp)
                for _name, _nums in EVEN_MONEY.items():
                    if _n in _nums: last36_even_money[_name] += 1
                for _name, _nums in COLUMNS.items():
                    if _n in _nums: last36_column_counts[_name] += 1
                for _name, _nums in DOZENS.items():
                    if _n in _nums: last36_dozen_counts[_name] += 1
            except ValueError:
                pass

        # --- Feature 1: Mathematical expectations (European roulette) ---
        EVEN_MONEY_EXP = (18 / 37) * 100   # ~48.65%
        DOZEN_COL_EXP  = (12 / 37) * 100   # ~32.43%

        def _dev_html(pct, expected):
            """Return a coloured deviation chip: +X.X% / -X.X% / ±X.X%."""
            dev = pct - expected
            if abs(dev) < 2.0:
                col, sign = "#777777", f"±{abs(dev):.1f}%"
            elif dev > 0:
                col, sign = "#16a34a", f"+{dev:.1f}%"
            else:
                col, sign = "#dc2626", f"{dev:.1f}%"
            return (
                f'<span style="display:inline-block;font-size:10px;color:{col};font-weight:800;'
                f'margin-left:4px;padding:1px 5px;background:rgba(0,0,0,0.07);'
                f'border-radius:8px;vertical-align:middle;">{sign}</span>'
            )

        def _trend_html(l36_count, l36_tot, all_count, all_tot):
            """Return a last-36 vs all-time trend row with arrow."""
            if all_tot == 0 or l36_tot == 0:
                return ""
            pct_36 = l36_count / l36_tot * 100
            pct_all = all_count / all_tot * 100
            diff = pct_36 - pct_all
            if abs(diff) < 2.0:
                arrow, acol = "→", "#888888"
            elif diff > 0:
                arrow, acol = "↗", "#16a34a"
            else:
                arrow, acol = "↘", "#dc2626"
            if l36_tot < 36:
                note = f"&thinsp;<span style='color:#999;font-style:italic;'>(only&nbsp;{l36_tot})</span>"
            else:
                note = ""
            return (
                f'<div style="font-size:9px;color:#555;margin-top:3px;text-align:center;line-height:1.4;">'
                f'<span style="color:{acol};font-size:11px;font-weight:900;">{arrow}</span>'
                f'&thinsp;L36:&thinsp;{pct_36:.1f}%&thinsp;|&thinsp;All:&thinsp;{pct_all:.1f}%{note}'
                f'</div>'
            )

        # --- 2. OLD DISPLAY: Horizontal Badges ---
        old_html = '''<style>
        @keyframes dominant-pulse {
            0%   { box-shadow: 0 0 0 0 rgba(255,215,0,0.8), 0 0 8px rgba(255,215,0,0.5); transform: scale(1); }
            50%  { box-shadow: 0 0 0 6px rgba(255,215,0,0), 0 0 16px rgba(255,215,0,0.8); transform: scale(1.05); }
            100% { box-shadow: 0 0 0 0 rgba(255,215,0,0.8), 0 0 8px rgba(255,215,0,0.5); transform: scale(1); }
        }
        .dominant-pulse-badge {
            display: inline-flex !important;
            align-items: center !important;
            gap: 4px !important;
            background: linear-gradient(135deg, #FFD700, #FFA000) !important;
            color: #000 !important;
            font-weight: 900 !important;
            border: 2px solid #FFD700 !important;
            border-radius: 20px !important;
            padding: 3px 10px !important;
            font-size: 13px !important;
            animation: dominant-pulse 1.8s infinite !important;
            cursor: default;
        }
        .dominant-pulse-badge .trophy { font-size: 15px; }
        </style>'''
        old_html += '<div class="hit-percentage-overview">'
        old_html += f'<h4>Hit Percentage Overview (Last {total_spins} Spins):</h4>'
        old_html += '<div class="percentage-wrapper">'

        # Even Money — find pair winners (Red/Black, Odd/Even, Low/High)
        pair_winners_em = set()
        for pair in [("Red","Black"),("Odd","Even"),("Low","High")]:
            a, b = even_money_counts[pair[0]], even_money_counts[pair[1]]
            if a > b: pair_winners_em.add(pair[0])
            elif b > a: pair_winners_em.add(pair[1])
        old_html += '<div class="percentage-group">'
        old_html += '<h4 style="color: #b71c1c;">Even Money Bets</h4>'
        old_html += '<div class="percentage-badges">'
        for name, count in even_money_counts.items():
            percentage = (count / total_spins * 100) if total_spins > 0 else 0
            bar_color = "#b71c1c" if name == "Red" else "#000000" if name == "Black" else "#666"
            is_dom = name in pair_winners_em and count == max_even_money and max_even_money > 0
            if is_dom:
                badge_html = f'<span class="dominant-pulse-badge"><span class="trophy">🏆</span>{name}: {percentage:.1f}%</span>'
            else:
                badge_class = "percentage-item even-money winner" if count == max_even_money and max_even_money > 0 else "percentage-item even-money"
                badge_html = f'<span class="{badge_class}">{name}: {percentage:.1f}%</span>'
            dev_chip = _dev_html(percentage, EVEN_MONEY_EXP)
            trend_row = _trend_html(last36_even_money[name], last36_total, all_even_money[name], all_total)
            old_html += (
                f'<div class="percentage-with-bar" data-category="even-money">'
                f'{badge_html}{dev_chip}'
                f'<div class="progress-bar"><div class="progress-fill" style="width: {percentage}%; background-color: {bar_color};"></div></div>'
                f'{trend_row}</div>'
            )
        old_html += '</div></div>'

        # Columns
        max_col_name = max(column_counts, key=column_counts.get) if column_counts else None
        old_html += '<div class="percentage-group">'
        old_html += '<h4 style="color: #1565c0;">Columns</h4>'
        old_html += '<div class="percentage-badges">'
        for name, count in column_counts.items():
            percentage = (count / total_spins * 100) if total_spins > 0 else 0
            bar_color = "#1565c0"
            is_dom = count == max_columns and max_columns > 0 and name == max_col_name
            if is_dom:
                badge_html = f'<span class="dominant-pulse-badge"><span class="trophy">🏆</span>{name.split()[0]}: {percentage:.1f}%</span>'
            else:
                badge_class = "percentage-item column winner" if count == max_columns and max_columns > 0 else "percentage-item column"
                badge_html = f'<span class="{badge_class}">{name.split()[0]}: {percentage:.1f}%</span>'
            dev_chip = _dev_html(percentage, DOZEN_COL_EXP)
            trend_row = _trend_html(last36_column_counts[name], last36_total, all_column_counts[name], all_total)
            old_html += (
                f'<div class="percentage-with-bar" data-category="columns">'
                f'{badge_html}{dev_chip}'
                f'<div class="progress-bar"><div class="progress-fill" style="width: {percentage}%; background-color: {bar_color};"></div></div>'
                f'{trend_row}</div>'
            )
        old_html += '</div></div>'

        # Dozens
        max_doz_name = max(dozen_counts, key=dozen_counts.get) if dozen_counts else None
        old_html += '<div class="percentage-group">'
        old_html += '<h4 style="color: #388e3c;">Dozens</h4>'
        old_html += '<div class="percentage-badges">'
        for name, count in dozen_counts.items():
            percentage = (count / total_spins * 100) if total_spins > 0 else 0
            bar_color = "#388e3c"
            is_dom = count == max_dozens and max_dozens > 0 and name == max_doz_name
            if is_dom:
                badge_html = f'<span class="dominant-pulse-badge"><span class="trophy">🏆</span>{name.split()[0]}: {percentage:.1f}%</span>'
            else:
                badge_class = "percentage-item dozen winner" if count == max_dozens and max_dozens > 0 else "percentage-item dozen"
                badge_html = f'<span class="{badge_class}">{name.split()[0]}: {percentage:.1f}%</span>'
            dev_chip = _dev_html(percentage, DOZEN_COL_EXP)
            trend_row = _trend_html(last36_dozen_counts[name], last36_total, all_dozen_counts[name], all_total)
            old_html += (
                f'<div class="percentage-with-bar" data-category="dozens">'
                f'{badge_html}{dev_chip}'
                f'<div class="progress-bar"><div class="progress-fill" style="width: {percentage}%; background-color: {bar_color};"></div></div>'
                f'{trend_row}</div>'
            )
        old_html += '</div></div>'

        # --- Feature 1: Player Guidance Card (Deviation from Expected) ---
        all_devs = {}
        for _nm, _cnt in even_money_counts.items():
            _pct = (_cnt / total_spins * 100) if total_spins > 0 else 0
            all_devs[_nm] = _pct - EVEN_MONEY_EXP
        for _nm, _cnt in column_counts.items():
            _pct = (_cnt / total_spins * 100) if total_spins > 0 else 0
            all_devs[_nm] = _pct - DOZEN_COL_EXP
        for _nm, _cnt in dozen_counts.items():
            _pct = (_cnt / total_spins * 100) if total_spins > 0 else 0
            all_devs[_nm] = _pct - DOZEN_COL_EXP

        most_pos_cat  = max(all_devs, key=all_devs.get)
        most_neg_cat  = min(all_devs, key=all_devs.get)
        max_dev_val   = all_devs[most_pos_cat]
        min_dev_val   = all_devs[most_neg_cat]

        guidance_cards = []

        if max_dev_val >= 5.0:
            opp = ""
            for pair in [("Red","Black"),("Black","Red"),("Even","Odd"),("Odd","Even"),("Low","High"),("High","Low")]:
                if pair[0] == most_pos_cat: opp = pair[1]; break
            opp_str = f" Mean reversion players may consider switching to <strong>{opp}</strong>." if opp else ""
            guidance_cards.append(
                f'<div style="flex:1;min-width:220px;background:rgba(22,163,74,0.08);border:1px solid #16a34a;'
                f'border-radius:8px;padding:10px 12px;">'
                f'<div style="font-size:11px;font-weight:800;color:#15803d;margin-bottom:4px;">🔥 HOT: {most_pos_cat} (+{max_dev_val:.1f}%)</div>'
                f'<div style="font-size:10px;color:#444;line-height:1.5;">'
                f'<strong>{most_pos_cat}</strong> is running significantly above expected. '
                f'Trend followers may continue riding <strong>{most_pos_cat}</strong>.{opp_str} '
                f'Large positive deviations often correct toward the mean over many spins.'
                f'</div></div>'
            )

        if min_dev_val <= -5.0:
            guidance_cards.append(
                f'<div style="flex:1;min-width:220px;background:rgba(220,38,38,0.08);border:1px solid #dc2626;'
                f'border-radius:8px;padding:10px 12px;">'
                f'<div style="font-size:11px;font-weight:800;color:#dc2626;margin-bottom:4px;">🧊 COLD: {most_neg_cat} ({min_dev_val:.1f}%)</div>'
                f'<div style="font-size:10px;color:#444;line-height:1.5;">'
                f'<strong>{most_neg_cat}</strong> is running well below expected — it has been cold. '
                f'Mean reversion players see this as a potential opportunity (the category may be "due"). '
                f'Trend followers would avoid it until it shows signs of recovery.'
                f'</div></div>'
            )

        if not guidance_cards:
            guidance_cards.append(
                f'<div style="flex:1;min-width:220px;background:rgba(100,100,100,0.07);border:1px solid #aaa;'
                f'border-radius:8px;padding:10px 12px;">'
                f'<div style="font-size:11px;font-weight:800;color:#555;margin-bottom:4px;">⚖️ BALANCED Distribution</div>'
                f'<div style="font-size:10px;color:#444;line-height:1.5;">'
                f'All categories are running close to mathematical expectation (within ±2%). '
                f'No strong signal either way — use streaks or patterns to guide your next bet.'
                f'</div></div>'
            )

        guidance_html = (
            f'<div style="margin-top:14px;padding:10px 12px;background:rgba(142,36,170,0.05);'
            f'border:1px solid rgba(142,36,170,0.25);border-radius:8px;">'
            f'<div style="font-size:11px;font-weight:800;color:#7b1fa2;margin-bottom:8px;">'
            f'📉 Deviation Guide — What Does It Mean?'
            f'</div>'
            f'<div style="font-size:9px;color:#666;margin-bottom:8px;line-height:1.5;">'
            f'<strong>Deviation</strong> = actual % − expected %. '
            f'Even Money expected: <strong>{EVEN_MONEY_EXP:.2f}%</strong>&nbsp;(18/37). '
            f'Dozens &amp; Columns expected: <strong>{DOZEN_COL_EXP:.2f}%</strong>&nbsp;(12/37). '
            f'Over time all categories tend to revert toward expectation.</div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:8px;">{"".join(guidance_cards)}'
            f'<div style="flex:1;min-width:220px;background:rgba(100,100,100,0.07);border:1px solid #bbb;'
            f'border-radius:8px;padding:10px 12px;">'
            f'<div style="font-size:11px;font-weight:800;color:#555;margin-bottom:4px;">🔄 Trend Arrows Explained</div>'
            f'<div style="font-size:10px;color:#444;line-height:1.5;">'
            f'<strong style="color:#16a34a;">↗ Heating Up</strong> — last 36 % &gt; all-time %.<br>'
            f'<strong style="color:#dc2626;">↘ Cooling Down</strong> — last 36 % &lt; all-time %.<br>'
            f'<strong style="color:#888;">→ Stable</strong> — within ±2% of all-time average.<br>'
            f'36 spins ≈ one full wheel cycle, a meaningful recent sample.</div></div>'
            f'</div></div>'
        )
        old_html += guidance_html

        old_html += '</div></div>' # End percentage-wrapper and overview

        # --- 3. NEW DISPLAY: Vertical Charts (Appended) ---
        
        # Helper: Get Rank Color (Yellow > Blue > Green)
        def get_rank_color(items_dict, key):
            sorted_items = sorted(items_dict.items(), key=lambda x: x[1], reverse=True)
            try:
                rank_idx = [k for k, v in sorted_items].index(key)
                if rank_idx == 0: return "#FFD700" # Yellow (Hottest)
                if rank_idx == 1: return "#00BFFF" # Deep Sky Blue (2nd)
                return "#32CD32" # Lime Green (Coldest/3rd)
            except ValueError:
                return "#ccc"

        # Helper: Create Vertical Bar HTML
        def create_bar(label, count, total, color):
            percent = (count / total * 100) if total > 0 else 0
            return f"""
            <div style="display: flex; flex-direction: column; align-items: center; margin: 0 5px;">
                <span style="font-size: 10px; font-weight: bold; color: #333; margin-bottom: 2px;">{percent:.0f}%</span>
                <div style="width: 30px; height: 100px; display: flex; align-items: flex-end; justify-content: center; background: #f0f0f0; border-radius: 4px; overflow: hidden; border: 1px solid #ddd;">
                    <div style="width: 100%; height: {percent}%; background-color: {color}; transition: height 0.5s ease; border-top: 2px solid rgba(0,0,0,0.1);"></div>
                </div>
                <span style="font-size: 10px; font-weight: bold; color: #555; margin-top: 4px; text-align: center; max-width: 40px; line-height: 1.1;">{label}</span>
                <span style="font-size: 9px; color: #888;">({count})</span>
            </div>
            """

        new_html = '<div class="charts-section" style="margin-top: 20px; border-top: 1px dashed #ccc; padding-top: 15px;">'
        new_html += '<h4 style="margin: 0 0 15px 0; font-size: 16px; color: #333;">Visual Trend Comparison</h4>'
        new_html += '<div class="charts-container" style="display: flex; flex-wrap: wrap; gap: 20px; justify-content: center;">'
        
        # Chart 1: Even Money Pairs
        new_html += '<div class="chart-card" style="background: white; padding: 10px; border-radius: 8px; border: 1px solid #ccc; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">'
        new_html += '<h4 style="text-align: center; margin: 0 0 10px 0; color: #b71c1c; font-size: 14px;">Even Money</h4>'
        new_html += '<div style="display: flex; gap: 15px;">'
        
        # Red vs Black
        rb_group = {"Red": even_money_counts["Red"], "Black": even_money_counts["Black"]}
        new_html += '<div style="display: flex; gap: 2px; border-right: 1px solid #eee; padding-right: 10px;">'
        new_html += create_bar("Red", even_money_counts["Red"], total_spins, get_rank_color(rb_group, "Red"))
        new_html += create_bar("Black", even_money_counts["Black"], total_spins, get_rank_color(rb_group, "Black"))
        new_html += '</div>'

        # Odd vs Even
        oe_group = {"Odd": even_money_counts["Odd"], "Even": even_money_counts["Even"]}
        new_html += '<div style="display: flex; gap: 2px; border-right: 1px solid #eee; padding-right: 10px;">'
        new_html += create_bar("Odd", even_money_counts["Odd"], total_spins, get_rank_color(oe_group, "Odd"))
        new_html += create_bar("Even", even_money_counts["Even"], total_spins, get_rank_color(oe_group, "Even"))
        new_html += '</div>'

        # Low vs High
        lh_group = {"Low": even_money_counts["Low"], "High": even_money_counts["High"]}
        new_html += '<div style="display: flex; gap: 2px;">'
        new_html += create_bar("Low", even_money_counts["Low"], total_spins, get_rank_color(lh_group, "Low"))
        new_html += create_bar("High", even_money_counts["High"], total_spins, get_rank_color(lh_group, "High"))
        new_html += '</div>'
        new_html += '</div></div>'

        # Chart 2: Columns
        new_html += '<div class="chart-card" style="background: white; padding: 10px; border-radius: 8px; border: 1px solid #ccc; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">'
        new_html += '<h4 style="text-align: center; margin: 0 0 10px 0; color: #1565c0; font-size: 14px;">Columns</h4>'
        new_html += '<div style="display: flex; gap: 5px;">'
        for name in ["1st Column", "2nd Column", "3rd Column"]:
            new_html += create_bar(name.split()[0], column_counts[name], total_spins, get_rank_color(column_counts, name))
        new_html += '</div></div>'

        # Chart 3: Dozens
        new_html += '<div class="chart-card" style="background: white; padding: 10px; border-radius: 8px; border: 1px solid #ccc; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">'
        new_html += '<h4 style="text-align: center; margin: 0 0 10px 0; color: #388e3c; font-size: 14px;">Dozens</h4>'
        new_html += '<div style="display: flex; gap: 5px;">'
        for name in ["1st Dozen", "2nd Dozen", "3rd Dozen"]:
            new_html += create_bar(name.split()[0], dozen_counts[name], total_spins, get_rank_color(dozen_counts, name))
        new_html += '</div></div>'
        
        new_html += '</div>' # End charts-container
        
        # Legend
        new_html += """
        <div style="display: flex; justify-content: center; gap: 15px; margin-top: 10px; font-size: 11px; color: #555;">
            <div style="display: flex; align-items: center;"><span style="width: 10px; height: 10px; background: #FFD700; display: inline-block; margin-right: 4px; border-radius: 2px;"></span>Hottest</div>
            <div style="display: flex; align-items: center;"><span style="width: 10px; height: 10px; background: #00BFFF; display: inline-block; margin-right: 4px; border-radius: 2px;"></span>2nd Hot</div>
            <div style="display: flex; align-items: center;"><span style="width: 10px; height: 10px; background: #32CD32; display: inline-block; margin-right: 4px; border-radius: 2px;"></span>Coldest</div>
        </div>
        """
        new_html += '</div>' # End charts-section

        # Return concatenated HTML (Old + Separator + New)
        return old_html + new_html

    except Exception as e:
        logger.error(f"calculate_hit_percentages: Error: {str(e)}")
        return "<p>Error calculating hit percentages.</p>"

def summarize_spin_traits(last_spin_count):
    """Summarize traits for the last X spins as HTML badges, highlighting winners, hot streaks, and chopping patterns."""
    try:
        if DEBUG:
            logger.debug(f"summarize_spin_traits: last_spin_count = {last_spin_count}")
        
        # Validate and clamp last_spin_count
        last_spin_count = int(last_spin_count) if last_spin_count is not None else 36
        last_spin_count = max(1, min(last_spin_count, 36))
        if DEBUG:
            logger.debug(f"summarize_spin_traits: After clamping, last_spin_count = {last_spin_count}")

        # Validate state
        if not isinstance(state.last_spins, list):
            if DEBUG:
                logger.debug(f"summarize_spin_traits: Invalid state.last_spins")
            return "<p>Error: Spin data not initialized.</p>"
        
        last_spins = state.last_spins[-last_spin_count:] if state.last_spins else []
        if DEBUG:
            logger.debug(f"summarize_spin_traits: last_spins = {last_spins}")
        if not last_spins:
            return "<p>No spins available for analysis.</p>"

        # Validate bet mappings
        if not all(x in globals() for x in ['EVEN_MONEY', 'COLUMNS', 'DOZENS']):
            missing = [x for x in ['EVEN_MONEY', 'COLUMNS', 'DOZENS'] if x not in globals()]
            if DEBUG:
                logger.debug(f"summarize_spin_traits: Missing bet mappings: {missing}")
            return "<p>Error: Bet mappings not defined.</p>"

        # Validate EVEN_MONEY mappings for Red and Black
        if "Red" not in EVEN_MONEY or "Black" not in EVEN_MONEY:
            if DEBUG:
                logger.debug(f"summarize_spin_traits: EVEN_MONEY missing Red or Black mappings")
            return "<p>Error: EVEN_MONEY mappings incomplete.</p>"

        # Initialize counters and streaks
        even_money_counts = {"Red": 0, "Black": 0, "Even": 0, "Odd": 0, "Low": 0, "High": 0}
        column_counts = {"1st Column": 0, "2nd Column": 0, "3rd Column": 0}
        dozen_counts = {"1st Dozen": 0, "2nd Dozen": 0, "3rd Dozen": 0}
        number_counts = {}
        even_money_streaks = {key: {"current": 0, "max": 0, "last_hit": False, "spins": []} for key in even_money_counts}
        column_streaks = {key: {"current": 0, "max": 0, "last_hit": False, "spins": []} for key in column_counts}
        dozen_streaks = {key: {"current": 0, "max": 0, "last_hit": False, "spins": []} for key in dozen_counts}
        if DEBUG:
            logger.debug(f"summarize_spin_traits: Initialized counters and streaks")

        # Analyze spins
        for idx, spin in enumerate(last_spins):
            if DEBUG:
                logger.debug(f"summarize_spin_traits: Processing spin {idx}: {spin}")
            try:
                num = int(spin)
                if DEBUG:
                    logger.debug(f"summarize_spin_traits: Converted spin to integer: {num}")
                
                # Reset last_hit flags
                for key in even_money_streaks:
                    even_money_streaks[key]["last_hit"] = False
                for key in column_streaks:
                    column_streaks[key]["last_hit"] = False
                for key in dozen_streaks:
                    dozen_streaks[key]["last_hit"] = False
                if DEBUG:
                    logger.debug(f"summarize_spin_traits: Reset last_hit flags for spin {num}")

                # Even Money Bets
                for name, numbers in EVEN_MONEY.items():
                    if num in numbers:
                        even_money_counts[name] += 1
                        even_money_streaks[name]["last_hit"] = True
                        even_money_streaks[name]["current"] += 1
                        even_money_streaks[name]["spins"].append(str(num))
                        if len(even_money_streaks[name]["spins"]) > even_money_streaks[name]["current"]:
                            even_money_streaks[name]["spins"] = even_money_streaks[name]["spins"][-even_money_streaks[name]["current"]:]
                        even_money_streaks[name]["max"] = max(even_money_streaks[name]["max"], even_money_streaks[name]["current"])
                    else:
                        if not even_money_streaks[name]["last_hit"]:
                            even_money_streaks[name]["current"] = 0
                            even_money_streaks[name]["spins"] = []
                if DEBUG:
                    logger.debug(f"summarize_spin_traits: Processed Even Money Bets for spin {num}")

                # Columns
                for name, numbers in COLUMNS.items():
                    if num in numbers:
                        column_counts[name] += 1
                        column_streaks[name]["last_hit"] = True
                        column_streaks[name]["current"] += 1
                        column_streaks[name]["spins"].append(str(num))
                        if len(column_streaks[name]["spins"]) > column_streaks[name]["current"]:
                            column_streaks[name]["spins"] = column_streaks[name]["spins"][-column_streaks[name]["current"]:]
                        column_streaks[name]["max"] = max(column_streaks[name]["max"], column_streaks[name]["current"])
                    else:
                        if not column_streaks[name]["last_hit"]:
                            column_streaks[name]["current"] = 0
                            column_streaks[name]["spins"] = []
                if DEBUG:
                    logger.debug(f"summarize_spin_traits: Processed Columns for spin {num}")

                # Dozens
                for name, numbers in DOZENS.items():
                    if num in numbers:
                        dozen_counts[name] += 1
                        dozen_streaks[name]["last_hit"] = True
                        dozen_streaks[name]["current"] += 1
                        dozen_streaks[name]["spins"].append(str(num))
                        if len(dozen_streaks[name]["spins"]) > dozen_streaks[name]["current"]:
                            dozen_streaks[name]["spins"] = dozen_streaks[name]["spins"][-dozen_streaks[name]["current"]:]
                        dozen_streaks[name]["max"] = max(dozen_streaks[name]["max"], dozen_streaks[name]["current"])
                    else:
                        if not dozen_streaks[name]["last_hit"]:
                            dozen_streaks[name]["current"] = 0
                            dozen_streaks[name]["spins"] = []
                if DEBUG:
                    logger.debug(f"summarize_spin_traits: Processed Dozens for spin {num}")

                number_counts[num] = number_counts.get(num, 0) + 1
                if DEBUG:
                    logger.debug(f"summarize_spin_traits: Processed Repeat Numbers for spin {num}")
            except ValueError as ve:
                if DEBUG:
                    logger.error(f"summarize_spin_traits: ValueError converting spin {spin} to integer: {str(ve)}")
                continue

        # Calculate max counts
        if DEBUG:
            logger.debug(f"summarize_spin_traits: Calculating max counts")
        max_even_money = max(even_money_counts.values()) if even_money_counts else 0
        max_columns = max(column_counts.values()) if column_counts else 0
        max_dozens = max(dozen_counts.values()) if dozen_counts else 0
        if DEBUG:
            logger.debug(f"summarize_spin_traits: Max counts - Even Money: {max_even_money}, Columns: {max_columns}, Dozens: {max_dozens}")

        # Quick Trends and Betting Suggestions
        if DEBUG:
            logger.debug(f"summarize_spin_traits: Calculating Quick Trends")
        total_spins = len(last_spins)
        trends = []
        suggestions = []
        if total_spins > 0:
            all_counts = {**even_money_counts, **column_counts, **dozen_counts}
            dominant = max(all_counts.items(), key=lambda x: x[1], default=("None", 0))
            if dominant[1] > 0:
                percentage = (dominant[1] / total_spins * 100)
                trends.append(("hot", f"{dominant[0]} dominates with {percentage:.1f}% hits"))
                # Add suggestion for dominant trait
                if percentage >= 40:  # Suggest only if hit rate is significant
                    suggestions.append(f"Bet on {dominant[0]} - {percentage:.1f}% hit rate in last {total_spins} spins!")
            all_streaks = {**even_money_streaks, **column_streaks, **dozen_streaks}
            longest_streak = max((v["current"] for v in all_streaks.values() if v["current"] > 1), default=0)
            if longest_streak > 1:
                streak_name = next(k for k, v in all_streaks.items() if v["current"] == longest_streak)
                streak_spins = ", ".join(all_streaks[streak_name]["spins"][-longest_streak:])
                trends.append(("streak", f"{streak_name} on a {longest_streak}-spin streak (Spins: {streak_spins})"))
                # Add suggestion for streak
                if longest_streak >= 3:  # Suggest for significant streaks
                    suggestions.append(f"{streak_name} is hot - {longest_streak}/{total_spins} hits!")
            # Add cold trend for least hit trait
            least_hit = min(all_counts.items(), key=lambda x: x[1], default=("None", 0))
            if least_hit[1] == 0 and least_hit[0] != "None":
                trends.append(("cold", f"{least_hit[0]} has no hits"))
        if DEBUG:
            logger.debug(f"summarize_spin_traits: Quick Trends calculated: {trends}, Suggestions: {suggestions}")

        # Calculate Red/Black Switches (Suggestion 9)
        switch_count = 0
        switch_dots = []
        recent_spins = last_spins[-6:] if len(last_spins) >= 6 else last_spins
        if DEBUG:
            logger.debug(f"summarize_spin_traits: Recent spins for switch alert: {recent_spins}")
        for i, spin in enumerate(recent_spins):
            try:
                num = int(spin)
                color = "green" if num == 0 else \
                        "red" if num in EVEN_MONEY["Red"] else \
                        "black" if num in EVEN_MONEY["Black"] else "unknown"
                switch_dots.append(color)
                if i > 0 and color != "green" and switch_dots[i-1] != "green" and color != switch_dots[i-1]:
                    switch_count += 1
            except ValueError:
                switch_dots.append("unknown")
        switch_class = " high-switches" if switch_count >= 4 else ""
        if DEBUG:
            logger.debug(f"summarize_spin_traits: Red/Black Switches: {switch_count}, Dots: {switch_dots}")

        # Calculate Dozen Shifts (Suggestion 10)
        dozen_counts_prev = {"1st Dozen": 0, "2nd Dozen": 0, "3rd Dozen": 0}
        dozen_counts_current = {"1st Dozen": 0, "2nd Dozen": 0, "3rd Dozen": 0}
        prev_spins = last_spins[-10:-5] if len(last_spins) >= 10 else last_spins[:5] if len(last_spins) >= 5 else []
        current_spins = last_spins[-5:] if len(last_spins) >= 5 else last_spins
        for spin in prev_spins:
            try:
                num = int(spin)
                for name, numbers in DOZENS.items():
                    if num in numbers:
                        dozen_counts_prev[name] += 1
            except ValueError:
                continue
        for spin in current_spins:
            try:
                num = int(spin)
                for name, numbers in DOZENS.items():
                    if num in numbers:
                        dozen_counts_current[name] += 1
            except ValueError:
                continue
        dozen_shifts = {name: dozen_counts_current[name] - dozen_counts_prev[name] for name in dozen_counts}
        max_shift = max(dozen_shifts.values(), default=0)
        dominant_dozen = None
        dozen_class = ""
        if max_shift > 0:
            dominant_dozen = next(name for name, shift in dozen_shifts.items() if shift == max_shift)
            dozen_class = "d1" if dominant_dozen == "1st Dozen" else "d2" if dominant_dozen == "2nd Dozen" else "d3"
        if DEBUG:
            logger.debug(f"summarize_spin_traits: Dozen Shifts - Previous: {dozen_counts_prev}, Current: {dozen_counts_current}, Shifts: {dozen_shifts}, Dominant: {dominant_dozen}")

        # --- Pattern Type Detection for Badge ---
        def _detect_pattern_type(spins_list, sw_count):
            """Return (label, color, icon, description) for the dominant pattern."""
            n = len(spins_list)
            if n < 4:
                return ("WAITING", "#888888", "⏳", "Need more spins")
            # Streak: same color or same dozen appearing ≥4 times in last 6
            recent6 = spins_list[-6:]
            colors_r = []
            for s in recent6:
                try:
                    num = int(s)
                    if num in EVEN_MONEY.get("Red", set()): colors_r.append("R")
                    elif num in EVEN_MONEY.get("Black", set()): colors_r.append("B")
                    else: colors_r.append("G")
                except ValueError:
                    pass
            if colors_r.count("R") >= 4 or colors_r.count("B") >= 4:
                return ("STREAK", "#d32f2f", "⚡", "Same colour streak detected")
            # Check dozen streak
            doz_r = []
            for s in recent6:
                try:
                    num = int(s)
                    if num in DOZENS.get("1st Dozen", set()): doz_r.append("D1")
                    elif num in DOZENS.get("2nd Dozen", set()): doz_r.append("D2")
                    elif num in DOZENS.get("3rd Dozen", set()): doz_r.append("D3")
                    else: doz_r.append("Z")
                except ValueError:
                    pass
            for dz in ("D1","D2","D3"):
                if doz_r.count(dz) >= 4:
                    return ("STREAK", "#d32f2f", "⚡", f"{dz} dozen streak detected")
            # Chopping: high switch count
            if sw_count >= 4:
                return ("CHOPPING", "#e65100", "🔀", f"{sw_count} Red/Black switches")
            if sw_count >= 2:
                return ("CHOPPY", "#f57c00", "↕️", "Some alternation detected")
            # Balanced: no strong bias
            if n >= 8:
                total = n
                for name, nums in EVEN_MONEY.items():
                    cnt = sum(1 for s in spins_list if str(s) in [str(x) for x in nums])
                    if total > 0 and (cnt / total) > 0.65:
                        return ("BIASED", "#7b1fa2", "📌", f"{name} dominant: {cnt}/{total}")
                return ("BALANCED", "#2e7d32", "⚖️", "No clear pattern — mixed results")
            return ("RANDOM", "#555555", "🎲", "Insufficient data for pattern")

        _pattern_label, _pattern_color, _pattern_icon, _pattern_desc = _detect_pattern_type(last_spins, switch_count)

        _pattern_bg = {
            "STREAK":   "linear-gradient(135deg,#b71c1c,#d32f2f)",
            "CHOPPING": "linear-gradient(135deg,#bf360c,#e64a19)",
            "CHOPPY":   "linear-gradient(135deg,#e65100,#f57c00)",
            "BIASED":   "linear-gradient(135deg,#4a148c,#7b1fa2)",
            "BALANCED": "linear-gradient(135deg,#1b5e20,#388e3c)",
            "RANDOM":   "linear-gradient(135deg,#37474f,#546e7a)",
            "WAITING":  "linear-gradient(135deg,#616161,#9e9e9e)",
        }.get(_pattern_label, "linear-gradient(135deg,#555,#777)")

        # Build HTML
        if DEBUG:
            logger.debug(f"summarize_spin_traits: Building HTML")
        html = '<div class="traits-overview debug-highlight">'
        html += f'<h4>SpinTrend Radar (Last {len(last_spins)} Spins):</h4>'
        # --- Pattern Type Badge ---
        html += f'''<div style="display:flex; align-items:center; gap:12px; margin-bottom:12px; padding:10px 14px;
                        background:{_pattern_bg}; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.18);">
            <span style="font-size:26px; line-height:1;">{_pattern_icon}</span>
            <div>
                <div style="font-size:18px; font-weight:900; color:#fff; letter-spacing:1.5px;
                            text-transform:uppercase; text-shadow:0 1px 3px rgba(0,0,0,0.4);">
                    {_pattern_label}
                </div>
                <div style="font-size:11px; color:rgba(255,255,255,0.85); margin-top:2px;">{_pattern_desc}</div>
            </div>
        </div>'''
        html += '<div class="traits-wrapper">'
        html += '<div class="quick-trends">'
        html += '<h4 style="color: #ff9800;">Quick Trends</h4>'
        if trends or suggestions or switch_dots or (dominant_dozen and max_shift > 0):
            html += '<ul style="list-style-type: none; padding-left: 0;">'
            # Add trends
            for trend_type, trend in trends:
                icon = '<span class="trend-icon hot">🔥</span>' if trend_type == "hot" else \
                       '<span class="trend-icon cold">❄️</span>' if trend_type == "cold" else \
                       '<span class="trend-icon streak">⚡️</span>'
                html += f'<li style="color: #333; margin: 5px 0;">{icon}{trend}</li>'
            # Add suggestions
            for suggestion in suggestions[:2]:  # Limit to 2 suggestions to avoid clutter
                html += f'<li class="bet-suggestion" style="color: #ff4500; font-style: italic; margin: 5px 0;">{suggestion}</li>'
            # Add Red/Black Switch Alert as a trend item
            html += f'<li class="switch-alert{switch_class}" data-tooltip="{switch_count} color switches detected!" style="margin: 5px 0; padding: 8px; display: flex; flex-direction: column; align-items: flex-start;">'
            if switch_dots and any(color != "unknown" for color in switch_dots):
                html += '<div class="switch-dots-container">'
                for color in switch_dots:
                    if color != "unknown":
                        html += f'<span class="switch-dot {color}"></span>'
                html += '</div>'
                if switch_count >= 4:
                    spins_str = ", ".join(recent_spins)
                    logger.debug(f"summarize_spin_traits: Rendering chopping alert with {switch_count} switches, spins: {spins_str}")
                    html += f'<div class="chopping-alert"><span class="switch-alert">⚠️ Red/Black Chopping Alert: {switch_count} switches in {spins_str}!</span> <span class="red-badge"></span> <span class="black-badge"></span></div>'
                else:
                    html += f'<span style="color: #666; font-size: 12px;">Color switches: {switch_count}</span>'
            else:
                html += '<span style="color: #666; font-size: 12px;">No valid spins for color switch analysis.</span>'
            html += '</li>'
            # Add Dozen Shift Indicator as a trend item
            if dominant_dozen and max_shift > 0:
                html += f'<li class="dozen-shift-indicator" data-tooltip="Dozen Shift: {dominant_dozen}" style="margin: 5px 0; padding: 8px; display: flex; align-items: center;">'
                html += f'<span class="dozen-badge {dozen_class}">▲</span>'
                html += f'<span style="color: #333; font-size: 12px; margin-left: 5px;">{dominant_dozen} (+{max_shift} hits)</span>'
                html += '</li>'
            html += '</ul>'
        else:
            html += '<p>No significant trends detected yet.</p>'
        html += '</div>'
        if DEBUG:
            logger.debug(f"summarize_spin_traits: Quick Trends, Switch Alert, and Dozen Shift Indicator HTML generated")

        # Even Money Bets
        pair_winners_radar = set()
        for pair in [("Red","Black"),("Odd","Even"),("Low","High")]:
            a, b = even_money_counts[pair[0]], even_money_counts[pair[1]]
            if a > b: pair_winners_radar.add(pair[0])
            elif b > a: pair_winners_radar.add(pair[1])
        html += '<div class="badge-group">'
        html += '<h4 style="color: #b71c1c;">Even Money Bets</h4>'
        html += '<div class="percentage-badges">'
        for name, count in even_money_counts.items():
            streak = even_money_streaks[name]["max"]
            streak_title = f"{name} Hot Streak: {streak} consecutive hits" if streak >= 3 else ""
            percentage = (count / total_spins * 100) if total_spins > 0 else 0
            bar_color = "#b71c1c" if name in ["Red", "Even", "Low"] else "#000000" if name in ["Black", "Odd", "High"] else "#666"
            is_dom = name in pair_winners_radar and count == max_even_money and max_even_money > 0
            if is_dom:
                badge_html = f'<span class="dominant-pulse-badge" title="{streak_title}"><span class="trophy">🏆</span>{name}: {count}</span>'
            else:
                badge_class = "trait-badge even-money winner" if count == max_even_money and max_even_money > 0 else "trait-badge even-money"
                badge_html = f'<span class="{badge_class}" title="{streak_title}">{name}: {count}</span>'
            html += f'<div class="percentage-with-bar" data-category="even-money">{badge_html}<div class="progress-bar"><div class="progress-fill" style="width: {percentage}%; background-color: {bar_color};"></div></div></div>'
        html += '</div></div>'
        if DEBUG:
            logger.debug(f"summarize_spin_traits: Even Money Bets HTML generated")

        # Columns
        max_col_radar = max(column_counts, key=column_counts.get) if column_counts else None
        html += '<div class="badge-group">'
        html += '<h4 style="color: #1565c0;">Columns</h4>'
        html += '<div class="percentage-badges">'
        for name, count in column_counts.items():
            streak = column_streaks[name]["max"]
            streak_title = f"{name} Hot Streak: {streak} consecutive hits" if streak >= 3 else ""
            percentage = (count / total_spins * 100) if total_spins > 0 else 0
            is_dom = count == max_columns and max_columns > 0 and name == max_col_radar
            if is_dom:
                badge_html = f'<span class="dominant-pulse-badge" title="{streak_title}"><span class="trophy">🏆</span>{name}: {count}</span>'
            else:
                badge_class = "trait-badge column winner" if count == max_columns and max_columns > 0 else "trait-badge column"
                badge_html = f'<span class="{badge_class}" title="{streak_title}">{name}: {count}</span>'
            html += f'<div class="percentage-with-bar" data-category="columns">{badge_html}<div class="progress-bar"><div class="progress-fill" style="width: {percentage}%; background-color: {bar_color};"></div></div></div>'
        html += '</div></div>'
        if DEBUG:
            logger.debug(f"summarize_spin_traits: Columns HTML generated")

        # Dozens
        max_doz_radar = max(dozen_counts, key=dozen_counts.get) if dozen_counts else None
        html += '<div class="badge-group">'
        html += '<h4 style="color: #388e3c;">Dozens</h4>'
        html += '<div class="percentage-badges">'
        for name, count in dozen_counts.items():
            streak = dozen_streaks[name]["max"]
            streak_title = f"{name} Hot Streak: {streak} consecutive hits" if streak >= 3 else ""
            percentage = (count / total_spins * 100) if total_spins > 0 else 0
            is_dom = count == max_dozens and max_dozens > 0 and name == max_doz_radar
            if is_dom:
                badge_html = f'<span class="dominant-pulse-badge" title="{streak_title}"><span class="trophy">🏆</span>{name.split()[0]}: {count}</span>'
            else:
                badge_class = "trait-badge dozen winner" if count == max_dozens and max_dozens > 0 else "trait-badge dozen"
                badge_html = f'<span class="{badge_class}" title="{streak_title}">{name}: {count}</span>'
            html += f'<div class="percentage-with-bar" data-category="dozens">{badge_html}<div class="progress-bar"><div class="progress-fill" style="width: {percentage}%; background-color: {bar_color};"></div></div></div>'
        html += '</div></div>'
        if DEBUG:
            logger.debug(f"summarize_spin_traits: Dozens HTML generated")

        # Repeat Numbers
        html += '<div class="badge-group">'
        html += '<h4 style="color: #7b1fa2;">Repeat Numbers</h4>'
        html += '<div class="percentage-badges">'
        repeats = {num: count for num, count in number_counts.items() if count > 1}
        if repeats:
            for num, count in sorted(repeats.items()):
                html += f'<span class="trait-badge repeat">{num}: {count} hits</span>'
        else:
            html += '<span class="trait-badge repeat">No repeats</span>'
        html += '</div></div>'
        html += '</div></div>'  # Close traits-wrapper and traits-overview
        if DEBUG:
            logger.debug(f"summarize_spin_traits: Repeat Numbers HTML generated")

        if DEBUG:
            logger.debug(f"summarize_spin_traits: Returning HTML successfully")
        return html

    except Exception as e:
        logger.error(f"summarize_spin_traits: Unexpected error: {str(e)}\n{traceback.format_exc()}")
        return "<div style='color:#ef4444;padding:8px;'>⚠️ Traits analysis error — spins are preserved.</div>"

def cache_analysis(spins, last_spin_count):
    """Cache the results of summarize_spin_traits to avoid redundant calculations."""
    spins_list = state.last_spins
    if not spins_list and isinstance(spins, str) and spins.strip():
        spins_list = [s.strip() for s in spins.split(",") if s.strip()]
    
    cache_key = f"{last_spin_count}_{hash(tuple(spins_list))}"
    if cache_key in state.analysis_cache:
        if DEBUG:
            logger.debug(f"cache_analysis: Cache hit for key {cache_key}")
        return state.analysis_cache[cache_key]
    
    # Limit cache size
    MAX_CACHE_SIZE = 100
    if len(state.analysis_cache) >= MAX_CACHE_SIZE:
        oldest_key = next(iter(state.analysis_cache))
        del state.analysis_cache[oldest_key]
        if DEBUG:
            logger.debug(f"cache_analysis: Removed oldest cache entry {oldest_key}")
    
    # Perform analysis
    result = summarize_spin_traits(last_spin_count)
    state.analysis_cache[cache_key] = result
    if DEBUG:
        logger.debug(f"cache_analysis: Cached result for key {cache_key}")
    return result

def select_next_spin_top_pick(last_spin_count, trait_filter=None, trait_match_weight=100, secondary_match_weight=10, wheel_side_weight=5, section_weight=10, recency_weight=1, hit_bonus_weight=5, neighbor_weight=2):
    try:
        last_spin_count = int(last_spin_count) if last_spin_count is not None else 18
        last_spin_count = max(1, min(last_spin_count, 36))
        last_spins = state.last_spins[-last_spin_count:] if state.last_spins else []
        if not last_spins:
            return "<p>No spins available for analysis.</p>"
        # Log the spins being analyzed
        logger.debug(f"Analyzing last {last_spin_count} spins: {last_spins}")
        numbers = set(range(37))
        hit_counts = {n: 0 for n in range(37)}
        last_positions = {n: -1 for n in range(37)}
        for i, spin in enumerate(last_spins):
            try:
                num = int(spin)
                hit_counts[num] += 1
                last_positions[num] = i
            except ValueError:
                continue
        # Default to all traits if none specified or empty
        if trait_filter is None or not trait_filter:
            trait_filter = ["Red/Black", "Even/Odd", "Low/High", "Dozens", "Columns", "Wheel Sections", "Neighbors"]
        even_money_counts = {"Red": 0, "Black": 0, "Even": 0, "Odd": 0, "Low": 0, "High": 0}
        column_counts = {"1st Column": 0, "2nd Column": 0, "3rd Column": 0}
        dozen_counts = {"1st Dozen": 0, "2nd Dozen": 0, "3rd Dozen": 0}
        for spin in last_spins:
            try:
                num = int(spin)
                if "Red/Black" in trait_filter:
                    if num in EVEN_MONEY["Red"]:
                        even_money_counts["Red"] += 1
                    elif num in EVEN_MONEY["Black"]:
                        even_money_counts["Black"] += 1
                if "Even/Odd" in trait_filter:
                    if num in EVEN_MONEY["Even"]:
                        even_money_counts["Even"] += 1
                    elif num in EVEN_MONEY["Odd"]:
                        even_money_counts["Odd"] += 1
                if "Low/High" in trait_filter:
                    if num in EVEN_MONEY["Low"]:
                        even_money_counts["Low"] += 1
                    elif num in EVEN_MONEY["High"]:
                        even_money_counts["High"] += 1
                if "Dozens" in trait_filter:
                    for name, nums in DOZENS.items():
                        if num in nums:
                            dozen_counts[name] += 1
                if "Columns" in trait_filter:
                    for name, nums in COLUMNS.items():
                        if num in nums:
                            column_counts[name] += 1
            except ValueError:
                continue
        # Calculate percentages for included traits
        total_spins = len(last_spins)
        trait_percentages = {}
        if "Red/Black" in trait_filter:
            for trait in ["Red", "Black"]:
                trait_percentages[trait] = (even_money_counts[trait] / total_spins) * 100 if total_spins > 0 else 0
        if "Even/Odd" in trait_filter:
            for trait in ["Even", "Odd"]:
                trait_percentages[trait] = (even_money_counts[trait] / total_spins) * 100 if total_spins > 0 else 0
        if "Low/High" in trait_filter:
            for trait in ["Low", "High"]:
                trait_percentages[trait] = (even_money_counts[trait] / total_spins) * 100 if total_spins > 0 else 0
        if "Dozens" in trait_filter:
            for trait in dozen_counts:
                trait_percentages[trait] = (dozen_counts[trait] / total_spins) * 100 if total_spins > 0 else 0
        if "Columns" in trait_filter:
            for trait in column_counts:
                trait_percentages[trait] = (column_counts[trait] / total_spins) * 100 if total_spins > 0 else 0
        # Sort traits by percentage (highest to lowest)
        sorted_traits = sorted(trait_percentages.items(), key=lambda x: (-x[1], x[0]))
        # Determine hottest traits (top non-conflicting traits)
        hottest_traits = []
        seen_categories = set()
        for trait, percentage in sorted_traits:
            if trait in ["Red", "Black"]:
                if "Red-Black" in seen_categories:
                    continue
                hottest_traits.append(trait)
                seen_categories.add("Red-Black")
            elif trait in ["Even", "Odd"]:
                if "Even-Odd" in seen_categories:
                    continue
                hottest_traits.append(trait)
                seen_categories.add("Even-Odd")
            elif trait in ["Low", "High"]:
                if "Low-High" in seen_categories:
                    continue
                hottest_traits.append(trait)
                seen_categories.add("Low-High")
            elif trait in ["1st Dozen", "2nd Dozen", "3rd Dozen"]:
                if "Dozens" in seen_categories:
                    continue
                hottest_traits.append(trait)
                seen_categories.add("Dozens")
            elif trait in ["1st Column", "2nd Column", "3rd Column"]:
                if "Columns" in seen_categories:
                    continue
                hottest_traits.append(trait)
                seen_categories.add("Columns")
        # Second best traits for tiebreakers
        second_best_traits = []
        seen_categories = set()
        for trait, percentage in sorted_traits:
            if trait in hottest_traits:
                continue
            if trait in ["Red", "Black"]:
                if "Red-Black" in seen_categories:
                    continue
                second_best_traits.append(trait)
                seen_categories.add("Red-Black")
            elif trait in ["Even", "Odd"]:
                if "Even-Odd" in seen_categories:
                    continue
                second_best_traits.append(trait)
                seen_categories.add("Even-Odd")
            elif trait in ["Low", "High"]:
                if "Low-High" in seen_categories:
                    continue
                second_best_traits.append(trait)
                seen_categories.add("Low-High")
            elif trait in ["1st Dozen", "2nd Dozen", "3rd Dozen"]:
                if "Dozens" in seen_categories:
                    continue
                second_best_traits.append(trait)
                seen_categories.add("Dozens")
            elif trait in ["1st Column", "2nd Column", "3rd Column"]:
                if "Columns" in seen_categories:
                    continue
                second_best_traits.append(trait)
                seen_categories.add("Columns")
        # Wheel side analysis (only if included)
        left_side = set(LEFT_OF_ZERO_EUROPEAN)
        right_side = set(RIGHT_OF_ZERO_EUROPEAN)
        left_hits = 0
        right_hits = 0
        if "Wheel Sections" in trait_filter:
            left_hits = sum(hit_counts[num] for num in left_side)
            right_hits = sum(hit_counts[num] for num in right_side)
        most_hit_side = "Left" if left_hits > right_hits else "Right" if right_hits > left_hits else "Both"
        betting_sections = {
            "Voisins du Zero": [22, 18, 29, 7, 28, 12, 35, 3, 26, 0, 32, 15, 19, 4, 21, 2, 25],
            "Orphelins": [17, 34, 6, 1, 20, 14, 31, 9],
            "Tiers du Cylindre": [27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33]
        }
        section_hits = {name: 0 for name in betting_sections}
        section_last_pos = {name: -1 for name in betting_sections}
        if "Wheel Sections" in trait_filter:
            section_hits = {name: sum(hit_counts[num] for num in nums) for name, nums in betting_sections.items()}
            for name, nums in betting_sections.items():
                for num in nums:
                    if last_positions[num] > section_last_pos[name]:
                        section_last_pos[name] = last_positions[num]
        sorted_sections = sorted(section_hits.items(), key=lambda x: (-x[1], -section_last_pos[x[0]]))
        top_section = sorted_sections[0][0] if sorted_sections and "Wheel Sections" in trait_filter else None
        neighbor_boost = {num: 0 for num in range(37)}
        if "Neighbors" in trait_filter:
            last_five = last_spins[-5:] if len(last_spins) >= 5 else last_spins
            last_five_set = set(last_five)
            for num in range(37):
                if num in NEIGHBORS_EUROPEAN:
                    left, right = NEIGHBORS_EUROPEAN[num]
                    if left is not None and str(left) in last_five_set:
                        neighbor_boost[num] += 2
                    if right is not None and str(right) in last_five_set:
                        neighbor_boost[num] += 2
        # Score numbers based on the number of matching traits in order
        scores = []
        for num in range(37):
            if num not in hit_counts or hit_counts[num] == 0:
                continue  # Only consider numbers that appear in the spins
            # Count matching traits in order
            matching_traits = 0
            for trait in hottest_traits:
                if trait in EVEN_MONEY and num in EVEN_MONEY[trait]:
                    matching_traits += 1
                elif trait in DOZENS and num in DOZENS[trait]:
                    matching_traits += 1
                elif trait in COLUMNS and num in COLUMNS[trait]:
                    matching_traits += 1
            # Secondary score for second best traits
            secondary_matches = 0
            for trait in second_best_traits:
                if trait in EVEN_MONEY and num in EVEN_MONEY[trait]:
                    secondary_matches += 1
                elif trait in DOZENS and num in DOZENS[trait]:
                    secondary_matches += 1
                elif trait in COLUMNS and num in COLUMNS[trait]:
                    secondary_matches += 1
            # Additional scoring factors
            wheel_side_score = 0
            if "Wheel Sections" in trait_filter:
                if most_hit_side == "Both" or (most_hit_side == "Left" and num in left_side) or (most_hit_side == "Right" and num in right_side):
                    wheel_side_score = 1  # Will be scaled by weight
            section_score = 1 if top_section and num in betting_sections.get(top_section, []) else 0
            recency_score = (last_spin_count - (last_positions[num] + 1)) if last_positions[num] >= 0 else 0
            if last_positions[num] == last_spin_count - 1:
                recency_score = max(recency_score, 10)
            hit_bonus = 1 if hit_counts[num] > 0 else 0
            neighbor_score = neighbor_boost[num] if "Neighbors" in trait_filter else 0
            tiebreaker_score = 0
            if num == 0:
                pass
            else:
                if num in EVEN_MONEY["Red"] and "Red/Black" in trait_filter:
                    tiebreaker_score += even_money_counts["Red"]
                elif num in EVEN_MONEY["Black"] and "Red/Black" in trait_filter:
                    tiebreaker_score += even_money_counts["Black"]
                if num in EVEN_MONEY["Even"] and "Even/Odd" in trait_filter:
                    tiebreaker_score += even_money_counts["Even"]
                elif num in EVEN_MONEY["Odd"] and "Even/Odd" in trait_filter:
                    tiebreaker_score += even_money_counts["Odd"]
                if num in EVEN_MONEY["Low"] and "Low/High" in trait_filter:
                    tiebreaker_score += even_money_counts["Low"]
                elif num in EVEN_MONEY["High"] and "Low/High" in trait_filter:
                    tiebreaker_score += even_money_counts["High"]
            if "Dozens" in trait_filter:
                for name, nums in DOZENS.items():
                    if num in nums:
                        tiebreaker_score += dozen_counts[name]
                        break
            if "Columns" in trait_filter:
                for name, nums in COLUMNS.items():
                    if num in nums:
                        tiebreaker_score += column_counts[name]
                        break
            # Apply configurable weights
            total_score = (
                matching_traits * trait_match_weight +
                secondary_matches * secondary_match_weight +
                wheel_side_score * wheel_side_weight +
                section_score * section_weight +
                recency_score * recency_weight +
                hit_bonus * hit_bonus_weight +
                neighbor_score * neighbor_weight
            )
            scores.append((num, total_score, matching_traits, secondary_matches, wheel_side_score, section_score, recency_score, hit_bonus, neighbor_score, tiebreaker_score))
        # Sort by number of matching traits, then secondary matches, then tiebreaker, then recency
        scores.sort(key=lambda x: (-x[2], -x[3], -x[9], -x[6], -x[0]))
        # Ensure top 10 picks have at least as many matches as the 10th pick
        if len(scores) > 10:
            min_traits = sorted([x[2] for x in scores[:10]], reverse=True)[9]
            top_picks = [x for x in scores if x[2] >= min_traits][:10]
        else:
            top_picks = scores[:10]
            
        # --- NEW: SAVE TOP PICKS TO STATE FOR DE2D TRACKER ---
        # Only update previous if spins have actually changed (prevents double-fire wipe)
        new_top_10 = [x[0] for x in top_picks[:10]]
        if new_top_10 != state.current_top_picks:
            state.previous_top_picks = list(state.current_top_picks)
            state.current_top_picks = new_top_10
        # -----------------------------------------------------

        state.current_top_pick = top_picks[0][0]
        top_pick = top_picks[0][0]
        # Calculate confidence based on matching traits
        max_possible_traits = len(hottest_traits)
        top_traits_matched = top_picks[0][2]
        confidence = max(0, min(100, int((top_traits_matched / max_possible_traits) * 100))) if max_possible_traits > 0 else 0
        characteristics = []
        top_pick_int = int(top_pick)
        if top_pick_int == 0:
            characteristics.append("Green")
        elif "Red" in EVEN_MONEY and top_pick_int in EVEN_MONEY["Red"] and "Red/Black" in trait_filter:
            characteristics.append("Red")
        elif "Black" in EVEN_MONEY and top_pick_int in EVEN_MONEY["Black"] and "Red/Black" in trait_filter:
            characteristics.append("Black")
        if top_pick_int != 0:
            if "Even" in EVEN_MONEY and top_pick_int in EVEN_MONEY["Even"] and "Even/Odd" in trait_filter:
                characteristics.append("Even")
            elif "Odd" in EVEN_MONEY and top_pick_int in EVEN_MONEY["Odd"] and "Even/Odd" in trait_filter:
                characteristics.append("Odd")
            if "Low" in EVEN_MONEY and top_pick_int in EVEN_MONEY["Low"] and "Low/High" in trait_filter:
                characteristics.append("Low")
            elif "High" in EVEN_MONEY and top_pick_int in EVEN_MONEY["High"] and "Low/High" in trait_filter:
                characteristics.append("High")
        if "Dozens" in trait_filter:
            for name, nums in DOZENS.items():
                if top_pick_int in nums:
                    characteristics.append(name)
                    break
        if "Columns" in trait_filter:
            for name, nums in COLUMNS.items():
                if top_pick_int in nums:
                    characteristics.append(name)
                    break
        characteristics_str = ", ".join(characteristics) if characteristics else "No notable characteristics"
        color = colors.get(str(top_pick), "black")
        _, total_score, matching_traits, secondary_matches, wheel_side_score, section_score, recency_score, hit_bonus, neighbor_score, tiebreaker_score = top_picks[0]
        reasons = []
        matched_traits = []
        for trait in hottest_traits:
            if trait in EVEN_MONEY and top_pick in EVEN_MONEY[trait]:
                matched_traits.append(trait)
            elif trait in DOZENS and top_pick in DOZENS[trait]:
                matched_traits.append(trait)
            elif trait in COLUMNS and top_pick in COLUMNS[trait]:
                matched_traits.append(trait)
        if matched_traits:
            reasons.append(f"Matches the hottest traits: {', '.join(matched_traits)} (weight: {trait_match_weight})")
        if section_score > 0 and "Wheel Sections" in trait_filter:
            reasons.append(f"Located in the hottest wheel section: {top_section} (weight: {section_weight})")
        if recency_score > 0:
            last_pos = last_positions[top_pick]
            reasons.append(f"Recently appeared in the spin history (position {last_pos}) (weight: {recency_weight})")
        if hit_bonus > 0:
            reasons.append(f"Has appeared in the spin history (weight: {hit_bonus_weight})")
        if wheel_side_score > 0 and "Wheel Sections" in trait_filter:
            reasons.append(f"On the most hit side of the wheel: {most_hit_side} (weight: {wheel_side_weight})")
        if neighbor_score > 0 and "Neighbors" in trait_filter:
            neighbors_hit = [str(n) for n in NEIGHBORS_EUROPEAN.get(top_pick, (None, None)) if str(n) in last_five_set]
            reasons.append(f"Has recent neighbors in the last 5 spins: {', '.join(neighbors_hit)} (weight: {neighbor_weight})")
        if tiebreaker_score > 0:
            reasons.append(f"Boosted by aggregated trait scores (tiebreaker: {tiebreaker_score})")
        reasons_html = "<ul>" + "".join(f"<li>{reason}</li>" for reason in reasons) + "</ul>" if reasons else "<p>No specific reasons available.</p>"
        last_five_spins = last_spins[-5:] if len(last_spins) >= 5 else last_spins
        last_five_spins_html = ""
        for spin in last_five_spins:
            spin_color = colors.get(str(spin), "black")
            last_five_spins_html += f'<span class="first-spin {spin_color}">{spin}</span>'
        top_5_html = ""
        for i, (num, total_score, matching_traits, secondary_matches, wheel_side_score, section_score, recency_score, hit_bonus, neighbor_score, tiebreaker_score) in enumerate(top_picks[1:10], 1):
            num_color = colors.get(str(num), "black")
            num_characteristics = []
            if num == 0:
                num_characteristics.append("Green")
            elif "Red" in EVEN_MONEY and num in EVEN_MONEY["Red"] and "Red/Black" in trait_filter:
                num_characteristics.append("Red")
            elif "Black" in EVEN_MONEY and num in EVEN_MONEY["Black"] and "Red/Black" in trait_filter:
                num_characteristics.append("Black")
            if num != 0:
                if "Even" in EVEN_MONEY and num in EVEN_MONEY["Even"] and "Even/Odd" in trait_filter:
                    num_characteristics.append("Even")
                elif "Odd" in EVEN_MONEY and num in EVEN_MONEY["Odd"] and "Even/Odd" in trait_filter:
                    num_characteristics.append("Odd")
                if "Low" in EVEN_MONEY and num in EVEN_MONEY["Low"] and "Low/High" in trait_filter:
                    num_characteristics.append("Low")
                elif "High" in EVEN_MONEY and num in EVEN_MONEY["High"] and "Low/High" in trait_filter:
                    num_characteristics.append("High")
            if "Dozens" in trait_filter:
                for name, nums in DOZENS.items():
                    if num in nums:
                        num_characteristics.append(name)
                        break
            if "Columns" in trait_filter:
                for name, nums in COLUMNS.items():
                    if num in nums:
                        num_characteristics.append(name)
                        break
            num_characteristics_str = ", ".join(num_characteristics) if num_characteristics else "No notable characteristics"
            num_reasons = []
            num_matched_traits = []
            for trait in hottest_traits:
                if trait in EVEN_MONEY and num in EVEN_MONEY[trait]:
                    num_matched_traits.append(trait)
                elif trait in DOZENS and num in DOZENS[trait]:
                    num_matched_traits.append(trait)
                elif trait in COLUMNS and num in COLUMNS[trait]:
                    num_matched_traits.append(trait)
            if num_matched_traits:
                num_reasons.append(f"Matches: {', '.join(num_matched_traits)}")
            if "Wheel Sections" in trait_filter:
                for section_name, nums in betting_sections.items():
                    if num in nums:
                        num_reasons.append(f"In {section_name}")
                        break
            if tiebreaker_score > 0:
                num_reasons.append(f"Tiebreaker: {tiebreaker_score}")
            num_reasons_str = ", ".join(num_reasons) if num_reasons else "No notable reasons"
            top_5_html += f'''
            <div class="secondary-pick">
              <span class="secondary-badge {num_color}" data-number="{num}">{num}</span>
              <div class="secondary-info">
                <div class="secondary-characteristics">
                  {''.join(f'<span class="char-badge {char.lower()}">{char}</span>' for char in num_characteristics_str.split(", "))}
                </div>
                <div class="secondary-reasons">{num_reasons_str}</div>
              </div>
            </div>
            '''
        html = f'''
        <div class="first-spins">
          <h5>Last 5 Spins</h5>
          <div class="first-spins-container">{last_five_spins_html}</div>
        </div>
        <div class="top-pick-container">
          <h4>Top Pick for Next Spin</h4>
          <div class="top-pick-wrapper">
            <div class="badge-wrapper">
              <span class="top-pick-badge {color}" data-number="{top_pick}" onclick="copyToClipboard('{top_pick}')">{top_pick}</span>
            </div>
            <div class="top-pick-characteristics">
              {''.join(f'<span class="char-badge {char.lower()}">{char}</span>' for char in characteristics_str.split(", "))}
            </div>
          </div>
          <div class="confidence-bar">
            <div class="confidence-fill" style="width: {confidence}%"></div>
            <span>Confidence: {confidence}%</span>
          </div>
          <p class="top-pick-description">Based on analysis of the last {last_spin_count} spins.</p>
          <div class="accordion">
            <input type="checkbox" id="reasons-toggle" class="accordion-toggle">
            <label for="reasons-toggle" class="accordion-header">Why This Number Was Chosen</label>
            <div class="accordion-content">
              <div class="top-pick-reasons">
                {reasons_html}
              </div>
            </div>
          </div>
          <div class="secondary-picks">
            <h5>Other Top Picks</h5>
            <div class="secondary-picks-container">
              {top_5_html}
            </div>
          </div>
        </div>
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700&display=swap');
          @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
          }}
          @keyframes confetti {{
            0% {{ transform: translateY(0) rotate(0deg); opacity: 1; }}
            100% {{ transform: translateY(100vh) rotate(720deg); opacity: 0; }}
          }}
          .first-spins {{
            margin-bottom: 10px;
            text-align: center;
          }}
          .first-spins h5 {{
            margin: 0 0 5px 0;
            color: #FFD700;
            font-family: 'Montserrat', sans-serif;
            font-size: 16px;
            text-transform: uppercase;
          }}
          .first-spins-container {{
            display: flex;
            justify-content: center;
            gap: 5px;
          }}
          .first-spin {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 30px;
            height: 30px;
            border-radius: 15px;
            font-size: 18px;
            font-weight: bold;
            color: #ffffff !important;
            border: 1px solid #ffffff;
            box-shadow: 0 0 5px rgba(0, 0, 0, 0.3);
          }}
          .first-spin.red {{ background-color: red; }}
          .first-spin.black {{ background-color: black; }}
          .first-spin.green {{ background-color: green; }}
          .accordion {{
            margin: 10px 0;
            border: 1px solid #FFD700;
            border-radius: 8px;
            background: linear-gradient(135deg, #2E8B57, #FFD700);
            transition: all 0.3s ease;
          }}
          .accordion-toggle {{
            display: none;
          }}
          .accordion-header {{
            padding: 12px;
            font-weight: bold;
            font-size: 18px;
            color: #FFD700;
            cursor: pointer;
            text-transform: uppercase;
            display: flex;
            align-items: center;
            gap: 8px;
            font-family: 'Montserrat', sans-serif;
            position: sticky;
            top: 0;
            z-index: 10;
            background: inherit;
          }}
          .chip-icon {{
            font-size: 20px;
          }}
          .accordion-header:hover {{
            background-color: rgba(255, 255, 255, 0.2);
          }}
          .accordion-content {{
            display: none !important;
            animation: fadeIn 0.5s ease-in-out;
          }}
          .accordion-toggle:checked + .accordion-header + .accordion-content {{
            display: block !important;
          }}
          .top-pick-container {{
            background: linear-gradient(135deg, #2E8B57, #FFD700);
            border: 3px solid #FFD700;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 6px 12px rgba(0, 0, 0, 0.3);
            margin: 10px 0;
          }}
          .top-pick-container h4 {{
            margin: 0 0 15px 0;
            color: #FFD700;
            font-size: 24px;
            font-weight: bold;
            text-transform: uppercase;
            font-family: 'Montserrat', sans-serif;
          }}
          .top-pick-wrapper {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 10px;
          }}
          .badge-wrapper {{
            display: flex;
            align-items: center;
            gap: 10px;
          }}
          .top-pick-badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 60px;
            height: 60px;
            border-radius: 30px;
            font-weight: bold;
            font-size: 28px;
            color: #ffffff !important;
            background-color: {color};
            border: 2px solid #ffffff;
            box-shadow: 0 0 12px rgba(0, 0, 0, 0.3);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            cursor: pointer;
            position: relative;
          }}
          .top-pick-badge:hover {{
            transform: rotate(360deg) scale(1.2);
            box-shadow: 0 0 20px rgba(255, 215, 0, 0.8);
          }}
          .top-pick-badge.red {{ background-color: red; }}
          .top-pick-badge.black {{ background-color: black; }}
          .top-pick-badge.green {{ background-color: green; }}
          .top-pick-characteristics {{
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
            justify-content: center;
          }}
          .char-badge {{
            background-color: rgba(255, 213, 0, 0.9);
            color: #FFD700;
            font-weight: bold;
            font-size: 14px;
            padding: 3px 8px;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
          }}
          .char-badge.red {{ background-color: #FF0000; color: #ffffff; }}
          .char-badge.black {{ background-color: #000000; color: #ffffff; }}
          .char-badge.even {{ background-color: #4682B4; color: #ffffff; }}
          .char-badge.odd {{ background-color: #4682B4; color: #ffffff; }}
          .char-badge.low {{ background-color: #32CD32; color: #ffffff; }}
          .char-badge.high {{ background-color: #32CD32; color: #ffffff; }}
          .confidence-bar {{
            margin-top: 10px;
            background-color: #2E8B57;
            border-radius: 5px;
            height: 20px;
            position: relative;
            overflow: hidden;
          }}
          .confidence-fill {{
            height: 100%;
            background-color: #FFD700;
            transition: width 1s ease;
          }}
          .confidence-bar span {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: #2E8B57;
            font-size: 12px;
            font-weight: bold;
          }}
          .top-pick-description {{
            margin-top: 15px;
            font-style: italic;
            color: #3e2723;
            font-size: 14px;
          }}
          .top-pick-reasons {{
            padding: 10px;
            color: #3e2723;
            font-size: 14px;
          }}
          .top-pick-reasons ul {{
            list-style-type: disc;
            padding-left: 20px;
            margin: 0;
          }}
          .top-pick-reasons li {{
            margin-bottom: 5px;
          }}
          .secondary-picks {{
            margin-top: 20px;
            text-align: center;
          }}
          .secondary-picks h5 {{
            margin: 0 0 10px 0;
            color: #FFD700;
            font-family: 'Montserrat', sans-serif;
            font-size: 16px;
            text-transform: uppercase;
          }}
          .secondary-picks-container {{
            display: flex;
            justify-content: center;
            gap: 15px;
            flex-wrap: wrap;
          }}
          .secondary-pick {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 5px;
          }}
          .secondary-badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 50px;
            height: 50px;
            border-radius: 25px;
            font-weight: bold;
            font-size: 28px;
            color: #ffffff !important;
            border: 2px solid #ffffff;
            box-shadow: 0 0 8px rgba(0, 0, 0, 0.2);
            position: relative;
            transition: transform 0.3s ease;
          }}
          .secondary-badge:hover {{
            transform: rotate(360deg) scale(1.2);
          }}
          .secondary-badge.red {{ background-color: red; }}
          .secondary-badge.black {{ background-color: black; }}
          .secondary-badge.green {{ background-color: green; }}
          .secondary-info {{
            text-align: center;
          }}
          .secondary-characteristics {{
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
            justify-content: center;
          }}
          .secondary-reasons {{
            font-size: 10px;
            color: #3e2723;
            font-style: italic;
          }}
          .celebration {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 1000;
          }}
          .confetti {{
            position: absolute;
            width: 10px;
            height: 10px;
            background-color: #FFD700;
            animation: confetti 2s ease infinite;
          }}
          @media (max-width: 600px) {{
            .top-pick-badge {{
              width: 50px;
              height: 50px;
              font-size: 24px;
            }}
            .first-spin {{
              width: 25px;
              height: 25px;
              font-size: 14px;
            }}
            .secondary-badge {{
              width: 40px;
              height: 40px;
              font-size: 20px;
            }}
            .top-pick-container h4 {{
              font-size: 20px;
            }}
            .accordion-header {{
              font-size: 16px;
            }}
          }}
        </style>
        <script>
          function triggerConfetti() {{
            const celebration = document.querySelector('.celebration');
            for (let i = 0; i < 50; i++) {{
              const confetti = document.createElement('div');
              confetti.className = 'confetti';
              confetti.style.left = Math.random() * 100 + 'vw';
              confetti.style.backgroundColor = ['#FFD700', '#FF0000', '#2E8B57'][Math.floor(Math.random() * 3)];
              confetti.style.animationDelay = Math.random() * 2 + 's';
              celebration.appendChild(confetti);
            }}
          }}
          function copyToClipboard(text) {{
            navigator.clipboard.writeText(text).then(() => {{
              alert('Number ' + text + ' copied to clipboard!');
            }}).catch(err => {{
              console.error('Failed to copy: ', err);
            }});
          }}
        </script>
        '''
        return html
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as e:
        logger.error(f"select_next_spin_top_pick: Error: {str(e)}")
        return "<p>Error selecting top pick.</p>"

