"""데모 모드 검증.

원래 버그: 데모 응답 블록에 .type 속성이 없어 base/orchestrator/synthesizer의
`getattr(block, "type", None) == "text"` 필터에 전부 걸러져 발언·답변이 빈 문자열이 됐다.
아래 E2E 테스트가 이 회귀를 잡는다.
"""
import json
import os
import unittest


class DemoModeTests(unittest.TestCase):
    def setUp(self):
        os.environ["AI_RESEARCHER_DEMO_MODE"] = "1"
        os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_demo_client_blocks_have_text_type(self):
        from main import build_runtime_client

        client = build_runtime_client()
        resp = client.messages.create(
            model="demo-model",
            max_tokens=100,
            system="리서처 역할",
            messages=[{"role": "user", "content": "질문"}],
        )
        self.assertTrue(resp.content)
        self.assertEqual(resp.content[0].type, "text")
        self.assertTrue(resp.content[0].text.strip())

    def test_orchestrator_demo_returns_valid_json(self):
        from main import build_runtime_client

        client = build_runtime_client()
        resp = client.messages.create(
            model="demo-model",
            max_tokens=100,
            system="당신은 AI 연구팀의 팀 리더 (오케스트레이터)입니다.",
            messages=[{"role": "user", "content": "결정하세요"}],
        )
        decision = json.loads(resp.content[0].text)
        self.assertIn(decision["action"], ("encounter", "finalize"))

    def test_end_to_end_demo_produces_nonempty_output(self):
        from main import run_session

        state = run_session("소규모 스타트업에 적합한 RAG 아키텍처는?")

        # 최종 답변이 비어있지 않아야 한다 (원래 버그는 여기서 빈 문자열이었음).
        self.assertTrue(state.final_answer and state.final_answer.strip())
        # 실제 발언이 쌓였고, 메시지가 비어있지 않아야 한다.
        self.assertGreater(len(state.history), 0)
        for u in state.history:
            self.assertTrue(u.message.strip(), f"빈 발언: {u}")


if __name__ == "__main__":
    unittest.main()
