"""Local read-only data stores: NIST catalog (JSON), POA&Ms (SQLite), CMMC status.

All POA&M access is READ-ONLY (ADR-005): the SQLite connection is opened with the
immutable/read-only URI so the MCP cannot mutate compliance data even if a tool is
coerced via prompt injection. Queries are parameterized and status_filter is
enum-validated (no arbitrary string search — T-MCP-E).
"""

from __future__ import annotations

import json
import os
import sqlite3
from functools import lru_cache
from typing import List, Optional

from .models import CmmcDomain, CmmcStatus, NaicsEntry, NistControl, Poam, PoamSummary

_DATA_DIR = os.environ.get(
    "MCP_DATA_DIR",
    os.path.join(os.path.dirname(__file__), "..", "data"),
)
NIST_PATH = os.path.join(_DATA_DIR, "nist_800_53_subset.json")
CMMC_PATH = os.path.join(_DATA_DIR, "cmmc_l2_status.json")
POAM_DB = os.path.join(_DATA_DIR, "poams.db")

VALID_POAM_STATUS = {"open", "in_progress", "completed", "risk_accepted"}


# --------------------------------------------------------------------------- #
# NIST 800-53 subset
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _load_nist() -> dict:
    with open(NIST_PATH) as fh:
        return json.load(fh)


def nist_control_lookup(control_id: str) -> Optional[NistControl]:
    control_id = (control_id or "").strip().upper()
    controls = _load_nist().get("controls", {})
    raw = controls.get(control_id)
    if raw is None:
        return None
    return NistControl(**raw)


def nist_available_controls() -> List[str]:
    return sorted(_load_nist().get("controls", {}).keys())


# --------------------------------------------------------------------------- #
# POA&M store (read-only SQLite)
# --------------------------------------------------------------------------- #
def _connect_ro(db_path: str = POAM_DB) -> sqlite3.Connection:
    # mode=ro => the connection cannot write. immutable would be even stricter
    # but ro keeps WAL/readers happy. The file must already exist.
    uri = f"file:{os.path.abspath(db_path)}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_poam(row: sqlite3.Row) -> Poam:
    try:
        milestones = json.loads(row["milestones_json"] or "[]")
    except (json.JSONDecodeError, TypeError):
        milestones = []
    return Poam(
        id=row["id"],
        control_id=row["control_id"],
        weakness_description=row["weakness_description"],
        severity=row["severity"],
        status=row["status"],
        scheduled_completion_date=row["scheduled_completion_date"],
        milestones=milestones,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def poam_list(status_filter: Optional[str] = None,
              db_path: Optional[str] = None) -> List[Poam]:
    db_path = db_path or POAM_DB
    if status_filter is not None:
        status_filter = status_filter.strip().lower()
        if status_filter not in VALID_POAM_STATUS:
            raise ValueError(
                f"invalid status_filter '{status_filter}'; "
                f"allowed: {sorted(VALID_POAM_STATUS)}"
            )
    conn = _connect_ro(db_path)
    try:
        if status_filter:
            cur = conn.execute(
                "SELECT * FROM poams WHERE status = ? ORDER BY "
                "CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
                "WHEN 'moderate' THEN 2 ELSE 3 END, id",
                (status_filter,),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM poams ORDER BY "
                "CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
                "WHEN 'moderate' THEN 2 ELSE 3 END, id"
            )
        return [_row_to_poam(r) for r in cur.fetchall()]
    finally:
        conn.close()


def poam_summary(db_path: Optional[str] = None) -> PoamSummary:
    db_path = db_path or POAM_DB
    conn = _connect_ro(db_path)
    try:
        sev = {r["severity"]: r["n"] for r in conn.execute(
            "SELECT severity, count(*) AS n FROM poams GROUP BY severity")}
        sts = {r["status"]: r["n"] for r in conn.execute(
            "SELECT status, count(*) AS n FROM poams GROUP BY status")}
        total = conn.execute("SELECT count(*) AS n FROM poams").fetchone()["n"]
        return PoamSummary(total=total, by_severity=sev, by_status=sts)
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# CMMC L2 status
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _load_cmmc() -> dict:
    with open(CMMC_PATH) as fh:
        return json.load(fh)


def cmmc_level2_status() -> CmmcStatus:
    raw = _load_cmmc()
    meta = raw.get("_meta", {})
    return CmmcStatus(
        framework=meta.get("framework", "CMMC 2.0 Level 2"),
        total_practices=raw["total_practices"],
        implemented=raw["implemented"],
        partial=raw["partial"],
        not_implemented=raw["not_implemented"],
        last_assessed=raw.get("last_assessed"),
        score_sprs_estimate=raw.get("score_sprs_estimate"),
        domains=[CmmcDomain(**d) for d in raw.get("domains", [])],
        disclaimer=meta.get("disclaimer", ""),
    )
