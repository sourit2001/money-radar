import unittest

from money_radar.opportunities import build_opportunities


def post(title, body, subreddit="Automation", signal="pain"):
    return {
        "title": title,
        "selftext": body,
        "subreddit": subreddit,
        "channel": "ai_saas_automation",
        "signal": signal,
        "value_score": 4,
        "num_comments": 10,
        "score": 20,
        "permalink": "https://reddit.com/example",
    }


class OpportunityTests(unittest.TestCase):
    def test_groups_similar_posts_and_exposes_evidence(self):
        opportunities = build_opportunities([
            post("How do I automate weekly client reports?", "I use spreadsheets and copying takes too long."),
            post("Looking for software for client reporting", "I tried several tools but none of them work for my agency dashboards.", "SaaS"),
        ])
        self.assertEqual(opportunities[0]["title"], "Client Reporting Tools")
        self.assertEqual(opportunities[0]["post_count"], 2)
        self.assertGreaterEqual(opportunities[0]["failed_solution_count"], 1)
        self.assertIn("spreadsheet", opportunities[0]["current_workaround"])

    def test_single_post_is_marked_as_signal_not_proof(self):
        opportunities = build_opportunities([
            post("Looking for a tool for monthly inventory", "Manual tracking is frustrating.", "smallbusiness")
        ])
        self.assertEqual(opportunities[0]["evidence_level"], "signal")
        self.assertTrue(opportunities[0]["title"].startswith("Early signal:"))

    def test_groups_video_subtitle_workflows(self):
        opportunities = build_opportunities([
            post("Looking for software for video subtitles", "Manual timing is frustrating.", "VideoEditors"),
            post("Looking for software for video dubbing", "I tried several transcription tools but need editable subtitles.", "TextToSpeech"),
        ])
        self.assertEqual(opportunities[0]["title"], "Video Postproduction Tools")
        self.assertEqual(opportunities[0]["post_count"], 2)

    def test_separates_willingness_to_pay_from_a_price_ceiling(self):
        opportunities = build_opportunities([
            post(
                "Looking for a tool for AI brand visibility",
                "I manually run prompts every morning. No huge dashboard and no $200 monthly plan.",
            ),
            post(
                "Looking for a tool for AI brand tracking",
                "I would pay for a simple option because manual prompts take too long.",
                "SaaS",
            ),
        ])
        item = opportunities[0]
        self.assertEqual(item["paid_signal_count"], 1)
        self.assertEqual(item["price_ceiling_count"], 1)
        self.assertEqual(len(item["source_evidence"]["payment_willingness"]), 1)


if __name__ == "__main__":
    unittest.main()
