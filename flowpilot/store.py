"""Small durable JSON store. Every meaningful trace event is committed immediately."""

import json
import sqlite3
import threading
from pathlib import Path
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        path.chmod(0o600)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS objects (kind TEXT, id TEXT, payload TEXT, PRIMARY KEY(kind,id))"
        )
        self.db.commit()

    def put(self, kind, obj):
        with self.lock:
            self.db.execute(
                "INSERT OR REPLACE INTO objects VALUES (?,?,?)",
                (kind, obj["id"], json.dumps(obj, ensure_ascii=False)),
            )
            self.db.commit()
        return obj

    def get(self, kind, oid):
        with self.lock:
            r = self.db.execute(
                "SELECT payload FROM objects WHERE kind=? AND id=?", (kind, oid)
            ).fetchone()
        return json.loads(r[0]) if r else None

    def list(self, kind):
        with self.lock:
            rows = self.db.execute(
                "SELECT payload FROM objects WHERE kind=?", (kind,)
            ).fetchall()
        return sorted(
            (json.loads(r[0]) for r in rows),
            key=lambda o: o["created_at"],
            reverse=True,
        )

    def recover(self):
        for kind in ("run", "evaluation"):
            for obj in self.list(kind):
                if obj["status"] in ("running", "queued"):
                    obj.update(
                        status="failed",
                        error="Application restarted during execution. Start a new run to investigate again.",
                        updated_at=now(),
                    )
                    self.put(kind, obj)

    def close(self):
        self.db.close()
