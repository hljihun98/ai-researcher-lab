"""Gemini 팩트체커의 Google Search grounding 경로 검증."""
import unittest
from unittest.mock import patch


class _TextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, text):
        self.content = [_TextBlock(text)]


class GeminiClient:
    """이름 기반 백엔드 분기 검증용 네트워크 없는 가짜 클라이언트."""

    def __init__(self):
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Response("검색 근거를 확인했습니다. [확신: 높음]")


class AnthropicClient(GeminiClient):
    """기존 Anthropic 도구 경로 보존 검증용 가짜 클라이언트."""


class GroundingTests(unittest.TestCase):
    def test_demo_fact_checker_speaks_without_grounding_requirement(self):
        from agents.fact_checker import FactCheckerAgent
        from conversation import ConversationState
        from main import DemoClient

        client = DemoClient()
        utterance = FactCheckerAgent("fact_checker", client).speak(
            ConversationState(question="데모 팩트체크")
        )

        self.assertTrue(utterance.message)
        self.assertNotIn("grounding", client.calls[-1])

    def test_fact_checker_enables_grounding_only_for_gemini(self):
        from agents.fact_checker import FactCheckerAgent
        from conversation import ConversationState

        client = GeminiClient()
        state = ConversationState(question="사실인지 확인해줘")
        FactCheckerAgent("fact_checker", client).speak(state)

        self.assertIs(client.calls[-1]["grounding"], True)
        self.assertNotIn("tools", client.calls[-1])
        self.assertEqual(state.fact_checker_search_count, 1)

    def test_anthropic_fact_checker_keeps_web_search_tool(self):
        from agents.fact_checker import FactCheckerAgent
        from conversation import ConversationState

        client = AnthropicClient()
        FactCheckerAgent("fact_checker", client).speak(
            ConversationState(question="사실인지 확인해줘")
        )

        self.assertNotIn("grounding", client.calls[-1])
        self.assertEqual(client.calls[-1]["tools"][0]["name"], "web_search")

    def test_grounding_adds_google_search_tool_to_config(self):
        from gemini_client import GeminiClient as RealGeminiClient

        client = object.__new__(RealGeminiClient)
        config = client._build_config("시스템", 300, False, grounding=True)

        self.assertEqual(len(config.tools), 1)
        tool = config.tools[0]
        self.assertTrue(
            getattr(tool, "google_search", None) is not None
            or getattr(tool, "google_search_retrieval", None) is not None
        )

    def test_unsupported_grounding_falls_back_without_network(self):
        from gemini_client import GeminiClient as RealGeminiClient

        client = object.__new__(RealGeminiClient)
        client._model = "gemini-3.5-flash"
        calls = []

        def generate_best(contents, system, max_tokens, grounding=False):
            calls.append(grounding)
            if grounding:
                raise RuntimeError("google_search is unsupported")
            return "일반 생성 응답"

        with patch.object(client, "_generate_best", side_effect=generate_best):
            response = client._create(
                system="시스템",
                messages=[{"role": "user", "content": "질문"}],
                max_tokens=300,
                grounding=True,
            )

        self.assertEqual(calls, [True, False])
        self.assertEqual(response.content[0].text, "일반 생성 응답")


if __name__ == "__main__":
    unittest.main()
