"""
조율자: 마주침에 참여하지 않고 대화 끝에서 최종 답변만 낸다.
speak()가 아니라 finalize()를 씀.
"""
import config
from conversation import ConversationState
from .base import BaseAgent


class SynthesizerAgent(BaseAgent):
    def finalize(self, state: ConversationState) -> str:
        """전체 대화를 읽고 최종 답변 생성. state.final_answer에도 저장."""
        history_block = state.formatted_history()  # 전체
        user_content = (
            f"[사용자 질문]\n{state.question}\n\n"
            f"[대화 로그 - 총 {state.turn_count}턴, 최종 신뢰도 {state.confidence_score}/100]\n"
            f"{history_block}\n\n"
            f"이제 사용자에게 전달할 최종 답변을 작성하세요. "
            f"프롬프트의 형식/톤/길이 규칙을 지키세요."
        )

        response = self.client.messages.create(
            model=config.MODEL_NAME,
            max_tokens=1200,  # 최종 답변은 길이 여유
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        answer = self._extract_text(response)

        state.final_answer = answer
        return answer

    # 방어: 실수로 speak() 부르지 않도록
    def speak(self, *args, **kwargs):
        raise RuntimeError(
            "Synthesizer는 인카운터에 참여하지 않습니다. finalize()를 쓰세요."
        )
