import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pricing
import report
import tracker
from data import Data

CFG = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
TODAY = date(2026, 11, 1)


def s(d, booked=None, comps=None, today=TODAY, cfg=None):
    return pricing.suggest(d, today, cfg or CFG, booked, comps or {})


class RuleTests(unittest.TestCase):
    def test_base_season_and_weekday(self):
        # 20 Nov 2026 is a Friday: 3800 base x1.10 = 4180 -> 4200
        r = s(date(2026, 11, 20))
        self.assertEqual(r["suggested"], 4200)
        # Wednesday 18 Nov: just the base
        self.assertEqual(s(date(2026, 11, 18))["suggested"], 3800)

    def test_monsoon_hits_floor_not_below(self):
        r = s(date(2026, 7, 15))   # base 1800 = floor; Wednesday
        self.assertEqual(r["suggested"], 1800)
        cfg = dict(CFG, floor_rate=2000)
        r = s(date(2026, 7, 15), cfg=cfg)
        self.assertEqual(r["suggested"], 2000)
        self.assertTrue(any("floor" in x for x in r["reasons"]))

    def test_event_wraps_over_new_year(self):
        for d in (date(2026, 12, 25), date(2027, 1, 1), date(2027, 1, 2), date(2026, 12, 20)):
            self.assertTrue(any("Christmas" in x for x in s(d)["reasons"]), d)
        self.assertFalse(any("Christmas" in x for x in s(date(2027, 1, 3))["reasons"]))
        self.assertFalse(any("Christmas" in x for x in s(date(2026, 12, 19))["reasons"]))

    def test_one_off_event_dates(self):
        self.assertTrue(any("Diwali" in x for x in s(date(2026, 11, 8))["reasons"]))
        self.assertFalse(any("Diwali" in x for x in s(date(2026, 11, 11))["reasons"]))

    def test_ceiling_cap(self):
        cfg = dict(CFG, ceiling_rate=5000)
        r = s(date(2026, 12, 26), cfg=cfg)   # Saturday in the festive window
        self.assertEqual(r["suggested"], 5000)
        self.assertTrue(any("ceiling" in x for x in r["reasons"]))

    def test_high_occupancy_raises_price(self):
        base = s(date(2026, 11, 18))["suggested"]
        hot = s(date(2026, 11, 18), booked=7)["suggested"]    # 87.5% booked
        self.assertGreater(hot, base)

    def test_low_occupancy_last_minute_discount_only_when_close(self):
        today = date(2026, 11, 15)
        base = s(date(2026, 11, 18), today=today)["suggested"]
        close = s(date(2026, 11, 18), booked=1, today=today)["suggested"]   # 3 days out, 12.5%
        self.assertLess(close, base)
        far = s(date(2026, 11, 18), booked=1, today=date(2026, 11, 1))["suggested"]  # 17 days out
        self.assertEqual(far, base)

    def test_past_dates_ignore_occupancy_signal(self):
        past = s(date(2026, 10, 14), booked=8, today=TODAY)
        self.assertFalse(any("demand" in x for x in past["reasons"]))

    def test_competitor_blend(self):
        d = date(2026, 11, 18)
        r = s(d, comps={d: [5000.0, 5000.0, 5000.0]})
        own = 3800
        expected = pricing.round_to(0.6 * own + 0.4 * 5000, 50)
        self.assertEqual(r["suggested"], expected)

    def test_competitor_nearby_date_fallback(self):
        d = date(2026, 11, 18)
        comps = {date(2026, 11, 20): [5000.0]}
        self.assertEqual(pricing.competitor_median(comps, d), 5000.0)
        self.assertIsNone(pricing.competitor_median({date(2026, 12, 1): [1.0]}, d))

    def test_median_not_mean(self):
        d = date(2026, 11, 18)
        self.assertEqual(pricing.competitor_median({d: [3000.0, 3200.0, 99999.0]}, d), 3200.0)

    def test_rounding(self):
        self.assertEqual(pricing.round_to(4180, 50), 4200)
        self.assertEqual(pricing.round_to(4174, 50), 4150)
        self.assertEqual(pricing.round_to(4175, 50), 4200)

    def test_bad_date(self):
        with self.assertRaises(ValueError):
            pricing.parse_date("20/11/2026")


class StatsTests(unittest.TestCase):
    def test_month_stats(self):
        rows = [{"date": "2026-11-01", "rooms": 4, "revenue": 16000.0},
                {"date": "2026-11-02", "rooms": 8, "revenue": 36000.0}]
        st = pricing.month_stats(rows, 8)
        self.assertAlmostEqual(st["occupancy"], 12 / 16)
        self.assertAlmostEqual(st["adr"], 52000 / 12)
        self.assertAlmostEqual(st["revpar"], 52000 / 16)

    def test_stats_without_revenue(self):
        st = pricing.month_stats([{"date": "2026-11-01", "rooms": 4, "revenue": None}], 8)
        self.assertEqual(st["occupancy"], 0.5)
        self.assertIsNone(st["adr"])
        self.assertIsNone(st["revpar"])

    def test_empty(self):
        self.assertIsNone(pricing.month_stats([], 8)["occupancy"])


class DataTests(unittest.TestCase):
    def test_log_validation_and_upsert(self):
        d = Data()
        with self.assertRaises(ValueError):
            d.log_night(date(2026, 11, 1), 9, None, 8)
        with self.assertRaises(ValueError):
            d.log_night(date(2026, 11, 1), 2, -5.0, 8)
        d.log_night(date(2026, 11, 1), 2, 8000.0, 8)
        d.log_night(date(2026, 11, 1), 3, None, 8)   # update rooms, keep revenue
        row = d.nights_in_month(2026, 11)[0]
        self.assertEqual((row["rooms"], row["revenue"]), (3, 8000.0))

    def test_competitor_validation(self):
        d = Data()
        for bad in (("", 100.0), ("X", 0.0), ("X", -3.0)):
            with self.assertRaises(ValueError):
                d.log_competitor(date(2026, 11, 1), *bad)


class CliTests(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as t:
            db = str(Path(t) / "s.db")
            base = ["--db", db, "--today", "2026-11-15"]
            self.assertEqual(tracker.main(base + ["log", "2026-11-20", "--rooms", "7", "--revenue", "30000"]), 0)
            self.assertEqual(tracker.main(base + ["log", "2026-11-21", "--rooms", "99"]), 1)
            self.assertEqual(tracker.main(base + ["comp", "2026-11-20", "Sea View Inn", "5200"]), 0)
            f = Path(t) / "c.csv"
            with open(f, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["date", "name", "rate"])
                w.writerow(["2026-11-21", "Palm Inn", "4800"])
                w.writerow(["bad", "X", "1"])
            self.assertEqual(tracker.main(base + ["import-comps", str(f)]), 0)
            self.assertEqual(tracker.main(base + ["suggest", "--days", "10"]), 0)
            self.assertEqual(tracker.main(base + ["summary"]), 0)
            out = Path(t) / "r.html"
            self.assertEqual(tracker.main(base + ["report", "--days", "10", "-o", str(out)]), 0)
            html = out.read_text(encoding="utf-8")
            self.assertIn("<svg", html)
            self.assertEqual(tracker.main(base + ["suggest", "--days", "0"]), 1)

    def test_report_escapes_html(self):
        rows = [pricing.suggest(date(2026, 11, 18), TODAY, CFG, None, {})]
        rows[0]["reasons"] = ["<script>alert(1)</script>"]
        html = report.render("<b>My</b> Place", "₹", rows)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<b>My</b>", html)


if __name__ == "__main__":
    unittest.main()
