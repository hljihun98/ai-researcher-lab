"""
오케스트레이터: 매 라운드 다음 행동을 결정.
- 어느 에이전트 둘을 만나게 할지
- 어디서 만나게 할지
- 아니면 이제 조율자로 마무리할지

출력은 반드시 JSON. 파싱 실패 시 폴백 규칙(라운드로빈)을 사용.
"""
import json
import random
from pathlib import Path
from typing import Any

import config
from conversation import ConversationState, is_failure_message


class Orchestrator:
    def __init__(self, client: Any):
        self.client = client
        self.system_prompt = (
            Path(config.PROJECT_ROOT / config.ORCHESTRATOR_PROMPT_FILE)
            .read_text(encoding="utf-8")
        )

    def decide(self, state: ConversationState) -> dict:
        """다음 액션을 결정. 실패 시 폴백."""
        user_content = self._build_prompt(state)

        try:
            response = self.client.messages.create(
                model=config.MODEL_NAME,
                max_tokens=400,
                system=self.system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
            raw = "".join(
                b.text for b in response.content if getattr(b, "type", None) == "text"
            ).strip()
            decision = self._parse_json(raw)
            decision = self._validate(decision, state)
        except Exception as e:
            decision = self._fallback_decision(state, reason=f"파싱실패: {e}")

        self._apply_and_log(state, decision)
        return decision

    def decide_offline(self, state: ConversationState) -> dict:
        """LLM 호출 없이 라이트 모드의 다음 액션을 결정한다."""
        schedule = (
            (["researcher", "critic"], "whiteboard", "가설을 제안하고 논리적 허점을 점검합니다."),
            (["fact_checker", "expert"], "server_room", "핵심 사실을 확인하고 실무 관점으로 보강합니다."),
        )
        round_index = sum(
            1 for entry in state.orchestrator_log if entry.get("action") == "encounter"
        )

        if round_index >= len(schedule):
            decision = {
                "action": "finalize",
                "confidence_score": state.confidence_score,
                "confidence_delta": 0,
                "confidence_reason": "두 차례의 라이트 모드 검토가 완료되었습니다.",
                "reason": "라이트 모드 라운드 완료",
            }
        else:
            agents, location, confidence_reason = schedule[round_index]
            confidence_after = min(
                100, state.confidence_score + config.LITE_CONFIDENCE_DELTA
            )
            decision = {
                "action": "encounter",
                "agents": agents,
                "location": location,
                "confidence_score": confidence_after,
                "confidence_delta": confidence_after - state.confidence_score,
                "confidence_reason": confidence_reason,
                "reason": f"라이트 모드 규칙 기반 라운드 {round_index + 1}",
            }

        self._apply_and_log(state, decision)
        return decision

    def reconcile_offline_round(
        self,
        state: ConversationState,
        decision: dict,
        runtime_failed: bool = False,
    ) -> None:
        """실패한 라이트 라운드에 선반영된 신뢰도 상승을 되돌린다."""
        if decision.get("action") != "encounter" or not state.orchestrator_log:
            return

        log = state.orchestrator_log[-1]
        round_start_turn = int(log.get("turn") or 0)
        round_utterances = state.history[round_start_turn:]
        has_failed_message = any(
            is_failure_message(utterance.message) for utterance in round_utterances
        )
        if not runtime_failed and not has_failed_message:
            return

        applied_delta = max(0, int(decision.get("confidence_delta") or 0))
        state.confidence_score = max(0, state.confidence_score - applied_delta)
        failure_reason = "라운드 발언 생성 실패로 신뢰도를 올리지 않았습니다."

        decision["confidence_score"] = state.confidence_score
        decision["confidence_delta"] = 0
        decision["confidence_reason"] = failure_reason
        log["confidence_after"] = state.confidence_score
        log["delta"] = 0
        log["reason"] = failure_reason
        log["confidence_reason"] = failure_reason

    @staticmethod
    def _apply_and_log(state: ConversationState, decision: dict) -> None:
        """결정의 신뢰도를 반영하고 공통 로그 스키마로 기록한다."""
        if "confidence_score" in decision:
            state.confidence_score = int(decision["confidence_score"])
        confidence_reason = decision.get("confidence_reason")
        state.orchestrator_log.append(
            {
                "turn": state.turn_count,
                "confidence_after": state.confidence_score,
                "delta": decision.get("confidence_delta"),
                "reason": confidence_reason,
                "confidence_reason": confidence_reason,
                "action": decision.get("action"),
                "agents": decision.get("agents"),
                "location": decision.get("location"),
            }
        )

    def _build_prompt(self, state: ConversationState) -> str:
        # 각 에이전트의 최근 활동 요약
        last_actions = {}
        for aid in config.ENCOUNTER_AGENTS:
            utters = state.utterances_by(aid)
            if utters:
                last = utters[-1]
                last_actions[aid] = (
                    f"턴{last.turn}에 '{last.message[:30]}...' 발언 "
                    f"[확신: {last.confidence}]"
                )
            else:
                last_actions[aid] = "아직 등장 안함"

        agent_state_lines = "\n".join(
            f"- {config.AGENTS[aid]['display_name']} ({aid}): {last_actions[aid]}"
            for aid in config.ENCOUNTER_AGENTS
        )

        location_list = "\n".join(
            f"- {lid}: {desc}" for lid, desc in config.LOCATIONS.items()
        )

        return (
            f"[사용자 질문]\n{state.question}\n\n"
            f"[현재 상태]\n"
            f"- 신뢰도: {state.confidence_score}/100 (임계값 {state.confidence_threshold})\n"
            f"- 진행 턴: {state.turn_count}/{state.max_turns}\n"
            f"- 팩트체커 검색 사용: {state.fact_checker_search_count}/"
            f"{config.FACT_CHECKER_MAX_SEARCHES}\n\n"
            f"[에이전트 최근 활동]\n{agent_state_lines}\n\n"
            f"[사용 가능 장소]\n{location_list}\n\n"
            f"[최근 대화 로그]\n{state.formatted_history(last_n=10)}\n\n"
            f"이제 JSON으로 결정을 출력하세요."
        )

    def _parse_json(self, raw: str) -> dict:
        # 코드펜스 제거
        raw = raw.strip()
        if raw.startswith("```"):
            # ```json ... ``` 또는 ``` ... ```
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
        # 첫 { 부터 마지막 } 까지
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"JSON 못 찾음: {raw[:200]}")
        return json.loads(raw[start : end + 1])

    def _validate(self, d: dict, state: ConversationState) -> dict:
        action = d.get("action")
        if action not in ("encounter", "finalize"):
            raise ValueError(f"잘못된 action: {action}")

        if action == "encounter":
            agents = d.get("agents", [])
            if not (isinstance(agents, list) and len(agents) == 2):
                raise ValueError(f"agents는 정확히 2명이어야 함: {agents}")
            for a in agents:
                if a not in config.ENCOUNTER_AGENTS:
                    raise ValueError(f"인카운터 불가 에이전트: {a}")
            if agents[0] == agents[1]:
                raise ValueError("자기 자신과 마주칠 수 없음")
            loc = d.get("location")
            if loc and loc not in config.LOCATIONS:
                # 잘못된 장소면 기본값
                d["location"] = "meeting_desk"

        return d

    def _fallback_decision(self, state: ConversationState, reason: str) -> dict:
        """오케스트레이터 실패 시 안전한 라운드로빈 페어링."""
        # 조기 종료 조건
        if state.turn_count >= state.max_turns - 1:
            return {
                "action": "finalize",
                "confidence_score": state.confidence_score,
                "confidence_delta": 0,
                "confidence_reason": f"[폴백] {reason}. 턴 상한 근접.",
                "reason": "안전 종료",
            }

        # 활동 적은 에이전트 우선
        activity = {
            aid: len(state.utterances_by(aid))
            for aid in config.ENCOUNTER_AGENTS
        }
        sorted_agents = sorted(activity.items(), key=lambda x: x[1])
        pair = [sorted_agents[0][0], sorted_agents[1][0]]
        random.shuffle(pair)

        return {
            "action": "encounter",
            "agents": pair,
            "location": random.choice(list(config.LOCATIONS.keys())),
            "confidence_score": state.confidence_score + 5,
            "confidence_delta": 5,
            "confidence_reason": f"[폴백] {reason}",
            "reason": "폴백: 활동 적은 에이전트끼리 매칭",
        }
