"""지난 연구 세션 저장·목록·조회 API 검증."""
import os
import unittest
from unittest.mock import patch


class SessionHistoryTests(unittest.TestCase):
    def setUp(self):
        self._previous_demo = os.environ.get("AI_RESEARCHER_DEMO_MODE")
        os.environ["AI_RESEARCHER_DEMO_MODE"] = "1"

        import config
        import server

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

    def _run_two_sessions(self):
        first = self.client.post("/api/run", json={"question": "첫 번째 연구 질문"})
        second = self.client.post("/api/run", json={"question": "두 번째 연구 질문"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        return first.get_json(), second.get_json()

    def test_sessions_are_listed_newest_first(self):
        self._run_two_sessions()

        response = self.client.get("/api/sessions")
        self.assertEqual(response.status_code, 200)
        sessions = response.get_json()["sessions"]
        self.assertEqual(len(sessions), 2)
        self.assertEqual(
            [item["question"] for item in sessions],
            ["두 번째 연구 질문", "첫 번째 연구 질문"],
        )
        for item in sessions:
            self.assertEqual(
                set(item), {"id", "question", "confidence_score", "ts"}
            )
            self.assertIsInstance(item["ts"], int)

    def test_session_detail_has_complete_run_schema(self):
        first_result, _ = self._run_two_sessions()
        sessions = self.client.get("/api/sessions").get_json()["sessions"]
        first_id = sessions[1]["id"]

        response = self.client.get(f"/api/session/{first_id}")
        self.assertEqual(response.status_code, 200)
        detail = response.get_json()
        self.assertEqual(detail, first_result)
        self.assertEqual(
            set(detail),
            {
                "id",
                "question",
                "confidence_score",
                "confidence_threshold",
                "final_answer",
                "history",
                "orchestrator_log",
                "status",
                "has_errors",
            },
        )
        self.assertTrue(detail["history"])
        self.assertTrue(detail["final_answer"].strip())

    def test_missing_session_returns_404(self):
        response = self.client.get("/api/session/not-found")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
