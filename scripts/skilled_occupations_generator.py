#!/usr/bin/env python3
"""
Generate public/skilled-occupations.json from the official federal combined list
plus best-effort state nomination lists.

Inputs (all in public/):
  - all-anzsco-occupations.json    (full ABS 2022 master list)
  - official-occupation-lists.json (federal combined list + state nomination lists)
"""

from __future__ import annotations

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

ASSESSING_AUTHORITIES = {
    "411411": "ANMAC",
    "1331": "VETASSESS", "1332": "VETASSESS",
    "2211": "CA ANZ / CPA Australia", "2212": "CA ANZ / CPA Australia",
    "2231": "IPA", "2232": "IPA",
    "2241": "VETASSESS", "2245": "VETASSESS",
    "2247": "VETASSESS",
    # 231 Air and Marine Transport Professionals — not engineering; VETASSESS Group B.
    "2311": "VETASSESS", "2312": "VETASSESS",
    # 232 Architects, Designers, Planners and Surveyors — NOT Engineers Australia.
    # (Was previously bucketed with 233 Engineering Professionals below, which wrongly
    # routed e.g. 232411 Graphic Designer to Engineers Australia instead of VETASSESS.)
    "2321": "VETASSESS", "2322": "VETASSESS", "2323": "VETASSESS",
    "2324": "VETASSESS", "2325": "VETASSESS", "2326": "VETASSESS",
    # 233 Engineering Professionals — the real Engineers Australia unit groups.
    "2331": "Engineers Australia", "2332": "Engineers Australia",
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
    "2541": "ANMAC",
    "2544": "ANMAC",
    "2611": "ACS", "2612": "ACS", "2613": "ACS",
    "2621": "ACS", "2631": "ACS", "2632": "ACS",
    "2711": "SLAA", "2712": "SLAA", "2713": "SLAA",
    "3": "TRA",
}

OCCUPATION_OVERRIDES = {
    "251511": {"authority": "APharmC"},
    "251512": {"authority": "VETASSESS"},
    "251513": {"authority": "APharmC"},
    "263311": {"authority": "Engineers Australia"},
    "263312": {"authority": "Engineers Australia"},
}

ALLOWED_STATES = {"NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"}

# Repealed/obsolete visa subclasses that still show up in upstream source
# data (e.g. official-occupation-lists.json) but no longer exist as valid
# pathways. SC 489 (Skilled Regional (Provisional)) closed in Nov 2019 and
# was replaced by SC 491 -- 481 of 685 occupations still carried it before
# this filter. SC 887 is 489's/495's permanent follow-on, also repealed.
BANNED_VISAS = {"489", "887"}


def get_group_name(anzsco: str) -> str:
    if anzsco:
        return ANZSCO_GROUPS.get(anzsco[0], "Various")
    return "Various"


def get_assessing_authority(anzsco: str) -> str | None:
    auth = ASSESSING_AUTHORITIES.get(anzsco)
    if auth:
        return auth
    if len(anzsco) >= 4:
        auth = ASSESSING_AUTHORITIES.get(anzsco[:4])
        if auth:
            return auth
    if anzsco:
        auth = ASSESSING_AUTHORITIES.get(anzsco[0])
        if auth:
            return auth
    return None


def main() -> int:
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat()

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

    name_lookup: dict[str, dict] = {}
    for item in all_items:
        code = str(item.get("anzsco", "")).strip()
        if code:
            name_lookup[code] = item

    federal_occupations = official_data.get("federal", {}).get("occupations", [])
    federal_by_code: dict[str, dict] = {}
    ignored_non_master = 0
    for item in federal_occupations:
        code = str(item.get("anzsco", "")).strip()
        if not code:
            continue
        if code not in name_lookup:
            ignored_non_master += 1
            continue
        entry = federal_by_code.setdefault(code, {
            "lists": set(),
            "visas": set(),
            "assessingAuthority": None,
            "name": item.get("name") or name_lookup[code].get("name") or f"ANZSCO {code}",
        })
        entry["lists"].update(item.get("lists", []))
        entry["visas"].update(str(v) for v in item.get("visas", []) if str(v) not in BANNED_VISAS)
        if item.get("assessingAuthority"):
            entry["assessingAuthority"] = item["assessingAuthority"]

    log.info("Federal combined occupations matched to ABS 2022 master: %d", len(federal_by_code))
    if ignored_non_master:
        log.info("Ignored %d federal entries not present in ABS 2022 master", ignored_non_master)

    states_data = official_data.get("states", {})
    state_190: dict[str, set[str]] = {}
    state_491: dict[str, set[str]] = {}
    for state_code, state_info in states_data.items():
        if state_code not in ALLOWED_STATES:
            continue
        codes_190 = {code for code in state_info.get("190", []) if code in name_lookup}
        codes_491 = {code for code in state_info.get("491", []) if code in name_lookup}
        if codes_190:
            state_190[state_code] = codes_190
        if codes_491:
            state_491[state_code] = codes_491
        log.info("  %s: 190=%d, 491=%d", state_code, len(codes_190), len(codes_491))

    all_state_codes: set[str] = set()
    for codes in state_190.values():
        all_state_codes.update(codes)
    for codes in state_491.values():
        all_state_codes.update(codes)

    eligible_codes = set(federal_by_code) | all_state_codes
    log.info("Total eligible occupations (federal or any state): %d", len(eligible_codes))

    items: list[dict] = []
    for code in sorted(eligible_codes):
        info = name_lookup.get(code, {})
        federal = federal_by_code.get(code, {})
        override = OCCUPATION_OVERRIDES.get(code)

        name = federal.get("name") or info.get("name") or f"ANZSCO {code}"
        group = info.get("group") or get_group_name(code)

        lists = sorted(set(federal.get("lists", set())))
        visas = sorted(set(federal.get("visas", set())))

        states: dict[str, list[str]] = {}
        for state_code in sorted(ALLOWED_STATES):
            state_visas: list[str] = []
            if state_code in state_190 and code in state_190[state_code]:
                state_visas.append("190")
            if state_code in state_491 and code in state_491[state_code]:
                state_visas.append("491")
            if state_visas:
                states[state_code] = state_visas
                visas = sorted(set(visas) | set(state_visas))

        authority = (
            (override or {}).get("authority")
            or federal.get("assessingAuthority")
            or info.get("assessingAuthority")
            or get_assessing_authority(code)
        )

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

    output = {
        "snapshotDate": today,
        "lastUpdated": now,
        "source": "Department of Home Affairs combined list + state nomination programs",
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
