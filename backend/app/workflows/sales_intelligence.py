import logging
import time
from datetime import UTC, datetime

from backend.app.agents.critic import critique
from backend.app.agents.outreach import draft_outreach, revise_outreach
from backend.app.agents.qualification import qualify
from backend.app.agents.research import synthesize_company
from backend.app.config import settings
from backend.app.models.domain import (
    Campaign,
    Company,
    Evidence,
    Prospect,
    Qualification,
    WorkflowEvent,
    WorkflowRun,
)
from backend.app.tools.company_search import SearchProvider
from backend.app.tools.llm import LLMProvider
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Stored prompts are truncated for auditability without unbounded bloat.
_PROMPT_STORE_LIMIT = 8000


def _campaign(c):
    return {
        "product_description": c.product_description,
        "target_industries": c.target_industries,
        "target_company_characteristics": c.target_company_characteristics,
        "qualification_criteria": c.qualification_criteria,
    }


def _ev(e):
    return {"url": e.source_url, "title": e.source_title, "excerpt": e.excerpt}


def _prospect_status(decision: str, approved: bool) -> str:
    if decision == "GO":
        return "AWAITING_APPROVAL" if approved else "QUALIFIED"
    if decision == "NO_GO":
        return "REJECTED"
    return "MAYBE"


def _approved_flag(review: dict) -> bool:
    """Coerce the critic's approved field to a real boolean.

    Defense in depth alongside critic._as_bool: LLMs sometimes return
    "false"/"no" as strings, and bool("false") is True — which would wrongly
    route unapproved outreach to human approval.
    """
    raw = review.get("approved")
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"true", "yes", "1"}


def _cost_estimate(usage: dict) -> float:
    """Estimated USD cost from reported token usage and configured pricing."""
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    return (
        input_tokens / 1_000_000 * settings.GROQ_PRICE_PER_M_INPUT_TOKENS
        + output_tokens / 1_000_000 * settings.GROQ_PRICE_PER_M_OUTPUT_TOKENS
    )


def _prompt_input(provider, extra: dict | None = None) -> dict:
    """Capture the messages sent to the provider for the audit trail (M6)."""
    payload: dict = dict(extra or {})
    messages = getattr(provider, "last_messages", None) or []
    for message in messages:
        role = message.get("role")
        content = str(message.get("content", ""))
        if role == "system":
            payload["system"] = content
        elif role == "user":
            payload["prompt"] = content[:_PROMPT_STORE_LIMIT]
    return payload


def _event(db, run, name, event_type, inp, out, started, usage=None):
    e = WorkflowEvent(
        run_id=run.id,
        name=name,
        event_type=event_type,
        input=inp,
        output=out,
        latency_ms=int((time.monotonic() - started) * 1000),
        token_usage=usage or {},
    )
    db.add(e)
    if usage:
        run.total_tokens += int(usage.get("total_tokens", 0))
        run.total_cost = run.total_cost + _cost_estimate(usage)
    db.flush()


def _retries(db, run, provider, step):
    """Persist the retries a provider performed for this step, then clear them."""
    attempts = getattr(provider, "retry_attempts", None) or []
    for a in list(attempts):
        e = WorkflowEvent(
            run_id=run.id,
            name=f"{step}_retry",
            event_type="RETRY",
            input={"step": step},
            output={
                "retry": a.retry,
                "delay_seconds": a.delay_seconds,
                "reason": a.reason,
                "status_code": a.status_code,
                "detail": a.detail,
            },
            latency_ms=None,
            token_usage={},
        )
        db.add(e)
    attempts.clear()
    db.flush()


def run_sales_intelligence(
    db: Session, campaign: Campaign, domain: str, search: SearchProvider, llm: LLMProvider
) -> tuple[Prospect, WorkflowRun, dict]:
    run_started = time.monotonic()
    company = db.query(Company).filter(Company.domain == domain).one_or_none()
    if not company:
        company = Company(domain=domain)
        db.add(company)
        db.flush()
    prospect = (
        db.query(Prospect).filter_by(campaign_id=campaign.id, company_id=company.id).one_or_none()
    )
    if not prospect:
        prospect = Prospect(campaign_id=campaign.id, company_id=company.id, status="RESEARCHING")
        db.add(prospect)
        db.flush()
    prospect.status = "RESEARCHING"
    run = WorkflowRun(prospect_id=prospect.id, status="RUNNING", total_tokens=0, total_cost=0)
    db.add(run)
    db.flush()
    step = "company_search"
    try:
        t = time.monotonic()
        results = search.search(
            f"{domain} company products industry location recent commercial activity", 5
        )
        _event(db, run, "company_search", "TOOL", {"domain": domain}, {"results": len(results)}, t)
        _retries(db, run, search, step)
        if not results:
            raise RuntimeError("Search returned no evidence")
        evidence = []
        for r in results:
            existing = (
                db.query(Evidence).filter_by(company_id=company.id, source_url=r.url).one_or_none()
            )
            if existing:
                evidence.append(existing)
                continue
            e = Evidence(
                company_id=company.id,
                source_url=r.url,
                source_title=r.title,
                excerpt=r.content[:4000],
                evidence_type="SEARCH_RESULT",
                raw_metadata={"score": r.score},
            )
            db.add(e)
            evidence.append(e)
        company.last_researched_at = datetime.now(UTC)
        db.flush()
        evidence_payload = [_ev(e) for e in evidence]

        step = "research_agent"
        t = time.monotonic()
        intel, usage = synthesize_company(llm, domain, evidence_payload)
        _event(db, run, "research_agent", "LLM", _prompt_input(llm), intel, t, usage)
        _retries(db, run, llm, step)
        for field in ("name", "description", "industry", "location"):
            if intel.get(field):
                setattr(company, field, intel[field])

        step = "qualification_agent"
        t = time.monotonic()
        q, usage = qualify(llm, _campaign(campaign), intel)
        _event(db, run, "qualification_agent", "LLM", _prompt_input(llm), q, t, usage)
        _retries(db, run, llm, step)
        qual = db.query(Qualification).filter_by(
            prospect_id=prospect.id
        ).one_or_none() or Qualification(
            prospect_id=prospect.id,
            score=0,
            confidence=0,
            decision="MAYBE",
            reasoning="",
            scoring_breakdown={},
        )
        qual.score = q["score"]
        qual.confidence = q["confidence"]
        qual.decision = q["decision"]
        qual.reasoning = q.get("reasoning", "")
        qual.scoring_breakdown = q.get("scoring_breakdown", {})
        db.add(qual)

        step = "outreach_agent"
        t = time.monotonic()
        draft, usage = draft_outreach(llm, _campaign(campaign), intel, q)
        _event(db, run, "outreach_agent", "LLM", _prompt_input(llm), draft, t, usage)
        _retries(db, run, llm, step)

        step = "critic_agent"
        t = time.monotonic()
        review, usage = critique(llm, evidence_payload, draft)
        _event(db, run, "critic_agent", "LLM", _prompt_input(llm), review, t, usage)
        _retries(db, run, llm, step)

        # Bounded critic-driven revision: when the critic rejects the draft and
        # names unsupported claims, re-draft and re-review up to
        # OUTREACH_MAX_REVISIONS times, then gate on the final review. Every
        # attempt is persisted as workflow events.
        revisions = 0
        while (
            not _approved_flag(review)
            and review.get("unsupported_claims")
            and revisions < settings.OUTREACH_MAX_REVISIONS
        ):
            revisions += 1
            step = "outreach_revision"
            t = time.monotonic()
            draft, usage = revise_outreach(
                llm, _campaign(campaign), intel, q, draft, review["unsupported_claims"]
            )
            _event(
                db,
                run,
                "outreach_revision",
                "LLM",
                _prompt_input(
                    llm, {"revision": revisions, "rejected_claims": review["unsupported_claims"]}
                ),
                draft,
                t,
                usage,
            )
            _retries(db, run, llm, step)
            step = "critic_agent"
            t = time.monotonic()
            review, usage = critique(llm, evidence_payload, draft)
            _event(
                db,
                run,
                "critic_revision",
                "LLM",
                _prompt_input(llm, {"revision": revisions}),
                review,
                t,
                usage,
            )
            _retries(db, run, llm, step)

        prospect.status = _prospect_status(q["decision"], _approved_flag(review))
        run.status = "AWAITING_APPROVAL" if prospect.status == "AWAITING_APPROVAL" else "COMPLETED"
        db.commit()
        db.refresh(prospect)
        db.refresh(run)
        return (
            prospect,
            run,
            {"intelligence": intel, "qualification": q, "outreach": draft, "critic": review},
        )
    except Exception as exc:
        logger.exception("workflow_failed domain=%s step=%s", domain, step)
        _retries(db, run, search, step)
        _retries(db, run, llm, step)
        run.status = "FAILED"
        prospect.status = "FAILED"
        _event(
            db, run, "workflow_failure", "ERROR", {"step": step}, {"error": str(exc)}, run_started
        )
        db.commit()
        raise
