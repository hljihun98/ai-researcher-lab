"""
전역 설정.
변경하고 싶은 값은 여기서. 프롬프트 파일은 prompts/ 폴더.
"""
import os
from pathlib import Path

# ---- API ----
# 실시간 백엔드는 Gemini. (GEMINI_API_KEY 설정 시)
# MODEL_NAME은 Anthropic 폴백 경로에서만 쓰인다.
MODEL_NAME = "claude-sonnet-4-6"  # Anthropic 폴백용
FALLBACK_MODEL = "claude-haiku-4-5"  # 비용 절감 실험용 (현재 미사용)

# Gemini 모델. GEMINI_MODEL 환경변수로 오버라이드 가능.
# 참고: gemini-2.5-flash는 일부(신규) 계정에서 차단됨("no longer available to
# new users"). 실제 키로 검증된 gemini-3.5-flash를 기본값으로 사용.
GEMINI_MODEL = "gemini-3.5-flash"
MAX_TOKENS_PER_TURN = 300  # 한 발언은 짧게


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """잘못된 배포 환경변수 때문에 앱 import가 실패하지 않도록 범위를 제한한다."""
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


# Google SDK와 어댑터 재시도가 중첩되어 웹 요청이 수분간 멈추지 않도록 제한.
GEMINI_REQUEST_TIMEOUT_SECONDS = _bounded_env_int(
    "GEMINI_REQUEST_TIMEOUT_SECONDS", 20, 5, 60
)
GEMINI_MAX_ATTEMPTS = _bounded_env_int("GEMINI_MAX_ATTEMPTS", 1, 1, 3)
# Render gunicorn timeout(300초) 전에 부분 결과를 JSON으로 반환할 전체 세션 예산.
WEB_SESSION_BUDGET_SECONDS = _bounded_env_int(
    "AI_RESEARCHER_SESSION_BUDGET_SECONDS", 60, 30, 240
)

# ---- 대화 제어 ----
MAX_TURNS = 20                    # 안전장치: 이 이상 돌면 강제 종료
CONFIDENCE_THRESHOLD = 85         # 이 이상이면 조율자 호출
INITIAL_CONFIDENCE = 20           # 시작 신뢰도
ENCOUNTER_MAX_EXCHANGES = 2       # 한 마주침 발언 수 (무료 등급 호출 절약 위해 2)

# Gemini 무료 등급용 실행 경로. 오케스트레이터를 규칙 기반으로 바꾸고
# 2라운드(에이전트 4회) + 최종 조율 1회로 LLM 호출을 세션당 5회로 제한한다.
LITE_MODE = os.environ.get("AI_RESEARCHER_LITE") == "1"
LITE_MAX_ROUNDS = 2
LITE_ENCOUNTER_MAX_EXCHANGES = 2
LITE_CONFIDENCE_DELTA = 30

# ---- 팩트체커 ----
FACT_CHECKER_MAX_SEARCHES = 5     # 웹 검색 총 횟수 상한

# ---- 에이전트 목록 ----
# 순서는 오케스트레이터가 참고하는 순서 (표시용)
AGENTS = {
    "researcher": {
        "display_name": "리서처",
        "emoji": "💡",
        "role_desc": "아이디어 발산",
        "color": "#7F77DD",
        "prompt_file": "prompts/researcher.txt",
        "can_search": False,
    },
    "critic": {
        "display_name": "비평가",
        "emoji": "🧐",
        "role_desc": "논리 허점 짚기",
        "color": "#D85A30",
        "prompt_file": "prompts/critic.txt",
        "can_search": False,
    },
    "expert": {
        "display_name": "전문가",
        "emoji": "🎓",
        "role_desc": "실무 관점",
        "color": "#0F6E56",
        "prompt_file": "prompts/expert.txt",
        "can_search": False,
    },
    "fact_checker": {
        "display_name": "팩트체커",
        "emoji": "🔍",
        "role_desc": "사실 검증",
        "color": "#378ADD",
        "prompt_file": "prompts/fact_checker.txt",
        "can_search": True,  # 유일하게 웹 검색 가능
    },
    "synthesizer": {
        "display_name": "조율자",
        "emoji": "🧩",
        "role_desc": "최종 종합",
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
