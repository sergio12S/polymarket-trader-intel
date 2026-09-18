# MCP surface

Tool functions in `tools.py`; stdio servers: `server.py` (here) and root `../server.py`.

## CORE path

1. `discover_btc15m_earners` — wallets active on BTC 15m via recent trades
2. `btc15m_closed_pnl` — TIMESTAMP-sorted closed PnL (honest WR)
3. `find_stable_btc15m_earners` — discover → TIMESTAMP PnL → stable filter

**Never** trust `/closed-positions` without `sortBy=TIMESTAMP` (API default is REALIZEDPNL → inflated WR).

Do **not** auto-copy trades; research only.
