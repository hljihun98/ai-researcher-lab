"""개발용 평가 하네스의 네트워크 없는 구조 검증."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class EvalHarnessTests(unittest.TestCase):
    def test_blind_order_is_deterministic_and_alternates(self):
        from eval.harness import _blind_answers

        _, even_map = _blind_answers(0, "단일", "멀티")
        _, odd_map = _blind_answers(1, "단일", "멀티")

        self.assertEqual(even_map, {"A": "baseline", "B": "multi"})
        self.assertEqual(odd_map, {"A": "multi", "B": "baseline"})

    def test_judge_scores_are_mapped_back_from_blind_labels(self):
        from eval.harness import parse_judgment

        raw = """```json
        {
          "A": {"relevance": 2, "factuality": 2, "actionability": 3, "completeness": 3},
          "B": {"relevance": 5, "factuality": 4, "actionability": 5, "completeness": 4},
          "winner": "B",
          "reason": "B가 더 구체적이다."
        }
        ```"""
        judgment = parse_judgment(raw, {"A": "multi", "B": "baseline"})

        self.assertTrue(judgment["valid"])
        self.assertEqual(judgment["winner"], "baseline")
        self.assertEqual(judgment["baseline_scores"]["total"], 18)
        self.assertEqual(judgment["multi_scores"]["total"], 10)

    def test_demo_evaluation_writes_results_structure(self):
        from eval.harness import run_evaluation

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "results.json"
            with patch.dict(os.environ, {"AI_RESEARCHER_DEMO_MODE": "1"}):
                payload = run_evaluation(
                    n=1,
                    delay=0,
                    results_path=output,
                    printer=lambda _: None,
                )

            saved = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(saved, payload)
        self.assertIsInstance(saved["results"], list)
        self.assertEqual(len(saved["results"]), 1)
        row = saved["results"][0]
        required = {
            "category",
            "question",
            "baseline_answer",
            "multi_answer",
            "blind_order",
            "baseline_scores",
            "multi_scores",
            "winner",
            "reason",
            "judgment_valid",
        }
        self.assertTrue(required.issubset(row))
        self.assertIn("multi_win_rate_pct", saved["summary"])
        self.assertFalse(row["judgment_valid"])


if __name__ == "__main__":
    unittest.main()
