import tempfile
import unittest
from pathlib import Path

from money_radar.storage import connect, init_db, list_posts, metadata, upsert_post


def sample_post(reddit_id="abc", value_score=3, comments=8):
    return {
        "reddit_id": reddit_id,
        "subreddit": "SaaS",
        "channel": "entrepreneurship",
        "title": "Looking for a tool to track churn",
        "selftext": "Manual tracking is annoying.",
        "permalink": "https://reddit.com/r/SaaS/comments/abc/example",
        "url": "https://reddit.com/r/SaaS/comments/abc/example",
        "author": "someone",
        "score": 42,
        "num_comments": comments,
        "created_utc": 1710000000,
        "fetched_at": "2026-07-07T00:00:00Z",
        "signal": "tool_search",
        "signal_phrase": "looking for",
        "pain_summary": "Manual tracking is annoying.",
        "opportunity_type": "SaaS",
        "value_score": value_score,
        "raw_json": {},
    }


class StorageTests(unittest.TestCase):
    def test_upsert_and_list_posts(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(Path(tmp) / "radar.sqlite3")
            init_db(conn)
            upsert_post(conn, sample_post("abc", value_score=2, comments=5))
            upsert_post(conn, sample_post("abc", value_score=5, comments=40))
            posts = list_posts(conn)
            self.assertEqual(len(posts), 1)
            self.assertEqual(posts[0]["value_score"], 5)
            self.assertEqual(posts[0]["num_comments"], 40)
            self.assertEqual(metadata(conn)["total"], 1)

    def test_query_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(Path(tmp) / "radar.sqlite3")
            init_db(conn)
            upsert_post(conn, sample_post("abc", value_score=5))
            upsert_post(
                conn,
                {
                    **sample_post("def", value_score=1),
                    "subreddit": "excel",
                    "channel": "productivity",
                    "title": "Need help cleaning spreadsheet rows",
                    "selftext": "Excel formulas are confusing.",
                    "pain_summary": "Excel formulas are confusing.",
                },
            )
            self.assertEqual(len(list_posts(conn, channel="productivity")), 1)
            self.assertEqual(len(list_posts(conn, min_value_score=4)), 1)
            self.assertEqual(len(list_posts(conn, search="churn")), 1)


if __name__ == "__main__":
    unittest.main()
