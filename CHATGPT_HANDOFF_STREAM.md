# ChatGPT 작업 지시서 — 실시간 스트리밍(SSE) 백엔드

> 이 파일 `=== 여기부터 복사 ===` 아래 전부를 ChatGPT에 붙여넣으세요.
> 프론트(스트림 소비/애니메이션)는 Claude가 담당합니다. 여기서는 **백엔드만**.

---

=== 여기부터 복사 ===

너는 Python 백엔드 엔지니어다. Flask 앱 "AI Researcher Lab"에 **실시간 스트리밍(SSE)**
엔드포인트를 추가한다. **UI/디자인/CSS/HTML/JS(server.py의 INDEX_HTML)와
static/js/pixel-office.js는 절대 건드리지 마라 — Claude 담당.**

## 왜
지금은 `POST /api/run`이 세션을 **끝까지 계산한 뒤** 결과를 한 번에 준다. 그래서
사용자는 기다리는 동안 스피너만 본다. 발언이 만들어지는 즉시 흘려보내면, 프론트가
연구원들을 **실시간으로** 움직이며 대화시키게 할 수 있다(특히 무료 등급의 느린 호출을
"관람 시간"으로 바꿔줌).

## 재사용/유지할 것 (깨지 말 것)
- `run_session_web(question)`의 기존 흐름(라이트/풀 분기, `config.WEB_SESSION_BUDGET_SECONDS`
  deadline, 인카운터 예외 처리, `state.runtime_errors`)과 `_state_to_result`,
  `_store_session`, owner 쿠키, 오류/신뢰도 로직을 **그대로 재사용**.
- LLM 클라이언트 표면(`client.messages.create` → `content[i].text`) 유지.
- 기존 `POST /api/run`, `GET /api/sessions`, `GET /api/session/<id>`(+/export)는
  **그대로 남겨둔다**(지난연구 재생·공유가 이걸 씀).

## 구현할 것 (server.py 백엔드만)
1. **세션 루프를 제너레이터로 추출**: `iter_session_events(question)` 를 만들어
   세션을 진행하면서 아래 이벤트를 **발생 즉시** `yield` 한다(dict).
   - `{"type":"round", "index":n(1부터), "agents":[a1,a2], "location":loc, "confidence":int}`
     — 오케스트레이터가 인카운터를 정한 직후(에이전트가 이동 시작하기 전).
   - `{"type":"utterance", "agent":id, "message":str, "confidence":str,
       "location":loc, "turn":int, "responds_to":id|None}` — 각 `agent.speak()` **직후 즉시**.
     (한 인카운터의 첫 발언은 `responds_to=None` — 프론트 라운드 시작 규칙.)
   - `{"type":"final", "final_answer":str, "confidence_score":int,
       "confidence_threshold":int, "status":"ok|partial", "has_errors":bool, "id":str}`
     — 마지막에 1회. 여기서 세션을 `_store_session` 으로 저장하고 그 `id`를 담는다.
   - `{"type":"error", "message":str}` — 치명 오류 시(가급적 final로 마무리).
   - 기존 `run_session_web`은 내부적으로 `iter_session_events`를 소비해 최종 state를
     반환하도록 리팩터(중복 로직 제거). 즉 일괄 경로와 스트림 경로가 **같은 코어**를 쓴다.
2. **`POST /api/run/stream`** 라우트: body `{"question": ...}`.
   - `Response(stream_with_context(gen()), mimetype="text/event-stream")` 로 반환.
   - 각 이벤트는 SSE 형식으로: `data: ` + `json.dumps(event, ensure_ascii=False)` + `\n\n`.
   - 헤더: `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive`.
   - 빈 질문이면 400(JSON `{"error":...}`) — 스트림 열기 전에 검사.
   - owner 쿠키 로직(`_request_owner`/`after_request`)이 스트림 응답에도 적용되게 유지.
3. 세션 저장은 **스트림에서도 1회만**(final 직전). 일괄 `/api/run`과 이중 저장되지 않게.
4. 데모/라이트/풀 모드 모두에서 동작. deadline 초과 시 지금처럼 `runtime_errors`에
   남기고 정상적으로 final을 방출(스트림이 매달리지 않게).

## 계약 (반드시)
- 이벤트 필드명·`responds_to==None` 규칙·`location`은 `config.LOCATIONS` 키.
- 기존 엔드포인트/스키마 불변, `/api/run`은 계속 동작.
- INDEX_HTML·pixel-office.js·프론트 JS는 **절대 수정 금지**.

## 산출물
- `server.py`: `iter_session_events`, `/api/run/stream`, `run_session_web` 리팩터.
- `tests/test_stream.py`: 데모 모드로
  (a) `iter_session_events`가 `round`→`utterance`(들)→`final` 순으로 나오고,
  (b) 각 인카운터 첫 utterance가 `responds_to is None`,
  (c) `final`에 `id`·`status`·`has_errors`가 있고 저장소에서 그 id 조회가 되는지,
  (d) `POST /api/run/stream`이 200 + `text/event-stream`이고 최소 1개 `data:` 라인.
  (Flask `app.test_client()`, 네트워크 없이)
- 변경 요약 몇 줄.

먼저 계획을 3~5줄로 제시하고, 그 다음 전체 수정 코드를 파일별로 보여줘라.

=== 여기까지 복사 ===

---

## 백엔드 배포 후 Claude가 할 프론트(참고)
- `run()`이 `/api/run/stream`을 `fetch`+`ReadableStream`(또는 EventSource)로 소비:
  `round`→`PixelOffice.encounter()`, `utterance`→`showSpeech()`+타이핑,
  `final`→`PixelOffice.finalize()`+답변/버튼. 스트림 미지원·오류 시 기존 `/api/run` 폴백.
