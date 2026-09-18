#!/usr/bin/env python3
"""Stdio MCP server: Polymarket trader intelligence."""

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "intel_mcp"))

from mcp.server.fastmcp import FastMCP
import tools as T

mcp = FastMCP(
    "polymarket-trader-intel",
    instructions=(
        "CORE path: discover_btc15m_earners → btc15m_closed_pnl / "
        "find_stable_btc15m_earners. Closed-position WR/PnL MUST use "
        "sortBy=TIMESTAMP (this server always does). Never trust "
        "/closed-positions without TIMESTAMP — default REALIZEDPNL sort "
        "inflates winrates. Not for copy-trading; research only."
    ),
)


@mcp.tool()
def list_leaderboard_traders(period: str = "WEEK", limit: int = 25) -> dict[str, Any]:
    """Pull Polymarket PnL leaderboard into local SQLite and return wallet list."""
    return T.list_leaderboard_traders(period=period, limit=limit)


@mcp.tool()
def scan_top_traders(period: str = "WEEK", limit: int = 12, max_trades: int = 300) -> dict[str, Any]:
    """Pull top traders and download their recent trades/activity."""
    return T.scan_top_traders(period=period, limit=limit, max_trades=max_trades)


@mcp.tool()
def discover_btc15m_earners(scan_trades: int = 3000, limit: int = 15, max_trades: int = 300) -> dict[str, Any]:
    """CORE 1: Find wallets active on BTC 15m via recent global trades (not PnL leaderboard)."""
    return T.discover_btc15m_earners(scan_trades=scan_trades, limit=limit, max_trades=max_trades)


@mcp.tool()
def btc15m_closed_pnl(wallet: str, max_rows: int = 400) -> dict[str, Any]:
    """CORE 2: TIMESTAMP-sorted BTC 15m closed-position PnL (honest WR). Never use default PnL sort."""
    return T.btc15m_closed_pnl(wallet=wallet, max_rows=max_rows)


@mcp.tool()
def find_stable_btc15m_earners(
    scan_trades: int = 3000,
    limit: int = 15,
    max_closed: int = 400,
    min_n: int = 15,
    min_wr: float = 0.55,
    max_concentration: float = 0.5,
) -> dict[str, Any]:
    """CORE 3: discover → TIMESTAMP closed PnL → stable filter. Not for copy-trading."""
    return T.find_stable_btc15m_earners(
        scan_trades=scan_trades,
        limit=limit,
        max_closed=max_closed,
        min_n=min_n,
        min_wr=min_wr,
        max_concentration=max_concentration,
    )


@mcp.tool()
def pull_trader(wallet: str, max_trades: int = 400) -> dict[str, Any]:
    """Fetch trades/activity for one Polymarket proxyWallet into SQLite."""
    return T.pull_trader(wallet=wallet, max_trades=max_trades)


@mcp.tool()
def explain_trader_style(wallet: str) -> dict[str, Any]:
    """BTC 15m style card: timing, side/outcome mix, avg entry, style label (secondary)."""
    return T.explain_trader_style(wallet=wallet)


@mcp.tool()
def find_btc15m_earners(min_btc_trades: int = 10, limit: int = 20) -> Any:
    """Rank already-pulled traders by BTC 15m focus (secondary)."""
    return T.find_btc15m_earners(min_btc_trades=min_btc_trades, limit=limit)


@mcp.tool()
def tool_catalog() -> Any:
    """List trader-intel tools and short descriptions."""
    return T.TOOL_CATALOG


if __name__ == "__main__":
    mcp.run(transport="stdio")
