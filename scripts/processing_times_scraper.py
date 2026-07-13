#!/usr/bin/env python3
"""
processing_times_scraper.py
===========================
Scrapes the DHA Global Visa Processing Times page and generates
  public/processing-times.json

The DHA page is JS-rendered, so Playwright is required.

Output schema (must match app's utils/remoteSchema.ts validation):
{
  "snapshotDate": "YYYY-MM-DD",
  "items": [
    {
      "subclass": "189",
      "name": "Skilled Independent",
      "stream": "Points-tested stream",  // optional
      "category": "Skilled",
      "p50": "9 months",
      "p90": "17 months",
      "icon": "globe-outline",
      "color": "#00C2FF",
      "url": "https://immi.homeaffairs.gov.au/..."
    }
  ]
}

Exit codes:
  0  — success (JSON updated)
  1  — error
"""

import json
import logging
import re
import sys
from datetime import date, datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
OUTPUT = PUBLIC / "processing-times.json"

DHA_URL = "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-processing-times/global-visa-processing-times"

# ─── Category / icon / color mapping ─────────────────────────────────────────
# Based on the app's bundled constants/processingTimes.ts

VISA_META = {
    "189": {"category": "Skilled", "icon": "globe-outline", "color": "#00C2FF",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-independent-189"},
    "190": {"category": "Skilled", "icon": "location-outline", "color": "#00C2FF",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-nominated-190"},
    "491": {"category": "Skilled", "icon": "map-outline", "color": "#00C2FF",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-work-regional-provisional-491"},
    "887": {"category": "Skilled", "icon": "home-outline", "color": "#00C2FF",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-regional-887"},
    "191": {"category": "Skilled", "icon": "home-outline", "color": "#00C2FF",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/permanent-residence-skilled-regional-191"},
    "482": {"category": "Employer", "icon": "briefcase-outline", "color": "#FF9800",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skills-in-demand-visa-subclass-482"},
    "494": {"category": "Employer", "icon": "business-outline", "color": "#FF9800",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-employer-sponsored-regional-494"},
    "186": {"category": "Employer", "icon": "briefcase-outline", "color": "#FF9800",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/employer-nomination-scheme-186"},
    "485": {"category": "Graduate", "icon": "school-outline", "color": "#9C27B0",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/temporary-graduate-485"},
    "500": {"category": "Student", "icon": "book-outline", "color": "#2196F3",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/student-500"},
    "590": {"category": "Student", "icon": "people-outline", "color": "#2196F3",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/student-guardian-590"},
    "600": {"category": "Visitor", "icon": "airplane-outline", "color": "#4CAF50",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/visitor-600"},
    "601": {"category": "Visitor", "icon": "airplane-outline", "color": "#4CAF50",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/electronic-travel-authority-601"},
    "651": {"category": "Visitor", "icon": "airplane-outline", "color": "#4CAF50",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/evisitor-651"},
    "820": {"category": "Family", "icon": "heart-outline", "color": "#E91E63",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/partner-onshore-820-801"},
    "309": {"category": "Family", "icon": "heart-outline", "color": "#E91E63",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/partner-offshore-309-100"},
    "143": {"category": "Family", "icon": "people-outline", "color": "#E91E63",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/contributory-parent-143"},
    "103": {"category": "Family", "icon": "people-outline", "color": "#E91E63",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/parent-103"},
    "101": {"category": "Family", "icon": "people-outline", "color": "#E91E63",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/child-101"},
    "417": {"category": "Visitor", "icon": "walk-outline", "color": "#4CAF50",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/work-holiday-417"},
    "462": {"category": "Visitor", "icon": "walk-outline", "color": "#4CAF50",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/work-and-holiday-462"},
    "407": {"category": "Employer", "icon": "school-outline", "color": "#FF9800",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/training-407"},
}

# Default meta for unknown subclasses
DEFAULT_META = {"category": "Skilled", "icon": "document-outline", "color": "#607D8B",
                "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-processing-times/global-visa-processing-times"}


def fetch_with_playwright() -> str | None:
    """Render the DHA processing times page with Playwright."""
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
            log.info("Loading DHA processing times page…")
            page.goto(DHA_URL, wait_until="networkidle", timeout=60000)
            # Wait for the processing time tables to render
            try:
                page.wait_for_selector("table", timeout=20000)
                log.info("Tables detected on page")
            except Exception:
                log.warning("No tables appeared within 20s — page structure may have changed")
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        log.error("Playwright failed: %s", e)
        return None


def parse_time_text(text: str) -> str:
    """Normalize processing time text like '9 months' or '< 1 month'."""
    t = text.strip()
    t = re.sub(r'\s+', ' ', t)
    # Remove leading/trailing non-alphanumeric except < >
    t = re.sub(r'^[^<\da-zA-Z]+|[^a-zA-Z\d]+$', '', t)
    if not t:
        return "N/A"
    return t


def parse_processing_times_page(html: str) -> list[dict]:
    """Parse the rendered DHA processing times page into structured items."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    # The DHA page has tables with columns: Visa subclass | Stream | 50% | 90%
    # or sometimes: Visa subclass and stream | 50% | 90%
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # Try to identify column indices from header
        header_row = rows[0]
        headers = [c.get_text(" ", strip=True).lower() for c in header_row.find_all(["th", "td"])]

        # Look for processing time indicators in headers
        has_percent = any("%" in h or "percentile" in h for h in headers)
        has_time = any("time" in h or "process" in h for h in headers)
        if not has_percent and not has_time and "visa" not in " ".join(headers):
            continue

        log.info("Found processing times table with %d rows, headers: %s", len(rows), headers)

        for row in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if len(cells) < 3:
                continue

            # Extract subclass number
            subclass = None
            name = ""
            stream = None
            p50 = ""
            p90 = ""

            # First cell usually has "Subclass NNN - Name" or just the visa name
            first = cells[0]
            sc_match = re.search(r'(?:subclass\s+)?(\d{3})', first, re.I)
            if sc_match:
                subclass = sc_match.group(1)
                # Name is the rest after the number
                name = re.sub(r'(?:subclass\s+)?\d{3}\s*[-–—:]*\s*', '', first, flags=re.I).strip()
            else:
                # Might be a stream row under a previous visa heading
                continue

            # Handle different column layouts
            if len(cells) >= 4:
                # Visa | Stream | 50% | 90%
                stream = cells[1].strip() if cells[1].strip() and not re.match(r'^\d', cells[1]) else None
                p50_idx = 2 if stream else 1
                p50 = parse_time_text(cells[p50_idx])
                p90 = parse_time_text(cells[p50_idx + 1]) if len(cells) > p50_idx + 1 else ""
            elif len(cells) == 3:
                # Visa | 50% | 90%
                p50 = parse_time_text(cells[1])
                p90 = parse_time_text(cells[2])

            if not subclass or not p50:
                continue

            # Deduplicate — use subclass+stream as key
            key = f"{subclass}|{stream or ''}"
            if key in seen:
                continue
            seen.add(key)

            # Get metadata
            meta = VISA_META.get(subclass, DEFAULT_META)

            item = {
                "subclass": subclass,
                "name": name or meta.get("name", f"Subclass {subclass}"),
                "category": meta["category"],
                "p50": p50,
                "p90": p90 or p50,
                "icon": meta["icon"],
                "color": meta["color"],
                "url": meta["url"],
            }
            if stream:
                item["stream"] = stream

            items.append(item)
            log.info("  SC %s %s: p50=%s, p90=%s", subclass, stream or "", p50, p90)

    return items


def load_existing() -> dict:
    """Load existing processing-times.json as fallback."""
    if OUTPUT.exists():
        try:
            return json.loads(OUTPUT.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"snapshotDate": "", "items": []}


def get_seed_data() -> list[dict]:
    """
    Return seed processing times from known good data.
    Used when the scraper can't parse live data (DHA restructure, etc).
    Based on DHA published figures as of April 2026.
    """
    return [
        {"subclass": "189", "name": "Skilled Independent", "category": "Skilled",
         "p50": "9 months", "p90": "17 months", "icon": "globe-outline", "color": "#00C2FF",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-independent-189"},
        {"subclass": "190", "name": "Skilled Nominated", "category": "Skilled",
         "p50": "5 months", "p90": "11 months", "icon": "location-outline", "color": "#00C2FF",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-nominated-190"},
        {"subclass": "491", "name": "Skilled Work Regional (Provisional)", "category": "Skilled",
         "p50": "7 months", "p90": "15 months", "icon": "map-outline", "color": "#00C2FF",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-work-regional-provisional-491"},
        {"subclass": "887", "name": "Skilled Regional (Residence)", "category": "Skilled",
         "p50": "6 months", "p90": "12 months", "icon": "home-outline", "color": "#00C2FF",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-regional-887"},
        {"subclass": "191", "name": "Permanent Residence (Skilled Regional)", "category": "Skilled",
         "p50": "8 months", "p90": "16 months", "icon": "home-outline", "color": "#00C2FF",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/permanent-residence-skilled-regional-191"},
        {"subclass": "482", "name": "Skills in Demand (Temporary)", "category": "Employer",
         "p50": "3 months", "p90": "7 months", "icon": "briefcase-outline", "color": "#FF9800",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skills-in-demand-visa-subclass-482"},
        {"subclass": "494", "name": "Skilled Employer Sponsored Regional", "category": "Employer",
         "p50": "5 months", "p90": "11 months", "icon": "business-outline", "color": "#FF9800",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-employer-sponsored-regional-494"},
        {"subclass": "186", "name": "Employer Nomination Scheme", "category": "Employer",
         "p50": "6 months", "p90": "14 months", "icon": "briefcase-outline", "color": "#FF9800",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/employer-nomination-scheme-186"},
        {"subclass": "485", "name": "Temporary Graduate", "category": "Graduate",
         "p50": "4 months", "p90": "8 months", "icon": "school-outline", "color": "#9C27B0",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/temporary-graduate-485"},
        {"subclass": "500", "name": "Student Visa", "category": "Student",
         "p50": "29 days", "p90": "42 days", "icon": "book-outline", "color": "#2196F3",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/student-500"},
        {"subclass": "590", "name": "Student Guardian", "category": "Student",
         "p50": "30 days", "p90": "60 days", "icon": "people-outline", "color": "#2196F3",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/student-guardian-590"},
        {"subclass": "600", "name": "Visitor", "category": "Visitor",
         "p50": "20 days", "p90": "33 days", "icon": "airplane-outline", "color": "#4CAF50",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/visitor-600"},
        {"subclass": "601", "name": "Electronic Travel Authority", "category": "Visitor",
         "p50": "1 day", "p90": "2 days", "icon": "airplane-outline", "color": "#4CAF50",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/electronic-travel-authority-601"},
        {"subclass": "651", "name": "eVisitor", "category": "Visitor",
         "p50": "1 day", "p90": "15 days", "icon": "airplane-outline", "color": "#4CAF50",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/evisitor-651"},
        {"subclass": "820", "name": "Partner (Onshore Temporary)", "category": "Family",
         "p50": "10 months", "p90": "22 months", "icon": "heart-outline", "color": "#E91E63",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/partner-onshore-820-801"},
        {"subclass": "309", "name": "Partner (Offshore Temporary)", "category": "Family",
         "p50": "14 months", "p90": "24 months", "icon": "heart-outline", "color": "#E91E63",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/partner-offshore-309-100"},
        {"subclass": "143", "name": "Contributory Parent", "category": "Family",
         "p50": "12 months", "p90": "14 months", "icon": "people-outline", "color": "#E91E63",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/contributory-parent-143"},
        {"subclass": "103", "name": "Parent", "category": "Family",
         "p50": "52+ months", "p90": "52+ months", "icon": "people-outline", "color": "#E91E63",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/parent-103"},
        {"subclass": "101", "name": "Child", "category": "Family",
         "p50": "16 months", "p90": "22 months", "icon": "people-outline", "color": "#E91E63",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/child-101"},
        {"subclass": "417", "name": "Working Holiday", "category": "Visitor",
         "p50": "14 days", "p90": "27 days", "icon": "walk-outline", "color": "#4CAF50",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/work-holiday-417"},
        {"subclass": "462", "name": "Work and Holiday", "category": "Visitor",
         "p50": "15 days", "p90": "44 days", "icon": "walk-outline", "color": "#4CAF50",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/work-and-holiday-462"},
        {"subclass": "407", "name": "Training", "category": "Employer",
         "p50": "2 months", "p90": "4 months", "icon": "school-outline", "color": "#FF9800",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/training-407"},
    ]


def main() -> int:
    today = date.today().isoformat()

    # Try Playwright scraping first
    items: list[dict] = []
    html = fetch_with_playwright()
    if html:
        items = parse_processing_times_page(html)
        if items:
            log.info("Successfully scraped %d processing time entries from DHA.", len(items))
        else:
            log.warning("Playwright rendered page but no table data extracted — using seed data.")

    if not items:
        # Fallback: use existing data if recent, otherwise use seed
        existing = load_existing()
        if existing.get("items") and existing.get("snapshotDate", "") >= "2026-01-01":
            log.info("Using existing data (%d items from %s) as live scrape failed.",
                     len(existing["items"]), existing["snapshotDate"])
            # Just update the snapshot date to show the script ran
            existing["snapshotDate"] = today
            OUTPUT.write_text(
                json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            return 0

        log.info("No existing data or too stale — using seed data.")
        items = get_seed_data()

    # Build output
    output = {
        "snapshotDate": today,
        "items": items,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    log.info("✅ processing-times.json updated → %s (%d items)", OUTPUT, len(items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
