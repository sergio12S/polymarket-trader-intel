"""SQLite ledger for trader intel."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "trader_intel.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS traders (
  proxy_wallet TEXT PRIMARY KEY,
  username TEXT,
  x_username TEXT,
  verified INTEGER,
  last_rank TEXT,
  last_pnl REAL,
  last_vol REAL,
  last_period TEXT,
  profile_json TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS leaderboard_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pulled_at TEXT NOT NULL,
  period TEXT NOT NULL,
  category TEXT NOT NULL,
  order_by TEXT NOT NULL,
  rank TEXT,
  proxy_wallet TEXT,
  username TEXT,
  pnl REAL,
  vol REAL,
  raw_json TEXT
);

CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proxy_wallet TEXT NOT NULL,
  tx_hash TEXT,
  timestamp INTEGER,
  side TEXT,
  outcome TEXT,
  price REAL,
  size REAL,
  slug TEXT,
  title TEXT,
  condition_id TEXT,
  asset TEXT,
  event_slug TEXT,
  raw_json TEXT,
  UNIQUE(proxy_wallet, tx_hash, asset, side, timestamp, price, size)
);

CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proxy_wallet TEXT NOT NULL,
  tx_hash TEXT,
  timestamp INTEGER,
  type TEXT,
  side TEXT,
  outcome TEXT,
  price REAL,
  size REAL,
  usdc_size REAL,
  slug TEXT,
  title TEXT,
  condition_id TEXT,
  raw_json TEXT,
  UNIQUE(proxy_wallet, tx_hash, type, asset_key, timestamp)
);
"""
# activity unique needs asset_key — simplify: use slug+outcome as asset_key in insert


def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: Path | str = DEFAULT_DB) -> None:
    with connect(db_path) as conn:
        # rebuild activity unique without phantom column — use simpler schema
        conn.executescript(
            """
CREATE TABLE IF NOT EXISTS traders (
  proxy_wallet TEXT PRIMARY KEY,
  username TEXT,
  x_username TEXT,
  verified INTEGER,
  last_rank TEXT,
  last_pnl REAL,
  last_vol REAL,
  last_period TEXT,
  profile_json TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS leaderboard_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pulled_at TEXT NOT NULL,
  period TEXT NOT NULL,
  category TEXT NOT NULL,
  order_by TEXT NOT NULL,
  rank TEXT,
  proxy_wallet TEXT,
  username TEXT,
  pnl REAL,
  vol REAL,
  raw_json TEXT
);
CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proxy_wallet TEXT NOT NULL,
  tx_hash TEXT,
  timestamp INTEGER,
  side TEXT,
  outcome TEXT,
  price REAL,
  size REAL,
  slug TEXT,
  title TEXT,
  condition_id TEXT,
  asset TEXT,
  event_slug TEXT,
  raw_json TEXT,
  UNIQUE(proxy_wallet, tx_hash, asset, side, timestamp, price, size)
);
CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proxy_wallet TEXT NOT NULL,
  tx_hash TEXT,
  timestamp INTEGER,
  type TEXT,
  side TEXT,
  outcome TEXT,
  price REAL,
  size REAL,
  usdc_size REAL,
  slug TEXT,
  title TEXT,
  condition_id TEXT,
  asset TEXT,
  raw_json TEXT,
  UNIQUE(proxy_wallet, tx_hash, type, asset, timestamp, size)
);
CREATE INDEX IF NOT EXISTS idx_trades_wallet_ts ON trades(proxy_wallet, timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_slug ON trades(slug);
CREATE INDEX IF NOT EXISTS idx_activity_wallet_ts ON activity(proxy_wallet, timestamp);
"""
        )


def utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def upsert_trader(conn: sqlite3.Connection, row: dict, period: str, profile: Optional[dict] = None) -> None:
    conn.execute(
        """
        INSERT INTO traders(proxy_wallet, username, x_username, verified, last_rank, last_pnl, last_vol, last_period, profile_json, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(proxy_wallet) DO UPDATE SET
          username=excluded.username,
          x_username=excluded.x_username,
          verified=excluded.verified,
          last_rank=excluded.last_rank,
          last_pnl=excluded.last_pnl,
          last_vol=excluded.last_vol,
          last_period=excluded.last_period,
          profile_json=COALESCE(excluded.profile_json, traders.profile_json),
          updated_at=excluded.updated_at
        """,
        (
            row.get("proxyWallet"),
            row.get("userName"),
            row.get("xUsername"),
            1 if row.get("verifiedBadge") else 0,
            str(row.get("rank")) if row.get("rank") is not None else None,
            row.get("pnl"),
            row.get("vol"),
            period,
            json.dumps(profile, default=str) if profile else None,
            utc_now(),
        ),
    )


def insert_leaderboard_rows(conn: sqlite3.Connection, rows: list[dict], period: str, category: str, order_by: str) -> int:
    pulled = utc_now()
    n = 0
    for r in rows:
        conn.execute(
            """
            INSERT INTO leaderboard_snapshots(pulled_at, period, category, order_by, rank, proxy_wallet, username, pnl, vol, raw_json)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                pulled,
                period,
                category,
                order_by,
                str(r.get("rank")),
                r.get("proxyWallet"),
                r.get("userName"),
                r.get("pnl"),
                r.get("vol"),
                json.dumps(r, default=str),
            ),
        )
        upsert_trader(conn, r, period)
        n += 1
    return n


def insert_trades(conn: sqlite3.Connection, wallet: str, rows: list[dict]) -> int:
    n = 0
    for r in rows:
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO trades(
                  proxy_wallet, tx_hash, timestamp, side, outcome, price, size, slug, title,
                  condition_id, asset, event_slug, raw_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    wallet,
                    r.get("transactionHash"),
                    r.get("timestamp"),
                    r.get("side"),
                    r.get("outcome"),
                    r.get("price"),
                    r.get("size"),
                    r.get("slug"),
                    r.get("title"),
                    r.get("conditionId"),
                    r.get("asset"),
                    r.get("eventSlug"),
                    json.dumps(r, default=str),
                ),
            )
            n += conn.execute("SELECT changes()").fetchone()[0]
        except sqlite3.Error:
            continue
    return n


def insert_activity(conn: sqlite3.Connection, wallet: str, rows: list[dict]) -> int:
    n = 0
    for r in rows:
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO activity(
                  proxy_wallet, tx_hash, timestamp, type, side, outcome, price, size, usdc_size,
                  slug, title, condition_id, asset, raw_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    wallet,
                    r.get("transactionHash"),
                    r.get("timestamp"),
                    r.get("type"),
                    r.get("side"),
                    r.get("outcome"),
                    r.get("price"),
                    r.get("size"),
                    r.get("usdcSize"),
                    r.get("slug"),
                    r.get("title"),
                    r.get("conditionId"),
                    r.get("asset"),
                    json.dumps(r, default=str),
                ),
            )
            n += conn.execute("SELECT changes()").fetchone()[0]
        except sqlite3.Error:
            continue
    return n
