#!/usr/bin/env python3
"""stay-pricing-tracker: occupancy log + rate suggestions for a guesthouse. Standard library only.

    python tracker.py log 2026-12-24 --rooms 8 --revenue 52000   # a night's booked rooms (+ revenue)
    python tracker.py import-nights nights.csv                   # date,rooms,revenue
    python tracker.py comp 2026-12-24 "Sea View Inn" 6500        # a nearby place's advertised rate
    python tracker.py import-comps comps.csv                     # date,name,rate
    python tracker.py suggest --days 30                          # suggested rates, with reasons
    python tracker.py summary                                    # occupancy, ADR, RevPAR per month
    python tracker.py report --days 60 -o pricing.html           # shareable HTML report

Competitor rates are typed or imported by you (look at public listings yourself);
this tool does not scrape any website.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pricing
import report
from data import Data

HERE = Path(__file__).parent


def build_rows(data: Data, cfg: dict, start: date, days: int, today: date) -> list[dict]:
    end = start + timedelta(days=days - 1)
    booked = data.booked(start, end)
    comps = data.competitor_rates(start - timedelta(days=3), end + timedelta(days=3))
    return [pricing.suggest(start + timedelta(days=i), today, cfg,
                            booked.get(start + timedelta(days=i)), comps) for i in range(days)]


def read_csv(path: str):
    with open(path, newline="", encoding="utf-8-sig") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):
            yield n, {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # piped output on Windows defaults to cp1252 and can't print ₹
        if not stream.isatty():
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="stay.db")
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--today", help="pretend today is this date (YYYY-MM-DD), for testing")
    sub = ap.add_subparsers(dest="cmd", required=True)

    l = sub.add_parser("log")
    l.add_argument("date")
    l.add_argument("--rooms", type=int, required=True)
    l.add_argument("--revenue", type=float)
    sub.add_parser("import-nights").add_argument("csv_file")
    c = sub.add_parser("comp")
    c.add_argument("date")
    c.add_argument("name")
    c.add_argument("rate", type=float)
    sub.add_parser("import-comps").add_argument("csv_file")
    s = sub.add_parser("suggest")
    s.add_argument("--from", dest="start")
    s.add_argument("--days", type=int, default=30)
    sub.add_parser("summary")
    r = sub.add_parser("report")
    r.add_argument("--from", dest="start")
    r.add_argument("--days", type=int, default=60)
    r.add_argument("-o", "--output", default="pricing.html")
    args = ap.parse_args(argv)

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    cur = cfg.get("currency", "")
    data = Data(args.db)
    try:
        today = pricing.parse_date(args.today) if args.today else date.today()
        if args.cmd == "log":
            data.log_night(pricing.parse_date(args.date), args.rooms, args.revenue, cfg["rooms"])
            print("saved")
        elif args.cmd == "import-nights":
            ok = bad = 0
            for n, row in read_csv(args.csv_file):
                try:
                    rev = float(row["revenue"]) if row.get("revenue") else None
                    data.log_night(pricing.parse_date(row["date"]), int(row["rooms"]), rev, cfg["rooms"])
                    ok += 1
                except (ValueError, KeyError) as e:
                    bad += 1
                    print(f"line {n}: {e}", file=sys.stderr)
            print(f"imported {ok}, rejected {bad}")
        elif args.cmd == "comp":
            data.log_competitor(pricing.parse_date(args.date), args.name, args.rate)
            print("saved")
        elif args.cmd == "import-comps":
            ok = bad = 0
            for n, row in read_csv(args.csv_file):
                try:
                    data.log_competitor(pricing.parse_date(row["date"]), row["name"], float(row["rate"]))
                    ok += 1
                except (ValueError, KeyError) as e:
                    bad += 1
                    print(f"line {n}: {e}", file=sys.stderr)
            print(f"imported {ok}, rejected {bad}")
        elif args.cmd in ("suggest", "report"):
            if not 1 <= args.days <= 366:
                raise ValueError("--days must be between 1 and 366")
            start = pricing.parse_date(args.start) if args.start else today
            rows = build_rows(data, cfg, start, args.days, today)
            if args.cmd == "suggest":
                for x in rows:
                    occ = f"{x['occupancy']:.0%}" if x["occupancy"] is not None else "  - "
                    comp = f"{cur}{x['competitor_median']:,.0f}" if x["competitor_median"] else "-"
                    print(f"{x['date'].strftime('%a %Y-%m-%d')}  {cur}{x['suggested']:>6,}  booked {occ:>4}  "
                          f"nearby {comp:>8}  | {'; '.join(x['reasons'])}")
            else:
                Path(args.output).write_text(report.render(cfg["property_name"], cur, rows), encoding="utf-8")
                print(f"wrote {args.output}")
        elif args.cmd == "summary":
            months = data.months_with_data()
            if not months:
                print("no nights logged yet")
            for m in months:
                y, mo = int(m[:4]), int(m[5:])
                st = pricing.month_stats(data.nights_in_month(y, mo), cfg["rooms"])
                occ = f"{st['occupancy']:.0%}" if st["occupancy"] is not None else "n/a"
                adr = f"{cur}{st['adr']:,.0f}" if st["adr"] else "n/a"
                rev = f"{cur}{st['revpar']:,.0f}" if st["revpar"] else "n/a"
                print(f"{m}  nights logged {st['nights']:>2}  occupancy {occ:>4}  ADR {adr:>8}  RevPAR {rev:>8}")
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        data.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
