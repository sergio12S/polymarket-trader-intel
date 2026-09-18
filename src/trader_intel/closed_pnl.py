"""TIMESTAMP-sorted closed-position PnL helpers for BTC 15m.

Core honesty rule: Polymarket GET /closed-positions defaults to REALIZEDPNL
desc. Summaries / winrate / stable-earner filters MUST use rows fetched with
sortBy=TIMESTAMP (see PolyClient.closed_positions).
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from .analyze import is_btc_15m

# Alias preferred by the closed-PnL surface
is_btc_15m_slug = is_btc_15m


def _f(row: dict, *keys: str, default: float = 0.0) -> float:
    for k in keys:
        if k in row and row[k] is not None:
            try:
                return float(row[k])
            except (TypeError, ValueError):
                continue
    return default


def summarize_btc15m_closed(rows: list[dict]) -> dict[str, Any]:
    """Summarize closed-position rows (already filtered to BTC 15m if desired).

    Expects keys like realizedPnl, totalBought, avgPrice, timestamp, outcome.
    """
    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "wins": 0,
            "losses": 0,
            "zeros": 0,
            "wr": None,
            "pnl": 0.0,
            "avg": None,
            "max_win": None,
            "max_loss": None,
            "concentration": None,
            "bought": 0.0,
            "avg_price": None,
            "span_hours": None,
            "outcome_mix": {},
        }

    pnls = [_f(r, "realizedPnl", "realized_pnl") for r in rows]
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    zeros = sum(1 for p in pnls if p == 0)
    decided = wins + losses
    wr = (wins / decided) if decided else None
    total_pnl = sum(pnls)
    avg = total_pnl / n
    max_win = max(pnls)
    max_loss = min(pnls)
    concentration = (max_win / total_pnl) if total_pnl > 0 and max_win > 0 else None

    boughts = [_f(r, "totalBought", "total_bought") for r in rows]
    prices = []
    for r in rows:
        if r.get("avgPrice") is not None or r.get("avg_price") is not None:
            prices.append(_f(r, "avgPrice", "avg_price"))
    outcomes = Counter(str((r.get("outcome") or "?")).upper() for r in rows)

    ts = []
    for r in rows:
        t = r.get("timestamp")
        if t is not None:
            try:
                ts.append(int(t))
            except (TypeError, ValueError):
                pass
    span_hours = ((max(ts) - min(ts)) / 3600.0) if len(ts) >= 2 else (0.0 if ts else None)

    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "zeros": zeros,
        "wr": wr,
        "pnl": total_pnl,
        "avg": avg,
        "max_win": max_win,
        "max_loss": max_loss,
        "concentration": concentration,
        "bought": sum(boughts),
        "avg_price": (sum(prices) / len(prices)) if prices else None,
        "span_hours": span_hours,
        "outcome_mix": dict(outcomes),
    }


def is_stable_earner(
    summary: dict,
    *,
    min_n: int = 15,
    min_wr: float = 0.55,
    require_pnl_positive: bool = True,
    max_concentration: float = 0.5,
) -> bool:
    """Gate: enough samples, decent WR, positive PnL, not one-trade-dominated."""
    if not summary or summary.get("n", 0) < min_n:
        return False
    wr = summary.get("wr")
    if wr is None or wr < min_wr:
        return False
    if require_pnl_positive and not (summary.get("pnl") or 0) > 0:
        return False
    conc = summary.get("concentration")
    if conc is not None and conc > max_concentration:
        return False
    return True


def rank_stable_earners(summaries: list[dict], **criteria) -> list[dict]:
    """Filter with is_stable_earner, sort by pnl descending."""
    stable = [s for s in summaries if is_stable_earner(s, **criteria)]
    stable.sort(key=lambda s: float(s.get("pnl") or 0), reverse=True)
    return stable
