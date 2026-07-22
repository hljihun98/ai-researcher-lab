"""단일 LLM 답변과 멀티에이전트 답변을 블라인드 비교하는 평가 CLI."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Iterable

import config
from main import build_runtime_client


EVAL_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = EVAL_DIR / "questions.json"
RESULTS_PATH = EVAL_DIR / "results.json"
METRICS = ("relevance", "factuality", "actionability", "completeness")
METRIC_LABELS = {
    "relevance": "관련성",
    "factuality": "사실성",
    "actionability": "실행가능성",
    "completeness": "완결성",
}
BASELINE_SYSTEM = "너는 전문가다. 질문에 정확하고 실행 가능하게 답하라."
JUDGE_SYSTEM = (
    "너는 엄격하고 공정한 답변 품질 심판이다. 답변 작성 주체를 추측하지 말고 "
    "제공된 내용만 평가하라. 반드시 요청한 JSON 객체 하나만 출력하라."
)


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict[str, str]]:
    """벤치마크 질문 파일을 읽고 최소 스키마를 검증한다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("질문 파일은 비어 있지 않은 JSON 배열이어야 합니다.")
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"질문 {index + 1}은 객체여야 합니다.")
        if not isinstance(item.get("category"), str) or not item["category"].strip():
            raise ValueError(f"질문 {index + 1}의 category가 비어 있습니다.")
        if not isinstance(item.get("q"), str) or not item["q"].strip():
            raise ValueError(f"질문 {index + 1}의 q가 비어 있습니다.")
    return data


def _extract_text(response: Any) -> str:
    text = "".join(
        block.text
        for block in getattr(response, "content", [])
        if getattr(block, "type", None) == "text"
    ).strip()
    if not text:
        raise ValueError("LLM이 텍스트 응답을 반환하지 않았습니다.")
    return text


def _call_model(client: Any, model: str, system: str, prompt: str, max_tokens: int) -> str:
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_text(response)


def generate_baseline(client: Any, question: str, model: str) -> str:
    """비교 기준인 단일 모델 1회 답변을 생성한다."""
    return _call_model(
        client,
        model,
        BASELINE_SYSTEM,
        question,
        max(config.MAX_TOKENS_PER_TURN * 4, 1200),
    )


def generate_multi_agent(question: str) -> str:
    """웹앱과 동일한 멀티에이전트 파이프라인의 최종 답변을 생성한다."""
    from server import run_session_web

    state = run_session_web(question)
    answer = (state.final_answer or "").strip()
    if not answer:
        raise ValueError("멀티에이전트 파이프라인이 최종 답변을 반환하지 않았습니다.")
    return answer


def _blind_answers(index: int, baseline: str, multi: str) -> tuple[dict[str, str], dict[str, str]]:
    """질문 인덱스의 홀짝으로 결정적인 블라인드 순서를 만든다."""
    if index % 2 == 0:
        return {"A": baseline, "B": multi}, {"A": "baseline", "B": "multi"}
    return {"A": multi, "B": baseline}, {"A": "multi", "B": "baseline"}


def _judge_prompt(question: str, answers: dict[str, str]) -> str:
    metric_lines = "\n".join(
        f"- {key} ({label}): 1~5 정수" for key, label in METRIC_LABELS.items()
    )
    return f"""[질문]
{question}

[답변 A]
{answers['A']}

[답변 B]
{answers['B']}

두 답변을 독립적으로 평가하라.
{metric_lines}

winner는 반드시 "A", "B", "tie" 중 하나로 정하고 reason은 한 줄로 작성하라.
다음 스키마와 정확히 같은 JSON 객체만 출력하라:
{{
  "A": {{"relevance": 1, "factuality": 1, "actionability": 1, "completeness": 1}},
  "B": {{"relevance": 1, "factuality": 1, "actionability": 1, "completeness": 1}},
  "winner": "A",
  "reason": "한 줄 근거"
}}"""


def _first_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for position, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[position:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("심판 응답에서 JSON 객체를 찾지 못했습니다.")


def _validated_scores(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError(f"심판의 {label} 점수가 객체가 아닙니다.")
    scores = {}
    for metric in METRICS:
        score = value.get(metric)
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError(f"심판의 {label}.{metric} 점수가 숫자가 아닙니다.")
        integer_score = int(score)
        if integer_score != score or not 1 <= integer_score <= 5:
            raise ValueError(f"심판의 {label}.{metric} 점수는 1~5 정수여야 합니다.")
        scores[metric] = integer_score
    scores["total"] = sum(scores.values())
    return scores


def parse_judgment(text: str, label_map: dict[str, str]) -> dict[str, Any]:
    """심판 JSON을 검증하고 블라인드 라벨을 실제 답변 종류로 되돌린다."""
    raw = _first_json_object(text)
    label_scores = {
        "A": _validated_scores(raw.get("A"), "A"),
        "B": _validated_scores(raw.get("B"), "B"),
    }
    raw_winner = str(raw.get("winner", "")).strip()
    winner_key = raw_winner.upper() if raw_winner.lower() != "tie" else "tie"
    if winner_key not in ("A", "B", "tie"):
        raise ValueError("심판 winner는 A, B, tie 중 하나여야 합니다.")
    reason = str(raw.get("reason", "")).strip()
    if not reason:
        raise ValueError("심판 reason이 비어 있습니다.")

    scores_by_source = {
        label_map[label]: scores for label, scores in label_scores.items()
    }
    winner = "tie" if winner_key == "tie" else label_map[winner_key]
    return {
        "valid": True,
        "baseline_scores": scores_by_source["baseline"],
        "multi_scores": scores_by_source["multi"],
        "winner": winner,
        "reason": reason,
    }


def judge_answers(
    client: Any,
    question: str,
    baseline: str,
    multi: str,
    index: int,
    model: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    answers, label_map = _blind_answers(index, baseline, multi)
    raw_text = _call_model(
        client,
        model,
        JUDGE_SYSTEM,
        _judge_prompt(question, answers),
        max(config.MAX_TOKENS_PER_TURN * 3, 900),
    )
    try:
        return parse_judgment(raw_text, label_map), label_map
    except ValueError as error:
        # DemoClient는 심판 전용 JSON 대본이 없다. 실제 모델의 형식 오류도 전체 평가를
        # 중단시키지 않고 무효 판정으로 남겨 비싼 앞선 호출 결과를 보존한다.
        neutral = {metric: 3 for metric in METRICS}
        neutral["total"] = sum(neutral.values())
        return (
            {
                "valid": False,
                "baseline_scores": dict(neutral),
                "multi_scores": dict(neutral),
                "winner": "tie",
                "reason": f"심판 JSON 파싱 실패: {error}",
            },
            label_map,
        )


def aggregate_results(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(results)
    valid_rows = [row for row in rows if row["judgment_valid"]]
    wins = {"baseline": 0, "multi": 0, "tie": 0}
    for row in valid_rows:
        wins[row["winner"]] += 1

    judged_count = len(valid_rows)
    differences = {}
    for metric in METRICS:
        if judged_count:
            difference = sum(
                row["multi_scores"][metric] - row["baseline_scores"][metric]
                for row in valid_rows
            ) / judged_count
        else:
            difference = 0.0
        differences[metric] = round(difference, 2)

    return {
        "question_count": len(rows),
        "judged_count": judged_count,
        "invalid_judgment_count": len(rows) - judged_count,
        "wins": wins,
        "multi_win_rate_pct": round(
            (wins["multi"] / judged_count * 100) if judged_count else 0.0, 1
        ),
        "average_score_difference_multi_minus_baseline": differences,
    }


def _pause(delay: float, sleep_fn: Callable[[float], None]) -> None:
    if delay > 0:
        sleep_fn(delay)


@contextmanager
def _model_override(model: str | None):
    previous_env = os.environ.get("GEMINI_MODEL")
    previous_anthropic_model = config.MODEL_NAME
    if model:
        os.environ["GEMINI_MODEL"] = model
        config.MODEL_NAME = model
    try:
        yield
    finally:
        config.MODEL_NAME = previous_anthropic_model
        if previous_env is None:
            os.environ.pop("GEMINI_MODEL", None)
        else:
            os.environ["GEMINI_MODEL"] = previous_env


def _runtime_model(client: Any, requested_model: str | None) -> str:
    if requested_model:
        return requested_model
    if type(client).__name__ == "GeminiClient":
        return getattr(client, "_model", config.GEMINI_MODEL)
    if type(client).__name__ == "DemoClient":
        return "demo-model"
    return config.MODEL_NAME


def run_evaluation(
    n: int | None = None,
    delay: float = 3.0,
    model: str | None = None,
    questions_path: Path = QUESTIONS_PATH,
    results_path: Path = RESULTS_PATH,
    sleep_fn: Callable[[float], None] = time.sleep,
    printer: Callable[[str], None] = print,
) -> dict[str, Any]:
    """평가를 실행하고 콘솔 및 JSON 파일로 결과를 남긴다."""
    if n is not None and n < 1:
        raise ValueError("--n은 1 이상이어야 합니다.")
    if delay < 0:
        raise ValueError("--delay는 0 이상이어야 합니다.")

    questions = load_questions(questions_path)
    selected = questions if n is None else questions[:n]
    if not selected:
        raise ValueError("평가할 질문이 없습니다.")

    rows = []
    with _model_override(model):
        client = build_runtime_client()
        runtime_model = _runtime_model(client, model)

        for index, item in enumerate(selected):
            question = item["q"]
            baseline = generate_baseline(client, question, runtime_model)
            _pause(delay, sleep_fn)
            multi = generate_multi_agent(question)
            _pause(delay, sleep_fn)
            judgment, label_map = judge_answers(
                client, question, baseline, multi, index, runtime_model
            )

            row = {
                "index": index + 1,
                "category": item["category"],
                "question": question,
                "baseline_answer": baseline,
                "multi_answer": multi,
                "blind_order": label_map,
                "baseline_scores": judgment["baseline_scores"],
                "multi_scores": judgment["multi_scores"],
                "winner": judgment["winner"],
                "reason": judgment["reason"],
                "judgment_valid": judgment["valid"],
            }
            rows.append(row)
            if index < len(selected) - 1:
                _pause(delay, sleep_fn)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": runtime_model,
        "delay_seconds": delay,
        "results": rows,
        "summary": aggregate_results(rows),
    }
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print_report(payload, printer=printer)
    return payload


def print_report(payload: dict[str, Any], printer: Callable[[str], None] = print) -> None:
    printer("\nAI Researcher Lab 평가 결과")
    printer("-" * 63)
    printer(f"{'#':>2}  {'카테고리':<10} {'단일':>4} {'멀티':>4}  승자")
    printer("-" * 63)
    winner_labels = {"baseline": "단일", "multi": "멀티", "tie": "동점"}
    for row in payload["results"]:
        validity = "" if row["judgment_valid"] else " (무효)"
        printer(
            f"{row['index']:>2}  {row['category']:<10} "
            f"{row['baseline_scores']['total']:>4} "
            f"{row['multi_scores']['total']:>4}  "
            f"{winner_labels[row['winner']]}{validity}"
        )

    summary = payload["summary"]
    printer("-" * 63)
    printer(
        f"유효 심판 {summary['judged_count']}/{summary['question_count']} · "
        f"멀티 승률 {summary['multi_win_rate_pct']:.1f}% · "
        f"승/패/무 {summary['wins']['multi']}/"
        f"{summary['wins']['baseline']}/{summary['wins']['tie']}"
    )
    differences = summary["average_score_difference_multi_minus_baseline"]
    diff_text = ", ".join(
        f"{METRIC_LABELS[key]} {differences[key]:+.2f}" for key in METRICS
    )
    printer(f"평균 점수 차이(멀티-단일): {diff_text}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="단일 모델과 멀티에이전트 답변을 LLM 심판으로 비교합니다."
    )
    parser.add_argument("--n", type=int, default=None, help="앞에서부터 평가할 질문 수")
    parser.add_argument(
        "--delay", type=float, default=3.0, help="평가 단계 사이 지연(초, 기본 3)"
    )
    parser.add_argument("--model", help="Gemini/Anthropic 모델명 임시 오버라이드")
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS_PATH,
        help="결과 JSON 경로(기본 eval/results.json)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_evaluation(
        n=args.n,
        delay=args.delay,
        model=args.model,
        results_path=args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
