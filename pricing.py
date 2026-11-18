"""Pricing engine: a transparent, rule-based nightly rate suggestion. Standard library only.

This is a heuristic, not a forecast. Every suggestion comes with the reasons behind it
so the owner can see why and override it.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median
from typing import Optional

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def parse_date(text: str) -> date:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"can't read date {text!r}; use YYYY-MM-DD") from None


def _event_hits(ev: dict, d: date) -> bool:
    """Events use 'YYYY-MM-DD' (one-off) or 'MM-DD' (every year, may wrap over New Year)."""
    s, e = ev["start"], ev["end"]
    if len(s) == 10:
        return parse_date(s) <= d <= parse_date(e)
    sm, sd = int(s[:2]), int(s[3:])
    em, ed = int(e[:2]), int(e[3:])
    cur, start, end = (d.month, d.day), (sm, sd), (em, ed)
    return start <= cur <= end if start <= end else (cur >= start or cur <= end)


def round_to(x: float, step: int) -> int:
    return int(x / step + 0.5) * step


def competitor_median(comps: dict[date, list[float]], d: date, window: int = 3) -> Optional[float]:
    """Median competitor rate for `d`, or the nearest date within `window` days."""
    for offset in range(window + 1):
        for cand in {d - timedelta(days=offset), d + timedelta(days=offset)}:
            if comps.get(cand):
                return float(median(comps[cand]))
    return None


def suggest(d: date, today: date, cfg: dict, booked_rooms: Optional[int],
            comps: dict[date, list[float]]) -> dict:
    reasons: list[str] = []
    cur = cfg.get("currency", "")
    base = float(cfg["season_base"][str(d.month)])
    reasons.append(f"base for {d.strftime('%B')}: {cur}{base:,.0f}")

    mult = 1.0
    hits = [ev for ev in cfg.get("events", []) if _event_hits(ev, d)]
    if hits:
        best = max(hits, key=lambda e: e["multiplier"])
        mult *= best["multiplier"]
        reasons.append(f"{best['name']} x{best['multiplier']}")
    wd = cfg.get("weekday_multiplier", {}).get(WEEKDAYS[d.weekday()], 1.0)
    if wd != 1.0:
        mult *= wd
        reasons.append(f"{WEEKDAYS[d.weekday()].title()} x{wd}")
    model = base * mult

    adj = model
    occ = None
    if booked_rooms is not None and cfg["rooms"] > 0:
        occ = booked_rooms / cfg["rooms"]
        if d >= today:
            o = cfg.get("occupancy", {})
            days_out = (d - today).days
            if occ >= o.get("high_threshold", 0.8):
                adj *= o.get("high_boost", 1.1)
                reasons.append(f"{occ:.0%} booked, demand is high x{o.get('high_boost', 1.1)}")
            elif occ <= o.get("low_threshold", 0.3) and days_out <= o.get("low_cut_within_days", 7):
                adj *= o.get("low_cut", 0.9)
                reasons.append(f"only {occ:.0%} booked with {days_out} days left x{o.get('low_cut', 0.9)}")

    cmed = competitor_median(comps, d)
    final = adj
    w = float(cfg.get("competitor_weight", 0.4))
    if cmed is not None:
        final = (1 - w) * adj + w * cmed
        reasons.append(f"nearby places charge about {cur}{cmed:,.0f} (blended {w:.0%})")

    lo, hi = float(cfg["floor_rate"]), float(cfg["ceiling_rate"])
    if final < lo:
        final = lo
        reasons.append(f"raised to your floor {cur}{lo:,.0f}")
    elif final > hi:
        final = hi
        reasons.append(f"capped at your ceiling {cur}{hi:,.0f}")
    suggested = max(round_to(final, int(cfg.get("round_to", 50))), int(lo))
    return {"date": d, "suggested": suggested, "model": round(model), "competitor_median": cmed,
            "occupancy": occ, "reasons": reasons}


def month_stats(rows: list[dict], rooms: int) -> dict:
    """rows: [{'date','rooms','revenue'}] for one period. Occupancy, ADR, RevPAR."""
    nights = len(rows)
    sold = sum(r["rooms"] for r in rows)
    with_rev = [r for r in rows if r.get("revenue") is not None]
    revenue = sum(r["revenue"] for r in with_rev)
    sold_with_rev = sum(r["rooms"] for r in with_rev)
    available = rooms * nights
    return {
        "nights": nights, "rooms_sold": sold,
        "occupancy": sold / available if available else None,
        "adr": revenue / sold_with_rev if sold_with_rev else None,       # average daily rate
        "revpar": revenue / available if available and with_rev else None,  # revenue per available room
        "revenue": revenue,
    }
