import unittest

from money_radar.reddit import parse_rss_entries


class RedditRssTests(unittest.TestCase):
    def test_parses_atom_published_time(self):
        xml = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Looking for software for client reporting</title>
            <link href="https://www.reddit.com/r/SaaS/comments/abc/example/" />
            <published>2026-07-12T10:30:00+00:00</published>
            <content type="html">It&amp;#39;s manual. submitted by /u/tester [link] [comments]</content>
            <author><name>/u/tester</name></author>
          </entry>
        </feed>"""
        posts = parse_rss_entries(xml)
        self.assertEqual(len(posts), 1)
        self.assertGreater(posts[0]["created_utc"], 0)
        self.assertEqual(posts[0]["subreddit"], "SaaS")
        self.assertEqual(posts[0]["selftext"], "It's manual.")


if __name__ == "__main__":
    unittest.main()
