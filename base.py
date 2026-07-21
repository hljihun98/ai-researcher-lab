"""
모든 에이전트의 부모 클래스.
개별 에이전트는 이걸 상속하고, 필요하면 speak()만 오버라이드한다.
"""
from pathlib import Path
from typing import Optional
import re

from anthropic import Anthropic

import config
from conversation import ConversationState, Utterance


class BaseAgent:
    def __init__(self, agent_id: str, client: Anthropic):
        if agent_id not in config.AGENTS:
            raise ValueError(f"Unknown agent: {agent_id}")
        self.agent_id = agent_id
        self.meta = config.AGENTS[agent_id]
        self.client = client
        self.system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        prompt_path = config.PROJECT_ROOT / self.meta["prompt_file"]
        return prompt_path.read_text(encoding="utf-8")

    @property
    def display_name(self) -> str:
        return self.meta["display_name"]

    def speak(
        self,
        state: ConversationState,
        location: Optional[str] = None,
        responds_to: Optional[str] = None,
        extra_instruction: str = "",
    ) -> Utterance:
        """에이전트가 한 마디 발언. 결과를 state에 추가하고 그 Utterance를 반환."""
        user_content = self._build_user_message(state, location, responds_to, extra_instruction)

        response = self.client.messages.create(
            model=config.MODEL_NAME,
            max_tokens=config.MAX_TOKENS_PER_TURN,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        raw_text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ).strip()

        message, confidence = self._parse_response(raw_text)
        u = Utterance(
            agent=self.agent_id,
            message=message,
            confidence=confidence,
            location=location,
            responds_to=responds_to,
        )
        state.add_utterance(u)
        return u

    def _build_user_message(
        self,
        state: ConversationState,
        location: Optional[str],
        responds_to: Optional[str],
        extra_instruction: str,
    ) -> str:
        loc_desc = ""
        if location and location in config.LOCATIONS:
            loc_desc = f"\n\n[현재 장소: {config.LOCATIONS[location]}]"

        responds_desc = ""
        if responds_to:
            last = state.last_utterance()
            if last and last.agent == responds_to:
                other_name = config.AGENTS[responds_to]["display_name"]
                responds_desc = f"\n\n[방금 {other_name}가 이렇게 말했습니다]\n{other_name}: {last.message}"

        history_desc = ""
        if state.history:
            history_desc = f"\n\n[지금까지 대화]\n{state.formatted_history(last_n=8)}"

        extra = f"\n\n{extra_instruction}" if extra_instruction else ""

        return (
            f"[사용자 질문]\n{state.question}"
            f"{history_desc}"
            f"{loc_desc}"
            f"{responds_desc}"
            f"{extra}"
            f"\n\n이제 당신의 발언 한 마디를 하세요. 규칙: 1~2문장, 40자 내외, "
            f"마지막에 [확신: 낮음/중간/높음] 태그."
        )

    def _parse_response(self, raw: str) -> tuple[str, str]:
        """발언 텍스트와 확신도 태그를 분리."""
        # [확신: 낮음/중간/높음] 패턴 찾기
        pattern = r"\[확신[:\s]*([가-힣]+)\]"
        match = re.search(pattern, raw)
        confidence = "medium"
        if match:
            kr = match.group(1)
            confidence = {"낮음": "low", "중간": "medium", "높음": "high"}.get(kr, "medium")
            message = re.sub(pattern, "", raw).strip()
        else:
            message = raw
        # 다중 공백 정리
        message = re.sub(r"\s+", " ", message).strip()
        return message, confidence
