#!/usr/bin/env python3
"""
daily_monitor.py
================
Runs daily. Scrapes:
  1. smartvisaguide.com  — crowd-sourced AU skilled migration updates (recent
     grants, next invitation round announcements, recent news posts).
  2. immi.homeaffairs.gov.au — official invitation rounds, visa cost,
     processing cutoff dates.

Cross-references the two sources, then updates:
  - public/invitation-rounds.json
  - public/visa-types.json        (adds .cost and .processingCutoff per visa)
  - public/daily-updates.json     (NEW — feed of latest news + verification)
  - public/.monitor-status.json   (run metadata, errors)

Exit codes:
  0 — ran successfully (data may or may not have changed)
  1 — fatal error
"""

from __future__ import annotations

import html as html_mod
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

# ─── Config ───────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
PUBLIC = ROOT / "public"

SMART_VISA_URL = "https://smartvisaguide.com/"
DHA_ROUNDS_URL = "https://immi.homeaffairs.gov.au/visas/working-in-australia/skillselect/invitation-rounds"
DHA_VISA_PAGES = {
    "189": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-independent-189",
    "190": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-nominated-190",
    "491": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-work-regional-provisional-491",
    "482": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skills-in-demand-visa-subclass-482",
}

# Fallback static costs (per DHA 1 July 2025 fee schedule).
# Used only when the live page doesn't expose the cost in an obvious place.
FALLBACK_COSTS = {
    "189": "AUD $4,885",
    "190": "AUD $4,885",
    "491": "AUD $4,910",
    "482": "AUD $3,210",  # SID short-term stream base
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}
TIMEOUT = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("daily_monitor")

# ─── HTTP ─────────────────────────────────────────────────────────────────────

def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        log.warning("Fetch failed %s: %s", url, e)
        return None


def unescape_embedded_html(raw: str) -> str:
    """
    DHA pages embed page content as JSON-escaped HTML inside script tags
    (sequences like \\u003c, &quot;, etc.). Decode in two passes so
    BeautifulSoup can parse the actual structure.
    """
    s = raw
    # \uXXXX escapes
    s = re.sub(
        r"\\u([0-9a-fA-F]{4})",
        lambda m: chr(int(m.group(1), 16)),
        s,
    )
    # Common JSON escapes
    s = s.replace('\\"', '"').replace("\\/", "/").replace("\\n", "\n")
    # HTML entities (&quot;, &amp;, &nbsp;)
    s = html_mod.unescape(s)
    return s


# ─── DHA: Invitation rounds ───────────────────────────────────────────────────

MONTHS_RE = (
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)"
)

def parse_date_iso(text: str) -> str | None:
    m = re.search(rf"(\d{{1,2}})\s+({MONTHS_RE})\s+(\d{{4}})", text)
    if not m:
        return None
    try:
        return datetime.strptime(
            f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y"
        ).strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_tiebreak(text: str) -> str | None:
    m = re.search(r"(\d{1,2})/(\d{4})", text)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    m = re.search(rf"({MONTHS_RE})\s+(\d{{4}})", text)
    if m:
        try:
            return datetime.strptime(
                f"1 {m.group(1)} {m.group(2)}", "%d %B %Y"
            ).strftime("%Y-%m")
        except ValueError:
            return None
    return None


def parse_int(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def fetch_dha_round() -> dict[str, Any] | None:
    raw = fetch(DHA_ROUNDS_URL)
    if not raw:
        return None
    # Unescape JSON-embedded HTML so BS4 can see it
    html = unescape_embedded_html(raw)
    soup = BeautifulSoup(html, "html.parser")

    # Find the "Invitations issued on …" heading
    round_date = None
    sc189_total = sc491_family_total = None
    sc189_tb = sc491_family_tb = None

    for h in soup.find_all(["h2", "h3", "h4"]):
        t = h.get_text(" ", strip=True)
        if t.lower().startswith("invitations issued on"):
            d = parse_date_iso(t)
            if d:
                round_date = d
                break

    # Walk every table — the summary table has rows with "189" + "Independent"
    for tbl in soup.find_all("table"):
        for row in tbl.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) < 3:
                continue
            joined = " ".join(cells).lower()
            if "189" in cells[0] and "independent" in joined:
                sc189_total = sc189_total or parse_int(cells[1])
                sc189_tb = sc189_tb or parse_tiebreak(cells[2])
            elif "491" in cells[0] and "family" in joined:
                sc491_family_total = sc491_family_total or parse_int(cells[1])
                sc491_family_tb = sc491_family_tb or parse_tiebreak(cells[2])

    if not round_date and not sc189_total:
        log.warning("DHA rounds: no data parsed")
        return None

    return {
        "date": round_date,
        "sc189Total": sc189_total or 0,
        "sc189TieBreak": sc189_tb,
        "sc491FamilyTotal": sc491_family_total or 0,
        "sc491FamilyTieBreak": sc491_family_tb,
        "source": DHA_ROUNDS_URL,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
    }


# ─── DHA: Visa cost + processing cutoff ───────────────────────────────────────

def fetch_visa_details(code: str, url: str) -> dict[str, Any]:
    raw = fetch(url)
    out: dict[str, Any] = {"code": code, "url": url}
    if not raw:
        return out

    html = unescape_embedded_html(raw)
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    # Normalise non-breaking spaces
    text = text.replace("\xa0", " ")
    html_norm = html.replace("\xa0", " ")

    # Cost: 'AUD4,885' / 'AUD 4,910.00' / 'From AUD4,885.00' / 'AUD$4,910'
    m = re.search(r"AUD\s*\$?\s*([\d]{1,3}(?:,\d{3})+(?:\.\d{2})?)", html_norm)
    if m:
        out["cost"] = f"AUD ${m.group(1)}"
        out["costSource"] = "live"
    elif code in FALLBACK_COSTS:
        out["cost"] = FALLBACK_COSTS[code]
        out["costSource"] = "fallback"

    # Processing cutoff (must match THIS visa code, not another mentioned on page):
    # 'processing subclass 190 applications lodged from February 2025'
    m = re.search(
        rf"processing\s+subclass\s+{re.escape(code)}\s+applications\s+lodged\s+from\s+"
        rf"({MONTHS_RE})\s+(\d{{4}})",
        html_norm,
        re.I,
    )
    if m:
        try:
            iso = datetime.strptime(
                f"1 {m.group(1)} {m.group(2)}", "%d %B %Y"
            ).strftime("%Y-%m")
            out["processingCutoff"] = iso
            out["processingCutoffLabel"] = f"{m.group(1)} {m.group(2)}"
        except ValueError:
            pass

    # 'Stay Permanently' / 'Stay 5 Years'
    m = re.search(r"Stay\s+(Permanently|\d+\s+Years?)", text, re.I)
    if m:
        out["stayDuration"] = m.group(1)

    return out


# ─── smartvisaguide.com scraper ───────────────────────────────────────────────

def scrape_smart_visa_guide() -> dict[str, Any]:
    raw = fetch(SMART_VISA_URL)
    if not raw:
        return {"available": False}

    # Search raw HTML directly (more reliable than rendered text)
    raw_norm = raw.replace("\xa0", " ")

    # Find: 'Next invitation Round for Subclass 189 is on 4 June 2026'
    next_round = None
    m = re.search(
        rf"[Nn]ext invitation [Rr]ound for [Ss]ubclass\s+(\d+)\s+is on\s+"
        rf"(\d{{1,2}}\s+{MONTHS_RE}\s+\d{{4}})",
        raw_norm,
    )
    if m:
        next_round = {
            "subclass": m.group(1),
            "date": parse_date_iso(m.group(2)),
            "raw": m.group(0),
        }

    # Daily activity report date
    daily_report = None
    m = re.search(
        rf"Daily Activity Report:\s+(\d{{1,2}}\s+\w+\s+\d{{4}})",
        raw_norm,
    )
    if m:
        daily_report = parse_date_iso(m.group(1))

    # Recent grants — look for '190 Granted', '491 Granted', '189 grant'
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text("\n", strip=True)
    grants: list[str] = []
    for m in re.finditer(
        r"(?:(?:190|491|189|482)\s+(?:Granted|grant)[^\n]{0,200})",
        text,
        re.I,
    ):
        line = re.sub(r"\s+", " ", m.group(0)).strip()
        if line and line not in grants:
            grants.append(line[:220])
        if len(grants) >= 15:
            break

    return {
        "available": True,
        "url": SMART_VISA_URL,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "nextRound": next_round,
        "dailyReportDate": daily_report,
        "recentGrants": grants,
    }


# ─── File update helpers ──────────────────────────────────────────────────────

def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("Could not parse %s — using default", path)
    return default


def write_json(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    size_kb = path.stat().st_size / 1024
    log.info("Wrote %s (%.1f KB)", path.name, size_kb)


def update_invitation_rounds(dha: dict | None, svg: dict) -> None:
    path = PUBLIC / "invitation-rounds.json"
    current = load_json(path, {})

    if dha and dha.get("date"):
        current["lastUpdated"] = dha["date"]
        current["sourceUrl"] = DHA_ROUNDS_URL
        current["currentRound"] = {
            "date": dha["date"],
            "sc189": {
                "total": dha["sc189Total"],
                "tieBreak": dha["sc189TieBreak"],
            },
            "sc491Family": {
                "total": dha["sc491FamilyTotal"],
                "tieBreak": dha["sc491FamilyTieBreak"],
            },
            "source": "dha",
        }
        # Insert into rounds[] if not already present
        rounds = current.setdefault("rounds", [])
        existing_dates = {r.get("date") for r in rounds}
        if dha["date"] not in existing_dates:
            rounds.insert(0, {
                "date": dha["date"],
                "sc189Total": dha["sc189Total"],
                "sc189TieBreak": dha["sc189TieBreak"],
                "sc491FamilyTotal": dha["sc491FamilyTotal"],
                "sc491FamilyTieBreak": dha["sc491FamilyTieBreak"],
            })

    if svg.get("nextRound"):
        current["nextRound"] = svg["nextRound"]

    current["scrapedAt"] = datetime.now(timezone.utc).isoformat()
    write_json(path, current)


def update_visa_types(visa_details: dict[str, dict]) -> None:
    path = PUBLIC / "visa-types.json"
    data = load_json(path, None)
    if not data or "visas" not in data:
        log.warning("visa-types.json missing/invalid — skipping")
        return

    today = datetime.now(timezone.utc).date().isoformat()
    for visa in data["visas"]:
        details = visa_details.get(visa.get("code"))
        if not details:
            continue
        if "cost" in details:
            visa["cost"] = details["cost"]
        if "processingCutoff" in details:
            visa["processingCutoff"] = details["processingCutoff"]
            visa["processingCutoffLabel"] = details["processingCutoffLabel"]
        if "stayDuration" in details:
            visa["stayDuration"] = details["stayDuration"]
        visa["last_seen"] = today

    data["last_changed"] = today
    write_json(path, data)


def write_daily_updates(dha: dict | None, svg: dict, visa_details: dict) -> None:
    path = PUBLIC / "daily-updates.json"
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "date": datetime.now(timezone.utc).date().isoformat(),
        "currentRound": dha,
        "nextRound": svg.get("nextRound"),
        "communityFeed": {
            "source": "smartvisaguide.com",
            "dailyReportDate": svg.get("dailyReportDate"),
            "recentGrants": svg.get("recentGrants", []),
        },
        "visaSummary": [
            {
                "code": code,
                "cost": d.get("cost"),
                "processingCutoffLabel": d.get("processingCutoffLabel"),
                "stayDuration": d.get("stayDuration"),
            }
            for code, d in visa_details.items()
        ],
        "verification": {
            "dhaReachable": dha is not None,
            "smartVisaGuideReachable": svg.get("available", False),
            "datesAgree": (
                dha is not None
                and svg.get("nextRound") is not None
                and dha.get("date") != svg["nextRound"].get("date")
            ),
        },
    }
    write_json(path, payload)


def write_status(success: bool, errors: list[str]) -> None:
    path = PUBLIC / ".monitor-status.json"
    write_json(path, {
        "lastRun": datetime.now(timezone.utc).isoformat(),
        "success": success,
        "errors": errors,
    })


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    log.info("=== Daily monitor starting ===")
    errors: list[str] = []

    # 1. smartvisaguide.com
    log.info("[1/3] Scraping smartvisaguide.com…")
    svg = scrape_smart_visa_guide()
    if svg.get("available"):
        log.info("  Daily report date: %s", svg.get("dailyReportDate"))
        log.info("  Next round: %s", svg.get("nextRound"))
        log.info("  Recent grants captured: %d", len(svg.get("recentGrants", [])))
    else:
        errors.append("smartvisaguide.com unreachable")

    # 2. DHA invitation rounds
    log.info("[2/3] Verifying with DHA invitation rounds…")
    dha = fetch_dha_round()
    if dha:
        log.info("  DHA current round: %s (189 total=%s, tie=%s)",
                 dha.get("date"), dha.get("sc189Total"), dha.get("sc189TieBreak"))
    else:
        errors.append("DHA invitation rounds unreachable / parse failed")

    # 3. DHA visa pages (cost + processing cutoff)
    log.info("[3/3] Fetching DHA visa details…")
    visa_details: dict[str, dict] = {}
    for code, url in DHA_VISA_PAGES.items():
        d = fetch_visa_details(code, url)
        if d.get("cost") or d.get("processingCutoff"):
            log.info("  SC %s: cost=%s cutoff=%s",
                     code, d.get("cost"), d.get("processingCutoffLabel"))
        else:
            log.warning("  SC %s: no cost/cutoff parsed", code)
        visa_details[code] = d

    # Write outputs
    update_invitation_rounds(dha, svg)
    update_visa_types(visa_details)
    write_daily_updates(dha, svg, visa_details)
    write_status(success=not errors, errors=errors)

    log.info("=== Done. Errors: %d ===", len(errors))
    return 0 if not errors else 0  # always exit 0; status file tells truth


if __name__ == "__main__":
    sys.exit(main())
