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

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - 선택적 의존성
    pass

from flask import Flask, Response, jsonify, request

import config
from agents import build_agents
from conversation import ConversationState
from main import build_runtime_client
from orchestrator import Orchestrator

app = Flask(__name__)

# 한 요청이 무한히 돌지 않도록 상한. 무료 등급 분당 한도(5회)를 감안해 낮게 유지.
# (라운드마다 오케스트레이터 1 + 발언 2회 호출 → 라운드 4면 약 12+1회)
MAX_ROUNDS = 4


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
    has_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    demo = os.environ.get("AI_RESEARCHER_DEMO_MODE") == "1" or not has_key
    return jsonify(
        {
            "demo_mode": demo,
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

    state = run_session_web(question)
    return jsonify(
        {
            "question": state.question,
            "confidence_score": state.confidence_score,
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
            "orchestrator_log": state.orchestrator_log,
        }
    )


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
  * { box-sizing: border-box; }
  :root {
    --bg: #0b0e14; --panel: #141924; --panel2: #1b2130; --line: #262d3d;
    --text: #e9edf5; --muted: #8b93a7; --accent: #5b8cff; --ok: #2fbf71;
  }
  html, body { margin: 0; }
  body {
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans KR", sans-serif;
    color: var(--text); line-height: 1.55;
    background:
      radial-gradient(1100px 500px at 80% -10%, #1a2740 0%, transparent 60%),
      radial-gradient(900px 500px at -10% 10%, #23183a 0%, transparent 55%),
      var(--bg);
    background-attachment: fixed;
    min-height: 100vh;
  }
  .wrap { max-width: 820px; margin: 0 auto; padding: 22px 18px 60px; }
  header h1 { margin: 0; font-size: 22px; letter-spacing: -.3px; }
  header p { margin: 6px 0 0; color: var(--muted); font-size: 13.5px; }
  .badge {
    display: inline-flex; align-items: center; gap: 5px; font-size: 12px;
    padding: 3px 10px; border-radius: 999px; margin-left: 8px; vertical-align: middle;
    background: var(--panel2); color: var(--muted); border: 1px solid var(--line);
  }
  .badge .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); }
  .badge.live .dot { background: var(--ok); box-shadow: 0 0 8px var(--ok); }

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
    background: #0e131d; border: 2px solid #333;
  }
  .card .nm { font-size: 13px; font-weight: 700; }
  .card .rl { font-size: 11px; color: var(--muted); margin-top: 2px; }

  /* 입력 */
  form { display: flex; gap: 8px; margin: 16px 0 8px; }
  input[type=text] {
    flex: 1; padding: 13px 15px; border-radius: 12px; border: 1px solid var(--line);
    background: #0f1420; color: var(--text); font-size: 15px; outline: none;
  }
  input[type=text]:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(91,140,255,.18); }
  button {
    padding: 13px 20px; border-radius: 12px; border: 0; font-size: 15px; font-weight: 700;
    background: linear-gradient(180deg, #6b97ff, #4f7cff); color: #fff; cursor: pointer;
  }
  button:disabled { opacity: .5; cursor: default; }
  .examples { font-size: 13px; color: var(--muted); }
  .examples a { color: #8fb0ff; cursor: pointer; text-decoration: none; margin-right: 14px; }
  .examples a:hover { text-decoration: underline; }

  /* 신뢰도 게이지 */
  .gauge { margin: 18px 0 6px; display: none; }
  .gauge .top { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
  .gauge .lbl { font-size: 12px; color: var(--muted); letter-spacing: .3px; }
  .gauge .val { font-size: 15px; font-weight: 800; }
  .track { position: relative; height: 12px; border-radius: 999px; background: #0f1420; border: 1px solid var(--line); overflow: hidden; }
  .fill { height: 100%; width: 0%; border-radius: 999px;
          background: linear-gradient(90deg, #ff6b6b, #ffcf5c 55%, #2fbf71); transition: width .6s cubic-bezier(.2,.8,.2,1); }
  .tick { position: absolute; top: -3px; bottom: -3px; width: 2px; background: #cdd6ea; opacity: .7; }
  .tick::after { content: "목표"; position: absolute; top: -16px; left: -8px; font-size: 9px; color: var(--muted); }

  /* 연구소 맵 (에이전트가 걸어다니며 마주침) */
  .map {
    position: relative; height: 300px; margin: 16px 0 4px; border-radius: 16px; overflow: hidden;
    background: linear-gradient(180deg, #0f1626, #0b0f18);
    border: 1px solid var(--line);
    background-image: radial-gradient(circle, #1a2540 1px, transparent 1.4px);
    background-size: 24px 24px; display: none;
  }
  .loc-marker {
    position: absolute; transform: translate(-50%, -50%); text-align: center;
    font-size: 11px; color: var(--muted); pointer-events: none; transition: color .3s; width: 92px;
  }
  .loc-marker .ic { font-size: 24px; display: block; margin-bottom: 2px; filter: grayscale(.35) opacity(.7); transition: filter .3s; }
  .loc-marker.active { color: var(--text); }
  .loc-marker.active .ic { filter: none; }
  .loc-ring {
    position: absolute; transform: translate(-50%, -50%); width: 84px; height: 84px; border-radius: 50%;
    border: 2px dashed transparent; transition: border-color .3s, box-shadow .3s;
  }
  .loc-ring.active { border-color: var(--accent); box-shadow: 0 0 22px rgba(91,140,255,.35) inset; }
  .token {
    position: absolute; transform: translate(-50%, -50%); width: 48px; text-align: center; z-index: 3;
    color: #777;
    transition: left .95s cubic-bezier(.45,.05,.25,1), top .95s cubic-bezier(.45,.05,.25,1);
  }
  .token .av2 {
    width: 38px; height: 38px; margin: 0 auto; border-radius: 12px; display: grid; place-items: center;
    font-size: 20px; color: #fff; background: currentColor; box-shadow: 0 3px 8px rgba(0,0,0,.45);
    transition: box-shadow .2s;
  }
  .token .av2 span { filter: drop-shadow(0 1px 1px rgba(0,0,0,.4)); }
  .token .nm2 { font-size: 10px; margin-top: 3px; color: var(--muted); white-space: nowrap; }
  .token.walking .av2 { animation: bob .42s ease-in-out infinite; }
  .token.speaking .av2 { box-shadow: 0 0 0 3px currentColor, 0 0 16px currentColor; }
  .token.speaking .nm2 { color: var(--text); font-weight: 700; }
  @keyframes bob { 50% { transform: translateY(-5px); } }

  /* 라운드 + 말풍선 */
  .round-head {
    display: flex; align-items: center; gap: 8px; margin: 20px 0 8px; font-size: 12px; color: var(--muted);
    opacity: 0; transform: translateY(6px); animation: rise .4s forwards;
  }
  .round-head .rn { background: var(--panel2); border: 1px solid var(--line); border-radius: 999px; padding: 2px 9px; font-weight: 700; color: var(--text); }
  .round-head .loc { background: #0f1420; border: 1px solid var(--line); border-radius: 999px; padding: 2px 9px; }
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
    background: #0f1420; border: 1px dashed var(--line); color: var(--muted);
  }
  .topic b { color: var(--text); font-weight: 700; }
  .msg .who { font-size: 12.5px; font-weight: 800; margin-bottom: 3px; display: flex; align-items: center; gap: 7px; }
  .conf { font-size: 10.5px; font-weight: 600; padding: 1px 7px; border-radius: 999px; }
  .conf.low { background: #3a2530; color: #ff9db5; }
  .conf.medium { background: #2a2f45; color: #9fb2ff; }
  .conf.high { background: #14342a; color: #66e0a3; }
  @keyframes rise { to { opacity: 1; transform: translateY(0); } }

  #answer { margin-top: 24px; padding: 18px 20px; border-radius: 16px; display: none;
            background: linear-gradient(180deg, #10241a, #0e1a15); border: 1px solid #1f6d3f; white-space: pre-wrap; }
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
    <h1>🔬 AI Researcher Lab <span id="mode" class="badge"><span class="dot"></span><span id="modeTxt">…</span></span></h1>
    <p>전문화된 AI 연구원들이 연구소에서 만나 대화하고 반박하며 답을 정제합니다.</p>
  </header>

  <div id="roster" class="roster"></div>

  <form id="f">
    <input id="q" type="text" placeholder="예: 소규모 스타트업에 가장 적합한 RAG 아키텍처는?" autocomplete="off" />
    <button id="go" type="submit">🚀 연구 시작</button>
  </form>
  <div class="examples">
    예시:
    <a data-q="소규모 스타트업에 가장 적합한 RAG 아키텍처는?">RAG 아키텍처</a>
    <a data-q="주니어 개발자가 처음 배우기 좋은 언어는?">첫 언어 추천</a>
    <a data-q="원격 근무 팀의 생산성을 높이는 방법은?">원격 근무</a>
  </div>

  <div id="gauge" class="gauge">
    <div class="top"><span class="lbl">🎯 답변 신뢰도</span><span class="val"><span id="cval">0</span>/100</span></div>
    <div class="track"><div id="fill" class="fill"></div><div id="tick" class="tick"></div></div>
  </div>

  <div id="map" class="map"></div>

  <div id="spin" class="spinner"><span class="d"></span><span class="d"></span><span class="d"></span> 연구원들이 대화 중…</div>
  <div id="thread"></div>
  <div id="answer"></div>
</div>

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
  renderMap();
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

// ---- 연구소 맵 (에이전트가 장소로 걸어가 마주침) ----
const MAP_POS = {
  library:      { x: 16, y: 27 },
  whiteboard:   { x: 50, y: 20 },
  coffee:       { x: 84, y: 29 },
  server_room:  { x: 26, y: 63 },
  meeting_desk: { x: 72, y: 61 },
};
const HOME = {};

function renderMap() {
  const map = document.getElementById("map");
  if (!map) return;
  map.innerHTML = "";
  for (const id of Object.keys(MAP_POS)) {
    const p = MAP_POS[id];
    const desc = (META.locations && META.locations[id]) || id;
    const head = desc.split(" - ")[0];
    const sp = head.indexOf(" ");
    const emoji = sp > 0 ? head.slice(0, sp) : "📍";
    const label = sp > 0 ? head.slice(sp + 1) : head;
    const ring = document.createElement("div");
    ring.className = "loc-ring"; ring.dataset.loc = id;
    ring.style.left = p.x + "%"; ring.style.top = p.y + "%";
    map.appendChild(ring);
    const m = document.createElement("div");
    m.className = "loc-marker"; m.dataset.loc = id;
    m.style.left = p.x + "%"; m.style.top = p.y + "%";
    m.innerHTML = '<span class="ic">' + emoji + "</span>" + esc(label);
    map.appendChild(m);
  }
  const ids = Object.keys(META.agents);
  ids.forEach((id, i) => {
    const x = 10 + (80 * i) / Math.max(1, ids.length - 1);
    HOME[id] = { x: x, y: 90 };
    const m = META.agents[id];
    const t = document.createElement("div");
    t.className = "token"; t.dataset.agent = id;
    t.style.color = m.color;
    t.style.left = x + "%"; t.style.top = "90%";
    t.innerHTML =
      '<div class="av2"><span>' + (m.emoji || "🔬") + "</span></div>" +
      '<div class="nm2">' + esc(m.display_name) + "</div>";
    map.appendChild(t);
  });
  map.style.display = "block";
}

function tokenEl(id) { return document.querySelector('.token[data-agent="' + id + '"]'); }
function moveToken(id, x, y, walking) {
  const t = tokenEl(id); if (!t) return;
  t.classList.toggle("walking", !!walking);
  t.style.left = x + "%"; t.style.top = y + "%";
}
function setSpeaking(id) {
  document.querySelectorAll(".token").forEach((t) =>
    t.classList.toggle("speaking", t.dataset.agent === id));
}
function clearSpeaking() {
  document.querySelectorAll(".token.speaking").forEach((t) => t.classList.remove("speaking"));
}
function activateLoc(id) {
  document.querySelectorAll(".loc-marker,.loc-ring").forEach((e) =>
    e.classList.toggle("active", e.dataset.loc === id));
}
function homeAll() {
  Object.keys(META.agents).forEach((id) => {
    if (HOME[id]) moveToken(id, HOME[id].x, HOME[id].y, false);
  });
  clearSpeaking(); activateLoc(null);
}
async function gotoStation(participants, locId) {
  const p = MAP_POS[locId] || { x: 50, y: 42 };
  const offs = participants.length > 1 ? [-9, 9, -9] : [0];
  participants.forEach((id, i) => moveToken(id, p.x + (offs[i] || 0), p.y, true));
  Object.keys(META.agents).forEach((id) => {
    if (!participants.includes(id) && HOME[id]) moveToken(id, HOME[id].x, HOME[id].y, false);
  });
  activateLoc(locId);
  await sleep(1000);
  participants.forEach((id) => { const t = tokenEl(id); if (t) t.classList.remove("walking"); });
}

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

  homeAll();

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

    // 두 에이전트가 장소로 걸어간다
    await gotoStation(participants, locId);
    if (typeof enc.confidence_after === "number") setGauge(enc.confidence_after);

    for (const u of grp) {
      pulseCard(u.agent);
      setSpeaking(u.agent);
      const el = msgEl(u);
      thread.appendChild(el);
      el.scrollIntoView({ block: "end", behavior: "smooth" });
      await sleep(120);
      await typeInto(el.querySelector(".bubble2"), u.message);
      await sleep(180);
    }
    clearSpeaking();
  }

  pulseCard(null);
  // 조율자가 회의 책상으로 나와 최종 정리
  homeAll();
  const md = MAP_POS.meeting_desk;
  moveToken("synthesizer", md.x, md.y, true);
  activateLoc("meeting_desk");
  await sleep(900);
  setSpeaking("synthesizer");
  const st = tokenEl("synthesizer");
  if (st) st.classList.remove("walking");
  setGauge(data.confidence_score);

  const answer = document.getElementById("answer");
  const synth = agentMeta("synthesizer");
  answer.innerHTML =
    "<h3>" + (synth.emoji || "🧩") + " 최종 답변 " +
    '<span class="muted" style="font-size:13px;font-weight:500">(신뢰도 ' +
    data.confidence_score + "/100)</span></h3>" + esc(data.final_answer || "");
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
  try {
    const res = await fetch("/api/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "요청 실패");
    spin.style.display = "none";
    await reveal(data);
  } catch (e) {
    spin.style.display = "none";
    const answer = document.getElementById("answer");
    answer.innerHTML = "<h3>⚠️ 오류</h3>" + esc(e.message);
    answer.style.display = "block";
  } finally {
    go.disabled = false;
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
