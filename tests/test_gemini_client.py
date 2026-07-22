"""Gemini 어댑터의 모델별 요청 경로 최적화 검증."""
import unittest
from unittest.mock import patch


class GeminiClientOptimizationTests(unittest.TestCase):
    @staticmethod
    def _client(model):
        from gemini_client import GeminiClient

        client = object.__new__(GeminiClient)
        client._model = model
        return client

    def test_gemini_3_skips_unsupported_disable_thinking_attempt(self):
        client = self._client("gemini-3.5-flash")
        with (
            patch.object(client, "_build_config", return_value="config") as build,
            patch.object(client, "_generate", return_value="응답") as generate,
        ):
            result = client._generate_best("질문", "시스템", 300)

        self.assertEqual(result, "응답")
        build.assert_called_once_with("시스템", 1024, False, False)
        generate.assert_called_once_with("질문", "config")

    def test_gemini_2_keeps_disable_thinking_fast_path(self):
        client = self._client("gemini-2.5-flash")
        with (
            patch.object(client, "_build_config", return_value="config") as build,
            patch.object(client, "_generate", return_value="응답") as generate,
        ):
            result = client._generate_best("질문", "시스템", 300)

        self.assertEqual(result, "응답")
        build.assert_called_once_with("시스템", 300, True, False)
        generate.assert_called_once_with("질문", "config")


if __name__ == "__main__":
    unittest.main()
