"""다중 Gemini 키 파싱·로테이션 구조 검증(네트워크 없음)."""

import os
import unittest


def _genai_available():
    try:
        from google import genai  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipUnless(_genai_available(), "google-genai 미설치")
class KeyRotationTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("GEMINI_MODEL", None)

    def test_comma_keys_build_multiple_clients_and_rotate(self):
        from gemini_client import GeminiClient

        c = GeminiClient("k1, k2 , k3")
        self.assertEqual(len(c._clients), 3)
        first = c._client
        self.assertTrue(c._switch_key())          # 다음 키로 전환
        self.assertIsNot(c._client, first)
        c._switch_key(); c._switch_key()           # 한 바퀴 돌아 원위치
        self.assertIs(c._client, first)

    def test_single_key_has_no_switch(self):
        from gemini_client import GeminiClient

        c = GeminiClient("only-one")
        self.assertEqual(len(c._clients), 1)
        self.assertFalse(c._switch_key())


if __name__ == "__main__":
    unittest.main()
