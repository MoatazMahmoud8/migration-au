#!/usr/bin/env python3
import json
import sys
from pathlib import Path

import requests

from rounds_parser import parse_current_round


ROOT = Path(__file__).parent.parent
DATA_PATH = ROOT / "public" / "invitation-rounds.json"
SOURCE_URL = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds"


def normalise_round(round_data: dict) -> dict:
    return {
        "date": round_data.get("date"),
        "sc189Total": round_data.get("sc189Total", (round_data.get("sc189") or {}).get("total")),
        "sc189TieBreak": round_data.get("sc189TieBreak", (round_data.get("sc189") or {}).get("tieBreak")),
        "sc491FamilyTotal": round_data.get(
            "sc491FamilyTotal",
            (round_data.get("sc491Family") or {}).get("total"),
        ),
        "sc491FamilyTieBreak": round_data.get(
            "sc491FamilyTieBreak",
            (round_data.get("sc491Family") or {}).get("tieBreak"),
        ),
    }


def main() -> int:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    response = requests.get(SOURCE_URL, timeout=30)
    response.raise_for_status()
    official = parse_current_round(response.text)
    current = normalise_round(data.get("currentRound") or {})

    if current != official:
        print(f"Current round does not match Home Affairs:\nJSON: {current}\nDHA:  {official}", file=sys.stderr)
        return 1

    rounds = data.get("rounds") or []
    dates = [round_data.get("date") for round_data in rounds]
    if len(dates) != len(set(dates)):
        print("Round history contains duplicate dates", file=sys.stderr)
        return 1

    incomplete_dates = [
        round_data.get("date")
        for round_data in rounds
        if normalise_round(round_data)["sc189Total"] is None
        or normalise_round(round_data)["sc491FamilyTotal"] is None
    ]
    if incomplete_dates:
        print(f"Round history has missing invitation totals: {incomplete_dates}", file=sys.stderr)
        return 1

    matching_history = next(
        (normalise_round(round_data) for round_data in rounds if round_data.get("date") == official["date"]),
        None,
    )
    if matching_history != official:
        print(
            f"Current history entry does not match Home Affairs:\nJSON: {matching_history}\nDHA:  {official}",
            file=sys.stderr,
        )
        return 1

    planning_by_year = {
        item.get("financialYear"): item
        for item in data.get("migrationProgramPlanning", [])
    }
    planning_2026 = planning_by_year.get("2026-27")
    if not planning_2026:
        print("Missing 2026-27 Migration Program planning levels", file=sys.stderr)
        return 1
    if planning_2026["skilled"] + planning_2026["family"] + planning_2026["specialEligibility"] != planning_2026["total"]:
        print("2026-27 Migration Program categories do not equal the total", file=sys.stderr)
        return 1
    if planning_2026["onshore"] + planning_2026["offshore"] + planning_2026["specialEligibility"] != planning_2026["total"]:
        print("2026-27 onshore/offshore figures do not equal the total", file=sys.stderr)
        return 1
    if planning_2026["regional"] != 14110:
        print("2026-27 Regional planning level must be the official 14,110", file=sys.stderr)
        return 1

    print(
        f"Verified {official['date']}: SC 189={official['sc189Total']}, "
        f"SC 491 Family={official['sc491FamilyTotal']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())