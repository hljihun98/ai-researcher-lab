"""세션 소유권·무작위 ID와 실패 상태/신뢰도 보정 검증."""
import os
import re
import unittest
from unittest.mock import patch


class SecurityAndErrorStateTests(unittest.TestCase):
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
        self.owner_a = self.server.app.test_client()
        self.owner_b = self.server.app.test_client()
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

    def test_session_lists_are_owner_scoped_and_ids_are_random(self):
        response_a = self.owner_a.post(
            "/api/run", json={"question": "A 브라우저의 질문"}
        )
        response_b = self.owner_b.post(
            "/api/run", json={"question": "B 브라우저의 질문"}
        )
        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(response_b.status_code, 200)

        result_a = response_a.get_json()
        result_b = response_b.get_json()
        self.assertFalse(re.fullmatch(r"s\d+", result_a["id"]))
        self.assertRegex(result_a["id"], r"^[A-Za-z0-9_-]{10,}$")
        self.assertNotEqual(result_a["id"], result_b["id"])
        self.assertNotIn("owner", result_a)

        cookie = response_a.headers.get("Set-Cookie", "")
        self.assertIn("owner=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Path=/", cookie)
        self.assertIn("Max-Age=", cookie)

        sessions_a = self.owner_a.get("/api/sessions").get_json()["sessions"]
        sessions_b = self.owner_b.get("/api/sessions").get_json()["sessions"]
        self.assertEqual([item["question"] for item in sessions_a], ["A 브라우저의 질문"])
        self.assertEqual([item["question"] for item in sessions_b], ["B 브라우저의 질문"])

        # 무작위 ID를 가진 공유 링크는 owner가 달라도 직접 조회할 수 있어야 한다.
        shared = self.owner_b.get(f"/api/session/{result_a['id']}")
        self.assertEqual(shared.status_code, 200)
        self.assertEqual(shared.get_json()["question"], "A 브라우저의 질문")
        self.assertNotIn("owner", shared.get_json())

    def test_failed_utterance_marks_partial_and_reduces_confidence(self):
        from conversation import ConversationState, Utterance

        state = ConversationState(question="실패 상태 테스트", confidence_score=80)
        state.add_utterance(
            Utterance(
                agent="researcher",
                message="(Gemini 오류: 429 RESOURCE_EXHAUSTED)",
                confidence="low",
                location="whiteboard",
                responds_to=None,
            )
        )
        state.final_answer = "가능한 범위에서 만든 부분 답변"

        with patch.object(self.server, "run_session_web", return_value=state):
            response = self.owner_a.post(
                "/api/run", json={"question": state.question}
            )

        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertTrue(result["has_errors"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["confidence_score"], 60)

        replay = self.owner_a.get(f"/api/session/{result['id']}").get_json()
        self.assertTrue(replay["has_errors"])
        self.assertEqual(replay["status"], "partial")
        self.assertEqual(replay["confidence_score"], 60)

    def test_failed_lite_round_does_not_keep_confidence_gain(self):
        from conversation import ConversationState, Utterance
        from orchestrator import Orchestrator

        state = ConversationState(question="라이트 실패 테스트")
        orchestrator = Orchestrator(client=object())
        decision = orchestrator.decide_offline(state)
        self.assertEqual(state.confidence_score, 50)

        state.add_utterance(
            Utterance(
                agent="researcher",
                message="(빈 응답)",
                confidence="low",
                location="whiteboard",
                responds_to=None,
            )
        )
        orchestrator.reconcile_offline_round(state, decision)

        self.assertEqual(state.confidence_score, self.config.INITIAL_CONFIDENCE)
        self.assertEqual(decision["confidence_delta"], 0)
        self.assertEqual(state.orchestrator_log[-1]["delta"], 0)
        self.assertIn("실패", state.orchestrator_log[-1]["confidence_reason"])


if __name__ == "__main__":
    unittest.main()
