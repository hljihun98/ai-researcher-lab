"""에이전트의 빈 LLM 응답이 정상 발언으로 처리되지 않는지 검증."""
import unittest


class _EmptyResponse:
    content = []


class _EmptyMessages:
    def create(self, **kwargs):
        return _EmptyResponse()


class _EmptyClient:
    messages = _EmptyMessages()


class AgentErrorNormalizationTests(unittest.TestCase):
    def test_base_agent_normalizes_empty_response(self):
        from agents.base import BaseAgent
        from conversation import ConversationState, is_failure_message

        state = ConversationState(question="빈 응답 테스트")
        utterance = BaseAgent("researcher", _EmptyClient()).speak(state)

        self.assertEqual(utterance.message, "(빈 응답)")
        self.assertTrue(is_failure_message(utterance.message))

    def test_fact_checker_normalizes_empty_response(self):
        from agents.fact_checker import FactCheckerAgent
        from conversation import ConversationState, is_failure_message

        state = ConversationState(question="팩트체커 빈 응답 테스트")
        utterance = FactCheckerAgent("fact_checker", _EmptyClient()).speak(state)

        self.assertEqual(utterance.message, "(빈 응답)")
        self.assertTrue(is_failure_message(utterance.message))

    def test_synthesizer_normalizes_empty_response(self):
        from agents.synthesizer import SynthesizerAgent
        from conversation import ConversationState, is_failure_message

        state = ConversationState(question="조율자 빈 응답 테스트")
        answer = SynthesizerAgent("synthesizer", _EmptyClient()).finalize(state)

        self.assertEqual(answer, "(빈 응답)")
        self.assertTrue(is_failure_message(answer))


if __name__ == "__main__":
    unittest.main()
