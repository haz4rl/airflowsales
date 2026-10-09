from uuid import UUID

from backend.app.db.session import get_db
from backend.app.models.domain import (
    Campaign,
    Company,
    Evidence,
    Prospect,
    Qualification,
    WorkflowEvent,
    WorkflowRun,
)
from backend.app.schemas.campaign import CampaignRef
from backend.app.schemas.prospect import DiscoveryRequest, DiscoveryResponse, ProspectListItem
from backend.app.services.providers import get_llm_provider, get_search_provider
from backend.app.tools.company_search import SearchProvider, SearchProviderError
from backend.app.tools.llm import LLMProvider, LLMProviderError
from backend.app.workflows.sales_intelligence import run_sales_intelligence
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

router = APIRouter()


def _latest_run(db: Session, prospect_id: UUID) -> WorkflowRun | None:
    return (
        db.query(WorkflowRun)
        .filter(WorkflowRun.prospect_id == prospect_id)
        .order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
        .first()
    )


def _agent_outputs(db: Session, run_id: UUID) -> tuple[dict | None, dict | None]:
    events = (
        db.query(WorkflowEvent)
        .filter(
            WorkflowEvent.run_id == run_id,
            WorkflowEvent.name.in_(
                ("outreach_agent", "critic_agent", "outreach_revision", "critic_revision")
            ),
        )
        .order_by(WorkflowEvent.created_at.asc(), WorkflowEvent.id.asc())
        .all()
    )
    outreach = None
    critic = None
    for event in events:
        if event.name in ("outreach_agent", "outreach_revision"):
            outreach = event.output
        elif event.name == "critic_agent" or event.name == "critic_revision":
            critic = event.output
    return outreach, critic


@router.get("", response_model=list[ProspectListItem])
@router.get("/", response_model=list[ProspectListItem])
def list_prospects(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    rows = (
        db.query(Prospect)
        .options(
            joinedload(Prospect.company),
            joinedload(Prospect.qualification),
            joinedload(Prospect.campaign),
        )
        .order_by(Prospect.created_at.desc(), Prospect.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    items = []
    for p in rows:
        company = p.company
        items.append(
            {
                "prospect": p,
                "company": company,
                "qualification": p.qualification,
                "campaign": CampaignRef.model_validate(p.campaign) if p.campaign else None,
                "research_date": (company.last_researched_at or p.created_at)
                if company
                else p.created_at,
            }
        )
    return items


@router.post("/discover", response_model=DiscoveryResponse)
def discover(
    req: DiscoveryRequest,
    db: Session = Depends(get_db),
    search: SearchProvider = Depends(get_search_provider),
    llm: LLMProvider = Depends(get_llm_provider),
):
    campaign = db.get(Campaign, req.campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    try:
        prospect, run, artifacts = run_sales_intelligence(db, campaign, req.domain, search, llm)
    except (SearchProviderError, LLMProviderError, RuntimeError) as exc:
        raise HTTPException(502, str(exc)) from exc
    company = db.get(Company, prospect.company_id)
    evidence = db.query(Evidence).filter_by(company_id=company.id).all()
    qualification = db.query(Qualification).filter_by(prospect_id=prospect.id).one_or_none()
    return {
        "prospect": prospect,
        "company": company,
        "evidence": evidence,
        "qualification": qualification,
        "workflow_run_id": run.id,
        "outreach": artifacts.get("outreach"),
        "critic": artifacts.get("critic"),
    }


@router.get("/{prospect_id}", response_model=DiscoveryResponse)
def get_prospect(prospect_id: UUID, db: Session = Depends(get_db)):
    p = db.get(Prospect, prospect_id)
    if not p:
        raise HTTPException(404, "Prospect not found")
    c = db.get(Company, p.company_id)
    run = _latest_run(db, p.id)
    outreach, critic = _agent_outputs(db, run.id) if run else (None, None)
    return {
        "prospect": p,
        "company": c,
        "evidence": db.query(Evidence).filter_by(company_id=c.id).all(),
        "qualification": db.query(Qualification).filter_by(prospect_id=p.id).one_or_none(),
        "workflow_run_id": run.id if run else None,
        "outreach": outreach,
        "critic": critic,
    }
