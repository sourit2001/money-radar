import unittest

from money_radar.annotator import annotate_post


class AnnotatorTests(unittest.TestCase):
    def test_annotation_has_medium_fields(self):
        post = {
            "title": "Is there a way to automate weekly client reports?",
            "selftext": "This is manual and takes too long.",
            "score": 120,
            "num_comments": 24,
        }
        annotation = annotate_post(post)
        self.assertEqual(annotation["opportunity_type"], "automation")
        self.assertIn(annotation["signal"], {"opportunity", "pain"})
        self.assertGreaterEqual(annotation["value_score"], 1)
        self.assertLessEqual(annotation["value_score"], 5)
        self.assertTrue(annotation["pain_summary"])


if __name__ == "__main__":
    unittest.main()

