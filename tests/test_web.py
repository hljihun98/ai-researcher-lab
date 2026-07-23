"""웹 서버 스모크 테스트 (데모 모드).

로컬에 Python이 없어 개발 중 수동 실행이 안 되므로, CI가 이 테스트로
server.py의 import·라우팅·데모 세션 흐름을 검증한다.
"""
import os
import unittest


class WebSmokeTests(unittest.TestCase):
    def setUp(self):
        os.environ["AI_RESEARCHER_DEMO_MODE"] = "1"
        os.environ.pop("ANTHROPIC_API_KEY", None)
        from server import app

        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_healthz(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ok")

    def test_index_serves_html(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"AI Researcher Lab", resp.data)
        html = resp.get_data(as_text=True)
        self.assertIn("initRandomExamples", html)
        self.assertIn("EXAMPLE_QUESTIONS", html)
        self.assertNotIn("소규모 스타트업에 가장 적합한 RAG 아키텍처", html)

    def test_meta_reports_demo(self):
        resp = self.client.get("/api/meta")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["demo_mode"])
        self.assertIn("lite_mode", body)
        self.assertEqual(body["orchestration_version"], "group-meeting-v1")
        self.assertEqual(body["session_budget_seconds"], 60)
        self.assertIn("researcher", body["agents"])

    def test_empty_question_rejected(self):
        resp = self.client.post("/api/run", json={"question": "  "})
        self.assertEqual(resp.status_code, 400)

    def test_run_produces_answer_and_history(self):
        resp = self.client.post(
            "/api/run", json={"question": "소규모 스타트업에 적합한 RAG 아키텍처는?"}
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["final_answer"].strip())
        self.assertGreater(len(body["history"]), 0)
        for u in body["history"]:
            self.assertTrue(u["message"].strip(), f"빈 발언: {u}")


if __name__ == "__main__":
    unittest.main()
