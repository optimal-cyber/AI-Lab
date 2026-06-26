"""Structured request audit log for the gateway façade.

One JSON line per request, to stdout AND a rotated file — the same shape and
philosophy as NeMo's decisions.log, so the two join on `request_id` to
reconstruct a full life-of-a-prompt for a 3PAO.

PRIVACY: we never log prompt or completion CONTENT here. Only metadata
(identity fingerprint, model, token counts, latency, decision). The virtual key
is never logged raw — only a non-reversible fingerprint (prefix + sha256 head).
"""

from __future__ import annotations

import hashlib
import json
import logging
import logging.handlers
import os
import sys
import threading
from datetime import datetime, timezone
from typing import Any, Optional

# Tamper-evident hash chain: every audit row carries `prev` (the previous row's
# hash) and `hash` (sha256 of this row's content + prev). Altering, deleting, or
# reordering any row breaks the chain from that point on — verify_chain() proves it.
GENESIS = "0" * 64


def _row_digest(row: dict) -> str:
    """SHA-256 over the row's canonical JSON (sorted keys, compact, WITHOUT `hash`)."""
    canon = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _recover_prev(log_path: str) -> str:
    """Read the last row's hash from the active log so the chain survives restarts."""
    try:
        last = None
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last = line
        if last:
            return json.loads(last).get("hash") or GENESIS
    except (FileNotFoundError, ValueError, OSError):
        pass
    return GENESIS


def verify_chain(log_path: str) -> dict:
    """Re-walk the audit log and verify the tamper-evident hash chain.

    Returns {ok, count, broken_at, reason}. ok=True means every row's content
    hashes to its stored `hash` AND each row links to the previous row's hash.
    """
    prev_expected = None
    chained = 0
    row_no = 0
    try:
        f = open(log_path, "r", encoding="utf-8")
    except (FileNotFoundError, OSError):
        return {"ok": True, "count": 0, "broken_at": None, "reason": "empty"}
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row_no += 1
            try:
                row = json.loads(line)
            except ValueError:
                return {"ok": False, "count": chained, "broken_at": row_no, "reason": "unparseable"}
            stored = row.pop("hash", None)
            if stored is None:
                # legacy row written before hash-chaining — skip, reset the anchor.
                prev_expected = None
                continue
            if _row_digest(row) != stored:
                return {"ok": False, "count": chained, "broken_at": row_no, "reason": "content_tampered"}
            if prev_expected is not None and row.get("prev") != prev_expected:
                return {"ok": False, "count": chained, "broken_at": row_no, "reason": "chain_break"}
            prev_expected = stored
            chained += 1
    return {"ok": True, "count": chained, "broken_at": None, "reason": "intact"}


def key_fingerprint(key: Optional[str]) -> Optional[str]:
    """Non-reversible, low-cardinality id for a virtual key (audit only).

    Returns e.g. "sk-…a1b2:9f86d081" — enough to correlate requests from the
    same key without ever storing the secret.
    """
    if not key:
        return None
    tail = key[-4:] if len(key) >= 4 else key
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
    return f"…{tail}:{digest}"


class Auditor:
    def __init__(self, log_path: str) -> None:
        self._log = logging.getLogger("gateway.audit")
        self._log.setLevel(logging.INFO)
        self._log.propagate = False
        if not self._log.handlers:
            stdout = logging.StreamHandler(sys.stdout)
            stdout.setFormatter(logging.Formatter("%(message)s"))
            self._log.addHandler(stdout)
            try:
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                fileh = logging.handlers.RotatingFileHandler(
                    log_path, maxBytes=10_000_000, backupCount=5)
                fileh.setFormatter(logging.Formatter("%(message)s"))
                self._log.addHandler(fileh)
            except OSError:
                pass  # stdout is enough if the volume isn't mounted yet
        self._log_path = log_path
        self._lock = threading.Lock()
        self._prev = _recover_prev(log_path)  # continue the chain across restarts

    def emit(self, **fields: Any) -> None:
        # Drop None values for a compact row; callers pass only what they have.
        # Each row is hash-chained to the previous one (tamper-evident ledger);
        # a UTC timestamp leads so it reads as time-ordered evidence.
        with self._lock:
            row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "event": "gateway_request",
                   **{k: v for k, v in fields.items() if v is not None},
                   "prev": self._prev}
            row["hash"] = _row_digest(row)
            self._log.info(json.dumps(row, separators=(",", ":")))
            self._prev = row["hash"]

    def verify(self) -> dict:
        """Verify this Auditor's on-disk hash chain (for /admin/audit/verify)."""
        return verify_chain(self._log_path)
