# AI Researcher Lab — 프로젝트 메모

> 이 문서는 프로젝트의 방향과 현재 상태를 담습니다.
> **새 세션을 시작하는 AI는 이 문서를 먼저 읽고 작업을 이어가세요.**
> 코드보다 이 문서가 항상 우선입니다. 결정이 바뀌면 여기부터 갱신하세요.

---

## 1. 한 줄 요약

사용자가 던진 질문을 **여러 명의 전문화된 AI 에이전트**가 2D 게임(카이로소프트 스타일) 안에서 돌아다니며 서로 대화하고 반박하며 답을 정제하는 시스템. 결과는 시각적 애니메이션 + 최종 통합 답변으로 나온다.

## 2. 최종 비전 (여기까지 가는 게 목표)

- 픽셀 아트 스타일의 "연구소" 맵
- 5명의 AI 연구원 스프라이트가 자기 목적을 갖고 이동
- 서로 마주치면 말풍선으로 짧은 대화 (2~3턴)
- 대화가 실제로 답변 신뢰도를 올림 (연출이 아니라 실제 사고)
- 답변 신뢰도가 임계값 넘으면 조율자가 최종 답변 발표
- 사용자는 언제든 개입 가능 (에이전트 클릭해서 방향 지시)

## 3. 개발 단계 (Phase)

| Phase | 목표 | 상태 |
|-------|------|------|
| **1** | CLI 백엔드 — 5명 에이전트가 텍스트로 대화하며 답 정제 | 🚧 진행 중 |
| 2 | 정적 시각화 — 대화 로그를 화면에 말풍선으로 표시 | 대기 |
| 3 | 이동 애니메이션 — 목적지 걸어가서 마주치는 흐름 | 대기 |
| 4 | 사용자 개입 — 신뢰도 게이지, 에이전트 클릭 지시 | 대기 |

**중요한 원칙**: Phase 1을 완벽하게 만든 뒤에 Phase 2로 넘어간다. 시각화가 뒤에 붙어야 프롬프트 튜닝이 안 흔들린다.

## 4. 설계 결정 (왜 이렇게 만들었는가)

이 섹션은 **왜 그렇게 했는지**를 기록. 나중에 "왜 이걸 이렇게 했지?" 하고 다시 찾을 때 여기 봄.

- **에이전트 5명**: 3명은 너무 단조롭고 7명은 대화가 산만해짐. 5명이 역할 겹침 없이 창발성 나오는 지점.
- **한 마주침 = 2~3턴**: 길어지면 사용자가 말풍선 못 따라감. 시각화 단계에서도 자연스러움.
- **오케스트레이터 분리**: 에이전트끼리 자율적으로 만나게 하면 수렴이 안 됨. 별도 지휘자가 "다음은 X와 Y가 화이트보드에서 만나라"고 명시적으로 결정.
- **웹 검색은 팩트체커만**: 모든 에이전트가 검색하면 비용/시간 폭증. 근거 필요 시 팩트체커에게 의뢰하는 흐름.
- **한 발언 40자 내외**: 나중에 말풍선에 담기려면 지금부터 제약 걸어야 함. 프롬프트에 명시.
- **확신도 태그 강제**: 매 발언 끝에 `[확신: 낮음/중간/높음]`. 조율자가 최종 답변 만들 때 가중치로 씀.
- **Claude Sonnet 4.6 기본**: 비용/성능 밸런스. 오케스트레이터도 같은 모델. 필요시 config.py에서 변경.
- **JSON 기반 오케스트레이터 응답**: 파싱 안정성 위해. 자연어 지시는 모호함.
- **한국어 우선**: 사용자가 한국인. 프롬프트/응답 모두 한국어. 다국어는 나중.

## 5. 폴더 구조

```
ai-researcher-lab/
├── PROJECT_MEMO.md          # 이 파일. 프로젝트의 헌법.
├── README.md                 # 사용자용 실행 가이드
├── requirements.txt          # 의존성
├── .env.example              # 환경변수 템플릿
├── config.py                 # 모델명, 임계값, 에이전트 목록
├── agents/
│   ├── __init__.py
│   ├── base.py              # BaseAgent - 모든 에이전트의 부모
│   ├── researcher.py        # 리서처
│   ├── critic.py            # 비평가
│   ├── expert.py            # 도메인 전문가 (동적 페르소나)
│   ├── fact_checker.py      # 팩트체커 (웹 검색 툴 사용)
│   └── synthesizer.py       # 조율자 (최종 답변)
├── prompts/                  # 시스템 프롬프트 텍스트 파일
│   ├── researcher.txt
│   ├── critic.txt
│   ├── expert.txt
│   ├── fact_checker.txt
│   ├── synthesizer.txt
│   └── orchestrator.txt
├── conversation.py           # 대화 로그 + 상태 관리
├── orchestrator.py           # 지휘자 - 누가 언제 만날지 결정
├── main.py                   # CLI 엔트리포인트
└── logs/                     # 실행 로그 저장 (JSON)
```

## 6. 각 에이전트 상세 사양

### 리서처 (Researcher)
- **역할**: 정보 수집, 가설 여러 개 제안
- **말투**: 열정적, 열려있음, "~ 어떨까요?" "~할 수도 있어요"
- **강점**: 아이디어 발산
- **약점**: 근거 부족한 채로 확장하는 경향
- **색상 (시각화용)**: 보라 (#7F77DD)

### 비평가 (Critic)
- **역할**: 논리적 허점, 반례, 놓친 조건 찾기
- **말투**: 짧고 직설적, "하지만" "그건 좋은데"로 시작
- **강점**: 약한 주장 걸러냄
- **약점**: 지나치게 부정적일 수 있음 (프롬프트로 균형 강제)
- **색상**: 코랄 (#D85A30)

### 도메인 전문가 (Domain Expert)
- **역할**: 질문 카테고리에 맞는 심도있는 지식 제공
- **말투**: 정확하고 전문적, 용어 사용
- **특이점**: **첫 턴에 자기 페르소나를 정함** (예: "이건 SW 아키텍처 질문이니 시니어 백엔드 엔지니어 관점에서 접근")
- **색상**: 청록 (#0F6E56)

### 팩트체커 (Fact-Checker)
- **역할**: 다른 에이전트의 주장을 웹 검색으로 검증
- **말투**: 중립적, "확인된 바로는" "출처는"
- **특이점**: **유일하게 웹 검색 툴 사용 가능**
- **색상**: 파랑 (#378ADD)

### 조율자 (Synthesizer)
- **역할**: 대화가 충분히 성숙하면 최종 답변 작성
- **말투**: 균형있고 종합적, 각 관점을 인정
- **특이점**: 마주침에 참여하지 않음. 대화 끝에서만 호출됨.
- **색상**: 앰버 (#EF9F27)

## 7. 데이터 흐름 (한 라운드)

```
[사용자 질문]
      ↓
[오케스트레이터] "다음은 리서처가 서고에서 아이디어 뽑아라"
      ↓
[리서처] 발언 (40자) + 확신도 태그
      ↓ (대화 히스토리에 추가)
[오케스트레이터] "리서처 아이디어를 비평가가 화이트보드에서 반박"
      ↓
[비평가] 발언 → [리서처] 재반박 (2~3턴 인카운터)
      ↓
[오케스트레이터] 신뢰도 계산. 아직 낮음.
      ↓
[팩트체커] 웹 검색으로 특정 주장 검증
      ↓
[전문가] 새로운 관점 추가
      ↓
... (신뢰도 85 넘을 때까지) ...
      ↓
[조율자] 전체 로그 읽고 최종 답변 작성
      ↓
[사용자에게 출력]
```

## 8. 상태 관리 (ConversationState)

프로젝트 전체가 하나의 `ConversationState` 객체를 공유:

```python
{
  "question": str,              # 사용자 원 질문
  "history": [                  # 모든 발언 로그
    {
      "agent": "critic",
      "message": "그건 좋은데 비용 검증이 없어요.",
      "confidence": "medium",
      "location": "whiteboard",
      "turn": 3,
      "responds_to": "researcher"
    },
    ...
  ],
  "confidence_score": 0-100,    # 오케스트레이터가 매 라운드 갱신
  "turn_count": int,
  "max_turns": 20,              # 안전장치
  "confidence_threshold": 85,   # 이상이면 조율자 호출
  "location_history": [...],    # 마지막 인카운터 장소
  "final_answer": str | None
}
```

## 9. 남은 위험/미해결 이슈

- **에이전트가 반복 발언할 위험**: 같은 주장 계속함. → 오케스트레이터가 "새로운 관점 요구" 감지 필요.
- **비용 폭주 위험**: 한 질문에 5명 × 20턴 × 여러 마주침 = 토큰 폭발. → max_turns 상한, cache 활용.
- **한국어 프롬프트 정확도**: Claude가 한국어에서 지시 잘 따르는지 실제 테스트 필요.
- **팩트체커 웹 검색 무한루프**: 검색 결과에 또 검색하고 싶어할 수 있음. → 검색 횟수 상한.

## 10. 개발 로그

날짜별로 무엇을 했는지 짧게. 새 세션 진입한 AI는 여기 마지막 항목을 보고 이어감.

### 2026-07-21 (초기 세션 — Phase 1 구조 완성)

**완료한 것**
- 프로젝트 컨셉 정립, 계획 문서 작성
- 폴더 구조 확정
- `PROJECT_MEMO.md` 작성 (이 파일)
- `config.py` — 중앙 설정 (모델명, 임계값, 5개 에이전트 정의, 5개 장소 정의)
- `prompts/*.txt` — 6개 시스템 프롬프트 (researcher, critic, expert, fact_checker, synthesizer, orchestrator)
- `conversation.py` — `ConversationState`, `Utterance` 데이터클래스, JSON 로그 저장 기능
- `agents/base.py` — 공통 `BaseAgent` 클래스. 확신도 태그 파싱 포함
- `agents/fact_checker.py` — 웹 검색 툴 활성화 (`web_search_20250305`)
- `agents/synthesizer.py` — `speak()` 대신 `finalize()` 사용
- `agents/__init__.py` — `build_agents()` 팩토리
- `orchestrator.py` — JSON 결정 파싱, 검증, 폴백 라운드로빈
- `main.py` — CLI 엔트리포인트, 컬러 출력, 라운드 루프
- `README.md`, `requirements.txt`, `.env.example`
- 임포트 트리 + JSON 파싱 + 응답 파싱 단위 검증 완료 (API 호출 없이)

**아직 안 한 것 / 다음 할 일**
1. **실제 API로 end-to-end 테스트** — 사용자가 `ANTHROPIC_API_KEY` 설정 후 첫 질문 돌려보고 프롬프트 튜닝 필요한 부분 파악.
2. **프롬프트 조정 대상 (예상)**
   - 리서처가 리스트로 답하면 다시 대화체 강제
   - 비평가가 3턴 연속 부정만 하면 균형 규칙 강화
   - 오케스트레이터가 자꾸 같은 페어 골라내면 다양성 규칙 추가
3. **`agents/researcher.py`, `critic.py`, `expert.py` 생성** — 현재는 base로 커버되지만, 나중에 개별 특화 로직(예: 전문가 페르소나 자동 판정) 넣을 자리.
4. **Phase 2 준비**: 로그 JSON 스키마 안정화 (시각화가 이걸 읽어 재생함)
5. **에러 처리 강화**: API 레이트 리밋, 타임아웃, 부분 실패 등

**튜닝 시 주의**
- 프롬프트 바꿀 때 반드시 `PROJECT_MEMO.md` 섹션 4(설계 결정)와 6(에이전트 사양)도 함께 갱신할 것.
- `config.py` 값 바꾸면 여기 로그에 이유 남길 것.

**다음 세션 시작 시 이 명령부터**
```bash
cd ai-researcher-lab
export ANTHROPIC_API_KEY='...'
python main.py "테스트 질문"
```
결과를 보고 무엇을 고칠지 판단.

### 2026-07-22 (데모 모드 정상화 + 배포 설정 정리)

**완료한 것**
- **데모 모드 버그 수정**: `DemoResponse` 블록에 `type="text"`가 없어 `base/orchestrator/synthesizer`의 `getattr(block,"type")=="text"` 필터에 전부 걸러져 발언·최종답변이 빈 문자열이던 문제 해결. `DemoClient`를 역할 인식 기반으로 재작성 → 데모 모드가 실제 대화 흐름(신뢰도 상승 → finalize)을 시연.
- **테스트 강화**: `tests/test_demo_mode.py`에 E2E 테스트 추가 (final_answer·발언 비어있지 않음 검증) — 원래 버그를 잡아냄. GitHub Actions에 데모 스모크 스텝 추가.
- **배포 설정**: `render.yaml`을 web → **cron** 타입으로 수정(CLI는 상시 서버가 아님). `deploy.yml`을 "Deploy" → "CI (build & verify)"로 정직하게 개명하고 실제 배포는 주석 예시로 남김. `.gitignore`, `.env.example` 추가.
- **모델명 정합**: `config.MODEL_NAME` `claude-sonnet-4-5` → `claude-sonnet-4-6` (섹션 4 설계결정과 일치).
- **에러 처리**: `run_session`의 `synthesizer.finalize()`를 try/except로 감싸 최종 답변 실패 시에도 로그 저장 후 안전 종료.
- **로그 스키마 안정화(Phase 2 대비)**: `save_log`에 `schema_version`, `generated_at`, `agents`(색상 포함), `locations`, `confidence_threshold` 추가. 스키마 바꾸면 `LOG_SCHEMA_VERSION` 올리고 여기 기록.
- 중복 스크래치 파일 제거(`check_demo.py`, `verify_demo.py`, `verify_git.bat`).

**주의 / 미해결**
- **로컬에 실제 Python 미설치** (Microsoft Store 스텁만 존재) → 로컬 실행/테스트 불가. CI(ubuntu)에서 검증됨. 실제 API E2E는 여전히 미검증(섹션 10 초기 세션의 다음 할 일 1번).
- Render cron/worker는 유료 플랜이 필요할 수 있음 — 실제 배포 전 확인.
- `FALLBACK_MODEL`은 정의만 되어 있고 미사용.

### 2026-07-22 (Phase 1.5 — 웹 서버 배포)

사용자가 "브라우저로 열리는 링크"를 기대(GitHub Pages 시도)했으나, Phase 1은 CLI뿐이라 볼 화면이 없었음. **CLI를 웹앱으로 감싸 실제 실행 서버로 배포**하기로 결정.

**완료한 것**
- `server.py` — Flask 웹앱. `GET /`(질문 입력 UI), `POST /api/run`(세션 실행 후 대화+최종답변 JSON 반환), `GET /api/meta`(에이전트 색상/장소/데모여부), `GET /healthz`. `run_session_web()`은 CLI의 흐름을 출력 없이 재현하고 `MAX_ROUNDS`로 방어.
- 브라우저 UI: 에이전트별 색상 말풍선, 신뢰도 표시, 최종 답변 박스. 단일 HTML(인라인) — 외부 의존성 없음.
- `requirements.txt`에 flask, gunicorn 추가.
- `render.yaml`: cron → **web** 타입, `gunicorn server:app --bind 0.0.0.0:$PORT`. 기본 데모 모드.
- `Dockerfile`: 웹 서버(gunicorn)로 변경, `EXPOSE 8000`.
- `tests/test_web.py`: Flask test client로 라우팅·데모 세션 스모크(로컬 Python 부재 → CI가 유일한 검증).
- README 배포 섹션 갱신 + "GitHub Pages로는 파이썬 실행 불가" 명시.

**중요 — 배포 방법**
- 앱 URL은 `github.io`가 아니라 **Render**(`https://<이름>.onrender.com`). 
- Render에 저장소를 **Blueprint로 연결**해야 실제로 배포됨(코드 푸시만으로는 Render가 자동 생성 안 함 — 최초 1회 연결 필요). README 배포 섹션 참고.

**미해결**
- 실시간(실제 API) 모드에서 한 요청이 gunicorn 120s 타임아웃을 넘을 수 있음 → 배포 기본은 데모 모드로 회피.
- Phase 2(로그 재생 시각화)는 여전히 별개 과제. 이 웹앱은 "지금 실행"용이고, 저장된 로그 재생 UI는 아님.

### 2026-07-22 (실시간 백엔드 Anthropic → Gemini 교체)

사용자가 **회사 계정이라 Claude API 발급이 어려움** → 실시간 백엔드를 Google Gemini로 교체.

**설계 결정**
- 기존 코드가 모두 Anthropic식 `client.messages.create(...)` + `response.content[i].text` 패턴이라, **Gemini를 같은 인터페이스로 감싸는 어댑터**(`gemini_client.py`, `GeminiClient`)를 만들어 에이전트/오케스트레이터 코드는 그대로 둠. DemoClient와 같은 전략.
- 백엔드 선택 우선순위(`build_runtime_client`): 데모 > Gemini(`GEMINI_API_KEY`) > Anthropic(`ANTHROPIC_API_KEY`, 폴백) > 데모.
- `system` → Gemini `system_instruction`, `max_tokens` → `max_output_tokens`, `messages`의 user content를 이어붙여 `contents`로. Anthropic 전용 인자(`tools` 등)는 무시.
- **2.5 계열 thinking이 출력 토큰을 먹어 빈 응답이 나는 것 방지**: `thinking_config=ThinkingConfig(thinking_budget=0)` (SDK 버전 없으면 자동 생략).
- 모델: `config.GEMINI_MODEL`(기본 `gemini-2.5-flash`), `GEMINI_MODEL` 환경변수로 오버라이드.

**보안 원칙 (중요)**
- **키 값은 절대 소스/커밋에 넣지 않음.** `GEMINI_API_KEY` 환경변수로만 주입 (로컬 `.env`는 gitignore, 배포는 Render 대시보드).
- 사용자가 채팅에 붙인 Gemini 키는 노출됐으므로 재발급 권고함.

**기능 손실(주의)**
- 팩트체커의 Anthropic `web_search` 툴은 Gemini 어댑터에서 무시됨 → 팩트체커는 웹 검색 없이 모델 지식으로만 답함. Gemini grounding 연동은 추후 과제.

**검증**
- `tests/test_backend.py`: 백엔드 선택 분기 검증(네트워크 호출 없음). 로컬 Python 부재 → CI에서만 검증.

### 2026-07-22 (웹 UI 개편 — "밋밋함" 해소, Phase 2 방향으로 한 걸음)

**완료한 것**
- `server.py` UI 전면 재작성 (여전히 단일 인라인 HTML, 외부 의존성 0):
  - **연구팀 로스터**: 5명 카드(이모지 아바타 + 이름 + 역할). 발언 시 해당 카드가 하이라이트(pulse).
  - **신뢰도 게이지**: 라운드 진행에 따라 애니메이션으로 채워지고, 목표(임계값) 눈금 표시.
  - **말풍선**: `responds_to==null`을 라운드 경계로 삼아 "라운드 N + 장소" 헤더로 그룹핑, 발언이 하나씩 슬라이드-인. 아바타·색상·확신도 배지.
  - 다크 그라디언트 배경, 스피너(점 3개) 등.
- `config.AGENTS`에 `emoji`, `role_desc` 추가 → `/api/meta`로 노출.
- `/api/run` 응답에 `orchestrator_log`, `responds_to`, `confidence_threshold` 추가(프론트 렌더용).
- `index()`가 Jinja 파싱을 타지 않게 `Response(..., mimetype="text/html")`로 원시 반환 (JS의 `{}` 오파싱 방지).

**주의**
- 여전히 이건 "지금 실행" 결과를 예쁘게 보여주는 것. Phase 2의 "저장 로그 재생/맵 위 이동 애니메이션"은 아직 아님(다음 단계 후보).
- 로컬 Python 부재로 시각 확인 불가 → 배포/CI로 확인 필요.

### 2026-07-22 (.env 자동 로드 + 말풍선 타이핑 효과)

**완료한 것**
- `python-dotenv` 추가. `main.py`/`server.py`가 시작 시 `.env`를 자동 로드(로컬 편의). 배포는 대시보드 env 사용.
- `.env` 자리표시자 파일 생성(**gitignore됨, 커밋 안 됨**): `GEMINI_API_KEY=` 한 줄에 키만 넣으면 실시간 동작. 키 실제 값은 사용자가 직접 입력(요청대로 주석/자리표시자로 안내).
- UI: 말풍선 **타이핑 효과**(한 글자씩, 깜빡이는 캐럿), **연구 주제 배너** 추가.

**보안 원칙 유지**: 키 값은 코드/커밋에 절대 넣지 않음. 공개 repo라 커밋 시 즉시 유출.

### 2026-07-22 (데모 역할 오판별 버그 수정 + Phase 3 맵 애니메이션)

**버그 수정**
- `_demo_role`가 조율자 프롬프트를 오케스트레이터로 오판별 → 최종 답변 칸에
  오케스트레이터 JSON이 새던 문제. 조율자 프롬프트가 본문에 "오케스트레이터",
  "리서처" 단어를 포함하기 때문. 판별 마커를 **고유한 굵은 역할명**(`**조율자**`,
  `**리서처**`, …)과 `팀 리더`로 교체.
- 회귀 테스트 추가(`test_demo_mode.py`): 실제 프롬프트 6개가 올바른 역할로
  판별되는지 + 최종 답변이 오케스트레이터 JSON이 아닌지 검증.

**Phase 3 맵 애니메이션 (server.py UI)**
- "연구소 맵" 패널: 5개 장소 마커(서고/화이트보드/커피/도구실/회의책상) +
  5개 에이전트 토큰(이모지). 로드 시 하단 홈에 정렬.
- 라운드마다 참여 두 에이전트가 해당 장소로 **걸어가고**(bob 애니메이션 +
  left/top 트랜지션), 장소 링이 활성화되며, 그 시점에 말풍선이 타이핑됨.
  발언 중인 토큰은 색상 링(speaking)으로 강조.
- 마지막에 조율자가 회의 책상으로 나와 최종 답변 정리.
- 라운드 경계는 기존과 동일하게 `responds_to==null`로 판별.

**주의**
- 데모 모드는 질문과 무관한 캔드 대본(RAG) 재생 → 사용자가 "질문과 다른 답"으로
  느낌. 질문에 맞는 답은 실시간(GEMINI_API_KEY) 모드에서만.
- 여전히 로컬 Python 부재 → 시각 확인은 배포로.

### 2026-07-22 (실시간 검증 + 무료등급 429 대응)

**실측으로 확인한 것 (배포 사이트에 직접 호출)**
- 키 유효 ✅ (`x-goog-api-key` 방식). `/api/meta` demo_mode=false 확인.
- `gemini-2.5-flash`는 이 계정 차단(404) → `gemini-3.5-flash`로 작동.
- **가장 큰 벽: 무료 등급 분당 5회 한도**(`GenerateRequestsPerMinutePerProjectPerModel-FreeTier`, limit 5).
  앱은 한 세션에 15~20회 호출 → 6번째부터 전부 429.

**대응**
- `GeminiClient`: 429면 retryDelay 파싱해 백오프 재시도(최대 3회, 상한 26s).
  thinkingBudget 미지원(400)은 thinking 켠 채 폴백.
- 호출 절감: `ENCOUNTER_MAX_EXCHANGES` 3→2, 웹 `MAX_ROUNDS` 30→4.
- gunicorn `--timeout` 120→300 (백오프로 요청이 길어짐).
- `render.yaml`에서 `AI_RESEARCHER_DEMO_MODE` 제거 → Blueprint가 데모모드를
  되살리지 않게. 키 없으면 코드가 자동 데모 폴백.

**미해결/권고**
- 무료 등급에선 여전히 한 세션이 분당 5회를 넘겨 **느리거나(수십 초~수 분)
  일부 발언이 429로 남을 수 있음**. 원활하려면 **Gemini API 유료(pay-as-you-go)
  활성화**가 사실상 필요. 또는 세션 호출 수를 더 줄인 "라이트 모드" 검토.

### 2026-07-22 (라이트 모드 / 지난연구·내보내기 / 맵 말풍선 / 정직성·안전성)

이 시점부터 **디자인·애니메이션=Claude, 연산·백엔드=ChatGPT** 분담으로 진행
(핸드오프: `CHATGPT_HANDOFF.md`).

**GPT가 구현(연산)**: 라이트 파이프라인(`LITE_MODE`, `decide_offline`, 세션 5호출),
인메모리 세션 저장소 + `/api/sessions`·`/api/session/<id>`, 마크다운 내보내기
`/api/session/<id>/export` + 응답 `id`.

**Claude가 구현(디자인/애니메이션)**: 라이트 모드 기본 + 다크 토글, 맵 위 토큰
머리 위 말풍선 타이핑 + 바닥 그림자, "지난 연구 다시보기" UI, 내보내기·공유 버튼 +
`?session=` 자동 재생.

**정직성·안전성 업데이트(이번)**:
- (Claude) "신뢰도" 문구 → **"검토 진행도"**로 정직화(게이지/최종답변/목록).
  오류 경고 배지(`#warnBadge`) 틀 추가 — `has_errors`/`status`로 자동 노출.
  문서 정합(README 첫머리·모델명 3.5-flash, Dockerfile worker 1 + 데모 주석).
- (GPT에게 넘김) 세션 ID 무작위화 + 브라우저별 소유권(쿠키)로 프라이버시,
  오류 상태 분리(`status`/`has_errors`) + 실패 시 신뢰도 하향.

**GPT 진단 메모(중요, `CHATGPT_HANDOFF.md` 하단)** — 아직 남은 핵심 과제:
1. **평가 하네스**: 단일 Gemini 답변 vs 멀티에이전트 답변 비교(관련성·사실성·
   실행가능성·반박반영). "여러 에이전트가 낫다"는 핵심 가치가 아직 미입증.
2. **진짜 팩트체크**: Gemini 경로 팩트체커가 실제 검색 안 함(`tools` 무시).
   Grounding/검색 어댑터 연결 전엔 "검증 완료" 강조 금지.
3. Phase 4(사용자 개입: 에이전트 클릭 지시)는 미구현.
→ 다음 큰 방향은 **1(평가 하네스)** 를 GPT 작업으로 예약.

---

## 부록: 새 세션 진입 AI를 위한 체크리스트

프로젝트에 새로 붙었다면:
1. 이 파일 전체 읽기 (섹션 1~9)
2. 섹션 10 개발 로그 마지막 항목 확인
3. 코드 실행해서 현재 어디까지 되는지 확인 (`python main.py`)
4. 작업 후 반드시 섹션 10에 오늘 한 일과 다음 할 일 추가
5. 설계 결정을 바꿨다면 섹션 4에 이유와 함께 기록
