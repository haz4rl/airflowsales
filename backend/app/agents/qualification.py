from backend.app.agents.prompts import dumps
from backend.app.tools.llm import LLMProvider

SYSTEM = "You qualify B2B prospects conservatively. Use only provided facts. Return JSON."


def _as_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def qualify(llm: LLMProvider, campaign: dict, intelligence: dict):
    prompt = (
        f"Campaign:\n{dumps(campaign)}\n\n"
        f"Company intelligence:\n{dumps(intelligence)}\n\n"
        "Return score (0-100), confidence (0-1), decision (GO|MAYBE|NO_GO), reasoning, "
        "scoring_breakdown object. Penalize missing evidence."
    )
    data, usage = llm.generate_json(SYSTEM, prompt)
    data["score"] = max(0, min(100, _as_int(data.get("score"), 0)))
    data["confidence"] = max(0.0, min(1.0, _as_float(data.get("confidence"), 0.0)))
    data["decision"] = (
        data.get("decision") if data.get("decision") in {"GO", "MAYBE", "NO_GO"} else "MAYBE"
    )
    return data, usage
