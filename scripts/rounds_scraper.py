#!/usr/bin/env python3
"""
SkillSelect Invitation Rounds Scraper
======================================
Fetches the current SkillSelect invitation round from the Dept of Home Affairs,
parses per-occupation min points for SC 189 and SC 491 (Family Sponsored),
and updates public/invitation-rounds.json.

Exit codes:
  0  — no changes detected (already up to date)
  1  — error
  2  — new round detected and JSON updated
"""

import json
import logging
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ─── Config ───────────────────────────────────────────────────────────────────

CURRENT_URL   = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds"
PREVIOUS_URL  = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/previous-rounds"
OUTPUT_PATH   = Path(__file__).parent.parent / "public" / "invitation-rounds.json"
TIMEOUT       = 30
HEADERS       = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def parse_score(text: str) -> int | None:
    """Return integer points or None for N/A / blank."""
    t = text.strip()
    if not t or t.upper().startswith("N/A") or t == "*":
        return None
    # strip asterisks and whitespace
    t = t.rstrip("* \t\n")
    try:
        return int(t)
    except ValueError:
        return None


def parse_round_date(heading: str) -> str | None:
    """Extract ISO date from a heading like 'Invitations issued on 13 November 2025'."""
    m = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", heading, re.IGNORECASE)
    if not m:
        return None
    try:
        dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_tiebreak(text: str) -> str | None:
    """
    Extract 'YYYY-MM' from a tie-break cell like '11/2025' or 'November 2025'.
    """
    # MM/YYYY  or  M/YYYY
    m = re.search(r"(\d{1,2})/(\d{4})", text)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    # Month Year
    m = re.search(r"(\w+)\s+(\d{4})", text, re.IGNORECASE)
    if m:
        try:
            dt = datetime.strptime(f"1 {m.group(1)} {m.group(2)}", "%d %B %Y")
            return dt.strftime("%Y-%m")
        except ValueError:
            pass
    return None


def parse_total_invitations(text: str) -> int | None:
    """Extract integer from '10,000' or '10000'."""
    t = re.sub(r"[^\d]", "", text.strip())
    return int(t) if t else None

# ─── Scraper ──────────────────────────────────────────────────────────────────

def fetch_current_round() -> dict | None:
    """
    Fetches the current round page and returns a dict with:
      round_date, sc189Total, sc189TieBreak,
      sc491FamilyTotal, sc491FamilyTieBreak, occupationScores
    Returns None on failure.
    """
    log.info("Fetching current round page…")
    try:
        r = requests.get(CURRENT_URL, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as e:
        log.error("Failed to fetch current round page: %s", e)
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # ── Find "Current round" section ──────────────────────────────────────────
    # Look for a heading containing "Current round"
    current_section = None
    for tag in soup.find_all(["h2", "h3", "h4"]):
        if "current round" in tag.get_text(strip=True).lower():
            current_section = tag
            break

    if not current_section:
        log.error("Could not locate 'Current round' section on the page.")
        return None

    # ── Extract round date ────────────────────────────────────────────────────
    round_date = None
    # Walk siblings after current_section heading
    for sibling in current_section.find_next_siblings():
        heading_text = sibling.get_text(" ", strip=True)
        if "invitations issued on" in heading_text.lower():
            round_date = parse_round_date(heading_text)
            if round_date:
                log.info("Round date: %s", round_date)
                break
        # Also check sub-headings
        for tag in sibling.find_all(["h3", "h4", "h5", "strong"]):
            t = tag.get_text(" ", strip=True)
            if "invitations issued on" in t.lower():
                round_date = parse_round_date(t)
                if round_date:
                    break
        if round_date:
            break

    if not round_date:
        log.warning("Could not parse round date; will use today.")
        round_date = date.today().isoformat()

    # ── Extract total invitations (summary table) ─────────────────────────────
    sc189_total = None
    sc491_family_total = None
    sc189_tiebreak = None
    sc491_family_tiebreak = None

    # Find tables after "current round"
    for tbl in current_section.find_all_next("table"):
        rows = tbl.find_all("tr")
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if not cells:
                continue
            row_text = " ".join(cells).lower()
            # Summary row: SC 189 total invitations + tie break
            if "189" in cells[0] and "independent" in row_text:
                if len(cells) >= 3:
                    sc189_total = parse_total_invitations(cells[1])
                    sc189_tiebreak = parse_tiebreak(cells[2])
            elif "491" in cells[0] and "family" in row_text:
                if len(cells) >= 3:
                    sc491_family_total = parse_total_invitations(cells[1])
                    sc491_family_tiebreak = parse_tiebreak(cells[2])

        # Once we have both totals, stop looking
        if sc189_total and sc491_family_total is not None:
            break

    log.info("SC 189: %s invitations, tie break %s", sc189_total, sc189_tiebreak)
    log.info("SC 491 Family: %s invitations, tie break %s", sc491_family_total, sc491_family_tiebreak)

    # ── Extract per-occupation scores ─────────────────────────────────────────
    occupation_scores: list[dict] = []
    # Find "Invitations issued by occupation" table
    for tbl in current_section.find_all_next("table"):
        rows = tbl.find_all("tr")
        if len(rows) < 5:
            continue  # too small
        # Check first data row has occupation-like content (not just numbers)
        first_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
        if not first_cells or all(c.replace(",", "").replace(" ", "").isdigit() for c in first_cells if c):
            continue
        # This looks like the occupation table
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) < 2:
                continue
            name = cells[0].strip()
            # Skip header rows and footers
            if not name or name.lower() in {"occupation", "visa subclass", ""}:
                continue
            if name.lower().startswith("skilled"):
                continue
            sc189 = parse_score(cells[1]) if len(cells) > 1 else None
            sc491 = parse_score(cells[2]) if len(cells) > 2 else None
            occupation_scores.append({
                "name": name,
                "sc189": sc189,
                "sc491Family": sc491,
            })

        if occupation_scores:
            log.info("Parsed %d occupation rows.", len(occupation_scores))
            break

    if not occupation_scores:
        log.warning("No occupation scores parsed — HTML structure may have changed.")

    return {
        "round_date": round_date,
        "sc189Total": sc189_total or 0,
        "sc189TieBreak": sc189_tiebreak,
        "sc491FamilyTotal": sc491_family_total or 0,
        "sc491FamilyTieBreak": sc491_family_tiebreak,
        "occupationScores": occupation_scores,
    }


def fetch_state_nominations() -> dict | None:
    """
    Parses the state nomination totals from the current-round page.
    Returns {'period': str, 'sc190': {STATE: n}, 'sc491': {STATE: n}}
    """
    STATE_COLS = ["NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"]

    log.info("Parsing state nomination totals…")
    try:
        r = requests.get(CURRENT_URL, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    sc190: dict[str, int] = {}
    sc491: dict[str, int] = {}
    period = ""

    for tbl in soup.find_all("table"):
        rows = tbl.find_all("tr")
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if not cells:
                continue
            row_text = " ".join(cells).lower()
            if "190" in cells[0] and len(cells) >= len(STATE_COLS) + 1:
                nums = [parse_total_invitations(cells[i + 1]) or 0 for i in range(len(STATE_COLS))]
                sc190 = dict(zip(STATE_COLS, nums))
            elif "491" in cells[0] and "state" in row_text and len(cells) >= len(STATE_COLS) + 1:
                nums = [parse_total_invitations(cells[i + 1]) or 0 for i in range(len(STATE_COLS))]
                sc491 = dict(zip(STATE_COLS, nums))

    if sc190 or sc491:
        # Derive the program year from what's on the page (best effort)
        m = re.search(r"(\d{4}[-–]\d{2,4})", soup.get_text())
        if m:
            period = m.group(1)
        else:
            y = date.today().year
            period = f"{y}-{str(y + 1)[-2:]}"
        log.info("State SC 190: %s", sc190)
        log.info("State SC 491: %s", sc491)
        return {"period": period, "sc190": sc190, "sc491": sc491}

    return None


def fetch_previous_rounds_list() -> list[dict]:
    """
    Fetches the dates of previous rounds from the previous-rounds index page.
    Returns a list of {'date': ISO, 'label': str} dicts (newest first).
    """
    log.info("Fetching previous rounds list…")
    try:
        r = requests.get(PREVIOUS_URL, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("Could not fetch previous rounds: %s", e)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    rounds = []
    for tag in soup.find_all(["h2", "h3", "h4"]):
        text = tag.get_text(" ", strip=True)
        # Headings like "21 August 2025"
        d = parse_round_date(text)
        if d and re.match(r"\d{1,2}\s+\w+\s+\d{4}", text):
            rounds.append({"date": d, "label": text.strip()})

    # De-duplicate and sort newest-first
    seen = set()
    unique = []
    for r in rounds:
        if r["date"] not in seen:
            seen.add(r["date"])
            unique.append(r)
    unique.sort(key=lambda x: x["date"], reverse=True)
    log.info("Found %d previous round dates.", len(unique))
    return unique

# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    today = date.today().isoformat()

    # Load existing JSON
    existing: dict = {}
    if OUTPUT_PATH.exists():
        try:
            with open(OUTPUT_PATH, encoding="utf-8") as f:
                existing = json.load(f)
            log.info("Loaded existing invitation-rounds.json (lastUpdated: %s)",
                     existing.get("lastUpdated", "unknown"))
        except json.JSONDecodeError:
            log.warning("Existing JSON is invalid — will overwrite.")

    # Fetch current round
    current = fetch_current_round()
    if current is None:
        log.error("Aborting: could not fetch current round data.")
        return 1

    new_round_date = current["round_date"]
    existing_round_date = (existing.get("currentRound") or {}).get("date", "")

    log.info("New round date: %s | Existing round date: %s", new_round_date, existing_round_date)

    # Determine if this is actually a new round
    is_new_round = new_round_date > existing_round_date

    if not is_new_round and existing.get("occupationScores"):
        log.info("No new round detected. Updating lastUpdated only.")
        existing["lastUpdated"] = today
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        return 0

    log.info("New round detected (%s). Updating full dataset…", new_round_date)

    # Fetch state nominations
    state_noms = fetch_state_nominations()
    if state_noms:
        sn = state_noms
    else:
        # Fall back to existing data
        sn = existing.get("stateNominations", {
            "period": "",
            "sc190": {},
            "sc491": {},
        })

    # Fetch previous rounds list for history
    prev_rounds = fetch_previous_rounds_list()

    # Build full rounds history
    # Start with the new current round, then the history list
    round_history: list[dict] = []
    seen_dates: set[str] = set()

    # Current round goes first
    new_round_entry = {
        "date": new_round_date,
        "label": _iso_to_label(new_round_date),
        "sc189Total": current["sc189Total"],
        "sc189TieBreak": current["sc189TieBreak"],
        "sc491FamilyTotal": current["sc491FamilyTotal"],
        "sc491FamilyTieBreak": current["sc491FamilyTieBreak"],
    }
    round_history.append(new_round_entry)
    seen_dates.add(new_round_date)

    # Then any previous rounds from the index (dates only, no per-occ data)
    for pr in prev_rounds:
        if pr["date"] not in seen_dates and pr["date"] != new_round_date:
            # Try to find existing totals for this date
            existing_entry = next(
                (r for r in existing.get("rounds", []) if r["date"] == pr["date"]),
                None
            )
            entry: dict = {"date": pr["date"], "label": pr["label"]}
            if existing_entry:
                entry.update({k: v for k, v in existing_entry.items() if k not in entry})
            round_history.append(entry)
            seen_dates.add(pr["date"])

    # Sort history newest-first
    round_history.sort(key=lambda x: x["date"], reverse=True)

    # Build new JSON
    occupation_scores = current["occupationScores"]
    # Fall back to existing scores if scraper couldn't parse the table
    if not occupation_scores:
        log.warning("Using existing occupation scores as fallback.")
        occupation_scores = existing.get("occupationScores", [])

    new_data = {
        "lastUpdated": today,
        "sourceUrl": CURRENT_URL,
        "previousRoundsUrl": PREVIOUS_URL,
        "note": (
            "SC 190 and SC 491 (State/Territory Nominated) are managed by states "
            "independently — no departmental invitation rounds apply. "
            "SC 189 and SC 491 (Family Sponsored) rounds are issued by the Dept of Home Affairs."
        ),
        "currentRound": {
            "date": new_round_date,
            "label": _iso_to_label(new_round_date),
            "sc189Total": current["sc189Total"],
            "sc189TieBreak": current["sc189TieBreak"],
            "sc491FamilyTotal": current["sc491FamilyTotal"],
            "sc491FamilyTieBreak": current["sc491FamilyTieBreak"],
        },
        "stateNominations": sn,
        "occupationScores": occupation_scores,
        "rounds": round_history,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(new_data, f, indent=2, ensure_ascii=False)

    log.info("✅ invitation-rounds.json updated → %s (%d occupations, %d rounds)",
             OUTPUT_PATH, len(occupation_scores), len(round_history))
    return 2


def _iso_to_label(iso: str) -> str:
    """'2025-11-13' → '13 November 2025'"""
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%-d %B %Y")
    except ValueError:
        return iso


if __name__ == "__main__":
    sys.exit(main())
