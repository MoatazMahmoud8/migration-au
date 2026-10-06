#!/usr/bin/env python3
"""
state_news_scraper.py
=====================
Scrapes Australian state migration news pages and updates Firebase Firestore.

Designed to run via GitHub Actions every three hours.

Supported sources:
  - Victoria (Skills Victoria)
  - New South Wales (NSW Skills)
  - Queensland (Trade and Investment QLD)
  - South Australia (Migration SA)
  - Western Australia (Migration WA)

Requirements:
    pip install requests beautifulsoup4 google-cloud-firestore python-dateutil

Environment variables:
    FIREBASE_SERVICE_ACCOUNT_JSON  — base64-encoded Firebase service account JSON
    DRY_RUN                        — set to "true" to skip Firestore writes (optional)
"""

import base64
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from google.cloud import firestore
from google.oauth2 import service_account

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
# Configuration
# ---------------------------------------------------------------------------
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MigrationAU-Bot/1.0; "
        "+https://github.com/yourorg/migration-au)"
    )
}

REQUEST_TIMEOUT = 20  # seconds


@dataclass
class ScraperSource:
    name: str
    state_code: str
    url: str
    article_selector: str       # CSS selector for article containers
    title_selector: str         # within article container
    summary_selector: str       # within article container
    link_selector: str          # within article container (href)
    date_selector: str          # within article container
    base_url: str = ""          # prepend to relative hrefs
    use_playwright: bool = False  # render with headless Chromium (JS-driven pages)


# NOTE (2026-10-06): Skills Victoria and Migration NSW's old news/article pages
# have both been retired by their respective sites (VIC: business.vic.gov.au's
# migration section 404s entirely now -- the site was restructured and no
# equivalent article-based news page could be located; NSW: the "topics/
# skilled-migration-to-nsw" page 404s too, and its closest replacement
# (nsw-skills-lists) is a static reference page with no dated articles, not a
# news feed). Both were silently returning 0 articles on every run for weeks.
# Removed rather than left broken; re-add once a real replacement URL with
# dated article cards is found for each state.
SOURCES: list[ScraperSource] = [
    ScraperSource(
        name="Migration SA",
        state_code="SA",
        url="https://migration.sa.gov.au/news",
        # SA's news list is rendered client-side (no article HTML in the raw
        # response), so this source requires Playwright. Verified card shape:
        # <div class="col-span-full ... pb-site ..."><span>date</span>
        #   <h3 class="t-subheading">title</h3><a href="...">Read More</a></div>
        article_selector="div.col-span-full.pb-site",
        title_selector="h3.t-subheading, h3",
        summary_selector="p",
        link_selector="a[href]",
        date_selector="span",
        base_url="https://migration.sa.gov.au",
        use_playwright=True,
    ),
]

# ---------------------------------------------------------------------------
# Firestore client
# ---------------------------------------------------------------------------

def build_firestore_client() -> firestore.Client:
    """Build Firestore client from base64-encoded service account JSON."""
    encoded = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not encoded:
        raise EnvironmentError(
            "FIREBASE_SERVICE_ACCOUNT_JSON environment variable is not set."
        )

    decoded = base64.b64decode(encoded).decode("utf-8")
    service_account_info = json.loads(decoded)

    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )

    return firestore.Client(
        project=service_account_info["project_id"],
        credentials=credentials,
    )


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

@dataclass
class NewsArticle:
    title: str
    summary: str
    url: str
    state: str
    source: str
    published_at: datetime
    occupations: list[str] = field(default_factory=list)
    doc_id: str = ""

    def __post_init__(self):
        # Generate a stable document ID from URL
        self.doc_id = hashlib.md5(self.url.encode()).hexdigest()[:16]


def extract_anzsco_codes(text: str) -> list[str]:
    """Extract ANZSCO occupation codes (6-digit numbers) from text."""
    return re.findall(r'\b[1-9]\d{5}\b', text)


def parse_date(date_text: str) -> datetime:
    """Parse a date string into a timezone-aware datetime."""
    try:
        dt = dateparser.parse(date_text, fuzzy=True)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt or datetime.now(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def fetch_rendered_html(url: str) -> Optional[str]:
    """Fetch a page's fully-rendered (post-JS) HTML using headless Chromium.

    Needed for sources whose news lists are populated client-side, where a
    plain `requests.get` only returns the empty app shell.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                ))
                page.goto(url, timeout=30000, wait_until="networkidle")
                return page.content()
            finally:
                browser.close()
    except Exception as e:
        logger.warning(f"Playwright render failed for {url}: {e}")
        return None


def scrape_source(source: ScraperSource) -> list[NewsArticle]:
    """Scrape a single source and return a list of NewsArticle objects."""
    logger.info(f"Scraping {source.name} ({source.state_code})...")

    if source.use_playwright:
        html = fetch_rendered_html(source.url)
        if html is None:
            return []
    else:
        try:
            response = requests.get(source.url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch {source.url}: {e}")
            return []
        html = response.text

    soup = BeautifulSoup(html, "html.parser")
    containers = soup.select(source.article_selector)

    if not containers:
        logger.warning(f"No articles found for {source.name} with selector '{source.article_selector}'")
        return []

    articles = []
    seen_urls: set[str] = set()
    for container in containers:  # de-duped below; cap applied after dedup
        try:
            # Title
            title_el = container.select_one(source.title_selector)
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue

            # Summary
            summary_el = container.select_one(source.summary_selector)
            summary = summary_el.get_text(strip=True) if summary_el else ""

            # Link
            link_el = container.select_one(source.link_selector)
            href = link_el.get("href", "") if link_el else ""
            if href and href.startswith("/"):
                href = source.base_url + href
            if not href or not href.startswith("http"):
                # Malformed / relative query-string link (e.g. a filter
                # chip like "?category=other-news") rather than a real
                # article URL — skip this card instead of letting it
                # collapse into a duplicate of the source's own homepage.
                continue

            # Date
            date_el = container.select_one(source.date_selector)
            date_text = ""
            if date_el:
                date_text = date_el.get("datetime", "") or date_el.get_text(strip=True)
            published_at = parse_date(date_text) if date_text else datetime.now(timezone.utc)

            # ANZSCO codes in title + summary
            combined_text = f"{title} {summary}"
            occupations = extract_anzsco_codes(combined_text)

            if href in seen_urls:
                continue  # duplicate card (e.g. responsive mobile/desktop markup)
            seen_urls.add(href)

            article = NewsArticle(
                title=title,
                summary=summary[:500],  # cap summary length
                url=href,
                state=source.state_code,
                source=source.name,
                published_at=published_at,
                occupations=occupations,
            )
            articles.append(article)
            if len(articles) >= 10:  # limit to 10 most recent per source
                break

        except Exception as e:
            logger.warning(f"Error parsing article from {source.name}: {e}")
            continue

    logger.info(f"  Found {len(articles)} articles from {source.name}")
    return articles


# ---------------------------------------------------------------------------
# Firestore writer
# ---------------------------------------------------------------------------

def write_to_firestore(
    db: firestore.Client,
    articles: list[NewsArticle],
) -> tuple[list[NewsArticle], int]:
    """
    Write articles to Firestore 'news' collection.
    Uses doc_id (MD5 of URL) to avoid duplicates.

    Returns: (new_articles, skipped_count)
    """
    collection = db.collection("news")
    new_articles: list[NewsArticle] = []
    skipped = 0

    for article in articles:
        doc_ref = collection.document(article.doc_id)
        existing = doc_ref.get()

        if existing.exists:
            skipped += 1
            continue

        doc_data = {
            "title": article.title,
            "summary": article.summary,
            "url": article.url,
            "state": article.state,
            "source": article.source,
            "publishedAt": article.published_at,
            "occupations": article.occupations,
            "scrapedAt": datetime.now(timezone.utc),
        }

        if DRY_RUN:
            logger.info(f"[DRY RUN] Would write: {article.title[:60]}")
        else:
            doc_ref.set(doc_data)
            logger.info(f"Written: [{article.state}] {article.title[:60]}")

        new_articles.append(article)

    return new_articles, skipped


# ---------------------------------------------------------------------------
# Admin approval queue
# ---------------------------------------------------------------------------

def build_notification_draft(article: NewsArticle) -> tuple[str, dict]:
    """Build a deterministic approval draft for a newly archived article."""
    draft_id = f"scraper-{article.state.lower()}-{article.doc_id}"
    created_at = datetime.now(timezone.utc)
    return draft_id, {
        "id": draft_id,
        "title": article.title[:100],
        "body": article.summary[:500] or "New migration news available",
        "category": "News",
        "source": article.source,
        "sourceUrl": article.url,
        "url": article.url,
        "state": article.state,
        "status": "draft",
        "articleDate": article.published_at,
        "createdAt": created_at.isoformat(),
        "timestamp": created_at.isoformat(),
        "createdBy": "scraper_automation",
        "sourceFingerprint": article.doc_id,
    }


def write_notification_drafts(
    db: firestore.Client,
    articles: list[NewsArticle],
) -> None:
    """Write new articles to the admin queue without publishing or sending FCM."""
    drafts = db.collection("notifications_draft")

    for article in articles:
        draft_id, draft_data = build_notification_draft(article)

        if DRY_RUN:
            logger.info(f"[DRY RUN] Would queue draft: {article.title[:60]}")
        else:
            drafts.document(draft_id).set(draft_data)
            logger.info(f"Queued for admin approval: [{article.state}] {article.title[:60]}")



# ---------------------------------------------------------------------------
# Admin dashboard heartbeat
# ---------------------------------------------------------------------------

def write_scraper_heartbeat(
    db: Optional[firestore.Client],
    *,
    status: str,
    items_found: int = 0,
    items_published: int = 0,
    duplicates_skipped: int = 0,
    error_message: Optional[str] = None,
    summary: Optional[str] = None,
) -> None:
    """
    Update system_health/scraper_status so the admin dashboard's
    ScraperStatusPill reflects the real outcome of this run instead of
    going stale. Best-effort — never let a heartbeat failure fail the run.
    """
    if db is None or DRY_RUN:
        logger.info("[heartbeat] Skipped (no Firestore client or DRY_RUN)")
        return
    try:
        db.collection("system_health").document("scraper_status").set(
            {
                "last_run_at": datetime.now(timezone.utc),
                "status": status,
                "items_found": items_found,
                "items_published": items_published,
                "duplicates_skipped": duplicates_skipped,
                "sources_checked": [source.name for source in SOURCES],
                "error_message": error_message,
                "summary": summary
                or f"{items_published} new, {duplicates_skipped} duplicates skipped",
            },
            merge=True,
        )
        logger.info("[heartbeat] system_health/scraper_status updated")
    except Exception as e:  # noqa: BLE001 - best-effort, never fatal
        logger.warning(f"[heartbeat] Failed to update scraper_status: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    logger.info("=== MigrationAU News Scraper ===")
    if DRY_RUN:
        logger.info("DRY RUN mode — no Firestore writes will occur")

    # Build Firestore client
    try:
        db = build_firestore_client()
        logger.info("Firestore client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Firestore: {e}")
        write_scraper_heartbeat(
            None, status="error", error_message=f"Firestore init failed: {e}"
        )
        return 1

    # Scrape all sources
    all_articles: list[NewsArticle] = []
    for source in SOURCES:
        articles = scrape_source(source)
        all_articles.extend(articles)

    logger.info(f"Total articles scraped: {len(all_articles)}")

    if not all_articles:
        logger.warning("No articles found. Exiting.")
        write_scraper_heartbeat(
            db, status="ok", items_found=0, summary="No articles found this run"
        )
        return 0

    # Write to Firestore — returns only the newly written articles
    written, skipped = write_to_firestore(db, all_articles)
    logger.info(f"Firestore: {len(written)} written, {skipped} skipped (already exist)")

    # Newly archived articles wait for explicit admin approval before FCM delivery.
    write_notification_drafts(db, written)

    write_scraper_heartbeat(
        db,
        status="ok",
        items_found=len(all_articles),
        items_published=len(written),
        duplicates_skipped=skipped,
    )

    logger.info("=== Scraper complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
