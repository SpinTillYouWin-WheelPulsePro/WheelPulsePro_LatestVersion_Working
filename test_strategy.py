"""
Test script for AIDEA_Tuned_Fusion (S85+C2) strategy logic.
Run: python test_strategy.py
"""

# Exact copy of the progression from app.py
sniper_progression = [
    # Phases 1-85: Street bet on 1ST STREET (1, 2, 3) — Payout 11:1
    0.01, 0.01, 0.01, 0.01, 0.01, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02, 0.03, 0.03, 0.03, 0.03, 0.04, 0.04, 0.04, 0.05, 0.05,
    0.06, 0.06, 0.07, 0.07, 0.08, 0.09, 0.09, 0.10, 0.11, 0.12, 0.13, 0.14, 0.16, 0.17, 0.18, 0.20, 0.22, 0.24, 0.26, 0.28,
    0.31, 0.34, 0.37, 0.40, 0.44, 0.48, 0.52, 0.56, 0.61, 0.67, 0.73, 0.80, 0.87, 0.94, 1.03, 1.12, 1.22, 1.33, 1.45, 1.58,
    1.72, 1.88, 2.04, 2.23, 2.43, 2.64, 2.88, 3.14, 3.42, 3.73, 4.06, 4.43, 4.82, 5.25, 5.72, 6.24, 6.80, 7.41, 8.07, 8.79,
    9.58, 10.44, 11.37, 12.39, 13.50,
    # Phases 86-87: Corner bet on 2-3-5-6 — Payout 8:1
    20.51, 23.22
]

SNIPER_WAIT = 22

def run_sniper(spins):
    """Exact replica of the sniper logic from app.py. Returns full state."""
    s_active = False
    s_step = 1
    s_miss_count = 0
    s_locked_misses = 0
    total_wagered = 0.0
    total_won = 0.0
    wins = 0
    losses = 0
    log = []

    for s in spins:
        if not s_active:
            if s not in {1, 2, 3}:
                s_miss_count += 1
            else:
                s_miss_count = 0

            if s_miss_count >= SNIPER_WAIT:
                s_active = True
                s_step = 1
                s_locked_misses = s_miss_count
                log.append(f"  >> ACTIVATED after {s_locked_misses} misses")
        else:
            if s_step <= 85:
                targets = {1, 2, 3}
                bet_type = "Street (1,2,3)"
                payout_mult = 11
            else:
                targets = {2, 3, 5, 6}
                bet_type = "Corner (2,3,5,6)"
                payout_mult = 8

            bet_amt = sniper_progression[s_step - 1]
            total_wagered += bet_amt

            if s in targets:
                winnings = bet_amt * payout_mult
                total_won += winnings + bet_amt  # return bet + profit
                wins += 1
                log.append(f"  Phase {s_step} [{bet_type}] Bet ${bet_amt:.2f} -> SPIN {s} -> WIN! +${winnings:.2f}")
                s_active = False
                s_step = 1
                s_miss_count = 0
            else:
                losses += 1
                log.append(f"  Phase {s_step} [{bet_type}] Bet ${bet_amt:.2f} -> SPIN {s} -> LOSS")
                s_step += 1
                if s_step > len(sniper_progression):
                    log.append(f"  >> BUST! Progression exhausted at phase 87.")
                    s_active = False
                    s_step = 1
                    s_miss_count = 1 if s not in {1, 2, 3} else 0

    return {
        "active": s_active,
        "step": s_step,
        "miss_count": s_miss_count,
        "wagered": total_wagered,
        "won": total_won,
        "profit": total_won - total_wagered,
        "wins": wins,
        "losses": losses,
        "log": log,
    }


def test_1_progression_length():
    """Verify the array has exactly 87 entries (85 street + 2 corner)."""
    assert len(sniper_progression) == 87, f"Expected 87 phases, got {len(sniper_progression)}"
    print("TEST 1 PASSED: Progression has 87 phases (85 street + 2 corner)")


def test_2_trigger_on_22_misses():
    """22 spins without 1,2,3 should activate the sniper."""
    spins = [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]  # 22 misses
    result = run_sniper(spins)
    assert result["active"] == True, "Should be active after 22 misses"
    assert result["step"] == 1, "Should be on step 1 (no bet evaluated yet)"
    print("TEST 2 PASSED: Activates after 22 consecutive misses of {1,2,3}")


def test_3_no_trigger_with_hit():
    """If 1,2,3 appears within the 22 spins, should NOT activate."""
    spins = [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 2, 22, 23, 24]  # hit at spin 19
    result = run_sniper(spins)
    assert result["active"] == False, "Should NOT activate — number 2 appeared"
    assert result["miss_count"] == 3, f"Should have 3 misses after the hit, got {result['miss_count']}"
    print("TEST 3 PASSED: Does NOT activate when 1,2,3 hits within window")


def test_4_zero_does_not_reset():
    """0 should NOT reset miss count (unlike old {0,1,2,3} logic)."""
    spins = [4, 5, 6, 7, 8, 9, 10, 11, 0, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]  # 0 at spin 9
    result = run_sniper(spins)
    assert result["active"] == True, "0 should NOT reset — only {1,2,3} resets"
    print("TEST 4 PASSED: 0 does NOT reset miss count (correct — old bug would have reset)")


def test_5_street_win_early():
    """Win on phase 1 with spin landing on 2 (street target)."""
    spins = [4]*22 + [2]  # 22 misses then hit
    result = run_sniper(spins)
    assert result["active"] == False
    assert result["wins"] == 1
    assert result["wagered"] == 0.01
    assert result["profit"] == 0.01 * 11  # 11:1 payout
    print(f"TEST 5 PASSED: Street win at phase 1 — bet $0.01, profit ${result['profit']:.2f}")


def test_6_corner_phase_targets():
    """After 85 street losses, phases 86-87 should target {2,3,5,6}."""
    # 22 misses to activate, then 85 losses on non-target numbers, then spin 5 (corner win)
    spins = [4]*22 + [7]*85 + [5]
    result = run_sniper(spins)
    assert result["active"] == False, "Should have won on corner"
    assert result["wins"] == 1
    # Phase 86 bet is 20.51, corner payout is 8:1
    for line in result["log"]:
        if "WIN" in line:
            assert "Corner (2,3,5,6)" in line, f"Should be corner bet: {line}"
            assert "$20.51" in line, f"Should be phase 86 bet amount: {line}"
            break
    print(f"TEST 6 PASSED: Corner rescue at phase 86 — bet $20.51, target 2,3,5,6")


def test_7_corner_win_on_number_6():
    """Number 6 should be a win in corner phase (new target, wasn't in old {0,1,2,3})."""
    spins = [4]*22 + [7]*85 + [6]
    result = run_sniper(spins)
    assert result["wins"] == 1
    print("TEST 7 PASSED: Number 6 is a valid corner win (was NOT a win in old basket logic)")


def test_8_full_bust():
    """87 consecutive losses should bust and reset."""
    spins = [4]*22 + [7]*87  # 22 trigger + 87 losses
    result = run_sniper(spins)
    assert result["active"] == False, "Should have reset after bust"
    assert result["wins"] == 0
    total_bet = sum(sniper_progression)
    assert abs(result["wagered"] - total_bet) < 0.01, f"Should have wagered full progression: ${total_bet:.2f}"
    print(f"TEST 8 PASSED: Full bust after 87 phases — total wagered ${result['wagered']:.2f}")


def test_9_bet_amounts_match_spec():
    """Verify key bet amounts match the AIDEA_Tuned_Fusion specification."""
    # Phase 1-5 should be $0.01
    for i in range(5):
        assert sniper_progression[i] == 0.01, f"Phase {i+1} should be $0.01"
    # Phase 6-11 should be $0.02
    for i in range(5, 11):
        assert sniper_progression[i] == 0.02, f"Phase {i+1} should be $0.02"
    # Phase 85 should be $13.50
    assert sniper_progression[84] == 13.50, f"Phase 85 should be $13.50, got {sniper_progression[84]}"
    # Phase 86 should be $20.51 (corner)
    assert sniper_progression[85] == 20.51, f"Phase 86 should be $20.51, got {sniper_progression[85]}"
    # Phase 87 should be $23.22 (corner)
    assert sniper_progression[86] == 23.22, f"Phase 87 should be $23.22, got {sniper_progression[86]}"
    print("TEST 9 PASSED: Key bet amounts match AIDEA_Tuned_Fusion spec")


def test_10_total_bet_amount():
    """Total progression sum should match ~$207.82 for $0.01 base."""
    total = sum(sniper_progression)
    print(f"TEST 10 INFO: Total progression = ${total:.2f}")
    assert 207 < total < 209, f"Total should be ~$207.82, got ${total:.2f}"
    print(f"TEST 10 PASSED: Total bet across all 87 phases = ${total:.2f}")


if __name__ == "__main__":
    print("=" * 60)
    print("AIDEA_Tuned_Fusion (S85+C2) Strategy Tests")
    print("=" * 60)
    print()

    tests = [
        test_1_progression_length,
        test_2_trigger_on_22_misses,
        test_3_no_trigger_with_hit,
        test_4_zero_does_not_reset,
        test_5_street_win_early,
        test_6_corner_phase_targets,
        test_7_corner_win_on_number_6,
        test_8_full_bust,
        test_9_bet_amounts_match_spec,
        test_10_total_bet_amount,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAILED: {test.__name__} — {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {test.__name__} — {e}")
            failed += 1
        print()

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 60)
