import tempfile
import unittest
from pathlib import Path

from money_radar.obsidian import export_obsidian_markdown, render_obsidian_markdown
from money_radar.storage import connect, init_db, upsert_post


class ObsidianExportTests(unittest.TestCase):
    def test_render_obsidian_markdown_includes_ranked_posts(self):
        markdown = render_obsidian_markdown(
            [
                {
                    "title": "Looking for invoice software",
                    "value_score": 5,
                    "subreddit": "smallbusiness",
                    "channel": "business",
                    "created_utc": 1783382400,
                    "signal": "tool_search",
                    "opportunity_type": "saas",
                    "permalink": "https://reddit.com/example",
                    "pain_summary": "Manual invoicing takes too long.",
                    "selftext": "I need something better than spreadsheets.",
                }
            ],
            total_saved=3,
            min_score=4,
        )

        self.assertIn("# Money Radar Latest", markdown)
        self.assertIn("## 1. Looking for invoice software", markdown)
        self.assertIn("- Score: 5/5", markdown)
        self.assertIn("Manual invoicing takes too long.", markdown)

    def test_export_obsidian_markdown_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "money.sqlite3"
            target_dir = Path(tmp) / "vault"
            conn = connect(db_path)
            init_db(conn)
            upsert_post(
                conn,
                {
                    "reddit_id": "abc",
                    "subreddit": "excel",
                    "channel": "productivity",
                    "title": "Need an app to clean CSV files",
                    "selftext": "This recurring cleanup is painful.",
                    "permalink": "https://reddit.com/r/excel/comments/abc",
                    "url": "https://reddit.com/r/excel/comments/abc",
                    "author": "user",
                    "score": 0,
                    "num_comments": 0,
                    "created_utc": 1783382400,
                    "fetched_at": "2026-07-13T00:00:00+00:00",
                    "signal": "tool_search",
                    "signal_phrase": "Need an app",
                    "pain_summary": "Recurring CSV cleanup.",
                    "opportunity_type": "automation",
                    "value_score": 4,
                    "raw_json": {},
                },
            )
            conn.close()

            output_path = export_obsidian_markdown(db_path, target_dir)

            self.assertEqual(output_path, target_dir / "Money Radar Latest.md")
            self.assertIn("Need an app to clean CSV files", output_path.read_text())


if __name__ == "__main__":
    unittest.main()
