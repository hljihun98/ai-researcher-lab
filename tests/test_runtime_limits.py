"""배포 요청이 외부 API 재시도로 무한정 지연되지 않는지 검증."""

import time
import unittest
from unittest.mock import patch


class RuntimeLimitTests(unittest.TestCase):
    @staticmethod
    def _gemini_client():
        from gemini_client import GeminiClient

        client = object.__new__(GeminiClient)
        client._model = "gemini-3.5-flash"
        client._deadline = None
        return client

    def test_google_sdk_retries_are_not_stacked_with_adapter_retries(self):
        import config
        from gemini_client import GeminiClient

        with patch("gemini_client.genai.Client") as constructor:
            GeminiClient(api_key="test-key")

        http_options = constructor.call_args.kwargs["http_options"]
        self.assertEqual(
            http_options.timeout, config.GEMINI_REQUEST_TIMEOUT_SECONDS * 1000
        )
        self.assertEqual(http_options.retry_options.attempts, 1)

    def test_gemini_rate_limit_uses_bounded_attempt_count(self):
        import config

        client = self._gemini_client()
        error = RuntimeError("429 RESOURCE_EXHAUSTED")
        with (
            patch.object(config, "GEMINI_MAX_ATTEMPTS", 1),
            patch.object(client, "_generate_best", side_effect=error) as generate,
            patch("gemini_client.time.sleep") as sleep,
        ):
            response = client._create(
                system="시스템",
                messages=[{"role": "user", "content": "질문"}],
                max_tokens=300,
            )

        self.assertEqual(generate.call_count, 1)
        sleep.assert_not_called()
        self.assertIn("429", response.content[0].text)

    def test_expired_deadline_skips_remote_generation(self):
        client = self._gemini_client()
        client._deadline = time.monotonic() - 1
        with patch.object(client, "_generate_best") as generate:
            response = client._create(
                system="시스템",
                messages=[{"role": "user", "content": "질문"}],
                max_tokens=300,
            )

        generate.assert_not_called()
        self.assertIn("시간 예산", response.content[0].text)

    def test_near_deadline_does_not_start_another_http_request(self):
        import config

        client = self._gemini_client()
        client._deadline = (
            time.monotonic() + config.GEMINI_REQUEST_TIMEOUT_SECONDS - 1
        )
        with patch.object(client, "_generate_best") as generate:
            response = client._create(
                system="시스템",
                messages=[{"role": "user", "content": "질문"}],
                max_tokens=300,
            )

        generate.assert_not_called()
        self.assertIn("남은 시간", response.content[0].text)

    def test_web_session_applies_deadline_to_client(self):
        import config
        from main import DemoClient
        import server

        class DeadlineDemoClient(DemoClient):
            def set_deadline(self, deadline):
                self.deadline = deadline

        client = DeadlineDemoClient()
        before = time.monotonic()
        with (
            patch.object(config, "LITE_MODE", True),
            patch.object(config, "WEB_SESSION_BUDGET_SECONDS", 60),
            patch.object(server, "build_runtime_client", return_value=client),
        ):
            state = server.run_session_web("진단 질문")

        self.assertGreaterEqual(client.deadline, before + 59)
        self.assertTrue(state.final_answer)

    def test_render_defaults_to_lite_bounded_runtime(self):
        import config

        render_config = (config.PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("key: AI_RESEARCHER_LITE", render_config)
        self.assertIn("key: AI_RESEARCHER_SESSION_BUDGET_SECONDS", render_config)
        self.assertIn("key: GEMINI_MAX_ATTEMPTS", render_config)

    def test_unexpected_api_failure_returns_json(self):
        import server

        server.app.config.update(TESTING=True)
        with (
            patch.object(server, "run_session_web", side_effect=RuntimeError("boom")),
            patch.object(server.app.logger, "exception") as log_exception,
        ):
            response = server.app.test_client().post(
                "/api/run", json={"question": "진단 질문"}
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.get_json(), {"error": "연구 실행 중 서버 오류가 발생했습니다."}
        )
        log_exception.assert_called_once()


if __name__ == "__main__":
    unittest.main()
