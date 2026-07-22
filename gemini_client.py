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


class _SessionDeadlineExceeded(RuntimeError):
    """웹 세션 시간 예산을 모두 사용했을 때 원격 호출을 중단한다."""


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
        http_options = None
        try:
            retry_options = types.HttpRetryOptions(attempts=1)
            http_options = types.HttpOptions(
                timeout=config.GEMINI_REQUEST_TIMEOUT_SECONDS * 1000,
                retry_options=retry_options,
            )
        except (AttributeError, TypeError, ValueError):
            try:
                http_options = types.HttpOptions(
                    timeout=config.GEMINI_REQUEST_TIMEOUT_SECONDS * 1000
                )
            except (AttributeError, TypeError, ValueError):
                pass

        client_kwargs = {"api_key": api_key}
        if http_options is not None:
            client_kwargs["http_options"] = http_options
        try:
            self._client = genai.Client(**client_kwargs)
        except TypeError:
            # 초기 google-genai SDK가 http_options를 받지 않는 경우의 호환 경로.
            self._client = genai.Client(api_key=api_key)
        self._model = model or os.environ.get("GEMINI_MODEL", config.GEMINI_MODEL)
        self._deadline = None

    def set_deadline(self, deadline: float | None) -> None:
        """time.monotonic() 기준 세션 마감 시각을 설정한다."""
        self._deadline = deadline

    def _ensure_time_remaining(self) -> None:
        deadline = getattr(self, "_deadline", None)
        if deadline is None:
            return
        # 마감 직전에 새 20초 HTTP 요청을 시작하면 세션 예산을 초과할 수 있다.
        # 요청 제한만큼의 시간이 남지 않았으면 원격 호출 없이 부분 결과로 마무리한다.
        if time.monotonic() + config.GEMINI_REQUEST_TIMEOUT_SECONDS >= deadline:
            raise _SessionDeadlineExceeded(
                "세션 시간 예산의 남은 시간이 새 요청 제한보다 짧습니다."
            )

    class _Messages:
        def __init__(self, parent):
            self.parent = parent

        def create(self, **kwargs):
            return self.parent._create(**kwargs)

    @property
    def messages(self):
        return self._Messages(self)

    @staticmethod
    def _google_search_tool():
        """설치된 SDK가 지원하는 Google Search 도구를 반환한다."""
        try:
            return types.Tool(google_search=types.GoogleSearch())
        except (AttributeError, TypeError, ValueError):
            try:
                return types.Tool(
                    google_search_retrieval=types.GoogleSearchRetrieval()
                )
            except (AttributeError, TypeError, ValueError):
                return None

    def _build_config(self, system, max_tokens, disable_thinking, grounding=False):
        cfg_kwargs = {}
        if max_tokens:
            cfg_kwargs["max_output_tokens"] = int(max_tokens)
        if isinstance(system, str) and system.strip():
            cfg_kwargs["system_instruction"] = system
        if grounding:
            search_tool = self._google_search_tool()
            if search_tool is not None:
                cfg_kwargs["tools"] = [search_tool]
        # 2.5 계열은 기본 'thinking'이 출력 토큰을 먹어 빈 응답이 날 수 있어 끈다.
        # 단, 신형(3.x) 일부는 thinking을 못 꺼서 400을 낸다 → 폴백에서 켠 채로 재시도.
        if disable_thinking:
            try:
                cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            except Exception:
                pass
        try:
            return types.GenerateContentConfig(**cfg_kwargs)
        except (TypeError, ValueError):
            if "thinking_config" in cfg_kwargs:
                cfg_kwargs.pop("thinking_config")
                try:
                    return types.GenerateContentConfig(**cfg_kwargs)
                except (TypeError, ValueError):
                    pass
            # 검색 도구 필드를 모르는 구형 SDK에서도 일반 생성은 계속한다.
            cfg_kwargs.pop("tools", None)
            return types.GenerateContentConfig(**cfg_kwargs)

    def _generate(self, contents, cfg):
        self._ensure_time_remaining()
        resp = self._client.models.generate_content(
            model=self._model, contents=contents, config=cfg
        )
        return (getattr(resp, "text", None) or "").strip()

    def _generate_best(self, contents, system, max_tokens, grounding=False):
        """2.x는 thinking 비활성화를 우선하고 3.x는 기본 thinking을 바로 사용한다."""
        model_name = self._model.rsplit("/", 1)[-1].lower()
        is_gemini_3 = bool(re.match(r"^gemini-3(?:[.\-]|$)", model_name))
        if not is_gemini_3:
            try:
                text = self._generate(
                    contents,
                    self._build_config(system, max_tokens, True, grounding),
                )
                if text:
                    return text
            except Exception as e:
                if _is_rate_limit(e):
                    raise  # 429는 상위에서 백오프 재시도
                # thinkingBudget 미지원 등은 기본 thinking 설정으로 폴백

        # Gemini 3.x는 thinking_budget=0이 거부될 수 있으므로 실패 요청을 먼저 보내지 않는다.
        budget = max(int(max_tokens or 0), 1024)
        return (
            self._generate(
                contents,
                self._build_config(system, budget, False, grounding),
            )
            or ""
        )

    def _create(self, **kwargs):
        # Anthropic 전용 인자(tools 등)는 Gemini에서 무시한다.
        system = kwargs.get("system")
        messages = kwargs.get("messages", [])
        max_tokens = kwargs.get("max_tokens")
        grounding = kwargs.get("grounding") is True

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
        max_attempts = config.GEMINI_MAX_ATTEMPTS
        for attempt in range(max_attempts):
            try:
                self._ensure_time_remaining()
                try:
                    text = self._generate_best(
                        contents, system, max_tokens, grounding=grounding
                    )
                    if grounding and not text:
                        text = self._generate_best(
                            contents, system, max_tokens, grounding=False
                        )
                except Exception as grounding_error:
                    if (
                        isinstance(grounding_error, _SessionDeadlineExceeded)
                        or not grounding
                        or _is_rate_limit(grounding_error)
                    ):
                        raise
                    # 검색 미지원/실패 시 동일 요청을 일반 생성으로 조용히 폴백한다.
                    text = self._generate_best(
                        contents, system, max_tokens, grounding=False
                    )
                return _Response(text or "(빈 응답)")
            except Exception as e:
                last_err = e
                if _is_rate_limit(e) and attempt < max_attempts - 1:
                    delay = _retry_delay(e)
                    deadline = getattr(self, "_deadline", None)
                    if deadline is not None and time.monotonic() + delay >= deadline:
                        return _Response(
                            "(Gemini 오류: 세션 시간 예산 내에 재시도할 수 없습니다.)"
                        )
                    time.sleep(delay)
                    continue
                return _Response(f"(Gemini 오류: {e})")
        return _Response(f"(Gemini 오류: {last_err})")
