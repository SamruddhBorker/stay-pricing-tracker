# stay-pricing-tracker

[![tests](https://github.com/SamruddhBorker/stay-pricing-tracker/actions/workflows/tests.yml/badge.svg)](https://github.com/SamruddhBorker/stay-pricing-tracker/actions/workflows/tests.yml)

Nightly rate suggestions and an occupancy log for small guesthouses, homestays
and villas in tourist destinations where demand swings hard with the season.

**The problem:** small owners guess their prices. Charge too little at Christmas
and you leave money on the table. Charge too much in the monsoon and the rooms
stay empty. This tool turns your own numbers into a clear suggested rate for each
night, and tells you *why*.

- Python 3.9+, **standard library only**, SQLite storage
- Every suggestion lists its reasons, so you stay in control
- Produces a shareable one-file HTML report with a chart
- Defaults are set up for **Goa**; edit one JSON file for anywhere else

## Quick start

```bash
python tracker.py log 2026-12-24 --rooms 8 --revenue 52000     # rooms booked that night (+ revenue)
python tracker.py comp 2026-12-24 "Sea View Inn" 6500           # a nearby place's advertised rate
python tracker.py suggest --days 30                             # suggested rates with reasons
python tracker.py summary                                       # occupancy, ADR, RevPAR by month
python tracker.py report --days 60 -o pricing.html              # report you can open or share
```

Bulk-load with `import-nights nights.csv` (`date,rooms,revenue`) and
`import-comps comps.csv` (`date,name,rate`).

## How a rate is worked out

1. **Season base** for the month (editable table in `config.json`)
2. **Events** (Christmas to New Year, Diwali, Carnival...) multiply the rate
3. **Weekday** uplift for Friday and Saturday
4. **Your bookings**: 80%+ booked pushes the price up; under 30% booked with a
   week to go gives a last-minute discount
5. **Nearby competitors**: blends in the *median* of rates you've entered (default 40% weight)
6. Clamped to your **floor and ceiling**, rounded to the nearest ₹50

Example output:

```
Fri 2026-11-20  ₹ 4,850  booked 88%  nearby ₹5,200  | base for November: ₹3,800; Fri x1.1;
                88% booked, demand is high x1.1; nearby places charge about ₹5,200 (blended 40%)
```

## Make it yours

Edit [`config.json`](config.json): number of rooms, currency, floor and ceiling,
monthly base rates, events and the occupancy rules.

**Please edit the event dates.** The Diwali and Carnival entries are examples
with placeholder dates for one year. Festival dates move every year, and only
`MM-DD` entries (like Christmas) repeat automatically.

## Honest limits

- It's a **rule-based heuristic, not a forecast**. It doesn't learn from your history
  and knows nothing about weather, flights or local news
- Competitor rates are **typed in by you**. The tool doesn't scrape any website
  (that would break most sites' terms and is fragile). A quick look at public
  listings once a week is enough
- Occupancy means rooms booked per night; there's no room-type or length-of-stay logic yet
- Defaults are starting points: calibrate them against your own last year's numbers

## Metrics

- **Occupancy** = rooms sold ÷ rooms available
- **ADR** = revenue ÷ rooms sold
- **RevPAR** = revenue ÷ rooms available (the single best health number)

## Layout

| File | Role |
|---|---|
| `tracker.py` | command-line interface |
| `pricing.py` | the pricing rules and metrics |
| `data.py` | SQLite storage |
| `report.py` | HTML report (all text is escaped) |
| `config.json` | your property and pricing rules |

## Tests

```bash
python -m unittest -v
```

## License

MIT
