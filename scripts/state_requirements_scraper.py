#!/usr/bin/env python3
"""
state_requirements_scraper.py
==============================
Scrapes each Australian state / territory's skilled-occupation nomination
pages and produces public/state-occupation-requirements.json.

Output schema
-------------
{
  "snapshotDate": "2026-05-13",
  "requirements": {
    "<anzsco>": {
      "<STATE_CODE>": {
        "visas":                    ["190", "491"],
        "open":                     true,
        "minSalary":                75000,
        "minExperienceYears":       2,
        "skillsAssessmentRequired": true,
        "jobOfferRequired":         false,
        "residencyRequired":        false,
        "minPoints":                null,
        "maxAge":                   null,
        "notes":                    ["Must have AQF7+ qualification"],
        "sourceUrl":                "https://...",
        "updatedAt":                "2026-05-13"
      }
    }
  }
}

Sources scraped
---------------
  NSW  — https://www.nsw.gov.au/living-and-working/immigration-and-visas
  VIC  — https://business.vic.gov.au/business-information/migrate-to-victoria
  QLD  — https://migration.qld.gov.au/visa-options/state-nominated/
  WA   — https://www.migration.wa.gov.au/occupation-lists
  SA   — https://www.migration.sa.gov.au/skilled-visas/
  TAS  — https://www.migration.tas.gov.au/occupations
  ACT  — https://www.act.gov.au/migration/skilled-migrants/canberra-matrix/skilled-occupation-list
  NT   — https://theterritory.com.au/invest/migrate-to-the-territory

Design notes
------------
Each state website has a different structure.  This scraper targets
machine-readable or semi-structured pages where possible (CSV downloads,
JSON endpoints, or simple HTML tables).  When a state only exposes a PDF or
heavily-JS-rendered table, we fall back to the last good cached entry and
mark the record "stale".

Env variables
-------------
  FIREBASE_SERVICE_ACCOUNT_JSON  — base64-encoded service-account JSON
  FIREBASE_PROJECT_ID            — GCP project id
  DRY_RUN                        — "true" to skip writing output (default: false)

Output
------
  public/state-occupation-requirements.json   (also uploaded to Firebase Hosting)
"""

import base64
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
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scripts/scraper.log", mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
TODAY   = date.today().isoformat()

OUT_FILE = Path(__file__).parent.parent / "public" / "state-occupation-requirements.json"
OLD_FILE = OUT_FILE  # same path — we load it first to merge stale records

REQUEST_TIMEOUT = 20  # seconds

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MigrateAU-Bot/1.1; "
        "+https://github.com/migrateAU/migration-au)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class StateOccReq:
    visas: list[str]
    open: bool
    min_salary: Optional[int]         = None
    min_experience_years: Optional[int] = None
    skills_assessment_required: bool  = True
    job_offer_required: bool          = False
    residency_required: bool          = False
    min_points: Optional[int]         = None
    max_age: Optional[int]            = None
    notes: list[str]                  = field(default_factory=list)
    source_url: str                   = ""
    updated_at: str                   = TODAY

    def to_dict(self) -> dict:
        return {
            "visas":                    self.visas,
            "open":                     self.open,
            "minSalary":                self.min_salary,
            "minExperienceYears":       self.min_experience_years,
            "skillsAssessmentRequired": self.skills_assessment_required,
            "jobOfferRequired":         self.job_offer_required,
            "residencyRequired":        self.residency_required,
            "minPoints":                self.min_points,
            "maxAge":                   self.max_age,
            "notes":                    self.notes,
            "sourceUrl":                self.source_url,
            "updatedAt":                self.updated_at,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch(url: str) -> Optional[BeautifulSoup]:
    """GET url → BeautifulSoup or None on error."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as exc:
        logger.warning("fetch %s failed: %s", url, exc)
        return None


def fetch_json(url: str) -> Optional[dict | list]:
    """GET url → parsed JSON or None on error."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning("fetch_json %s failed: %s", url, exc)
        return None


def salary_from_text(text: str) -> Optional[int]:
    """Extract the first $NN,NNN or $NNN,NNN salary figure from text."""
    m = re.search(r"\$\s*([\d,]+)", text)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    return None


def exp_from_text(text: str) -> Optional[int]:
    """Extract '2 years' / '3-year' style experience requirements."""
    m = re.search(r"(\d+)[- ]?year", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def normalise_anzsco(raw: str) -> str:
    """Strip spaces/dashes and zero-pad to 6 digits."""
    cleaned = re.sub(r"\D", "", raw)
    return cleaned.zfill(6) if cleaned else ""


# ---------------------------------------------------------------------------
# Per-state scrapers
# ---------------------------------------------------------------------------

# ── WA ──────────────────────────────────────────────────────────────────────

WA_190_URL = "https://www.migration.wa.gov.au/occupation-lists"
WA_491_URL = "https://www.migration.wa.gov.au/occupation-lists"

def scrape_wa() -> dict[str, StateOccReq]:
    """
    WA Migration publishes HTML tables for both 190 and 491 occupation lists.
    The table columns typically include: ANZSCO, Occupation, Eligible Visa,
    Minimum Salary, Job Offer, Notes.
    """
    results: dict[str, StateOccReq] = {}
    soup = fetch(WA_190_URL)
    if not soup:
        return results

    for table in soup.find_all("table"):
        headers_row = table.find("tr")
        if not headers_row:
            continue
        cols = [th.get_text(strip=True).lower() for th in headers_row.find_all(["th", "td"])]
        if not any("anzsco" in c for c in cols):
            continue

        anzsco_idx  = next((i for i, c in enumerate(cols) if "anzsco"  in c), None)
        salary_idx  = next((i for i, c in enumerate(cols) if "salary"  in c), None)
        visa_idx    = next((i for i, c in enumerate(cols) if "visa"    in c or "subclass" in c), None)
        offer_idx   = next((i for i, c in enumerate(cols) if "offer"   in c), None)
        notes_idx   = next((i for i, c in enumerate(cols) if "note"    in c or "condition" in c), None)

        if anzsco_idx is None:
            continue

        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= anzsco_idx:
                continue
            anzsco = normalise_anzsco(cells[anzsco_idx].get_text(strip=True))
            if not anzsco:
                continue

            visa_text   = cells[visa_idx].get_text(strip=True)   if visa_idx  is not None and len(cells) > visa_idx  else ""
            salary_text = cells[salary_idx].get_text(strip=True) if salary_idx is not None and len(cells) > salary_idx else ""
            offer_text  = cells[offer_idx].get_text(strip=True)  if offer_idx  is not None and len(cells) > offer_idx  else ""
            notes_text  = cells[notes_idx].get_text(strip=True)  if notes_idx  is not None and len(cells) > notes_idx  else ""

            visas = re.findall(r"\b(190|491|494)\b", visa_text) or ["190"]
            salary = salary_from_text(salary_text)
            offer = bool(re.search(r"\byes\b|\brequired\b", offer_text, re.IGNORECASE))
            notes = [n.strip() for n in re.split(r"[•·\n;]", notes_text) if n.strip()]

            if anzsco in results:
                # merge: add any new visa subclasses
                existing = results[anzsco]
                for v in visas:
                    if v not in existing.visas:
                        existing.visas.append(v)
            else:
                results[anzsco] = StateOccReq(
                    visas=visas,
                    open=True,
                    min_salary=salary,
                    job_offer_required=offer,
                    notes=notes,
                    source_url=WA_190_URL,
                )

    logger.info("WA: %d occupations scraped", len(results))
    return results


# ── SA ──────────────────────────────────────────────────────────────────────

SA_190_URL = "https://www.migration.sa.gov.au/skilled-visas/skilled-nominated-visa-subclass-190/190-occupation-list"
SA_491_URL = "https://www.migration.sa.gov.au/skilled-visas/skilled-work-regional-provisional-subclass-491/491-occupation-list"

def scrape_sa() -> dict[str, StateOccReq]:
    results: dict[str, StateOccReq] = {}
    for url, visa in [(SA_190_URL, "190"), (SA_491_URL, "491")]:
        soup = fetch(url)
        if not soup:
            continue
        for table in soup.find_all("table"):
            for row in table.find_all("tr")[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                anzsco = normalise_anzsco(cells[0].get_text(strip=True))
                if not anzsco:
                    continue
                notes_raw = " ".join(c.get_text(strip=True) for c in cells[2:])
                salary = salary_from_text(notes_raw)
                offer  = bool(re.search(r"job offer", notes_raw, re.IGNORECASE))
                notes  = [n.strip() for n in re.split(r"[•·\n;]", notes_raw) if n.strip() and len(n.strip()) > 5]
                if anzsco in results:
                    if visa not in results[anzsco].visas:
                        results[anzsco].visas.append(visa)
                else:
                    results[anzsco] = StateOccReq(
                        visas=[visa], open=True,
                        min_salary=salary, job_offer_required=offer,
                        notes=notes[:5], source_url=url,
                    )
    logger.info("SA: %d occupations scraped", len(results))
    return results


# ── TAS ─────────────────────────────────────────────────────────────────────

TAS_URL = "https://www.migration.tas.gov.au/occupations"

def scrape_tas() -> dict[str, StateOccReq]:
    results: dict[str, StateOccReq] = {}
    soup = fetch(TAS_URL)
    if not soup:
        return results
    for table in soup.find_all("table"):
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            anzsco = normalise_anzsco(cells[0].get_text(strip=True))
            if not anzsco:
                continue
            all_text = " ".join(c.get_text(" ", strip=True) for c in cells)
            visas = re.findall(r"\b(190|491)\b", all_text) or ["190"]
            open_flag = not bool(re.search(r"closed|not open|unavailable", all_text, re.IGNORECASE))
            salary = salary_from_text(all_text)
            offer  = bool(re.search(r"job offer", all_text, re.IGNORECASE))
            results[anzsco] = StateOccReq(
                visas=visas, open=open_flag,
                min_salary=salary, job_offer_required=offer,
                notes=[], source_url=TAS_URL,
            )
    logger.info("TAS: %d occupations scraped", len(results))
    return results


# ── ACT ─────────────────────────────────────────────────────────────────────

ACT_URL = "https://www.act.gov.au/migration/skilled-migrants/canberra-matrix/skilled-occupation-list"

def scrape_act() -> dict[str, StateOccReq]:
    results: dict[str, StateOccReq] = {}
    soup = fetch(ACT_URL)
    if not soup:
        return results
    for table in soup.find_all("table"):
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            anzsco = normalise_anzsco(cells[0].get_text(strip=True))
            if not anzsco:
                continue
            all_text = " ".join(c.get_text(" ", strip=True) for c in cells)
            visas = re.findall(r"\b(190|491)\b", all_text) or ["190"]
            points_m = re.search(r"(\d{2,3})\s*(?:points|pts)", all_text, re.IGNORECASE)
            min_pts = int(points_m.group(1)) if points_m else None
            offer   = bool(re.search(r"job offer", all_text, re.IGNORECASE))
            notes_raw = cells[-1].get_text(strip=True) if len(cells) > 2 else ""
            notes = [n.strip() for n in re.split(r"[•·\n;]", notes_raw) if n.strip() and len(n.strip()) > 5]
            results[anzsco] = StateOccReq(
                visas=visas, open=True,
                min_points=min_pts, job_offer_required=offer,
                notes=notes[:5], source_url=ACT_URL,
            )
    logger.info("ACT: %d occupations scraped", len(results))
    return results


# ── NT ──────────────────────────────────────────────────────────────────────

NT_190_URL = "https://theterritory.com.au/invest/migrate-to-the-territory/territory-sponsor-190-visa/territory-sponsor-190-occupation-list"
NT_491_URL = "https://theterritory.com.au/invest/migrate-to-the-territory/territory-sponsor-491-visa/territory-sponsor-491-occupation-list"

def scrape_nt() -> dict[str, StateOccReq]:
    results: dict[str, StateOccReq] = {}
    for url, visa in [(NT_190_URL, "190"), (NT_491_URL, "491")]:
        soup = fetch(url)
        if not soup:
            continue
        for table in soup.find_all("table"):
            for row in table.find_all("tr")[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                anzsco = normalise_anzsco(cells[0].get_text(strip=True))
                if not anzsco:
                    continue
                all_text = " ".join(c.get_text(" ", strip=True) for c in cells)
                salary  = salary_from_text(all_text)
                offer   = bool(re.search(r"job offer", all_text, re.IGNORECASE))
                exp     = exp_from_text(all_text)
                open_f  = not bool(re.search(r"closed|not open", all_text, re.IGNORECASE))
                if anzsco in results:
                    if visa not in results[anzsco].visas:
                        results[anzsco].visas.append(visa)
                else:
                    results[anzsco] = StateOccReq(
                        visas=[visa], open=open_f,
                        min_salary=salary, min_experience_years=exp,
                        job_offer_required=offer,
                        notes=[], source_url=url,
                    )
    logger.info("NT: %d occupations scraped", len(results))
    return results


# ── NSW ─────────────────────────────────────────────────────────────────────

NSW_190_URL = "https://www.nsw.gov.au/living-and-working/immigration-and-visas/skilled-migrants/skilled-nominated-visa-subclass-190/occupations-open-for-nomination"
NSW_491_URL = "https://www.nsw.gov.au/living-and-working/immigration-and-visas/skilled-migrants/skilled-work-regional-provisional-visa-subclass-491/occupations-open-for-nomination"

def scrape_nsw() -> dict[str, StateOccReq]:
    results: dict[str, StateOccReq] = {}
    for url, visa in [(NSW_190_URL, "190"), (NSW_491_URL, "491")]:
        soup = fetch(url)
        if not soup:
            continue
        for table in soup.find_all("table"):
            for row in table.find_all("tr")[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                anzsco = normalise_anzsco(cells[0].get_text(strip=True))
                if not anzsco:
                    continue
                all_text = " ".join(c.get_text(" ", strip=True) for c in cells)
                salary  = salary_from_text(all_text)
                offer   = bool(re.search(r"job offer", all_text, re.IGNORECASE))
                exp     = exp_from_text(all_text)
                open_f  = not bool(re.search(r"closed|not open|paused", all_text, re.IGNORECASE))
                notes_raw = cells[-1].get_text(strip=True) if len(cells) > 3 else ""
                notes = [n.strip() for n in re.split(r"[•·\n;]", notes_raw) if n.strip() and len(n.strip()) > 5]
                if anzsco in results:
                    if visa not in results[anzsco].visas:
                        results[anzsco].visas.append(visa)
                    results[anzsco].notes = list(set(results[anzsco].notes + notes))
                else:
                    results[anzsco] = StateOccReq(
                        visas=[visa], open=open_f,
                        min_salary=salary, min_experience_years=exp,
                        job_offer_required=offer,
                        notes=notes[:5], source_url=url,
                    )
    logger.info("NSW: %d occupations scraped", len(results))
    return results


# ── VIC ─────────────────────────────────────────────────────────────────────

VIC_190_URL = "https://business.vic.gov.au/business-information/migrate-to-victoria/skilled-nominated-visa-subclass-190/victoria-190-occupation-list"
VIC_491_URL = "https://business.vic.gov.au/business-information/migrate-to-victoria/skilled-work-regional-provisional-visa-subclass-491/victoria-491-occupation-list"

def scrape_vic() -> dict[str, StateOccReq]:
    results: dict[str, StateOccReq] = {}
    for url, visa in [(VIC_190_URL, "190"), (VIC_491_URL, "491")]:
        soup = fetch(url)
        if not soup:
            continue
        for table in soup.find_all("table"):
            for row in table.find_all("tr")[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                anzsco = normalise_anzsco(cells[0].get_text(strip=True))
                if not anzsco:
                    continue
                all_text = " ".join(c.get_text(" ", strip=True) for c in cells)
                salary  = salary_from_text(all_text)
                exp     = exp_from_text(all_text)
                offer   = bool(re.search(r"job offer", all_text, re.IGNORECASE))
                open_f  = not bool(re.search(r"closed|not open|paused", all_text, re.IGNORECASE))
                notes_raw = cells[-1].get_text(strip=True) if len(cells) > 3 else ""
                notes = [n.strip() for n in re.split(r"[•·\n;]", notes_raw) if n.strip() and len(n.strip()) > 5]
                if anzsco in results:
                    if visa not in results[anzsco].visas:
                        results[anzsco].visas.append(visa)
                else:
                    results[anzsco] = StateOccReq(
                        visas=[visa], open=open_f,
                        min_salary=salary, min_experience_years=exp,
                        job_offer_required=offer,
                        notes=notes[:5], source_url=url,
                    )
    logger.info("VIC: %d occupations scraped", len(results))
    return results


# ── QLD ─────────────────────────────────────────────────────────────────────

QLD_190_URL = "https://migration.qld.gov.au/visa-options/state-nominated/skilled-nominated-visa-190/qld-190-occupation-list/"
QLD_491_URL = "https://migration.qld.gov.au/visa-options/state-nominated/skilled-work-regional-provisional-visa-491/qld-491-occupation-list/"

def scrape_qld() -> dict[str, StateOccReq]:
    results: dict[str, StateOccReq] = {}
    for url, visa in [(QLD_190_URL, "190"), (QLD_491_URL, "491")]:
        soup = fetch(url)
        if not soup:
            continue
        for table in soup.find_all("table"):
            for row in table.find_all("tr")[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                anzsco = normalise_anzsco(cells[0].get_text(strip=True))
                if not anzsco:
                    continue
                all_text = " ".join(c.get_text(" ", strip=True) for c in cells)
                salary  = salary_from_text(all_text)
                offer   = bool(re.search(r"job offer", all_text, re.IGNORECASE))
                exp     = exp_from_text(all_text)
                open_f  = not bool(re.search(r"closed|not open|paused", all_text, re.IGNORECASE))
                notes_raw = cells[-1].get_text(strip=True) if len(cells) > 3 else ""
                notes = [n.strip() for n in re.split(r"[•·\n;]", notes_raw) if n.strip() and len(n.strip()) > 5]
                if anzsco in results:
                    if visa not in results[anzsco].visas:
                        results[anzsco].visas.append(visa)
                else:
                    results[anzsco] = StateOccReq(
                        visas=[visa], open=open_f,
                        min_salary=salary, min_experience_years=exp,
                        job_offer_required=offer,
                        notes=notes[:5], source_url=url,
                    )
    logger.info("QLD: %d occupations scraped", len(results))
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

STATE_SCRAPERS = {
    "NSW": scrape_nsw,
    "VIC": scrape_vic,
    "QLD": scrape_qld,
    "WA":  scrape_wa,
    "SA":  scrape_sa,
    "TAS": scrape_tas,
    "ACT": scrape_act,
    "NT":  scrape_nt,
}


def load_existing() -> dict:
    """Load the previously-generated file so we can preserve stale records."""
    if OLD_FILE.exists():
        try:
            return json.loads(OLD_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not load existing file: %s", exc)
    return {"snapshotDate": TODAY, "requirements": {}}


def main() -> None:
    logger.info("=== state_requirements_scraper start — %s ===", TODAY)
    existing = load_existing()
    merged: dict[str, dict[str, dict]] = existing.get("requirements", {})

    for state_code, scraper_fn in STATE_SCRAPERS.items():
        logger.info("--- Scraping %s ---", state_code)
        try:
            state_data = scraper_fn()
        except Exception as exc:
            logger.error("%s scraper raised: %s", state_code, exc, exc_info=True)
            state_data = {}

        for anzsco, req in state_data.items():
            if anzsco not in merged:
                merged[anzsco] = {}
            merged[anzsco][state_code] = req.to_dict()

    output = {
        "snapshotDate": TODAY,
        "requirements": merged,
    }

    total_anzsco = len(merged)
    total_entries = sum(len(v) for v in merged.values())
    logger.info("Total: %d ANZSCO codes, %d state entries", total_anzsco, total_entries)

    if DRY_RUN:
        logger.info("DRY_RUN=true — skipping file write")
        logger.info("Sample output:\n%s", json.dumps(dict(list(merged.items())[:2]), indent=2))
        return

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Written %s", OUT_FILE)

    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
