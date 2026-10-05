import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "state_news_scraper.py"
SPEC = importlib.util.spec_from_file_location("state_news_scraper", SCRIPT_PATH)
state_news_scraper = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = state_news_scraper
SPEC.loader.exec_module(state_news_scraper)


class StateNewsApprovalTests(unittest.TestCase):
    def test_article_becomes_deterministic_draft(self):
        article = state_news_scraper.NewsArticle(
            title="A" * 120,
            summary="B" * 520,
            url="https://example.test/visa-update",
            state="VIC",
            source="Skills Victoria",
            published_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        )

        draft_id, draft = state_news_scraper.build_notification_draft(article)

        self.assertEqual(draft_id, f"scraper-vic-{article.doc_id}")
        self.assertEqual(draft["status"], "draft")
        self.assertEqual(draft["createdBy"], "scraper_automation")
        self.assertEqual(draft["sourceUrl"], article.url)
        self.assertEqual(len(draft["title"]), 100)
        self.assertEqual(len(draft["body"]), 500)
        self.assertNotIn("topics", draft)
        self.assertNotIn("sent", draft)


if __name__ == "__main__":
    unittest.main()