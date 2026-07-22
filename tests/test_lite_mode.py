"""무료 등급용 라이트 실행 파이프라인 검증."""
import importlib
import os
import unittest
from unittest.mock import patch


class LiteModeTests(unittest.TestCase):
    def setUp(self):
        self._previous_demo = os.environ.get("AI_RESEARCHER_DEMO_MODE")
        self._previous_lite = os.environ.get("AI_RESEARCHER_LITE")
        os.environ["AI_RESEARCHER_DEMO_MODE"] = "1"
        os.environ["AI_RESEARCHER_LITE"] = "1"

        import config
        import server

        importlib.reload(config)
        self.config = config
        self.server = server

    def tearDown(self):
        if self._previous_demo is None:
            os.environ.pop("AI_RESEARCHER_DEMO_MODE", None)
        else:
            os.environ["AI_RESEARCHER_DEMO_MODE"] = self._previous_demo
        if self._previous_lite is None:
            os.environ.pop("AI_RESEARCHER_LITE", None)
        else:
            os.environ["AI_RESEARCHER_LITE"] = self._previous_lite
        importlib.reload(self.config)

    def _run_session(self):
        from main import DemoClient

        client = DemoClient()
        with patch.object(self.server, "build_runtime_client", return_value=client):
            state = self.server.run_session_web("소규모 RAG 구성을 추천해줘")
        return state, client

    def test_lite_mode_limits_llm_calls_to_five(self):
        self.assertTrue(self.config.LITE_MODE)
        state, client = self._run_session()

        self.assertEqual(len(client.calls), 5)
        self.assertEqual(len(state.history), 4)
        self.assertTrue(state.final_answer and state.final_answer.strip())

    def test_history_and_orchestrator_schema_are_preserved(self):
        state, _ = self._run_session()

        self.assertEqual(len(state.orchestrator_log), 2)
        for round_index, log in enumerate(state.orchestrator_log):
            for field in (
                "action",
                "agents",
                "location",
                "confidence_after",
                "confidence_reason",
            ):
                self.assertIn(field, log)
            self.assertEqual(log["action"], "encounter")

            first, second = state.history[round_index * 2 : round_index * 2 + 2]
            self.assertIsNone(first.responds_to)
            self.assertEqual(second.responds_to, first.agent)
            self.assertEqual(first.location, log["location"])
            self.assertEqual(second.location, log["location"])

    def test_api_response_schema_is_preserved(self):
        from main import DemoClient

        client = DemoClient()
        self.server.app.config.update(TESTING=True)
        with patch.object(self.server, "build_runtime_client", return_value=client):
            response = self.server.app.test_client().post(
                "/api/run", json={"question": "소규모 RAG 구성을 추천해줘"}
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(
            set(body),
            {
                "question",
                "confidence_score",
                "confidence_threshold",
                "final_answer",
                "history",
                "orchestrator_log",
            },
        )
        self.assertLessEqual(len(client.calls), 5)
        self.assertTrue(body["final_answer"].strip())
        for utterance in body["history"]:
            self.assertEqual(
                set(utterance),
                {
                    "agent",
                    "message",
                    "confidence",
                    "location",
                    "turn",
                    "responds_to",
                },
            )


if __name__ == "__main__":
    unittest.main()
