"""실시간 연구 SSE 이벤트와 기존 세션 저장 계약 검증."""

import json
import unittest
from unittest.mock import patch


class StreamTests(unittest.TestCase):
    def setUp(self):
        import config
        import server

        self.config = config
        self.server = server
        self.server.app.config.update(TESTING=True)

    def _events(self, question="주말에 시작할 창작 취미를 추천해줘"):
        from main import DemoClient

        client = DemoClient()
        with (
            patch.object(self.config, "LITE_MODE", True),
            patch.object(self.server, "build_runtime_client", return_value=client),
        ):
            events = list(
                self.server.iter_session_events(
                    question,
                    owner="stream-test-owner",
                )
            )
        return events, client

    def test_generator_emits_round_utterances_then_final(self):
        events, client = self._events()
        event_types = [event["type"] for event in events]

        self.assertEqual(event_types[0], "round")
        self.assertEqual(event_types[-1], "final")
        self.assertEqual(event_types.count("round"), 3)
        self.assertEqual(event_types.count("utterance"), 4)
        self.assertEqual(len(client.calls), 5)

        round_indexes = [
            event["index"] for event in events if event["type"] == "round"
        ]
        self.assertEqual(round_indexes, [1, 2, 3])

    def test_round_is_yielded_before_first_agent_call(self):
        from main import DemoClient

        client = DemoClient()
        with (
            patch.object(self.config, "LITE_MODE", True),
            patch.object(self.server, "build_runtime_client", return_value=client),
        ):
            events = self.server.iter_session_events(
                "첫 이벤트 즉시 전송 확인",
                owner="stream-test-owner",
            )
            first = next(events)
            events.close()

        self.assertEqual(first["type"], "round")
        self.assertEqual(client.calls, [])

    def test_each_round_starts_with_non_reply_at_valid_location(self):
        events, _ = self._events("원격 팀의 회의를 줄이는 방법은?")

        for index, event in enumerate(events):
            if event["type"] != "round":
                continue
            self.assertEqual(len(event["agents"]), 2)
            self.assertIn(event["location"], self.config.LOCATIONS)
            first_utterance = events[index + 1]
            self.assertEqual(first_utterance["type"], "utterance")
            self.assertIsNone(first_utterance["responds_to"])
            self.assertEqual(first_utterance["location"], event["location"])

        for event in events:
            if event["type"] == "utterance":
                self.assertIn(event["location"], self.config.LOCATIONS)

    def test_final_event_has_id_and_saved_session(self):
        events, _ = self._events()
        final = events[-1]

        self.assertTrue(final["id"])
        self.assertEqual(final["status"], "ok")
        self.assertFalse(final["has_errors"])
        self.assertTrue(final["final_answer"].strip())
        self.assertIn("confidence_score", final)
        self.assertIn("confidence_threshold", final)

        saved = self.server._get_stored_session(final["id"])
        self.assertIsNotNone(saved)
        self.assertEqual(saved["id"], final["id"])
        self.assertEqual(saved["question"], "주말에 시작할 창작 취미를 추천해줘")

    def test_stream_route_returns_sse_and_stores_once(self):
        from main import DemoClient

        client = DemoClient()
        flask_client = self.server.app.test_client()
        with (
            patch.object(self.config, "LITE_MODE", True),
            patch.object(self.server, "build_runtime_client", return_value=client),
            patch.object(
                self.server,
                "_store_session",
                wraps=self.server._store_session,
            ) as store,
        ):
            response = flask_client.post(
                "/api/run/stream",
                json={"question": "집중력을 높이는 휴식 방법은?"},
                buffered=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/event-stream")
        self.assertEqual(response.headers["Cache-Control"], "no-cache")
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")
        store.assert_called_once()

        data_lines = [
            line[6:]
            for line in response.get_data(as_text=True).splitlines()
            if line.startswith("data: ")
        ]
        self.assertTrue(data_lines)
        events = [json.loads(line) for line in data_lines]
        self.assertEqual(events[0]["type"], "round")
        self.assertEqual(events[-1]["type"], "final")
        self.assertTrue(events[-1]["id"])

    def test_stream_route_rejects_empty_question_before_opening_stream(self):
        response = self.server.app.test_client().post(
            "/api/run/stream",
            json={"question": "  "},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "질문이 비어있습니다."})

    def test_stream_route_emits_error_event_on_fatal_failure(self):
        with (
            patch.object(
                self.server,
                "build_runtime_client",
                side_effect=RuntimeError("fatal setup failure"),
            ),
            patch.object(self.server.app.logger, "exception") as log_exception,
        ):
            response = self.server.app.test_client().post(
                "/api/run/stream",
                json={"question": "치명 오류 경로 확인"},
                buffered=True,
            )

        data_lines = [
            line[6:]
            for line in response.get_data(as_text=True).splitlines()
            if line.startswith("data: ")
        ]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(data_lines), 1)
        self.assertEqual(
            json.loads(data_lines[0]),
            {
                "type": "error",
                "message": "연구 실행 중 서버 오류가 발생했습니다.",
            },
        )
        log_exception.assert_called_once()

    def test_batch_route_still_stores_once(self):
        from main import DemoClient

        with (
            patch.object(self.config, "LITE_MODE", True),
            patch.object(
                self.server,
                "build_runtime_client",
                return_value=DemoClient(),
            ),
            patch.object(
                self.server,
                "_store_session",
                wraps=self.server._store_session,
            ) as store,
        ):
            response = self.server.app.test_client().post(
                "/api/run",
                json={"question": "기존 일괄 경로 확인"},
            )

        self.assertEqual(response.status_code, 200)
        store.assert_called_once()
        self.assertTrue(response.get_json()["id"])


if __name__ == "__main__":
    unittest.main()
