"""에이전트 팩토리."""
from typing import Any

import config
from .base import BaseAgent
from .fact_checker import FactCheckerAgent
from .synthesizer import SynthesizerAgent


def build_agents(client: Any) -> dict[str, BaseAgent]:
    """모든 에이전트를 만들어 dict로 반환."""
    agents: dict[str, BaseAgent] = {}
    for agent_id in config.AGENTS:
        if agent_id == "fact_checker":
            agents[agent_id] = FactCheckerAgent(agent_id, client)
        elif agent_id == "synthesizer":
            agents[agent_id] = SynthesizerAgent(agent_id, client)
        else:
            # researcher, critic, expert는 base 동작만으로 충분
            agents[agent_id] = BaseAgent(agent_id, client)
    return agents


__all__ = ["BaseAgent", "FactCheckerAgent", "SynthesizerAgent", "build_agents"]
