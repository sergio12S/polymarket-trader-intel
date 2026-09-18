"""CLI for polymarket trader intel."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyze import rank_btc15m_candidates, style_report
from .db import DEFAULT_DB, connect, init_db
from .ingest import (
    closed_pnl_for_wallet,
    discover_btc15m_wallets,
    discover_stable_btc15m_earners,
    pull_leaderboard,
    pull_top_and_wallets,
    pull_wallet,
)


def _db(args) -> Path:
    return Path(args.db) if getattr(args, "db", None) else DEFAULT_DB


def cmd_leaderboard(args):
    out = pull_leaderboard(
        db_path=_db(args),
        period=args.period,
        limit=args.limit,
        order_by=args.order_by,
        with_profiles=args.profiles,
    )
    print(json.dumps(out, indent=2))


def cmd_pull(args):
    out = pull_wallet(db_path=_db(args), wallet=args.wallet, max_trades=args.max_trades)
    print(json.dumps(out, indent=2))


def cmd_scan(args):
    out = pull_top_and_wallets(
        db_path=_db(args),
        period=args.period,
        limit=args.limit,
        max_trades=args.max_trades,
    )
    print(json.dumps(out, indent=2))


def cmd_report(args):
    init_db(_db(args))
    with connect(_db(args)) as conn:
        if args.wallet:
            rep = style_report(conn, args.wallet.lower())
            print(json.dumps(rep, indent=2, default=str))
        else:
            ranked = rank_btc15m_candidates(conn, min_btc_trades=args.min_btc)
            print(f"{'user':22} {'btc%':>6} {'btc_n':>6} {'style':22} {'avg_px':>7} {'timing'}")
            for r in ranked[: args.limit]:
                t = r["btc15m"].get("timing") or {}
                timing = f"e{t.get('early_0_60s',0)}/m{t.get('mid_1_10m',0)}/l{t.get('late_10_15m',0)}"
                print(
                    f"{(r.get('username') or r['wallet'][:10]):22.22} "
                    f"{100*r['btc15m_share']:5.1f}% {r['btc15m'].get('n',0):6d} "
                    f"{r['style_label']:22.22} "
                    f"{(r['btc15m'].get('avg_price') or 0):7.3f} {timing}"
                )
            if args.json:
                print(json.dumps(ranked[: args.limit], indent=2, default=str))


def cmd_discover_btc(args):
    out = discover_btc15m_wallets(
        db_path=_db(args),
        scan_trades=args.scan,
        top_wallets=args.limit,
        max_trades_each=args.max_trades,
    )
    print(json.dumps(out, indent=2))


def cmd_closed_pnl(args):
    out = closed_pnl_for_wallet(args.wallet, max_rows=args.max_rows)
    print(json.dumps(out, indent=2, default=str))


def cmd_stable_earners(args):
    out = discover_stable_btc15m_earners(
        db_path=_db(args),
        scan_trades=args.scan_trades,
        top_wallets=args.top_wallets,
        max_trades_each=args.max_trades_each,
        max_closed=args.max_closed,
        min_n=args.min_n,
        min_wr=args.min_wr,
        max_concentration=args.max_concentration,
    )
    print(out.get("warning", ""))
    print(
        f"{'wallet':14} {'n':>4} {'wr':>6} {'pnl':>10} {'avg':>8} "
        f"{'conc':>6} {'span_h':>7}"
    )
    for r in out.get("stable") or []:
        wr = r.get("wr")
        wr_s = f"{100*wr:5.1f}%" if wr is not None else "   n/a"
        conc = r.get("concentration")
        conc_s = f"{conc:5.2f}" if conc is not None else "  n/a"
        span = r.get("span_hours")
        span_s = f"{span:7.1f}" if span is not None else "    n/a"
        print(
            f"{r.get('wallet','')[:14]:14} {r.get('n',0):4d} {wr_s} "
            f"{float(r.get('pnl') or 0):10.2f} {float(r.get('avg') or 0):8.3f} "
            f"{conc_s} {span_s}"
        )
    print(f"\nstable={len(out.get('stable') or [])} / pnl_rows={len(out.get('pnl') or [])}")
    if args.json:
        print(json.dumps(out, indent=2, default=str))


def cmd_why(args):
    init_db(_db(args))
    with connect(_db(args)) as conn:
        r = style_report(conn, args.wallet.lower())
    b = r.get("btc15m") or {}
    t = b.get("timing") or {}
    lines = [
        f"Trader: {r.get('username') or '?'} ({r['wallet']})",
        f"Leaderboard PnL ({r.get('leaderboard_period')}): {r.get('leaderboard_pnl')}",
        f"Trades pulled: {r['trades_pulled']} | BTC15m share: {100*r['btc15m_share']:.1f}% ({b.get('n',0)} trades)",
        f"Style label: {r['style_label']}",
        f"BTC15m avg entry price: {b.get('avg_price')} | avg notional: {b.get('avg_notional')}",
        f"Outcome mix: {b.get('outcome_mix')}",
        f"Timing (sec into 15m window): early={t.get('early_0_60s')} mid={t.get('mid_1_10m')} late={t.get('late_10_15m')} avg_offset={t.get('avg_offset_sec')}",
        "",
        "Hypotheses to check next:",
    ]
    if r["style_label"] == "near_expiry_sniper":
        lines.append("- Often trades last 5m — likely intrabar/momentum or resolution sniping, not open-pattern.")
    elif r["style_label"] == "open_window":
        lines.append("- Clusters at window open — comparable to aipp-trading cycle timing; compare their side vs AIPP.")
    elif r["style_label"] == "not_btc15m_focused":
        lines.append("- PnL may come from other categories; do not copy into BTC 15m blindly.")
    else:
        lines.append("- Mixed timing — dig individual markets / hold vs flip via activity redeems.")
    if (b.get("avg_price") or 1) < 0.35:
        lines.append("- Buys cheap asks — possibly underdog / longshot style (high variance).")
    if (b.get("avg_price") or 0) > 0.65:
        lines.append("- Buys expensive favorites — needs high winrate after fees.")
    lines.append("")
    lines.append("Also run: closed-pnl <wallet>  (TIMESTAMP-sorted; never trust default PnL sort)")
    print("\n".join(lines))


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="trader_intel",
        description=(
            "Polymarket trader intelligence. CORE path: discover-btc15m → "
            "closed-pnl / stable-earners (TIMESTAMP sort). Never trust "
            "/closed-positions without sortBy=TIMESTAMP."
        ),
    )
    p.add_argument("--db", default=str(DEFAULT_DB))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("leaderboard", help="Pull leaderboard into SQLite")
    s.add_argument("--period", default="WEEK", choices=["DAY", "WEEK", "MONTH", "ALL"])
    s.add_argument("--limit", type=int, default=25)
    s.add_argument("--order-by", default="PNL", choices=["PNL", "VOL"])
    s.add_argument("--profiles", action="store_true")
    s.set_defaults(func=cmd_leaderboard)

    s = sub.add_parser("pull", help="Pull trades/activity for one wallet")
    s.add_argument("wallet")
    s.add_argument("--max-trades", type=int, default=400)
    s.set_defaults(func=cmd_pull)

    s = sub.add_parser("scan", help="Leaderboard + pull top wallets")
    s.add_argument("--period", default="WEEK", choices=["DAY", "WEEK", "MONTH", "ALL"])
    s.add_argument("--limit", type=int, default=12)
    s.add_argument("--max-trades", type=int, default=300)
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("report", help="BTC15m style ranking / one wallet JSON (secondary)")
    s.add_argument("--wallet")
    s.add_argument("--min-btc", type=int, default=10)
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser(
        "discover-btc15m",
        help="CORE step 1: find BTC 15m wallets via recent trades (not PnL leaderboard)",
    )
    s.add_argument("--scan", type=int, default=3000, help="recent global trades to scan")
    s.add_argument("--limit", type=int, default=15, help="top wallets to pull")
    s.add_argument("--max-trades", type=int, default=300)
    s.set_defaults(func=cmd_discover_btc)

    s = sub.add_parser(
        "closed-pnl",
        help="CORE: TIMESTAMP-sorted BTC 15m closed-position PnL for one wallet",
    )
    s.add_argument("wallet")
    s.add_argument("--max-rows", type=int, default=400)
    s.set_defaults(func=cmd_closed_pnl)

    s = sub.add_parser(
        "stable-earners",
        help="CORE: discover → TIMESTAMP closed PnL → stable-earner filter",
    )
    s.add_argument("--scan-trades", type=int, default=3000)
    s.add_argument("--top-wallets", type=int, default=20)
    s.add_argument("--max-trades-each", type=int, default=300)
    s.add_argument("--max-closed", type=int, default=400)
    s.add_argument("--min-n", type=int, default=15)
    s.add_argument("--min-wr", type=float, default=0.55)
    s.add_argument("--max-concentration", type=float, default=0.5)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_stable_earners)

    s = sub.add_parser("why", help="Human card: style + hypotheses (secondary)")
    s.add_argument("wallet")
    s.set_defaults(func=cmd_why)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
