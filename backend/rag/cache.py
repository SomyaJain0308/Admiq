import hashlib
import time
from typing import Optional


# IN PRODUCTION USE REDIS!


class ResponseCache:
    def __init__(self, ttl_seconds: int = 300):
        self.ttl = ttl_seconds
        self._cache: dict[str, dict] = {}
        self._hits = 0
        self._misses = 0

    def _make_key(self, query: str) -> str:
        normalized = str(query).lower().strip() # "What is the Fee?" & "   What is the fee?   " should be considered same
        return hashlib.sha256(normalized.encode()).hexdigest() # encode: text -> bytes, hashlib.sha256: passes bytes to sha256 (hashed), hexdigest: hash -> text SOLVES SECURITY AND SPEED
    
    def get(self, cache_input: str) -> Optional[str]:
        key = self._make_key(cache_input)

        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry["timestamp"] < self.ttl:
                self._hits += 1
                return entry["response"]
            else:
                del self._cache[key]

        self._misses += 1 
        return None
        
    def set(self, cache_input: str, response: str) -> None: # Cache a Response
        key = self._make_key(cache_input)
        self._cache[key] = {
            "response": response,
            "timestamp": time.time(),
            "query": cache_input,
        }

    @property
    def stats(self) -> dict: # Cache stats
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1%}",
            "cached_entries": len(self._cache),
        }