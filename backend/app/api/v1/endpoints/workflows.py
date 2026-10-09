from uuid import UUID

from backend.app.db.session import get_db
from backend.app.models.domain import Company, Prospect, WorkflowEvent, WorkflowRun
from backend.app.schemas.workflow import ApprovalRequest, WorkflowRunListItem, WorkflowRunRead
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("", response_model=list[WorkflowRunListItem])
@router.get("/", response_model=list[WorkflowRunListItem])
def list_runs(
    db: Session = Depends(get_db),
    prospect_id: UUID | None = None,
    status: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    q = (
        db.query(WorkflowRun, Company.name, Company.domain)
        .join(Prospect, WorkflowRun.prospect_id == Prospect.id)
        .join(Company, Prospect.company_id == Company.id)
    )
    if prospect_id:
        q = q.filter(WorkflowRun.prospect_id == prospect_id)
    if status:
        q = q.filter(WorkflowRun.status == status)
    rows = (
        q.order_by(WorkflowRun.created_at.desc(), WorkflowRun.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    counts = dict(
        db.query(WorkflowEvent.run_id, func.count(WorkflowEvent.id))
        .group_by(WorkflowEvent.run_id)
        .all()
    )
    return [
        {
            "id": r.id,
            "prospect_id": r.prospect_id,
            "status": r.status,
            "total_tokens": r.total_tokens,
            "total_cost": r.total_cost,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "event_count": counts.get(r.id, 0),
            "company_name": name,
            "company_domain": domain,
        }
        for r, name, domain in rows
    ]


@router.get("/{run_id}", response_model=WorkflowRunRead)
def get_run(run_id: UUID, db: Session = Depends(get_db)):
    r = db.get(WorkflowRun, run_id)
    if not r:
        raise HTTPException(404, "Workflow run not found")
    return r


@router.post("/{run_id}/approval", response_model=WorkflowRunRead)
def approve(run_id: UUID, body: ApprovalRequest, db: Session = Depends(get_db)):
    r = db.get(WorkflowRun, run_id)
    if not r:
        raise HTTPException(404, "Workflow run not found")
    if r.status != "AWAITING_APPROVAL":
        raise HTTPException(409, "Run is not awaiting approval")
    p = db.get(Prospect, r.prospect_id)
    r.status = "APPROVED" if body.approved else "REJECTED"
    p.status = r.status
    db.add(
        WorkflowEvent(
            run_id=r.id,
            event_type="HUMAN",
            name="approval",
            input={"note": body.note or ""},
            output={"approved": body.approved},
            token_usage={},
        )
    )
    db.commit()
    db.refresh(r)
    return r
