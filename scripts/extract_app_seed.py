#!/usr/bin/env python3
"""
Extract the hardcoded SKILLED_OCCUPATIONS array from
expo-app/constants/skilledOccupations.ts into a JSON file so the Python
data pipeline can include those legacy/ANZSCO-2013 codes that aren't in
all-anzsco-occupations.json (ANZSCO 2022).

Output: public/app-seed-occupations.json
"""
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
APP_CONST = ROOT.parent / "expo-app" / "constants" / "skilledOccupations.ts"
OUT = ROOT / "public" / "app-seed-occupations.json"

if not APP_CONST.exists():
    print(f"ERR: not found: {APP_CONST}", file=sys.stderr)
    sys.exit(1)

text = APP_CONST.read_text()

# Each line looks like:
#   { anzsco: '111111', name: 'Chief Executive...', lists: ['CSOL'], visas: ['482', '186', '494'], assessingAuthority: 'VETASSESS', group: 'Managers' },
row_re = re.compile(
    r"\{\s*anzsco:\s*'(?P<anzsco>\d{6})'"
    r"\s*,\s*name:\s*'(?P<name>(?:[^'\\]|\\.)*)'"
    r"\s*,\s*lists:\s*\[(?P<lists>[^\]]*)\]"
    r"\s*,\s*visas:\s*\[(?P<visas>[^\]]*)\]"
    r"\s*,\s*assessingAuthority:\s*'(?P<auth>[^']*)'"
    r"\s*,\s*group:\s*'(?P<group>[^']*)'"
    r"\s*\}",
    re.MULTILINE,
)


def parse_array(s: str) -> list[str]:
    return [m.strip().strip("'").strip('"') for m in s.split(",") if m.strip()]


items = []
for m in row_re.finditer(text):
    items.append({
        "anzsco": m.group("anzsco"),
        "name": m.group("name").replace("\\'", "'"),
        "lists": parse_array(m.group("lists")),
        "visas": parse_array(m.group("visas")),
        "assessingAuthority": m.group("auth"),
        "group": m.group("group"),
    })

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps({
    "snapshotDate": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    "source": "Extracted from expo-app/constants/skilledOccupations.ts SKILLED_OCCUPATIONS",
    "count": len(items),
    "items": items,
}, indent=2))
print(f"Extracted {len(items)} occupations → {OUT}")
