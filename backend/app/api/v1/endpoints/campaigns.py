import uuid

from backend.app.db.session import get_db
from backend.app.models.domain import (
    Campaign as CampaignModel,
)
from backend.app.models.domain import (
    Prospect as ProspectModel,
)
from backend.app.models.domain import (
    Qualification as QualificationModel,
)
from backend.app.models.domain import (
    WorkflowRun as WorkflowRunModel,
)
from backend.app.schemas.campaign import Campaign, CampaignCreate
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter()

_HISTORY_CONFLICT = (
    "Campaign has research history that is preserved and cannot be deleted with it: "
    "{prospects} prospect(s), {qualifications} qualification(s), {runs} workflow run(s). "
    "Only campaigns with no associated prospects can be deleted."
)


@router.post("", response_model=Campaign)
@router.post("/", response_model=Campaign)
def create_campaign(*, db: Session = Depends(get_db), campaign_in: CampaignCreate):
    """
    Create a new campaign.
    """
    campaign = CampaignModel(
        name=campaign_in.name,
        product_description=campaign_in.product_description,
        target_industries=campaign_in.target_industries,
        target_company_characteristics=campaign_in.target_company_characteristics,
        qualification_criteria=campaign_in.qualification_criteria,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("", response_model=list[Campaign])
@router.get("/", response_model=list[Campaign])
def list_campaigns(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    """
    Retrieve campaigns.
    """
    campaigns = (
        db.query(CampaignModel)
        .order_by(CampaignModel.created_at.desc(), CampaignModel.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return campaigns


def _research_history_counts(db: Session, campaign_id: uuid.UUID) -> dict:
    prospect_ids = [
        row[0]
        for row in db.query(ProspectModel.id).filter(ProspectModel.campaign_id == campaign_id)
    ]
    if not prospect_ids:
        return {"prospects": 0, "qualifications": 0, "runs": 0}

    qualifications = (
        db.query(QualificationModel)
        .filter(QualificationModel.prospect_id.in_(prospect_ids))
        .count()
    )
    runs = db.query(WorkflowRunModel).filter(WorkflowRunModel.prospect_id.in_(prospect_ids)).count()
    return {
        "prospects": len(prospect_ids),
        "qualifications": qualifications,
        "runs": runs,
    }


@router.delete("/{campaign_id}", status_code=204)
def delete_campaign(
    *,
    db: Session = Depends(get_db),
    campaign_id: uuid.UUID,
):
    """
    Delete a campaign.

    Only campaigns with no associated prospects can be deleted: prospect,
    qualification and workflow history is preserved and never cascade-deleted.
    """
    campaign = db.query(CampaignModel).filter(CampaignModel.id == campaign_id).first()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")

    counts = _research_history_counts(db, campaign_id)
    if counts["prospects"] > 0:
        raise HTTPException(
            status_code=409,
            detail=_HISTORY_CONFLICT.format(**counts),
        )

    db.delete(campaign)
    try:
        db.commit()
    except IntegrityError:
        # A prospect was attached between the check and the delete; the
        # NO ACTION foreign key refused the delete, so keep the campaign.
        db.rollback()
        counts = _research_history_counts(db, campaign_id)
        raise HTTPException(
            status_code=409,
            detail=_HISTORY_CONFLICT.format(**counts),
        ) from None
