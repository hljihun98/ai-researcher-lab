"""
전역 설정.
변경하고 싶은 값은 여기서. 프롬프트 파일은 prompts/ 폴더.
"""
import os
from pathlib import Path

# ---- API ----
# PROJECT_MEMO 섹션 4의 설계 결정("Sonnet 4.6 기본")과 일치.
MODEL_NAME = "claude-sonnet-4-6"  # 오케스트레이터 + 에이전트 공통
FALLBACK_MODEL = "claude-haiku-4-5"  # 비용 절감 실험용 (현재 미사용)
MAX_TOKENS_PER_TURN = 300  # 한 발언은 짧게

# ---- 대화 제어 ----
MAX_TURNS = 20                    # 안전장치: 이 이상 돌면 강제 종료
CONFIDENCE_THRESHOLD = 85         # 이 이상이면 조율자 호출
INITIAL_CONFIDENCE = 20           # 시작 신뢰도
ENCOUNTER_MAX_EXCHANGES = 3       # 한 마주침에서 주고받는 최대 발언 수

# ---- 팩트체커 ----
FACT_CHECKER_MAX_SEARCHES = 5     # 웹 검색 총 횟수 상한

# ---- 에이전트 목록 ----
# 순서는 오케스트레이터가 참고하는 순서 (표시용)
AGENTS = {
    "researcher": {
        "display_name": "리서처",
        "color": "#7F77DD",
        "prompt_file": "prompts/researcher.txt",
        "can_search": False,
    },
    "critic": {
        "display_name": "비평가",
        "color": "#D85A30",
        "prompt_file": "prompts/critic.txt",
        "can_search": False,
    },
    "expert": {
        "display_name": "전문가",
        "color": "#0F6E56",
        "prompt_file": "prompts/expert.txt",
        "can_search": False,
    },
    "fact_checker": {
        "display_name": "팩트체커",
        "color": "#378ADD",
        "prompt_file": "prompts/fact_checker.txt",
        "can_search": True,  # 유일하게 웹 검색 가능
    },
    "synthesizer": {
        "display_name": "조율자",
        "color": "#EF9F27",
        "prompt_file": "prompts/synthesizer.txt",
        "can_search": False,
    },
}

# 인카운터 참여 가능한 에이전트 (조율자는 최종 답변 전담이라 제외)
ENCOUNTER_AGENTS = ["researcher", "critic", "expert", "fact_checker"]

# ---- 맵 상의 장소 (Phase 1에서는 텍스트로만 씀. Phase 2에서 좌표 추가) ----
LOCATIONS = {
    "library": "📚 지식 서고 - 자료 조사, 근거 확인",
    "whiteboard": "📋 화이트보드 - 아이디어 발산, 반박",
    "coffee": "☕ 커피머신 - 브레인스토밍, 새로운 관점",
    "server_room": "🔧 도구실 - 웹 검색, 계산",
    "meeting_desk": "🪑 회의 책상 - 종합 토론",
}

# ---- 경로 ----
PROJECT_ROOT = Path(__file__).parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ---- 오케스트레이터 ----
ORCHESTRATOR_PROMPT_FILE = "prompts/orchestrator.txt"
