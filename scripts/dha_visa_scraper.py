#!/usr/bin/env python3
"""
dha_visa_scraper.py
===================
Scrapes the official DHA visa listing page and generates/updates
  public/visa-types.json

Designed to run via GitHub Actions on a weekly schedule.

Source:   https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing
Output:   public/visa-types.json

Requirements:
    pip install requests beautifulsoup4

Environment variables:
    DRY_RUN   — set to "true" to skip writing the output file (default: false)
"""

import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DHA_URL   = "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing"
OUT_FILE  = Path(__file__).parent.parent / "public" / "visa-types.json"
DRY_RUN   = os.environ.get("DRY_RUN", "false").lower() == "true"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MigrateAU-Bot/1.0; "
        "+https://github.com/migrateAU/migration-au)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}

# DHA section heading → canonical category name used by the app
SECTION_CATEGORY_MAP: dict[str, str] = {
    "visitor visas":                   "Visitor",
    "studying and training visas":     "Student",
    "family and partner visas":        "Family",
    "working and skilled visas":       "Skilled",   # refined per-visa below
    "refugee and humanitarian visas":  "Humanitarian",
    "other visas":                     "Other",
    "repealed visas":                  "Historical",
}

# Sub-mapping: visas within "Working and skilled" get a finer category
SUBCODE_CATEGORY_OVERRIDE: dict[str, str] = {
    "482": "Employer",
    "186": "Employer",
    "494": "Employer",
    "187": "Employer",
    "407": "Employer",
    "400": "Employer",
    "403": "Employer",
    "408": "Employer",
    "485": "Graduate",
    "417": "Working Holiday",
    "462": "Working Holiday",
    "188": "Business",
    "888": "Business",
    "132": "Business",
}

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class VisaRecord:
    code: str                    # e.g. "189", "820/801"
    name: str                    # human-readable name from DHA
    category: str                # e.g. "Skilled", "Family"
    status: str                  # "active" | "repealed"
    url: str                     # full DHA URL
    first_seen: str = ""         # ISO date this code first appeared in our data
    last_seen: str  = ""         # ISO date of last successful scrape


@dataclass
class Snapshot:
    snapshot_date: str
    source: str
    last_changed: str
    total_active: int
    total_repealed: int
    visas: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_codes(text: str) -> str:
    """
    Extract subclass number(s) from a DHA link text, e.g.:
      "Skilled Independent visa (subclass 189)"   → "189"
      "Partner visa (subclass 820 801)"            → "820/801"
      "Bridging visa E – BVE – (subclass 050 051)" → "050/051"
      "Refugee visas (subclass 200, 201, 203 and 204)" → "200–204"
    Returns empty string if none found.
    """
    # Find all numbers in parentheses after "subclass"
    m = re.search(r'subclass\s+([\d ,/–\-and\s]+)', text, re.IGNORECASE)
    if not m:
        return ""
    raw = m.group(1).strip().rstrip(")")
    # Collect all numeric tokens
    nums = re.findall(r'\d+', raw)
    if not nums:
        return ""
    if len(nums) == 1:
        return nums[0]
    if len(nums) == 2:
        return f"{nums[0]}/{nums[1]}"
    # 3+ numbers — compact into a range notation
    return f"{nums[0]}–{nums[-1]}"


def _extract_code_tokens(text: str) -> list[str]:
    """Return every subclass number mentioned in a visa listing link."""
    m = re.search(r'subclass\s+([\d ,/–\-and\s]+)', text, re.IGNORECASE)
    if not m:
        return []
    return re.findall(r'\d+', m.group(1))


def _clean_name(text: str) -> str:
    """Strip the '(subclass NNN)' suffix from a visa name."""
    return re.sub(r'\s*\(subclass[\s\d,/–\-and]+\)', '', text, flags=re.IGNORECASE).strip()


def _today() -> str:
    return date.today().isoformat()


def _record_from_link(
    link_text: str,
    href: str,
    category: str,
    is_repealed: bool,
    today: str,
) -> list[VisaRecord]:
    if "/visas/getting-a-visa/visa-listing/" not in href:
        return []

    codes = _extract_code_tokens(link_text)
    if not codes:
        return []

    link_is_repealed = is_repealed or "/repealed-visas/" in href
    full_url = (
        href if href.startswith("http")
        else f"https://immi.homeaffairs.gov.au{href}"
    )
    records: list[VisaRecord] = []

    for code in codes:
        resolved_cat = category
        if category in ("Skilled",):
            for sub_code, override in SUBCODE_CATEGORY_OVERRIDE.items():
                if sub_code == code:
                    resolved_cat = override
                    break

        records.append(VisaRecord(
            code=code,
            name=_clean_name(link_text),
            category=resolved_cat,
            status="repealed" if link_is_repealed else "active",
            url=full_url,
            first_seen=today,
            last_seen=today,
        ))

    return records


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

def fetch_page(url: str) -> BeautifulSoup:
    logger.info("Fetching %s", url)
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_visas(soup: BeautifulSoup) -> list[VisaRecord]:
    """
    Collect visa links from the DHA visa listing page.

    DHA currently stores the listing in a hidden PageSchema JSON field. Keep the
    older visible <h2> section parser as a fallback in case the page changes
    back to server-rendered markup.
    """
    records: list[VisaRecord] = []
    today = _today()

    schema_input = soup.find(
        "input",
        id=lambda value: value and "PageSchemaHiddenField_Input" in value,
    )
    if schema_input and schema_input.get("value"):
        try:
            schema = json.loads(schema_input["value"])
            for section in schema.get("content", []):
                heading_text = section.get("text", "").strip().lower()
                category = None
                for key, cat in SECTION_CATEGORY_MAP.items():
                    if key in heading_text:
                        category = cat
                        break
                if category is None:
                    continue

                block = BeautifulSoup(section.get("block", ""), "html.parser")
                is_repealed = "repealed" in heading_text
                for a in block.find_all("a", href=True):
                    records.extend(_record_from_link(
                        a.get_text(strip=True),
                        a["href"],
                        category,
                        is_repealed,
                        today,
                    ))
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Could not parse DHA PageSchemaHiddenField data: %s", exc)

    # Find all h2 elements — each is a section header
    for h2 in soup.find_all("h2"):
        heading_text = h2.get_text(strip=True).lower()
        category = None
        for key, cat in SECTION_CATEGORY_MAP.items():
            if key in heading_text:
                category = cat
                break
        if category is None:
            continue  # skip unrecognised sections (nav, footer, etc.)

        is_repealed = "repealed" in heading_text

        # Collect all <a> tags in the next sibling elements until the next h2
        node = h2.find_next_sibling()
        while node and node.name != "h2":
            for a in node.find_all("a", href=True):
                records.extend(_record_from_link(
                    a.get_text(strip=True),
                    a["href"],
                    category,
                    is_repealed,
                    today,
                ))
            node = node.find_next_sibling()

    # De-duplicate by code (keep first occurrence — active beats repealed)
    seen: dict[str, VisaRecord] = {}
    for r in records:
        if r.code not in seen:
            seen[r.code] = r
        elif seen[r.code].status == "repealed" and r.status == "active":
            # Prefer active record
            seen[r.code] = r

    return list(seen.values())


# ---------------------------------------------------------------------------
# Diff & change detection
# ---------------------------------------------------------------------------

def load_existing(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def diff_snapshots(
    existing: Optional[dict], new_records: list[VisaRecord]
) -> tuple[list[str], list[str], list[str]]:
    """
    Returns (added_codes, removed_codes, status_changed_codes).
    """
    if not existing:
        return [r.code for r in new_records], [], []

    old_by_code = {
        v["code"]: v
        for v in existing.get("visas", [])
        if not v.get("_scrape_missing")
    }
    new_by_code = {r.code: r for r in new_records}

    added   = [c for c in new_by_code if c not in old_by_code]
    removed = [c for c in old_by_code if c not in new_by_code]
    changed = [
        c for c in new_by_code
        if c in old_by_code
        and new_by_code[c].status != old_by_code[c].get("status")
    ]
    return added, removed, changed


# ---------------------------------------------------------------------------
# Build final JSON
# ---------------------------------------------------------------------------

def build_snapshot(
    records: list[VisaRecord],
    existing: Optional[dict],
    last_changed: str,
) -> dict:
    today = _today()
    old_by_code = {v["code"]: v for v in (existing or {}).get("visas", [])}

    visa_list = []
    for r in records:
        old = old_by_code.get(r.code, {})
        visa_list.append({
            "code":       r.code,
            "name":       r.name,
            "category":   r.category,
            "status":     r.status,
            "url":        r.url,
            "first_seen": old.get("first_seen", r.first_seen) or today,
            "last_seen":  today,
        })

    # Preserve visas from existing that were not found (could be a scrape miss)
    # — mark them with last_seen unchanged but add a warning flag
    for code, old in old_by_code.items():
        if code not in {v["code"] for v in visa_list}:
            warning_entry = dict(old)
            warning_entry["_scrape_missing"] = True
            visa_list.append(warning_entry)
            logger.warning("Visa %s was in previous snapshot but not found on DHA page — kept with _scrape_missing flag", code)

    active   = sum(1 for v in visa_list if v.get("status") == "active" and not v.get("_scrape_missing"))
    repealed = sum(1 for v in visa_list if v.get("status") == "repealed" and not v.get("_scrape_missing"))

    return {
        "snapshot_date":  today,
        "source":         DHA_URL,
        "last_changed":   last_changed,
        "total_active":   active,
        "total_repealed": repealed,
        "visas":          visa_list,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    today = _today()

    # 1. Fetch & parse
    try:
        soup = fetch_page(DHA_URL)
    except requests.RequestException as exc:
        logger.error("Failed to fetch DHA page: %s", exc)
        return 1

    records = parse_visas(soup)
    if not records:
        logger.error("No visa records parsed — aborting (likely page structure change)")
        return 1

    logger.info("Parsed %d visa records from DHA", len(records))

    # 2. Load existing snapshot
    existing = load_existing(OUT_FILE)

    # 3. Diff
    added, removed, changed = diff_snapshots(existing, records)

    if not added and not removed and not changed:
        logger.info("No changes detected — visa list is up to date")
        if DRY_RUN:
            logger.info("DRY_RUN=true — would write %s", OUT_FILE)
        # Still write to update last_seen / snapshot_date
    else:
        logger.info("Changes detected:")
        for c in added:
            r = next(x for x in records if x.code == c)
            logger.info("  + ADDED    SC %s  (%s)", c, r.name)
        for c in removed:
            logger.info("  - REMOVED  SC %s", c)
        for c in changed:
            r = next(x for x in records if x.code == c)
            old_status = {v["code"]: v for v in (existing or {}).get("visas", [])}.get(c, {}).get("status", "?")
            logger.info("  ~ CHANGED  SC %s: %s → %s", c, old_status, r.status)

    last_changed = today if (added or removed or changed) else (
        (existing or {}).get("last_changed", today)
    )

    # 4. Build & write snapshot
    snapshot = build_snapshot(records, existing, last_changed)

    if DRY_RUN:
        logger.info("DRY_RUN=true — printing JSON to stdout")
        print(json.dumps(snapshot, indent=2, ensure_ascii=False))
        return 0

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
        f.write("\n")

    logger.info("Written %s (%d visas)", OUT_FILE, len(snapshot["visas"]))

    # Exit code 2 = changes detected (used by CI to decide whether to deploy)
    return 2 if (added or removed or changed) else 0


if __name__ == "__main__":
    sys.exit(main())
