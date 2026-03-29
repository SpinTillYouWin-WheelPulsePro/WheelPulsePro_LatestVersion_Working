"""RouletteState: mutable session state for WheelPulsePro.

Contains the single source-of-truth object that tracks all in-session data
including scores, spin history, bankroll, and progression state.
"""

from roulette_data import (
    EVEN_MONEY, DOZENS, COLUMNS, STREETS, CORNERS, SIX_LINES, SPLITS,
)

# Custom progression sequences for the Live Brain bet tracker.
# Each entry maps a bet-type name to an ordered list of unit multipliers.
# On LOSS → advance to next step; on WIN → reset to step 0.
# Actual bet = sequence[step_index] × base_unit (0.01, 0.10, or 1.00).
CUSTOM_PROGRESSIONS = {
    "Missing Dozen/Col": [1, 1, 2, 3, 4, 5, 7, 9, 13, 18, 25, 36, 52, 75, 109, 156, 224, 323, 474, 697, 1024, 1505, 2212, 3251, 4777, 7020, 10536, 15812, 23731, 35615, 53451, 80219, 120393],
    "Even Money Drought": [1, 2, 3, 5, 9, 16, 29, 54, 102, 191, 358, 671, 1302, 2524, 4894, 9491, 18404, 36839, 73740, 147606, 295463],
    "Two Dozens/Columns": [1, 3, 6, 15, 39, 107, 295, 812, 2232, 6416, 18443, 53015, 152401, 457140, 1371238],
    "Voisins": [1, 2, 3, 5, 8, 13, 22, 39, 69, 124, 221, 393, 724, 1331, 2448, 4503, 8283, 15236, 28877, 54730, 103729, 196599],
    "Tiers+Orph": [1, 2, 4, 7, 14, 27, 57, 119, 250, 523, 1095, 2376, 5159, 11200, 24315, 52789, 118727, 267030, 600577],
    "Sides Left/Right": [1, 3, 7, 20, 59, 176, 552, 1727, 5404, 17679],
    "5 Double Streets": [1, 5, 22, 115, 605, 3374, 18827, 110784],
    "Dynamic 17": [1, 2, 3, 5, 8, 13, 22, 39, 69, 124, 221, 393, 724, 1331, 2448, 4503, 8283, 15236, 28877, 54730, 103729, 196599],
    "Corners": [1, 2, 4, 7, 14, 27, 57, 119, 250, 523, 1095, 2376, 5159, 11200, 24315, 52789, 118727, 267030, 600577],
    "Manual Grind": [1, 1, 2, 3, 4, 6, 8, 11, 16, 22, 31, 44, 62, 88, 123],
}

# Maps brain recommendation category names to the appropriate custom progression.
_DOZEN_COL_NAMES = {"1st Dozen", "2nd Dozen", "3rd Dozen", "1st Column", "2nd Column", "3rd Column"}
_EVEN_MONEY_NAMES = {"Red", "Black", "Even", "Odd", "Low", "High"}


def get_custom_progression_for_bet(top_name: str) -> str:
    """Return the CUSTOM_PROGRESSIONS key that matches the brain's recommendation."""
    if top_name in _DOZEN_COL_NAMES:
        return "Missing Dozen/Col"
    if top_name in _EVEN_MONEY_NAMES:
        return "Even Money Drought"
    return "Missing Dozen/Col"


class RouletteState:
    def __init__(self):
        self.scores = {n: 0 for n in range(37)}
        self.even_money_scores = {name: 0 for name in EVEN_MONEY.keys()}
        self.dozen_scores = {name: 0 for name in DOZENS.keys()}
        self.column_scores = {name: 0 for name in COLUMNS.keys()}
        self.street_scores = {name: 0 for name in STREETS.keys()}
        self.corner_scores = {name: 0 for name in CORNERS.keys()}
        self.six_line_scores = {name: 0 for name in SIX_LINES.keys()}
        self.split_scores = {name: 0 for name in SPLITS.keys()}
        self.side_scores = {"Left Side of Zero": 0, "Right Side of Zero": 0}
        self.selected_numbers = set()
        self.last_spins = []
        self.spin_history = []
        self.casino_data = {
            "spins_count": 100,
            "hot_numbers": {},
            "cold_numbers": {},
            "even_odd": {"Even": 0.0, "Odd": 0.0},
            "red_black": {"Red": 0.0, "Black": 0.0},
            "low_high": {"Low": 0.0, "High": 0.0},
            "dozens": {"1st Dozen": 0.0, "2nd Dozen": 0.0, "3rd Dozen": 0.0},
            "columns": {"1st Column": 0.0, "2nd Column": 0.0, "3rd Column": 0.0}
        }
        self.hot_suggestions = ""
        self.cold_suggestions = ""
        self.use_casino_winners = False
        self.bankroll = 1000
        self.initial_bankroll = 1000
        self.base_unit = 10
        self.stop_loss = -500
        self.stop_win = 200
        self.target_profit = 10
        self.bet_type = "Even Money"
        self.progression = "Martingale"
        self.current_bet = self.base_unit
        self.next_bet = self.base_unit
        self.progression_state = None
        self.consecutive_wins = 0
        self.is_stopped = False
        self.message = f"Start with base bet of {self.base_unit} on {self.bet_type} ({self.progression})"
        self.status = "Active"
        self.status_color = "white"
        self.last_dozen_alert_index = -1
        self.alerted_patterns = set()
        self.last_alerted_spins = None
        self.labouchere_sequence = ""
        self.victory_vortex_sequence = [1, 8, 11, 16, 24, 35, 52, 78, 116, 174, 260, 390, 584, 876, 1313, 1969]
        
        # --- NEW VARIABLES FOR DYNAMIC 17 ASSAULT ---
        self.d17_list = []
        self.d17_locked = False
        
        # --- NEW: SNIPER LATCH ---
        self.sniper_locked = False
        self.sniper_locked_misses = 0
        self.sniper_threshold = 22
        
        # --- NEW: Store Pinned Numbers Permanently ---
        self.pinned_numbers = set()

        # --- NEW: Store Top Picks for HUD and Comparison ---
        self.current_top_picks = []
        self.previous_top_picks = []
        self.stability_counter = 0

        # --- NEW: Non-Repeater Memory for IN/OUT Radar ---
        self.current_non_repeaters = set()
        self.previous_non_repeaters = set()
        self.nr_last_spin_count = 0

        # --- NEW VARIABLES FOR DYNAMIC AIDEA ROADMAP ---
        self.aidea_phases = []          # Stores the parsed phase data
        self.aidea_rules = {}           # Stores the Win/Loss routing rules
        self.aidea_current_id = None    # ID of the currently active phase
        self.aidea_completed_ids = set() # IDs of phases marked as checked

        # --- NEW: Auto-Pilot Target Data (The "Blind Pilot" Fix) ---
        self.active_strategy_targets = [] # Stores concrete list of numbers (e.g., [1, 2, ... 12]) for the Auto-Pilot
        self.aidea_active_targets = [] # Stores targets specifically from uploaded JSON
        
        # --- NEW: Auto-Pilot Session Data ---
        self.aidea_last_result = None  # "WIN", "LOSS", or None
        self.aidea_bankroll = 0.0      # Tracks profit/loss specifically for the AIDEA strategy
        self.aidea_phase_repeats = {}  # Tracks consecutive wins for Aggressor logic
        
        # --- NEW: Trinity Sensor Memory for V9 Strategy ---
        self.trinity_dozen = "1st Dozen"
        self.trinity_ds = "DS 1-6"
        self.trinity_corner_nums = [1, 2, 4, 5]

        # --- Labouchere Sequence Tracker ---
        self.lab_active = False
        self.lab_sequence = []
        self.lab_base = 1.0
        self.lab_target = 10.0
        self.lab_bankroll = 0.0
        self.lab_status = "Waiting to Start"
        self.lab_mode = "2 Targets (Dozens/Columns)"
        self.lab_split_limit = 0.0

        # --- NEW: Analysis Cache ---
        self.analysis_cache = {}

        # --- NEW: Statistical Intelligence Layer ---
        # Tracks how many spins have elapsed since each betting category last hit.
        # Keys: every dozen, column, and even-money category name.
        self.drought_counters = {
            **{name: 0 for name in DOZENS.keys()},
            **{name: 0 for name in COLUMNS.keys()},
            **{name: 0 for name in EVEN_MONEY.keys()},
        }
        # Window size (number of recent spins) used for recency-weighted sigma analysis.
        self.analysis_window = 50

        # --- Render/strategy step counters ---
        self.aidea_unit_multiplier = 1
        self.play_specific_numbers_counter = 0
        self.grind_step_index = 0
        self.grind_last_spin_count = 0
        self.ramp_step_index = 0
        self.ramp_last_spin_count = 0

        # --- NEW: Live Brain — Bankroll & Bet Tracker ---
        self.live_brain_active = False
        self.live_brain_bankroll = 100.0
        self.live_brain_start_bankroll = 100.0
        self.live_brain_base_unit = 0.10
        self.live_brain_bets = []  # list of {spin_num, bet_targets, bet_amount, result_number, won, payout, bankroll_after}
        self.live_brain_suggestions_followed = 0
        self.live_brain_suggestions_total = 0
        self.live_brain_last_suggestion = ""
        self.live_brain_auto_follow = False
        self.live_brain_auto_size = False
        self.live_brain_last_confidence = 0
        self.live_brain_next_bet_amount = 0.10
        # Custom progression tracking
        self.live_brain_custom_progression_name = ""
        self.live_brain_custom_progression_step = 0

        # --- Strategy enabled flags (synced from HUD visibility filters) ---
        self.strategy_sniper_enabled = False
        self.strategy_trinity_enabled = False
        self.strategy_nr_enabled = False
        self.strategy_lab_enabled = False
        self.strategy_ramp_enabled = False
        self.strategy_grind_enabled = False

    def reset(self):
        use_casino_winners = self.use_casino_winners
        casino_data = self.casino_data.copy()
        self.scores = {n: 0 for n in range(37)}
        self.even_money_scores = {name: 0 for name in EVEN_MONEY.keys()}
        self.dozen_scores = {name: 0 for name in DOZENS.keys()}
        self.column_scores = {name: 0 for name in COLUMNS.keys()}
        self.street_scores = {name: 0 for name in STREETS.keys()}
        self.corner_scores = {name: 0 for name in CORNERS.keys()}
        self.six_line_scores = {name: 0 for name in SIX_LINES.keys()}
        self.split_scores = {name: 0 for name in SPLITS.keys()}
        self.side_scores = {"Left Side of Zero": 0, "Right Side of Zero": 0}
        self.selected_numbers = set()
        self.last_spins = []
        self.spin_history = []
        self.use_casino_winners = use_casino_winners
        self.casino_data = casino_data

        # Reset alert tracking
        self.last_dozen_alert_index = -1
        self.alerted_patterns = set()
        self.last_alerted_spins = None

        # Reset 17 Assault
        self.d17_list = []
        self.d17_locked = False

        # Reset Sniper Latch (sniper_threshold is a config value — not reset)
        self.sniper_locked = False
        self.sniper_locked_misses = 0

        # Reset Pinned Numbers
        self.pinned_numbers = set()

        # Reset Top Picks
        self.current_top_picks = []
        self.previous_top_picks = []
        self.stability_counter = 0

        # Reset Non-Repeater Memory
        self.current_non_repeaters = set()
        self.previous_non_repeaters = set()
        self.nr_last_spin_count = 0

        # Reset AIDEA Roadmap
        self.aidea_phases = []
        self.aidea_rules = {}
        self.aidea_current_id = None
        self.aidea_completed_ids = set()

        # Reset Strategy Targets
        self.active_strategy_targets = []
        self.aidea_active_targets = []

        # Reset AIDEA Session Data
        self.aidea_last_result = None
        self.aidea_bankroll = 0.0
        self.aidea_phase_repeats = {}

        # Reset Trinity Sensor
        self.trinity_dozen = "1st Dozen"
        self.trinity_ds = "DS 1-6"
        self.trinity_corner_nums = [1, 2, 4, 5]

        # Reset Labouchere Sequence Tracker
        self.lab_active = False
        self.lab_sequence = []
        self.lab_base = 1.0
        self.lab_target = 10.0
        self.lab_bankroll = 0.0
        self.lab_status = "Waiting to Start"
        self.lab_mode = "2 Targets (Dozens/Columns)"
        self.lab_split_limit = 0.0

        # Reset Analysis Cache
        self.analysis_cache = {}

        # Reset Statistical Intelligence Layer
        self.drought_counters = {
            **{name: 0 for name in DOZENS.keys()},
            **{name: 0 for name in COLUMNS.keys()},
            **{name: 0 for name in EVEN_MONEY.keys()},
        }
        self.analysis_window = 50

        # Reset Render/strategy step counters
        self.aidea_unit_multiplier = 1
        self.play_specific_numbers_counter = 0
        self.grind_step_index = 0
        self.grind_last_spin_count = 0
        self.ramp_step_index = 0
        self.ramp_last_spin_count = 0

        # Reset Live Brain
        self.live_brain_active = False
        self.live_brain_bankroll = 100.0
        self.live_brain_start_bankroll = 100.0
        self.live_brain_base_unit = 0.10
        self.live_brain_bets = []
        self.live_brain_suggestions_followed = 0
        self.live_brain_suggestions_total = 0
        self.live_brain_last_suggestion = ""
        self.live_brain_auto_follow = False
        self.live_brain_auto_size = False
        self.live_brain_last_confidence = 0
        self.live_brain_next_bet_amount = 0.10
        self.live_brain_custom_progression_name = ""
        self.live_brain_custom_progression_step = 0

        # Reset Strategy enabled flags
        self.strategy_sniper_enabled = False
        self.strategy_trinity_enabled = False
        self.strategy_nr_enabled = False
        self.strategy_lab_enabled = False
        self.strategy_ramp_enabled = False
        self.strategy_grind_enabled = False

        self.reset_progression()

    def calculate_aggregated_scores_for_spins(self, numbers):
        """Calculate Aggregated Scores for a list of numbers (simulated spins)."""
        even_money_scores = {name: 0 for name in EVEN_MONEY.keys()}
        dozen_scores = {name: 0 for name in DOZENS.keys()}
        column_scores = {name: 0 for name in COLUMNS.keys()}

        for number in numbers:
            if number == 0:
                continue

            for name, numbers_set in EVEN_MONEY.items():
                if number in numbers_set:
                    even_money_scores[name] += 1

            for name, numbers_set in DOZENS.items():
                if number in numbers_set:
                    dozen_scores[name] += 1

            for name, numbers_set in COLUMNS.items():
                if number in numbers_set:
                    column_scores[name] += 1

        return even_money_scores, dozen_scores, column_scores

    def reset_progression(self):
        self.current_bet = self.base_unit
        self.next_bet = self.base_unit
        self.progression_state = None
        self.consecutive_wins = 0
        self.is_stopped = False
        self.message = f"Progression reset. Start with base bet of {self.base_unit} on {self.bet_type} ({self.progression})"
        self.check_status()
        return (
            self.bankroll,
            self.current_bet,
            self.next_bet,
            self.message,
            f'<div style="background-color: {self.status_color}; padding: 5px; border-radius: 3px;">{self.status}</div>'
        )

    def check_status(self):
        profit = self.bankroll - self.initial_bankroll
        if profit <= self.stop_loss:
            self.status = "Stopped: Stop Loss Reached"
            self.status_color = "red"
        elif profit >= self.stop_win:
            self.status = "Stopped: Stop Win Reached"
            self.status_color = "green"
        else:
            self.status = "Active"
            self.status_color = "white"

    def reset_bankroll(self):
        self.bankroll = self.initial_bankroll
        self.is_stopped = False
        self.message = f"Bankroll reset to {self.initial_bankroll}."
        self.check_status()
        return (
            self.bankroll,
            self.current_bet,
            self.next_bet,
            self.message,
            f'<div style="background-color: {self.status_color}; padding: 5px; border-radius: 3px;">{self.status}</div>'
        )

    def update_bankroll(self, won):
        payout = {"Even Money": 1, "Dozens": 2, "Columns": 2, "Streets": 11, "Straight Bets": 35}.get(self.bet_type, 1)
        if won:
            self.bankroll += self.current_bet * payout
        else:
            self.bankroll -= self.current_bet
        profit = self.bankroll - self.initial_bankroll
        if profit <= self.stop_loss:
            self.is_stopped = True
            self.status = f"Stopped: Hit Stop Loss of {self.stop_loss}"
            self.status_color = "red"
        elif profit >= self.stop_win:
            self.is_stopped = True
            self.status = f"Stopped: Hit Stop Win of {self.stop_win}"
            self.status_color = "green"
        else:
            self.status_color = "white"

    def update_progression(self, won):
        if self.is_stopped:
            return (
                self.bankroll,
                self.current_bet,
                self.next_bet,
                self.message,
                f'<div style="background-color: {self.status_color}; padding: 5px; border-radius: 3px;">{self.status}</div>'
            )
        self.update_bankroll(won)
        if self.bankroll < self.current_bet:
            self.is_stopped = True
            self.status = "Stopped: Insufficient bankroll"
            self.status_color = "red"
            self.message = "Cannot continue: Bankroll too low."
            return (
                self.bankroll,
                self.current_bet,
                self.next_bet,
                self.message,
                f'<div style="background-color: {self.status_color}; padding: 5px; border-radius: 3px;">{self.status}</div>'
            )

        if self.progression == "Martingale":
            self.current_bet = self.next_bet
            self.next_bet = self.base_unit if won else self.current_bet * 2
            self.message = f"{'Win' if won else 'Loss'}! Next bet: {self.next_bet}"
        elif self.progression == "Fibonacci":
            fib = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]
            if self.progression_state is None:
                self.progression_state = 0
            self.current_bet = self.next_bet
            if won:
                self.progression_state = max(0, self.progression_state - 2)
                self.next_bet = fib[self.progression_state] * self.base_unit
                self.message = f"Win! Move back to {self.next_bet}"
            else:
                self.progression_state = min(len(fib) - 1, self.progression_state + 1)
                self.next_bet = fib[self.progression_state] * self.base_unit
                self.message = f"Loss! Next Fibonacci bet: {self.next_bet}"
        elif self.progression == "Victory Vortex V.2":
            if self.progression_state is None:
                self.progression_state = 0
            self.current_bet = self.next_bet
            if won:
                self.progression_state = 0
                self.next_bet = self.victory_vortex_sequence[0] * self.base_unit
                self.message = f"Win! Reset to {self.next_bet} (Victory Vortex V.2, Step 1)"
            else:
                self.progression_state = min(len(self.victory_vortex_sequence) - 1, self.progression_state + 1)
                self.next_bet = self.victory_vortex_sequence[self.progression_state] * self.base_unit
                self.message = f"Loss! Next bet: {self.next_bet} (Victory Vortex V.2, Step {self.progression_state + 1})"
        elif self.progression == "Triple Martingale":
            self.current_bet = self.next_bet
            self.next_bet = self.base_unit if won else self.current_bet * 3
            self.message = f"{'Win' if won else 'Loss'}! Next bet: {self.next_bet}"
        elif self.progression == "Ladder":
            self.current_bet = self.next_bet
            if won:
                self.next_bet = self.base_unit
                self.message = f"Win! Reset to {self.next_bet}"
            else:
                self.next_bet = self.current_bet + self.base_unit
                self.message = f"Loss! Increase to {self.next_bet}"
        elif self.progression == "D'Alembert":
            self.current_bet = self.next_bet
            if won:
                self.next_bet = max(self.base_unit, self.current_bet - self.base_unit)
                self.message = f"Win! Decrease to {self.next_bet}"
            else:
                self.next_bet = self.current_bet + self.base_unit
                self.message = f"Loss! Increase to {self.next_bet}"
        elif self.progression == "Double After a Win":
            self.current_bet = self.next_bet
            if won:
                self.next_bet = self.current_bet * 2
                self.message = f"Win! Double to {self.next_bet}"
            else:
                self.next_bet = self.base_unit
                self.message = f"Loss! Reset to {self.next_bet}"
        elif self.progression == "+1 Win / -1 Loss":
            self.current_bet = self.next_bet
            if won:
                self.next_bet = self.current_bet + self.base_unit
                self.message = f"Win! Increase to {self.next_bet}"
            else:
                self.next_bet = max(self.base_unit, self.current_bet - self.base_unit)
                self.message = f"Loss! Decrease to {self.next_bet}"
        elif self.progression == "+2 Win / -1 Loss":
            self.current_bet = self.next_bet
            if won:
                self.next_bet = self.current_bet + (self.base_unit * 2)
                self.message = f"Win! Increase by 2 units to {self.next_bet}"
            else:
                self.next_bet = max(self.base_unit, self.current_bet - self.base_unit)
                self.message = f"Loss! Decrease to {self.next_bet}"
        elif self.progression == "Double Loss / +50% Win":
            self.current_bet = self.next_bet
            if won:
                self.consecutive_wins += 1
                if self.consecutive_wins >= 2:
                    self.next_bet = self.base_unit
                    self.message = f"Win! Resetting to base bet of {self.next_bet} after {self.consecutive_wins} wins."
                    self.consecutive_wins = 0
                else:
                    self.next_bet = round(self.current_bet * 1.5, 2)
                    self.message = f"Win! Increasing bet by 50% to {self.next_bet}."
            else:
                self.consecutive_wins = 0
                self.next_bet = round(self.current_bet * 2, 2)
                self.message = f"Loss! Doubling bet to {self.next_bet}."

        # Check stop conditions
        profit = self.bankroll - self.initial_bankroll
        if profit <= self.stop_loss:
            self.is_stopped = True
            self.status = "Stopped: Stop Loss Reached"
            self.status_color = "red"
            self.message = f"Stop Loss reached at {profit}. Current bankroll: {self.bankroll}"
        elif profit >= self.stop_win:
            self.is_stopped = True
            self.status = "Stopped: Stop Win Reached"
            self.status_color = "green"
            self.message = f"Stop Win reached at {profit}. Current bankroll: {self.bankroll}"

        return (
            self.bankroll,
            self.current_bet,
            self.next_bet,
            self.message,
            f'<div style="background-color: {self.status_color}; padding: 5px; border-radius: 3px;">{self.status}</div>'
        )

    def update_live_brain_progression(self, won: bool) -> None:
        """Advance or reset the custom progression step for the Live Brain tracker.

        On win  → reset to step 0 (profit secured, start fresh).
        On loss → advance one step deeper into the sequence (up to the last step).
        """
        prog_name = getattr(self, 'live_brain_custom_progression_name', '')
        if not prog_name or prog_name not in CUSTOM_PROGRESSIONS:
            return
        seq = CUSTOM_PROGRESSIONS[prog_name]
        if won:
            self.live_brain_custom_progression_step = 0
        else:
            step = getattr(self, 'live_brain_custom_progression_step', 0)
            self.live_brain_custom_progression_step = min(step + 1, len(seq) - 1)

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize all state fields to a JSON-serializable dict.

        Sets are stored as lists; integer-keyed dicts (scores) have their
        keys converted to strings so the result is valid JSON.
        """
        return {
            # --- Scores (int keys → str for JSON) ---
            "scores": {str(k): v for k, v in self.scores.items()},
            "even_money_scores": dict(self.even_money_scores),
            "dozen_scores": dict(self.dozen_scores),
            "column_scores": dict(self.column_scores),
            "street_scores": dict(self.street_scores),
            "corner_scores": dict(self.corner_scores),
            "six_line_scores": dict(self.six_line_scores),
            "split_scores": dict(self.split_scores),
            "side_scores": dict(self.side_scores),
            # --- Sets → lists ---
            "selected_numbers": list(self.selected_numbers),
            "alerted_patterns": list(self.alerted_patterns),
            "pinned_numbers": list(self.pinned_numbers),
            "current_non_repeaters": list(self.current_non_repeaters),
            "previous_non_repeaters": list(self.previous_non_repeaters),
            "aidea_completed_ids": list(self.aidea_completed_ids),
            # --- Spin history ---
            "last_spins": list(self.last_spins),
            "spin_history": list(self.spin_history),
            # --- Casino data ---
            "casino_data": self.casino_data,
            "hot_suggestions": self.hot_suggestions,
            "cold_suggestions": self.cold_suggestions,
            "use_casino_winners": self.use_casino_winners,
            # --- Bankroll / betting ---
            "bankroll": self.bankroll,
            "initial_bankroll": self.initial_bankroll,
            "base_unit": self.base_unit,
            "stop_loss": self.stop_loss,
            "stop_win": self.stop_win,
            "target_profit": self.target_profit,
            "bet_type": self.bet_type,
            "progression": self.progression,
            "current_bet": self.current_bet,
            "next_bet": self.next_bet,
            "progression_state": self.progression_state,
            "consecutive_wins": self.consecutive_wins,
            "is_stopped": self.is_stopped,
            "message": self.message,
            "status": self.status,
            "status_color": self.status_color,
            "last_dozen_alert_index": self.last_dozen_alert_index,
            "last_alerted_spins": self.last_alerted_spins,
            "labouchere_sequence": self.labouchere_sequence,
            "victory_vortex_sequence": list(self.victory_vortex_sequence),
            # --- Dynamic 17 Assault ---
            "d17_list": list(self.d17_list),
            "d17_locked": self.d17_locked,
            # --- Sniper ---
            "sniper_locked": self.sniper_locked,
            "sniper_locked_misses": self.sniper_locked_misses,
            "sniper_threshold": self.sniper_threshold,
            # --- Top picks / non-repeaters ---
            "current_top_picks": list(self.current_top_picks),
            "previous_top_picks": list(self.previous_top_picks),
            "stability_counter": self.stability_counter,
            "nr_last_spin_count": self.nr_last_spin_count,
            # --- AIDEA roadmap ---
            "aidea_phases": list(self.aidea_phases),
            "aidea_rules": dict(self.aidea_rules),
            "aidea_current_id": self.aidea_current_id,
            "active_strategy_targets": list(self.active_strategy_targets),
            "aidea_active_targets": list(self.aidea_active_targets),
            "aidea_last_result": self.aidea_last_result,
            "aidea_bankroll": self.aidea_bankroll,
            "aidea_phase_repeats": dict(self.aidea_phase_repeats),
            "aidea_unit_multiplier": self.aidea_unit_multiplier,
            # --- Trinity ---
            "trinity_dozen": self.trinity_dozen,
            "trinity_ds": self.trinity_ds,
            "trinity_corner_nums": list(self.trinity_corner_nums),
            # --- Labouchere ---
            "lab_active": self.lab_active,
            "lab_sequence": list(self.lab_sequence),
            "lab_base": self.lab_base,
            "lab_target": self.lab_target,
            "lab_bankroll": self.lab_bankroll,
            "lab_status": self.lab_status,
            "lab_mode": self.lab_mode,
            "lab_split_limit": self.lab_split_limit,
            # --- Statistical intelligence ---
            "drought_counters": dict(self.drought_counters),
            "analysis_window": self.analysis_window,
            # --- Step counters ---
            "play_specific_numbers_counter": self.play_specific_numbers_counter,
            "grind_step_index": self.grind_step_index,
            "grind_last_spin_count": self.grind_last_spin_count,
            "ramp_step_index": self.ramp_step_index,
            "ramp_last_spin_count": self.ramp_last_spin_count,
            # --- Live Brain ---
            "live_brain_active": self.live_brain_active,
            "live_brain_bankroll": self.live_brain_bankroll,
            "live_brain_start_bankroll": self.live_brain_start_bankroll,
            "live_brain_base_unit": self.live_brain_base_unit,
            "live_brain_bets": list(self.live_brain_bets),
            "live_brain_suggestions_followed": self.live_brain_suggestions_followed,
            "live_brain_suggestions_total": self.live_brain_suggestions_total,
            "live_brain_last_suggestion": self.live_brain_last_suggestion,
            "live_brain_auto_follow": self.live_brain_auto_follow,
            "live_brain_auto_size": self.live_brain_auto_size,
            "live_brain_last_confidence": self.live_brain_last_confidence,
            "live_brain_next_bet_amount": self.live_brain_next_bet_amount,
            "live_brain_custom_progression_name": self.live_brain_custom_progression_name,
            "live_brain_custom_progression_step": self.live_brain_custom_progression_step,
            # --- Strategy flags ---
            "strategy_sniper_enabled": self.strategy_sniper_enabled,
            "strategy_trinity_enabled": self.strategy_trinity_enabled,
            "strategy_nr_enabled": self.strategy_nr_enabled,
            "strategy_lab_enabled": self.strategy_lab_enabled,
            "strategy_ramp_enabled": self.strategy_ramp_enabled,
            "strategy_grind_enabled": self.strategy_grind_enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RouletteState":
        """Reconstruct a RouletteState from a dict produced by to_dict().

        Unknown or missing keys fall back to the same defaults used in
        ``__init__`` so older session files remain loadable.
        """
        obj = cls()  # populate all defaults first

        # --- Scores ---
        raw_scores = data.get("scores", {})
        try:
            obj.scores = {int(k): v for k, v in raw_scores.items()}
        except (ValueError, TypeError):
            pass
        obj.even_money_scores = data.get("even_money_scores", obj.even_money_scores)
        obj.dozen_scores = data.get("dozen_scores", obj.dozen_scores)
        obj.column_scores = data.get("column_scores", obj.column_scores)
        obj.street_scores = data.get("street_scores", obj.street_scores)
        obj.corner_scores = data.get("corner_scores", obj.corner_scores)
        obj.six_line_scores = data.get("six_line_scores", obj.six_line_scores)
        obj.split_scores = data.get("split_scores", obj.split_scores)
        obj.side_scores = data.get("side_scores", obj.side_scores)

        # --- Sets (stored as lists in JSON) ---
        obj.selected_numbers = set(data.get("selected_numbers", []))
        obj.alerted_patterns = set(data.get("alerted_patterns", []))
        obj.pinned_numbers = set(data.get("pinned_numbers", []))
        obj.current_non_repeaters = set(data.get("current_non_repeaters", []))
        obj.previous_non_repeaters = set(data.get("previous_non_repeaters", []))
        obj.aidea_completed_ids = set(data.get("aidea_completed_ids", []))

        # --- Spin history ---
        obj.last_spins = data.get("last_spins", [])
        obj.spin_history = data.get("spin_history", [])

        # --- Casino data ---
        obj.casino_data = data.get("casino_data", obj.casino_data)
        obj.hot_suggestions = data.get("hot_suggestions", "")
        obj.cold_suggestions = data.get("cold_suggestions", "")
        obj.use_casino_winners = data.get("use_casino_winners", False)

        # --- Bankroll / betting ---
        obj.bankroll = data.get("bankroll", 1000)
        obj.initial_bankroll = data.get("initial_bankroll", 1000)
        obj.base_unit = data.get("base_unit", 10)
        obj.stop_loss = data.get("stop_loss", -500)
        obj.stop_win = data.get("stop_win", 200)
        obj.target_profit = data.get("target_profit", 10)
        obj.bet_type = data.get("bet_type", "Even Money")
        obj.progression = data.get("progression", "Martingale")
        obj.current_bet = data.get("current_bet", obj.base_unit)
        obj.next_bet = data.get("next_bet", obj.base_unit)
        obj.progression_state = data.get("progression_state", None)
        obj.consecutive_wins = data.get("consecutive_wins", 0)
        obj.is_stopped = data.get("is_stopped", False)
        obj.message = data.get("message", obj.message)
        obj.status = data.get("status", "Active")
        obj.status_color = data.get("status_color", "white")
        obj.last_dozen_alert_index = data.get("last_dozen_alert_index", -1)
        obj.last_alerted_spins = data.get("last_alerted_spins", None)
        obj.labouchere_sequence = data.get("labouchere_sequence", "")
        obj.victory_vortex_sequence = data.get("victory_vortex_sequence", obj.victory_vortex_sequence)

        # --- Dynamic 17 Assault ---
        obj.d17_list = data.get("d17_list", [])
        obj.d17_locked = data.get("d17_locked", False)

        # --- Sniper ---
        obj.sniper_locked = data.get("sniper_locked", False)
        obj.sniper_locked_misses = data.get("sniper_locked_misses", 0)
        obj.sniper_threshold = data.get("sniper_threshold", 22)

        # --- Top picks / non-repeaters ---
        obj.current_top_picks = data.get("current_top_picks", [])
        obj.previous_top_picks = data.get("previous_top_picks", [])
        obj.stability_counter = data.get("stability_counter", 0)
        obj.nr_last_spin_count = data.get("nr_last_spin_count", 0)

        # --- AIDEA roadmap ---
        obj.aidea_phases = data.get("aidea_phases", [])
        obj.aidea_rules = data.get("aidea_rules", {})
        obj.aidea_current_id = data.get("aidea_current_id", None)
        obj.active_strategy_targets = data.get("active_strategy_targets", [])
        obj.aidea_active_targets = data.get("aidea_active_targets", [])
        obj.aidea_last_result = data.get("aidea_last_result", None)
        obj.aidea_bankroll = data.get("aidea_bankroll", 0.0)
        obj.aidea_phase_repeats = data.get("aidea_phase_repeats", {})
        obj.aidea_unit_multiplier = data.get("aidea_unit_multiplier", 1)

        # --- Trinity ---
        obj.trinity_dozen = data.get("trinity_dozen", "1st Dozen")
        obj.trinity_ds = data.get("trinity_ds", "DS 1-6")
        obj.trinity_corner_nums = data.get("trinity_corner_nums", [1, 2, 4, 5])

        # --- Labouchere ---
        obj.lab_active = data.get("lab_active", False)
        obj.lab_sequence = data.get("lab_sequence", [])
        obj.lab_base = data.get("lab_base", 1.0)
        obj.lab_target = data.get("lab_target", 10.0)
        obj.lab_bankroll = data.get("lab_bankroll", 0.0)
        obj.lab_status = data.get("lab_status", "Waiting to Start")
        obj.lab_mode = data.get("lab_mode", "2 Targets (Dozens/Columns)")
        obj.lab_split_limit = data.get("lab_split_limit", 0.0)

        # --- Statistical intelligence ---
        obj.drought_counters = data.get("drought_counters", obj.drought_counters)
        obj.analysis_window = data.get("analysis_window", 50)

        # --- Step counters ---
        obj.play_specific_numbers_counter = data.get("play_specific_numbers_counter", 0)
        obj.grind_step_index = data.get("grind_step_index", 0)
        obj.grind_last_spin_count = data.get("grind_last_spin_count", 0)
        obj.ramp_step_index = data.get("ramp_step_index", 0)
        obj.ramp_last_spin_count = data.get("ramp_last_spin_count", 0)

        # --- Live Brain ---
        obj.live_brain_active = data.get("live_brain_active", False)
        obj.live_brain_bankroll = data.get("live_brain_bankroll", 100.0)
        obj.live_brain_start_bankroll = data.get("live_brain_start_bankroll", 100.0)
        obj.live_brain_base_unit = data.get("live_brain_base_unit", 0.10)
        obj.live_brain_bets = data.get("live_brain_bets", [])
        obj.live_brain_suggestions_followed = data.get("live_brain_suggestions_followed", 0)
        obj.live_brain_suggestions_total = data.get("live_brain_suggestions_total", 0)
        obj.live_brain_last_suggestion = data.get("live_brain_last_suggestion", "")
        obj.live_brain_auto_follow = data.get("live_brain_auto_follow", False)
        obj.live_brain_auto_size = data.get("live_brain_auto_size", False)
        obj.live_brain_last_confidence = data.get("live_brain_last_confidence", 0)
        obj.live_brain_next_bet_amount = data.get("live_brain_next_bet_amount", 0.10)
        obj.live_brain_custom_progression_name = data.get("live_brain_custom_progression_name", "")
        obj.live_brain_custom_progression_step = data.get("live_brain_custom_progression_step", 0)

        # --- Strategy flags ---
        obj.strategy_sniper_enabled = data.get("strategy_sniper_enabled", False)
        obj.strategy_trinity_enabled = data.get("strategy_trinity_enabled", False)
        obj.strategy_nr_enabled = data.get("strategy_nr_enabled", False)
        obj.strategy_lab_enabled = data.get("strategy_lab_enabled", False)
        obj.strategy_ramp_enabled = data.get("strategy_ramp_enabled", False)
        obj.strategy_grind_enabled = data.get("strategy_grind_enabled", False)

        return obj
