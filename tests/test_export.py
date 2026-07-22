"""세션 ID 응답과 마크다운 내보내기 API 검증."""
import os
import unittest
from unittest.mock import patch


class SessionExportTests(unittest.TestCase):
    def setUp(self):
        self._previous_demo = os.environ.get("AI_RESEARCHER_DEMO_MODE")
        os.environ["AI_RESEARCHER_DEMO_MODE"] = "1"

        import config
        import server

        self.config = config
        self.server = server
        self._lite_mode = patch.object(config, "LITE_MODE", True)
        self._lite_mode.start()
        self.server.app.config.update(TESTING=True)
        self.client = self.server.app.test_client()
        with self.server._session_store_lock:
            self.server._session_store.clear()

    def tearDown(self):
        with self.server._session_store_lock:
            self.server._session_store.clear()
        self._lite_mode.stop()
        if self._previous_demo is None:
            os.environ.pop("AI_RESEARCHER_DEMO_MODE", None)
        else:
            os.environ["AI_RESEARCHER_DEMO_MODE"] = self._previous_demo

    def test_run_returns_id_and_export_downloads_markdown(self):
        question = "내보내기 기능을 검증하는 질문"
        run_response = self.client.post("/api/run", json={"question": question})
        self.assertEqual(run_response.status_code, 200)
        result = run_response.get_json()
        self.assertTrue(result["id"])

        export_response = self.client.get(
            f"/api/session/{result['id']}/export"
        )
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(
            export_response.headers["Content-Type"],
            "text/markdown; charset=utf-8",
        )
        self.assertEqual(
            export_response.headers["Content-Disposition"],
            f'attachment; filename="research_{result["id"]}.md"',
        )

        markdown = export_response.get_data(as_text=True)
        self.assertIn(question, markdown)
        self.assertIn(result["final_answer"], markdown)
        self.assertIn("## 대화", markdown)
        self.assertIn("## 최종 답변", markdown)
        self.assertIn("### 라운드 1", markdown)
        self.assertIn("### 라운드 2", markdown)
        self.assertIn("**리서처**", markdown)
        self.assertIn(self.config.LOCATIONS["whiteboard"], markdown)

    def test_missing_session_export_returns_404(self):
        response = self.client.get("/api/session/not-found/export")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
