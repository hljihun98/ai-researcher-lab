# ChatGPT 작업 지시서 (핸드오프 프롬프트)

> 이 파일은 **ChatGPT에게 그대로 복사-붙여넣기** 할 프롬프트입니다.
> 역할 분담: **디자인/UI는 Claude가 담당**(건드리지 말 것), **연산·로직만 ChatGPT가 담당**.
> 아래 `=== 여기부터 복사 ===` 밑을 전부 복사해서 ChatGPT에 붙여넣으세요.
> `[[작업]]` 부분만 원하는 다음 업데이트로 바꾸면 재사용할 수 있습니다.
> (아래엔 지금 가장 필요한 작업인 "무료 등급용 라이트 실행 파이프라인"을 예시로 채워뒀습니다.)

---

=== 여기부터 복사 ===

너는 Python 백엔드 엔지니어다. 아래 프로젝트의 **연산/로직 부분만** 수정한다.
**UI/디자인/CSS/HTML/JS는 절대 건드리지 마라** — 그건 다른 담당(Claude)이 관리한다.

## 프로젝트 개요
"AI Researcher Lab": 5명의 AI 연구원(리서처/비평가/전문가/팩트체커/조율자)이
서로 대화하며 사용자 질문에 대한 답을 정제하는 멀티 에이전트 시스템.
Flask 웹앱으로 배포(Render), 백엔드 LLM은 Google Gemini.

## 파일 구조와 담당
```
config.py            # 설정(모델명, 임계값, 에이전트/장소 정의)      ← 수정 가능
conversation.py      # ConversationState, Utterance                  ← 수정 가능
orchestrator.py      # 라운드마다 다음 행동 결정(JSON)               ← 수정 가능
agents/base.py       # BaseAgent.speak() — LLM 호출                  ← 수정 가능
agents/fact_checker.py, synthesizer.py                                ← 수정 가능
gemini_client.py     # Gemini를 Anthropic 인터페이스로 감싼 어댑터    ← 수정 가능
main.py              # CLI + build_runtime_client + DemoClient        ← 수정 가능(주의)
server.py            # Flask 라우트 + run_session_web()  →  로직만 수정 가능
server.py 안의 INDEX_HTML(문자열, <style>/<script>/HTML) = 디자인    ← ★절대 수정 금지★
tests/               # 단위 테스트                                    ← 추가/수정 가능
```

## 절대 깨면 안 되는 인터페이스(계약)
1. **LLM 클라이언트 표면**: 모든 에이전트/오케스트레이터는
   `client.messages.create(model=, max_tokens=, system=, messages=[{"role","content"}])`
   를 호출하고, 응답에서 `response.content[i].text`(블록에 `.type=="text"`)를 읽는다.
   Gemini/Demo 클라이언트 모두 이 표면을 흉내낸다. 이 형태를 바꾸지 마라.
2. **`build_runtime_client()`(main.py) 우선순위**: 데모 > Gemini(GEMINI_API_KEY) >
   Anthropic > 데모. `AI_RESEARCHER_DEMO_MODE=1`이면 무조건 DemoClient.
3. **`/api/run` 응답 JSON 스키마**(프론트가 이걸 읽어 렌더/애니메이션함) — 필드 유지:
   `question, confidence_score, confidence_threshold, final_answer,
    history[{agent, message, confidence, location, turn, responds_to}],
    orchestrator_log[...]`.
   특히 프론트는 `responds_to == null`을 "라운드 시작"으로 사용하므로,
   한 마주침의 첫 발언은 반드시 `responds_to=None`이어야 한다.
4. **DemoClient는 API 키 없이도 동작**해야 한다(테스트/무키 데모의 생명줄).

## 제약/환경
- 로컬에 Python이 없어 개발자가 직접 실행/시각 확인을 못 한다. **CI(GitHub Actions,
  ubuntu)가 유일한 검증 수단**이다. 반드시 `tests/`에 검증 테스트를 추가하고,
  `python -m unittest discover -s tests`로 통과해야 한다.
- 데모 모드에서 돌아가는 테스트를 우선 작성하라(네트워크/키 불필요).
- Windows/Render 양쪽에서 동작해야 한다.

## [[작업]] — 세션 "내보내기(.md)" + "공유 링크" 백엔드
프론트엔드(디자인/JS)는 Claude가 이미 다 넣었다. 최종 답변 아래에
**"⬇ 마크다운 저장"·"🔗 공유 링크 복사"** 버튼이 있고, 다음을 호출한다:
- 공유 링크: `location.origin + "/?session=<id>"` (페이지 로드 시 `?session=<id>`가
  있으면 그 세션을 자동 재생 — 프론트 완료).
- 내보내기: `window.open("/api/session/<id>/export")`로 마크다운 파일 다운로드.

지금은 (1) `/api/run`·`/api/session/<id>` 응답에 **`id`가 없어서** 프론트가 현재
세션을 가리키지 못하고, (2) `export` 엔드포인트가 없다. **너는 백엔드만** 만들면 된다
(디자인/INDEX_HTML은 절대 건드리지 마라).

구현할 것 (`server.py` 백엔드 부분):
1. **응답에 `id` 포함**:
   - `POST /api/run` 응답 JSON에 그 세션의 `id`를 넣는다(지금은 저장 시에만 붙고
     응답엔 빠져 있음 — 저장에 쓴 id를 응답에도 같이 반환).
   - `GET /api/session/<id>` 응답에도 `id`를 포함(현재는 pop 해서 제거 중 → 유지로 변경).
   - `history`/`orchestrator_log` 등 기존 필드는 그대로. `id` 추가만.
2. **`GET /api/session/<id>/export`**:
   - 저장된 세션을 **마크다운 문서**로 만들어 파일 다운로드로 반환한다.
     헤더: `Content-Type: text/markdown; charset=utf-8`,
     `Content-Disposition: attachment; filename="research_<id>.md"`.
   - 마크다운 구성: 제목(질문), 최종 신뢰도, "## 대화" 아래 라운드별로
     (장소 + 각 발언 `**표시이름** (@장소, 확신도): 메시지`), "## 최종 답변" + 본문.
   - 라운드 구분은 프론트와 동일 규칙: `responds_to`가 없는 발언에서 새 라운드 시작.
     에이전트 표시이름/장소이름은 `config.AGENTS[...]["display_name"]`,
     `config.LOCATIONS[...]`로 변환.
   - 없는 id는 404 + `{"error": "..."}`.
3. 데모 모드에서도 동작해야 한다(키 불필요).

## 디자인 틀 (Claude가 이미 제공함 — GPT는 데이터/API만 채운다)
- UI·프론트 JS 완료: `#answerActions`(내보내기/공유 버튼), `setActions(id)`,
  공유 링크 복사, `?session=<id>` 자동 재생이 모두 INDEX_HTML에 들어있다.
- 버튼은 **응답에 `id`가 있을 때만** 자동으로 나타난다(없으면 숨김). 즉 위 1번만 해도
  버튼이 살아나고, 2번을 하면 다운로드가 동작한다.
- **INDEX_HTML(마크업/CSS/JS)은 절대 수정 금지.**

## 산출물
- `server.py`: 응답에 `id` 포함 + `GET /api/session/<id>/export`(디자인 제외).
- `tests/test_export.py`: 데모 모드로 `/api/run` 1회 실행 후
  (a) 응답에 `id`가 있는지,
  (b) `GET /api/session/<id>/export`가 200 + `text/markdown` + 본문에 질문/최종답변이
      포함되는지, (c) 없는 id는 404인지 검증. (Flask `app.test_client()` 사용)
- 변경 요약 몇 줄.

먼저 계획을 3~5줄로 제시하고, 그 다음 전체 수정 코드를 파일별로 보여줘라.

=== 여기까지 복사 ===

---

## 재사용 방법
다른 업데이트가 필요하면 위 `[[작업]]` 섹션만 바꿔서 다시 쓰면 된다.
`## 산출물`도 그 작업에 맞게 조정하라. **"인터페이스 계약"과 "제약/환경",
"INDEX_HTML 수정 금지"** 부분은 항상 그대로 두는 것을 권장한다 —
그래야 ChatGPT 결과물이 Claude가 만든 UI/배포와 충돌하지 않는다.
