"""
MCP-facing tool functions for trader intel.

Wire these into an MCP server (Cursor / Claude). Keep pure: path + args → JSON-able dict.

CORE path: discover_btc15m_earners → btc15m_closed_pnl / find_stable_btc15m_earners
(TIMESTAMP sort). Never trust closed-positions without TIMESTAMP. Not for copy-trading.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "trader_intel.db"

# allow running without install
import sys
sys.path.insert(0, str(ROOT / "src"))

from trader_intel.analyze import rank_btc15m_candidates, style_report  # noqa: E402
from trader_intel.db import connect, init_db  # noqa: E402
from trader_intel.ingest import (  # noqa: E402
    closed_pnl_for_wallet,
    discover_btc15m_wallets,
    discover_stable_btc15m_earners,
    pull_leaderboard,
    pull_top_and_wallets,
    pull_wallet,
)


def list_leaderboard_traders(period: str = "WEEK", limit: int = 25) -> dict[str, Any]:
    return pull_leaderboard(db_path=DEFAULT_DB, period=period, limit=limit)


def pull_trader(wallet: str, max_trades: int = 400) -> dict[str, Any]:
    return pull_wallet(db_path=DEFAULT_DB, wallet=wallet, max_trades=max_trades)


def scan_top_traders(period: str = "WEEK", limit: int = 12, max_trades: int = 300) -> dict[str, Any]:
    return pull_top_and_wallets(db_path=DEFAULT_DB, period=period, limit=limit, max_trades=max_trades)


def explain_trader_style(wallet: str) -> dict[str, Any]:
    init_db(DEFAULT_DB)
    with connect(DEFAULT_DB) as conn:
        return style_report(conn, wallet.lower())


def find_btc15m_earners(min_btc_trades: int = 15, limit: int = 20) -> list[dict[str, Any]]:
    init_db(DEFAULT_DB)
    with connect(DEFAULT_DB) as conn:
        return rank_btc15m_candidates(conn, min_btc_trades=min_btc_trades)[:limit]


def discover_btc15m_earners(scan_trades: int = 3000, limit: int = 15, max_trades: int = 300) -> dict:
    return discover_btc15m_wallets(
        db_path=DEFAULT_DB, scan_trades=scan_trades, top_wallets=limit, max_trades_each=max_trades
    )


def btc15m_closed_pnl(wallet: str, max_rows: int = 400) -> dict[str, Any]:
    """TIMESTAMP-sorted BTC 15m closed-position PnL for one wallet."""
    return closed_pnl_for_wallet(wallet, max_rows=max_rows)


def find_stable_btc15m_earners(
    scan_trades: int = 3000,
    limit: int = 15,
    max_closed: int = 400,
    min_n: int = 15,
    min_wr: float = 0.55,
    max_concentration: float = 0.5,
    max_trades: int = 300,
) -> dict[str, Any]:
    """Discover → TIMESTAMP closed PnL → stable filter. Core research path."""
    return discover_stable_btc15m_earners(
        db_path=DEFAULT_DB,
        scan_trades=scan_trades,
        top_wallets=limit,
        max_trades_each=max_trades,
        max_closed=max_closed,
        min_n=min_n,
        min_wr=min_wr,
        max_concentration=max_concentration,
    )


TOOL_CATALOG = [
    {
        "name": "discover_btc15m_earners",
        "desc": "CORE 1: find wallets active on BTC 15m via recent global trades",
    },
    {
        "name": "btc15m_closed_pnl",
        "desc": "CORE 2: TIMESTAMP-sorted BTC 15m closed PnL for one wallet (honest WR)",
    },
    {
        "name": "find_stable_btc15m_earners",
        "desc": "CORE 3: discover → TIMESTAMP closed PnL → stable-earner filter",
    },
    {"name": "list_leaderboard_traders", "desc": "Pull Polymarket PnL leaderboard into local DB"},
    {"name": "pull_trader", "desc": "Fetch trades/activity for one proxyWallet"},
    {"name": "scan_top_traders", "desc": "Leaderboard + pull top N wallets"},
    {"name": "explain_trader_style", "desc": "BTC15m timing/side/price style card for a wallet"},
    {"name": "find_btc15m_earners", "desc": "Rank stored traders by BTC 15m focus/style (secondary)"},
]
