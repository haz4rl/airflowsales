from backend.app.db.session import get_db
from backend.app.models.domain import Company, Prospect, Qualification, WorkflowRun
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    """Aggregate workspace metrics from persisted data.

    ``statuses`` counts prospects; ``run_statuses`` counts workflow runs so
    clients can compute success rates from explicit run statuses instead of
    inferring "completed" as total-minus-failed.
    """
    status_rows = db.query(Prospect.status, func.count(Prospect.id)).group_by(Prospect.status).all()
    statuses = {status: count for status, count in status_rows}
    run_status_rows = (
        db.query(WorkflowRun.status, func.count(WorkflowRun.id)).group_by(WorkflowRun.status).all()
    )
    run_statuses = {status: count for status, count in run_status_rows}
    total_tokens = db.query(func.coalesce(func.sum(WorkflowRun.total_tokens), 0)).scalar()
    total_cost = db.query(func.coalesce(func.sum(WorkflowRun.total_cost), 0.0)).scalar()
    return {
        "prospects": db.query(func.count(Prospect.id)).scalar(),
        "companies": db.query(func.count(Company.id)).scalar(),
        "qualified": db.query(func.count(Qualification.id))
        .filter(Qualification.decision == "GO")
        .scalar(),
        "awaiting_approval": statuses.get("AWAITING_APPROVAL", 0),
        "workflow_runs": db.query(func.count(WorkflowRun.id)).scalar(),
        "failed_runs": run_statuses.get("FAILED", 0),
        "total_tokens": int(total_tokens),
        "total_cost": round(float(total_cost), 6),
        "statuses": statuses,
        "run_statuses": run_statuses,
    }
