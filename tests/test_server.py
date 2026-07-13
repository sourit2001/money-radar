import json
import tempfile
import unittest
from pathlib import Path

from money_radar.server import make_handler
from money_radar.storage import connect, init_db, upsert_post


class DummyWriter:
    def __init__(self):
        self.content = b""

    def write(self, content):
        self.content += content


class ServerApiTests(unittest.TestCase):
    def test_api_posts_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "radar.sqlite3"
            conn = connect(db_path)
            init_db(conn)
            upsert_post(
                conn,
                {
                    "reddit_id": "abc",
                    "subreddit": "SaaS",
                    "channel": "entrepreneurship",
                    "title": "Looking for software for churn tracking",
                    "selftext": "",
                    "permalink": "https://reddit.com/r/SaaS/comments/abc/example",
                    "url": "https://reddit.com/r/SaaS/comments/abc/example",
                    "author": "someone",
                    "score": 80,
                    "num_comments": 22,
                    "created_utc": 1710000000,
                    "fetched_at": "2026-07-07T00:00:00Z",
                    "signal": "tool_search",
                    "signal_phrase": "looking for",
                    "pain_summary": "Looking for software for churn tracking",
                    "opportunity_type": "SaaS",
                    "value_score": 5,
                    "raw_json": {},
                },
            )
            handler_cls = make_handler(db_path, static_dir=Path(tmp))
            handler = handler_cls.__new__(handler_cls)
            handler.path = "/api/posts?min_score=4"
            handler.wfile = DummyWriter()
            handler.send_response = lambda status: setattr(handler, "status", status)
            handler.send_header = lambda key, value: None
            handler.end_headers = lambda: None
            handler.do_GET()
            payload = json.loads(handler.wfile.content.decode("utf-8"))
            self.assertEqual(handler.status, 200)
            self.assertEqual(len(payload["posts"]), 1)
            self.assertEqual(payload["meta"]["total"], 1)


if __name__ == "__main__":
    unittest.main()

