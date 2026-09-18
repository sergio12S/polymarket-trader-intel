"""Unit tests for TIMESTAMP closed-PnL helpers."""
from __future__ import annotations

import unittest

from trader_intel.closed_pnl import (
    is_stable_earner,
    rank_stable_earners,
    summarize_btc15m_closed,
)


def _row(pnl, *, ts=1_000_000, outcome="Up", bought=10, price=0.5, slug="btc-updown-15m-1"):
    return {
        "realizedPnl": pnl,
        "timestamp": ts,
        "outcome": outcome,
        "totalBought": bought,
        "avgPrice": price,
        "slug": slug,
    }


class TestSummarize(unittest.TestCase):
    def test_summarize_counts_wr_correctly(self):
        rows = [
            _row(10, ts=100),
            _row(-3, ts=200),
            _row(5, ts=300),
            _row(0, ts=400),
            _row(-1, ts=500),
        ]
        s = summarize_btc15m_closed(rows)
        self.assertEqual(s["n"], 5)
        self.assertEqual(s["wins"], 2)
        self.assertEqual(s["losses"], 2)
        self.assertEqual(s["zeros"], 1)
        self.assertAlmostEqual(s["wr"], 0.5)
        self.assertAlmostEqual(s["pnl"], 11.0)
        self.assertAlmostEqual(s["avg"], 2.2)
        self.assertAlmostEqual(s["max_win"], 10.0)
        self.assertAlmostEqual(s["max_loss"], -3.0)
        self.assertAlmostEqual(s["concentration"], 10.0 / 11.0)
        self.assertAlmostEqual(s["bought"], 50.0)
        self.assertAlmostEqual(s["span_hours"], (500 - 100) / 3600.0)
        self.assertIn("UP", s["outcome_mix"])


class TestStableGates(unittest.TestCase):
    def test_is_stable_earner_gates(self):
        good = {
            "n": 20,
            "wr": 0.6,
            "pnl": 100.0,
            "concentration": 0.2,
        }
        self.assertTrue(is_stable_earner(good))
        self.assertFalse(is_stable_earner({**good, "n": 10}))
        self.assertFalse(is_stable_earner({**good, "wr": 0.4}))
        self.assertFalse(is_stable_earner({**good, "pnl": -1}))
        self.assertFalse(is_stable_earner({**good, "concentration": 0.9}))

    def test_rank_stable_earners_sorts_by_pnl(self):
        a = {"wallet": "a", "n": 20, "wr": 0.6, "pnl": 50.0, "concentration": 0.1}
        b = {"wallet": "b", "n": 20, "wr": 0.7, "pnl": 200.0, "concentration": 0.1}
        c = {"wallet": "c", "n": 5, "wr": 0.9, "pnl": 999.0, "concentration": 0.1}
        ranked = rank_stable_earners([a, b, c])
        self.assertEqual([r["wallet"] for r in ranked], ["b", "a"])


class TestPnlSortedPageInflatesWrVsTimestamp(unittest.TestCase):
    """Document the API trap: a PnL-sorted first page can inflate WR vs a time-sorted page."""

    def test_default_pnl_sorted_page_would_inflate_wr_vs_timestamp_page(self):
        # Simulated full recent history (TIMESTAMP order): mixed outcomes
        timestamp_page = [
            _row(2),
            _row(-5),
            _row(1),
            _row(-4),
            _row(3),
            _row(-2),
            _row(1),
            _row(-3),
        ]
        # What the API returns if you take top-N by REALIZEDPNL (winners only)
        pnl_sorted_page = sorted(timestamp_page, key=lambda r: r["realizedPnl"], reverse=True)[:4]

        wr_ts = summarize_btc15m_closed(timestamp_page)["wr"]
        wr_pnl = summarize_btc15m_closed(pnl_sorted_page)["wr"]
        self.assertLess(wr_ts, 0.6)
        self.assertEqual(wr_pnl, 1.0)
        self.assertGreater(wr_pnl, wr_ts)


if __name__ == "__main__":
    unittest.main()
