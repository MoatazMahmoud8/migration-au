#!/usr/bin/env python3
"""
skilled_occupations_generator.py
================================
Merges existing data sources to produce public/skilled-occupations.json.

Inputs (all in public/):
  - all-anzsco-occupations.json    (878 items — full ANZSCO code list)
  - official-occupation-lists.json (CSOL federal list + state nomination lists)

Output:
  - public/skilled-occupations.json

Schema (must match app's utils/remoteSchema.ts validateOccupationsSnapshot):
{
  "snapshotDate": "YYYY-MM-DD",
  "items": [
    {
      "anzsco": "261312",
      "name": "Developer Programmer",
      "group": "ICT Professionals",
      "lists": ["CSOL", "MLTSSL"],
      "visas": ["189", "190", "491"],
      "assessingAuthority": "ACS",
      "states": {
        "NSW": ["190", "491"],
        "VIC": ["190"]
      }
    }
  ]
}

Exit codes:
  0 — success
  1 — error
"""

import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"

ANZSCO_FILE = PUBLIC / "all-anzsco-occupations.json"
OFFICIAL_LISTS_FILE = PUBLIC / "official-occupation-lists.json"
OUTPUT = PUBLIC / "skilled-occupations.json"

# ANZSCO group codes → readable major group names
ANZSCO_GROUPS = {
    "1": "Managers",
    "2": "Professionals",
    "3": "Technicians and Trades Workers",
    "4": "Community and Personal Service Workers",
    "5": "Clerical and Administrative Workers",
    "6": "Sales Workers",
    "7": "Machinery Operators and Drivers",
    "8": "Labourers",
}

# Known assessing authorities by common ANZSCO prefixes/codes
# This is a simplified mapping — the full list is on DHA's site
ASSESSING_AUTHORITIES = {
    "1331": "VETASSESS", "1332": "VETASSESS",
    "2211": "CA ANZ / CPA Australia", "2212": "CA ANZ / CPA Australia",
    "2231": "IPA", "2232": "IPA",
    "2241": "VETASSESS", "2245": "VETASSESS",
    "2247": "VETASSESS",
    "2311": "Engineers Australia", "2312": "Engineers Australia",
    "2313": "Engineers Australia", "2321": "Engineers Australia",
    "2322": "Engineers Australia", "2323": "Engineers Australia",
    "2324": "Engineers Australia", "2325": "Engineers Australia",
    "2326": "Engineers Australia", "2332": "Engineers Australia",
    "2333": "Engineers Australia", "2334": "Engineers Australia",
    "2335": "Engineers Australia", "2336": "Engineers Australia",
    "2339": "Engineers Australia",
    "2341": "VETASSESS",
    "2346": "VETASSESS",
    "2347": "VETASSESS",
    "2411": "AITSL", "2412": "AITSL", "2413": "AITSL",
    "2414": "AITSL", "2415": "AITSL",
    "2491": "VETASSESS",
    "2511": "ANMAC", "2512": "ANMAC", "2513": "ANMAC",
    "2514": "ANMAC",
    "2521": "VETASSESS", "2523": "VETASSESS",
    "2524": "AASW", "2525": "VETASSESS",
    "2531": "Medical Board",
    "2532": "Medical Board",
    "2533": "Medical Board",
    "2534": "Medical Board",
    "2535": "Medical Board",
    "2539": "Medical Board",
    "2541": "VETASSESS",
    "2544": "VETASSESS",
    "2611": "ACS", "2612": "ACS", "2613": "ACS",
    "2621": "ACS", "2631": "ACS", "2632": "ACS",
    "2633": "ACS",
    "2711": "SLAA", "2712": "SLAA", "2713": "SLAA",
    "3": "TRA",  # Default for trades
}

# Visas eligible for CSOL occupations
CSOL_VISAS = ["189", "190", "491", "482", "494", "186"]
STATE_VISAS = ["190", "491"]

ALLOWED_STATES = {"NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"}


def get_group_name(anzsco: str) -> str:
    """Derive a readable group name from the ANZSCO code."""
    if len(anzsco) >= 1:
        major = ANZSCO_GROUPS.get(anzsco[0], "Various")
        return major
    return "Various"


def get_assessing_authority(anzsco: str) -> str | None:
    """Look up the assessing authority for an ANZSCO code."""
    # Try full 4-digit unit group first
    if len(anzsco) >= 4:
        auth = ASSESSING_AUTHORITIES.get(anzsco[:4])
        if auth:
            return auth
    # Try 1-digit major group (trades default to TRA)
    if len(anzsco) >= 1:
        auth = ASSESSING_AUTHORITIES.get(anzsco[0])
        if auth:
            return auth
    return None


def main() -> int:
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat()

    # Load inputs
    if not ANZSCO_FILE.exists():
        log.error("Missing %s", ANZSCO_FILE)
        return 1
    if not OFFICIAL_LISTS_FILE.exists():
        log.error("Missing %s", OFFICIAL_LISTS_FILE)
        return 1

    anzsco_data = json.loads(ANZSCO_FILE.read_text(encoding="utf-8"))
    official_data = json.loads(OFFICIAL_LISTS_FILE.read_text(encoding="utf-8"))

    all_items = anzsco_data.get("items", [])
    log.info("Loaded %d ANZSCO occupations", len(all_items))

    # Build federal CSOL set
    federal = official_data.get("federal", {})
    csol_codes: set[str] = set(federal.get("CSOL_anzscos", []))
    log.info("Federal CSOL: %d ANZSCO codes", len(csol_codes))

    # Build state nomination maps: state → set of ANZSCO codes (across all visa types)
    states_data = official_data.get("states", {})
    state_190: dict[str, set[str]] = {}
    state_491: dict[str, set[str]] = {}
    for state_code, state_info in states_data.items():
        if state_code not in ALLOWED_STATES:
            continue
        codes_190 = set(state_info.get("190", []))
        codes_491 = set(state_info.get("491", []))
        if codes_190:
            state_190[state_code] = codes_190
        if codes_491:
            state_491[state_code] = codes_491
        log.info("  %s: 190=%d, 491=%d", state_code, len(codes_190), len(codes_491))

    # Generate skilled-occupations items
    # Only include occupations that appear on at least one list (federal CSOL or any state)
    all_state_codes: set[str] = set()
    for codes in state_190.values():
        all_state_codes.update(codes)
    for codes in state_491.values():
        all_state_codes.update(codes)

    eligible_codes = csol_codes | all_state_codes
    log.info("Total eligible occupations (on any list): %d", len(eligible_codes))

    # Build name lookup from all-anzsco
    name_lookup: dict[str, dict] = {}
    for item in all_items:
        code = str(item.get("anzsco", "")).strip()
        if code:
            name_lookup[code] = item

    # Generate output items
    items: list[dict] = []
    for code in sorted(eligible_codes):
        info = name_lookup.get(code, {})
        name = info.get("name", f"ANZSCO {code}")
        group = info.get("group", "")
        if not group or group == "Various":
            group = get_group_name(code)

        # Determine which lists this occupation is on
        lists: list[str] = []
        if code in csol_codes:
            lists.append("CSOL")

        # Determine eligible visas
        visas: list[str] = []
        if code in csol_codes:
            visas = list(CSOL_VISAS)
        else:
            # State-only nominations get 190/491
            visas = list(STATE_VISAS)

        # Determine state availability
        states: dict[str, list[str]] = {}
        for state_code in sorted(ALLOWED_STATES):
            state_visas: list[str] = []
            if state_code in state_190 and code in state_190[state_code]:
                state_visas.append("190")
            if state_code in state_491 and code in state_491[state_code]:
                state_visas.append("491")
            if state_visas:
                states[state_code] = state_visas

        # Assessing authority
        authority = info.get("assessingAuthority") or get_assessing_authority(code)

        item: dict = {
            "anzsco": code,
            "name": name,
            "group": group,
            "lists": lists,
            "visas": visas,
        }
        if authority:
            item["assessingAuthority"] = authority
        if states:
            item["states"] = states

        items.append(item)

    log.info("Generated %d skilled occupation items", len(items))

    # Write output
    output = {
        "snapshotDate": today,
        "lastUpdated": now,
        "source": "Federal skilled occupation lists + state nomination programs",
        "items": items,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    size_kb = OUTPUT.stat().st_size / 1024
    log.info("✅ skilled-occupations.json updated → %.1f KB (%d items)", size_kb, len(items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
