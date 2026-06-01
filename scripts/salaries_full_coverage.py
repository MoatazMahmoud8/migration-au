#!/usr/bin/env python3
"""
salaries_full_coverage.py
=========================
Comprehensive salary estimator for all 1,236 ANZSCO occupations.

Strategy:
  1. Start with JSA salaries (266 occupations) — highest priority
  2. Load all-anzsco-occupations.json (1,236 total)
  3. For each unmatched occupation, estimate from Fairwork award rates
  4. Match occupation name/keywords to award categories
  5. Apply minimum wage + estimated uplift for skill level
  6. Output salaries.json with all 1,236 occupations

Fairwork 2026 Award Rates (approximate):
  - Minimum wage: $23.23/hr → $45,659/yr (38-hour week)
  - Award rates vary: $25-$50/hr depending on qualification level
  - Skilled trades: typically $30-45/hr
  - Professionals: typically $35-65/hr
  - Managers: typically $50-100+/hr
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "public"
JSA_FILE = OUTPUT_DIR / "salaries.json"
ALL_ANZSCO_FILE = OUTPUT_DIR / "all-anzsco-occupations.json"
OUTPUT_FILE = OUTPUT_DIR / "salaries-comprehensive.json"

# Fairwork 2026 Minimum wage: $23.23/hour, 38-hour week, 52 weeks
FAIRWORK_MIN_WAGE = 23.23
FAIRWORK_MIN_WEEKLY = FAIRWORK_MIN_WAGE * 38  # $883.74
FAIRWORK_MIN_ANNUAL = FAIRWORK_MIN_WEEKLY * 52  # $45,954.48

# Award rate mapping: category pattern → hourly rate (estimated 2026)
AWARD_RATES = {
    r"\b(manager|director|executive|ceo|cfo|cto|principal)\b": 60.0,  # $120k+
    r"\b(professional|engineer|architect|surveyor|scientist|analyst|consultant)\b": 50.0,  # $100k
    r"\b(doctor|physician|surgeon|dentist|lawyer|solicitor|barrister)\b": 70.0,  # $140k+
    r"\b(nurse|aged care|health|therapist|psychologist|counselor)\b": 40.0,  # $80k
    r"\b(teacher|educator|trainer|lecturer|professor)\b": 45.0,  # $90k
    r"\b(electrician|plumber|mechanic|carpenter|builder|tradesperson|tradesman)\b": 38.0,  # $76k
    r"\b(hvac|refrigeration|locksmith|fence|roof)\b": 37.0,  # $74k
    r"\b(driver|truck|bus|transport|logistics)\b": 32.0,  # $64k
    r"\b(sales|retail|customer service|checkout|cashier|attendant)\b": 26.0,  # $52k
    r"\b(chef|cook|kitchen|barista|cafe|restaurant)\b": 28.0,  # $56k
    r"\b(housekeeper|cleaner|janitor|laundry|sanitation)\b": 25.0,  # $50k
    r"\b(labourer|labour|general|assistant|helper|operator|loader)\b": 26.0,  # $52k
    r"\b(security|guard|patrol|bouncer)\b": 27.0,  # $54k
    r"\b(childcare|educator|carer|support|disability|aged care)\b": 29.0,  # $58k
    r"\b(accounting|accountant|bookkeeper|auditor|tax)\b": 48.0,  # $96k
    r"\b(it|software|programmer|developer|sys|admin|network|database)\b": 55.0,  # $110k
    r"\b(marketing|advertising|pr|communications|media)\b": 45.0,  # $90k
    r"\b(human resource|hr|recruitment|training)\b": 42.0,  # $84k
    r"\b(real estate|property|agent|broker)\b": 35.0,  # $70k (+ commission)
    r"\b(farming|agriculture|horticulture|vineyard|livestock)\b": 28.0,  # $56k
    r"\b(manufacturing|factory|production|assembly|machine operator)\b": 32.0,  # $64k
}


def estimate_salary_from_occupation_name(name: str) -> tuple[float, float]:
    """
    Estimate hourly and annual salary based on occupation name and keywords.
    Returns: (hourly_rate, annual_salary)
    """
    name_lower = name.lower()

    # Check against award rate patterns
    for pattern, hourly in sorted(AWARD_RATES.items(), key=lambda x: len(x[0]), reverse=True):
        if re.search(pattern, name_lower):
            annual = hourly * 38 * 52
            return hourly, annual

    # Default: minimum wage for unmatched occupations
    return FAIRWORK_MIN_WAGE, FAIRWORK_MIN_ANNUAL


def main():
    logger.info("=" * 70)
    logger.info("COMPREHENSIVE SALARY COVERAGE FOR ALL 1,236 ANZSCO OCCUPATIONS")
    logger.info("=" * 70)

    # Load existing JSA salaries
    jsa_data = {}
    if JSA_FILE.exists():
        try:
            with open(JSA_FILE) as f:
                data = json.load(f)
                jsa_data = data.get("salaries", {})
            logger.info(f"✓ Loaded {len(jsa_data)} JSA salaries")
        except Exception as e:
            logger.warning(f"Failed to load JSA data: {e}")

    # Load all ANZSCO occupations
    all_anzsco = {}
    if ALL_ANZSCO_FILE.exists():
        try:
            with open(ALL_ANZSCO_FILE) as f:
                data = json.load(f)
                for item in data.get("items", []):
                    all_anzsco[item["anzsco"]] = item.get("name", "Unknown")
            logger.info(f"✓ Loaded {len(all_anzsco)} all-anzsco occupations")
        except Exception as e:
            logger.warning(f"Failed to load all-anzsco data: {e}")

    if not all_anzsco:
        logger.error("No all-anzsco-occupations.json found. Exiting.")
        return

    # Build comprehensive salary data
    logger.info("🔄 Estimating salaries for all occupations...")
    comprehensive = {}
    matched_jsa = 0
    estimated_fairwork = 0

    for anzsco, name in sorted(all_anzsco.items()):
        # Priority 1: Use JSA data if available
        if anzsco in jsa_data:
            jsa_entry = jsa_data[anzsco]
            comprehensive[anzsco] = {
                "weeklyEarnings": jsa_entry.get("weeklyEarnings"),
                "annualSalary": jsa_entry.get("annualSalary"),
                "currency": "AUD",
                "occupationName": jsa_entry.get("occupationName", name),
                "sourceUrl": jsa_entry.get("sourceUrl"),
                "sourceLevel": jsa_entry.get("sourceLevel", "6-digit"),
                "sources": ["JSA"],
            }
            matched_jsa += 1
        else:
            # Priority 2: Estimate from Fairwork award rates
            hourly, annual = estimate_salary_from_occupation_name(name)
            weekly = hourly * 38
            comprehensive[anzsco] = {
                "weeklyEarnings": int(weekly),
                "annualSalary": int(annual),
                "currency": "AUD",
                "occupationName": name,
                "sourceUrl": "https://www.fairwork.gov.au",
                "sourceLevel": "estimated",
                "sources": ["Fairwork", "Keyword estimation"],
            }
            estimated_fairwork += 1

    # Generate output
    output = {
        "snapshotDate": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "source": "Multiple sources (JSA, Fairwork, ANZSCO)",
        "sourceUrl": "JSA: https://www.jobsandskills.gov.au | Fairwork: https://www.fairwork.gov.au",
        "sources": {
            "JSA": "Jobs and Skills Australia — official median earnings (266 occupations)",
            "Fairwork": "Fair Work Commission — award rates and minimum wage",
            "ANZSCO": "Australian and New Zealand Standard Classification of Occupations",
            "Estimation": "Keyword-based estimation from occupation name",
        },
        "salaries": comprehensive,
    }

    # Save output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    # Stats
    all_annual = [s["annualSalary"] for s in comprehensive.values()]
    logger.info("=" * 70)
    logger.info(f"✓ COMPLETE: {len(comprehensive)} occupations with salaries")
    logger.info(f"  JSA verified:      {matched_jsa} occupations")
    logger.info(f"  Fairwork estimated: {estimated_fairwork} occupations")
    logger.info(f"  Salary range: ${min(all_annual):,} - ${max(all_annual):,} AUD/yr")
    logger.info(f"  Median salary: ${sorted(all_annual)[len(all_annual)//2]:,} AUD/yr")
    logger.info(f"  Output: {OUTPUT_FILE}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
