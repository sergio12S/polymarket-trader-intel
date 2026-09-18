# polymarket-trader-intel

Discover **who** earns on Polymarket BTC Up/Down 15m with **honest closed-position PnL** (public Data API).

Not a copy-trader. Separate from live `aipp-trading`.

## API sort trap (read this)

`GET https://data-api.polymarket.com/closed-positions` **defaults to `sortBy=REALIZEDPNL` descending**.

Fetching the first N rows **without** `sortBy=TIMESTAMP` over-samples big winners → fake ~100% winrates.

**Honest WR / PnL / stable-earner filters must use `sortBy=TIMESTAMP`** (this repo always does; typically `sortDirection=DESC` for recent).

## Quick start — CORE workflow

```bash
cd /Users/serg/projects/my_trading/polymarket-trader-intel   # or /home/box/polymarket-trader-intel
pip install -r requirements.txt

# 1) Discover wallets active on BTC 15m (via recent trades — not PnL leaderboard)
PYTHONPATH=src python3 -m trader_intel discover-btc15m --scan 4000 --limit 15

# 2) Honest closed PnL for one wallet (TIMESTAMP sort)
PYTHONPATH=src python3 -m trader_intel closed-pnl 0xea5929609487194dc9ce00871e2b5d1e5f48f29d --max-rows 50

# 3) Discover → TIMESTAMP closed PnL → stable-earner filter
PYTHONPATH=src python3 -m trader_intel stable-earners --scan-trades 3000 --top-wallets 15 --min-n 15 --min-wr 0.55
```

SQLite: `data/trader_intel.db`

## Secondary (style / hypotheses)

```bash
PYTHONPATH=src python3 -m trader_intel report --min-btc 5
PYTHONPATH=src python3 -m trader_intel why 0x...
PYTHONPATH=src python3 -m trader_intel scan --period WEEK --limit 12   # overall PnL leaders ≠ BTC 15m
```

## Research

- [BTC 15m earner case studies (RU)](docs/research-btc15m-earners.ru.md)
- [BTC 15m earner case studies (EN)](docs/research-btc15m-earners.md)

## MCP

Stdio server: `server.py` / `intel_mcp/server.py`.

Core tools: `discover_btc15m_earners` → `btc15m_closed_pnl` / `find_stable_btc15m_earners`.

Never trust closed-positions without TIMESTAMP. Not for copy-trading.
