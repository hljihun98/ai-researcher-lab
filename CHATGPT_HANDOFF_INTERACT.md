# ChatGPT 작업 지시서 — Phase 4 인터랙티브 개입 (백엔드)

> `=== 여기부터 복사 ===` 아래를 ChatGPT에 붙여넣으세요. 프론트(클릭·개입 UI)는 Claude 담당.
> 선행: 스트리밍 백엔드(`/api/run/stream`, `iter_session_events`) 완료됨.

---

=== 여기부터 복사 ===

너는 Python 백엔드 엔지니어다. Flask 앱 "AI Researcher Lab"에 **사용자 개입(Phase 4)**
백엔드를 추가한다. **INDEX_HTML(HTML/CSS/JS)·static/js/pixel-office.js는 절대 수정 금지 — Claude.**

## 목표
지금은 사용자가 질문만 던지고 구경만 한다. **개입**을 넣어 능동적 연구로 만든다. v1은 둘:
1. **리드 지정**: 질문 시 특정 연구원을 "이번 연구 리더"로 지정 → 그 연구원이 먼저/더 발언.
2. **집중 후속(follow-up)**: 답변이 끝난 세션을 이어받아, 사용자가 지정한 방향
   ("이 관점 더 파기 / 반박 더 / 출처 확인 / 다른 관점" 또는 특정 연구원)으로
   **추가 라운드를 스트리밍으로 이어 실행**한다.

## 재사용/유지 (깨지 말 것)
- `iter_session_events`, `/api/run/stream`, `run_session_web`, `_state_to_result`,
  `_store_session`, owner 쿠키, 라이트/풀·deadline·오류/신뢰도 로직.
- `/api/run`·`/api/session/*`·기존 이벤트 스키마 불변. **추가만**.

## 구현 (server.py 백엔드만)
1. **리드 지정**: `/api/run/stream`(및 `/api/run`) body에 선택적 `lead`(agent id) 허용.
   - `iter_session_events(question, ..., lead=None)`: 오케스트레이터(풀=프롬프트로 유도,
     라이트=규칙)가 **첫 라운드에 그 연구원이 참여**하도록 편향. 유효하지 않은 id는 무시.
2. **집중 후속**: 새 엔드포인트 `POST /api/session/<id>/follow_stream` (SSE).
   - body: `{"directive": "이 관점 더 파기"| "반박"| "출처"| "다른 관점" | 자유문자열,
     "agent": <선택 agent id>}`.
   - 저장된 세션(`_get_stored_session`)의 **소유자만** 허용(owner 쿠키 검사) — 아니면 403.
   - 그 세션의 대화 히스토리를 시드로 `ConversationState`를 복원하고, directive/agent를
     반영한 **1~2 라운드 추가 인카운터 → 조율자 재요약**을 `iter_session_events`와 같은
     이벤트 형식(round/utterance/final)으로 스트리밍한다.
   - 끝나면 **이어진 전체 세션을 다시 저장**(새 id 또는 같은 id 갱신 — 택1, 문서에 명시).
   - directive→행동 매핑 예: "반박"=비평가 주도, "출처"=팩트체커(가능하면 grounding),
     "다른 관점"=전문가/리서처 새 페어, "이 관점 더 파기"=직전 주제 심화.
3. 데모/라이트/풀·세션 예산·오류 처리 모두 유지. SSE 헤더도 기존과 동일.

## 계약
- 이벤트 필드명·`responds_to==None`(라운드 시작)·`location`은 `config.LOCATIONS` 키.
- `lead`/`directive`/`agent`는 **선택**. 없으면 기존과 100% 동일 동작.
- 소유권 검사로 남의 세션 후속 실행 금지.

## 산출물
- `server.py`(+필요시 `orchestrator.py`/`conversation.py`): `lead` 편향, `follow_stream`,
  히스토리 시드 복원. **디자인/엔진/프론트 JS 미수정.**
- `tests/test_interact.py`(데모, 네트워크 없이):
  (a) `lead` 지정 시 첫 라운드에 그 agent가 포함되는지,
  (b) `follow_stream`이 소유자에겐 200 SSE·비소유자에겐 403,
  (c) 후속 스트림이 round→utterance→final 형식이고 최종 저장/조회되는지,
  (d) 옵션 미지정 시 스트림 결과가 스트림 기본과 동일한지(회귀).
- 변경 요약 몇 줄.

먼저 계획을 3~5줄로 제시하고, 그 다음 전체 수정 코드를 파일별로 보여줘라.

=== 여기까지 복사 ===

---

## 백엔드 후 Claude 프론트(참고)
- 캔버스 클릭 히트테스트로 연구원 선택(리드 지정/후속 대상), 답변 아래 "이 관점 더 파기 /
  반박 / 출처 / 다른 관점" 버튼 → `follow_stream` 소비(기존 스트림 소비 로직 재사용).
