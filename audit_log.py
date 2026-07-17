# -*- coding: utf-8 -*-
"""
Append-only JSONL audit log for field-level corrections.

Schema per entry:
  {ticket, field, old, new, source, timestamp, run_id}

source ∈ {auto_fix, manual_editor, bulk_paste, gis_retry, waive}
"""

import json
import os
import uuid
from datetime import datetime, timezone

_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit.jsonl")
VALID_SOURCES = {"auto_fix", "manual_editor", "bulk_paste", "gis_retry", "waive"}


def _default_log_path() -> str:
    return _LOG_FILE


def log_correction(
    ticket,
    field: str,
    old,
    new,
    source: str,
    run_id: str = "",
    log_path: str = "",
) -> dict:
    """Append one correction entry to the JSONL log and return it."""
    if source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES}, got {source!r}")

    entry = {
        "ticket":    str(ticket),
        "field":     field,
        "old":       old if old is not None else "",
        "new":       new if new is not None else "",
        "source":    source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id":    run_id or "",
    }

    path = log_path or _default_log_path()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


def load_log(log_path: str = "") -> list:
    """Load all entries from the JSONL log."""
    path = log_path or _default_log_path()
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def log_to_dataframe(log_path: str = ""):
    """Return the audit log as a pandas DataFrame."""
    import pandas as pd
    entries = load_log(log_path)
    if not entries:
        return pd.DataFrame(columns=["ticket", "field", "old", "new", "source", "timestamp", "run_id"])
    return pd.DataFrame(entries)
