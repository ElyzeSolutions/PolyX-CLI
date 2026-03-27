"""File-based JSON caching with TTL and atomic writes."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from contextlib import suppress
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from polyx.config import Config


class FileCache:
    """File-based cache with TTL expiry and atomic writes."""

    def __init__(self, config: Config) -> None:
        self._dir = config.cache_dir
        self._default_ttl = config.cache_ttl

    def _key_path(self, key: str) -> Path:
        hashed = hashlib.md5(key.encode()).hexdigest()
        return self._dir / f"{hashed}.json"

    def get(self, key: str, ttl: int | None = None) -> Any | None:
        """Get cached value if it exists and hasn't expired."""
        path = self._key_path(key)
        if not path.exists():
            return None

        try:
            with open(path) as f:
                entry = json.load(f)
        except (json.JSONDecodeError, OSError):
            # Corrupted cache file — silently remove
            path.unlink(missing_ok=True)
            return None

        effective_ttl = ttl if ttl is not None else entry.get("ttl", self._default_ttl)
        if time.time() - entry.get("timestamp", 0) > effective_ttl:
            path.unlink(missing_ok=True)
            return None

        return entry.get("data")

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Cache a value with atomic write (temp file + rename)."""
        path = self._key_path(key)
        entry = {
            "timestamp": time.time(),
            "ttl": ttl if ttl is not None else self._default_ttl,
            "key": key,
            "data": value,
        }

        # Atomic write: write to temp file then rename
        fd, tmp_path = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(entry, f, separators=(",", ":"))
            os.replace(tmp_path, path)
        except Exception:
            with suppress(OSError):
                os.unlink(tmp_path)
            raise

    def clear(self) -> int:
        """Delete all cache files. Returns count of deleted files."""
        count = 0
        for path in self._dir.glob("*.json"):
            try:
                path.unlink()
                count += 1
            except OSError:
                pass
        return count

    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        total_files = 0
        total_size = 0
        oldest = None
        newest = None

        for path in self._dir.glob("*.json"):
            total_files += 1
            total_size += path.stat().st_size
            mtime = path.stat().st_mtime
            if oldest is None or mtime < oldest:
                oldest = mtime
            if newest is None or mtime > newest:
                newest = mtime

        return {
            "total_files": total_files,
            "total_size_kb": total_size / 1024,
            "oldest": oldest,
            "newest": newest,
        }

    def prune(self) -> int:
        """Remove expired entries. Returns count of pruned files."""
        count = 0
        now = time.time()
        for path in self._dir.glob("*.json"):
            try:
                with open(path) as f:
                    entry = json.load(f)
                ttl = entry.get("ttl", self._default_ttl)
                if now - entry.get("timestamp", 0) > ttl:
                    path.unlink()
                    count += 1
            except (json.JSONDecodeError, OSError):
                path.unlink(missing_ok=True)
                count += 1
        return count
