"""Thin public Polymarket Data/Gamma client (no auth)."""
from __future__ import annotations

import time
from typing import Any, Iterator, Optional

import requests

DATA = "https://data-api.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"


class PolyClient:
    def __init__(self, sleep_s: float = 0.15, timeout: float = 30.0):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "polymarket-trader-intel/0.1"})
        self.sleep_s = sleep_s
        self.timeout = timeout

    def _get(self, url: str, params: Optional[dict] = None) -> Any:
        time.sleep(self.sleep_s)
        r = self.session.get(url, params=params or {}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def leaderboard(
        self,
        *,
        category: str = "OVERALL",
        time_period: str = "WEEK",
        order_by: str = "PNL",
        limit: int = 25,
        offset: int = 0,
    ) -> list[dict]:
        return self._get(
            f"{DATA}/v1/leaderboard",
            {
                "category": category,
                "timePeriod": time_period,
                "orderBy": order_by,
                "limit": limit,
                "offset": offset,
            },
        )

    def trades(self, user: str, *, limit: int = 100, offset: int = 0) -> list[dict]:
        return self._get(f"{DATA}/trades", {"user": user, "limit": limit, "offset": offset})

    def activity(self, user: str, *, limit: int = 100, offset: int = 0) -> list[dict]:
        return self._get(f"{DATA}/activity", {"user": user, "limit": limit, "offset": offset})

    def closed_positions(
        self,
        user: str,
        *,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "TIMESTAMP",
        sort_direction: str = "DESC",
    ) -> list[dict]:
        """Fetch closed positions. ALWAYS pass sortBy=TIMESTAMP for honest WR/PnL."""
        return self._get(
            f"{DATA}/closed-positions",
            {
                "user": user,
                "limit": limit,
                "offset": offset,
                "sortBy": sort_by,
                "sortDirection": sort_direction,
            },
        )

    def iter_closed_positions(
        self,
        user: str,
        *,
        max_rows: int = 400,
        page: int = 50,
        sort_by: str = "TIMESTAMP",
        sort_direction: str = "DESC",
    ) -> Iterator[dict]:
        offset = 0
        got = 0
        while got < max_rows:
            batch = self.closed_positions(
                user,
                limit=min(page, max_rows - got),
                offset=offset,
                sort_by=sort_by,
                sort_direction=sort_direction,
            )
            if not batch:
                break
            for row in batch:
                yield row
                got += 1
                if got >= max_rows:
                    return
            if len(batch) < page:
                break
            offset += len(batch)

    def profile(self, address: str) -> dict:
        return self._get(f"{GAMMA}/public-profile", {"address": address})

    def iter_trades(self, user: str, *, max_rows: int = 500, page: int = 100):
        offset = 0
        got = 0
        while got < max_rows:
            batch = self.trades(user, limit=min(page, max_rows - got), offset=offset)
            if not batch:
                break
            for row in batch:
                yield row
                got += 1
                if got >= max_rows:
                    return
            if len(batch) < page:
                break
            offset += len(batch)

    def recent_trades(self, *, limit: int = 100, offset: int = 0) -> list[dict]:
        return self._get(f"{DATA}/trades", {"limit": limit, "offset": offset})
