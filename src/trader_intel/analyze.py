"""Simple style metrics — especially BTC 15m Up/Down."""
from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from typing import Any, Optional

BTC_15M = re.compile(r"btc-updown-15m-", re.I)


def is_btc_15m(slug: Optional[str]) -> bool:
    return bool(slug and BTC_15M.search(slug))


def _rows(conn: sqlite3.Connection, wallet: str) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM trades WHERE proxy_wallet = ? ORDER BY timestamp ASC",
            (wallet,),
        )
    )


def style_report(conn: sqlite3.Connection, wallet: str) -> dict[str, Any]:
    trades = _rows(conn, wallet)
    trader = conn.execute(
        "SELECT * FROM traders WHERE proxy_wallet = ?", (wallet,)
    ).fetchone()

    all_n = len(trades)
    btc = [t for t in trades if is_btc_15m(t["slug"])]
    other = [t for t in trades if not is_btc_15m(t["slug"])]

    def bucket(rows: list[sqlite3.Row]) -> dict[str, Any]:
        if not rows:
            return {"n": 0}
        sides = Counter((r["side"] or "?").upper() for r in rows)
        outcomes = Counter((r["outcome"] or "?").upper() for r in rows)
        prices = [float(r["price"]) for r in rows if r["price"] is not None]
        sizes = [float(r["size"]) for r in rows if r["size"] is not None]
        notional = [
            float(r["price"]) * float(r["size"])
            for r in rows
            if r["price"] is not None and r["size"] is not None
        ]
        # seconds into 15m window from slug end ts if present: btc-updown-15m-<unix_start>
        offsets = []
        for r in rows:
            slug = r["slug"] or ""
            m = re.search(r"btc-updown-15m-(\d+)$", slug)
            if not m or r["timestamp"] is None:
                continue
            start = int(m.group(1))
            offsets.append(int(r["timestamp"]) - start)
        early = sum(1 for o in offsets if 0 <= o <= 60)
        mid = sum(1 for o in offsets if 60 < o <= 600)
        late = sum(1 for o in offsets if 600 < o <= 900)
        return {
            "n": len(rows),
            "buy_pct": sides.get("BUY", 0) / len(rows),
            "sell_pct": sides.get("SELL", 0) / len(rows),
            "outcome_mix": dict(outcomes),
            "avg_price": sum(prices) / len(prices) if prices else None,
            "median_price": sorted(prices)[len(prices) // 2] if prices else None,
            "avg_size": sum(sizes) / len(sizes) if sizes else None,
            "avg_notional": sum(notional) / len(notional) if notional else None,
            "timing": {
                "n_with_offset": len(offsets),
                "early_0_60s": early,
                "mid_1_10m": mid,
                "late_10_15m": late,
                "avg_offset_sec": (sum(offsets) / len(offsets)) if offsets else None,
            },
        }

    btc_share = (len(btc) / all_n) if all_n else 0.0
    top_slugs = Counter(t["slug"] for t in trades if t["slug"]).most_common(8)

    # crude style label
    b = bucket(btc)
    style = "unknown"
    if b.get("n", 0) >= 10 and b.get("timing", {}).get("n_with_offset", 0) >= 5:
        tmg = b["timing"]
        total_t = max(1, tmg["early_0_60s"] + tmg["mid_1_10m"] + tmg["late_10_15m"])
        if tmg["late_10_15m"] / total_t >= 0.45:
            style = "near_expiry_sniper"
        elif tmg["early_0_60s"] / total_t >= 0.45:
            style = "open_window"
        else:
            style = "intrabar_mixed"
    elif all_n and btc_share < 0.05:
        style = "not_btc15m_focused"

    return {
        "wallet": wallet,
        "username": trader["username"] if trader else None,
        "leaderboard_pnl": trader["last_pnl"] if trader else None,
        "leaderboard_vol": trader["last_vol"] if trader else None,
        "leaderboard_period": trader["last_period"] if trader else None,
        "trades_pulled": all_n,
        "btc15m_share": btc_share,
        "btc15m": b,
        "other_markets": {"n": len(other)},
        "top_slugs": top_slugs,
        "style_label": style,
    }


def rank_btc15m_candidates(conn: sqlite3.Connection, *, min_btc_trades: int = 15) -> list[dict]:
    wallets = [r[0] for r in conn.execute("SELECT proxy_wallet FROM traders")]
    out = []
    for w in wallets:
        rep = style_report(conn, w)
        if rep["btc15m"].get("n", 0) >= min_btc_trades:
            out.append(rep)
    out.sort(key=lambda r: (-r["btc15m_share"], -r["btc15m"].get("n", 0)))
    return out
