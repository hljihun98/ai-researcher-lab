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

```bash
# 인자로 질문 전달
python main.py "소규모 스타트업에 가장 적합한 RAG 아키텍처는?"

# 또는 대화형
python main.py
```

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
- `logs/` — 실행 로그 (Phase 2 시각화 재생용)

## 로드맵

- [x] Phase 1: CLI 백엔드
- [ ] Phase 2: 정적 시각화 (말풍선)
- [ ] Phase 3: 이동 애니메이션
- [ ] Phase 4: 사용자 개입
