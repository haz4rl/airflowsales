from backend.app.agents.prompts import dumps
from backend.app.tools.llm import LLMProvider

SYSTEM = (
    "Draft concise B2B outreach. Every factual claim must be grounded in supplied "
    "intelligence. Return JSON."
)
REVISE_SYSTEM = (
    "Revise a B2B outreach draft to remove or reword claims the critic flagged as "
    "unsupported. Keep the message concise and grounded in the supplied intelligence. "
    "Return JSON."
)


def draft_outreach(llm: LLMProvider, campaign: dict, intelligence: dict, qualification: dict):
    prompt = (
        f"Campaign:\n{dumps(campaign)}\n\n"
        f"Intelligence:\n{dumps(intelligence)}\n\n"
        f"Qualification:\n{dumps(qualification)}\n\n"
        "Return subject, body, claims (list)."
    )
    return llm.generate_json(SYSTEM, prompt)


def revise_outreach(
    llm: LLMProvider,
    campaign: dict,
    intelligence: dict,
    qualification: dict,
    draft: dict,
    unsupported_claims: list,
):
    prompt = (
        f"Campaign:\n{dumps(campaign)}\n\n"
        f"Intelligence:\n{dumps(intelligence)}\n\n"
        f"Qualification:\n{dumps(qualification)}\n\n"
        f"Previous draft:\n{dumps(draft)}\n\n"
        f"Claims the critic rejected as unsupported:\n{dumps(list(unsupported_claims))}\n\n"
        "Return a revised subject, body, and claims (list)."
    )
    return llm.generate_json(REVISE_SYSTEM, prompt)
