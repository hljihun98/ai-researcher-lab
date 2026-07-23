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

    def _run_session(self, question="소규모 RAG 구성을 추천해줘"):
        from main import DemoClient

        client = DemoClient()
        with patch.object(self.server, "build_runtime_client", return_value=client):
            state = self.server.run_session_web(question)
        return state, client

    @staticmethod
    def _sequence(state):
        return [
            (tuple(log["agents"]), log["location"])
            for log in state.orchestrator_log
            if log["action"] == "encounter"
        ]

    def test_lite_mode_limits_llm_calls_to_five(self):
        self.assertTrue(self.config.LITE_MODE)
        state, client = self._run_session()

        self.assertEqual(len(client.calls), 5)
        self.assertEqual(len(state.history), 4)
        self.assertTrue(state.final_answer and state.final_answer.strip())

    def test_history_and_orchestrator_schema_are_preserved(self):
        state, _ = self._run_session()

        self.assertEqual(len(state.orchestrator_log), 3)
        for log in state.orchestrator_log:
            for field in (
                "action",
                "agents",
                "location",
                "confidence_after",
                "confidence_reason",
            ):
                self.assertIn(field, log)
            self.assertEqual(log["action"], "encounter")

        rounds = []
        for utterance in state.history:
            if utterance.responds_to is None:
                rounds.append([])
            rounds[-1].append(utterance)

        self.assertEqual([len(group) for group in rounds], [1, 1, 2])
        for log, group in zip(state.orchestrator_log, rounds):
            self.assertIsNone(group[0].responds_to)
            self.assertTrue(all(u.location == log["location"] for u in group))
        self.assertEqual(rounds[-1][1].responds_to, rounds[-1][0].agent)

    def test_group_discussions_lead_to_representative_meeting(self):
        state, _ = self._run_session()
        first, second, meeting = state.orchestrator_log

        self.assertEqual(set(first["agents"]), {"researcher", "expert"})
        self.assertIn(first["location"], {"library", "coffee"})
        self.assertEqual(set(second["agents"]), {"critic", "fact_checker"})
        self.assertIn(second["location"], {"whiteboard", "server_room"})
        self.assertEqual(meeting["location"], "meeting_desk")
        self.assertEqual(len(meeting["agents"]), 2)
        self.assertEqual(len(set(meeting["agents"]) & set(first["agents"])), 1)
        self.assertEqual(len(set(meeting["agents"]) & set(second["agents"])), 1)

    def test_different_questions_get_different_deterministic_sequences(self):
        first_question = "오늘 저녁에 가볍게 즐길 취미를 추천해줘"
        second_question = "HTTP/3와 HTTP/2의 차이를 비교해줘"

        first_state, _ = self._run_session(first_question)
        repeated_state, _ = self._run_session(first_question)
        second_state, _ = self._run_session(second_question)

        self.assertEqual(self._sequence(first_state), self._sequence(repeated_state))
        self.assertNotEqual(self._sequence(first_state), self._sequence(second_state))

    def test_locations_and_round_boundaries_are_valid(self):
        state, _ = self._run_session("원격 팀의 회의 시간을 줄이는 방법은?")
        self.assertTrue(state.history)
        for utterance in state.history:
            self.assertIn(utterance.location, self.config.LOCATIONS)

        round_starts = [u for u in state.history if u.responds_to is None]
        self.assertEqual(len(round_starts), 3)

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
        self.assertTrue(body["id"])
        self.assertEqual(body["status"], "ok")
        self.assertFalse(body["has_errors"])
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
