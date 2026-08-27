import tempfile
import unittest
import os
from pathlib import Path

os.environ["MONEY_RADAR_DISABLE_SEMANTIC_ANALYSIS"] = "1"

from money_radar.obsidian import (
    export_obsidian_markdown,
    render_obsidian_markdown,
    render_opportunity_report,
)
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
        self.assertIn("## 1. 需求来源 1", markdown)
        self.assertIn("- Score / 评分: 5/5", markdown)
        self.assertIn("Manual invoicing takes too long.", markdown)

    def test_render_obsidian_markdown_hides_source_text_and_translation(self):
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
        self.assertIn("**Pain / 痛点摘要**：Billing takes too long.", markdown)
        self.assertNotIn("我每周都要手工完成。", markdown)
        self.assertNotIn("中文翻译", markdown)

    def test_opportunity_report_hides_original_and_translation(self):
        original = "I tried spreadsheets, but the manual reconciliation takes too long. " * 40
        translated = "我试过电子表格，但手工核对耗时太长。" * 40
        posts = [
            {
                "reddit_id": reddit_id,
                "subreddit": "Accounting",
                "channel": "business",
                "title": "Looking for invoice reconciliation software",
                "title_zh": "寻找发票核对软件",
                "selftext": original,
                "selftext_zh": translated,
                "sentence_translations": {
                    "I tried spreadsheets, but the manual reconciliation takes too long.": "我试过电子表格，但手工核对耗时太长。",
                },
                "semantic_annotations": {
                    "I tried spreadsheets, but the manual reconciliation takes too long.": "selected",
                },
                "semantic_brief": {"scenario": "小企业核对发票。", "current_workflow": "电子表格手工核对。", "pain": "人工核对耗时。", "friction": "电子表格无法减少重复步骤。", "user_wants": "更快完成核对。", "mvp": "导入账单后标记异常。", "evidence_boundary": "两条相似原帖，仍需更多验证。"},
                "permalink": f"https://reddit.com/r/accounting/comments/{reddit_id}",
                "value_score": 5,
                "signal": "pain",
            }
            for reddit_id in ("source-one", "source-two")
        ]

        markdown = render_opportunity_report(posts, total_saved=2, min_score=4)

        self.assertIn("**场景**：小企业核对发票。", markdown)
        self.assertIn("https://reddit.com/r/accounting/comments/source-one", markdown)
        self.assertIn("**当前做法 / 工具**：电子表格手工核对。", markdown)
        self.assertNotIn("I tried spreadsheets, but the manual reconciliation takes too long.", markdown)
        self.assertNotIn("我试过电子表格，但手工核对耗时太长。", markdown)
        self.assertNotIn("中文翻译", markdown)

    def test_free_daily_report_does_not_promote_a_single_post(self):
        markdown = render_opportunity_report(
            [{
                "reddit_id": "one-video", "subreddit": "videoediting", "channel": "creator",
                "title": "Need subtitle editing software for video",
                "selftext": "I tried several tools but none work; I would pay for a better option.",
                "permalink": "https://reddit.com/r/videoediting/comments/one-video",
                "value_score": 5, "signal": "pain",
            }],
            total_saved=1, min_score=4, market_products=[],
        )
        self.assertIn("今天没有满足", markdown)

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
                    "title": "Looking for software for invoice reconciliation",
                    "selftext": "I tried several tools and would pay for a better solution. Accounting spreadsheet cleanup is painful.",
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
            upsert_post(
                conn,
                {
                    "reddit_id": "def",
                    "subreddit": "Accounting",
                    "channel": "productivity",
                    "title": "Looking for software for invoice reconciliation",
                    "selftext": "I tried several tools and would pay for a better solution. Accounting spreadsheet cleanup is painful.",
                    "permalink": "https://reddit.com/r/Accounting/comments/def",
                    "url": "https://reddit.com/r/Accounting/comments/def",
                    "author": "user",
                    "score": 0,
                    "num_comments": 0,
                    "created_utc": 1783382400,
                    "fetched_at": "2026-07-13T00:00:00+00:00",
                    "value_score": 4,
                    "raw_json": {},
                },
            )
            conn.close()

            output_path = export_obsidian_markdown(db_path, target_dir)

            self.assertEqual(output_path, target_dir / "Money Radar Latest.md")
            self.assertIn("市场机会日报", output_path.read_text())
            self.assertIn("https://reddit.com/r/excel/comments/abc", output_path.read_text())

    def test_opportunity_reports_reuse_source_evidence_in_later_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "money.sqlite3"
            target_dir = Path(tmp) / "vault"
            conn = connect(db_path)
            init_db(conn)
            upsert_post(conn, {
                "reddit_id": "once-only",
                "subreddit": "SaaS",
                "channel": "business",
                "title": "Looking for software for invoice reconciliation",
                "selftext": "I tried several tools and would pay for a better solution. Manual billing is painful.",
                "permalink": "https://reddit.com/r/SaaS/comments/once-only/example",
                "url": "https://reddit.com/r/SaaS/comments/once-only/example",
                "author": "user",
                "created_utc": 1783382400,
                "fetched_at": "2026-07-13T00:00:00+00:00",
                "value_score": 5,
            })
            upsert_post(conn, {
                "reddit_id": "once-two",
                "subreddit": "Accounting",
                "channel": "business",
                "title": "Looking for software for invoice reconciliation",
                "selftext": "I tried several tools and would pay for a better solution. Accounting spreadsheet cleanup is painful.",
                "permalink": "https://reddit.com/r/Accounting/comments/once-two/example",
                "url": "https://reddit.com/r/Accounting/comments/once-two/example",
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

            self.assertIn("https://reddit.com/r/SaaS/comments/once-only/example", first.read_text())
            self.assertIn("https://reddit.com/r/SaaS/comments/once-only/example", rerun.read_text())
            self.assertIn("https://reddit.com/r/SaaS/comments/once-only/example", next_day.read_text())

    def test_existing_raw_reports_do_not_hide_opportunity_evidence(self):
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
                "title": "Looking for software for previously delivered invoices",
                "selftext": "I tried several apps but none work for our manual invoice workflow.",
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

            self.assertIn("previously delivered invoices", current.read_text())


if __name__ == "__main__":
    unittest.main()
