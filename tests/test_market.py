import unittest

from money_radar.market import (
    market_validation_for,
    parse_toolify_most_used,
    parse_toolify_markdown,
    parse_toolify_new_markdown,
    parse_toolify_detail,
    parse_product_hunt_feed,
    render_market_preview,
)


SAMPLE_FEED = """<?xml version=\"1.0\"?>
<feed xmlns=\"http://www.w3.org/2005/Atom\">
  <entry>
    <id>tag:www.producthunt.com,2005:Post/42</id>
    <published>2026-08-16T00:00:00-07:00</published>
    <link rel=\"alternate\" href=\"https://www.producthunt.com/products/example\"/>
    <title>Example AI editor</title>
    <content type=\"html\">&lt;p&gt;Editable video workflow&lt;/p&gt;</content>
  </entry>
</feed>"""


class MarketPreviewTests(unittest.TestCase):
    def test_parse_public_product_hunt_feed(self):
        products = parse_product_hunt_feed(SAMPLE_FEED)
        self.assertEqual(products[0]["id"], "42")
        self.assertEqual(products[0]["title"], "Example AI editor")
        self.assertEqual(products[0]["description"], "Editable video workflow")

    def test_preview_keeps_source_and_translation(self):
        markdown = render_market_preview(
            [{
                "id": "42", "title": "Example AI editor",
                "description": "Editable video workflow",
                "url": "https://www.producthunt.com/products/example", "published": "",
            }],
            translator=lambda text: f"中文：{text}",
        )
        self.assertIn("https://www.producthunt.com/products/example", markdown)
        self.assertIn("Editable video workflow", markdown)
        self.assertIn("中文：Editable video workflow", markdown)
        self.assertIn("个人开发切口", markdown)

    def test_market_matching_does_not_treat_lead_as_crm_context(self):
        validation = market_validation_for([
            {"title": "Automation can lead to errors", "selftext": "Manual review is safer."}
        ], [])
        self.assertIsNone(validation["watch"])

    def test_market_matching_requires_a_video_postproduction_job(self):
        validation = market_validation_for([
            {"title": "Can I force this app into full screen?", "selftext": "I use it for video calls."}
        ], [])
        self.assertIsNone(validation["watch"])

    def test_parse_toolify_keeps_public_tool_name_and_link(self):
        tools = parse_toolify_most_used(
            '<a href="/tool/capcut">CapCut</a><a href="/tool/capcut">duplicate</a>'
        )
        self.assertEqual(tools[0]["name"], "CapCut")
        self.assertEqual(tools[0]["url"], "https://www.toolify.ai/tool/capcut")
        self.assertEqual(tools[0]["rank"], 1)

    def test_parse_toolify_reader_markdown_keeps_description_and_rank(self):
        tools = parse_toolify_markdown(
            "[![Image 23: ChatGPT](https://img/x.webp) ChatGPT A free AI assistant.](http://www.toolify.ai/tool/chatgpt-4)",
            list_type="most_used",
        )
        self.assertEqual(tools[0]["name"], "ChatGPT")
        self.assertEqual(tools[0]["description"], "A free AI assistant.")
        self.assertEqual(tools[0]["rank"], 1)

    def test_parse_toolify_reader_markdown_handles_default_image_cards(self):
        tools = parse_toolify_markdown(
            "[![Image 52](https://img/default.webp) CapCut CapCut is an AI video editor.](http://www.toolify.ai/tool/capcut-com)",
            list_type="most_used",
        )
        self.assertEqual(tools[0]["name"], "Capcut")
        self.assertEqual(tools[0]["description"], "CapCut is an AI video editor.")

    def test_parse_toolify_new_cards_and_detail(self):
        tools = parse_toolify_new_markdown(
            "[![Image 3](https://img/default.webp) ![Image 4: Abliteration.ai](https://img/logo.webp)](http://www.toolify.ai/tool/abliteration-ai)\n\n## Featured*"
        )
        detail = parse_toolify_detail(
            "Introduction:\n\nAn API for security teams.\n\nAdded on:\n\nAug 16 2026\n\nMonthly Visitors:\n\n70.7K\n\n5 0 Reviews 0 Saved"
        )
        self.assertEqual(tools[0]["name"], "Abliteration.ai")
        self.assertEqual(detail["description"], "An API for security teams.")
        self.assertEqual(detail["monthly_visitors"], "70.7K")

    def test_parse_toolify_detail_uses_title_description_fallback(self):
        detail = parse_toolify_detail(
            "Title: Example: Turns still images into short videos.\n\nURL Source: http://www.toolify.ai/tool/example\n"
        )
        self.assertEqual(detail["description"], "Turns still images into short videos.")

    def test_toolify_only_counts_when_a_ranked_tool_matches_the_job(self):
        validation = market_validation_for(
            [{"title": "Need captions for video", "selftext": "Video transcription and subtitle editing."}],
            [], toolify_tools=[{"name": "CapCut", "url": "https://www.toolify.ai/tool/capcut"}],
        )
        self.assertEqual(validation["toolify_tools"][0]["name"], "CapCut")

    def test_crm_matching_rejects_generic_sales_automation(self):
        validation = market_validation_for(
            [{"title": "Need CRM follow up software", "selftext": "Sales customer workflow."}],
            [], toolify_tools=[
                {"name": "Polar", "description": "Automates research, operations, sales, and recruiting."},
                {"name": "HubSpot", "description": "Customer platform with sales and CRM software."},
            ],
        )
        self.assertEqual([tool["name"] for tool in validation["toolify_tools"]], ["HubSpot"])


if __name__ == "__main__":
    unittest.main()
