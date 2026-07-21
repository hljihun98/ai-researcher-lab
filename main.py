"""
AI Researcher Lab — Phase 1 CLI 엔트리포인트.

실행:
    python main.py "질문을 여기에 적으세요"

또는 인자 없이 실행하면 대화형으로 질문을 물어봄.
"""
import os
import sys
import time

from anthropic import Anthropic

import config
from agents import build_agents
from conversation import ConversationState
from orchestrator import Orchestrator


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
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
        print("  export ANTHROPIC_API_KEY='your-key-here'")
        sys.exit(1)

    client = Anthropic(api_key=api_key)
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
    answer = synthesizer.finalize(state)

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
