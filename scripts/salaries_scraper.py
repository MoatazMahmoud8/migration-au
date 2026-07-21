"""
Salaries scraper — pulls median weekly earnings for each ANZSCO occupation
from Jobs and Skills Australia (jobsandskills.gov.au, the official AU
government replacement for the legacy Job Outlook / Labour Market Insights
sites) and writes the result to public/salaries.json for Firebase Hosting.

Output schema (consumed by expo-app/utils/salaries.ts):
{
  "snapshotDate": "YYYY-MM-DD",
  "lastUpdated": "ISO-8601",
  "source": "Jobs and Skills Australia",
  "sourceUrl": "https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations",
  "salaries": {
    "<anzsco>": {
      "weeklyEarnings": 2537,        # AUD median weekly, integer
      "annualSalary": 131924,        # weekly * 52, integer
      "currency": "AUD",
      "occupationName": "Software Engineers",
      "sourceUrl": "https://www.jobsandskills.gov.au/..."
    }
  }
}

The list of codes to fetch is sourced from
public/state-occupation-requirements.json so we only ever scrape the
occupations the app actually shows.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "public"
OUTPUT_FILE = PUBLIC_DIR / "salaries.json"
# Cached JSA index so CI can still fetch salary pages even when the live
# sitemap times out (a known issue from GitHub Actions IP ranges).
INDEX_CACHE_FILE = ROOT / "scripts" / "jsa_index_cache.json"

INDEX_URL = "https://www.jobsandskills.gov.au/sitemap-default.xml"
PROFILE_BASE = (
    "https://www.jobsandskills.gov.au/"
    "data/occupation-and-industry-profiles/occupations/"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
}

REQUEST_TIMEOUT = 60  # Increased from 20s for slow JSA endpoints in GitHub Actions
REQUEST_RETRIES = 3
REQUEST_BACKOFF = 2  # exponential backoff multiplier
MAX_WORKERS = 6
INTER_REQUEST_SLEEP = 0.15  # extra politeness between submissions

WEEKLY_RE = re.compile(
    r"MEDIAN\s+WEEKLY\s+EARNINGS\s+\$\s*([\d,]+)",
    re.IGNORECASE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("salaries")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_anzsco_codes() -> list[str]:
    """Load the canonical list of ANZSCO codes the app cares about."""
    state_req = PUBLIC_DIR / "state-occupation-requirements.json"
    codes: set[str] = set()

    if state_req.exists():
        data = json.loads(state_req.read_text())
        codes.update((data.get("requirements") or {}).keys())

    # Fallback: pull codes from the expo-app's bundled occupation list so we
    # cover everything the UI may render (and not just the state-requirement
    # subset).
    expo_const = (
        ROOT.parent / "expo-app" / "constants" / "skilledOccupations.ts"
    )
    if expo_const.exists():
        for m in re.finditer(r"anzsco:\s*['\"](\d+)['\"]", expo_const.read_text()):
            codes.add(m.group(1))

    return sorted(codes)


def _load_index_cache() -> dict[str, tuple[str, str]]:
    """Return the committed JSA index cache, or an empty dict if missing."""
    if not INDEX_CACHE_FILE.exists():
        return {}
    try:
        raw: dict[str, list[str]] = json.loads(INDEX_CACHE_FILE.read_text())
        mapping = {code: (entry[0], entry[1]) for code, entry in raw.items()}
        log.info("Loaded %d entries from local JSA index cache.", len(mapping))
        return mapping
    except Exception as exc:
        log.warning("Could not read JSA index cache: %s", exc)
        return {}


def _save_index_cache(mapping: dict[str, tuple[str, str]]) -> None:
    """Persist the freshly-fetched index for future CI runs."""
    try:
        serialisable = {code: list(entry) for code, entry in mapping.items()}
        INDEX_CACHE_FILE.write_text(json.dumps(serialisable, indent=2) + "\n")
        log.info("Saved %d entries to JSA index cache.", len(mapping))
    except Exception as exc:
        log.warning("Could not write JSA index cache: %s", exc)


def _build_index(session: requests.Session) -> dict[str, tuple[str, str]]:
    """Map ANZSCO code -> (url, occupation name) using JSA's XML sitemap.

    The sitemap lists every occupation profile URL as ``<code>-<kebab-slug>``,
    which gives us both the canonical URL and a clean fallback name.

    On success the resulting index is persisted to ``scripts/jsa_index_cache.json``
    so that subsequent CI runs can use it even when the live sitemap is unreachable
    (GitHub Actions IP ranges are intermittently blocked by JSA).
    """
    log.info("Fetching JSA sitemap …")
    resp = None
    for attempt in range(REQUEST_RETRIES):
        try:
            resp = session.get(INDEX_URL, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt < REQUEST_RETRIES - 1:
                wait_time = REQUEST_BACKOFF ** attempt
                log.warning("Attempt %d failed: %s. Retrying in %ds...", attempt + 1, exc, wait_time)
                time.sleep(wait_time)
            else:
                log.warning(
                    "Could not fetch JSA sitemap after %d attempts: %s — using local cache.",
                    REQUEST_RETRIES,
                    exc,
                )
                cached = _load_index_cache()
                if cached:
                    return cached
                raise  # nothing to fall back to

    mapping: dict[str, tuple[str, str]] = {}
    pat = re.compile(
        r"https?://[^<\s]*/occupations/(\d+)-([a-z0-9-]+)",
        re.IGNORECASE,
    )
    for url, code, slug in (
        (m.group(0), m.group(1), m.group(2)) for m in pat.finditer(resp.text)
    ):
        if code in mapping:
            continue
        name = slug.replace("-", " ").title()
        mapping[code] = (url, name)

    log.info("Indexed %d occupation pages.", len(mapping))
    _save_index_cache(mapping)
    return mapping


def _extract_weekly(html: str) -> Optional[int]:
    """Parse the median weekly earnings (AUD) out of a profile page.

    JSA renders the metric tiles as separate DOM nodes, so we normalise the
    page down to plain text first and then look for the labelled value.
    Pages where the value is unavailable show ``N/A`` and are skipped.
    """
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    m = WEEKLY_RE.search(text)
    if not m:
        return None
    try:
        value = int(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return value if value > 0 else None


def _fetch_one(
    session: requests.Session,
    code: str,
    url: str,
    name: str,
    index: dict[str, tuple[str, str]],
) -> Optional[dict]:
    """Fetch a single occupation page; fall back to the 4-digit unit group.

    JSA only publishes earnings at the 4-digit ANZSCO unit-group level for
    most occupations — 6-digit pages routinely show ``N/A``. We therefore try
    the requested page first and, if no value is found, retry against the
    parent 4-digit code.
    """
    attempts: list[tuple[str, str, str]] = [(code, url, name)]
    if len(code) == 6:
        parent_code = code[:4]
        parent = index.get(parent_code)
        if parent:
            attempts.append((parent_code, parent[0], parent[1]))

    for level_code, level_url, level_name in attempts:
        try:
            resp = session.get(level_url, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            log.warning("Fetch failed for %s: %s", level_code, exc)
            continue
        if resp.status_code != 200:
            log.warning("HTTP %d for %s (%s)", resp.status_code, level_code, level_url)
            continue
        weekly = _extract_weekly(resp.text)
        if weekly is None:
            continue
        return {
            "weeklyEarnings": weekly,
            "annualSalary": weekly * 52,
            "currency": "AUD",
            "occupationName": level_name,
            "sourceUrl": level_url,
            "sourceLevel": "6-digit" if level_code == code else "4-digit",
        }
    return None


def _fetch_salary_for_code(
    session: requests.Session,
    code: str,
    index: dict[str, tuple[str, str]],
) -> Optional[dict]:
    entry = index.get(code)
    if not entry:
        return None
    url, name = entry
    return _fetch_one(session, code, url, name, index)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    codes = _load_anzsco_codes()
    lookup_codes = sorted(set(codes) | {code[:4] for code in codes if len(code) == 6})
    log.info("Will look up salaries for %d ANZSCO codes.", len(codes))
    log.info("Including %d parent unit-group codes for salary fallback.", len(lookup_codes) - len(codes))
    if not codes:
        log.error("No ANZSCO codes found — aborting.")
        return 1

    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        index = _build_index(session)
    except requests.RequestException as exc:
        log.error("Could not fetch JSA index: %s", exc)
        log.info("Falling back to existing salary data (no updates this run).")
        # Use existing data as fallback - don't crash the workflow
        if OUTPUT_FILE.exists():
            try:
                existing_payload = json.loads(OUTPUT_FILE.read_text())
                log.info("Using existing data with %d salaries.", len(existing_payload.get("salaries", {})))
                return 0  # Exit successfully with existing data
            except (json.JSONDecodeError, OSError):
                pass
        log.error("No existing salary data to fall back to.")
        return 1

    # Preserve previous results so a transient failure doesn't blow away data.
    existing: dict[str, dict] = {}
    if OUTPUT_FILE.exists():
        try:
            existing = (
                json.loads(OUTPUT_FILE.read_text()).get("salaries") or {}
            )
        except (json.JSONDecodeError, OSError):
            existing = {}

    results: dict[str, dict] = dict(existing)
    fetched = 0
    missing: list[str] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        for code in lookup_codes:
            entry = index.get(code)
            if not entry:
                missing.append(code)
                continue
            url, name = entry
            fut = pool.submit(_fetch_one, session, code, url, name, index)
            futures[fut] = code
            time.sleep(INTER_REQUEST_SLEEP)

        for fut in as_completed(futures):
            code = futures[fut]
            data = fut.result()
            if data is not None:
                results[code] = data
                fetched += 1

    if missing:
        log.info(
            "No JSA profile URL found for %d codes (sample: %s)",
            len(missing),
            ", ".join(missing[:5]),
        )

    log.info("Salaries fetched this run: %d", fetched)
    log.info("Total salaries in output: %d", len(results))

    if not results:
        log.error("No salary data — refusing to overwrite output.")
        return 1

    now = datetime.now(timezone.utc)
    payload = {
        "snapshotDate": now.date().isoformat(),
        "lastUpdated": now.isoformat(timespec="seconds"),
        "source": "Jobs and Skills Australia",
        "sourceUrl": INDEX_URL,
        "salaries": dict(sorted(results.items())),
    }

    OUTPUT_FILE.write_text(json.dumps(payload, indent=2) + "\n")
    log.info("Wrote %s (%d salaries).", OUTPUT_FILE, len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
