import unittest

from money_radar.filters import assess_opportunity, detect_signal, is_candidate_post, passes_engagement


class FilterTests(unittest.TestCase):
    def test_detects_tool_search_signal(self):
        post = {"title": "Looking for an app for invoice followups", "selftext": ""}
        match = detect_signal(post)
        self.assertIsNotNone(match)
        self.assertEqual(match.signal, "tool_search")

    def test_requires_engagement(self):
        self.assertFalse(passes_engagement({"score": 2, "num_comments": 1}))
        self.assertTrue(passes_engagement({"score": 11, "num_comments": 1}))
        self.assertTrue(passes_engagement({"score": 1, "num_comments": 5}))

    def test_candidate_rejects_stickied_posts(self):
        post = {
            "title": "Need help with budgeting",
            "score": 99,
            "num_comments": 30,
            "stickied": True,
        }
        self.assertFalse(is_candidate_post(post))

    def test_rejects_generic_help_without_product_opportunity(self):
        post = {
            "title": "I need help finding my target audience",
            "selftext": "Who should I talk to about my startup?",
            "score": 0,
            "num_comments": 0,
        }
        self.assertFalse(is_candidate_post(post))

    def test_accepts_concrete_recurring_workflow_pain(self):
        post = {
            "title": "Need help cleaning supplier spreadsheet every month",
            "selftext": "The manual cleanup is annoying and wastes time.",
            "score": 0,
            "num_comments": 0,
        }
        assessment = assess_opportunity(post)
        self.assertTrue(assessment.eligible)
        self.assertTrue(is_candidate_post(post))

    def test_rejects_promotional_launch_post(self):
        post = {
            "title": "I built a dashboard and launched it on Product Hunt",
            "selftext": "It helps teams automate client reports.",
            "score": 0,
            "num_comments": 0,
        }
        self.assertFalse(is_candidate_post(post))

    def test_accepts_explicit_app_search_with_financial_context(self):
        post = {
            "title": "Looking for an app for irregular income budgeting",
            "selftext": "Freelance income makes planning frustrating.",
            "score": 0,
            "num_comments": 0,
        }
        self.assertTrue(is_candidate_post(post))

    def test_rejects_product_launch_described_as_tool_for(self):
        post = {
            "title": "Yerd v2 - Local PHP development tool for MacOS and Linux",
            "selftext": "I shipped a lightweight tool after getting frustrated with subscriptions.",
            "score": 0,
            "num_comments": 0,
        }
        self.assertFalse(is_candidate_post(post))

    def test_rejects_generic_automation_advice_question(self):
        post = {
            "title": "The next step?",
            "selftext": "I enjoyed automation courses. How can I improve my business skills?",
            "score": 0,
            "num_comments": 0,
        }
        self.assertFalse(is_candidate_post(post))

    def test_rejects_broad_automation_discussion(self):
        post = {
            "title": "What finance tasks are safe to automate with AI?",
            "selftext": "Where do you draw the line for business workflows?",
            "score": 0,
            "num_comments": 0,
        }
        self.assertFalse(is_candidate_post(post))

    def test_accepts_latent_recurring_workflow_pain(self):
        post = {
            "title": "Monthly supplier reconciliation is painfully manual",
            "selftext": "Our team copies invoice data into a spreadsheet every month.",
            "score": 0,
            "num_comments": 0,
        }
        assessment = assess_opportunity(post)
        self.assertTrue(assessment.eligible)
        self.assertIn("latent demand: concrete workflow pain", assessment.reasons)

    def test_rejects_supply_post_even_when_it_mentions_pain(self):
        post = {
            "title": "A workflow tool I built for monthly client reports",
            "selftext": "My app removes frustrating manual reporting for agencies.",
            "score": 0,
            "num_comments": 0,
        }
        self.assertFalse(is_candidate_post(post))

    def test_accepts_failed_software_workaround_request(self):
        post = {
            "title": "Complex PDF table into Excel",
            "selftext": (
                "I've tried several OCR programs but none of them recognize the tables. "
                "Does anyone know a good workflow or software for this?"
            ),
            "score": 0,
            "num_comments": 0,
        }
        self.assertTrue(is_candidate_post(post))

    def test_rejects_disclosed_product_promotion_late_in_body(self):
        post = {
            "title": "I need a better way to find my saved prompts",
            "selftext": (
                "My prompts are scattered across files and the workflow is annoying. "
                + "Background details. " * 40
                + "Disclosure: I'm the developer of the Chrome extension linked below."
            ),
            "score": 0,
            "num_comments": 0,
        }
        self.assertFalse(is_candidate_post(post))

    def test_labels_direct_and_latent_demand(self):
        direct = assess_opportunity({
            "title": "Looking for software for client invoices",
            "selftext": "Our team does this manually.",
        })
        latent = assess_opportunity({
            "title": "Monthly invoice reconciliation is painfully manual",
            "selftext": "Our team copies data into a spreadsheet every month.",
        })
        self.assertEqual(direct.tier, "direct")
        self.assertEqual(latent.tier, "latent")


if __name__ == "__main__":
    unittest.main()
