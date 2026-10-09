"""add indexes on foreign keys and created_at

Revision ID: a1c4e2b9f7d3
Revises: e50ac658fba5
Create Date: 2026-10-09 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c4e2b9f7d3"
down_revision: str | None = "e50ac658fba5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _index(name: str, table: str, columns: list[str], unique: bool = False) -> None:
    op.create_index(op.f(name), table, columns, unique=unique)


def upgrade() -> None:
    # Foreign keys are never auto-indexed by Postgres; every list endpoint
    # orders by created_at, and joins/filters hit these FK columns.
    _index("ix_prospects_campaign_id", "prospects", ["campaign_id"])
    _index("ix_prospects_company_id", "prospects", ["company_id"])
    _index("ix_prospects_created_at", "prospects", ["created_at"])
    _index("ix_evidence_company_id", "evidence", ["company_id"])
    _index("ix_evidence_created_at", "evidence", ["created_at"])
    _index("ix_workflow_runs_prospect_id", "workflow_runs", ["prospect_id"])
    _index("ix_workflow_runs_created_at", "workflow_runs", ["created_at"])
    _index("ix_workflow_events_run_id", "workflow_events", ["run_id"])
    _index("ix_workflow_events_created_at", "workflow_events", ["created_at"])
    _index("ix_campaigns_created_at", "campaigns", ["created_at"])
    _index("ix_companies_created_at", "companies", ["created_at"])
    _index("ix_qualifications_created_at", "qualifications", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_qualifications_created_at"), table_name="qualifications")
    op.drop_index(op.f("ix_companies_created_at"), table_name="companies")
    op.drop_index(op.f("ix_campaigns_created_at"), table_name="campaigns")
    op.drop_index(op.f("ix_workflow_events_created_at"), table_name="workflow_events")
    op.drop_index(op.f("ix_workflow_events_run_id"), table_name="workflow_events")
    op.drop_index(op.f("ix_workflow_runs_created_at"), table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_prospect_id"), table_name="workflow_runs")
    op.drop_index(op.f("ix_evidence_created_at"), table_name="evidence")
    op.drop_index(op.f("ix_evidence_company_id"), table_name="evidence")
    op.drop_index(op.f("ix_prospects_created_at"), table_name="prospects")
    op.drop_index(op.f("ix_prospects_company_id"), table_name="prospects")
    op.drop_index(op.f("ix_prospects_campaign_id"), table_name="prospects")
