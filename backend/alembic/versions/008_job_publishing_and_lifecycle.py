"""Add job lifecycle history table and lifecycle columns to jobs table.

Revision ID: 008_job_publishing_lifecycle
Revises: 007_job_requisitions
Create Date: 2026-11-10 14:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "008_job_publishing_lifecycle"
down_revision: Union[str, None] = "007_job_requisitions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add lifecycle tracking columns to jobs table
    op.add_column("jobs", sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("reopened_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("change_request_reason", sa.Text(), nullable=True))

    # 2. Create job_lifecycle_history table
    op.create_table(
        "job_lifecycle_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("previous_status", sa.String(length=50), nullable=False),
        sa.Column("new_status", sa.String(length=50), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("actor_role", sa.String(length=50), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "audit_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            index=True,
        ),
    )

    op.create_index(
        "ix_job_lifecycle_job_created",
        "job_lifecycle_history",
        ["job_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_job_lifecycle_job_created", table_name="job_lifecycle_history")
    op.drop_table("job_lifecycle_history")

    op.drop_column("jobs", "change_request_reason")
    op.drop_column("jobs", "reopened_at")
    op.drop_column("jobs", "closed_at")
