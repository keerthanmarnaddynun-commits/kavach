"""Hash-chained append-only audit log for KAVACH API actions."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any


GENESIS_PREV_HASH = "0" * 64


def canonical_json(data: Any) -> str:
    """Serialize dictionary to canonical JSON with sorted keys and no whitespace."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class AuditLog:
    """Thread-safe append-only hash-chained audit log."""

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _get_last_entry(self) -> dict[str, Any] | None:
        """Read the last line from the audit log file if it exists."""
        if not self.path.is_file():
            return None

        # Read lines from end
        lines = [line.strip() for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return None

        try:
            return json.loads(lines[-1])
        except Exception:
            return None

    def append(
        self,
        actor: str,
        role: str,
        action: str,
        case_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Append an audit entry, hash-chained to the previous entry.
        Never logs passwords, tokens, or raw document texts.
        """
        with self._lock:
            last = self._get_last_entry()
            if last is None:
                seq = 1
                prev_hash = GENESIS_PREV_HASH
            else:
                seq = int(last.get("seq", 0)) + 1
                prev_hash = str(last.get("hash", GENESIS_PREV_HASH))

            ts = _now_iso()
            entry_without_hash = {
                "action": action,
                "actor": actor,
                "case_id": case_id,
                "detail": detail or {},
                "prev_hash": prev_hash,
                "role": role,
                "seq": seq,
                "ts": ts,
            }

            canon_payload = canonical_json(entry_without_hash)
            signing_text = f"{prev_hash}\n{canon_payload}".encode("utf-8")
            entry_hash = hashlib.sha256(signing_text).hexdigest()

            full_entry = {
                **entry_without_hash,
                "hash": entry_hash,
            }

            line = canonical_json(full_entry) + "\n"
            with open(self.path, "a", encoding="utf-8", newline="\n") as f:
                f.write(line)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass

            return full_entry

    def read(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Read audit entries with pagination."""
        if not self.path.is_file():
            return []

        entries: list[dict[str, Any]] = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    entries.append(json.loads(line_str))
                except Exception:
                    pass

        return entries[offset : offset + limit]

    def verify(self) -> tuple[bool, int, int | None]:
        """
        Verify the integrity of the audit log chain from line 0.
        Returns:
            (is_valid, verified_count, first_bad_index_or_none)
        """
        if not self.path.is_file():
            return True, 0, None

        lines = [l.strip() for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not lines:
            return True, 0, None

        expected_prev_hash = GENESIS_PREV_HASH
        expected_seq = 1

        for idx, line_str in enumerate(lines):
            try:
                entry = json.loads(line_str)
            except Exception:
                return False, idx, idx

            if not isinstance(entry, dict):
                return False, idx, idx

            # Check sequence and prev_hash
            if entry.get("seq") != expected_seq:
                return False, idx, idx

            if entry.get("prev_hash") != expected_prev_hash:
                return False, idx, idx

            recorded_hash = entry.get("hash")
            if not recorded_hash or not isinstance(recorded_hash, str):
                return False, idx, idx

            entry_without_hash = {k: v for k, v in entry.items() if k != "hash"}
            canon_payload = canonical_json(entry_without_hash)
            computed_hash = hashlib.sha256(f"{expected_prev_hash}\n{canon_payload}".encode("utf-8")).hexdigest()

            if computed_hash != recorded_hash:
                return False, idx, idx

            expected_prev_hash = recorded_hash
            expected_seq += 1

        return True, len(lines), None
