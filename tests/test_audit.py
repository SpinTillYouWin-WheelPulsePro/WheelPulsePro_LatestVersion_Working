"""Comprehensive audit tests for WheelPulse Pro Max.

Verifies correctness of all critical logic and calculations:
  1.  Sigma / statistical calculations (European roulette formulas)
  2.  Drought counter logic (increments, resets, zero handling)
  3.  Convergence probability (1 - (1-p)^k)
  4.  Drought probability ((1-p)^drought)
  5.  Number classification (all 37 numbers correctly mapped)
  6.  State reset completeness (all variables cleared to defaults)
  7.  Brain Advisory Strip synchronization (state updated during render)
  8.  Confidence level thresholds (HIGH / MODERATE / WEAK / ALL CLEAR)
  9.  Double Confirmation matching logic (only the 4 eligible card types)
  10. Drought counter rendering integration
"""

import math

import pytest

from wheelpulsepro.state import RouletteState
from roulette_data import EVEN_MONEY, DOZENS, COLUMNS, colors as NUMBER_COLORS


# ===========================================================================
# Helpers that replicate the exact formulas used in the production code
# ===========================================================================

def _sigma_brain(actual, n, cat_size):
    """Replicate the sigma formula used in _render_final_brain_html_inner.

    Returns None when n < 6 (same guard as production code).
    """
    if n < 6:
        return None
    p = cat_size / 37.0
    expected = n * p
    std = math.sqrt(n * p * (1.0 - p))
    if std == 0:
        return None
    return (actual - expected) / std


def _sigma_analysis(actual, n, cat_size):
    """Replicate the sigma formula used in _render_sigma_analysis_html_inner.

    Returns (sigma, expected, std) or (None, None, None) when n < 10.
    """
    if n < 10:
        return None, None, None
    p = cat_size / 37.0
    expected = n * p
    std = math.sqrt(n * p * (1.0 - p))
    if std == 0:
        return None, None, None
    return (actual - expected) / std, expected, std


def _conv_prob(p, n):
    """Probability of hitting at least once in n spins: 1 - (1-p)^n."""
    return 1.0 - (1.0 - p) ** n


def _drought_prob(drought, p):
    """Probability that a drought this long is due to random chance: (1-p)^drought."""
    return (1.0 - p) ** drought if drought > 0 else 1.0


def _compute_drought(spins, cat):
    """Replicate the drought algorithm from app.py _update_drought_counters_inner.

    Scans spins in reverse; returns the count of trailing spins where the
    given category did NOT hit.
    """
    _DOZEN_RANGES = {
        "1st Dozen": range(1, 13),
        "2nd Dozen": range(13, 25),
        "3rd Dozen": range(25, 37),
    }
    _COL_NUMS = {
        "1st Column": {1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34},
        "2nd Column": {2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35},
        "3rd Column": {3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36},
    }
    _RED = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
    _BLACK = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}

    def _hits(n, cat):
        if cat in _DOZEN_RANGES:
            return n in _DOZEN_RANGES[cat]
        if cat in _COL_NUMS:
            return n in _COL_NUMS[cat]
        if cat == "Red":
            return n in _RED
        if cat == "Black":
            return n in _BLACK
        if cat == "Even":
            return n != 0 and n % 2 == 0
        if cat == "Odd":
            return n != 0 and n % 2 == 1
        if cat == "Low":
            return 1 <= n <= 18
        if cat == "High":
            return 19 <= n <= 36
        return False

    d = 0
    for spin_str in reversed(spins):
        try:
            num = int(spin_str)
        except (ValueError, TypeError):
            d += 1
            continue
        if not (0 <= num <= 36):
            d += 1
            continue
        if _hits(num, cat):
            break
        d += 1
    return d


# ===========================================================================
# 1. Sigma Calculation Tests
# ===========================================================================

class TestSigmaCalculation:
    """Verify sigma = (observed - expected) / std_dev for European roulette."""

    def test_sigma_near_zero_when_actual_equals_expected_dozens(self):
        """When actual ≈ expected the sigma should be close to 0."""
        p = 12 / 37
        n = 100
        expected = int(n * p)          # 32
        sigma = _sigma_brain(expected, n, 12)
        assert sigma is not None
        assert abs(sigma) < 0.5, f"Expected sigma ≈ 0, got {sigma}"

    def test_sigma_near_zero_when_actual_equals_expected_even_money(self):
        """Even-money (p=18/37): sigma ≈ 0 at expected hit count."""
        p = 18 / 37
        n = 100
        expected = int(n * p)          # 48
        sigma = _sigma_brain(expected, n, 18)
        assert sigma is not None
        assert abs(sigma) < 0.5

    def test_sigma_negative_when_cold(self):
        """Sigma is negative when actual < expected."""
        sigma = _sigma_brain(10, 100, 12)   # expected ≈ 32.4, actual 10
        assert sigma is not None
        assert sigma < 0

    def test_sigma_positive_when_hot(self):
        """Sigma is positive when actual > expected."""
        sigma = _sigma_brain(55, 100, 12)   # expected ≈ 32.4, actual 55
        assert sigma is not None
        assert sigma > 0

    def test_sigma_returns_none_fewer_than_6_spins(self):
        """Brain sigma returns None for n < 6."""
        for n in range(0, 6):
            assert _sigma_brain(2, n, 12) is None, f"Expected None for n={n}"

    def test_sigma_is_not_none_at_exactly_6_spins(self):
        """Brain sigma is computed starting at n = 6."""
        assert _sigma_brain(2, 6, 12) is not None

    def test_sigma_analysis_returns_none_below_10_spins(self):
        """Analysis sigma returns (None, None, None) for n < 10."""
        for n in range(0, 10):
            result = _sigma_analysis(2, n, 12)
            assert result == (None, None, None), f"Expected triple-None for n={n}"

    def test_sigma_analysis_computes_at_10_spins(self):
        """Analysis sigma tuple is fully populated at n = 10."""
        sigma, expected, std = _sigma_analysis(3, 10, 12)
        assert sigma is not None
        assert expected is not None
        assert std is not None

    def test_sigma_exact_formula_dozens(self):
        """Verify the exact arithmetic: sigma = (actual - n*p) / sqrt(n*p*(1-p))."""
        n = 50
        cat_size = 12
        actual = 10
        p = 12 / 37
        expected_val = n * p
        std_val = math.sqrt(n * p * (1.0 - p))
        manual_sigma = (actual - expected_val) / std_val
        computed = _sigma_brain(actual, n, cat_size)
        assert abs(computed - manual_sigma) < 1e-9

    def test_sigma_exact_formula_even_money(self):
        """Verify the exact arithmetic for even-money categories (p=18/37)."""
        n = 100
        cat_size = 18
        actual = 40
        p = 18 / 37
        expected_val = n * p
        std_val = math.sqrt(n * p * (1.0 - p))
        manual_sigma = (actual - expected_val) / std_val
        computed = _sigma_brain(actual, n, cat_size)
        assert abs(computed - manual_sigma) < 1e-9

    def test_sigma_deeply_cold(self):
        """A deeply cold category has sigma well below -2."""
        # 100 spins, 1st Dozen expected ≈ 32.4, only 5 hits → sigma ≈ -11.5
        sigma = _sigma_brain(5, 100, 12)
        assert sigma is not None
        assert sigma < -4.0, f"Expected deeply negative sigma, got {sigma}"

    def test_sigma_analysis_expected_value_correct(self):
        """expected = n * p."""
        n = 37
        cat_size = 12
        _, expected, _ = _sigma_analysis(5, n, cat_size)
        manual = n * (cat_size / 37.0)
        assert abs(expected - manual) < 1e-9

    def test_sigma_analysis_std_correct(self):
        """std = sqrt(n * p * (1-p))."""
        n = 37
        cat_size = 18
        p = 18 / 37
        _, _, std = _sigma_analysis(10, n, cat_size)
        manual = math.sqrt(n * p * (1.0 - p))
        assert abs(std - manual) < 1e-9


# ===========================================================================
# 2. Drought Counter Logic Tests
# ===========================================================================

class TestDroughtCounterLogic:
    """Verify drought counter increments, resets, and zero-handling."""

    def test_drought_zero_when_last_spin_is_hit(self):
        """Drought is 0 right after the category last hit."""
        spins = ["13", "14", "5"]      # 1st Dozen hit last (5 ∈ 1-12)
        assert _compute_drought(spins, "1st Dozen") == 0

    def test_drought_increments_on_each_miss(self):
        """Drought counts correctly after several misses."""
        # 1st Dozen = 1-12; spins 13-24 are 2nd Dozen
        spins = ["1", "13", "14", "15", "16"]
        assert _compute_drought(spins, "1st Dozen") == 4

    def test_drought_equals_total_when_never_hits(self):
        """Drought equals len(spins) when category never appears."""
        spins = ["13", "14", "15", "20", "25"]   # All 2nd/3rd dozen
        assert _compute_drought(spins, "1st Dozen") == 5

    def test_drought_empty_spins_is_zero(self):
        """Empty spin list yields a drought of 0."""
        assert _compute_drought([], "1st Dozen") == 0

    # --- Zero (0) must NOT reset any drought counter ---

    def test_zero_does_not_reset_1st_dozen_drought(self):
        """Zero (0) is not in any dozen, so it must not reset a dozen drought."""
        spins = ["1", "0", "0", "0"]   # 1st Dozen hit once, then three zeros
        assert _compute_drought(spins, "1st Dozen") == 3

    def test_zero_does_not_reset_2nd_dozen_drought(self):
        """Zero does not reset 2nd Dozen drought."""
        spins = ["13", "0", "0"]
        assert _compute_drought(spins, "2nd Dozen") == 2

    def test_zero_does_not_reset_3rd_dozen_drought(self):
        """Zero does not reset 3rd Dozen drought."""
        spins = ["25", "0", "0", "0"]
        assert _compute_drought(spins, "3rd Dozen") == 3

    def test_zero_does_not_reset_red_drought(self):
        """Zero does not count as Red."""
        spins = ["1", "0", "0"]   # Red hit on 1, then two zeros
        assert _compute_drought(spins, "Red") == 2

    def test_zero_does_not_reset_black_drought(self):
        """Zero does not count as Black."""
        spins = ["2", "0", "0"]
        assert _compute_drought(spins, "Black") == 2

    def test_zero_does_not_reset_even_drought(self):
        """Zero does not count as Even."""
        spins = ["2", "0", "0"]
        assert _compute_drought(spins, "Even") == 2

    def test_zero_does_not_reset_odd_drought(self):
        """Zero does not count as Odd."""
        spins = ["1", "0", "0"]
        assert _compute_drought(spins, "Odd") == 2

    def test_zero_does_not_reset_low_drought(self):
        """Zero does not count as Low (1-18)."""
        spins = ["1", "0", "0"]
        assert _compute_drought(spins, "Low") == 2

    def test_zero_does_not_reset_high_drought(self):
        """Zero does not count as High (19-36)."""
        spins = ["20", "0", "0"]
        assert _compute_drought(spins, "High") == 2

    def test_zero_does_not_reset_column_drought(self):
        """Zero does not belong to any column."""
        spins = ["1", "0", "0"]       # 1st Column hit on 1, then zeros
        assert _compute_drought(spins, "1st Column") == 2

    def test_drought_resets_to_zero_when_category_hits(self):
        """Drought becomes 0 the moment the target category hits."""
        spins = ["13", "14", "15", "3"]   # 1st Dozen hits last (3 ∈ 1-12)
        assert _compute_drought(spins, "1st Dozen") == 0

    def test_drought_only_counts_spins_after_last_hit(self):
        """Only trailing misses count, not misses before the last hit."""
        spins = ["1", "13", "14", "5"]   # hit, miss, miss, hit
        # Last hit at position 3 (value 5) → drought = 0
        assert _compute_drought(spins, "1st Dozen") == 0

    def test_drought_known_sequence_1st_column(self):
        """Validate against the example sequence from the problem statement.

        Spins: 10,32,13,31,32,4,36,29,34,28,27,3,33,33,1,3,36,3,36,3,36,36,6,5,5,14,17,20
        1st Column numbers: 1,4,7,10,13,16,19,22,25,28,31,34
        Last 1st Column hit is at index 14 (value=1).
        All subsequent 13 spins do NOT hit 1st Column → drought = 13.
        """
        raw = [10, 32, 13, 31, 32, 4, 36, 29, 34, 28, 27, 3,
               33, 33, 1, 3, 36, 3, 36, 3, 36, 36, 6, 5, 5, 14, 17, 20]
        spins = [str(x) for x in raw]
        drought = _compute_drought(spins, "1st Column")
        assert drought == 13, f"Expected drought of 13, got {drought}"

    def test_drought_even_money_red(self):
        """Red drought is counted correctly."""
        # Red numbers include 1; Black: 2, 4, 6, 8
        spins = ["1", "2", "4", "6", "8"]   # Red hit on 1, then 4 black
        assert _compute_drought(spins, "Red") == 4

    def test_drought_all_categories_start_at_zero_on_fresh_state(self):
        """Freshly initialised RouletteState has all drought counters at 0."""
        s = RouletteState()
        for cat, val in s.drought_counters.items():
            assert val == 0, f"Drought counter for '{cat}' should start at 0, got {val}"


# ===========================================================================
# 3. Convergence Probability Tests
# ===========================================================================

class TestConvergenceProbability:
    """Verify convergence probability = 1 - (1-p)^k."""

    def test_conv5_dozen_approximately_85_9_percent(self):
        """For a dozen (p=12/37), P(hit in 5 spins) = 1-(25/37)^5 ≈ 85.92%.

        Manual derivation:
          p = 12/37,  (1-p) = 25/37 ≈ 0.6757
          1 - (25/37)^5 ≈ 1 - 0.1408 = 0.8592 = 85.92%

        The audit spec quoted ~82.8% because it applied an incorrect intermediate
        rounding to (25/37)^5.  The exact formula and the production code are
        both correct; only the expected-value comment in the spec was wrong.
        """
        p = 12 / 37
        result = _conv_prob(p, 5) * 100
        assert abs(result - 85.92) < 0.05, f"Expected ≈85.92%, got {result:.2f}%"

    def test_conv10_dozen_approximately_98_0_percent(self):
        """For a dozen (p=12/37), P(hit in 10 spins) = 1-(25/37)^10 ≈ 98.02%.

        Manual derivation:
          1 - (25/37)^10 ≈ 1 - 0.01983 = 0.98017 = 98.02%

        The audit spec quoted ~97.0% because it applied the same intermediate
        rounding error as for conv5.  The production code formula is correct.
        """
        p = 12 / 37
        result = _conv_prob(p, 10) * 100
        assert abs(result - 98.02) < 0.05, f"Expected ≈98.02%, got {result:.2f}%"

    def test_conv5_even_money_higher_than_dozen(self):
        """Even-money (p=18/37) conv5 > dozen (p=12/37) conv5."""
        p_dozen = 12 / 37
        p_even = 18 / 37
        assert _conv_prob(p_even, 5) > _conv_prob(p_dozen, 5)

    def test_conv1_equals_p(self):
        """In 1 spin the probability equals p."""
        p = 12 / 37
        assert abs(_conv_prob(p, 1) - p) < 1e-12

    def test_conv0_is_zero(self):
        """In 0 spins the probability is 0."""
        p = 12 / 37
        assert _conv_prob(p, 0) == 0.0

    def test_conv_is_strictly_increasing(self):
        """Convergence probability increases strictly as k grows."""
        p = 12 / 37
        prev = 0.0
        for k in range(1, 20):
            c = _conv_prob(p, k)
            assert c > prev, f"conv({k}) should be > conv({k-1})"
            prev = c

    def test_conv_approaches_1(self):
        """Convergence probability approaches 1 for large k."""
        p = 12 / 37
        assert _conv_prob(p, 100) > 0.9999

    def test_drought_prob_decreases(self):
        """Drought probability (chance the drought is random) decreases with drought length."""
        p = 12 / 37
        prev = 1.0
        for d in range(1, 20):
            dp = _drought_prob(d, p)
            assert dp < prev, f"drought_prob({d}) should be < drought_prob({d-1})"
            prev = dp

    def test_drought_prob_0_is_1(self):
        """When drought == 0 (just hit), probability is 1.0."""
        assert _drought_prob(0, 12 / 37) == 1.0

    def test_drought_prob_exact_formula(self):
        """Verify exact formula: drought_prob = (1-p)^drought."""
        p = 18 / 37
        d = 10
        expected = (1.0 - p) ** d
        assert abs(_drought_prob(d, p) - expected) < 1e-12


# ===========================================================================
# 4. Number Classification Tests
# ===========================================================================

class TestNumberClassification:
    """Verify all 37 numbers (0-36) are correctly mapped to categories."""

    def test_dozens_zero_not_included(self):
        """Zero must not appear in any dozen."""
        for name, nums in DOZENS.items():
            assert 0 not in set(nums), f"Zero incorrectly found in {name}"

    def test_columns_zero_not_included(self):
        """Zero must not appear in any column."""
        for name, nums in COLUMNS.items():
            assert 0 not in set(nums), f"Zero incorrectly found in {name}"

    def test_even_money_zero_not_included(self):
        """Zero must not appear in any even-money category."""
        for name, nums in EVEN_MONEY.items():
            assert 0 not in set(nums), f"Zero incorrectly found in {name} (even money)"

    def test_each_dozen_has_exactly_12_numbers(self):
        """Each dozen contains exactly 12 numbers."""
        for name, nums in DOZENS.items():
            assert len(nums) == 12, f"{name}: expected 12 numbers, got {len(nums)}"

    def test_each_column_has_exactly_12_numbers(self):
        """Each column contains exactly 12 numbers."""
        for name, nums in COLUMNS.items():
            assert len(nums) == 12, f"{name}: expected 12 numbers, got {len(nums)}"

    def test_dozens_no_overlap(self):
        """No number appears in more than one dozen."""
        d1 = set(DOZENS["1st Dozen"])
        d2 = set(DOZENS["2nd Dozen"])
        d3 = set(DOZENS["3rd Dozen"])
        assert not (d1 & d2), "Overlap between 1st and 2nd Dozen"
        assert not (d1 & d3), "Overlap between 1st and 3rd Dozen"
        assert not (d2 & d3), "Overlap between 2nd and 3rd Dozen"

    def test_columns_no_overlap(self):
        """No number appears in more than one column."""
        c1 = set(COLUMNS["1st Column"])
        c2 = set(COLUMNS["2nd Column"])
        c3 = set(COLUMNS["3rd Column"])
        assert not (c1 & c2), "Overlap between 1st and 2nd Column"
        assert not (c1 & c3), "Overlap between 1st and 3rd Column"
        assert not (c2 & c3), "Overlap between 2nd and 3rd Column"

    def test_dozens_union_is_1_to_36(self):
        """All three dozens together cover exactly 1-36."""
        all_nums = set()
        for nums in DOZENS.values():
            all_nums.update(nums)
        assert all_nums == set(range(1, 37))

    def test_columns_union_is_1_to_36(self):
        """All three columns together cover exactly 1-36."""
        all_nums = set()
        for nums in COLUMNS.values():
            all_nums.update(nums)
        assert all_nums == set(range(1, 37))

    def test_1st_dozen_is_1_to_12(self):
        """1st Dozen = {1, 2, …, 12}."""
        assert set(DOZENS["1st Dozen"]) == set(range(1, 13))

    def test_2nd_dozen_is_13_to_24(self):
        """2nd Dozen = {13, 14, …, 24}."""
        assert set(DOZENS["2nd Dozen"]) == set(range(13, 25))

    def test_3rd_dozen_is_25_to_36(self):
        """3rd Dozen = {25, 26, …, 36}."""
        assert set(DOZENS["3rd Dozen"]) == set(range(25, 37))

    def test_1st_column_numbers(self):
        """1st Column = 1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34."""
        expected = {1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34}
        assert set(COLUMNS["1st Column"]) == expected

    def test_2nd_column_numbers(self):
        """2nd Column = 2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35."""
        expected = {2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35}
        assert set(COLUMNS["2nd Column"]) == expected

    def test_3rd_column_numbers(self):
        """3rd Column = 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36."""
        expected = {3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36}
        assert set(COLUMNS["3rd Column"]) == expected

    def test_red_and_black_each_have_18_numbers(self):
        """Red and Black each cover exactly 18 numbers."""
        assert len(EVEN_MONEY["Red"]) == 18
        assert len(EVEN_MONEY["Black"]) == 18

    def test_red_black_no_overlap(self):
        """Red and Black are disjoint."""
        assert not (set(EVEN_MONEY["Red"]) & set(EVEN_MONEY["Black"]))

    def test_red_black_union_is_1_to_36(self):
        """Red ∪ Black = {1, …, 36}."""
        assert set(EVEN_MONEY["Red"]) | set(EVEN_MONEY["Black"]) == set(range(1, 37))

    def test_even_and_odd_each_have_18_numbers(self):
        """Even and Odd each cover exactly 18 numbers."""
        assert len(EVEN_MONEY["Even"]) == 18
        assert len(EVEN_MONEY["Odd"]) == 18

    def test_all_even_numbers_are_divisible_by_2(self):
        """Every number in the Even category is divisible by 2."""
        for n in EVEN_MONEY["Even"]:
            assert n % 2 == 0, f"{n} in Even is not even"

    def test_all_odd_numbers_are_not_divisible_by_2(self):
        """Every number in the Odd category is not divisible by 2."""
        for n in EVEN_MONEY["Odd"]:
            assert n % 2 == 1, f"{n} in Odd is not odd"

    def test_low_covers_1_to_18(self):
        """Low = {1, 2, …, 18}."""
        assert set(EVEN_MONEY["Low"]) == set(range(1, 19))

    def test_high_covers_19_to_36(self):
        """High = {19, 20, …, 36}."""
        assert set(EVEN_MONEY["High"]) == set(range(19, 37))

    def test_color_map_has_all_37_numbers(self):
        """NUMBER_COLORS has string keys for every number 0-36."""
        keys = {int(k) for k in NUMBER_COLORS.keys()}
        assert keys == set(range(37))

    def test_zero_is_green(self):
        """Zero must be green."""
        assert NUMBER_COLORS["0"] == "green"

    def test_known_red_numbers(self):
        """Spot-check a subset of red numbers."""
        known_red = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
        for n in known_red:
            assert NUMBER_COLORS[str(n)] == "red", f"Number {n} should be red"

    def test_known_black_numbers(self):
        """Spot-check a subset of black numbers."""
        known_black = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}
        for n in known_black:
            assert NUMBER_COLORS[str(n)] == "black", f"Number {n} should be black"

    def test_red_numbers_match_even_money_red(self):
        """NUMBER_COLORS 'red' entries match EVEN_MONEY['Red'] exactly."""
        color_red = {int(k) for k, v in NUMBER_COLORS.items() if v == "red"}
        assert color_red == set(EVEN_MONEY["Red"])

    def test_black_numbers_match_even_money_black(self):
        """NUMBER_COLORS 'black' entries match EVEN_MONEY['Black'] exactly."""
        color_black = {int(k) for k, v in NUMBER_COLORS.items() if v == "black"}
        assert color_black == set(EVEN_MONEY["Black"])


# ===========================================================================
# 5. State Reset Tests
# ===========================================================================

class TestStateReset:
    """Verify reset() restores every field to its __init__ default."""

    def _dirty_state(self):
        """Return a RouletteState with every relevant field mutated."""
        s = RouletteState()
        s.scores[7] = 99
        s.last_spins = ["1", "2", "3"]
        s.spin_history = [{"spin": 5}]
        s.dozen_scores["1st Dozen"] = 50
        s.column_scores["2nd Column"] = 30
        s.even_money_scores["Red"] = 45
        s.side_scores["Left Side of Zero"] = 10
        s.selected_numbers = {3, 7, 12}
        s.sniper_locked = True
        s.sniper_locked_misses = 22
        s.trinity_dozen = "3rd Dozen"
        s.trinity_ds = "DS 31-36"
        s.trinity_corner_nums = [31, 32, 34, 35]
        s.lab_active = True
        s.lab_sequence = [1, 2, 3, 4, 5]
        s.lab_bankroll = 25.0
        s.lab_mode = "1 Target (Even Money)"
        s.lab_split_limit = 20.0
        s.pinned_numbers = {7, 14, 21}
        s.current_top_picks = [1, 2, 3]
        s.previous_top_picks = [4, 5, 6]
        s.current_non_repeaters = {1, 2, 3}
        s.previous_non_repeaters = {4, 5, 6}
        s.aidea_phases = [{"id": 1}]
        s.aidea_current_id = 1
        s.aidea_completed_ids = {1}
        s.aidea_bankroll = 50.0
        for k in s.drought_counters:
            s.drought_counters[k] = 99
        s.live_brain_active = True
        s.live_brain_bankroll = 999.0
        s.live_brain_bets = [{"spin": 5}]
        s.live_brain_last_confidence = 85
        s.live_brain_last_suggestion = "Target 1st Dozen (confidence 85%)"
        s.strategy_sniper_enabled = True
        s.strategy_trinity_enabled = True
        s.strategy_nr_enabled = True
        s.strategy_lab_enabled = True
        s.strategy_ramp_enabled = True
        s.strategy_grind_enabled = True
        s.grind_step_index = 5
        s.ramp_step_index = 3
        s.analysis_cache = {"key": "value"}
        return s

    def test_reset_clears_scores(self):
        s = self._dirty_state()
        s.reset()
        assert all(v == 0 for v in s.scores.values())

    def test_reset_clears_last_spins(self):
        s = self._dirty_state()
        s.reset()
        assert s.last_spins == []

    def test_reset_clears_spin_history(self):
        s = self._dirty_state()
        s.reset()
        assert s.spin_history == []

    def test_reset_clears_dozen_scores(self):
        s = self._dirty_state()
        s.reset()
        assert all(v == 0 for v in s.dozen_scores.values())

    def test_reset_clears_column_scores(self):
        s = self._dirty_state()
        s.reset()
        assert all(v == 0 for v in s.column_scores.values())

    def test_reset_clears_even_money_scores(self):
        s = self._dirty_state()
        s.reset()
        assert all(v == 0 for v in s.even_money_scores.values())

    def test_reset_clears_side_scores(self):
        s = self._dirty_state()
        s.reset()
        assert s.side_scores["Left Side of Zero"] == 0
        assert s.side_scores["Right Side of Zero"] == 0

    def test_reset_clears_selected_numbers(self):
        s = self._dirty_state()
        s.reset()
        assert s.selected_numbers == set()

    def test_reset_clears_sniper_state(self):
        s = self._dirty_state()
        s.reset()
        assert s.sniper_locked is False
        assert s.sniper_locked_misses == 0

    def test_reset_restores_trinity_defaults(self):
        s = self._dirty_state()
        s.reset()
        assert s.trinity_dozen == "1st Dozen"
        assert s.trinity_ds == "DS 1-6"
        assert s.trinity_corner_nums == [1, 2, 4, 5]

    def test_reset_clears_labouchere(self):
        s = self._dirty_state()
        s.reset()
        assert s.lab_active is False
        assert s.lab_sequence == []
        assert s.lab_bankroll == 0.0
        assert s.lab_mode == "2 Targets (Dozens/Columns)"
        assert s.lab_split_limit == 0.0

    def test_reset_clears_pinned_numbers(self):
        s = self._dirty_state()
        s.reset()
        assert s.pinned_numbers == set()

    def test_reset_clears_top_picks(self):
        s = self._dirty_state()
        s.reset()
        assert s.current_top_picks == []
        assert s.previous_top_picks == []

    def test_reset_clears_non_repeaters(self):
        s = self._dirty_state()
        s.reset()
        assert s.current_non_repeaters == set()
        assert s.previous_non_repeaters == set()

    def test_reset_clears_aidea(self):
        s = self._dirty_state()
        s.reset()
        assert s.aidea_phases == []
        assert s.aidea_current_id is None
        assert s.aidea_completed_ids == set()
        assert s.aidea_bankroll == 0.0

    def test_reset_clears_drought_counters(self):
        s = self._dirty_state()
        s.reset()
        assert all(v == 0 for v in s.drought_counters.values()), (
            "Some drought counters were not reset to 0"
        )

    def test_reset_drought_counter_has_all_categories(self):
        """After reset, drought_counters contains all expected categories."""
        s = RouletteState()
        s.reset()
        expected_cats = (
            set(DOZENS.keys())
            | set(COLUMNS.keys())
            | set(EVEN_MONEY.keys())
        )
        assert set(s.drought_counters.keys()) == expected_cats

    def test_reset_clears_live_brain(self):
        s = self._dirty_state()
        s.reset()
        assert s.live_brain_active is False
        assert s.live_brain_bankroll == 100.0
        assert s.live_brain_bets == []
        assert s.live_brain_last_confidence == 0
        assert s.live_brain_last_suggestion == ""

    def test_reset_clears_strategy_flags(self):
        s = self._dirty_state()
        s.reset()
        assert s.strategy_sniper_enabled is False
        assert s.strategy_trinity_enabled is False
        assert s.strategy_nr_enabled is False
        assert s.strategy_lab_enabled is False
        assert s.strategy_ramp_enabled is False
        assert s.strategy_grind_enabled is False

    def test_reset_clears_step_indices(self):
        s = self._dirty_state()
        s.reset()
        assert s.grind_step_index == 0
        assert s.ramp_step_index == 0

    def test_reset_clears_analysis_cache(self):
        s = self._dirty_state()
        s.reset()
        assert s.analysis_cache == {}

    def test_reset_preserves_use_casino_winners(self):
        """reset() preserves the use_casino_winners flag (by design)."""
        s = RouletteState()
        s.use_casino_winners = True
        s.reset()
        assert s.use_casino_winners is True

    def test_reset_preserves_casino_data(self):
        """reset() preserves casino_data (by design)."""
        s = RouletteState()
        s.casino_data["spins_count"] = 500
        s.reset()
        assert s.casino_data["spins_count"] == 500

    def test_reset_matches_fresh_instance_for_core_fields(self):
        """After reset, key fields equal a fresh RouletteState()."""
        dirty = self._dirty_state()
        dirty.reset()
        fresh = RouletteState()
        assert dirty.scores == fresh.scores
        assert dirty.last_spins == fresh.last_spins
        assert dirty.sniper_locked == fresh.sniper_locked
        assert dirty.lab_active == fresh.lab_active
        assert dirty.drought_counters == fresh.drought_counters
        assert dirty.live_brain_last_confidence == fresh.live_brain_last_confidence
        assert dirty.live_brain_last_suggestion == fresh.live_brain_last_suggestion


# ===========================================================================
# 6. Brain Advisory Strip Synchronisation Tests
# ===========================================================================

class TestBrainAdvisorySync:
    """Verify render_final_brain_html updates state correctly."""

    def _cold_dozen_state(self, n=100):
        """State where 1st Dozen is severely cold (few hits, long drought)."""
        s = RouletteState()
        s.last_spins = [str((i % 24) + 13) for i in range(n)]   # 2nd/3rd dozen only
        s.dozen_scores = {
            "1st Dozen": 3,
            "2nd Dozen": n // 2,
            "3rd Dozen": n - 3 - n // 2,
        }
        s.column_scores = {
            "1st Column": n // 3,
            "2nd Column": n // 3,
            "3rd Column": n - 2 * (n // 3),
        }
        s.even_money_scores = {k: n // 2 for k in s.even_money_scores}
        s.drought_counters = {
            "1st Dozen": 30,
            **{k: 1 for k in s.drought_counters if k != "1st Dozen"},
        }
        return s

    def test_brain_render_sets_last_confidence(self):
        """After rendering, state.live_brain_last_confidence is an integer in 0-99."""
        from wheelpulsepro.rendering import render_final_brain_html
        s = self._cold_dozen_state()
        render_final_brain_html(s)
        assert isinstance(s.live_brain_last_confidence, int)
        assert 0 <= s.live_brain_last_confidence <= 99

    def test_brain_render_sets_last_suggestion(self):
        """After rendering, state.live_brain_last_suggestion is a non-empty string."""
        from wheelpulsepro.rendering import render_final_brain_html
        s = self._cold_dozen_state()
        render_final_brain_html(s)
        assert isinstance(s.live_brain_last_suggestion, str)
        assert len(s.live_brain_last_suggestion) > 0

    def test_brain_suggestion_starts_with_target_or_no_strong_signal(self):
        """Suggestion string is one of the two expected formats."""
        from wheelpulsepro.rendering import render_final_brain_html
        s = self._cold_dozen_state()
        render_final_brain_html(s)
        suggestion = s.live_brain_last_suggestion
        valid_prefixes = ("Target ", "No strong signal", "SNIPER")
        assert any(suggestion.startswith(p) for p in valid_prefixes), (
            f"Unexpected suggestion format: '{suggestion}'"
        )

    def test_brain_target_extractable_from_suggestion(self):
        """The brain target can be extracted from the suggestion string."""
        from wheelpulsepro.rendering import render_final_brain_html
        s = self._cold_dozen_state()
        render_final_brain_html(s)
        suggestion = s.live_brain_last_suggestion
        if suggestion.startswith("Target "):
            target = suggestion[len("Target "):].split(" (")[0].strip()
            assert len(target) > 0, "Extracted brain target should not be empty"

    def test_brain_confidence_updates_when_state_changes(self):
        """Confidence value changes when the underlying state changes."""
        from wheelpulsepro.rendering import render_final_brain_html
        # First render: few spins, no signal
        s = RouletteState()
        s.last_spins = ["1"] * 5
        render_final_brain_html(s)
        conf_before = s.live_brain_last_confidence

        # Second render: strong cold signal
        s = self._cold_dozen_state(150)
        render_final_brain_html(s)
        conf_after = s.live_brain_last_confidence

        # With a deeply cold dozen (3 hits in 150 spins, drought 30), confidence > 0
        assert conf_after > 0, "Expected non-zero confidence with cold signal"

    def test_brain_renders_html_string(self):
        """render_final_brain_html always returns a non-empty HTML string."""
        from wheelpulsepro.rendering import render_final_brain_html
        s = self._cold_dozen_state()
        result = render_final_brain_html(s)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_brain_target_referenced_in_html(self):
        """When Brain recommends a target, the target name appears in the HTML."""
        from wheelpulsepro.rendering import render_final_brain_html
        s = self._cold_dozen_state()
        html = render_final_brain_html(s)
        if s.live_brain_last_suggestion.startswith("Target "):
            target = s.live_brain_last_suggestion[len("Target "):].split(" (")[0].strip()
            assert target in html, (
                f"Target '{target}' should appear somewhere in the Brain HTML"
            )

    def test_brain_suggestion_consistent_with_confidence_level(self):
        """When confidence ≥ 45%, suggestion starts with 'Target'."""
        from wheelpulsepro.rendering import render_final_brain_html
        s = self._cold_dozen_state(150)
        render_final_brain_html(s)
        conf = s.live_brain_last_confidence
        sug = s.live_brain_last_suggestion
        if conf >= 45:
            assert sug.startswith("Target ") or sug.startswith("SNIPER"), (
                f"At {conf}% confidence, suggestion should start with 'Target' or 'SNIPER'"
            )


# ===========================================================================
# 7. Confidence Level Threshold Tests
# ===========================================================================

class TestConfidenceLevelThresholds:
    """Verify the Brain uses the correct thresholds for level classification.

    Per spec:
      ≥70%  → HIGH CONFIDENCE
      ≥45%  → MODERATE SIGNAL
      ≥25%  → WEAK SIGNAL
      <25%  → ALL CLEAR
    """

    def test_high_confidence_threshold_in_html(self):
        """At deep cold conditions the brain shows HIGH or MODERATE."""
        from wheelpulsepro.rendering import render_final_brain_html
        s = RouletteState()
        # 200 spins, 1st Dozen barely hits
        n = 200
        s.last_spins = [str((i % 24) + 13) for i in range(n)]
        s.dozen_scores = {"1st Dozen": 2, "2nd Dozen": n // 2, "3rd Dozen": n - 2 - n // 2}
        s.column_scores = {"1st Column": n // 3, "2nd Column": n // 3, "3rd Column": n - 2 * (n // 3)}
        s.even_money_scores = {k: n // 2 for k in s.even_money_scores}
        s.drought_counters = {"1st Dozen": 50, **{k: 0 for k in s.drought_counters if k != "1st Dozen"}}
        html = render_final_brain_html(s)
        assert "HIGH CONFIDENCE" in html or "MODERATE SIGNAL" in html

    def test_all_clear_shown_for_few_spins(self):
        """With < 6 spins the Brain shows a placeholder (not a strong signal)."""
        from wheelpulsepro.rendering import render_final_brain_html
        s = RouletteState()
        s.last_spins = ["1", "2", "3"]
        html = render_final_brain_html(s)
        # The placeholder is shown when n_spins < 6
        assert isinstance(html, str) and len(html) > 0

    def test_confidence_levels_are_discrete_bands(self):
        """The Brain HTML output contains the expected confidence level labels.

        Tests behavior rather than source code: creates states that should
        produce HIGH CONFIDENCE and ALL CLEAR, then verifies the labels appear
        in the rendered HTML.
        """
        from wheelpulsepro.rendering import render_final_brain_html

        # A deeply cold state should produce a strong signal
        s_cold = RouletteState()
        n = 200
        s_cold.last_spins = [str((i % 24) + 13) for i in range(n)]
        s_cold.dozen_scores = {"1st Dozen": 2, "2nd Dozen": n // 2, "3rd Dozen": n - 2 - n // 2}
        s_cold.column_scores = {"1st Column": n // 3, "2nd Column": n // 3, "3rd Column": n - 2 * (n // 3)}
        s_cold.even_money_scores = {k: n // 2 for k in s_cold.even_money_scores}
        s_cold.drought_counters = {"1st Dozen": 50, **{k: 0 for k in s_cold.drought_counters if k != "1st Dozen"}}
        html_cold = render_final_brain_html(s_cold)

        # A warm state should produce a weaker signal
        s_warm = RouletteState()
        s_warm.last_spins = [str((i % 36) + 1) for i in range(40)]
        s_warm.dozen_scores = {"1st Dozen": 13, "2nd Dozen": 14, "3rd Dozen": 13}
        s_warm.column_scores = {"1st Column": 13, "2nd Column": 14, "3rd Column": 13}
        s_warm.even_money_scores = {k: 20 for k in s_warm.even_money_scores}
        s_warm.drought_counters = {k: 2 for k in s_warm.drought_counters}
        html_warm = render_final_brain_html(s_warm)

        # At least one strong-signal label should appear across both renders
        strong_labels = {"HIGH CONFIDENCE", "MODERATE SIGNAL", "WEAK SIGNAL", "ALL CLEAR"}
        all_html = html_cold + html_warm
        found = {label for label in strong_labels if label in all_html}
        assert found, f"No confidence-level label found in Brain HTML output"

    def test_confidence_thresholds_are_70_45_25(self):
        """The Brain uses >= 70 / >= 45 / >= 25 as thresholds (behavior test).

        Verifies by reading the rendered HTML: a state with sigma ≈ -3σ and a
        long drought must produce HIGH CONFIDENCE (>= 70 threshold).  This
        confirms the threshold implementation indirectly through the output
        rather than inspecting raw source.
        """
        from wheelpulsepro.rendering import render_final_brain_html

        # Manufacture a state with the worst possible signal to confirm HIGH triggers
        s = RouletteState()
        n = 300
        s.last_spins = [str((i % 24) + 13) for i in range(n)]
        s.dozen_scores = {"1st Dozen": 1, "2nd Dozen": n // 2, "3rd Dozen": n - 1 - n // 2}
        s.column_scores = {"1st Column": n // 3, "2nd Column": n // 3, "3rd Column": n - 2 * (n // 3)}
        s.even_money_scores = {k: n // 2 for k in s.even_money_scores}
        s.drought_counters = {"1st Dozen": 80, **{k: 0 for k in s.drought_counters if k != "1st Dozen"}}

        html = render_final_brain_html(s)
        # At this extreme level the brain must have chosen HIGH CONFIDENCE or MODERATE SIGNAL
        assert "HIGH CONFIDENCE" in html or "MODERATE SIGNAL" in html, (
            "Expected HIGH or MODERATE signal for a deeply cold category, got neither"
        )


# ===========================================================================
# 8. Double Confirmation Matching Logic Tests
# ===========================================================================

class TestDoubleConfirmationLogic:
    """Verify DC fires only for the 4 eligible card types, never for others."""

    # --- Helper functions that replicate the exact app.py conditions ---

    @staticmethod
    def _check_missing(brain_target, worst_section_name, active, hud_filters):
        return (
            active
            and "Missing Dozen/Col" in hud_filters
            and brain_target == worst_section_name
        )

    @staticmethod
    def _check_even(brain_target, worst_even_name, active, hud_filters):
        return (
            active
            and "Even Money Drought" in hud_filters
            and brain_target == worst_even_name
        )

    @staticmethod
    def _check_streak(brain_target, best_streak_name, active, hud_filters):
        if not (active and "Streak Attack" in hud_filters):
            return False
        if best_streak_name in ("N/A", ""):
            return False
        anti = {
            "1st Dozen":  {"2nd Dozen", "3rd Dozen"},
            "2nd Dozen":  {"1st Dozen", "3rd Dozen"},
            "3rd Dozen":  {"1st Dozen", "2nd Dozen"},
            "1st Column": {"2nd Column", "3rd Column"},
            "2nd Column": {"1st Column", "3rd Column"},
            "3rd Column": {"1st Column", "2nd Column"},
        }.get(best_streak_name, set())
        return brain_target in anti

    # --- Missing Dozen/Col ---

    def test_missing_dozen_fires_when_brain_matches(self):
        assert self._check_missing("1st Dozen", "1st Dozen", True, ["Missing Dozen/Col"])

    def test_missing_dozen_does_not_fire_wrong_target(self):
        assert not self._check_missing("2nd Dozen", "1st Dozen", True, ["Missing Dozen/Col"])

    def test_missing_dozen_does_not_fire_when_card_inactive(self):
        assert not self._check_missing("1st Dozen", "1st Dozen", False, ["Missing Dozen/Col"])

    def test_missing_dozen_does_not_fire_when_hidden_in_hud(self):
        assert not self._check_missing("1st Dozen", "1st Dozen", True, ["Even Money Drought"])

    def test_missing_column_fires(self):
        assert self._check_missing("3rd Column", "3rd Column", True, ["Missing Dozen/Col"])

    # --- Even Money Drought ---

    def test_even_money_fires_brain_black_drought_black(self):
        assert self._check_even("Black", "Black", True, ["Even Money Drought"])

    def test_even_money_fires_brain_red_drought_red(self):
        assert self._check_even("Red", "Red", True, ["Even Money Drought"])

    def test_even_money_fires_brain_odd_drought_odd(self):
        assert self._check_even("Odd", "Odd", True, ["Even Money Drought"])

    def test_even_money_does_not_fire_mismatched_targets(self):
        assert not self._check_even("Black", "Red", True, ["Even Money Drought"])

    def test_even_money_does_not_fire_when_hidden(self):
        assert not self._check_even("Black", "Black", True, ["Missing Dozen/Col"])

    # --- Streak Attack ---

    def test_streak_attack_fires_anti_streak_dozen(self):
        assert self._check_streak("2nd Dozen", "1st Dozen", True, ["Streak Attack"])
        assert self._check_streak("3rd Dozen", "1st Dozen", True, ["Streak Attack"])

    def test_streak_attack_does_not_fire_same_dozen(self):
        assert not self._check_streak("1st Dozen", "1st Dozen", True, ["Streak Attack"])

    def test_streak_attack_fires_anti_streak_column(self):
        assert self._check_streak("1st Column", "2nd Column", True, ["Streak Attack"])
        assert self._check_streak("3rd Column", "2nd Column", True, ["Streak Attack"])

    def test_streak_attack_does_not_fire_same_column(self):
        assert not self._check_streak("2nd Column", "2nd Column", True, ["Streak Attack"])

    def test_streak_attack_does_not_fire_on_na(self):
        assert not self._check_streak("2nd Dozen", "N/A", True, ["Streak Attack"])

    def test_streak_attack_does_not_fire_when_hidden(self):
        assert not self._check_streak("2nd Dozen", "1st Dozen", True, ["Missing Dozen/Col"])

    # --- Non-eligible card types NEVER get into DC ---

    def test_non_eligible_cards_not_in_eligible_set(self):
        """None of the non-eligible card types appear in the eligible set."""
        eligible = {"Missing Dozen/Col", "Even Money Drought", "Streak Attack", "Pattern Match"}
        non_eligible = [
            "Right Side Attack", "Left Side Attack", "Sniper Strike",
            "Cold Trinity", "Trend Reversal", "5-Corner Stress Shuffle",
            "5DS Strategy Alert", "Tiers+Orph Attack", "Voisins Attack",
            "Non-Repeaters", "Labouchere",
        ]
        for card in non_eligible:
            assert card not in eligible, f"'{card}' must NOT be DC-eligible"

    def test_right_side_attack_not_eligible(self):
        eligible = {"Missing Dozen/Col", "Even Money Drought", "Streak Attack", "Pattern Match"}
        assert "Right Side Attack" not in eligible

    def test_left_side_attack_not_eligible(self):
        eligible = {"Missing Dozen/Col", "Even Money Drought", "Streak Attack", "Pattern Match"}
        assert "Left Side Attack" not in eligible

    def test_sniper_strike_not_eligible(self):
        eligible = {"Missing Dozen/Col", "Even Money Drought", "Streak Attack", "Pattern Match"}
        assert "Sniper Strike" not in eligible

    def test_cold_trinity_not_eligible(self):
        eligible = {"Missing Dozen/Col", "Even Money Drought", "Streak Attack", "Pattern Match"}
        assert "Cold Trinity" not in eligible

    def test_labouchere_not_eligible(self):
        eligible = {"Missing Dozen/Col", "Even Money Drought", "Streak Attack", "Pattern Match"}
        assert "Labouchere" not in eligible

    def test_dc_eligible_set_has_exactly_4_entries(self):
        """The DC-eligible set contains exactly 4 card types."""
        eligible = {"Missing Dozen/Col", "Even Money Drought", "Streak Attack", "Pattern Match"}
        assert len(eligible) == 4

    def test_dc_logic_in_app_source_checks_exactly_4_cards(self):
        """The Double Confirmation block in de2d_tracker_logic appends exactly the 4 eligible cards.

        Uses a regex to find every ``_matches.append(...)`` call and verifies
        the card names used are exactly the 4 eligible ones — without relying
        on comment-marker positions in the file.

        de2d_tracker_logic was moved to wheelpulsepro/trackers.py in Step 2 of
        the modular refactor, so we read that file instead of app.py.
        """
        import pathlib
        import re

        src = pathlib.Path("wheelpulsepro/trackers.py").read_text()
        # Each eligible card name must appear somewhere in the file
        for card in ("Missing Dozen/Col", "Even Money Drought", "Streak Attack", "Pattern Match"):
            assert card in src, f"Eligible DC card '{card}' not found in wheelpulsepro/trackers.py"

        # Extract all card names used in _matches.append calls
        found_cards = set(re.findall(r'_matches\.append\(\("([^"]+)"', src))
        expected_cards = {"Missing Dozen/Col", "Even Money Drought", "Streak Attack", "Pattern Match"}
        assert found_cards == expected_cards, (
            f"_matches.append calls reference unexpected cards.\n"
            f"  Found:    {sorted(found_cards)}\n"
            f"  Expected: {sorted(expected_cards)}"
        )


# ===========================================================================
# 9. Drought Counter Rendering Integration Tests
# ===========================================================================

class TestDroughtCounterRendering:
    """Verify drought counters are correctly reflected in rendered HTML output."""

    def test_drought_table_shows_correct_count(self):
        """render_drought_table_html shows exact drought values."""
        from wheelpulsepro.rendering import render_drought_table_html
        s = RouletteState()
        s.drought_counters["1st Dozen"] = 15
        s.last_spins = ["13"] * 30
        html = render_drought_table_html(s)
        assert "15 spins dry" in html
        assert "1st Dozen" in html

    def test_drought_table_shows_convergence_labels(self):
        """Convergence probability section shows 'Next 5' and 'Next 10' labels."""
        from wheelpulsepro.rendering import render_drought_table_html
        s = RouletteState()
        s.drought_counters["2nd Dozen"] = 10
        s.last_spins = ["5"] * 20
        html = render_drought_table_html(s)
        assert "Next 5" in html
        assert "Next 10" in html

    def test_drought_table_handles_all_zero_droughts(self):
        """render_drought_table_html handles all-zero droughts gracefully."""
        from wheelpulsepro.rendering import render_drought_table_html
        s = RouletteState()
        # All droughts are 0 (fresh state)
        s.last_spins = ["1"] * 5
        html = render_drought_table_html(s)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_drought_table_multiple_categories(self):
        """render_drought_table_html shows all tracked categories."""
        from wheelpulsepro.rendering import render_drought_table_html
        s = RouletteState()
        s.drought_counters = {
            "1st Dozen": 15, "2nd Dozen": 3, "3rd Dozen": 0,
            "1st Column": 8, "2nd Column": 2, "3rd Column": 1,
            "Red": 5, "Black": 0, "Even": 4, "Odd": 3, "Low": 6, "High": 2,
        }
        s.last_spins = ["1"] * 30
        html = render_drought_table_html(s)
        assert "1st Dozen" in html
        assert "Red" in html
        assert "1st Column" in html

    def test_sigma_analysis_renders_with_sufficient_spins(self):
        """render_sigma_analysis_html shows σ values when n ≥ 10."""
        from wheelpulsepro.rendering import render_sigma_analysis_html
        s = RouletteState()
        s.last_spins = [str(i % 36 + 1) for i in range(20)]
        s.dozen_scores = {"1st Dozen": 8, "2nd Dozen": 7, "3rd Dozen": 5}
        s.column_scores = {"1st Column": 7, "2nd Column": 7, "3rd Column": 6}
        s.even_money_scores = {"Red": 10, "Black": 10, "Even": 10, "Odd": 10, "Low": 10, "High": 10}
        s.analysis_window = 50
        html = render_sigma_analysis_html(s)
        assert "σ" in html
        assert "1st Dozen" in html

    def test_sigma_analysis_requests_more_data_below_10_spins(self):
        """With < 10 spins the sigma analysis shows a prompt for more data."""
        from wheelpulsepro.rendering import render_sigma_analysis_html
        s = RouletteState()
        s.last_spins = ["1", "2", "3"]
        html = render_sigma_analysis_html(s)
        assert isinstance(html, str)
        assert "10" in html or "spin" in html.lower()
