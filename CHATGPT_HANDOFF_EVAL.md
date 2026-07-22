# ChatGPT 작업 지시서 — 평가 하네스 (Eval Harness)

> 이 파일은 **ChatGPT에게 그대로 복사-붙여넣기** 할 프롬프트입니다.
> `=== 여기부터 복사 ===` 아래 전부를 붙여넣으세요.
> (보안/오류 상태 작업은 `CHATGPT_HANDOFF.md`에 따로 있습니다. 순서는 그걸 먼저 →
>  이 평가 하네스를 나중에 하는 걸 권장합니다.)

---

=== 여기부터 복사 ===

너는 Python 백엔드/평가 엔지니어다. 아래 프로젝트에 **평가 하네스**를 추가한다.
**UI/디자인/CSS/HTML/JS(server.py의 INDEX_HTML 문자열)는 절대 건드리지 마라** —
그건 다른 담당(Claude)이 관리한다. 이 작업은 웹 UI가 필요 없는 **개발용 CLI 도구**다.

## 프로젝트 개요
"AI Researcher Lab": 5명의 AI 연구원(리서처/비평가/전문가/팩트체커/조율자)이
대화하며 사용자 질문의 답을 정제하는 멀티 에이전트 시스템. 백엔드 LLM은 Google Gemini
(어댑터 `gemini_client.py`가 Anthropic식 `client.messages.create` 표면을 흉내낸다).
데모 모드(`AI_RESEARCHER_DEMO_MODE=1`)에선 API 키 없이 캔드 응답으로 동작한다.

## 이 작업의 목적(가장 중요)
이 제품의 핵심 가설은 **"여러 에이전트가 대화·반박하며 만든 최종 답변이, 같은 모델의
단일 호출 답변보다 낫다"** 이다. 이 하네스는 그 가설을 **정량적으로 검증**한다:
같은 질문을 (A) 단일 Gemini 1회 호출과 (B) 멀티에이전트 파이프라인에 각각 넣고,
**LLM 심판**으로 블라인드 비교해 점수/승률을 낸다.

## 재사용할 것 (깨지 말 것)
- `main.build_runtime_client()` — 실행 클라이언트(데모/Gemini/Anthropic) 선택.
- `client.messages.create(model=, max_tokens=, system=, messages=[{"role","content"}])`
  → `response.content[i].text`(블록 `.type=="text"`). 이 표면으로만 LLM을 부른다.
- 멀티에이전트 실행: `server.run_session_web(question)` 를 재사용하면 됨
  (`ConversationState` 반환, `.final_answer` 사용). import 시 순환참조 주의 —
  필요하면 `run_session_web`의 핵심 루프를 `eval/`에서 얇게 재구성해도 된다(단,
  기존 코드 표면·스키마는 변경 금지).
- `config.MODEL_NAME`/`config.GEMINI_MODEL`, `config.AGENTS` 등 설정 재사용.

## 구현할 것 — 새 `eval/` 디렉터리 (기존 앱 코드 변경 최소화)
1. **`eval/questions.json`**: 다양한 유형의 벤치마크 질문 12~15개(카테고리 태그 포함).
   아래 시드를 시작점으로 쓰고 살을 붙여라(카테고리: 기술선택/사실확인/비교/방법/
   주관추천/트레이드오프/도메인). 예시 시드:
   ```json
   [
     {"category":"기술선택","q":"소규모 스타트업에 적합한 RAG 아키텍처는?"},
     {"category":"비교","q":"pgvector와 Pinecone 중 초기 스타트업에 뭐가 나을까?"},
     {"category":"방법","q":"원격 근무 팀의 생산성을 높이는 구체적 방법은?"},
     {"category":"주관추천","q":"주니어 개발자가 처음 배우기 좋은 언어는?"},
     {"category":"트레이드오프","q":"모놀리스 vs 마이크로서비스, 5인 팀 기준 선택은?"},
     {"category":"사실확인","q":"HTTP/3가 HTTP/2 대비 실제로 개선한 지점은?"}
   ]
   ```
2. **`eval/harness.py`**: 각 질문에 대해
   - (A) **단일 베이스라인**: `client.messages.create`로 1회 호출
     (system="너는 전문가다. 질문에 정확하고 실행 가능하게 답하라.", 질문을 user로).
   - (B) **멀티에이전트**: `run_session_web(q).final_answer`.
   - (C) **LLM 심판**(같은 client): 두 답변을 **A/B 라벨을 무작위로 섞어**(순서 편향 방지)
     제시하고, 각 답변을 **관련성·사실성·실행가능성·완결성**(각 1~5)로 채점 + 승자 선택 +
     한 줄 근거. 심판 출력은 JSON으로 강제(파싱). 무작위는 질문 인덱스로 라벨 스왑
     (`Date.now()`/`random` 없이 결정적으로).
   - 각 라운드 사이에 무료 등급 429를 피하도록 **설정 가능한 지연**(기본 3초) + 재시도는
     `gemini_client`의 백오프에 위임.
3. **집계/출력**: 질문별 표(카테고리, A점수합, B점수합, 승자) + 전체 요약
   (멀티 승률 %, 항목별 평균 점수 차이). 콘솔 표 + `eval/results.json` 저장.
4. **CLI**: `python -m eval.harness [--n 6] [--delay 3] [--model ...]`.
   질문 수 제한(`--n`)으로 무료 등급 예산을 조절할 수 있게.

## 제약/환경
- 로컬에 Python이 없어 개발자가 직접 못 돌린다. **CI(GitHub Actions)가 유일한 검증**이다.
  → `tests/test_eval_harness.py`: **데모 모드**로 `--n 1`(또는 함수 직접 호출) 실행이
  **크래시 없이** 완주하고 `results.json` 구조(리스트/필수 키)가 나오는지 검증
  (데모 응답이라 점수 내용은 무의미해도 됨 — 구조/파이프라인만 확인).
- 실제 품질 평가는 `GEMINI_API_KEY` 필요 + 호출량이 많다(질문당 최소 3회). README나
  `eval/README.md`에 "무료 등급은 `--n`을 작게, 유료 권장" 주의를 적어라.
- 기존 앱 동작/스키마/INDEX_HTML은 변경하지 마라. 새 코드는 `eval/`에 격리.

## 산출물
- `eval/questions.json`, `eval/harness.py`, `eval/README.md`(간단 사용법),
  `tests/test_eval_harness.py`.
- 콘솔 출력 예시 + 변경 요약 몇 줄.

먼저 계획을 3~5줄로 제시하고, 그 다음 전체 코드를 파일별로 보여줘라.

=== 여기까지 복사 ===
