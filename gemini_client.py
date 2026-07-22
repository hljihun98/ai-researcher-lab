"""
Gemini 백엔드 어댑터.

기존 에이전트/오케스트레이터 코드는 전부 Anthropic식
`client.messages.create(model=, max_tokens=, system=, messages=[...])` 를
호출하고 `response.content[i].text` (블록에 .type=="text") 를 읽는다.
이 어댑터는 Google Gemini를 그 인터페이스로 감싸 코드 변경 없이 백엔드를 교체한다.

키는 절대 코드에 넣지 않는다. GEMINI_API_KEY 환경변수로만 주입.
모델명은 GEMINI_MODEL 환경변수(기본 config.GEMINI_MODEL)로 바꿀 수 있다.
"""
import os
import re
import time

try:
    from google import genai
    from google.genai import types
except Exception:  # pragma: no cover - 선택적 의존성
    genai = None
    types = None

import config


def _is_rate_limit(e) -> bool:
    s = str(e)
    return "RESOURCE_EXHAUSTED" in s or "429" in s


def _retry_delay(e, default=12) -> float:
    m = re.search(r"ret[Rr]etryDelay['\"]?\s*:?\s*['\"]?(\d+)", str(e))
    secs = int(m.group(1)) if m else default
    return min(secs, 25) + 1  # 상한 26초


class _Block:
    """Anthropic 응답 블록 흉내 (.type, .text)."""

    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _Response:
    def __init__(self, text: str):
        self.content = [_Block(text)]


class GeminiClient:
    """Anthropic 클라이언트와 같은 표면을 노출하는 Gemini 래퍼."""

    def __init__(self, api_key: str, model: str = None):
        if genai is None:
            raise RuntimeError(
                "google-genai 패키지가 설치되지 않았습니다. "
                "pip install google-genai"
            )
        self._client = genai.Client(api_key=api_key)
        self._model = model or os.environ.get("GEMINI_MODEL", config.GEMINI_MODEL)

    class _Messages:
        def __init__(self, parent):
            self.parent = parent

        def create(self, **kwargs):
            return self.parent._create(**kwargs)

    @property
    def messages(self):
        return self._Messages(self)

    def _build_config(self, system, max_tokens, disable_thinking):
        cfg_kwargs = {}
        if max_tokens:
            cfg_kwargs["max_output_tokens"] = int(max_tokens)
        if isinstance(system, str) and system.strip():
            cfg_kwargs["system_instruction"] = system
        # 2.5 계열은 기본 'thinking'이 출력 토큰을 먹어 빈 응답이 날 수 있어 끈다.
        # 단, 신형(3.x) 일부는 thinking을 못 꺼서 400을 낸다 → 폴백에서 켠 채로 재시도.
        if disable_thinking:
            try:
                cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            except Exception:
                pass
        try:
            return types.GenerateContentConfig(**cfg_kwargs)
        except TypeError:
            cfg_kwargs.pop("thinking_config", None)
            return types.GenerateContentConfig(**cfg_kwargs)

    def _generate(self, contents, cfg):
        resp = self._client.models.generate_content(
            model=self._model, contents=contents, config=cfg
        )
        return (getattr(resp, "text", None) or "").strip()

    def _generate_best(self, contents, system, max_tokens):
        """thinking을 끄고 먼저 시도(2.5), 실패/빈응답이면 thinking 허용(3.x)."""
        try:
            text = self._generate(contents, self._build_config(system, max_tokens, True))
            if text:
                return text
        except Exception as e:
            if _is_rate_limit(e):
                raise  # 429는 상위에서 백오프 재시도
            # 그 외 오류(예: thinkingBudget 미지원 400)는 폴백으로 진행
        budget = max(int(max_tokens or 0), 1024)
        return self._generate(contents, self._build_config(system, budget, False)) or ""

    def _create(self, **kwargs):
        # Anthropic 전용 인자(tools 등)는 Gemini에서 무시한다.
        system = kwargs.get("system")
        messages = kwargs.get("messages", [])
        max_tokens = kwargs.get("max_tokens")

        parts = []
        for m in messages:
            content = m.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for blk in content:
                    if isinstance(blk, dict) and isinstance(blk.get("text"), str):
                        parts.append(blk["text"])
        contents = "\n\n".join(parts) if parts else ""

        # 무료 등급 분당 한도(429)에 대비한 백오프 재시도.
        last_err = None
        for attempt in range(4):
            try:
                text = self._generate_best(contents, system, max_tokens)
                return _Response(text or "(빈 응답)")
            except Exception as e:
                last_err = e
                if _is_rate_limit(e) and attempt < 3:
                    time.sleep(_retry_delay(e))
                    continue
                return _Response(f"(Gemini 오류: {e})")
        return _Response(f"(Gemini 오류: {last_err})")
