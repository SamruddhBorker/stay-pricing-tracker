"""Self-contained HTML report (one file, no external resources)."""
from __future__ import annotations

from html import escape


def render(title: str, cur: str, rows: list[dict]) -> str:
    """rows: output of pricing.suggest() for consecutive days."""
    top = max([r["suggested"] for r in rows] + [r["competitor_median"] or 0 for r in rows] + [1])
    w, bar_w, h = max(len(rows) * 14 + 40, 300), 8, 140
    bars = []
    for i, r in enumerate(rows):
        x = 30 + i * 14
        hs = r["suggested"] / top * h
        bars.append(f'<rect x="{x}" y="{h + 10 - hs:.1f}" width="{bar_w}" height="{hs:.1f}" fill="#c2410c">'
                    f'<title>{escape(r["date"].isoformat())}: {escape(cur)}{r["suggested"]:,}</title></rect>')
        if r["competitor_median"]:
            hc = r["competitor_median"] / top * h
            bars.append(f'<circle cx="{x + bar_w / 2}" cy="{h + 10 - hc:.1f}" r="2.5" fill="#1d4ed8"/>')
    chart = (f'<svg viewBox="0 0 {w} {h + 30}" width="100%" role="img" '
             f'aria-label="Suggested rate per night (bars) and nearby competitor median (dots)">'
             f'{"".join(bars)}</svg>')
    body = []
    for r in rows:
        occ = f'{r["occupancy"]:.0%}' if r["occupancy"] is not None else "–"
        comp = f'{escape(cur)}{r["competitor_median"]:,.0f}' if r["competitor_median"] else "–"
        body.append(
            f'<tr><td>{r["date"].strftime("%a %d %b")}</td><td class="n"><b>{escape(cur)}{r["suggested"]:,}</b></td>'
            f'<td class="n">{occ}</td><td class="n">{comp}</td>'
            f'<td>{escape("; ".join(r["reasons"]))}</td></tr>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} pricing</title>
<style>
body{{font:15px/1.4 system-ui,sans-serif;margin:24px auto;max-width:980px;padding:0 16px;color:#1d2330}}
h1{{margin:0 0 4px}} .sub{{color:#6b7385;margin-bottom:16px}}
table{{border-collapse:collapse;width:100%}} th,td{{padding:6px 8px;border-bottom:1px solid #e6e2d9;text-align:left;vertical-align:top}}
.n{{text-align:right;white-space:nowrap}} th{{background:#f3f1ea}} .legend{{font-size:.85rem;color:#6b7385}}
</style></head><body>
<h1>{escape(title)}: suggested nightly rates</h1>
<div class="sub">Rule-based suggestions. Check them against your own judgement before changing prices.</div>
{chart}
<div class="legend">Bars: suggested rate. Dots: nearby competitor median.</div>
<table><thead><tr><th>Night</th><th class="n">Suggested</th><th class="n">Booked</th><th class="n">Nearby</th><th>Why</th></tr></thead>
<tbody>{"".join(body)}</tbody></table>
</body></html>
"""
