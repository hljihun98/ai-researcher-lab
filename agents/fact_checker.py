"""
팩트체커: base와 다르게 웹 검색 툴을 쓸 수 있음.
Anthropic web_search 툴 규격에 맞춰 툴 호출을 활성화.
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
        tools = []
        if state.fact_checker_search_count < config.FACT_CHECKER_MAX_SEARCHES:
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
        if tools:
            create_kwargs["tools"] = tools

        response = self.client.messages.create(**create_kwargs)

        # 텍스트 블록만 추출. 웹 검색 결과는 이미 모델이 흡수한 상태.
        text_parts = []
        used_search = False
        for block in response.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(block.text)
            elif btype in ("server_tool_use", "web_search_tool_result"):
                used_search = True

        raw_text = "".join(text_parts).strip()
        if used_search:
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
