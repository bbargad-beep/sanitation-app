# -*- coding: utf-8 -*-
"""
Tests for the acceptance card's claim.

The card is the one place the app makes a statistical promise about the data,
so its wording and its pass condition have to be exactly right.
"""

import spot_check as sc


def _stratum(label="s", lot=1000, n=46, reviewed=46, defects=0, unknown=0, verdict="pass"):
    return {"label": label, "lot_size": lot, "sample_n": n, "reviewed": reviewed,
            "unknown": unknown, "defects": defects, "verdict": verdict,
            "sample_tickets": []}


def test_clean_pass_states_detection_power_not_confidence():
    card = sc.build_acceptance_card("clean", [_stratum()], 0.05, 0.10)
    assert card["passed"] is True
    # β is the chance of *missing* a bad lot, so the honest claim is about
    # detection power — not a "90% confidence level".
    assert "90%" in card["claim"]
    assert "רמת ביטחון" not in card["claim"]
    assert "היה מגלה" in card["claim"] or "הייתה מגלה" in card["claim"]


def test_unknown_rows_block_a_pass():
    """A row nobody could judge must not be laundered into a passing claim."""
    card = sc.build_acceptance_card(
        "clean", [_stratum(reviewed=40, unknown=6, verdict="incomplete")], 0.05, 0.10)
    assert card["passed"] is False
    assert card["incomplete"] is True
    assert card["total_unknown"] == 6
    assert "לא הושלמו" in card["claim"]


def test_defects_fail_regardless_of_unknowns():
    card = sc.build_acceptance_card(
        "clean", [_stratum(reviewed=46, defects=2, verdict="fail")], 0.05, 0.10)
    assert card["passed"] is False
    assert card["incomplete"] is False
    assert "2 שגיאות" in card["claim"]


def test_one_incomplete_stratum_blocks_an_otherwise_clean_run():
    card = sc.build_acceptance_card(
        "clean",
        [_stratum(label="a"), _stratum(label="b", reviewed=10, unknown=36,
                                       verdict="incomplete")],
        0.05, 0.10)
    assert card["passed"] is False
    assert card["incomplete"] is True


def test_card_dataframe_exposes_the_unknown_column():
    card = sc.build_acceptance_card(
        "clean", [_stratum(reviewed=44, unknown=2, verdict="incomplete")], 0.05, 0.10)
    out = sc.card_to_dataframe(card)
    assert "לא בטוח" in out.columns
    assert out["לא בטוח"].tolist() == [2, 2]          # stratum row + total row
    assert out["פסיקה"].tolist() == ["⚠️ לא הושלם", "⚠️ לא הושלם"]


def test_sample_size_formula_unchanged():
    # ceil(-ln(0.10) / 0.05) = ceil(46.05) = 47
    assert sc.sample_size(10_000, 0.05, 0.10) == 47
    assert sc.sample_size(20, 0.05, 0.10) == 20      # capped at lot size
    assert sc.sample_size(0, 0.05, 0.10) == 0
