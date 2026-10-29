import os
import queue
import sqlite3
import threading


class ConnectionPool:
    def __init__(self, path, size=4):
        self.path = path
        self.size = size
        self._queue = queue.Queue(maxsize=size)
        self._init_lock = threading.Lock()
        self._ready = False

    def _connect(self):
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def start(self):
        with self._init_lock:
            if self._ready:
                return
            first = self._connect()
            first.execute(
                "CREATE TABLE IF NOT EXISTS snapshot ("
                "id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
            )
            first.commit()
            self._queue.put(first)
            for _ in range(self.size - 1):
                self._queue.put(self._connect())
            self._ready = True

    def checkout(self):
        self.start()
        return self._queue.get()

    def release(self, conn):
        self._queue.put(conn)

    def load_payload(self):
        conn = self.checkout()
        try:
            row = conn.execute("SELECT payload FROM snapshot WHERE id = 1").fetchone()
            if row is None:
                return None
            return row[0]
        finally:
            self.release(conn)

    def save_payload(self, payload_text):
        conn = self.checkout()
        try:
            conn.execute("BEGIN")
            conn.execute(
                "INSERT OR REPLACE INTO snapshot (id, payload) VALUES (1, ?)",
                (payload_text,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.release(conn)
