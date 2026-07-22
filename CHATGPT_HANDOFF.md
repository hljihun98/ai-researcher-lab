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

## [[작업]] — 무료 등급용 "라이트 실행 파이프라인"
문제: Gemini 무료 등급은 **분당 5회** 호출 한도인데, 현재 한 세션이 15~20회를
몰아 호출해 대부분 `429 RESOURCE_EXHAUSTED`가 난다.

목표: **한 세션의 LLM 호출을 5회 이하**로 줄이면서도 "여러 에이전트가 대화해
답을 정제한다"는 느낌은 유지한다. 구체적으로:
1. `config.py`에 `LITE_MODE`(bool, env `AI_RESEARCHER_LITE=1`로 켜짐) 도입.
   라이트 모드일 때:
   - 오케스트레이터의 **LLM 호출 없이** 규칙 기반으로 페어/장소/신뢰도를 결정
     (예: 라운드1 리서처×비평가@화이트보드, 라운드2 팩트체커×전문가@도구실,
     신뢰도는 라운드마다 +30). `orchestrator.py`에 `decide_offline(state)` 추가.
   - 라운드 2회, 마주침당 발언 2회 → 에이전트 발언 4회 + 조율자 1회 = **총 5회**.
2. `server.py`의 `run_session_web()`가 `LITE_MODE`면 위 오프라인 경로를 쓰도록
   분기(단, `/api/run` 응답 스키마·`responds_to` 규칙은 그대로 유지).
3. `orchestrator_log`는 오프라인 결정도 동일 형식(action/agents/location/
   confidence_after/confidence_reason)으로 채워 프론트 애니메이션이 그대로 동작하게.
4. 기존 풀 모드(오케스트레이터 LLM 사용)는 `LITE_MODE=0`에서 그대로 유지.

## 디자인 틀 (Claude가 이미 제공함 — GPT는 이 틀에 맞춰 데이터만 채운다)
- 이 작업(라이트 파이프라인)은 **새 UI가 필요 없다.** 기존 화면이 `/api/run`
  응답 JSON을 그대로 렌더링한다(로스터/신뢰도 게이지/맵 이동/말풍선 타이핑).
- 따라서 GPT가 할 일은 **같은 스키마의 데이터를 더 적은 호출로 생성**하는 것뿐이다.
  `history`의 `responds_to`/`location`/`confidence`와 `orchestrator_log`의
  `action/agents/location/confidence_after`만 규칙대로 채우면 UI가 자동으로 동작한다.
- 새 시각 요소가 필요한 작업이라면, 그때 Claude가 먼저 HTML/CSS 뼈대(클래스명 포함)를
  server.py의 INDEX_HTML에 넣어 주고, GPT는 그 뼈대에 들어갈 데이터/로직만 맡는다.
  → **GPT는 어떤 경우에도 INDEX_HTML의 마크업/CSS/JS를 새로 디자인하지 않는다.**

## 산출물
- 위 로직 변경(디자인/INDEX_HTML 제외).
- `tests/test_lite_mode.py`: 데모 모드 + `AI_RESEARCHER_LITE=1`로
  `run_session_web`을 돌려 (a) LLM/데모 호출 횟수가 5회 이하인지(카운트 검증),
  (b) 응답 스키마·`responds_to` 규칙이 유지되는지, (c) 최종답변이 비어있지 않은지 검증.
- 변경 요약(무엇을 왜 바꿨는지) 몇 줄.

먼저 계획을 3~5줄로 제시하고, 그 다음 전체 수정 코드를 파일별로 보여줘라.

=== 여기까지 복사 ===

---

## 재사용 방법
다른 업데이트가 필요하면 위 `[[작업]]` 섹션만 바꿔서 다시 쓰면 된다.
`## 산출물`도 그 작업에 맞게 조정하라. **"인터페이스 계약"과 "제약/환경",
"INDEX_HTML 수정 금지"** 부분은 항상 그대로 두는 것을 권장한다 —
그래야 ChatGPT 결과물이 Claude가 만든 UI/배포와 충돌하지 않는다.
