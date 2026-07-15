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
        self.assertIn("- Score / 评分: 5/5", markdown)
        self.assertIn("Manual invoicing takes too long.", markdown)

    def test_render_obsidian_markdown_includes_chinese_translation(self):
        markdown = render_obsidian_markdown(
            [{
                "title": "Need a billing tool",
                "title_zh": "需要一个账单工具",
                "value_score": 5,
                "pain_summary": "Billing takes too long.",
                "pain_summary_zh": "账单处理耗时太长。",
                "selftext": "I do this manually every week.",
                "selftext_zh": "我每周都要手工完成。",
            }],
            total_saved=1,
            min_score=4,
        )
        self.assertIn("**中文标题**：需要一个账单工具", markdown)
        self.assertIn("**痛点（中文）**：账单处理耗时太长。", markdown)
        self.assertIn("**中文翻译**", markdown)

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

    def test_posts_are_not_repeated_in_later_daily_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "money.sqlite3"
            target_dir = Path(tmp) / "vault"
            conn = connect(db_path)
            init_db(conn)
            upsert_post(conn, {
                "reddit_id": "once-only",
                "subreddit": "SaaS",
                "channel": "business",
                "title": "Need a billing tool",
                "selftext": "Manual billing is painful.",
                "permalink": "https://reddit.com/r/SaaS/comments/once-only/example",
                "url": "https://reddit.com/r/SaaS/comments/once-only/example",
                "author": "user",
                "created_utc": 1783382400,
                "fetched_at": "2026-07-13T00:00:00+00:00",
                "value_score": 5,
            })
            conn.close()

            first = export_obsidian_markdown(
                db_path, target_dir, filename="Money Radar 2026-07-14.md"
            )
            rerun = export_obsidian_markdown(
                db_path, target_dir, filename="Money Radar 2026-07-14.md"
            )
            next_day = export_obsidian_markdown(
                db_path, target_dir, filename="Money Radar 2026-07-15.md"
            )

            self.assertIn("Need a billing tool", first.read_text())
            self.assertIn("Need a billing tool", rerun.read_text())
            self.assertNotIn("Need a billing tool", next_day.read_text())

    def test_existing_reports_bootstrap_delivery_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "money.sqlite3"
            target_dir = Path(tmp) / "vault"
            target_dir.mkdir()
            conn = connect(db_path)
            init_db(conn)
            upsert_post(conn, {
                "reddit_id": "historical",
                "subreddit": "excel",
                "channel": "productivity",
                "title": "Previously delivered post",
                "permalink": "https://reddit.com/r/excel/comments/historical/example",
                "url": "https://reddit.com/r/excel/comments/historical/example",
                "created_utc": 1783382400,
                "fetched_at": "2026-07-13T00:00:00+00:00",
                "value_score": 5,
            })
            conn.close()
            (target_dir / "Money Radar 2026-07-14.md").write_text(
                "- Reddit: https://reddit.com/r/excel/comments/historical/example\n",
                encoding="utf-8",
            )

            current = export_obsidian_markdown(
                db_path, target_dir, filename="Money Radar 2026-07-15.md"
            )

            self.assertNotIn("Previously delivered post", current.read_text())


if __name__ == "__main__":
    unittest.main()
