"""Pull leaderboard + per-wallet trades into SQLite."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .client import PolyClient
from .db import connect, init_db, insert_activity, insert_leaderboard_rows, insert_trades, upsert_trader


def pull_leaderboard(
    *,
    db_path: Path,
    period: str = "WEEK",
    category: str = "OVERALL",
    order_by: str = "PNL",
    limit: int = 25,
    with_profiles: bool = False,
) -> dict:
    init_db(db_path)
    client = PolyClient()
    rows = client.leaderboard(category=category, time_period=period, order_by=order_by, limit=limit)
    with connect(db_path) as conn:
        n = insert_leaderboard_rows(conn, rows, period, category, order_by)
        if with_profiles:
            for r in rows:
                try:
                    profile = client.profile(r["proxyWallet"])
                    upsert_trader(conn, r, period, profile=profile)
                except Exception:
                    continue
    return {"period": period, "n": n, "wallets": [r.get("proxyWallet") for r in rows]}


def pull_wallet(
    *,
    db_path: Path,
    wallet: str,
    max_trades: int = 400,
    max_activity: int = 200,
) -> dict:
    init_db(db_path)
    client = PolyClient()
    wallet = wallet.lower()
    trades = list(client.iter_trades(wallet, max_rows=max_trades))
    activity = client.activity(wallet, limit=min(100, max_activity))
    # page activity lightly
    act_all = list(activity)
    offset = len(activity)
    while offset < max_activity:
        batch = client.activity(wallet, limit=min(100, max_activity - offset), offset=offset)
        if not batch:
            break
        act_all.extend(batch)
        if len(batch) < 100:
            break
        offset += len(batch)

    with connect(db_path) as conn:
        # ensure trader row exists
        conn.execute(
            "INSERT OR IGNORE INTO traders(proxy_wallet, updated_at) VALUES(?, datetime('now'))",
            (wallet,),
        )
        nt = insert_trades(conn, wallet, trades)
        na = insert_activity(conn, wallet, act_all)
    return {"wallet": wallet, "trades_fetched": len(trades), "trades_new": nt, "activity_new": na}


def pull_top_and_wallets(
    *,
    db_path: Path,
    period: str = "WEEK",
    limit: int = 15,
    max_trades: int = 300,
) -> dict:
    lb = pull_leaderboard(db_path=db_path, period=period, limit=limit)
    details = []
    for w in lb["wallets"]:
        if not w:
            continue
        details.append(pull_wallet(db_path=db_path, wallet=w, max_trades=max_trades))
    return {"leaderboard": lb, "wallets": details}


def discover_btc15m_wallets(
    *,
    db_path: Path,
    scan_trades: int = 3000,
    top_wallets: int = 20,
    max_trades_each: int = 300,
    slug_substr: str = "btc-updown-15m",
) -> dict:
    """Find wallets active on BTC 15m by scanning recent global trades (not PnL leaderboard)."""
    from collections import Counter

    init_db(db_path)
    client = PolyClient()
    counts: Counter[str] = Counter()
    seen_rows = 0
    offset = 0
    page = 100
    while seen_rows < scan_trades:
        batch = client.recent_trades(limit=page, offset=offset)
        if not batch:
            break
        for row in batch:
            seen_rows += 1
            slug = row.get("slug") or ""
            if slug_substr in slug:
                w = (row.get("proxyWallet") or "").lower()
                if w:
                    counts[w] += 1
        if len(batch) < page:
            break
        offset += len(batch)

    top = counts.most_common(top_wallets)
    with connect(db_path) as conn:
        for w, _c in top:
            conn.execute(
                "INSERT OR IGNORE INTO traders(proxy_wallet, username, updated_at) VALUES(?,?,datetime('now'))",
                (w, None),
            )
    details = []
    for w, c in top:
        details.append(pull_wallet(db_path=db_path, wallet=w, max_trades=max_trades_each) | {"btc15m_hits_in_scan": c})
    return {
        "scanned_trades": seen_rows,
        "btc15m_hits": sum(counts.values()),
        "unique_wallets": len(counts),
        "top": [{"wallet": w, "hits": c} for w, c in top],
        "pulled": details,
    }


def closed_pnl_for_wallet(
    wallet: str,
    *,
    max_rows: int = 400,
    slug_substr: str = "btc-updown-15m",
) -> dict:
    """TIMESTAMP-sorted closed PnL for one wallet, filtered to BTC 15m slugs."""
    from .closed_pnl import is_btc_15m_slug, summarize_btc15m_closed

    client = PolyClient()
    wallet = wallet.lower()
    rows = list(
        client.iter_closed_positions(
            wallet,
            max_rows=max_rows,
            sort_by="TIMESTAMP",
            sort_direction="DESC",
        )
    )
    if slug_substr:
        filtered = [
            r
            for r in rows
            if slug_substr in (r.get("slug") or "")
            or is_btc_15m_slug(r.get("slug"))
        ]
    else:
        filtered = rows
    summary = summarize_btc15m_closed(filtered)
    summary["wallet"] = wallet
    summary["sort_by"] = "TIMESTAMP"
    summary["sort_direction"] = "DESC"
    summary["closed_fetched"] = len(rows)
    summary["btc15m_closed"] = len(filtered)
    summary["note"] = (
        "Closed positions fetched with sortBy=TIMESTAMP. "
        "Do NOT trust default REALIZEDPNL sort for winrate/stability."
    )
    return summary


def closed_pnl_for_wallets(
    wallets: list[str],
    *,
    max_rows: int = 400,
    slug_substr: str = "btc-updown-15m",
) -> list[dict]:
    return [
        closed_pnl_for_wallet(w, max_rows=max_rows, slug_substr=slug_substr)
        for w in wallets
        if w
    ]


def discover_stable_btc15m_earners(
    *,
    db_path: Optional[Path] = None,
    scan_trades: int = 3000,
    top_wallets: int = 20,
    max_trades_each: int = 300,
    max_closed: int = 400,
    min_n: int = 15,
    min_wr: float = 0.55,
    max_concentration: float = 0.5,
) -> dict:
    """Discover BTC 15m wallets, score TIMESTAMP closed PnL, filter stable earners.

    Core path: discover via recent trades → closed-pnl (TIMESTAMP) → stable filter.
    """
    from .closed_pnl import rank_stable_earners
    from .db import DEFAULT_DB

    if db_path is None:
        db_path = DEFAULT_DB

    discovered = discover_btc15m_wallets(
        db_path=db_path,
        scan_trades=scan_trades,
        top_wallets=top_wallets,
        max_trades_each=max_trades_each,
    )
    wallets = [t["wallet"] for t in discovered.get("top") or []]
    pnl_rows = closed_pnl_for_wallets(wallets, max_rows=max_closed)
    criteria = dict(min_n=min_n, min_wr=min_wr, max_concentration=max_concentration)
    stable = rank_stable_earners(pnl_rows, **criteria)
    warning = (
        "WARNING: All closed-PnL / WR / stable results used sortBy=TIMESTAMP. "
        "Never trust /closed-positions without TIMESTAMP — default REALIZEDPNL "
        "sort inflates winrates. Not for copy-trading."
    )
    return {
        "discover": discovered,
        "pnl": pnl_rows,
        "stable": stable,
        "criteria": criteria,
        "sort_by": "TIMESTAMP",
        "warning": warning,
    }
