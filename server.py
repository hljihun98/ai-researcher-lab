"""
AI Researcher Lab — 웹 서버 (Phase 1.5).

CLI 백엔드를 Flask 웹앱으로 감싼다. 브라우저에서 질문을 입력하면
에이전트들이 대화한 로그와 최종 답변을 화면에 표시한다.

실행(로컬):
    python server.py            # http://localhost:8000

배포(Render web 서비스):
    gunicorn server:app --bind 0.0.0.0:$PORT --timeout 300 --workers 1

환경변수:
    ANTHROPIC_API_KEY      실제 모델로 대화 (설정 시)
    AI_RESEARCHER_DEMO_MODE=1  API 키 없이 캔드 응답으로 시연 (배포 기본값)
"""
import copy
import os
import secrets
import time
from collections import deque
from threading import Lock

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - 선택적 의존성
    pass

from flask import Flask, Response, g, jsonify, request

import config
from agents import build_agents
from conversation import ConversationState, is_failure_message
from main import build_runtime_client
from orchestrator import Orchestrator

app = Flask(__name__)

# 한 요청이 무한히 돌지 않도록 하는 풀 모드 상한.
MAX_ROUNDS = 4

# Render 무료 인스턴스의 비영속 환경에 맞춘 최근 세션 메모리 저장소.
SESSION_STORE_LIMIT = 20
OWNER_COOKIE_NAME = "owner"
OWNER_COOKIE_MAX_AGE = 60 * 60 * 24 * 7
CONFIDENCE_ERROR_PENALTY = 20
_session_store = deque(maxlen=SESSION_STORE_LIMIT)
_session_store_lock = Lock()


def _request_owner() -> str:
    """현재 브라우저의 owner 토큰을 가져오거나 새로 만든다."""
    cached = getattr(g, "session_owner", None)
    if cached:
        return cached

    owner = request.cookies.get(OWNER_COOKIE_NAME)
    if not owner:
        owner = secrets.token_urlsafe(16)
        g.session_owner_is_new = True
    g.session_owner = owner
    return owner


@app.after_request
def _ensure_owner_cookie(response):
    """owner 쿠키가 없는 브라우저에는 추측 불가능한 토큰을 발급한다."""
    owner = _request_owner()
    if getattr(g, "session_owner_is_new", False):
        response.set_cookie(
            OWNER_COOKIE_NAME,
            owner,
            max_age=OWNER_COOKIE_MAX_AGE,
            httponly=True,
            samesite="Lax",
            path="/",
        )
    return response


def _state_to_result(state: ConversationState) -> dict:
    """ConversationState를 /api/run의 공개 응답 스키마로 직렬화한다."""
    failed_outputs = sum(
        1 for utterance in state.history if is_failure_message(utterance.message)
    )
    if is_failure_message(state.final_answer):
        failed_outputs += 1
    failure_count = failed_outputs + len(state.runtime_errors)
    confidence_score = max(
        0, state.confidence_score - failure_count * CONFIDENCE_ERROR_PENALTY
    )

    return {
        "question": state.question,
        "confidence_score": confidence_score,
        "confidence_threshold": state.confidence_threshold,
        "final_answer": state.final_answer,
        "history": [
            {
                "agent": u.agent,
                "message": u.message,
                "confidence": u.confidence,
                "location": u.location,
                "turn": u.turn,
                "responds_to": u.responds_to,
            }
            for u in state.history
        ],
        "orchestrator_log": copy.deepcopy(state.orchestrator_log),
        "status": "partial" if failure_count else "ok",
        "has_errors": bool(failure_count),
    }


def _store_session(result: dict, owner: str) -> str:
    """완료된 세션을 독립 복사해 최신순 링버퍼에 저장한다."""
    saved = copy.deepcopy(result)
    with _session_store_lock:
        while True:
            session_id = secrets.token_urlsafe(8)
            if all(item["id"] != session_id for item in _session_store):
                break
        saved["id"] = session_id
        saved["owner"] = owner
        saved["ts"] = int(time.time())
        _session_store.appendleft(saved)
        return saved["id"]


def _get_stored_session(session_id: str) -> dict | None:
    """저장된 세션의 독립 복사본을 반환한다."""
    with _session_store_lock:
        return next(
            (copy.deepcopy(item) for item in _session_store if item["id"] == session_id),
            None,
        )


def _session_to_markdown(session: dict) -> str:
    """저장된 세션을 사람이 읽기 좋은 마크다운 문서로 변환한다."""
    lines = [
        f"# {session['question']}",
        "",
        f"**최종 신뢰도:** {session['confidence_score']}/100",
        "",
        "## 대화",
        "",
    ]

    rounds = []
    for utterance in session.get("history", []):
        if not rounds or utterance.get("responds_to") is None:
            rounds.append([])
        rounds[-1].append(utterance)

    if not rounds:
        lines.extend(["_(대화 기록 없음)_", ""])

    for round_number, utterances in enumerate(rounds, start=1):
        round_location_id = utterances[0].get("location")
        round_location = config.LOCATIONS.get(
            round_location_id, round_location_id or "장소 미지정"
        )
        lines.extend([f"### 라운드 {round_number} — {round_location}", ""])

        for utterance in utterances:
            agent_id = utterance.get("agent")
            display_name = config.AGENTS.get(agent_id, {}).get(
                "display_name", agent_id or "알 수 없는 에이전트"
            )
            location_id = utterance.get("location")
            location = config.LOCATIONS.get(
                location_id, location_id or "장소 미지정"
            )
            confidence = utterance.get("confidence", "medium")
            message = utterance.get("message", "")
            lines.append(
                f"**{display_name}** (@{location}, {confidence}): {message}"
            )
        lines.append("")

    lines.extend(
        [
            "## 최종 답변",
            "",
            session.get("final_answer") or "_(최종 답변 없음)_",
            "",
        ]
    )
    return "\n".join(lines)


def run_session_web(question: str) -> ConversationState:
    """CLI의 run_session과 같은 흐름이지만 출력 없이 state를 반환한다."""
    client = build_runtime_client()
    session_deadline = time.monotonic() + config.WEB_SESSION_BUDGET_SECONDS
    set_deadline = getattr(client, "set_deadline", None)
    if callable(set_deadline):
        set_deadline(session_deadline)
    agents_map = build_agents(client)
    orchestrator = Orchestrator(client)
    state = ConversationState(question=question)

    lite_mode = config.LITE_MODE
    max_rounds = config.LITE_MAX_ROUNDS if lite_mode else MAX_ROUNDS
    encounter_max_exchanges = (
        config.LITE_ENCOUNTER_MAX_EXCHANGES
        if lite_mode
        else config.ENCOUNTER_MAX_EXCHANGES
    )

    rounds = 0
    while not state.should_finalize() and rounds < max_rounds:
        if time.monotonic() >= session_deadline:
            state.runtime_errors.append(
                f"웹 세션 시간 예산({config.WEB_SESSION_BUDGET_SECONDS}초) 초과"
            )
            break
        rounds += 1
        decision = (
            orchestrator.decide_offline(state)
            if lite_mode
            else orchestrator.decide(state)
        )
        if decision.get("action") == "finalize":
            break
        if decision.get("action") == "encounter":
            runtime_failed = False
            try:
                a1_id, a2_id = decision["agents"]
                loc = decision.get("location")
                round_exchange_limit = max(
                    1,
                    min(
                        int(decision.get("exchange_limit", encounter_max_exchanges)),
                        encounter_max_exchanges,
                    ),
                )
                agents_map[a1_id].speak(state, location=loc, responds_to=None)
                if round_exchange_limit >= 2:
                    agents_map[a2_id].speak(state, location=loc, responds_to=a1_id)
                if round_exchange_limit >= 3:
                    agents_map[a1_id].speak(state, location=loc, responds_to=a2_id)
            except Exception as e:
                # 세션은 계속 진행하되 실패 사실은 상태와 신뢰도에 반영한다.
                runtime_failed = True
                state.runtime_errors.append(f"인카운터 오류: {e}")
            finally:
                if lite_mode:
                    orchestrator.reconcile_offline_round(
                        state, decision, runtime_failed=runtime_failed
                    )

    synthesizer = agents_map["synthesizer"]
    try:
        state.final_answer = synthesizer.finalize(state)
    except Exception as e:
        state.final_answer = f"(최종 답변 생성 중 오류: {e})"
    return state


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/meta")
def meta():
    """프론트가 에이전트 색상/이름과 데모 여부를 알도록."""
    has_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    demo = os.environ.get("AI_RESEARCHER_DEMO_MODE") == "1" or not has_key
    return jsonify(
        {
            "demo_mode": demo,
            "lite_mode": config.LITE_MODE,
            "session_budget_seconds": config.WEB_SESSION_BUDGET_SECONDS,
            "confidence_threshold": config.CONFIDENCE_THRESHOLD,
            "agents": {
                aid: {
                    "display_name": m["display_name"],
                    "emoji": m.get("emoji", "🔬"),
                    "role_desc": m.get("role_desc", ""),
                    "color": m["color"],
                }
                for aid, m in config.AGENTS.items()
            },
            "locations": config.LOCATIONS,
        }
    )


@app.post("/api/run")
def api_run():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "질문이 비어있습니다."}), 400

    owner = _request_owner()
    try:
        result = _state_to_result(run_session_web(question))
    except Exception:
        app.logger.exception("연구 세션 실행 실패")
        return jsonify({"error": "연구 실행 중 서버 오류가 발생했습니다."}), 500
    result["id"] = _store_session(result, owner)
    return jsonify(result)


@app.get("/api/sessions")
def api_sessions():
    """저장된 세션의 재생 목록을 최신순으로 반환한다."""
    owner = _request_owner()
    with _session_store_lock:
        sessions = [
            {
                "id": item["id"],
                "question": item["question"],
                "confidence_score": item["confidence_score"],
                "ts": item["ts"],
            }
            for item in _session_store
            if item.get("owner") == owner
        ]
    return jsonify({"sessions": sessions})


@app.get("/api/session/<session_id>")
def api_session(session_id: str):
    """지정한 과거 세션을 /api/run과 같은 스키마로 반환한다."""
    stored = _get_stored_session(session_id)
    if stored is None:
        return jsonify({"error": "세션을 찾을 수 없습니다."}), 404

    stored.pop("owner", None)
    stored.pop("ts", None)
    return jsonify(stored)


@app.get("/api/session/<session_id>/export")
def api_session_export(session_id: str):
    """지정한 과거 세션을 마크다운 파일로 내려받는다."""
    stored = _get_stored_session(session_id)
    if stored is None:
        return jsonify({"error": "세션을 찾을 수 없습니다."}), 404

    response = Response(
        _session_to_markdown(stored),
        content_type="text/markdown; charset=utf-8",
    )
    response.headers["Content-Disposition"] = (
        f'attachment; filename="research_{session_id}.md"'
    )
    return response


@app.get("/")
def index():
    # 정적 HTML — Jinja 파싱을 피하려고 문자열을 그대로 반환한다.
    return Response(INDEX_HTML, mimetype="text/html")


INDEX_HTML = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>AI Researcher Lab</title>
<style>
  /* 픽셀 게임 폰트(한글 지원, Galmuri) — 실패해도 시스템 폰트로 폴백 */
  @import url('https://cdn.jsdelivr.net/gh/quiple/galmuri/dist/galmuri.css');
  * { box-sizing: border-box; }
  :root {
    --pixel: "Galmuri11", "Galmuri", system-ui, "Noto Sans KR", sans-serif;
    --sans: system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans KR", sans-serif;
    /* 방(연구소) 색 — 아늑한 카페 톤 */
    --floor1: #f3e9d6; --floor2: #ecdfc6; --wall: #d9c6a4; --wall2: #cdb691;
    --rug: #ffffff; --floorTint: rgba(240, 222, 186, 0.34);
  }
  :root[data-theme="dark"] {
    --floor1: #1b2233; --floor2: #171d2c; --wall: #232c40; --wall2: #1c2436;
    --rug: #202a3e; --floorTint: rgba(16, 22, 36, 0.42);
  }
  /* 기본 = 라이트 모드 */
  :root {
    color-scheme: light;
    --bg: #f6f7fb; --panel: #ffffff; --panel2: #eef1f7; --line: #e2e6ef;
    --text: #1b2230; --muted: #66707f; --accent: #4f7cff; --ok: #1f9d57;
    --field: #ffffff; --tickc: #9aa6bf;
    --g1: #e4ebff; --g2: #efe7fb;
    --map1: #eef2fb; --map2: #e7ecf6; --dot: #d5ddee;
    --answer1: #eafaf0; --answer2: #f3fbf7; --answer-line: #b7e3c8;
    --cl-bg: #ffe1ea; --cl-fg: #c2245a;
    --cm-bg: #e6ecff; --cm-fg: #3a5bd0;
    --ch-bg: #dcf5e8; --ch-fg: #1f7a4d;
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --bg: #0b0e14; --panel: #141924; --panel2: #1b2130; --line: #262d3d;
    --text: #e9edf5; --muted: #8b93a7; --accent: #5b8cff; --ok: #2fbf71;
    --field: #0f1420; --tickc: #cdd6ea;
    --g1: #1a2740; --g2: #23183a;
    --map1: #0f1626; --map2: #0b0f18; --dot: #1a2540;
    --answer1: #10241a; --answer2: #0e1a15; --answer-line: #1f6d3f;
    --cl-bg: #3a2530; --cl-fg: #ff9db5;
    --cm-bg: #2a2f45; --cm-fg: #9fb2ff;
    --ch-bg: #14342a; --ch-fg: #66e0a3;
  }
  html, body { margin: 0; }
  body {
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans KR", sans-serif;
    color: var(--text); line-height: 1.55;
    background:
      radial-gradient(1100px 500px at 80% -10%, var(--g1) 0%, transparent 60%),
      radial-gradient(900px 500px at -10% 10%, var(--g2) 0%, transparent 55%),
      var(--bg);
    background-attachment: fixed;
    min-height: 100vh;
  }
  /* 게임 UI 요소는 픽셀 폰트, 본문/답변은 가독 폰트 유지 */
  header h1, .badge, .theme-btn, button, .ghost-btn,
  .card .nm, .card .rl, .pix-bubble,
  .round-head, .gauge .lbl, .gauge .val, .examples, .history-row {
    font-family: var(--pixel);
  }
  .wrap { max-width: 960px; margin: 0 auto; padding: 22px 18px 60px; }
  /* ---- 반응형 (모바일/태블릿) ---- */
  @media (max-width: 680px) {
    .wrap { padding: 14px 12px 48px; }
    header h1 { font-size: 18px; }
    header p { font-size: 12.5px; }
    form { flex-wrap: wrap; }
    form #q { flex: 1 1 100%; }
    form button { flex: 1 1 100%; }
    .roster { gap: 8px; }
    .card { width: 92px; padding: 10px 8px; }
    .examples { line-height: 1.9; }
  }
  @media (max-width: 400px) {
    .card { width: 82px; }
    .theme-btn, #soundBtn { padding: 6px 9px; font-size: 12px; }
  }
  header h1 { margin: 0; font-size: 22px; letter-spacing: -.3px; }
  header p { margin: 6px 0 0; color: var(--muted); font-size: 13.5px; }
  .badge {
    display: inline-flex; align-items: center; gap: 5px; font-size: 12px;
    padding: 3px 10px; border-radius: 999px; margin-left: 8px; vertical-align: middle;
    background: var(--panel2); color: var(--muted); border: 1px solid var(--line);
  }
  .badge .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); }
  .badge.live .dot { background: var(--ok); box-shadow: 0 0 8px var(--ok); }
  header .top { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
  .theme-btn {
    flex: 0 0 auto; padding: 8px 12px; border-radius: 999px; border: 1px solid var(--line);
    background: var(--panel); color: var(--text); font-size: 13px; font-weight: 600; cursor: pointer;
    line-height: 1;
  }
  .theme-btn:hover { border-color: var(--accent); }

  /* 연구팀 로스터 */
  .roster { display: flex; gap: 10px; margin: 18px 0 8px; overflow-x: auto; padding-bottom: 4px; }
  .card {
    flex: 0 0 auto; width: 108px; padding: 12px 10px; border-radius: 14px;
    background: linear-gradient(180deg, var(--panel), var(--panel2));
    border: 1px solid var(--line); text-align: center;
    transition: transform .18s, box-shadow .18s, border-color .18s;
  }
  .card.active { transform: translateY(-3px); }
  .card .av {
    width: 42px; height: 42px; border-radius: 12px; margin: 0 auto 7px;
    display: grid; place-items: center; font-size: 22px;
    background: var(--panel2); border: 2px solid var(--line);
  }
  .card .nm { font-size: 13px; font-weight: 700; }
  .card .rl { font-size: 11px; color: var(--muted); margin-top: 2px; }

  /* 입력 */
  form { display: flex; gap: 8px; margin: 16px 0 8px; }
  input[type=text] {
    flex: 1; padding: 13px 15px; border-radius: 12px; border: 1px solid var(--line);
    background: var(--field); color: var(--text); font-size: 15px; outline: none;
  }
  input[type=text]:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(91,140,255,.18); }
  button {
    padding: 13px 20px; border-radius: 12px; border: 0; font-size: 15px; font-weight: 700;
    background: linear-gradient(180deg, #6b97ff, #4f7cff); color: #fff; cursor: pointer;
  }
  button:disabled { opacity: .5; cursor: default; }
  .examples { font-size: 13px; color: var(--muted); }
  .examples a { color: var(--accent); cursor: pointer; text-decoration: none; margin-right: 14px; }
  .examples a:hover { text-decoration: underline; }

  /* 지난 연구 다시보기 */
  .history-row { display: flex; align-items: center; gap: 8px; margin: 12px 0 2px; flex-wrap: wrap; }
  .history-row .hist-lbl { font-size: 13px; color: var(--muted); font-weight: 600; }
  .history-row select {
    flex: 1; min-width: 180px; padding: 9px 11px; border-radius: 10px;
    border: 1px solid var(--line); background: var(--field); color: var(--text); font-size: 14px;
  }
  .ghost-btn {
    padding: 9px 14px; border-radius: 10px; border: 1px solid var(--line);
    background: var(--panel); color: var(--text); font-size: 14px; font-weight: 600; cursor: pointer;
  }
  .ghost-btn:hover { border-color: var(--accent); color: var(--accent); }
  .answer-actions { display: flex; align-items: center; gap: 8px; margin: 10px 0 0; flex-wrap: wrap; }
  .warn {
    margin: 16px 0 0; padding: 10px 14px; border-radius: 12px; font-size: 13px;
    background: var(--cl-bg); color: var(--cl-fg); border: 1px solid var(--cl-fg);
  }

  /* 신뢰도 게이지 */
  .gauge { margin: 18px 0 6px; display: none; }
  .gauge .top { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
  .gauge .lbl { font-size: 12px; color: var(--muted); letter-spacing: .3px; }
  .gauge .val { font-size: 15px; font-weight: 800; }
  .track { position: relative; height: 12px; border-radius: 999px; background: var(--field); border: 1px solid var(--line); overflow: hidden; }
  .fill { height: 100%; width: 0%; border-radius: 999px;
          background: linear-gradient(90deg, #ff6b6b, #ffcf5c 55%, #2fbf71); transition: width .6s cubic-bezier(.2,.8,.2,1); }
  .tick { position: absolute; top: -3px; bottom: -3px; width: 2px; background: var(--tickc); opacity: .7; }
  .tick::after { content: "목표"; position: absolute; top: -16px; left: -8px; font-size: 9px; color: var(--muted); }

  /* ===== 연구소(픽셀아트 방 · Canvas 렌더 · 에셋: Pixel Agents MIT) ===== */
  .stage-wrap {
    position: relative; margin: 16px auto 4px; width: 100%;
    display: flex; justify-content: center;
  }
  #stage {
    display: block;
    image-rendering: pixelated; image-rendering: crisp-edges;
    border: 3px solid var(--wall2); border-radius: 10px;
    background: var(--floor1);
    box-shadow: 0 8px 24px rgba(0,0,0,.14);
  }
  :root[data-theme="dark"] #stage { box-shadow: 0 8px 24px rgba(0,0,0,.5); }
  /* 말풍선 오버레이 레이어(캔버스와 동일 박스, JS가 크기 지정) */
  #bubbleLayer {
    position: absolute; left: 50%; top: 0; transform: translateX(-50%);
    pointer-events: none; overflow: visible;
  }
  /* 머리 위 말풍선 (픽셀 카툰풍: 하드 섀도, Galmuri) */
  .pix-bubble {
    position: absolute; transform: translate(-50%, -100%);
    width: max-content; max-width: 220px; text-align: left;
    background: var(--panel); color: var(--text); border: 2px solid var(--text);
    border-radius: 10px; padding: 6px 9px; font-size: 11px; line-height: 1.5;
    box-shadow: 3px 3px 0 rgba(0,0,0,.18); z-index: 9; pointer-events: none;
    animation: bpop .18s steps(2);
  }
  .pix-bubble::after {
    content: ""; position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
    border: 6px solid transparent; border-top-color: var(--text);
  }
  .pix-bubble .stext.typing::after {
    content: "▋"; margin-left: 1px; color: var(--accent);
    animation: caret .7s steps(1) infinite;
  }
  @keyframes bpop { from { opacity: 0; transform: translate(-50%, calc(-100% + 6px)); } }

  /* 라운드 + 말풍선 */
  .round-head {
    display: flex; align-items: center; gap: 8px; margin: 20px 0 8px; font-size: 12px; color: var(--muted);
    opacity: 0; transform: translateY(6px); animation: rise .4s forwards;
  }
  .round-head .rn { background: var(--panel2); border: 1px solid var(--line); border-radius: 999px; padding: 2px 9px; font-weight: 700; color: var(--text); }
  .round-head .loc { background: var(--field); border: 1px solid var(--line); border-radius: 999px; padding: 2px 9px; }
  .msg { display: flex; gap: 10px; margin: 10px 0; opacity: 0; transform: translateY(8px); animation: rise .42s forwards; }
  .msg .av { flex: 0 0 auto; width: 38px; height: 38px; border-radius: 11px; display: grid; place-items: center; font-size: 19px; color: #fff; }
  .msg .body { flex: 1; }
  .bubble2 {
    display: inline-block; padding: 9px 13px; border-radius: 4px 14px 14px 14px;
    background: var(--panel); border: 1px solid var(--line); max-width: 100%;
    min-height: 1.55em;
  }
  .bubble2.typing::after {
    content: "▋"; margin-left: 1px; color: var(--accent);
    animation: caret .7s steps(1) infinite;
  }
  @keyframes caret { 50% { opacity: 0; } }
  .topic {
    margin: 16px 0 4px; padding: 9px 13px; border-radius: 10px; font-size: 13px;
    background: var(--field); border: 1px dashed var(--line); color: var(--muted);
  }
  .topic b { color: var(--text); font-weight: 700; }
  .msg .who { font-size: 12.5px; font-weight: 800; margin-bottom: 3px; display: flex; align-items: center; gap: 7px; }
  .conf { font-size: 10.5px; font-weight: 600; padding: 1px 7px; border-radius: 999px; }
  .conf.low { background: var(--cl-bg); color: var(--cl-fg); }
  .conf.medium { background: var(--cm-bg); color: var(--cm-fg); }
  .conf.high { background: var(--ch-bg); color: var(--ch-fg); }
  @keyframes rise { to { opacity: 1; transform: translateY(0); } }

  #answer { margin-top: 24px; padding: 18px 20px; border-radius: 16px; display: none;
            background: linear-gradient(180deg, var(--answer1), var(--answer2)); border: 1px solid var(--answer-line); white-space: pre-wrap; }
  #answer h3 { margin: 0 0 10px; font-size: 16px; }
  .muted { color: var(--muted); }

  .spinner { display: none; align-items: center; gap: 10px; margin: 18px 0; color: var(--muted); font-size: 14px; }
  .spinner .d { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); animation: blink 1s infinite; }
  .spinner .d:nth-child(2) { animation-delay: .2s; }
  .spinner .d:nth-child(3) { animation-delay: .4s; }
  @keyframes blink { 0%,100% { opacity: .25; } 50% { opacity: 1; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="top">
      <h1>🔬 AI Researcher Lab <span id="mode" class="badge"><span class="dot"></span><span id="modeTxt">…</span></span></h1>
      <div style="display:flex;gap:8px;flex:0 0 auto">
        <button id="soundBtn" class="theme-btn" type="button" title="사운드 토글">🔇 소리</button>
        <button id="themeBtn" class="theme-btn" type="button" title="테마 전환">🌙 다크</button>
      </div>
    </div>
    <p>전문화된 AI 연구원들이 연구소에서 만나 대화하고 반박하며 답을 정제합니다.</p>
  </header>

  <div id="roster" class="roster"></div>

  <form id="f">
    <input id="q" type="text" placeholder="질문을 입력하거나 아래 예시를 골라보세요" autocomplete="off" />
    <button id="go" type="submit">🚀 연구 시작</button>
  </form>
  <div class="examples">
    예시: <span id="exampleLinks"></span>
  </div>

  <div id="historyRow" class="history-row" style="display:none">
    <span class="hist-lbl">📁 지난 연구</span>
    <select id="history"><option value="">— 다시 볼 연구를 선택 —</option></select>
    <button id="replayBtn" class="ghost-btn" type="button">▶ 다시보기</button>
  </div>

  <div id="gauge" class="gauge">
    <div class="top"><span class="lbl">🔎 검토 진행도</span><span class="val"><span id="cval">0</span>/100</span></div>
    <div class="track"><div id="fill" class="fill"></div><div id="tick" class="tick"></div></div>
  </div>

  <div id="stageWrap" class="stage-wrap">
    <canvas id="stage" width="512" height="320"></canvas>
    <div id="bubbleLayer"></div>
  </div>

  <div id="spin" class="spinner"><span class="d"></span><span class="d"></span><span class="d"></span> 연구원들이 대화 중…</div>
  <div id="thread"></div>
  <div id="warnBadge" class="warn" style="display:none"></div>
  <div id="answer"></div>
  <div id="answerActions" class="answer-actions" style="display:none">
    <button id="exportBtn" class="ghost-btn" type="button">⬇ 마크다운 저장</button>
    <button id="shareBtn" class="ghost-btn" type="button">🔗 공유 링크 복사</button>
    <span id="shareMsg" class="muted" style="font-size:12px"></span>
  </div>
</div>

<script src="/static/js/pixel-office.js"></script>
<script>
let META = { agents: {}, locations: {}, demo_mode: false, confidence_threshold: 85 };
const CONF_KR = { low: "확신 낮음", medium: "확신 중간", high: "확신 높음" };

function esc(s) {
  return (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function agentMeta(id) {
  return META.agents[id] || { display_name: id, emoji: "🔬", role_desc: "", color: "#777" };
}
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

// 실패 메시지(원시 Gemini 오류 등)를 사용자용 짧은 문구로 치환
function displayMessage(msg) {
  if (!msg) return "…";
  if (!/^\((Gemini 오류|빈 응답|최종 답변 생성 중 오류)/.test(msg)) return msg;
  if (/RESOURCE_EXHAUSTED|(^|\D)429(\D|$)/.test(msg))
    return "⚠️ 오늘 무료 호출 한도를 다 써서 잠시 쉬는 중이에요.";
  return "⚠️ 잠깐 응답을 못 받았어요.";
}

// 백엔드 계산 대기 동안 연구원들이 돌아가며 '생각 중'을 띄워 정적으로 안 보이게
let _thinkTimer = null;
const _THINK = ["음… 이건 어떻게 접근하지?", "자료를 좀 찾아볼까요?", "관점이 여러 개네요.", "잠깐 정리해볼게요.", "🤔 흠…"];
function startThinking() {
  if (!window.PixelOffice) return;
  stopThinking();
  const ids = Object.keys(META.agents);
  if (!ids.length) return;
  let k = 0;
  const tick = () => {
    const id = ids[k % ids.length];
    try {
      if (PixelOffice.setSpeaking) PixelOffice.setSpeaking(id);
      const s = PixelOffice.showSpeech(id);
      if (s) s.textContent = _THINK[k % _THINK.length];
    } catch (e) {}
    k++;
  };
  tick();
  _thinkTimer = setInterval(tick, 1500);
}
function stopThinking() {
  if (_thinkTimer) { clearInterval(_thinkTimer); _thinkTimer = null; }
  if (window.PixelOffice) {
    try { if (PixelOffice.clearSpeaking) PixelOffice.clearSpeaking(); } catch (e) {}
    try { if (PixelOffice.clearSpeech) PixelOffice.clearSpeech(); } catch (e) {}
  }
}

// 말풍선 텍스트를 한 글자씩 타이핑 (textContent라 XSS 안전)
async function typeInto(el, text) {
  el.textContent = "";
  el.classList.add("typing");
  for (let i = 0; i < text.length; i++) {
    el.textContent += text[i];
    if (i % 2 === 0) await sleep(14);
  }
  el.classList.remove("typing");
}

async function loadMeta() {
  try {
    META = await (await fetch("/api/meta")).json();
  } catch (e) {}
  const b = document.getElementById("mode");
  const live = !META.demo_mode;
  b.className = "badge" + (live ? " live" : "");
  document.getElementById("modeTxt").textContent = live ? "실시간" : "데모 모드";
  renderRoster();
  await PixelOffice.init(META);
  // 게이지 목표선
  const t = META.confidence_threshold || 85;
  document.getElementById("tick").style.left = t + "%";
}

function renderRoster() {
  const el = document.getElementById("roster");
  el.innerHTML = "";
  for (const id of Object.keys(META.agents)) {
    const m = META.agents[id];
    const card = document.createElement("div");
    card.className = "card";
    card.dataset.agent = id;
    card.style.setProperty("--c", m.color);
    card.innerHTML =
      '<div class="av" style="border-color:' + m.color + ';color:' + m.color + '">' + (m.emoji || "🔬") + "</div>" +
      '<div class="nm">' + esc(m.display_name) + "</div>" +
      '<div class="rl">' + esc(m.role_desc || "") + "</div>";
    el.appendChild(card);
  }
}
function pulseCard(id) {
  document.querySelectorAll(".card").forEach((c) => {
    const on = c.dataset.agent === id;
    c.classList.toggle("active", on);
    if (on) { c.style.boxShadow = "0 0 0 2px " + (META.agents[id] || {}).color; }
    else { c.style.boxShadow = "none"; }
  });
}

function setGauge(v) {
  v = Math.max(0, Math.min(100, Math.round(v)));
  document.getElementById("fill").style.width = v + "%";
  document.getElementById("cval").textContent = v;
}

// ---- 시각화는 static/js/pixel-office.js(캔버스 엔진)로 이관. reveal()이 그 API를 호출. ----

function msgEl(u) {
  const m = agentMeta(u.agent);
  const loc = (META.locations && META.locations[u.location]) || "";
  const conf = u.confidence || "medium";
  const el = document.createElement("div");
  el.className = "msg";
  el.innerHTML =
    '<div class="av" style="background:' + m.color + '">' + (m.emoji || "🔬") + "</div>" +
    '<div class="body">' +
      '<div class="who" style="color:' + m.color + '">' + esc(m.display_name) +
        (loc ? ' <span class="muted" style="font-weight:500">@ ' + esc(loc) + "</span>" : "") +
        ' <span class="conf ' + conf + '">' + (CONF_KR[conf] || "") + "</span>" +
      "</div>" +
      '<div class="bubble2"></div>' +  /* 텍스트는 타이핑 효과로 채운다 */
    "</div>";
  return el;
}

// 라운드 경계: responds_to가 null인 발언에서 새 라운드 시작
function groupRounds(history) {
  const rounds = [];
  for (const u of history) {
    if (u.responds_to == null || rounds.length === 0) rounds.push([u]);
    else rounds[rounds.length - 1].push(u);
  }
  return rounds;
}

async function reveal(data) {
  const thread = document.getElementById("thread");
  thread.innerHTML = "";
  const gauge = document.getElementById("gauge");
  gauge.style.display = "block";
  setGauge(20);

  // 연구 주제 배너
  const topic = document.createElement("div");
  topic.className = "topic";
  topic.innerHTML = "🧪 연구 주제 · <b>" + esc(data.question || "") + "</b>";
  thread.appendChild(topic);

  // 캔버스 엔진이 준비되면 전원 자리로 초기화(sit)
  if (window.PixelOffice) { try { await PixelOffice.ready; } catch (e) {} PixelOffice.reset(); }

  // 라운드/인카운터 재구성: history를 responds_to==null 경계로 그룹핑(백엔드 스키마 그대로)
  const rounds = groupRounds(data.history || []);
  const encounters = (data.orchestrator_log || []).filter((e) => e.action === "encounter");

  for (let i = 0; i < rounds.length; i++) {
    const enc = encounters[i] || {};
    const grp = rounds[i];
    const locId = grp[0] && grp[0].location;
    const locName = (META.locations && META.locations[locId]) || locId || "";
    const participants = [];
    grp.forEach((u) => { if (!participants.includes(u.agent)) participants.push(u.agent); });

    const head = document.createElement("div");
    head.className = "round-head";
    head.innerHTML =
      '<span class="rn">라운드 ' + (i + 1) + "</span>" +
      (locName ? '<span class="loc">' + esc(locName) + "</span>" : "");
    thread.appendChild(head);
    head.scrollIntoView({ block: "nearest", behavior: "smooth" });

    // 두 에이전트가 자리에서 일어나 장소로 BFS 이동 → 마주봄
    if (window.PixelOffice) await PixelOffice.encounter(participants, locId);
    if (typeof enc.confidence_after === "number") setGauge(enc.confidence_after);

    for (const u of grp) {
      pulseCard(u.agent);
      if (window.PixelOffice) PixelOffice.setSpeaking(u.agent);
      const el = msgEl(u);
      thread.appendChild(el);
      el.scrollIntoView({ block: "end", behavior: "smooth" });
      await sleep(120);
      // 캔버스 말풍선에 타이핑, 아래 스레드에는 전문을 즉시 기록(로그)
      const speech = window.PixelOffice ? PixelOffice.showSpeech(u.agent) : null;
      const threadBubble = el.querySelector(".bubble2");
      const shown = displayMessage(u.message);
      if (speech) {
        await typeInto(speech, shown);
        threadBubble.textContent = shown;
      } else {
        await typeInto(threadBubble, shown);
      }
      await sleep(500);
    }
    // 인카운터 종료: 참가자들이 각자 자리로 복귀(sit)
    if (window.PixelOffice) await PixelOffice.endEncounter(participants);
  }

  pulseCard(null);
  // 조율자가 화이트보드 앞으로 나와 최종 정리(read)
  if (window.PixelOffice) {
    await PixelOffice.finalize();
    PixelOffice.setSpeaking("synthesizer");
    const sSpeech = PixelOffice.showSpeech("synthesizer");
    if (sSpeech) await typeInto(sSpeech, "제가 종합해서 정리해볼게요!");
  }
  setGauge(data.confidence_score);
  await sleep(300);

  // 일부 응답 실패 경고 (data.has_errors/status는 백엔드가 채움)
  const warn = document.getElementById("warnBadge");
  const hasErr = data.has_errors === true || (data.status && data.status !== "ok");
  if (hasErr) {
    warn.textContent = "⚠️ 일부 에이전트 응답이 실패했습니다. 이 결과는 불완전할 수 있어요.";
    warn.style.display = "block";
  } else {
    warn.style.display = "none";
  }

  const answer = document.getElementById("answer");
  const synth = agentMeta("synthesizer");
  answer.innerHTML =
    "<h3>" + (synth.emoji || "🧩") + " 최종 답변 " +
    '<span class="muted" style="font-size:13px;font-weight:500">(검토 진행도 ' +
    data.confidence_score + "/100)</span></h3>" + esc(displayMessage(data.final_answer || ""));
  answer.style.display = "block";
  answer.scrollIntoView({ block: "nearest", behavior: "smooth" });
}


async function run(question) {
  const go = document.getElementById("go");
  const spin = document.getElementById("spin");
  document.getElementById("thread").innerHTML = "";
  document.getElementById("answer").style.display = "none";
  go.disabled = true;
  spin.style.display = "flex";
  if (window.PixelOffice && PixelOffice.setBusy) PixelOffice.setBusy(true);  // 상시활동 정지
  startThinking();  // 대기 동안 연구원들이 '생각 중'
  try {
    const res = await fetch("/api/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "요청 실패");
    stopThinking();
    spin.style.display = "none";
    await reveal(data);
    setActions(data.id);  // data.id는 백엔드가 채움(없으면 버튼 숨김)
  } catch (e) {
    stopThinking();
    spin.style.display = "none";
    hideActions();
    const answer = document.getElementById("answer");
    answer.innerHTML = "<h3>⚠️ 오류</h3>" + esc(e.message);
    answer.style.display = "block";
  } finally {
    go.disabled = false;
    if (window.PixelOffice && PixelOffice.setBusy) PixelOffice.setBusy(false);  // 상시활동 재개
    loadHistory();  // 방금 실행한 연구를 목록에 반영
  }
}

// ---- 내보내기 / 공유 (id가 있을 때만 노출) ----
// 계약(백엔드가 구현): /api/run·/api/session/<id> 응답에 id 포함,
//                     GET /api/session/<id>/export -> 마크다운 파일 다운로드
let currentSessionId = null;
function setActions(id) {
  currentSessionId = id || null;
  document.getElementById("answerActions").style.display = id ? "flex" : "none";
  document.getElementById("shareMsg").textContent = "";
}
function hideActions() { setActions(null); }
(function wireActions() {
  const exp = document.getElementById("exportBtn");
  const sh = document.getElementById("shareBtn");
  if (exp) exp.addEventListener("click", () => {
    if (currentSessionId) window.open("/api/session/" + encodeURIComponent(currentSessionId) + "/export", "_blank");
  });
  if (sh) sh.addEventListener("click", async () => {
    if (!currentSessionId) return;
    const url = location.origin + "/?session=" + encodeURIComponent(currentSessionId);
    try { await navigator.clipboard.writeText(url); document.getElementById("shareMsg").textContent = "복사됨 ✓"; }
    catch (e) { document.getElementById("shareMsg").textContent = url; }
  });
})();

// ---- 지난 연구 다시보기 ----
// 계약(백엔드가 구현): GET /api/sessions -> {sessions:[{id,question,confidence_score,ts}]}
//                     GET /api/session/<id> -> /api/run 과 동일 스키마
async function loadHistory() {
  try {
    const r = await fetch("/api/sessions");
    if (!r.ok) return;
    const d = await r.json();
    const list = (d && (d.sessions || (Array.isArray(d) ? d : []))) || [];
    const sel = document.getElementById("history");
    const row = document.getElementById("historyRow");
    if (!Array.isArray(list) || list.length === 0) { row.style.display = "none"; return; }
    sel.innerHTML = '<option value="">— 다시 볼 연구를 선택 —</option>';
    list.forEach((s) => {
      const o = document.createElement("option");
      o.value = s.id;
      const c = (typeof s.confidence_score === "number") ? " · 진행도 " + s.confidence_score : "";
      const q = (s.question || "(제목 없음)");
      o.textContent = (q.length > 42 ? q.slice(0, 42) + "…" : q) + c;
      sel.appendChild(o);
    });
    row.style.display = "flex";
  } catch (e) {}
}
async function replaySelected(id) {
  id = (typeof id === "string" && id) ? id : document.getElementById("history").value;
  if (!id) return;
  try {
    const r = await fetch("/api/session/" + encodeURIComponent(id));
    if (!r.ok) throw new Error("세션을 불러오지 못했습니다.");
    const data = await r.json();
    document.getElementById("answer").style.display = "none";
    hideActions();
    await reveal(data);
    setActions(data.id || id);
  } catch (e) {
    hideActions();
    const a = document.getElementById("answer");
    a.innerHTML = "<h3>⚠️ 오류</h3>" + esc(e.message);
    a.style.display = "block";
  }
}
document.getElementById("replayBtn").addEventListener("click", replaySelected);
document.getElementById("history").addEventListener("change", replaySelected);

document.getElementById("f").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = document.getElementById("q").value.trim();
  if (q) run(q);
});
const EXAMPLE_QUESTIONS = [
  { label: "오늘 저녁 메뉴", q: "오늘 저녁, 배달 말고 30분 안에 만들 수 있는 메뉴를 추천해줘" },
  { label: "한 달 취미", q: "한 달 동안 꾸준히 할 수 있는 재미있는 취미를 추천해줘" },
  { label: "주말 모험", q: "이번 주말을 특별하게 보낼 수 있는 혼자만의 작은 모험을 계획해줘" },
  { label: "퇴근 후 운동", q: "퇴근 후 30분만 투자하는 지루하지 않은 운동 루틴을 만들어줘" },
  { label: "만원의 행복", q: "만원으로 친구를 기분 좋게 해줄 수 있는 선물 아이디어는?" },
  { label: "집중력 실험", q: "자꾸 딴짓하게 될 때 집중력을 되찾는 재미있는 방법은?" },
  { label: "AI 사이드 프로젝트", q: "주말 이틀 안에 완성할 수 있는 엉뚱한 AI 사이드 프로젝트를 추천해줘" },
  { label: "반려식물 입문", q: "식물을 자주 죽이는 사람도 키울 수 있는 반려식물과 관리법은?" },
  { label: "독서 습관", q: "책을 끝까지 못 읽는 사람이 독서 습관을 만드는 현실적인 방법은?" },
  { label: "회의 다이어트", q: "팀 회의를 절반으로 줄이면서 소통은 더 좋아지게 만들 수 있을까?" },
  { label: "비 오는 날", q: "비 오는 날 집에서 영화 말고 재미있게 할 수 있는 것은?" },
  { label: "새로운 친구", q: "낯가림이 심한 사람이 자연스럽게 새로운 친구를 만드는 방법은?" },
];

function initRandomExamples() {
  const shuffled = [...EXAMPLE_QUESTIONS];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }

  let previous = "";
  try { previous = localStorage.getItem("lastExamples") || ""; } catch (e) {}
  let selected = shuffled.slice(0, 3);
  for (let offset = 0; offset < shuffled.length; offset++) {
    const rotated = shuffled.slice(offset).concat(shuffled.slice(0, offset));
    const candidate = rotated.slice(0, 3);
    if (candidate.map((item) => item.q).join("|") !== previous) {
      selected = candidate;
      break;
    }
  }

  const signature = selected.map((item) => item.q).join("|");
  try { localStorage.setItem("lastExamples", signature); } catch (e) {}

  const links = document.getElementById("exampleLinks");
  selected.forEach((item) => {
    const anchor = document.createElement("a");
    anchor.textContent = item.label;
    anchor.dataset.q = item.q;
    anchor.addEventListener("click", () => {
      document.getElementById("q").value = item.q;
      run(item.q);
    });
    links.appendChild(anchor);
  });
  document.getElementById("q").placeholder = "예: " + selected[0].q;
}
initRandomExamples();
// ---- 테마 (기본: 라이트, localStorage 저장) ----
function applyTheme(theme) {
  const dark = theme === "dark";
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  if (window.PixelOffice) PixelOffice.onThemeChange();
  const btn = document.getElementById("themeBtn");
  if (btn) btn.textContent = dark ? "☀️ 라이트" : "🌙 다크";
}
(function initTheme() {
  let saved = "light";
  try { saved = localStorage.getItem("theme") || "light"; } catch (e) {}
  applyTheme(saved);
  const btn = document.getElementById("themeBtn");
  if (btn) btn.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    try { localStorage.setItem("theme", next); } catch (e) {}
    applyTheme(next);
  });
})();

loadMeta();
loadHistory();
// 공유 링크(?session=<id>)로 들어오면 해당 세션을 바로 재생
(function initShared() {
  try {
    const id = new URLSearchParams(location.search).get("session");
    if (id) replaySelected(id);
  } catch (e) {}
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
