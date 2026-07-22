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

## [[작업]] — 팩트체커 "진짜 검색(grounding)" 연결
> 앞선 "세션 ID 보안 + 오류 상태 분리" 작업은 이미 완료되어 커밋됨. 이건 다음 작업.

문제: 지금 Gemini 경로의 팩트체커는 **실제로 웹 검색을 하지 않는다.**
`FactCheckerAgent`는 Anthropic식 `web_search` 툴을 넘기지만 `GeminiClient`가
`tools`를 무시한다. 그래서 "확인했습니다"는 사실 모델 내부 지식일 뿐이다.
**팩트체커만** Google Gemini의 **검색 그라운딩(google_search)** 을 쓰게 해서,
근거 있는 검증으로 바꾼다. **너는 백엔드만** 수정한다(디자인/INDEX_HTML 금지).

구현:
1. `gemini_client.py`에 **그라운딩 옵션**을 추가하라. `GeminiClient._create`가
   `kwargs`로 `grounding=True`를 받으면, google-genai의 검색 도구를 켠다:
   `types.Tool(google_search=types.GoogleSearch())`를 `GenerateContentConfig.tools`에 넣기.
   (SDK 버전에 따라 `google_search_retrieval`일 수 있으니, 둘 중 되는 것으로 시도하고
   실패 시 그라운딩 없이 폴백. thinking 폴백 로직과 충돌 없게.)
2. `agents/fact_checker.py`(또는 base): 팩트체커가 **Gemini 백엔드일 때** `grounding=True`
   로 호출하도록 하라. Anthropic 백엔드면 기존 `web_search` 툴 경로를 유지(분기).
   백엔드 종류 판별은 `type(client).__name__`(`"GeminiClient"`) 정도로 충분.
3. 그라운딩이 근거(출처)를 반환하면, 팩트체커 발언 뒤에 아주 짧게 반영하되
   **발언 길이 규칙(1~2문장)은 유지**. 출처 URL을 응답 스키마에 넣고 싶으면
   `history` 항목에 선택적 `sources: [..]`를 **추가만**(기존 필드 유지) — 프론트가
   무시해도 안전하게. 필수는 아님.
4. 실검색 실패/미지원 시 **조용히 기존 동작으로 폴백**(세션이 죽지 않게).

### 계약 (반드시 지킬 것)
- LLM 클라이언트 표면(`client.messages.create(...)` → `content[i].text`)·`/api/run`
  스키마·`responds_to` 규칙 유지. 새 필드는 **추가만**, 제거/이름변경 금지.
- 데모/Anthropic 경로는 그대로 동작. 그라운딩은 **Gemini 팩트체커에만** 적용.

## 산출물
- `gemini_client.py` + `agents/fact_checker.py`(필요시 base) 수정. **디자인 제외.**
- `tests/test_grounding.py`: (a) 데모 모드에서 팩트체커가 그라운딩 인자 유무와 무관하게
  크래시 없이 발언하는지, (b) `GeminiClient._create`가 `grounding=True`일 때 config에
  검색 도구를 넣으려 시도하는지(모의/몽키패치로 호출 인자 검사), (c) 그라운딩 미지원
  예외 시 폴백해 텍스트를 돌려주는지. (네트워크 실제 호출 없이)
- 변경 요약 몇 줄. **주의**: 무료 등급에서 그라운딩은 호출/쿼터를 더 쓸 수 있음 — 명시.

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
