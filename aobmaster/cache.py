"""Simple caching for PE metadata to improve performance."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .pe import PEFile


class PECache:
    """Simple in-memory cache for PE file objects."""
    
    def __init__(self):
        self._cache: dict[tuple[Path, int], PEFile] = {}
    
    def get(self, path: Path) -> PEFile | None:
        """Get cached PE file if available and unchanged."""
        try:
            stat = path.stat()
            key = (path, stat.st_mtime_ns)
            return self._cache.get(key)
        except (OSError, FileNotFoundError):
            return None
    
    def put(self, path: Path, pe: PEFile) -> None:
        """Cache a PE file object."""
        try:
            stat = path.stat()
            key = (path, stat.st_mtime_ns)
            self._cache[key] = pe
            
            # Evict old entries for same path (file was modified)
            to_remove = [k for k in self._cache if k[0] == path and k != key]
            for k in to_remove:
                del self._cache[k]
        except (OSError, FileNotFoundError):
            pass
    
    def get_or_load(self, path: Path) -> PEFile:
        """Get from cache or load and cache."""
        pe = self.get(path)
        if pe is None:
            pe = PEFile(path)
            self.put(path, pe)
        return pe
    
    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
    
    def size(self) -> int:
        """Return number of cached entries."""
        return len(self._cache)


# Global cache instance
_global_cache = PECache()


def get_cached_pe(path: Path) -> PEFile:
    """Get PE file from global cache or load it."""
    return _global_cache.get_or_load(path)


def clear_pe_cache() -> None:
    """Clear the global PE cache."""
    _global_cache.clear()
