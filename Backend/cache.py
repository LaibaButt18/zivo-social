import time
from threading import Lock


class ReadCache:
    def __init__(self, max_entries=128, ttl=5):
        self.max_entries = max_entries
        self.ttl = ttl
        self._lock = Lock()
        self._items = {}

    def get(self, key):
        now = time.monotonic()
        with self._lock:
            row = self._items.get(key)
            if row is None:
                return None
            expires, value = row
            if expires < now:
                del self._items[key]
                return None
            return value

    def put(self, key, value):
        now = time.monotonic()
        with self._lock:
            if key not in self._items and len(self._items) >= self.max_entries:
                oldest = min(self._items, key=lambda item: self._items[item][0])
                del self._items[oldest]
            self._items[key] = (now + self.ttl, value)

    def clear(self):
        with self._lock:
            self._items.clear()


read_cache = ReadCache()
