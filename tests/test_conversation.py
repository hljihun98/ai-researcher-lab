"""대화 상태 저장과 안전장치 검증."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


class ConversationSafetyTests(unittest.TestCase):
    def test_default_log_paths_do_not_collide_within_same_second(self):
        import config
        from conversation import ConversationState

        state = ConversationState(question="로그 파일명 충돌 테스트")
        state.final_answer = "답변"
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(config, "LOG_DIR", Path(temp_dir)):
                first = state.save_log()
                second = state.save_log()

            self.assertNotEqual(first, second)
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())

    def test_cli_stops_after_round_cap_when_all_encounters_fail(self):
        import config
        import main

        previous_demo = os.environ.get("AI_RESEARCHER_DEMO_MODE")
        os.environ["AI_RESEARCHER_DEMO_MODE"] = "1"

        class AlwaysEncounterOrchestrator:
            calls = 0

            def __init__(self, client):
                pass

            def decide(self, state):
                type(self).calls += 1
                return {
                    "action": "encounter",
                    "agents": ["researcher", "critic"],
                    "location": "whiteboard",
                    "confidence_delta": 0,
                }

        class FailingAgent:
            def speak(self, *args, **kwargs):
                raise RuntimeError("강제 실패")

        class FinalizingAgent:
            def finalize(self, state):
                state.final_answer = "안전 종료 답변"
                return state.final_answer

        agents = {
            "researcher": FailingAgent(),
            "critic": FailingAgent(),
            "expert": FailingAgent(),
            "fact_checker": FailingAgent(),
            "synthesizer": FinalizingAgent(),
        }

        try:
            with (
                patch.object(config, "MAX_TURNS", 3),
                patch.object(main, "build_runtime_client", return_value=object()),
                patch.object(main, "build_agents", return_value=agents),
                patch.object(main, "Orchestrator", AlwaysEncounterOrchestrator),
                patch.object(main.time, "sleep", return_value=None),
                patch("conversation.ConversationState.save_log", return_value=Path("log.json")),
                redirect_stdout(io.StringIO()),
            ):
                state = main.run_session("무한루프 방지 테스트")
        finally:
            if previous_demo is None:
                os.environ.pop("AI_RESEARCHER_DEMO_MODE", None)
            else:
                os.environ["AI_RESEARCHER_DEMO_MODE"] = previous_demo

        self.assertEqual(AlwaysEncounterOrchestrator.calls, 3)
        self.assertEqual(len(state.runtime_errors), 3)
        self.assertEqual(state.final_answer, "안전 종료 답변")


if __name__ == "__main__":
    unittest.main()
