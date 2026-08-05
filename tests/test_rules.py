# -*- coding: utf-8 -*-
"""Tests for rules.py — the rule ledger that replaces per-row correction review."""

import pandas as pd
import pytest

import rules as R
import clean_pipeline as cp


@pytest.fixture
def df():
    """Small frame carrying the provenance columns the ledger reads."""
    return pd.DataFrame({
        "מס' פניה":          [f"100{i}" for i in range(8)],
        "נושא":              ["פינוי אשפה"] * 4 + ["ניקיון"] * 4,
        "תת נושא":           ["אי פינוי", "", "", "", "", "", "", ""],
        "תת_נושא_חדש":       ["אי פינוי"] * 4 + ["משטח מלוכלך"] * 4,
        "סיווג_מקור":        ["map"] + ["topic_fallback"] * 7,
        "אחריות":            ["עירייה"] * 4 + ["טבעי", "טבעי", "א.מ.ל", "א.מ.ל"],
        "אחריות_מקור":       ["map"] * 4 + ["keyword:טבעי"] * 2 + ["unresolved"] * 2,
        "אחריות_מילה":       [""] * 4 + ["עלים", "עלים"] + [""] * 2,
        "מסלול_כתובת":       ["std"] * 6 + ["landmark"] * 2,
        "רחוב_ראשי":         ["סוקולוב"] * 8,
        "מספר_בית":          ["1", "2", "3", "4", "5", "6", "", ""],
        "כתובת ואתר/מוסד":   ["סוקולוב 1"] * 8,
        "תיאור":             ["עלים נשרו על המדרכה"] * 8,
        "_confidence":       ["medium"] * 8,
    })


def test_ledger_groups_by_rule_not_by_row(df):
    led = R.build_ledger(df)
    kinds = {r["kind"] for r in led}
    assert {"cat_map", "cat_fallback", "resp_map", "resp_keyword", "addr_route"} <= kinds
    # Far fewer rules than corrections
    assert len(led) < sum(r["n_rows"] for r in led)


def test_topic_fallback_is_visible(df):
    """The fallback path assigned 7 of 8 categories; it must not be invisible."""
    fb = [r for r in R.build_ledger(df) if r["kind"] == "cat_fallback"]
    assert sum(r["n_rows"] for r in fb) == 7
    assert {r["before"] for r in fb} == {"פינוי אשפה", "ניקיון"}


def test_keyword_rule_reports_the_matched_word_not_the_result(df):
    kw = [r for r in R.build_ledger(df) if r["kind"] == "resp_keyword"]
    assert len(kw) == 1
    assert kw[0]["before"] == "עלים"      # the trigger
    assert kw[0]["after"] == "טבעי"       # the result
    assert "עלים" in R.explain(kw[0])


def test_mask_round_trips_for_every_rule(df):
    for r in R.build_ledger(df):
        assert int(R.rule_mask(df, r).sum()) == r["n_rows"], r


def test_reject_withdraws_every_row_the_rule_touched(df):
    rule = next(r for r in R.build_ledger(df) if r["kind"] == "resp_map")
    out, n = R.apply_verdict(df.copy(), rule, R.VERDICT_REJECTED)
    assert n == 4
    m = R.rule_mask(df, rule)
    assert (out.loc[m, "אחריות"] == "א.מ.ל").all()
    assert (out.loc[m, "_confidence"] == "low").all()
    assert (out.loc[m, "אחריות_מקור"] == R.SRC_REJECTED).all()


def test_edit_rewrites_every_row_the_rule_touched(df):
    rule = next(r for r in R.build_ledger(df) if r["kind"] == "resp_map")
    out, n = R.apply_verdict(df.copy(), rule, R.VERDICT_EDITED, "טבעי")
    assert n == 4
    assert (out.loc[R.rule_mask(df, rule), "אחריות"] == "טבעי").all()


def test_reject_never_blanks_a_parsed_address(df):
    """An address parse has no meaningful undo; rejecting only flags for review."""
    rule = next(r for r in R.build_ledger(df) if r["kind"] == "addr_route")
    out, _ = R.apply_verdict(df.copy(), rule, R.VERDICT_REJECTED)
    m = R.rule_mask(df, rule)
    assert (out.loc[m, "רחוב_ראשי"] == "סוקולוב").all()
    assert (out.loc[m, "_confidence"] == "low").all()


def test_approve_stamps_a_verdict_without_changing_values(df):
    rule = next(r for r in R.build_ledger(df) if r["kind"] == "resp_map")
    out, _ = R.apply_verdict(df.copy(), rule, R.VERDICT_APPROVED)
    m = R.rule_mask(df, rule)
    assert (out.loc[m, "אחריות"] == "עירייה").all()
    assert (out.loc[m, R.COL_VERDICT] == R.VERDICT_APPROVED).all()


def test_coverage_counts_rows_not_rules(df):
    led = R.build_ledger(df)
    biggest = max(led, key=lambda r: r["n_rows"])
    cov = R.coverage(led, {biggest["rule_id"]: {"verdict": R.VERDICT_APPROVED}})
    assert cov["reviewed_rows"] == biggest["n_rows"]
    assert cov["n_reviewed"] == 1
    assert 0 < cov["pct_reviewed"] <= 100


def test_rejecting_a_rule_still_counts_as_having_reviewed_it(df):
    """merge_decided keeps the denominator stable when a verdict withdraws rows."""
    led = R.build_ledger(df)
    rule = next(r for r in led if r["kind"] == "resp_map")
    total_before = R.coverage(led, {})["total_rows"]

    out, n = R.apply_verdict(df.copy(), rule, R.VERDICT_REJECTED)
    decisions = {rule["rule_id"]: {"verdict": R.VERDICT_REJECTED, "rows": n, "rule": rule}}
    merged = R.merge_decided(R.build_ledger(out), decisions)
    cov = R.coverage(merged, decisions)

    assert cov["total_rows"] == total_before
    assert cov["reviewed_rows"] == rule["n_rows"]


def test_pareto_returns_the_number_of_rules_covering_the_target(df):
    led = R.build_ledger(df)
    assert 1 <= R.pareto(led, 90) <= len([r for r in led if not r["user_made"]])


def test_highlight_marks_every_occurrence():
    out = R.highlight("עלים נשרו, עוד עלים", "עלים")
    assert out.count("<mark") == 2
    assert R.highlight("טקסט", "") == "טקסט"


def test_ledger_is_empty_without_provenance():
    plain = pd.DataFrame({"מס' פניה": ["1"], "תיאור": ["x"]})
    assert R.has_provenance(plain) is False
    assert R.build_ledger(plain) == []


def test_legacy_frame_without_keyword_column_still_builds(df):
    """Files cleaned before אחריות_מילה existed must not crash the ledger."""
    legacy = df.drop(columns=["אחריות_מילה"])
    kw = [r for r in R.build_ledger(legacy) if r["kind"] == "resp_keyword"]
    assert len(kw) == 1
    assert kw[0]["n_rows"] == 2
    assert "לא נשמרה" in R.explain(kw[0])


def test_resolve_responsibility_kw_returns_the_trigger():
    resp, kw = cp.resolve_responsibility_kw("משטח מלוכלך", "עלים נשרו מהעץ")
    assert resp == "טבעי"
    assert kw == "עלים"
    # Map-derived decisions have no keyword to report
    assert cp.resolve_responsibility_kw("אי פינוי", "כל טקסט") == ("עירייה", "")
    assert cp.resolve_responsibility_kw("משטח מלוכלך", "אין כאן רמז") == ("א.מ.ל", "")
    # The old single-value API keeps working
    assert cp.resolve_responsibility("משטח מלוכלך", "עלים נשרו") == "טבעי"
