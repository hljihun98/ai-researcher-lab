"""
대화 상태 관리.
프로젝트 전체가 하나의 ConversationState를 공유한다.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

import config


FAILURE_MESSAGE_PREFIXES = (
    "(Gemini 오류",
    "(빈 응답",
    "(최종 답변 생성 중 오류",
)


def is_failure_message(message: Optional[str]) -> bool:
    """LLM 어댑터와 세션 실행기가 만든 실패 응답인지 판정한다."""
    if not isinstance(message, str):
        return False
    return message.lstrip().startswith(FAILURE_MESSAGE_PREFIXES)


@dataclass
class Utterance:
    """한 발언 = 인카운터 내 한 마디."""
    agent: str                        # agent id (e.g. "researcher")
    message: str                      # 발언 내용
    confidence: str = "medium"        # "low" | "medium" | "high"
    location: Optional[str] = None    # 발언 장소 id
    turn: int = 0                     # 전체 대화에서 몇 번째 발언인가
    responds_to: Optional[str] = None # 방금 응답한 상대 agent id
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_display(self) -> str:
        """CLI/로그용 예쁜 한 줄."""
        name = config.AGENTS[self.agent]["display_name"]
        conf_emoji = {"low": "💭", "medium": "💬", "high": "❗"}.get(self.confidence, "💬")
        loc = f" @{self.location}" if self.location else ""
        return f"{conf_emoji} {name}{loc}: {self.message}"


@dataclass
class ConversationState:
    """대화 전체 상태. 모든 에이전트/오케스트레이터가 이걸 읽고 씀."""
    question: str
    history: list[Utterance] = field(default_factory=list)
    confidence_score: int = config.INITIAL_CONFIDENCE
    turn_count: int = 0
    max_turns: int = config.MAX_TURNS
    confidence_threshold: int = config.CONFIDENCE_THRESHOLD
    fact_checker_search_count: int = 0
    final_answer: Optional[str] = None
    # 예외로 인해 발언 자체가 만들어지지 못한 런타임 실패(공개 응답에는 직접 노출 안 함).
    runtime_errors: list[str] = field(default_factory=list)
    # 오케스트레이터 로그 (신뢰도 변화 추적)
    orchestrator_log: list[dict] = field(default_factory=list)

    def add_utterance(self, u: Utterance) -> None:
        self.turn_count += 1
        u.turn = self.turn_count
        self.history.append(u)

    def last_utterance(self) -> Optional[Utterance]:
        return self.history[-1] if self.history else None

    def utterances_by(self, agent: str) -> list[Utterance]:
        return [u for u in self.history if u.agent == agent]

    def formatted_history(self, last_n: Optional[int] = None) -> str:
        """LLM에게 넘기기 좋은 형식."""
        entries = self.history[-last_n:] if last_n else self.history
        if not entries:
            return "(아직 대화 없음)"
        lines = []
        for u in entries:
            name = config.AGENTS[u.agent]["display_name"]
            loc = f" [{u.location}]" if u.location else ""
            lines.append(f"턴{u.turn} {name}{loc}: {u.message} [확신: {u.confidence}]")
        return "\n".join(lines)

    def should_finalize(self) -> bool:
        """조율자를 부를 때인가?"""
        if self.final_answer is not None:
            return True
        if self.confidence_score >= self.confidence_threshold:
            return True
        if self.turn_count >= self.max_turns:
            return True
        return False

    # 로그 스키마 버전. Phase 2 시각화가 이 값으로 호환성을 판단한다.
    # 스키마를 바꾸면 반드시 올리고 PROJECT_MEMO에 기록할 것.
    LOG_SCHEMA_VERSION = 1

    def save_log(self, path: Optional[Path] = None) -> Path:
        """JSON으로 로그 저장. 나중에 시각화 단계에서 재생용."""
        if path is None:
            # 같은 초에 여러 세션이 끝나도 로그 파일이 덮어써지지 않도록 마이크로초 포함.
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = config.LOG_DIR / f"session_{ts}.json"
        data = {
            "schema_version": self.LOG_SCHEMA_VERSION,
            "generated_at": datetime.now().isoformat(),
            # 시각화가 로그만으로 재생할 수 있도록 에이전트/장소 정의를 함께 저장.
            "agents": {
                aid: {"display_name": m["display_name"], "color": m["color"]}
                for aid, m in config.AGENTS.items()
            },
            "locations": config.LOCATIONS,
            "question": self.question,
            "final_answer": self.final_answer,
            "confidence_score": self.confidence_score,
            "confidence_threshold": self.confidence_threshold,
            "turn_count": self.turn_count,
            "history": [asdict(u) for u in self.history],
            "orchestrator_log": self.orchestrator_log,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
