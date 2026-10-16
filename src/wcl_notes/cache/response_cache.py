"""SQLite cache of WCL GraphQL responses (stdlib only, safe to share between threads).

A finished report never changes, so its responses are kept forever; rankings move, so
they expire. Payloads are zlib-compressed JSON: report master data is large.
"""

import hashlib
import json
import logging
import os
import sqlite3
import sys
import threading
import time
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

APP_DIR_NAME = "wcl-notes"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    key        TEXT PRIMARY KEY,
    query_name TEXT NOT NULL,
    stored_at  REAL NOT NULL,
    expires_at REAL,            -- NULL: never expires
    payload    BLOB NOT NULL    -- zlib-compressed JSON of the GraphQL "data"
)
"""


def default_cache_path() -> Path:
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        base = Path(os.environ["LOCALAPPDATA"])
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / APP_DIR_NAME / "cache.sqlite"


@dataclass(frozen=True, slots=True)
class CacheStats:
    entries: int
    size_bytes: int


class ResponseCache:
    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time) -> None:
        self.path = path
        self._clock = clock
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        with self._lock, self._conn:
            self._conn.execute(_SCHEMA)

    @staticmethod
    def make_key(query: str, variables: Mapping[str, object]) -> str:
        """The query text is part of the key: editing a .graphql file invalidates it."""
        raw = query + "\0" + json.dumps(variables, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT payload, expires_at FROM responses WHERE key = ?", (key,)
                ).fetchone()
        except sqlite3.Error:
            log.exception("Cache read failed")
            return None
        if row is None:
            return None
        payload, expires_at = row
        if expires_at is not None and expires_at <= self._clock():
            return None
        try:
            data = json.loads(zlib.decompress(payload))
        except (zlib.error, ValueError):
            log.warning("Corrupted cache entry %s ignored", key)
            return None
        return data if isinstance(data, dict) else None

    def put(self, key: str, query_name: str, data: dict[str, Any], ttl_s: float | None) -> None:
        now = self._clock()
        payload = zlib.compress(json.dumps(data, ensure_ascii=False).encode("utf-8"))
        try:
            with self._lock, self._conn:
                self._conn.execute(
                    "INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?, ?)",
                    (key, query_name, now, None if ttl_s is None else now + ttl_s, payload),
                )
        except sqlite3.Error:
            log.exception("Cache write failed")

    def prune(self) -> int:
        """Delete expired entries; returns how many were removed."""
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "DELETE FROM responses WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (self._clock(),),
            )
        return cursor.rowcount

    def clear(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM responses")
        with self._lock:
            self._conn.execute("VACUUM")

    def stats(self) -> CacheStats:
        with self._lock:
            count, size = self._conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(LENGTH(payload)), 0) FROM responses"
            ).fetchone()
        return CacheStats(entries=int(count), size_bytes=int(size))

    def close(self) -> None:
        with self._lock:
            self._conn.close()
