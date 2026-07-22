"""
AI Researcher Lab — Phase 1 CLI 엔트리포인트.

실행:
    python main.py "질문을 여기에 적으세요"

또는 인자 없이 실행하면 대화형으로 질문을 물어봄.
"""
import json
import os
import sys
import time
from dataclasses import dataclass

try:
    from anthropic import Anthropic
except Exception:  # pragma: no cover - optional dependency in demo mode
    Anthropic = None

import config
from agents import build_agents
from conversation import ConversationState
from orchestrator import Orchestrator


class _DemoBlock:
    """anthropic 응답 블록 흉내. base.py/orchestrator.py가 .type로 필터하므로 필수."""

    def __init__(self, text: str):
        self.type = "text"
        self.text = text


@dataclass
class DemoResponse:
    content: list

    def __init__(self, text: str):
        self.content = [_DemoBlock(text)]


# 데모 대화 대본 — API 키 없이도 "실제 대화가 흐르는 것처럼" 보이게 하는 캔드 응답.
# 역할은 시스템 프롬프트 내용으로 판별한다.
_DEMO_LINES = {
    "researcher": [
        "소규모라면 pgvector로 시작하는 게 어때요? [확신: 중간]",
        "임베딩 캐시만 잘 써도 비용은 잡힐 것 같아요. [확신: 낮음]",
        "그럼 BM25랑 하이브리드로 가면 정확도도 오르죠. [확신: 중간]",
    ],
    "critic": [
        "좋은데, 트래픽 스파이크 오면 pgvector 버틸까요? [확신: 중간]",
        "그 임베딩 비용 계산은 실제로 해보셨어요? [확신: 높음]",
        "말씀 일리 있지만 운영 인덱스 유지비를 빼먹었어요. [확신: 중간]",
    ],
    "expert": [
        "[10년차 백엔드 관점] 월 10만 쿼리 이하면 오버킬이에요. [확신: 높음]",
        "실무에선 대부분 하이브리드 안 씁니다. 단순한 게 이겨요. [확신: 높음]",
    ],
    "fact_checker": [
        "확인했더니 임베딩 API 가격 최근 크게 내렸습니다. [확신: 높음]",
        "pgvector는 10만 벡터도 벤치마크상 잘 돕니다. [확신: 높음]",
    ],
    "synthesizer": [
        "**결론**: 소규모 스타트업이라면 pgvector + BM25 하이브리드로 시작하는 게 최선입니다.\n\n"
        "리서처가 pgvector 도입을 제안했고 비평가가 임베딩 비용·스파이크 우려를 짚었습니다. "
        "전문가는 \"월 10만 쿼리 이하면 오버킬\"이라며 단순한 구성을 권했고, "
        "팩트체커가 임베딩 가격 인하와 pgvector 성능을 확인해 비용 우려는 상당 부분 해소됐습니다.\n\n"
        "다만 트래픽이 예측 불가능하면 관리형 벡터 DB가 나을 수 있다는 관점은 남아 있습니다.\n\n"
        "**최종 확신도: 높음**\n\n"
        "_(⚠ 데모 모드 응답입니다. 실제 답변을 보려면 ANTHROPIC_API_KEY를 설정하세요.)_"
    ],
}

# 데모 오케스트레이터가 라운드마다 내놓을 결정 (신뢰도 상승 → finalize).
_DEMO_DECISIONS = [
    {"confidence_score": 45, "confidence_delta": 25, "action": "encounter",
     "agents": ["researcher", "critic"], "location": "whiteboard",
     "confidence_reason": "리서처 가설에 비평가가 비용 이슈 제기.",
     "reason": "발산된 아이디어를 비평가가 검증."},
    {"confidence_score": 65, "confidence_delta": 20, "action": "encounter",
     "agents": ["fact_checker", "expert"], "location": "server_room",
     "confidence_reason": "비용 우려를 팩트체커가 검증, 전문가가 실무 관점 보강.",
     "reason": "제기된 우려를 검증/보강."},
    {"confidence_score": 88, "confidence_delta": 23, "action": "finalize",
     "confidence_reason": "검증 완료, 실무 관점 일치. 반박 해소됨.",
     "reason": "대부분 주장이 검증되어 조율자 호출."},
]


def _demo_role(system: str) -> str:
    for key, marker in (
        ("orchestrator", "오케스트레이터"),
        ("researcher", "리서처"),
        ("critic", "비평가"),
        ("expert", "도메인 전문가"),
        ("fact_checker", "팩트체커"),
        ("synthesizer", "조율자"),
    ):
        if marker in system:
            return key
    return "unknown"


class DemoClient:
    def __init__(self):
        self.calls = []
        self._orch_round = 0
        self._turn_counts = {}

    class Messages:
        def __init__(self, parent):
            self.parent = parent

        def create(self, **kwargs):
            self.parent.calls.append(kwargs)
            role = _demo_role(kwargs.get("system", ""))

            if role == "orchestrator":
                idx = min(self.parent._orch_round, len(_DEMO_DECISIONS) - 1)
                self.parent._orch_round += 1
                return DemoResponse(json.dumps(_DEMO_DECISIONS[idx], ensure_ascii=False))

            lines = _DEMO_LINES.get(role)
            if not lines:
                return DemoResponse("데모 모드 응답입니다. [확신: 낮음]")
            n = self.parent._turn_counts.get(role, 0)
            self.parent._turn_counts[role] = n + 1
            return DemoResponse(lines[n % len(lines)])

    @property
    def messages(self):
        return self.Messages(self)


def build_runtime_client():
    if os.environ.get("AI_RESEARCHER_DEMO_MODE") == "1" or not os.environ.get("ANTHROPIC_API_KEY"):
        return DemoClient()
    if Anthropic is None:
        raise RuntimeError("anthropic 패키지가 설치되지 않았습니다.")
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


# ---- 예쁜 CLI 출력 ----
COLORS = {
    "researcher": "\033[95m",   # magenta
    "critic": "\033[91m",       # red
    "expert": "\033[92m",       # green
    "fact_checker": "\033[94m", # blue
    "synthesizer": "\033[93m",  # yellow
    "orchestrator": "\033[90m", # grey
}
RESET = "\033[0m"
BOLD = "\033[1m"


def color_agent(agent_id: str, text: str) -> str:
    return f"{COLORS.get(agent_id, '')}{text}{RESET}"


def banner(text: str) -> None:
    line = "─" * 60
    print(f"\n{line}\n{BOLD}{text}{RESET}\n{line}")


def print_orchestrator(decision: dict, state: ConversationState) -> None:
    reason = decision.get("reason", "")
    conf = state.confidence_score
    delta = decision.get("confidence_delta", 0)
    delta_str = f"+{delta}" if delta >= 0 else str(delta)
    header = f"[지휘부] 신뢰도 {conf}/100 ({delta_str}) · {decision.get('action')}"
    print(color_agent("orchestrator", header))
    if reason:
        print(color_agent("orchestrator", f"  이유: {reason}"))
    if decision.get("action") == "encounter":
        names = [config.AGENTS[a]["display_name"] for a in decision["agents"]]
        loc = decision.get("location", "?")
        loc_desc = config.LOCATIONS.get(loc, loc)
        print(color_agent("orchestrator", f"  → {names[0]} × {names[1]} @ {loc_desc}"))


def print_utterance(u, state: ConversationState) -> None:
    name = config.AGENTS[u.agent]["display_name"]
    conf_mark = {"low": "?", "medium": "·", "high": "!"}.get(u.confidence, "·")
    loc = f" @{u.location}" if u.location else ""
    line = f"  [{conf_mark}] {name}{loc}: {u.message}"
    print(color_agent(u.agent, line))


# ---- 인카운터 실행 ----
def run_encounter(agents_map, state, decision):
    """두 에이전트가 마주쳐 2~3턴 주고받음."""
    a1_id, a2_id = decision["agents"]
    location = decision.get("location")
    agent1 = agents_map[a1_id]
    agent2 = agents_map[a2_id]

    # 1턴: agent1이 대화 시작
    u1 = agent1.speak(state, location=location, responds_to=None)
    print_utterance(u1, state)

    # 2턴: agent2가 반응
    u2 = agent2.speak(state, location=location, responds_to=a1_id)
    print_utterance(u2, state)

    # 3턴 (선택): agent1이 재반응. exchanges=3이면.
    if config.ENCOUNTER_MAX_EXCHANGES >= 3:
        u3 = agent1.speak(state, location=location, responds_to=a2_id)
        print_utterance(u3, state)


# ---- 메인 루프 ----
def run_session(question: str) -> ConversationState:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    demo_mode = os.environ.get("AI_RESEARCHER_DEMO_MODE") == "1"

    if not api_key and not demo_mode:
        print("ERROR: ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
        print("  export ANTHROPIC_API_KEY='your-key-here'")
        print("  또는 AI_RESEARCHER_DEMO_MODE=1 로 데모 모드로 실행할 수 있습니다.")
        sys.exit(1)

    client = build_runtime_client()
    agents_map = build_agents(client)
    orchestrator = Orchestrator(client)

    state = ConversationState(question=question)

    banner(f"❓ 질문: {question}")

    round_num = 0
    while not state.should_finalize():
        round_num += 1
        print(f"\n{BOLD}━━━ 라운드 {round_num} ━━━{RESET}")

        decision = orchestrator.decide(state)
        print_orchestrator(decision, state)

        if decision.get("action") == "finalize":
            break

        if decision.get("action") == "encounter":
            try:
                run_encounter(agents_map, state, decision)
            except Exception as e:
                print(f"  ⚠ 인카운터 오류: {e}")
            time.sleep(0.3)  # UI 정신없지 않게

    # 최종 답변
    banner("📝 최종 답변 작성 중...")
    synthesizer = agents_map["synthesizer"]
    try:
        answer = synthesizer.finalize(state)
    except Exception as e:
        answer = (
            f"(최종 답변 생성 중 오류가 발생했습니다: {e})\n"
            f"지금까지의 대화 로그는 아래 경로에 저장됩니다."
        )
        state.final_answer = answer

    banner("✅ 최종 답변")
    print(answer)
    print()

    log_path = state.save_log()
    print(f"\n{BOLD}세션 로그 저장:{RESET} {log_path}")
    return state


def main():
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        try:
            question = input("질문을 입력하세요: ").strip()
        except EOFError:
            question = ""

    if not question:
        print("질문이 비어있습니다.")
        sys.exit(1)

    run_session(question)


if __name__ == "__main__":
    main()
