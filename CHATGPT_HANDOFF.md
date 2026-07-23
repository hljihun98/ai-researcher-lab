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

## [[작업]] — 대화 다양화 + "같은 부류끼리 먼저 논의 → 회의" 구조
> 앞선 grounding·보안·오류·평가 하네스 작업은 모두 완료·커밋됨. 이건 다음 작업.
> **너는 백엔드/프롬프트만** 수정한다. `server.py`의 INDEX_HTML(HTML/CSS/JS)과
> `static/js/pixel-office.js`(캔버스 엔진)는 **절대 건드리지 마라 — Claude 담당.**

두 가지 불만을 해결한다:
1) 오가는 대화가 **너무 반복적** — 질문이 달라도 비슷한 말/구조가 나온다.
2) 흐름이 밋밋 — **같은 부류(성향)의 연구원끼리 먼저 논의**하고, 그 결론을
   **회의(meeting_desk)에서 종합**하는 서사가 있으면 좋겠다.

### A. 대화 다양화
- `prompts/*.txt` 강화(리서처/비평가/전문가/팩트체커/조율자): **질문 유형·도메인에
  맞춰** 답하고, **직전과 같은 표현·구조를 반복하지 말 것**을 명시. 좋은/나쁜 예시를
  질문 카테고리(기술/일상/추천/비교 등)별로 다양화. 단, **한 발언 1~2문장·40자 내외·
  대화체·확신도 태그** 규칙은 유지(말풍선에 담겨야 함).
- **라이트 모드의 고정 시퀀스 제거**: 지금 `orchestrator.decide_offline`는 항상
  `리서처×비평가@화이트보드 → 팩트체커×전문가@도구실`로 똑같다. 질문 문자열 해시로
  **결정적이지만 질문마다 다른** 페어/장소를 고르게 하라(같은 질문=같은 흐름 재현은 유지).
- (선택) 데모 대본(`main.py` `_DEMO_LINES`)도 역할별 문장을 늘려 반복 완화.

### B. "같은 부류끼리 먼저 → 회의" 구조 (오케스트레이션)
- 구성 아이디어(2인 인카운터 단위는 유지 — 시각 엔진이 2명씩 마주보게 처리하므로):
  - 라운드1: **아이디어 그룹**(예: 리서처×전문가) @ library/coffee — 발산.
  - 라운드2: **검증 그룹**(예: 비평가×팩트체커) @ server_room/whiteboard — 반박·검증.
  - 라운드3: **회의**(각 그룹 대표 1명씩, 예: 리서처×비평가) @ **meeting_desk** — 종합 조율.
  - 이후 `synthesizer.finalize()`로 최종 답변(기존과 동일).
- 풀 모드(`orchestrator.decide`)는 프롬프트에 위 "그룹 논의 → 회의" 흐름을 유도하는
  지침을 넣어 자연스럽게 그 순서로 페어링하도록. 라이트 모드(`decide_offline`)는 위
  3라운드 구조를 규칙으로 구현(단, 라이트는 호출 5회 제한 존중 — 라운드당 발언 최소화).
- `location`은 반드시 `config.LOCATIONS` 키만 사용(프론트 맵이 그 키로 이동).

### 계약 (반드시 지킬 것)
- `/api/run` 응답 스키마·필드명 유지. **한 마주침의 첫 발언은 `responds_to=None`**
  (프론트가 라운드 시작으로 씀). `location`은 기존 5개 키 중 하나.
- LLM 클라이언트 표면(`client.messages.create` → `content[i].text`) 유지.
- 데모 모드·라이트 모드 5회 호출 상한·세션 시간 예산 로직을 깨지 마라.

## 산출물
- `prompts/*.txt`, `orchestrator.py`(decide/decide_offline), 필요시 `config.py`.
  **INDEX_HTML·pixel-office.js·API 스키마 변경 금지.**
- `tests/`:
  (a) 서로 다른 질문 2개로 라이트 세션을 돌리면 **페어/장소 시퀀스가 다르게** 나오는지,
  (b) 같은 질문은 **같은 시퀀스**로 재현되는지(결정성),
  (c) 모든 발언의 `location`이 유효 키이고 각 마주침 첫 발언이 `responds_to=None`인지.
  (데모 모드·네트워크 없이)
- 변경 요약 몇 줄.

먼저 계획을 3~5줄로 제시하고, 그 다음 전체 수정 코드를 파일별로 보여줘라.

=== 여기까지 복사 ===

---

## 재사용 방법
다른 업데이트가 필요하면 위 `[[작업]]` 섹션만 바꿔서 다시 쓰면 된다.
`## 산출물`도 그 작업에 맞게 조정하라. **"인터페이스 계약"과 "제약/환경",
"INDEX_HTML 수정 금지"** 부분은 항상 그대로 두는 것을 권장한다 —
그래야 ChatGPT 결과물이 Claude가 만든 UI/배포와 충돌하지 않는다.

---

## GPT 방향 진단 메모 → Claude 전달용 (2026-07-22)

### 한 줄 결론

**제품의 외형과 상호작용은 원래 비전에 잘 맞게 빠르게 구현됐지만, 핵심 가치인
“여러 에이전트의 실제 검토가 단일 답변보다 품질과 신뢰도를 높인다”는 부분은 아직
입증되지 않았다.** 지금은 UI 기능을 더 늘리기보다 연구 품질·검증 가능성·운영 안전성을
먼저 보강하는 편이 원래 방향에 더 가깝다.

### 원래 방향대로 잘 구현된 부분

- 5개 역할(리서처/비평가/전문가/팩트체커/조율자), 대화 히스토리 공유,
  `responds_to` 기반 캐치볼, 마지막 조율자의 종합이라는 기본 구조는 살아 있다.
- 풀 모드에서는 오케스트레이터가 대화 내용을 보고 페어·장소·종료 시점을 정하므로
  단순히 다섯 답변을 병렬로 붙이는 구조는 아니다.
- 장소 정보가 에이전트 프롬프트에도 전달되며, 프론트의 맵 이동·말풍선·신뢰도 게이지와
  백엔드 로그가 같은 스키마로 연결되어 있다. 시각 연출과 실제 실행 데이터의 연결은 좋다.
- 지난 연구 재생, 마크다운 내보내기, 공유 링크까지 같은 세션 데이터를 재사용하는 방향도
  “연구 과정을 결과물로 남긴다”는 제품 경험과 잘 맞는다.
- DemoClient와 단위 테스트 덕분에 키나 네트워크 없이도 구조적 회귀를 잡을 수 있다.

### 가장 큰 방향 이탈 또는 미완성 지점

1. **UI는 Phase 3 수준인데 핵심 Phase 1 품질 검증이 끝나지 않았다.**
   `PROJECT_MEMO.md`는 “Phase 1을 완벽히 만든 뒤 시각화”를 원칙으로 삼았지만,
   실제 Gemini 질문군에 대한 품질 평가와 프롬프트 튜닝보다 UI·재생·공유가 앞서갔다.
   현재 테스트는 API 스키마와 빈 응답 여부는 검증하지만 답이 질문에 맞는지, 반박 후
   실제로 개선됐는지, 단일 Gemini 호출보다 나은지는 검증하지 않는다.

2. **현재 Gemini 경로의 팩트체커는 실제 웹 검색을 하지 않는다.**
   `FactCheckerAgent`는 Anthropic 형식의 `web_search` 도구를 넘기지만
   `GeminiClient`가 `tools`를 무시한다. UI/프롬프트에서는 “확인했다”고 보여도 실제로는
   모델 내부 지식일 수 있다. 이 상태에서는 “팩트체크 완료”나 높은 신뢰도를 사실 검증으로
   표현하면 안 된다. Gemini Grounding 또는 별도 검색 어댑터가 필요하다.

3. **신뢰도 점수는 아직 신뢰도가 아니라 진행 연출에 가깝다.**
   풀 모드는 오케스트레이터 LLM의 자기평가이고, 라이트 모드는 대화 내용과 무관하게
   라운드마다 `+30`이다. 특히 라이트 모드의 `20 → 50 → 80`은 증거의 강도를 측정하지
   않는다. 백엔드가 보정되기 전까지 UI 문구를 “정답 신뢰도”보다 “검토 진행도” 또는
   “연구 성숙도”로 표현하는 것이 정직하다.

4. **라이트 모드는 무료 등급 대응에는 맞지만 동적 멀티에이전트성은 약하다.**
   모든 질문이 `리서처×비평가@화이트보드 → 팩트체커×전문가@도구실` 순서로 진행된다.
   질문 유형에 따라 역할과 장소를 고르는 원래 오케스트레이션 비전은 풀 모드에만 있다.
   또한 테스트가 세는 것은 `messages.create` 5회다. Gemini 어댑터의 thinking 폴백과
   429 재시도 때문에 실제 원격 `generate_content` 요청 수는 5회를 넘을 수 있다.

5. **오류가 정상 연구 결과처럼 섞일 수 있다.**
   웹 세션은 인카운터 예외를 `pass`로 삼키고, Gemini 어댑터는 오류를
   `"(Gemini 오류: ...)"` 텍스트 응답으로 바꾼다. 그 결과 실패한 발언을 포함하고도
   세션이 성공·고신뢰도로 표시될 수 있다. 부분 실패 상태와 최종 신뢰도 하향 규칙이 필요하다.

6. **“지난 연구/공유”는 현재 데모 기능이지 안전한 영속 기능이 아니다.**
   저장소는 모든 방문자가 공유하는 전역 메모리이고 `/api/sessions`도 전역 목록이다.
   순차 ID(`s1`, `s2`)는 추측 가능해 다른 사용자의 질문을 조회할 수 있다. Render 재시작·
   슬립 시 기록과 공유 링크도 사라진다. 공개 배포라면 최소한 무작위 ID, 브라우저별 소유권
   또는 공개/비공개 구분, TTL이 필요하고, 진짜 공유 링크라면 외부 영속 저장소가 필요하다.

7. **Phase 4의 핵심인 사용자 개입은 아직 없다.**
   현재 클릭 동작은 예시 질문·테마·재생·내보내기이며, 에이전트를 클릭해 조사 방향을
   지시하거나 진행 중 대화를 바꾸는 백엔드 상태 전이는 구현되지 않았다.

### 운영·문서 상태 (최신 재점검)

- `README.md`의 Phase 표기와 기본 Gemini 모델 예시는 현재 코드에 맞게 수정됨.
- `.env.example`도 기본 `gemini-3.5-flash` 안내로 동기화됨.
- Render와 Dockerfile 모두 인메모리 세션 일관성을 위해 worker 1로 맞춰짐.
- `PROJECT_MEMO.md` 개발 로그는 최근 라이트 모드·지난 연구·내보내기·보안/최적화 작업을
  아직 모두 반영하지 않았으므로 추후 한 번에 갱신 필요.

### Claude에게 권하는 다음 우선순위

**P0 — 제품 약속을 진짜로 만들기**

1. 서로 다른 질문군 10~20개로 `단일 Gemini 답변` 대 `멀티에이전트 최종 답변`을 비교하는
   평가 하네스를 먼저 만든다. 관련성, 사실성, 실행 가능성, 반박 반영 여부를 기록한다.
2. Gemini 팩트체커에 실제 검색/grounding과 출처 데이터를 연결한다. 연결 전에는 UI에서
   “검증 완료”를 강하게 주장하지 않는다.
3. ~~오류 텍스트를 세션 상태로 분리하고 실패 시 신뢰도를 낮춘다.~~ **GPT 작업으로 완료.**
   최신 구현은 `status`, `has_errors`, 건당 -20 감점과 라이트 라운드 상승 롤백을 포함한다.
4. 라이트 모드도 LLM 호출 없이 질문 키워드/분류에 따라 2개 페어 중 하나를 고르거나,
   1회의 계획 호출 결과를 나머지 4회가 공유하도록 개선한다.

**P1 — 공개 배포 안전성**

1. ~~세션 ID를 추측 불가능하게 바꾸고 전역 목록을 격리한다.~~ **GPT 작업으로 완료.**
   owner별 목록 격리 + 무작위 ID 직접 조회 방식으로 공유 링크를 유지한다.
2. “공유 링크”를 유지하려면 Render 외부 저장소와 만료 정책을 도입한다. 메모리 유지라면
   UI에 “서버 재시작 시 사라지는 임시 링크”임을 명시한다.
3. README, `.env.example`, Dockerfile, `PROJECT_MEMO.md`를 실제 동작과 동기화한다.

**P2 — 그 다음 사용자 경험**

1. Phase 4 사용자 개입의 최소 형태를 정의한다. 예: 다음 라운드에서 특정 에이전트에게
   한 줄 지시를 주고, 그 지시를 `extra_instruction`으로 전달.
2. 의미 품질이 확인된 뒤 픽셀 스프라이트·맵 디테일을 추가한다. 지금 CSS/이모지 맵은
   훌륭한 프로토타입이지만 최종 카이로소프트풍 아트 단계는 아니다.

### GPT 최신 작업 완료 보고 → Claude (2026-07-22)

> 이 항목이 이전의 “현재 작업 트리 인계 주의”보다 최신이다.

#### 1. 세션 보안·소유권·오류 상태 작업

- `server.py`
  - 순차 세션 ID(`s1`, `s2`)를 `secrets.token_urlsafe(8)` 무작위 ID로 교체.
  - owner 쿠키를 7일 수명, `HttpOnly`, `SameSite=Lax`, `Path=/`로 발급.
  - `/api/sessions`는 owner가 같은 세션만 최신순으로 반환.
  - `/api/session/<id>`와 `/export`는 무작위 ID를 아는 경우 owner와 무관하게 직접 조회 가능
    (공유 링크 계약 유지). 응답에는 owner를 노출하지 않음.
  - 실패 출력 수에 따라 `confidence_score`를 건당 20점 감점하고
    `status="partial"`, `has_errors=true`를 반환.
  - 인카운터 예외를 더 이상 `pass`로 버리지 않고 `runtime_errors`에 기록.
- `conversation.py`
  - `is_failure_message()` 추가. `(Gemini 오류`, `(빈 응답`,
    `(최종 답변 생성 중 오류` 접두사를 실패로 판정.
  - 발언 생성 전에 발생한 예외를 보존하는 `runtime_errors` 추가.
- `orchestrator.py`
  - 라이트 모드에서 실패한 라운드에 선반영된 `+30`을 되돌리고
    state와 `orchestrator_log`를 모두 `delta=0`으로 보정.
- 신규 `tests/test_security_errors.py`
  - 브라우저별 목록 격리, 무작위 ID, 공유 직접 조회, 쿠키 속성,
    partial 상태/감점, 실패 라운드 롤백을 검증.

#### 2. 전체 코드 오류 점검·최적화 작업

- `agents/base.py`, `agents/fact_checker.py`, `agents/synthesizer.py`
  - 텍스트 블록이 없거나 비어 있는 LLM 응답을 `(빈 응답)`으로 정규화해 정상 발언으로
    오인하지 않게 함.
  - 확신도 정규식을 클래스 수준에서 한 번만 컴파일.
  - 불필요한 Anthropic import 제거, 팩트체커의 비정상 response 방어 처리.
- `gemini_client.py`
  - Gemini 3.x에서는 거부될 수 있는 `thinking_budget=0` 요청을 먼저 보내지 않고
    기본 thinking 설정으로 바로 한 번 호출. Gemini 2.x의 빠른 비활성화 경로는 유지.
  - `models/gemini-...` 형태의 모델명도 판별 가능.
- `main.py`
  - 발언 생성 실패로 `turn_count`가 늘지 않아도 CLI가 무한 반복되지 않도록 라운드 상한 추가.
  - CLI 인카운터 예외도 `runtime_errors`에 기록.
- `conversation.py`
  - 기본 로그 파일명에 마이크로초를 넣어 같은 초에 종료된 세션끼리 덮어쓰는 문제 수정.
- 신규 테스트
  - `tests/test_agent_errors.py`: 일반 에이전트/팩트체커/조율자 빈 응답 정규화.
  - `tests/test_gemini_client.py`: Gemini 2.x/3.x 요청 경로와 호출 횟수.
  - `tests/test_conversation.py`: 로그 이름 충돌과 CLI 무한루프 방지.

#### 3. 최종 검증 결과

- `python -m compileall -q .` 통과.
- `python -m unittest discover -s tests -v`: **31개 전부 통과**.
- Ruff 정적 검사: **오류 0건**.
- Flask 앱 import 및 라우트 **8개 정상 등록**.
- 테스트가 만든 임시 로그는 정리 완료.
- `server.py`의 `INDEX_HTML`/CSS/JS는 이번 GPT 작업에서 수정하지 않음.

#### 4. 현재 미커밋 변경 인계

- 수정: `agents/base.py`, `agents/fact_checker.py`, `agents/synthesizer.py`,
  `conversation.py`, `gemini_client.py`, `main.py`, `orchestrator.py`, `server.py`,
  `tests/test_history.py`, `tests/test_lite_mode.py`.
- 신규: `tests/test_agent_errors.py`, `tests/test_conversation.py`,
  `tests/test_gemini_client.py`, `tests/test_security_errors.py`.
- Claude가 `server.py` UI를 편집할 때 `INDEX_HTML` 바깥의 위 백엔드 변경을 덮어쓰지 말 것.

#### 5. 의도적으로 남겨 둔 제한

- 실제 Gemini API 네트워크 E2E는 키/과금 호출 없이 수행하지 않았음.
- Gemini 경로에서 Anthropic 형식 `web_search`가 무시되는 기존 문제는 남아 있음
  (Gemini Grounding 또는 별도 검색 어댑터 필요).
- 지난 연구 저장소는 여전히 프로세스 메모리이므로 서버 재시작 시 사라짐.

---

## GPT Google Search Grounding 작업 완료 보고 → Claude (2026-07-22)

> 이 항목이 위의 “GPT 최신 작업 완료 보고”보다 최신이다.

- `gemini_client.py`
  - `messages.create(..., grounding=True)`를 지원한다.
  - 최신 SDK의 `types.Tool(google_search=types.GoogleSearch())`를 우선 사용하고,
    구형 SDK에서는 `google_search_retrieval`을 시도한다.
  - 검색 도구 구성 또는 모델 호출이 실패하면 429 재시도와 충돌하지 않게 같은 요청을
    일반 생성으로 조용히 폴백한다. Gemini 2.x/3.x thinking 분기 역시 유지했다.
- `agents/fact_checker.py`
  - Gemini 팩트체커만 `grounding=True`를 전달한다.
  - Anthropic은 기존 `web_search_20250305` 도구 경로를 유지하고 DemoClient에도
    Gemini 전용 인자를 전달하지 않는다.
  - 기존 `FACT_CHECKER_MAX_SEARCHES` 한도를 Gemini grounding 요청에도 적용한다.
- `tests/test_grounding.py` 신규 추가
  - 데모 발언, Gemini 전용 분기, Anthropic 기존 도구, 실제 SDK config의 검색 도구,
    검색 미지원 시 네트워크 없는 일반 생성 폴백을 검증한다.
- 검증 결과: 전체 단위 테스트 **36개 통과**, compileall 통과, Ruff 오류 0건,
  Flask 라우트 8개 정상 등록.
- 실제 Gemini API 호출은 키·쿼터를 소비하지 않도록 수행하지 않았다. 운영 시 Google Search
  grounding은 일반 생성보다 추가 호출/검색 쿼터를 사용할 수 있다.
- `server.py`와 그 안의 `INDEX_HTML`/CSS/JS는 수정하지 않았다.

---

## GPT Render 300초 타임아웃 수정 완료 보고 → Claude (2026-07-22)

- 실제 배포 사이트를 진단했다.
  - 첫 무료 인스턴스 기동은 약 53초였으나 이후 `/healthz`는 0.38초에 200을 반환했다.
  - `/api/meta`는 `demo_mode=false`였고, 실제 `/api/run`은 300.5초 후 Gunicorn 500으로
    종료됐다. 정적 UI 문제가 아니라 Gemini 실행 요청의 서버 타임아웃이었다.
  - 설치된 `google-genai` SDK 기본 재시도(최대 5회)와 기존 어댑터 재시도(4회)가
    중첩되어 호출 하나가 최악의 경우 20번까지 시도될 수 있음을 확인했다.
- `gemini_client.py`
  - SDK 내부 재시도를 1회(추가 재시도 없음), 어댑터 시도도 최대 1회로 제한했다.
  - 개별 Gemini HTTP 요청 기본 제한을 20초로 설정했다.
  - 서버가 전달한 `time.monotonic()` 마감 시각을 넘으면 추가 원격 호출과 백오프를 중단한다.
- `server.py` / `config.py`
  - 웹 세션 전체 기본 예산을 60초로 두고 GeminiClient에 마감 시각을 전달한다.
  - 예산 초과는 오류 상태가 포함된 부분 결과로 반환하며, 예상 밖 예외도 HTML 500 대신
    JSON 오류로 반환한다.
  - `/api/meta`에 `lite_mode`, `session_budget_seconds`를 추가해 배포 반영을 확인할 수 있다.
- `render.yaml`
  - `AI_RESEARCHER_LITE=1`, 세션 60초, 개별 요청 20초, 최대 시도 1회를 배포 기본값으로
    추가했다. 기존 Render 서비스가 Blueprint 환경변수를 자동 동기화하지 않으면 대시보드에
    같은 네 값을 직접 넣어야 한다.
- `.env.example`, `README.md`에 운영 설정을 동기화했다.
- 신규 `tests/test_runtime_limits.py`를 포함해 전체 단위 테스트 **45개 통과**,
  `compileall` 통과, Ruff 오류 0건.
- Claude의 최신 픽셀 UI 변경은 보존했고 `INDEX_HTML`/CSS/JS는 수정하지 않았다.
- 아직 배포 전 로컬 변경이다. 커밋·푸시 및 Render 재배포 후 `/api/meta`에서
  `lite_mode=true`, `session_budget_seconds=60`을 확인해야 한다.

---

## GPT 라이브 검증 + 무작위 예시 질문 완료 보고 → Claude (2026-07-22)

- `https://ai-researcher-lab.onrender.com/`을 실제 외부 요청으로 검증했다.
  - `/healthz` 0.29초, `/api/meta` 0.43초로 서버 자체는 정상이다.
  - 기존 RAG 예시가 아닌 “한 달 동안 꾸준히 할 수 있는 재미있는 취미” 질문으로
    `/api/run`을 호출했으며 **HTTP 200**, 최종 답변과 발언 4개를 반환했다.
  - 다만 완료까지 **139.76초**가 걸렸고 팩트체커가 `429 RESOURCE_EXHAUSTED`여서
    `status=partial`, `confidence_score=30`이었다. 라이브 기능은 작동하지만 현재 배포는
    아직 느리고 Gemini 검색 쿼터 때문에 완전 성공하지 못한다.
  - `/api/meta`에 새 `lite_mode`, `session_budget_seconds` 필드가 없으므로 위의 타임아웃
    수정 코드가 아직 라이브 커밋에 배포되지 않은 것도 확인했다.
- `server.py`의 기존 RAG 고정 예시를 제거했다.
  - 재미있는 생활·취미·팀워크·사이드 프로젝트 질문 12개 후보를 추가했다.
  - 페이지를 열 때마다 Fisher-Yates 방식으로 3개를 무작위 표시한다.
  - 직전 3개 조합을 `localStorage`에 저장하고 같은 조합이 연속 표시되지 않게 한다.
  - 첫 번째 무작위 질문을 입력창 placeholder에도 반영하며, 예시 클릭 즉시 연구를 시작하는
    기존 동작은 유지한다.
- JavaScript 문법 검사 통과, 전체 단위 테스트 **45개 통과**, `compileall` 통과,
  Ruff 오류 0건.
- 이번에는 사용자가 명시적으로 요청한 예시 영역의 HTML/JS만 수정했으며 기존 픽셀 맵,
  캐릭터, CSS 디자인은 변경하지 않았다.

---

## Render 비밀키 설정 상태 기록 → Claude (2026-07-22)

- 사용자가 Render 서비스의 Environment Variables에 `GEMINI_API_KEY`를 직접 설정했다.
- **실제 API 키 값은 보안상 확인·복사·문서화하지 않았고 저장소 어디에도 기록하지 않는다.**
- 함께 확인된 비민감 운영값:
  - `GEMINI_MODEL=gemini-3.5-flash`
  - `PYTHON_VERSION=3.11`
  - `AI_RESEARCHER_LITE=1`
  - `GEMINI_MAX_ATTEMPTS=1`
  - `GEMINI_REQUEST_TIMEOUT_SECONDS=20`
  - `AI_RESEARCHER_SESSION_BUDGET_SECONDS=60`
- 라이브 `/api/meta`에서 `demo_mode=false`였고 실제 Gemini 답변도 생성되어 키가 실시간
  백엔드 선택에 사용되는 것은 확인했다. 현재 부분 실패는 잘못된 키가 아니라 무료 등급의
  `429 RESOURCE_EXHAUSTED` 문제다.
- 향후 키를 재발급하거나 교체해도 Render 대시보드에서만 다루고 Git·로그·핸드오프에는
  실제 값을 남기지 말 것.

---

## GPT 실배포 및 세션 마감 보정 → Claude (2026-07-22)

- 커밋 `b8e28dc`를 `origin/main`에 푸시해 Render 자동 배포를 완료했다.
- 라이브 `/api/meta`에서 `lite_mode=true`, `session_budget_seconds=60`, 루트 HTML에서
  무작위 예시 코드와 기존 RAG 예시 제거를 확인했다.
- 새 배포에서 실제 질문을 실행해 HTTP 200, 발언 4개, 최종 답변 반환을 확인했다.
  Gemini 무료 쿼터가 소진된 상태라 결과는 `partial`이었다.
- 실측 완료 시간이 78.26초로 60초 예산보다 길었다. 마감 직전에 시작한 20초 HTTP 요청이
  완료될 때까지 기다리는 경계 문제였으므로, 남은 시간이 개별 요청 제한보다 짧으면 새
  Gemini 요청을 시작하지 않도록 `GeminiClient`를 추가 보정했다.

---

## GPT 대화 다양화 + 그룹 논의·대표 회의 구현 → Claude (2026-07-23)

- 구현 커밋: `c62f64c` (`origin/main` 푸시 완료).
- `orchestrator.py` / `config.py` / `server.py`
  - 라이트 모드를 질문 문자열의 정규화된 SHA-256 해시로 계획해, 같은 질문은 같은
    페어·장소를 재현하고 질문이 달라지면 순서·장소·대표가 달라지게 했다.
  - 1라운드는 리서처×전문가 @ `library|coffee`, 2라운드는 비평가×팩트체커 @
    `whiteboard|server_room`, 3라운드는 각 그룹 대표 1명씩 @ `meeting_desk`다.
  - 무료 등급 5회 상한 때문에 그룹별 대표 발언 1회 + 대표 회의 2회 + 최종 조율 1회,
    즉 `1+1+2+1=5회`로 배분했다. 공개 `/api/run` 스키마와 오케스트레이터 로그 필드는
    유지했고 매 라운드 첫 발언의 `responds_to=None` 계약도 유지했다.
  - 풀 모드 동적 오케스트레이터에도 아이디어 그룹 → 검증 그룹 → 대표 회의의 현재 단계를
    명시해, 시간·턴 상한이 아니라면 세 단계를 건너뛰지 않도록 유도했다.
  - `/api/meta`에 배포 판별용 `orchestration_version="group-meeting-v1"`을 추가했다.
- `prompts/*.txt`
  - 리서처·비평가·전문가·팩트체커·조율자 프롬프트에 기술/일상/추천/비교별 관점과
    직전 표현·문장 구조 반복 금지 규칙, 도메인 중립 예시를 추가했다.
- 직전 다중 키 커밋 회귀 보정
  - `GeminiClient`가 `_clients` 없는 단일/테스트 인스턴스에서도 안전하게 1개 클라이언트로
    처리하도록 해 grounding·시간 제한 테스트 4개 오류를 복구했다.
  - `tests/test_key_rotation.py`의 기존 Ruff `E702` 오류도 정리했다.
- 검증
  - 전체 단위 테스트 **51개 통과**, `compileall` 통과, Ruff 오류 0건, `git diff --check`
    통과. 비밀키 패턴 검사에서 실제 키가 저장소에 없음을 확인했다.
  - `server.py`의 `INDEX_HTML`과 `static/js/pixel-office.js`는 수정하지 않았다.
