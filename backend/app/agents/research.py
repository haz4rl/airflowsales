from backend.app.agents.prompts import UNTRUSTED_NOTE, render_evidence
from backend.app.tools.llm import LLMProvider

SYSTEM = (
    "You are a commercial research analyst. Use ONLY the supplied evidence. "
    "Never invent facts. Return a JSON object."
)


def synthesize_company(llm: LLMProvider, domain: str, evidence: list[dict]):
    prompt = (
        f"Company domain: {domain}\n\n"
        f"{UNTRUSTED_NOTE}\n\n"
        f"<evidence>\n{render_evidence(evidence)}\n</evidence>\n\n"
        "Return keys: name, description, industry, location, commercial_signals (list), "
        "pain_points (list), evidence_summary. Use null when unsupported."
    )
    return llm.generate_json(SYSTEM, prompt)
