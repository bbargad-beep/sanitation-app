# -*- coding: utf-8 -*-
"""
Append-only JSONL audit log for field-level corrections.

Schema per entry:
  {ticket, field, old, new, source, timestamp, run_id}

source ∈ {auto_fix, manual_editor, bulk_paste, gis_retry, waive, ...}

Logs are written per-run, into the system temp directory:

    <tmp>/herzliya_audit/audit_<run_id>.jsonl

Rationale: the previous single ``audit.jsonl`` sat beside the source file and
was shared by every run ever executed, so "what did I change in this run?"
had no answer.  It was also tracked in git, which meant local activity showed
up as repository changes, and on Streamlit Cloud it lived on ephemeral disk
inside the deployment directory.
"""

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone

LOG_DIR = os.path.join(tempfile.gettempdir(), "herzliya_audit")

VALID_SOURCES = {"auto_fix", "manual_editor", "bulk_paste", "gis_retry", "waive",
                 "manual_review", "spot_check_approval", "user_qa",
                 "user_override", "user_resp_term", "user_resp_default",
                 "context_resolve",
                 # Rule-ledger verdicts: a human accepting, rejecting, or
                 # rewriting one rule for every row that rule produced.
                 "rule_review"}

# Run currently being logged.  Set once per session via set_run(); callers that
# do not set it get a stable "unscoped" bucket rather than silently mixing into
# whatever the last run happened to be.
_CURRENT_RUN_ID = ""


def new_run_id() -> str:
    """Generate a fresh run identifier."""
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def set_run(run_id: str) -> str:
    """Set the run this process is logging to. Returns the run_id."""
    global _CURRENT_RUN_ID
    _CURRENT_RUN_ID = run_id or ""
    return _CURRENT_RUN_ID


def current_run() -> str:
    return _CURRENT_RUN_ID


def log_path_for(run_id: str = "") -> str:
    """Path of the JSONL file for a given run (defaults to the current run)."""
    rid = run_id or _CURRENT_RUN_ID or "unscoped"
    safe = "".join(c for c in str(rid) if c.isalnum() or c in "-_")
    return os.path.join(LOG_DIR, f"audit_{safe or 'unscoped'}.jsonl")


def _default_log_path() -> str:
    return log_path_for()


def log_correction(
    ticket,
    field: str,
    old,
    new,
    source: str,
    run_id: str = "",
    log_path: str = "",
) -> dict:
    """Append one correction entry to this run's JSONL log and return it."""
    if source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES}, got {source!r}")

    rid = run_id or _CURRENT_RUN_ID or "unscoped"
    entry = {
        "ticket":    str(ticket),
        "field":     field,
        "old":       old if old is not None else "",
        "new":       new if new is not None else "",
        "source":    source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id":    rid,
    }

    path = log_path or log_path_for(rid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


def load_log(log_path: str = "", run_id: str = "") -> list:
    """Load all entries for one run (defaults to the current run)."""
    path = log_path or log_path_for(run_id)
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def list_runs() -> list:
    """Return [(run_id, path, n_entries, mtime)] for every run on disk, newest first."""
    if not os.path.isdir(LOG_DIR):
        return []
    out = []
    for name in os.listdir(LOG_DIR):
        if not (name.startswith("audit_") and name.endswith(".jsonl")):
            continue
        path = os.path.join(LOG_DIR, name)
        rid = name[len("audit_"):-len(".jsonl")]
        try:
            with open(path, "r", encoding="utf-8") as f:
                n = sum(1 for line in f if line.strip())
            out.append((rid, path, n, os.path.getmtime(path)))
        except OSError:
            continue
    return sorted(out, key=lambda t: t[3], reverse=True)


def log_to_dataframe(log_path: str = "", run_id: str = ""):
    """Return one run's audit log as a pandas DataFrame."""
    import pandas as pd
    entries = load_log(log_path, run_id)
    cols = ["ticket", "field", "old", "new", "source", "timestamp", "run_id"]
    if not entries:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(entries)
