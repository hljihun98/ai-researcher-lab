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

## [[작업]] — "지난 연구 다시보기" 백엔드 (세션 저장·목록·조회)
프론트엔드(디자인/JS)는 Claude가 이미 다 넣었다. 화면에는 "📁 지난 연구" 드롭다운이
있고, 아래 **두 API를 호출**해 과거 세션을 그대로 재생(reveal 애니메이션)한다.
지금은 그 API가 없어서 드롭다운이 숨겨져 있다. **너는 이 두 엔드포인트와 저장 로직만**
만들면 된다(디자인/INDEX_HTML은 절대 건드리지 마라).

구현할 것 (`server.py` 백엔드 부분):
1. **인메모리 세션 저장소**: 모듈 레벨에 최근 세션을 담는 링버퍼(예: 최대 20개).
   - Render 무료 인스턴스는 파일시스템이 비영속이라 **파일 대신 메모리**를 쓴다
     (재시작 시 사라져도 됨). 스레드 안전을 위해 `threading.Lock` 사용 권장.
   - 각 항목은 `/api/run`이 반환하는 것과 **완전히 동일한 dict** + `id`, `ts`(초, int).
     `id`는 짧은 문자열(예: 카운터 기반 "s1", "s2" 또는 uuid4 hex 앞 8자).
   - **주의**: `time.time()`/`uuid` 사용은 괜찮다(이건 서버 런타임 코드다).
2. **`run_session_web` 실행 후 저장**: `/api/run`이 결과를 반환하기 직전, 그 결과
   dict를 저장소에 push(가장 최근이 앞).
3. **`GET /api/sessions`** → `{"sessions": [{id, question, confidence_score, ts}, ...]}`
   (최신순). 프론트가 이 형식을 기대한다.
4. **`GET /api/session/<id>`** → 저장된 그 세션의 **전체 dict**(= `/api/run` 스키마:
   question, confidence_score, confidence_threshold, final_answer, history[...],
   orchestrator_log[...]). 없으면 404 + `{"error": "..."}`.
5. 데모 모드에서도 동작해야 한다(키 불필요).

## 디자인 틀 (Claude가 이미 제공함 — GPT는 데이터/API만 채운다)
- UI·프론트 JS 완료: `#historyRow`, `#history`(select), `#replayBtn`, 그리고
  `loadHistory()`(→ `GET /api/sessions`)와 `replaySelected()`(→ `GET /api/session/<id>`
  → 기존 `reveal(data)`로 재생)가 이미 INDEX_HTML에 들어있다.
- 따라서 **API 계약만 지키면** 드롭다운·재생이 자동으로 살아난다.
  응답 필드명(`sessions`, `id`, `question`, `confidence_score`, `ts`)을 정확히 맞출 것.
- **INDEX_HTML(마크업/CSS/JS)은 절대 수정 금지.**

## 산출물
- `server.py`의 저장소 + 두 엔드포인트 + run 후 저장 로직(디자인 제외).
- `tests/test_history.py`: 데모 모드로 `/api/run`을 2번 호출한 뒤
  (a) `GET /api/sessions`가 2건을 최신순으로 주는지,
  (b) `GET /api/session/<id>`가 `history`/`final_answer` 포함 전체 스키마를 주는지,
  (c) 없는 id는 404인지 검증. (Flask `app.test_client()` 사용)
- 변경 요약 몇 줄.

먼저 계획을 3~5줄로 제시하고, 그 다음 전체 수정 코드를 파일별로 보여줘라.

=== 여기까지 복사 ===

---

## 재사용 방법
다른 업데이트가 필요하면 위 `[[작업]]` 섹션만 바꿔서 다시 쓰면 된다.
`## 산출물`도 그 작업에 맞게 조정하라. **"인터페이스 계약"과 "제약/환경",
"INDEX_HTML 수정 금지"** 부분은 항상 그대로 두는 것을 권장한다 —
그래야 ChatGPT 결과물이 Claude가 만든 UI/배포와 충돌하지 않는다.
