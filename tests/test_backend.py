"""백엔드 선택 로직 테스트.

로컬에 Python이 없어 수동 실행이 안 되므로 CI가 build_runtime_client의
분기를 검증한다. (실제 Gemini 네트워크 호출은 하지 않는다.)
"""
import importlib
import os
import unittest


class BackendSelectionTests(unittest.TestCase):
    def setUp(self):
        for k in ("AI_RESEARCHER_DEMO_MODE", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
            os.environ.pop(k, None)
        import main

        importlib.reload(main)
        self.main = main

    def tearDown(self):
        for k in ("AI_RESEARCHER_DEMO_MODE", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
            os.environ.pop(k, None)

    def test_demo_mode_wins(self):
        os.environ["AI_RESEARCHER_DEMO_MODE"] = "1"
        os.environ["GEMINI_API_KEY"] = "dummy"
        self.assertEqual(type(self.main.build_runtime_client()).__name__, "DemoClient")

    def test_no_key_falls_back_to_demo(self):
        self.assertEqual(type(self.main.build_runtime_client()).__name__, "DemoClient")

    def test_gemini_key_selects_gemini(self):
        try:
            from google import genai  # noqa: F401
        except Exception:
            self.skipTest("google-genai 미설치")
        os.environ["GEMINI_API_KEY"] = "dummy-key-not-used-for-network"
        client = self.main.build_runtime_client()
        self.assertEqual(type(client).__name__, "GeminiClient")
        # 인터페이스 표면만 확인 (create 호출 안 함 → 네트워크 없음).
        self.assertTrue(hasattr(client, "messages"))


if __name__ == "__main__":
    unittest.main()
