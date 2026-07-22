"""
팩트체커: base와 다르게 웹 검색 툴을 쓸 수 있음.
Gemini는 Google Search grounding, Anthropic은 web_search 툴을 사용.
"""
from typing import Optional

import config
from conversation import ConversationState, Utterance
from .base import BaseAgent


class FactCheckerAgent(BaseAgent):
    """유일하게 웹 검색이 가능한 에이전트."""

    def speak(
        self,
        state: ConversationState,
        location: Optional[str] = None,
        responds_to: Optional[str] = None,
        extra_instruction: str = "",
    ) -> Utterance:
        user_content = self._build_user_message(state, location, responds_to, extra_instruction)

        # 검색 한도 남았을 때만 툴 붙임
        is_gemini = type(self.client).__name__ == "GeminiClient"
        can_search = state.fact_checker_search_count < config.FACT_CHECKER_MAX_SEARCHES
        tools = []
        if can_search and not is_gemini:
            tools = [
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 2,  # 이 발언 내에서 최대 2회
                }
            ]

        create_kwargs = dict(
            model=config.MODEL_NAME,
            max_tokens=config.MAX_TOKENS_PER_TURN * 3,  # 검색 결과 처리 여유
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        grounding_requested = can_search and is_gemini
        if grounding_requested:
            create_kwargs["grounding"] = True
        elif tools:
            create_kwargs["tools"] = tools

        response = self.client.messages.create(**create_kwargs)

        # 텍스트 블록만 추출. 웹 검색 결과는 이미 모델이 흡수한 상태.
        text_parts = []
        used_search = False
        for block in getattr(response, "content", []):
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(block.text)
            elif btype in ("server_tool_use", "web_search_tool_result"):
                used_search = True

        raw_text = "".join(text_parts).strip() or "(빈 응답)"
        # Gemini는 Anthropic식 tool-use 블록을 반환하지 않으므로 grounding 요청을
        # 한 번의 검색 시도로 계산해 기존 호출 한도를 동일하게 적용한다.
        if used_search or grounding_requested:
            state.fact_checker_search_count += 1

        message, confidence = self._parse_response(raw_text)
        u = Utterance(
            agent=self.agent_id,
            message=message,
            confidence=confidence,
            location=location or "server_room",
            responds_to=responds_to,
        )
        state.add_utterance(u)
        return u
