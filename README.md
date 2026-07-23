# AI Researcher Lab

여러 명의 전문화된 AI 연구원이 서로 대화하며 사용자 질문에 답을 정제해가는 시스템.
카이로소프트 스타일 2D 게임으로 시각화하는 게 최종 목표입니다. 현재는 **웹앱(Flask)** 으로 배포되어,
연구원들이 **연구소 맵에서 걸어다니며 대화**하는 것을 브라우저에서 볼 수 있습니다(Phase 3 수준).

> **개발자/AI 어시스턴트라면 먼저 `PROJECT_MEMO.md`를 읽으세요.**
> 프로젝트의 전체 방향과 현재 상태가 거기 있습니다.

## 설치

```bash
pip install -r requirements.txt
```

## 백엔드 (LLM)

- **실시간 기본**: Google **Gemini** (`GEMINI_API_KEY`)
- 폴백: Anthropic Claude (`ANTHROPIC_API_KEY`, Gemini 키 없을 때만)
- 키 없음/데모: 캔드 응답

> ⚠️ 실제 키는 `.env`(gitignore됨)나 배포 대시보드 환경변수로만 넣으세요. 소스코드/커밋 금지.

## 실행

### 데모 모드(배포/로컬 검증용)
```bash
set AI_RESEARCHER_DEMO_MODE=1
python main.py "소규모 스타트업에 가장 적합한 RAG 아키텍처는?"
```

### 실시간 (Gemini)
```bash
set GEMINI_API_KEY=your-gemini-key
python main.py "소규모 스타트업에 가장 적합한 RAG 아키텍처는?"
```
모델 변경: `set GEMINI_MODEL=gemini-2.0-flash` (기본 `gemini-2.0-flash-lite`, 무료 하루한도 큼).

### 웹앱 (브라우저)
```bash
pip install -r requirements.txt
python server.py          # http://localhost:8000
```
질문을 입력하면 에이전트 대화와 최종 답변이 화면에 표시됩니다.
API 키가 없으면 자동으로 데모 모드로 동작합니다.

### Docker 실행 (웹 서버)
```bash
docker build -t ai-researcher-lab .
docker run --rm -p 8000:8000 -e AI_RESEARCHER_DEMO_MODE=1 ai-researcher-lab
# → http://localhost:8000
```

## 배포 (Render web 서비스)

이 앱은 파이썬 웹 서버입니다. **GitHub Pages로는 실행할 수 없습니다**(Pages는 정적 파일 전용).
배포 URL은 `https://<서비스이름>.onrender.com` 형태입니다.

1. https://render.com 에서 GitHub 계정 연결
2. **New → Blueprint** → 이 저장소 선택 (루트의 `render.yaml`을 자동 인식)
3. 배포되면 위 형태의 URL이 발급됨. 기본은 데모 모드(키 불필요).
4. 실시간으로 돌리려면 Render 대시보드에서 `AI_RESEARCHER_DEMO_MODE`를 지우고
   `GEMINI_API_KEY`를 환경변수로 추가. (`onrender.com` 대시보드 → Environment)
5. 무료 Gemini 등급에서는 `AI_RESEARCHER_LITE=1`을 유지. `render.yaml`은 요청이
   Gunicorn 300초 제한에 닿지 않도록 세션 60초, 개별 Gemini 요청 20초, 최대 1회 시도로
   설정되어 있다. 대시보드에서 만든 기존 서비스라면 이 환경변수들을 직접 추가해야 한다.

- GitHub Actions(`.github/workflows/deploy.yml`): main 푸시 시 테스트 + 데모 스모크 + Docker 빌드 검증.

## 출력 예시

```
━━━ 라운드 1 ━━━
[지휘부] 신뢰도 25/100 (+5) · encounter
  → 리서처 × 비평가 @ 📋 화이트보드
  [·] 리서처 @whiteboard: 벡터DB + BM25 하이브리드로 시작하면 어때요?
  [!] 비평가 @whiteboard: 임베딩 비용 계산 하셨어요?
  [·] 리서처 @whiteboard: OpenAI ada-002는 100만 토큰에 $0.1이라 저렴해요.
...
```

## 프로젝트 구조

- `PROJECT_MEMO.md` — **프로젝트의 헌법**. 방향/결정/상태
- `config.py` — 모델명, 임계값, 에이전트 목록
- `gemini_client.py` — Gemini 백엔드 어댑터 (Anthropic 인터페이스 호환)
- `prompts/` — 각 에이전트 시스템 프롬프트
- `agents/` — 에이전트 클래스
- `orchestrator.py` — 매 라운드 지휘
- `conversation.py` — 대화 상태
- `main.py` — CLI 엔트리
- `server.py` — 웹 서버 (Flask) + 브라우저 UI
- `logs/` — 실행 로그 (Phase 2 시각화 재생용)

## 에셋 출처 (Credits)

연구소 맵의 픽셀아트 스프라이트(캐릭터·바닥·가구)는 **Pixel Agents**
(https://github.com/pixel-agents-hq/pixel-agents, © 2026 Pablo De Lucca, **MIT License**)
에서 가져와 사용합니다. 렌더링 코드는 본 프로젝트에서 자체 작성했습니다.
자세한 내용: [static/assets/CREDITS.md](static/assets/CREDITS.md).

## 로드맵

- [x] Phase 1: CLI 백엔드
- [x] Phase 1.5: 웹앱(Flask) + 브라우저 UI + 배포(Render)
- [x] Phase 2: 정적 시각화 (색상 말풍선 + 타이핑 효과)
- [x] Phase 3: 이동 애니메이션 (연구소 맵에서 에이전트가 걸어가 마주침)
- [~] Phase 2.5: 지난 연구 다시보기 (세션 재생) — 프론트 완료, 저장 백엔드 진행 중
- [ ] Phase 4: 사용자 개입 (에이전트 클릭 지시)
