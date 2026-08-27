import json
import tempfile
import unittest

from money_radar.semantic_analysis import add_deepseek_analyses, add_market_product_analyses
from money_radar.storage import connect, init_db


class SemanticAnalysisTests(unittest.TestCase):
    def test_attaches_only_model_selected_sentence_analyses_and_caches_them(self):
        calls = []

        def caller(api_key, model, prompt):
            calls.append((api_key, model, prompt))
            return json.dumps({
                "annotations": [{"sentence_id": 2}],
                "brief": {"scenario": "视频字幕制作。", "current_workflow": "手动调整时间轴。", "pain": "时间轴调整耗时。", "friction": "原帖未说明。", "user_wants": "可编辑初稿。", "mvp": "生成可编辑时间轴。", "evidence_boundary": "单条用户证据。"},
            })

        posts = [{"title": "Subtitle workflow", "selftext": "I make videos. Manual timing takes too long."}]
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(f"{tmp}/radar.sqlite3")
            init_db(conn)
            self.assertTrue(add_deepseek_analyses(conn, posts, api_key="test", caller=caller))
            self.assertEqual(posts[0]["semantic_annotations"], {
                "Manual timing takes too long.": "selected"
            })
            self.assertEqual(posts[0]["semantic_brief"]["pain"], "时间轴调整耗时。")
            again = [{"title": "Subtitle workflow", "selftext": "I make videos. Manual timing takes too long."}]
            add_deepseek_analyses(conn, again, api_key="test", caller=caller)
            self.assertEqual(len(calls), 1)

    def test_missing_api_key_keeps_report_without_fake_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(f"{tmp}/radar.sqlite3")
            init_db(conn)
            self.assertFalse(add_deepseek_analyses(conn, [{"selftext": "A sentence."}], api_key=""))

    def test_market_product_analysis_stays_structured(self):
        products = [{"id": "p1", "name": "Example", "description": "Automates invoice matching."}]
        response = {"analyses": [{
            "id": "p1", "problem": "自动匹配发票。", "target_user": "财务人员。",
            "coverage": "已经提供自动匹配。", "solo_gap": "研究异常复核。",
            "evidence_limit": "简介没有用户评论。",
        }]}
        self.assertTrue(add_market_product_analyses(
            products, api_key="test", caller=lambda *_: json.dumps(response, ensure_ascii=False)
        ))
        self.assertEqual(products[0]["analysis"]["problem"], "自动匹配发票。")
