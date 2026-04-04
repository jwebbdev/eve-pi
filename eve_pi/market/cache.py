"""File-based cache with TTL for market data."""
import json
import time
from pathlib import Path
from typing import Any, Optional


class FileCache:
    def __init__(self, cache_dir: Path, ttl_seconds: int = 900):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe_key = key.replace("/", "_").replace("?", "_").replace("&", "_").replace("=", "_")
        return self.cache_dir / f"{safe_key}.json"

    def load(self, key: str) -> Optional[Any]:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if time.time() - cached.get("timestamp", 0) > self.ttl_seconds:
                return None
            return cached.get("data")
        except (json.JSONDecodeError, IOError):
            return None

    def save(self, key: str, data: Any) -> None:
        path = self._path(key)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"timestamp": time.time(), "data": data}, f)
        except IOError:
            pass
