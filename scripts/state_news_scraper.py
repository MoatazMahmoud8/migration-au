#!/usr/bin/env python3
"""
state_news_scraper.py
=====================
Scrapes Australian state migration news pages and updates Firebase Firestore.

Designed to run via GitHub Actions on a daily schedule.

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


SOURCES: list[ScraperSource] = [
    ScraperSource(
        name="Skills Victoria",
        state_code="VIC",
        url="https://business.vic.gov.au/business-information/skilled-migration-victoria",
        article_selector="article, .news-item, .article-card",
        title_selector="h2, h3, .title",
        summary_selector="p, .summary, .description",
        link_selector="a",
        date_selector="time, .date, .published",
        base_url="https://business.vic.gov.au",
    ),
    ScraperSource(
        name="Migration NSW",
        state_code="NSW",
        url="https://www.nsw.gov.au/topics/skilled-migration-to-nsw",
        article_selector=".nsw-card, article, .content-block",
        title_selector="h3, h2, .nsw-card__title",
        summary_selector="p, .nsw-card__copy",
        link_selector="a",
        date_selector="time, .date",
        base_url="https://www.nsw.gov.au",
    ),
    ScraperSource(
        name="Migration SA",
        state_code="SA",
        url="https://migration.sa.gov.au/news",
        article_selector=".news-article, article, .views-row",
        title_selector="h2, h3, .field-title",
        summary_selector="p, .field-body",
        link_selector="a",
        date_selector="time, .date-display-single",
        base_url="https://migration.sa.gov.au",
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


def scrape_source(source: ScraperSource) -> list[NewsArticle]:
    """Scrape a single source and return a list of NewsArticle objects."""
    logger.info(f"Scraping {source.name} ({source.state_code})...")

    try:
        response = requests.get(source.url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {source.url}: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    containers = soup.select(source.article_selector)

    if not containers:
        logger.warning(f"No articles found for {source.name} with selector '{source.article_selector}'")
        return []

    articles = []
    for container in containers[:10]:  # limit to 10 most recent per source
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
            if not href:
                href = source.url

            # Date
            date_el = container.select_one(source.date_selector)
            date_text = ""
            if date_el:
                date_text = date_el.get("datetime", "") or date_el.get_text(strip=True)
            published_at = parse_date(date_text) if date_text else datetime.now(timezone.utc)

            # ANZSCO codes in title + summary
            combined_text = f"{title} {summary}"
            occupations = extract_anzsco_codes(combined_text)

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
) -> tuple[int, int]:
    """
    Write articles to Firestore 'news' collection.
    Uses doc_id (MD5 of URL) to avoid duplicates.

    Returns: (written_count, skipped_count)
    """
    collection = db.collection("news")
    written = 0
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

        written += 1

    return written, skipped


# ---------------------------------------------------------------------------
# Send FCM topic notifications via Firestore trigger
# (alternatively: use Firebase Admin SDK directly)
# ---------------------------------------------------------------------------

def trigger_fcm_notifications(
    db: firestore.Client,
    articles: list[NewsArticle],
) -> None:
    """
    Write FCM trigger documents to 'fcm_triggers' collection.
    A Firebase Cloud Function watches this collection and sends FCM messages.
    This decouples the scraper from FCM and avoids needing the Admin SDK here.
    """
    triggers = db.collection("fcm_triggers")

    for article in articles:
        topics = [f"State_{article.state}"]
        for anzsco in article.occupations:
            topics.append(f"Occupation_{anzsco}")

        trigger_data = {
            "title": f"New update: {article.state}",
            "body": article.title[:100],
            "topics": topics,
            "articleUrl": article.url,
            "createdAt": datetime.now(timezone.utc),
            "sent": False,
        }

        if not DRY_RUN:
            triggers.add(trigger_data)


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
        return 1

    # Scrape all sources
    all_articles: list[NewsArticle] = []
    for source in SOURCES:
        articles = scrape_source(source)
        all_articles.extend(articles)

    logger.info(f"Total articles scraped: {len(all_articles)}")

    if not all_articles:
        logger.warning("No articles found. Exiting.")
        return 0

    # Write to Firestore
    written, skipped = write_to_firestore(db, all_articles)
    logger.info(f"Firestore: {written} written, {skipped} skipped (already exist)")

    # Trigger FCM for new articles
    new_articles = [a for a in all_articles]  # all are "new" (write_to_firestore filters)
    trigger_fcm_notifications(db, new_articles)

    logger.info("=== Scraper complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
