#!/usr/bin/env python3
"""
Scrape official Australian skilled migration occupation lists.

Output: public/official-occupation-lists.json with structure:
{
  "snapshotDate": "...",
  "sources": {...URLs...},
  "federal": {
    "CSOL_unit_groups": ["1111", "1112", ...],  # 4-digit ABS unit groups
    "CSOL_anzscos": ["111111", "111211", ...]   # expanded to 6-digit
  },
  "states": {
    "NSW": {"190": [...anzscos...], "491": [...anzscos...], "source": "url", "scraped": bool},
    ...
  }
}

For state lists where scraping is unreliable, falls back to "all federal CSOL"
with a disclaimer flag (scraped=False, fallback=True).
"""
from __future__ import annotations

import json
import re
import sys
import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Set, Dict, List

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept-Language": "en-AU,en;q=0.9"}

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
OUT = PUBLIC / "official-occupation-lists.json"
ANZSCO_FILE = PUBLIC / "all-anzsco-occupations.json"

SOURCES = {
    "federal_CSOL": "https://immi.homeaffairs.gov.au/visas/working-in-australia/skill-occupation-list",
    "NSW": "https://www.nsw.gov.au/visas-and-migration/skilled-visas/nsw-skills-lists",
    "VIC": "https://liveinmelbourne.vic.gov.au/migrate/skilled-migration-visas/visa-nomination",
    "QLD": "https://migration.qld.gov.au/occupation-lists/queensland-onshore-skilled-occupation-list",
    "WA": "https://migration.wa.gov.au/services/skilled-migration-western-australia/wa-skilled-migration-occupation-list",
    "SA": "https://migration.sa.gov.au/before-applying/work-in-sa/occupation-lists/occupations-list",
    "TAS": "https://www.migration.tas.gov.au/skilled_migration",
    "ACT": "https://www.act.gov.au/migration/skilled-migrants/act-nominated-migration-program-occupation-list",
    "NT": "https://theterritory.com.au/migrate/migrate-to-work/northern-territory-migration-occupation-list",
}


def fetch(url: str, timeout: int = 30) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code != 200:
            print(f"  ! {url} → HTTP {r.status_code}", file=sys.stderr)
            return None
        return r.text
    except Exception as e:
        print(f"  ! {url} → {e}", file=sys.stderr)
        return None


# ---------- ANZSCO master ----------

def load_all_anzscos() -> Dict[str, str]:
    """Returns {anzsco: name} from public/all-anzsco-occupations.json."""
    data = json.loads(ANZSCO_FILE.read_text())
    out = {}
    for item in data.get("items", []):
        code = str(item.get("anzsco", "")).strip()
        if len(code) == 6 and code.isdigit():
            out[code] = item.get("name", "")
    return out


def expand_unit_groups(unit_groups: Set[str], all_anzscos: Dict[str, str]) -> List[str]:
    """Given a set of 4-digit ABS unit groups, expand to all matching 6-digit ANZSCOs."""
    result = sorted(c for c in all_anzscos if c[:4] in unit_groups)
    return result


# ---------- Federal CSOL ----------

def scrape_federal_csol() -> tuple[List[str], List[str]] | None:
    """Returns (unit_groups, anzscos) for federal CSOL."""
    html_text = fetch(SOURCES["federal_CSOL"])
    if not html_text:
        return None
    # The CSOL page links each occupation row to ABS browse-classification with the 4-digit unit group as the last segment
    groups = sorted(set(re.findall(r"browse-classification/\d/\d+/\d+/(\d{4})", html_text)))
    if len(groups) < 50:
        print(f"  ! Federal CSOL: only {len(groups)} unit groups parsed (suspicious)", file=sys.stderr)
        return None
    return groups, []  # anzscos filled by caller


# ---------- Generic 6-digit code extractor for state pages ----------

def extract_anzsco_codes(text: str, all_anzscos: Dict[str, str]) -> Set[str]:
    """Pulls 6-digit numbers from page text and filters to known ANZSCOs."""
    if not text:
        return set()
    # Find all standalone 6-digit numbers
    candidates = set(re.findall(r"\b(\d{6})\b", text))
    return {c for c in candidates if c in all_anzscos}


def extract_unit_groups(text: str) -> Set[str]:
    """Pulls 4-digit unit-group numbers from page text."""
    if not text:
        return set()
    return set(re.findall(r"\b([1-6]\d{3})\b", text))


# ---------- State scrapers (best-effort, fallback to federal CSOL) ----------

def scrape_state(state_code: str, all_anzscos: Dict[str, str], federal_anzscos: List[str]) -> dict:
    """Returns {"190": [...], "491": [...], "source": url, "scraped": bool, "fallback": str}.

    Strategy: fetch the state page, extract any 6-digit ANZSCOs or 4-digit unit groups.
    If we get a reasonable count (>=20 codes), trust it. Otherwise fall back to federal CSOL.
    """
    url = SOURCES.get(state_code)
    if not url:
        return {"190": federal_anzscos, "491": federal_anzscos, "source": "", "scraped": False, "fallback": "federal_CSOL"}

    text = fetch(url)
    if not text:
        return {"190": federal_anzscos, "491": federal_anzscos, "source": url, "scraped": False, "fallback": "federal_CSOL_after_fetch_fail"}

    # Strip HTML for plain text matching
    soup = BeautifulSoup(text, "html.parser")
    plain = soup.get_text(separator=" ", strip=True)
    # Also include any data attributes / JSON-embedded content
    combined = plain + " " + text

    # 6-digit ANZSCO codes
    codes_6 = extract_anzsco_codes(combined, all_anzscos)
    # 4-digit unit groups
    codes_4 = extract_unit_groups(plain)
    # Expand 4-digit to 6-digit
    expanded = set()
    for ug in codes_4:
        for code in all_anzscos:
            if code.startswith(ug):
                expanded.add(code)

    all_codes = sorted(codes_6 | expanded)

    if len(all_codes) >= 20:
        # Trust scrape. Without per-visa segmentation on most pages, apply to both 190 and 491.
        return {
            "190": all_codes,
            "491": all_codes,
            "source": url,
            "scraped": True,
            "fallback": None,
            "note": f"Scraped {len(all_codes)} codes from page (combined 4+6 digit matches)",
        }
    else:
        return {
            "190": federal_anzscos,
            "491": federal_anzscos,
            "source": url,
            "scraped": False,
            "fallback": "federal_CSOL_insufficient_data",
            "note": f"Only {len(all_codes)} codes parsed — using federal CSOL as proxy",
        }


# ---------- Main ----------

def main():
    print(f"[official_lists_scraper] {datetime.now().isoformat()}")
    all_anzscos = load_all_anzscos()
    print(f"  Loaded {len(all_anzscos)} ANZSCO codes from master")

    # Federal CSOL
    print("[1/9] Federal CSOL …")
    fed = scrape_federal_csol()
    if fed is None:
        print("  ✗ Federal CSOL fetch failed — using empty list (states will all fall back to empty)", file=sys.stderr)
        federal_unit_groups: List[str] = []
        federal_anzscos: List[str] = []
    else:
        federal_unit_groups, _ = fed
        federal_anzscos = expand_unit_groups(set(federal_unit_groups), all_anzscos)
        print(f"  ✓ {len(federal_unit_groups)} unit groups → {len(federal_anzscos)} ANZSCO codes")

    # States
    states = {}
    for i, state_code in enumerate(["NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"], start=2):
        print(f"[{i}/9] {state_code} …")
        result = scrape_state(state_code, all_anzscos, federal_anzscos)
        states[state_code] = result
        status = "scraped" if result["scraped"] else f"fallback ({result['fallback']})"
        print(f"  → 190: {len(result['190'])}  491: {len(result['491'])}  [{status}]")

    output = {
        "snapshotDate": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sources": SOURCES,
        "federal": {
            "CSOL_unit_groups": federal_unit_groups,
            "CSOL_anzscos": federal_anzscos,
            "count_unit_groups": len(federal_unit_groups),
            "count_anzscos": len(federal_anzscos),
        },
        "states": states,
        "notes": [
            "Federal CSOL (Combined Skilled Occupation List) replaced MLTSSL/STSOL/ROL on 7 Dec 2024.",
            "All four skilled visas (189, 190, 491, 482) draw from the federal CSOL at federal level.",
            "State nomination lists are state-specific subsets/additions.",
            "Per-state '190' and '491' arrays are best-effort scrapes from official pages.",
            "Where scraping yields <20 codes, the federal CSOL is used as a proxy and 'scraped:false' is flagged.",
            "Always verify eligibility against the linked official source URL before applying.",
        ],
    }

    PUBLIC.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2))
    print(f"\n✓ Wrote {OUT} ({OUT.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
