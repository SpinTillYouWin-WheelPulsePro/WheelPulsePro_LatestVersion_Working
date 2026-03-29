"""Tests for wheelpulsepro.spins (PR18).

Verifies:
  1. The module imports without Gradio.
  2. All public symbols are present.
  3. parse_spins_input handles representative inputs and edge cases.
  4. validate_spins correctly classifies valid / invalid tokens including
     edge cases: empty input, whitespace-only, non-integer tokens, out-of-range
     values, boundary values (0 and 36).
"""

import importlib
import types

import pytest

from wheelpulsepro.spins import (
    MAX_SPINS,
    SPIN_MAX,
    SPIN_MIN,
    parse_spins_input,
    validate_spins,
)


# ---------------------------------------------------------------------------
# 1. Module import and symbol presence
# ---------------------------------------------------------------------------

def test_spins_module_importable():
    mod = importlib.import_module("wheelpulsepro.spins")
    assert isinstance(mod, types.ModuleType)


def test_spins_public_symbols_present():
    from wheelpulsepro import spins
    assert callable(spins.parse_spins_input)
    assert callable(spins.validate_spins)
    assert isinstance(spins.MAX_SPINS, int)
    assert isinstance(spins.SPIN_MIN, int)
    assert isinstance(spins.SPIN_MAX, int)


def test_spins_no_gradio_dependency():
    import sys
    if "wheelpulsepro.spins" in sys.modules:
        del sys.modules["wheelpulsepro.spins"]
    importlib.import_module("wheelpulsepro.spins")
    spins_mod = sys.modules["wheelpulsepro.spins"]
    assert "gr" not in vars(spins_mod), "spins.py must not import gradio as 'gr'"
    assert "gradio" not in vars(spins_mod), "spins.py must not import gradio"


# ---------------------------------------------------------------------------
# 2. Constants sanity
# ---------------------------------------------------------------------------

def test_constants_values():
    assert SPIN_MIN == 0
    assert SPIN_MAX == 36
    assert MAX_SPINS == 1000
    assert SPIN_MIN < SPIN_MAX


# ---------------------------------------------------------------------------
# 3. parse_spins_input
# ---------------------------------------------------------------------------

def test_parse_empty_string():
    assert parse_spins_input("") == []


def test_parse_whitespace_only():
    assert parse_spins_input("   ") == []
    assert parse_spins_input("\t\n") == []


def test_parse_none_like_empty_string():
    # None is not a valid str, but guard against callers passing falsy values
    assert parse_spins_input("") == []


def test_parse_single_spin():
    assert parse_spins_input("5") == ["5"]


def test_parse_single_spin_with_spaces():
    assert parse_spins_input("  5  ") == ["5"]


def test_parse_multiple_spins_spaces():
    assert parse_spins_input("1, 2, 3") == ["1", "2", "3"]


def test_parse_multiple_spins_no_spaces():
    assert parse_spins_input("0,36,17") == ["0", "36", "17"]


def test_parse_extra_whitespace_around_tokens():
    assert parse_spins_input("  1 ,  2 ,  3  ") == ["1", "2", "3"]


def test_parse_trailing_comma_ignored():
    # trailing empty token after comma is filtered out
    result = parse_spins_input("1,2,3,")
    assert result == ["1", "2", "3"]


def test_parse_preserves_order():
    result = parse_spins_input("7, 3, 15, 0")
    assert result == ["7", "3", "15", "0"]


def test_parse_preserves_duplicates():
    # parse does NOT deduplicate — that is the caller's concern
    result = parse_spins_input("1, 1, 2")
    assert result == ["1", "1", "2"]


def test_parse_non_numeric_tokens_preserved():
    # parse just splits; validation is separate
    result = parse_spins_input("abc, 5, xyz")
    assert result == ["abc", "5", "xyz"]


# ---------------------------------------------------------------------------
# 4. validate_spins – happy path
# ---------------------------------------------------------------------------

def test_validate_empty_list():
    valid, errors = validate_spins([])
    assert valid == []
    assert errors == []


def test_validate_all_valid():
    tokens = ["0", "1", "17", "36"]
    valid, errors = validate_spins(tokens)
    assert valid == ["0", "1", "17", "36"]
    assert errors == []


def test_validate_boundary_zero():
    valid, errors = validate_spins(["0"])
    assert valid == ["0"]
    assert errors == []


def test_validate_boundary_thirty_six():
    valid, errors = validate_spins(["36"])
    assert valid == ["36"]
    assert errors == []


def test_validate_returns_normalized_strings():
    # Input "01" should normalize to "1"
    valid, errors = validate_spins(["01"])
    assert valid == ["1"]
    assert errors == []


# ---------------------------------------------------------------------------
# 5. validate_spins – invalid inputs
# ---------------------------------------------------------------------------

def test_validate_out_of_range_above():
    valid, errors = validate_spins(["37"])
    assert valid == []
    assert len(errors) == 1
    assert "37" in errors[0]
    assert "out of range" in errors[0]


def test_validate_out_of_range_below():
    valid, errors = validate_spins(["-1"])
    assert valid == []
    assert len(errors) == 1
    assert "-1" in errors[0]


def test_validate_large_number():
    valid, errors = validate_spins(["100"])
    assert valid == []
    assert len(errors) == 1


def test_validate_non_integer_alpha():
    valid, errors = validate_spins(["abc"])
    assert valid == []
    assert len(errors) == 1
    assert "abc" in errors[0]
    assert "not a valid integer" in errors[0]


def test_validate_non_integer_float():
    valid, errors = validate_spins(["1.5"])
    assert valid == []
    assert len(errors) == 1


def test_validate_non_integer_special_chars():
    valid, errors = validate_spins(["!@#"])
    assert valid == []
    assert len(errors) == 1


def test_validate_empty_token():
    # An empty string is not a valid integer
    valid, errors = validate_spins([""])
    assert valid == []
    assert len(errors) == 1


def test_validate_whitespace_token():
    # Whitespace-only token is not a valid integer
    valid, errors = validate_spins(["   "])
    assert valid == []
    assert len(errors) == 1


# ---------------------------------------------------------------------------
# 6. validate_spins – mixed valid and invalid
# ---------------------------------------------------------------------------

def test_validate_mixed_valid_and_invalid():
    tokens = ["1", "abc", "36", "37"]
    valid, errors = validate_spins(tokens)
    assert valid == ["1", "36"]
    assert len(errors) == 2


def test_validate_all_invalid():
    tokens = ["xyz", "-5", "100"]
    valid, errors = validate_spins(tokens)
    assert valid == []
    assert len(errors) == 3


def test_validate_preserves_order_of_valid():
    tokens = ["5", "bad", "0", "12", "oops", "36"]
    valid, errors = validate_spins(tokens)
    assert valid == ["5", "0", "12", "36"]
    assert len(errors) == 2


# ---------------------------------------------------------------------------
# 7. Round-trip: parse then validate
# ---------------------------------------------------------------------------

def test_roundtrip_clean_input():
    raw = parse_spins_input("1, 2, 3, 0, 36")
    valid, errors = validate_spins(raw)
    assert valid == ["1", "2", "3", "0", "36"]
    assert errors == []


def test_roundtrip_with_invalid_tokens():
    raw = parse_spins_input("5, abc, 17, 99")
    valid, errors = validate_spins(raw)
    assert valid == ["5", "17"]
    assert len(errors) == 2


def test_roundtrip_empty():
    raw = parse_spins_input("")
    valid, errors = validate_spins(raw)
    assert valid == []
    assert errors == []


def test_roundtrip_max_spins_boundary():
    # Exactly MAX_SPINS tokens — all valid (cycling 0-36)
    tokens = [str(i % 37) for i in range(MAX_SPINS)]
    raw = parse_spins_input(", ".join(tokens))
    assert len(raw) == MAX_SPINS
    valid, errors = validate_spins(raw)
    assert len(valid) == MAX_SPINS
    assert errors == []


def test_roundtrip_over_max_spins():
    # Caller is responsible for the MAX_SPINS check before calling validate_spins.
    # validate_spins itself processes all tokens regardless of count.
    tokens = [str(i % 37) for i in range(MAX_SPINS + 1)]
    valid, errors = validate_spins(tokens)
    assert len(valid) == MAX_SPINS + 1
    assert errors == []
