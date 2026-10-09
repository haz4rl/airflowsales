from backend.app.agents.prompts import UNTRUSTED_NOTE, dumps, render_evidence
from backend.app.tools.llm import LLMProvider

SYSTEM = "You are a strict factuality critic. Reject unsupported claims. Return JSON."


def _as_bool(value) -> bool:
    """Coerce LLM output to a real boolean.

    LLMs occasionally return "false"/"no" as strings; naive bool() would treat
    those as True and incorrectly route unapproved outreach to human approval.
    """
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "yes", "1"}


def critique(llm: LLMProvider, evidence: list[dict], draft: dict):
    prompt = (
        f"{UNTRUSTED_NOTE}\n\n"
        f"<evidence>\n{render_evidence(evidence)}\n</evidence>\n\n"
        f"Draft to review:\n{dumps(draft)}\n\n"
        "Return approved (boolean), unsupported_claims (list of strings quoted from the draft), notes."
    )
    data, usage = llm.generate_json(SYSTEM, prompt)
    data["approved"] = _as_bool(data.get("approved"))
    claims = data.get("unsupported_claims")
    data["unsupported_claims"] = [str(c) for c in claims] if isinstance(claims, list) else []
    return data, usage
