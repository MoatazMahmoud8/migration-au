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
import time
import subprocess
from datetime import date, datetime
from pathlib import Path

from bs4 import BeautifulSoup

try:
    from rounds_parser import parse_current_round, unescape_embedded_html
except ModuleNotFoundError:
    from scripts.rounds_parser import parse_current_round, unescape_embedded_html

# ─── Config ───────────────────────────────────────────────────────────────────

CURRENT_URL   = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds"
PREVIOUS_URL  = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/previous-rounds"
OUTPUT_PATH   = Path(__file__).parent.parent / "public" / "invitation-rounds.json"
TIMEOUT       = 30
HEADERS       = [
    "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "-H", "Accept-Language: en-AU,en;q=0.9,en-GB;q=0.8",
    "-H", "Accept-Encoding: gzip, deflate, br",
    "-H", "Referer: https://immi.homeaffairs.gov.au/",
    "-H", "Sec-Fetch-Dest: document",
    "-H", "Sec-Fetch-Mode: navigate",
    "-H", "Sec-Fetch-Site: same-origin",
    "-H", "Connection: keep-alive",
]

def fetch_url(url: str) -> str | None:
    """Fetch URL using curl first, fall back to Playwright for JS-rendered pages."""
    try:
        cmd = [
            "curl", "-s", "--max-time", str(TIMEOUT),
            "--compressed",
            "--http1.1",
        ] + HEADERS + [url]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT + 5,
        )
        
        if result.returncode == 0:
            html = result.stdout
            if '<table' in unescape_embedded_html(html).lower():
                return html
            log.info("curl returned no table content — trying Playwright for JS rendering")
    except Exception as e:
        log.warning("curl failed for %s: %s — trying Playwright", url, e)

    # Fallback: use Playwright to render JS-heavy pages
    return fetch_url_playwright(url)


def fetch_url_playwright(url: str) -> str | None:
    """Render a page with Playwright headless browser to get JS-rendered content."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page.goto(url, wait_until="networkidle", timeout=45000)
            # Wait for tables to appear (round data)
            try:
                page.wait_for_selector("table", timeout=15000)
            except Exception:
                log.warning("No tables appeared within 15s on %s", url)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        log.error("Playwright failed for %s: %s", url, e)
        return None

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
    html = fetch_url(CURRENT_URL)
    if not html:
        log.error("Failed to fetch current round page")
        return None
    
    # Add a small delay to appear human-like
    time.sleep(0.5)

    try:
        outcome = parse_current_round(html)
    except ValueError as error:
        log.error("Current round validation failed: %s", error)
        return None

    soup = BeautifulSoup(unescape_embedded_html(html), "html.parser")

    round_date = outcome["date"]
    sc189_total = outcome["sc189Total"]
    sc491_family_total = outcome["sc491FamilyTotal"]
    sc189_tiebreak = outcome["sc189TieBreak"]
    sc491_family_tiebreak = outcome["sc491FamilyTieBreak"]

    log.info("SC 189: %s invitations, tie break %s", sc189_total, sc189_tiebreak)
    log.info("SC 491 Family: %s invitations, tie break %s", sc491_family_total, sc491_family_tiebreak)

    # ── Extract per-occupation scores ─────────────────────────────────────────
    occupation_scores: list[dict] = []
    # Find "Invitations issued by occupation" table
    for tbl in soup.find_all("table"):
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
    These are cumulative EOIs nominated, not annual allocation quotas.
    """
    # Home Affairs table column order: ACT, NSW, NT, QLD, SA, TAS, VIC, WA.
    STATE_COLS = ["ACT", "NSW", "NT", "QLD", "SA", "TAS", "VIC", "WA"]

    log.info("Parsing state nomination totals…")
    html = fetch_url(CURRENT_URL)
    if not html:
        return None
    
    # Add a small delay to appear human-like
    time.sleep(0.5)

    soup = BeautifulSoup(unescape_embedded_html(html), "html.parser")
    sc190: dict[str, int] = {}
    sc491: dict[str, int] = {}
    period = ""
    reporting_period = ""

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
        page_text = soup.get_text(" ", strip=True)
        # Scope the program-year match to the State and Territory nominations section.
        state_text = page_text.split("State and Territory nominations", 1)[-1]
        m = re.search(r"(\d{4}[-–]\d{2,4})\s+program year", state_text, re.I)
        if m:
            period = f"{m.group(1)} program year"
        else:
            y = date.today().year
            start_year = y if date.today().month >= 7 else y - 1
            period = f"{start_year}-{str(start_year + 1)[-2:]} program year"

        date_match = re.search(
            r"from\s+(\d{1,2}\s+July\s+\d{4})\s+to\s+(\d{1,2}\s+\w+\s+\d{4})",
            state_text,
            re.I,
        )
        if date_match:
            reporting_period = f"{date_match.group(1)} – {date_match.group(2)}"
        log.info("State SC 190: %s", sc190)
        log.info("State SC 491: %s", sc491)
        return {
            "period": period,
            "reportingPeriod": reporting_period,
            "metric": "nominations-issued",
            "sc190": sc190,
            "sc491": sc491,
        }

    return None


def fetch_previous_rounds_list() -> list[dict]:
    """
    Fetches the dates of previous rounds from the previous-rounds index page.
    Returns a list of {'date': ISO, 'label': str} dicts (newest first).
    """
    log.info("Fetching previous rounds list…")
    html = fetch_url(PREVIOUS_URL)
    if not html:
        return []
    
    # Add a small delay to appear human-like
    time.sleep(0.5)

    soup = BeautifulSoup(unescape_embedded_html(html), "html.parser")
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
        log.error("Could not verify current round data. Existing JSON was not modified.")
        return 1

    new_round_date = current["round_date"]
    existing_round_date = (existing.get("currentRound") or {}).get("date", "")

    log.info("New round date: %s | Existing round date: %s", new_round_date, existing_round_date)

    # Determine if this is actually a new round
    is_new_round = new_round_date > existing_round_date

    log.info(
        "%s round %s. Refreshing verified values.",
        "New" if is_new_round else "Existing",
        new_round_date,
    )

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

    # Build full rounds history.
    # Always start from the existing rounds so hardcoded historical data is
    # never lost, even when DHA's "previous rounds" page only shows a limited
    # window.  We then overlay / prepend the new round on top.
    round_history: list[dict] = []
    seen_dates: set[str] = set()

    # New current round goes first — include occupation scores
    new_round_entry = {
        "date": new_round_date,
        "label": _iso_to_label(new_round_date),
        "sc189Total": current["sc189Total"],
        "sc189TieBreak": current["sc189TieBreak"],
        "sc491FamilyTotal": current["sc491FamilyTotal"],
        "sc491FamilyTieBreak": current["sc491FamilyTieBreak"],
        "occupationScores": current["occupationScores"],
    }
    round_history.append(new_round_entry)
    seen_dates.add(new_round_date)

    # Preserve ALL existing rounds (historical data must never be dropped)
    for existing_entry in existing.get("rounds", []):
        d = existing_entry.get("date")
        if d and d not in seen_dates:
            round_history.append(existing_entry)
            seen_dates.add(d)

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
        "migrationProgramPlanning": existing.get("migrationProgramPlanning", []),
        "stateNominations": sn,
        "stateAllocations": existing.get("stateAllocations", []),
        "occupationScores": occupation_scores,
        "rounds": round_history,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(new_data, f, indent=2, ensure_ascii=False)

    log.info("✅ invitation-rounds.json updated → %s (%d occupations, %d rounds)",
             OUTPUT_PATH, len(occupation_scores), len(round_history))
    return 0


def _iso_to_label(iso: str) -> str:
    """'2025-11-13' → '13 November 2025'"""
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%-d %B %Y")
    except ValueError:
        return iso


if __name__ == "__main__":
    sys.exit(main())
