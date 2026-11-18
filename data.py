"""SQLite storage for nightly occupancy/revenue and competitor rates."""
from __future__ import annotations

import sqlite3
import threading
from datetime import date
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS nights (
  date TEXT PRIMARY KEY,
  rooms INTEGER NOT NULL,          -- rooms sold/booked for that night
  revenue REAL                     -- optional: total room revenue for that night
);
CREATE TABLE IF NOT EXISTS competitors (
  date TEXT NOT NULL,
  name TEXT NOT NULL,
  rate REAL NOT NULL,
  PRIMARY KEY (date, name)
);
"""


class Data:
    def __init__(self, path: str = ":memory:") -> None:
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def log_night(self, d: date, rooms: int, revenue: Optional[float], max_rooms: int) -> None:
        if not 0 <= rooms <= max_rooms:
            raise ValueError(f"rooms must be between 0 and {max_rooms}")
        if revenue is not None and revenue < 0:
            raise ValueError("revenue can't be negative")
        with self.lock:
            self.db.execute(
                "INSERT INTO nights(date,rooms,revenue) VALUES(?,?,?) "
                "ON CONFLICT(date) DO UPDATE SET rooms=excluded.rooms, "
                "revenue=COALESCE(excluded.revenue, nights.revenue)",
                (d.isoformat(), rooms, revenue))

    def log_competitor(self, d: date, name: str, rate: float) -> None:
        name = " ".join(name.split())[:60]
        if not name:
            raise ValueError("competitor name is required")
        if not 0 < rate < 1_000_000:
            raise ValueError("rate must be a positive number")
        with self.lock:
            self.db.execute(
                "INSERT INTO competitors(date,name,rate) VALUES(?,?,?) "
                "ON CONFLICT(date,name) DO UPDATE SET rate=excluded.rate",
                (d.isoformat(), name, rate))

    def booked(self, start: date, end: date) -> dict[date, int]:
        with self.lock:
            rows = self.db.execute("SELECT date, rooms FROM nights WHERE date>=? AND date<=?",
                                   (start.isoformat(), end.isoformat())).fetchall()
        return {date.fromisoformat(r["date"]): r["rooms"] for r in rows}

    def competitor_rates(self, start: date, end: date) -> dict[date, list[float]]:
        with self.lock:
            rows = self.db.execute("SELECT date, rate FROM competitors WHERE date>=? AND date<=?",
                                   (start.isoformat(), end.isoformat())).fetchall()
        out: dict[date, list[float]] = {}
        for r in rows:
            out.setdefault(date.fromisoformat(r["date"]), []).append(r["rate"])
        return out

    def nights_in_month(self, year: int, month: int) -> list[dict]:
        prefix = f"{year:04d}-{month:02d}-%"
        with self.lock:
            rows = self.db.execute("SELECT date, rooms, revenue FROM nights WHERE date LIKE ? ORDER BY date",
                                   (prefix,)).fetchall()
        return [dict(r) for r in rows]

    def months_with_data(self) -> list[str]:
        with self.lock:
            rows = self.db.execute("SELECT DISTINCT substr(date,1,7) m FROM nights ORDER BY m").fetchall()
        return [r["m"] for r in rows]
