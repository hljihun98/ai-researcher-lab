"""
AI Researcher Lab — 웹 서버 (Phase 1.5).

CLI 백엔드를 Flask 웹앱으로 감싼다. 브라우저에서 질문을 입력하면
에이전트들이 대화한 로그와 최종 답변을 화면에 표시한다.

실행(로컬):
    python server.py            # http://localhost:8000

배포(Render web 서비스):
    gunicorn server:app --bind 0.0.0.0:$PORT --timeout 120

환경변수:
    ANTHROPIC_API_KEY      실제 모델로 대화 (설정 시)
    AI_RESEARCHER_DEMO_MODE=1  API 키 없이 캔드 응답으로 시연 (배포 기본값)
"""
import os

from flask import Flask, jsonify, render_template_string, request

import config
from agents import build_agents
from conversation import ConversationState
from main import build_runtime_client
from orchestrator import Orchestrator

app = Flask(__name__)

# 한 요청이 무한히 돌지 않도록 상한 (max_turns 안전장치와 별개의 웹 방어선)
MAX_ROUNDS = 30


def run_session_web(question: str) -> ConversationState:
    """CLI의 run_session과 같은 흐름이지만 출력 없이 state를 반환한다."""
    client = build_runtime_client()
    agents_map = build_agents(client)
    orchestrator = Orchestrator(client)
    state = ConversationState(question=question)

    rounds = 0
    while not state.should_finalize() and rounds < MAX_ROUNDS:
        rounds += 1
        decision = orchestrator.decide(state)
        if decision.get("action") == "finalize":
            break
        if decision.get("action") == "encounter":
            try:
                a1_id, a2_id = decision["agents"]
                loc = decision.get("location")
                agents_map[a1_id].speak(state, location=loc, responds_to=None)
                agents_map[a2_id].speak(state, location=loc, responds_to=a1_id)
                if config.ENCOUNTER_MAX_EXCHANGES >= 3:
                    agents_map[a1_id].speak(state, location=loc, responds_to=a2_id)
            except Exception:
                # 개별 인카운터 실패는 세션 전체를 죽이지 않는다.
                pass

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
    demo = os.environ.get("AI_RESEARCHER_DEMO_MODE") == "1" or not os.environ.get(
        "ANTHROPIC_API_KEY"
    )
    return jsonify(
        {
            "demo_mode": demo,
            "agents": {
                aid: {"display_name": m["display_name"], "color": m["color"]}
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

    state = run_session_web(question)
    return jsonify(
        {
            "question": state.question,
            "confidence_score": state.confidence_score,
            "final_answer": state.final_answer,
            "history": [
                {
                    "agent": u.agent,
                    "message": u.message,
                    "confidence": u.confidence,
                    "location": u.location,
                    "turn": u.turn,
                }
                for u in state.history
            ],
        }
    )


@app.get("/")
def index():
    return render_template_string(INDEX_HTML)


INDEX_HTML = r"""
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>AI Researcher Lab</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    background: #0f1115; color: #e8e8ea; line-height: 1.5;
  }
  header { padding: 24px 20px 12px; border-bottom: 1px solid #23262d; }
  h1 { margin: 0; font-size: 20px; }
  header p { margin: 6px 0 0; color: #9aa0aa; font-size: 13px; }
  .wrap { max-width: 760px; margin: 0 auto; padding: 20px; }
  form { display: flex; gap: 8px; margin-bottom: 8px; }
  input[type=text] {
    flex: 1; padding: 12px 14px; border-radius: 10px; border: 1px solid #2c313a;
    background: #171a20; color: #e8e8ea; font-size: 15px;
  }
  button {
    padding: 12px 18px; border-radius: 10px; border: 0; font-size: 15px; font-weight: 600;
    background: #4f7cff; color: white; cursor: pointer;
  }
  button:disabled { opacity: .5; cursor: default; }
  .badge { display: inline-block; font-size: 12px; padding: 2px 8px; border-radius: 999px;
           background: #2a2f3a; color: #b9c0cc; margin-left: 8px; }
  .bubble {
    margin: 10px 0; padding: 10px 14px; border-radius: 12px; background: #171a20;
    border-left: 4px solid #555; max-width: 88%;
  }
  .bubble .who { font-size: 12px; font-weight: 700; margin-bottom: 2px; }
  .bubble .loc { font-size: 11px; color: #8a909a; font-weight: 400; }
  .conf { font-size: 11px; color: #8a909a; margin-left: 6px; }
  #answer {
    margin-top: 20px; padding: 16px 18px; border-radius: 12px;
    background: #14261c; border: 1px solid #1f6d3f; white-space: pre-wrap;
  }
  #answer h3 { margin: 0 0 8px; font-size: 15px; }
  .muted { color: #8a909a; font-size: 13px; }
  .spinner { display: none; margin: 16px 0; color: #9aa0aa; }
  .examples { margin: 4px 0 0; font-size: 13px; }
  .examples a { color: #7fa2ff; cursor: pointer; text-decoration: none; margin-right: 12px; }
</style>
</head>
<body>
<header>
  <div class="wrap" style="padding-bottom:0">
    <h1>🔬 AI Researcher Lab <span id="mode" class="badge"></span></h1>
    <p>5명의 AI 연구원이 서로 대화하며 답을 정제합니다. 질문을 던져보세요.</p>
  </div>
</header>
<div class="wrap">
  <form id="f">
    <input id="q" type="text" placeholder="예: 소규모 스타트업에 가장 적합한 RAG 아키텍처는?" autocomplete="off" />
    <button id="go" type="submit">실행</button>
  </form>
  <div class="examples muted">
    예시:
    <a data-q="소규모 스타트업에 가장 적합한 RAG 아키텍처는?">RAG 아키텍처</a>
    <a data-q="주니어 개발자가 처음 배우기 좋은 언어는?">첫 언어 추천</a>
  </div>
  <div id="spin" class="spinner">🤖 연구원들이 대화 중…</div>
  <div id="log"></div>
  <div id="answer" style="display:none"></div>
</div>
<script>
let META = { agents: {}, locations: {}, demo_mode: false };

async function loadMeta() {
  try {
    META = await (await fetch("/api/meta")).json();
    const m = document.getElementById("mode");
    m.textContent = META.demo_mode ? "데모 모드" : "실시간";
  } catch (e) {}
}

function bubble(u) {
  const meta = META.agents[u.agent] || { display_name: u.agent, color: "#777" };
  const loc = (META.locations && META.locations[u.location]) || u.location || "";
  const confMark = { low: "확신 낮음", medium: "확신 중간", high: "확신 높음" }[u.confidence] || "";
  const div = document.createElement("div");
  div.className = "bubble";
  div.style.borderLeftColor = meta.color;
  div.innerHTML =
    '<div class="who" style="color:' + meta.color + '">' +
    escapeHtml(meta.display_name) +
    (loc ? ' <span class="loc">@ ' + escapeHtml(loc) + "</span>" : "") +
    '<span class="conf">' + confMark + "</span></div>" +
    "<div>" + escapeHtml(u.message) + "</div>";
  return div;
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

async function run(question) {
  const go = document.getElementById("go");
  const log = document.getElementById("log");
  const answer = document.getElementById("answer");
  const spin = document.getElementById("spin");
  log.innerHTML = "";
  answer.style.display = "none";
  go.disabled = true;
  spin.style.display = "block";
  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "요청 실패");
    (data.history || []).forEach((u) => log.appendChild(bubble(u)));
    answer.innerHTML =
      "<h3>✅ 최종 답변 <span class='muted'>(신뢰도 " +
      data.confidence_score + "/100)</span></h3>" +
      escapeHtml(data.final_answer || "");
    answer.style.display = "block";
  } catch (e) {
    answer.innerHTML = "<h3>⚠️ 오류</h3>" + escapeHtml(e.message);
    answer.style.display = "block";
  } finally {
    go.disabled = false;
    spin.style.display = "none";
  }
}

document.getElementById("f").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = document.getElementById("q").value.trim();
  if (q) run(q);
});
document.querySelectorAll(".examples a").forEach((a) =>
  a.addEventListener("click", () => {
    document.getElementById("q").value = a.dataset.q;
    run(a.dataset.q);
  }));
loadMeta();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
