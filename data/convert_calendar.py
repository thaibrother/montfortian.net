#!/usr/bin/env python3
"""
convert_calendar.py — Calendar_YYYY.csv → rome_calendar_YYYY.json

Usage:
    python3 convert_calendar.py Calendar_2026.csv

CSV columns expected:
    Date, Day, Liturgical Season/Sunday, Saints/Feasts,
    Special Days/Events, Historical Events, Deceased Brothers

Output: data/rome_calendar_YYYY.json (used by js/liturgical-calendar.js)
"""
import csv
import json
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: convert_calendar.py <Calendar_YYYY.csv>")
    sys.exit(1)

src = Path(sys.argv[1])
year = "".join(c for c in src.stem if c.isdigit())
if not year:
    print(f"❌ Cannot detect year in filename {src.name}")
    sys.exit(1)

out_dir = Path(__file__).resolve().parent
out = out_dir / f"rome_calendar_{year}.json"

cal = {}
with src.open(encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        date = row["Date"].strip()
        if not date:
            continue
        cal[date] = {
            "day": row.get("Day", "").strip(),
            "season": row.get("Liturgical Season/Sunday", "").strip(),
            "saints": row.get("Saints/Feasts", "").strip(),
            "special": row.get("Special Days/Events", "").strip(),
            "history": row.get("Historical Events", "").strip(),
            "deceased": row.get("Deceased Brothers", "").strip(),
        }

out.write_text(json.dumps(cal, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"✓ {len(cal)} days → {out}")
