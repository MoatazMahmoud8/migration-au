#!/usr/bin/env python3
"""
Scrape official Australian skilled migration occupation lists.

Output: public/official-occupation-lists.json with structure:
{
  "snapshotDate": "...",
  "sources": {...URLs...},
  "federal": {
    "occupations": [
      {"anzsco": "111211", "name": "Corporate General Manager", "version": "2022", "lists": ["CSOL"], "visas": ["189", ...], "assessingAuthority": "VETASSESS"}
    ],
    "CSOL_anzscos": [...],
    "MLTSSL_anzscos": [...],
    "STSOL_anzscos": [...],
    "ROL_anzscos": [...]
  },
  "states": {...}
}
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept-Language": "en-AU,en;q=0.9"}
JSON_HEADERS = {
    **HEADERS,
    "Content-Type": "application/json; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
}

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
OUT = PUBLIC / "official-occupation-lists.json"
ANZSCO_FILE = PUBLIC / "all-anzsco-occupations.json"

SOURCES = {
    "federal_combined": "https://immi.homeaffairs.gov.au/visas/working-in-australia/skill-occupation-list",
    "federal_combined_api": "https://immi.homeaffairs.gov.au/_layouts/15/api/Data.aspx/GetSkillOccupation",
    "NSW": "https://www.nsw.gov.au/visas-and-migration/skilled-visas/nsw-skills-lists",
    "VIC": "https://liveinmelbourne.vic.gov.au/migrate/skilled-migration-visas/visa-nomination",
    "QLD": "https://migration.qld.gov.au/occupation-lists/queensland-onshore-skilled-occupation-list",
    "WA": "https://migration.wa.gov.au/services/skilled-migration-western-australia/wa-skilled-migration-occupation-list",
    "SA": "https://migration.sa.gov.au/before-applying/work-in-sa/occupation-lists/occupations-list",
    "TAS": "https://www.migration.tas.gov.au/skilled_migration",
    "ACT": "https://www.act.gov.au/migration/skilled-migrants/act-nominated-migration-program-occupation-list",
    "NT": "https://theterritory.com.au/migrate/migrate-to-work/northern-territory-migration-occupation-list",
}

FEDERAL_LIST_KEYS = ("CSOL", "MLTSSL", "STSOL", "ROL")


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


def load_all_anzscos() -> Dict[str, str]:
    data = json.loads(ANZSCO_FILE.read_text())
    out = {}
    for item in data.get("items", []):
        code = str(item.get("anzsco", "")).strip()
        if len(code) == 6 and code.isdigit():
            out[code] = item.get("name", "")
    return out


def extract_anzsco_codes(text: str, all_anzscos: Dict[str, str]) -> Set[str]:
    if not text:
        return set()
    candidates = set(re.findall(r"\b(\d{6})\b", text))
    return {c for c in candidates if c in all_anzscos}


def extract_unit_groups(text: str) -> Set[str]:
    if not text:
        return set()
    return set(re.findall(r"\b([1-8]\d{3})\b", text))


def clean_text(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_list_name(value: str) -> str | None:
    raw = clean_text(value).upper().replace(",", ";")
    raw = raw.replace("RSMS ROL", "ROL")
    if raw in FEDERAL_LIST_KEYS:
        return raw
    return None


def parse_federal_occupation_rows(all_anzscos: Dict[str, str]) -> dict:
    try:
        response = requests.post(
            SOURCES["federal_combined_api"],
            headers=JSON_HEADERS,
            data='{"webUrl":"/work-in-australia","listname":"Occupations"}',
            timeout=60,
        )
        response.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Federal combined API failed: {e}") from e

    payload = response.json()
    rows = payload.get("d", {}).get("data", [])
    occupations: dict[str, dict] = {}
    skipped_non_master = 0

    for row in rows:
        anzsco_field = clean_text(row.get("anzscocode", ""))
        match = re.search(r"ANZSCO\s*(20\d{2}|2013)\s*-\s*(\d{6})", anzsco_field)
        if not match:
            match = re.search(r"(20\d{2}|2013).*?(\d{6})", anzsco_field)
        if not match:
            continue

        version, code = match.group(1), match.group(2)
        if code not in all_anzscos:
            skipped_non_master += 1
            continue

        entry = occupations.setdefault(code, {
            "anzsco": code,
            "name": row.get("occupation", "") or all_anzscos.get(code, ""),
            "version": version,
            "lists": set(),
            "visas": set(),
            "assessingAuthority": None,
        })

        for piece in re.split(r"[;|]", row.get("list", "")):
            normalized = normalize_list_name(piece)
            if normalized:
                entry["lists"].add(normalized)

        visa_blob = f"{row.get('visas', '')} {row.get('visacaveats', '')}"
        for visa_code in re.findall(r"\b(1\d{2}|4\d{2}|5\d{2})\b", visa_blob):
            entry["visas"].add(visa_code)

        assess_html = row.get("assessauth", "")
        authority_options = [
            clean_text(part)
            for part in re.findall(r"<a [^>]*>\s*([^<]+?)\s*</a>", assess_html or "", flags=re.I)
        ]
        authority_options = [a for a in authority_options if a and not a.startswith("javascript:")]
        if authority_options:
            entry["assessingAuthority"] = authority_options[0]

    by_list = {key: [] for key in FEDERAL_LIST_KEYS}
    federal_occupations = []
    for code in sorted(occupations):
        entry = occupations[code]
        lists = sorted(entry["lists"])
        visas = sorted(entry["visas"])
        for list_name in lists:
            by_list[list_name].append(code)
        federal_occupations.append({
            "anzsco": code,
            "name": entry["name"],
            "version": entry["version"],
            "lists": lists,
            "visas": visas,
            "assessingAuthority": entry["assessingAuthority"],
        })

    return {
        "occupations": federal_occupations,
        "CSOL_unit_groups": sorted({code[:4] for code in by_list["CSOL"]}),
        "CSOL_anzscos": by_list["CSOL"],
        "MLTSSL_anzscos": by_list["MLTSSL"],
        "STSOL_anzscos": by_list["STSOL"],
        "ROL_anzscos": by_list["ROL"],
        "combined_anzscos": sorted(occupations.keys()),
        "count_unit_groups": len({code[:4] for code in by_list["CSOL"]}),
        "count_anzscos": len(occupations),
        "count_by_list": {key: len(value) for key, value in by_list.items()},
        "skipped_non_master": skipped_non_master,
    }


def scrape_state(state_code: str, all_anzscos: Dict[str, str], federal_anzscos: List[str]) -> dict:
    """Scrape a state's own occupation-nomination list.

    IMPORTANT: on failure (blocked / 404 / page doesn't expose a parseable
    list) we do NOT fall back to the full federal combined list as a proxy.
    Previously this silently treated "we couldn't scrape this state" as
    "every federally-eligible occupation is open in this state", which
    made VIC/WA/SA/TAS/NT (all of which fail to scrape — Cloudflare/WAF
    blocks return 403, WA's URL 404s, SA's page has no plain-text codes)
    blanket-show as "Open" for ~682 occupations regardless of whether that
    state's real, much smaller nomination list actually includes them.
    We now return an empty, explicitly-unverified result instead, so
    downstream consumers can show "Not Verified — Check Official Site"
    rather than a false "Open".
    """
    url = SOURCES.get(state_code)
    if not url:
        return {"190": [], "491": [], "source": "", "scraped": False, "dataAvailable": False, "fallback": None, "note": "No source URL configured"}

    text = fetch(url)
    if not text:
        return {"190": [], "491": [], "source": url, "scraped": False, "dataAvailable": False, "fallback": None, "note": "Fetch failed (blocked/404/timeout) — list NOT verified, NOT assumed open"}

    soup = BeautifulSoup(text, "html.parser")
    plain = soup.get_text(separator=" ", strip=True)
    combined = plain + " " + text

    codes_6 = extract_anzsco_codes(combined, all_anzscos)
    codes_4 = extract_unit_groups(plain)
    expanded = set()
    for ug in codes_4:
        for code in all_anzscos:
            if code.startswith(ug):
                expanded.add(code)

    all_codes = sorted(codes_6 | expanded)

    if len(all_codes) >= 20:
        return {
            "190": all_codes,
            "491": all_codes,
            "source": url,
            "scraped": True,
            "dataAvailable": True,
            "fallback": None,
            "note": f"Scraped {len(all_codes)} codes from page (combined 4+6 digit matches)",
        }

    return {
        "190": [],
        "491": [],
        "source": url,
        "scraped": False,
        "dataAvailable": False,
        "fallback": None,
        "note": f"Only {len(all_codes)} codes parsed — insufficient to trust; list NOT verified, NOT assumed open",
    }


def main():
    print(f"[official_lists_scraper] {datetime.now().isoformat()}")
    all_anzscos = load_all_anzscos()
    print(f"  Loaded {len(all_anzscos)} ANZSCO codes from master")

    print("[1/9] Federal combined list …")
    federal = parse_federal_occupation_rows(all_anzscos)
    federal_anzscos = federal["combined_anzscos"]
    print(
        "  ✓ "
        f"{federal['count_anzscos']} occupations "
        f"(CSOL {federal['count_by_list']['CSOL']}, MLTSSL {federal['count_by_list']['MLTSSL']}, "
        f"STSOL {federal['count_by_list']['STSOL']}, ROL {federal['count_by_list']['ROL']})"
    )

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
        "federal": federal,
        "states": states,
        "notes": [
            "Federal combined skilled occupation data is sourced from the Department of Home Affairs occupation list API.",
            "Only six-digit ANZSCO codes present in the ABS 2022 master list are kept in this file.",
            "Per-state '190' and '491' arrays are best-effort scrapes from official pages.",
            "Where scraping yields <20 codes or the page blocks access, the federal combined list is used as a proxy and 'scraped:false' is flagged.",
            "Always verify eligibility against the linked official source URL before applying.",
        ],
    }

    PUBLIC.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(output, indent=2))
    print(f"\n✓ Wrote {OUT} ({OUT.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
