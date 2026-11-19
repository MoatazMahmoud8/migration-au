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
import sys
from datetime import date
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
VISA_TYPES_FILE = PUBLIC / "visa-types.json"

# Fallback landing page used only when a subclass has no verified URL.
VISA_LISTING_URL = "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing"


def load_verified_urls() -> dict[str, str]:
    """
    Build a {subclass -> canonical DHA url} map from visa-types.json, which is
    scraped directly from the DHA visa-listing page. This keeps processing-time
    links correct automatically on every build, even when DHA changes a slug.
    """
    urls: dict[str, str] = {}
    if VISA_TYPES_FILE.exists():
        try:
            data = json.loads(VISA_TYPES_FILE.read_text(encoding="utf-8"))
            for v in data.get("visas", []):
                code = str(v.get("code", "")).strip()
                url = v.get("url")
                if code and url and url.startswith("https://"):
                    urls[code] = url
            log.info("Loaded %d verified visa URLs from visa-types.json", len(urls))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Could not load visa-types.json: %s", e)
    return urls


# Cache HEAD-check results within a run to avoid duplicate network calls.
_url_status_cache: dict[str, int | None] = {}


def url_is_live(url: str) -> bool | None:
    """
    HEAD-check a URL. Returns:
      True  → 200 (definitely good)
      False → 404/410 (definitely broken)
      None  → inconclusive (network error / other status) — caller should not
              downgrade based on this.
    """
    if url in _url_status_cache:
        code = _url_status_cache[url]
    else:
        code = None
        try:
            import urllib.request
            req = urllib.request.Request(
                url, method="HEAD",
                headers={"User-Agent": "Mozilla/5.0 (compatible; MigrateAU-Bot/1.0)"},
            )
            code = urllib.request.urlopen(req, timeout=15).getcode()
        except Exception as e:  # noqa: BLE001 — includes HTTPError
            code = getattr(e, "code", None)
        _url_status_cache[url] = code

    if code == 200:
        return True
    if code in (404, 410):
        return False
    return None


def resolve_url(subclass: str, current_url: str | None, verified_urls: dict[str, str]) -> str:
    """
    Pick the best URL for a subclass by validating candidates in priority order:
      1. VISA_META hardcoded URL (manually verified)
      2. verified_urls (from visa-types.json)
      3. the entry's current URL
    Returns the first candidate that HEAD-checks as live (200). If none are
    confirmed live but some are only inconclusive (network issues), keep the
    top candidate. Only if a candidate is confirmed broken (404) and no live
    candidate exists do we fall back to the visa-listing landing page.
    """
    candidates: list[str] = []
    for c in (
        (VISA_META.get(subclass) or {}).get("url"),
        verified_urls.get(subclass),
        current_url,
    ):
        if c and c.startswith("https://") and c not in candidates:
            candidates.append(c)

    if not candidates:
        return VISA_LISTING_URL

    any_broken = False
    for c in candidates:
        status = url_is_live(c)
        if status is True:
            return c
        if status is False:
            any_broken = True

    # No candidate confirmed live.
    if any_broken:
        # Top candidate is broken and nothing else works → safe landing page.
        return VISA_LISTING_URL
    # All inconclusive (e.g. CI can't reach DHA) → trust the top candidate.
    return candidates[0]


# ─── Category / icon / color mapping ─────────────────────────────────────────
# Based on the app's bundled constants/processingTimes.ts
# NOTE: the "url" values below are only fallbacks — the canonical URL is pulled
# from visa-types.json at runtime via load_verified_urls().

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
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-regional-191"},
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
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/student-590"},
    "600": {"category": "Visitor", "icon": "airplane-outline", "color": "#4CAF50",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/visitor-600"},
    "601": {"category": "Visitor", "icon": "airplane-outline", "color": "#4CAF50",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/electronic-travel-authority-601"},
    "651": {"category": "Visitor", "icon": "airplane-outline", "color": "#4CAF50",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/evisitor-651"},
    "820": {"category": "Family", "icon": "heart-outline", "color": "#E91E63",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/partner-onshore"},
    "309": {"category": "Family", "icon": "heart-outline", "color": "#E91E63",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/partner-offshore"},
    "143": {"category": "Family", "icon": "people-outline", "color": "#E91E63",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/contributory-parent-143"},
    "103": {"category": "Family", "icon": "people-outline", "color": "#E91E63",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/parent-103"},
    "101": {"category": "Family", "icon": "people-outline", "color": "#E91E63",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/child-101"},
    "417": {"category": "Visitor", "icon": "walk-outline", "color": "#4CAF50",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/work-holiday-417"},
    "462": {"category": "Visitor", "icon": "walk-outline", "color": "#4CAF50",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/work-holiday-462"},
    "407": {"category": "Employer", "icon": "school-outline", "color": "#FF9800",
            "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/training-407"},
}

# Default meta for unknown subclasses
DEFAULT_META = {"category": "Skilled", "icon": "document-outline", "color": "#607D8B",
                "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-processing-times/global-visa-processing-times"}


# DHA's own processing-times page is a client-rendered SPA with no <table>
# markup in the DOM — it fetches its data from this public, unauthenticated
# API at runtime. Calling it directly is far more reliable than rendering the
# page and scraping tables that don't exist (which silently failed on every
# run and caused this script to repeatedly re-publish stale fallback data).
GPT_API_URL = "https://immi.homeaffairs.gov.au/_layouts/15/api/GPT.aspx/GetVisaGlobalProcessingTime"

# Display names for each monitored subclass (DHA's GPT API only returns
# stream names + percentiles, not the visa's display name).
VISA_NAMES = {
    "189": "Skilled Independent",
    "190": "Skilled Nominated",
    "491": "Skilled Work Regional (Provisional)",
    "887": "Skilled Regional (Residence)",
    "191": "Permanent Residence (Skilled Regional)",
    "482": "Skills in Demand (Temporary)",
    "494": "Skilled Employer Sponsored Regional",
    "186": "Employer Nomination Scheme",
    "485": "Temporary Graduate",
    "500": "Student Visa",
    "590": "Student Guardian",
    "600": "Visitor",
    "601": "Electronic Travel Authority",
    "651": "eVisitor",
    "820": "Partner (Onshore Temporary)",
    "309": "Partner (Offshore Temporary)",
    "143": "Contributory Parent",
    "103": "Parent",
    "101": "Child",
    "417": "Working Holiday",
    "462": "Work and Holiday",
    "407": "Training",
}


def _normalize_gpt_duration(text: str | None) -> str | None:
    """Return a cleaned duration string, or None for DHA's placeholder text."""
    if not text or not isinstance(text, str):
        return None
    t = text.strip()
    if not t or "not available" in t.lower():
        return None
    return t


def fetch_live_processing_times() -> list[dict]:
    """
    Query DHA's official GPT.aspx API — the same endpoint the processing-times
    page itself calls client-side — for every monitored subclass. Returns
    structured v2-schema items (with "streams"), skipping subclasses for which
    DHA publishes no percentile data at all (e.g. 103/143 parent visas).
    """
    import requests

    items: list[dict] = []
    headers = {"Content-Type": "application/json; charset=UTF-8", "Accept": "application/json"}

    for subclass in VISA_META:
        try:
            payload = {"gptRequest": [{"VisaSubclassCode": subclass, "StreamCode": ""}]}
            resp = requests.post(GPT_API_URL, data=json.dumps(payload), headers=headers, timeout=20)
            resp.raise_for_status()
            body = resp.json().get("d", {})
            if not body.get("success"):
                log.warning("GPT API reported failure for SC %s", subclass)
                continue
            records = body.get("data") or []
        except Exception as e:
            log.warning("GPT API request failed for SC %s: %s", subclass, e)
            continue

        streams = []
        for record in records:
            p50 = _normalize_gpt_duration(record.get("Percent50"))
            p90 = _normalize_gpt_duration(record.get("Percent90"))
            if not p50 or not p90:
                continue
            stream = {"p50": p50, "p90": p90}
            stream_name = record.get("StreamText")
            if isinstance(stream_name, str) and stream_name.strip():
                stream["name"] = stream_name.strip()
            streams.append(stream)

        if not streams:
            log.info("SC %s: no usable processing time data published by DHA.", subclass)
            continue

        meta = VISA_META.get(subclass, DEFAULT_META)
        items.append({
            "subclass": subclass,
            "name": VISA_NAMES.get(subclass, f"Subclass {subclass}"),
            "category": meta["category"],
            "streams": streams,
            "icon": meta["icon"],
            "color": meta["color"],
            "url": meta["url"],
        })
        log.info("SC %s: %d stream(s) fetched live from DHA", subclass, len(streams))

    return items


def load_existing() -> dict:
    """Load existing processing-times.json as fallback."""
    if OUTPUT.exists():
        try:
            return json.loads(OUTPUT.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"snapshotDate": "", "items": []}


def normalize_items(items: list[dict]) -> list[dict]:
    """Group legacy subclass/stream rows into the v2 streams schema."""
    grouped: dict[str, dict] = {}
    for raw in items:
        subclass = str(raw.get("subclass", "")).strip()
        if not subclass:
            continue

        streams = raw.get("streams")
        if not isinstance(streams, list):
            p50 = raw.get("p50")
            p90 = raw.get("p90")
            if not isinstance(p50, str) or not p50.strip() or not isinstance(p90, str) or not p90.strip():
                continue
            streams = [{"name": raw.get("stream"), "p50": p50, "p90": p90}]

        if subclass not in grouped:
            item = {
                key: value
                for key, value in raw.items()
                if key not in {"p50", "p90", "stream", "streams"}
            }
            item["streams"] = []
            grouped[subclass] = item

        existing_streams = grouped[subclass]["streams"]
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            p50 = stream.get("p50")
            p90 = stream.get("p90")
            if not isinstance(p50, str) or not p50.strip() or not isinstance(p90, str) or not p90.strip():
                continue
            normalized = {"p50": p50.strip(), "p90": p90.strip()}
            name = stream.get("name")
            if isinstance(name, str) and name.strip():
                normalized["name"] = name.strip()
            stream_key = normalized.get("name", "")
            if not any(existing.get("name", "") == stream_key for existing in existing_streams):
                existing_streams.append(normalized)

    return [item for item in grouped.values() if item["streams"]]


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
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/skilled-regional-191"},
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
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/student-590"},
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
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/partner-onshore"},
        {"subclass": "309", "name": "Partner (Offshore Temporary)", "category": "Family",
         "p50": "14 months", "p90": "24 months", "icon": "heart-outline", "color": "#E91E63",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/partner-offshore"},
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
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/work-holiday-462"},
        {"subclass": "407", "name": "Training", "category": "Employer",
         "p50": "2 months", "p90": "4 months", "icon": "school-outline", "color": "#FF9800",
         "url": "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/training-407"},
    ]


def main() -> int:
    today = date.today().isoformat()

    # Load DHA-verified URLs so every entry links to the correct visa page.
    verified_urls = load_verified_urls()

    def apply_verified_urls(entries: list[dict]) -> int:
        """Resolve each entry to a validated, live DHA url."""
        fixed = 0
        for e in entries:
            sc = str(e.get("subclass", ""))
            best = resolve_url(sc, e.get("url"), verified_urls)
            if best != e.get("url"):
                e["url"] = best
                fixed += 1
        return fixed

    # Fetch live data from DHA's GPT API for every monitored subclass.
    try:
        items = fetch_live_processing_times()
    except Exception as e:
        log.error("Live GPT API fetch failed entirely: %s", e)
        items = []

    if items:
        log.info("Successfully fetched %d processing time entries live from DHA.", len(items))

    # Some subclasses (e.g. 103/143 parent visas) have no published percentile
    # data at all — fall back to existing/seed data for those only, rather
    # than discarding the live data we DID get for everything else.
    live_subclasses = {item["subclass"] for item in items}
    missing = [sc for sc in VISA_META if sc not in live_subclasses]
    if missing:
        log.info("No live data for SC %s — using existing/seed fallback for these only.",
                  ", ".join(missing))
        existing_by_sc = {
            str(i.get("subclass")): i
            for i in normalize_items(load_existing().get("items", []))
        }
        seed_by_sc = {str(i.get("subclass")): i for i in normalize_items(get_seed_data())}
        for sc in missing:
            fallback_item = existing_by_sc.get(sc) or seed_by_sc.get(sc)
            if fallback_item:
                items.append(fallback_item)

    if not items:
        log.error("No processing time data available at all (live + fallback) — aborting.")
        return 1

    items = normalize_items(items)

    # Ensure every entry links to the correct, DHA-verified URL.
    fixed = apply_verified_urls(items)
    log.info("Applied %d verified URLs from visa-types.json.", fixed)

    # Build output
    output = {
        "schemaVersion": 2,
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
