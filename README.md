# AI Researcher Lab

여러 명의 전문화된 AI 연구원이 서로 대화하며 사용자 질문에 답을 정제해가는 시스템.
카이로소프트 스타일 2D 게임으로 시각화하는 게 최종 목표이지만, 현재는 **Phase 1 — CLI 백엔드** 단계입니다.

> **개발자/AI 어시스턴트라면 먼저 `PROJECT_MEMO.md`를 읽으세요.**
> 프로젝트의 전체 방향과 현재 상태가 거기 있습니다.

## 설치

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY='sk-ant-...'
```

## 실행

### 데모 모드(배포/로컬 검증용)
```bash
set AI_RESEARCHER_DEMO_MODE=1
python main.py "소규모 스타트업에 가장 적합한 RAG 아키텍처는?"
```

### 실제 Anthropic API 사용
```bash
set ANTHROPIC_API_KEY=sk-ant-...
python main.py "소규모 스타트업에 가장 적합한 RAG 아키텍처는?"
```

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
   `ANTHROPIC_API_KEY`를 환경변수로 추가.

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
- `prompts/` — 각 에이전트 시스템 프롬프트
- `agents/` — 에이전트 클래스
- `orchestrator.py` — 매 라운드 지휘
- `conversation.py` — 대화 상태
- `main.py` — CLI 엔트리
- `server.py` — 웹 서버 (Flask) + 브라우저 UI
- `logs/` — 실행 로그 (Phase 2 시각화 재생용)

## 로드맵

- [x] Phase 1: CLI 백엔드
- [ ] Phase 2: 정적 시각화 (말풍선)
- [ ] Phase 3: 이동 애니메이션
- [ ] Phase 4: 사용자 개입
