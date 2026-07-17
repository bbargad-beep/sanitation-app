# -*- coding: utf-8 -*-
"""
Tests for Step 11 — Three-level severity + accounted override.

Accept criteria:
  - flags.py exports SEVERITY_BLOCK, SEVERITY_REVIEW, SEVERITY_INFO constants
  - count_review() / count_info() functions exist and return ints
  - waived_tickets() returns ticket IDs for blocking rows
  - FLAG_COLORS covers block, warn/review, info
  - audit_log records a "waive" entry for each waived ticket
"""

import pandas as pd
import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import flags as fl
import audit_log as al


def _make_flagged():
    """Small DataFrame with one blocking and one warn row."""
    rows = [
        {
            "מס' פניה": "101",
            "תאריך": "2024-06-15",
            "רחוב_ראשי": None,      # triggers addr_empty → block
            "מספר_בית": "",
            "סוג_מיקום": "כתובת",
            "קו_רוחב": None,
            "קו_אורך": None,
            "geocode_method": "",
            "תת_נושא_חדש": "אי פינוי",
            "סטטוס פנייה": "סגור",
        },
        {
            "מס' פניה": "102",
            "תאריך": "2024-06-15",
            "רחוב_ראשי": "הבנים",
            "מספר_בית": None,       # triggers no_house → warn
            "סוג_מיקום": "כתובת",
            "קו_רוחב": 32.165,
            "קו_אורך": 34.835,
            "geocode_method": "nominatim",
            "תת_נושא_חדש": "אי פינוי",
            "סטטוס פנייה": "סגור",
        },
        {
            "מס' פניה": "103",
            "תאריך": "2024-06-15",
            "רחוב_ראשי": "סוקולוב",
            "מספר_בית": "5",
            "סוג_מיקום": "כתובת",
            "קו_רוחב": 32.165,
            "קו_אורך": 34.835,
            "geocode_method": "nominatim",
            "תת_נושא_חדש": "אי פינוי",
            "סטטוס פנייה": "סגור",
        },
    ]
    df = pd.DataFrame(rows)
    return fl.detect_flags(df, stage="clean")


# ── Severity constants ────────────────────────────────────────────────────────

def test_severity_constants_exist():
    assert hasattr(fl, "SEVERITY_BLOCK")
    assert hasattr(fl, "SEVERITY_REVIEW")
    assert hasattr(fl, "SEVERITY_INFO")


def test_severity_block_value():
    assert fl.SEVERITY_BLOCK == "block"


def test_severity_review_maps_to_warn():
    """SEVERITY_REVIEW is the canonical internal value ("warn") for review-level flags."""
    assert fl.SEVERITY_REVIEW in ("warn", "review")


# ── Counting functions ────────────────────────────────────────────────────────

def test_count_review_function_exists():
    flagged = _make_flagged()
    result = fl.count_review(flagged)
    assert isinstance(result, int)


def test_count_info_function_exists():
    flagged = _make_flagged()
    result = fl.count_info(flagged)
    assert isinstance(result, int)
    assert result >= 0


def test_count_review_equals_count_warnings():
    flagged = _make_flagged()
    assert fl.count_review(flagged) == fl.count_warnings(flagged)


def test_count_blocking_correct():
    flagged = _make_flagged()
    # Row 101 has blank street with כתובת type → block
    assert fl.count_blocking(flagged) >= 1


# ── waived_tickets ────────────────────────────────────────────────────────────

def test_waived_tickets_returns_list():
    flagged = _make_flagged()
    result = fl.waived_tickets(flagged)
    assert isinstance(result, list)


def test_waived_tickets_only_blocking():
    flagged = _make_flagged()
    tickets = fl.waived_tickets(flagged)
    # Only ticket 101 is blocking
    assert "101" in tickets
    assert "103" not in tickets  # clean row


def test_waived_tickets_empty_when_no_blocks():
    df = pd.DataFrame([{
        "מס' פניה": "200",
        "תאריך": "2024-06-15",
        "רחוב_ראשי": "הבנים",
        "מספר_בית": "5",
        "סוג_מיקום": "כתובת",
        "קו_רוחב": 32.165,
        "קו_אורך": 34.835,
        "geocode_method": "nominatim",
        "תת_נושא_חדש": "אי פינוי",
        "סטטוס פנייה": "סגור",
    }])
    flagged = fl.detect_flags(df, stage="clean")
    assert fl.waived_tickets(flagged) == []


# ── Audit log integration ─────────────────────────────────────────────────────

def test_waive_override_logs_to_audit(tmp_path):
    """Simulating the override button: each waived ticket appears in audit log."""
    log_path = str(tmp_path / "audit.jsonl")
    flagged = _make_flagged()
    tickets = fl.waived_tickets(flagged)
    assert tickets, "Need at least one blocking ticket for this test"

    for tid in tickets:
        al.log_correction(tid, "_flag_severity", "block", "waived", "waive",
                          log_path=log_path)

    entries = al.load_log(log_path=log_path)
    waive_entries = [e for e in entries if e["source"] == "waive"]
    assert len(waive_entries) == len(tickets), \
        f"Expected {len(tickets)} waive entries, got {len(waive_entries)}"
    logged_tickets = {e["ticket"] for e in waive_entries}
    assert set(tickets) == logged_tickets


# ── FLAG_COLORS ───────────────────────────────────────────────────────────────

def test_flag_colors_has_three_levels():
    colors = fl.FLAG_COLORS
    assert "block" in colors
    assert any(k in colors for k in ("warn", "review"))
    assert "info" in colors
