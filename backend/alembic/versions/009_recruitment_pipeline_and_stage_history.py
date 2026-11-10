"""Add recruitment pipeline stage history table, stage versioning, and org pipeline settings.

Revision ID: 009_recruitment_pipeline
Revises: 008_job_publishing_lifecycle
Create Date: 2026-11-10 14:55:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "009_recruitment_pipeline"
down_revision: Union[str, None] = "008_job_publishing_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add pipeline configuration column to organizations table
    op.add_column(
        "organizations",
        sa.Column("pipeline_stages", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # 2. Add stage versioning and rejection tracking to job_applications table
    op.add_column(
        "job_applications",
        sa.Column("stage_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "job_applications",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )

    # 3. Create application_stage_history table
    op.create_table(
        "application_stage_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_applications.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("previous_stage", sa.String(length=50), nullable=False),
        sa.Column("new_stage", sa.String(length=50), nullable=False),
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
        "ix_app_stage_history_app_created",
        "application_stage_history",
        ["application_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_app_stage_history_app_created", table_name="application_stage_history")
    op.drop_table("application_stage_history")

    op.drop_column("job_applications", "rejection_reason")
    op.drop_column("job_applications", "stage_version")

    op.drop_column("organizations", "pipeline_stages")
