"""Add complete HR job requisition management fields and indexes.

Revision ID: 007_job_requisitions
Revises: 006_candidate_settings_privacy
Create Date: 2026-11-10 14:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007_job_requisitions"
down_revision: Union[str, None] = "006_candidate_settings_privacy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add requisition fields to jobs table
    op.add_column("jobs", sa.Column("responsibilities", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("required_qualifications", sa.Text(), nullable=True))
    op.add_column(
        "jobs",
        sa.Column(
            "preferred_skills",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column("jobs", sa.Column("experience_requirements", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("education_requirements", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("country", sa.String(length=100), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("vacancies_count", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "recruiter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "hiring_manager_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column("visibility", sa.String(length=50), server_default="public", nullable=False),
    )
    op.add_column(
        "jobs",
        sa.Column("approval_status", sa.String(length=50), server_default="draft", nullable=False),
    )

    # Indexes
    op.create_index("ix_jobs_recruiter_id", "jobs", ["recruiter_id"])
    op.create_index("ix_jobs_hiring_manager_id", "jobs", ["hiring_manager_id"])
    op.create_index("ix_jobs_approval_status", "jobs", ["approval_status"])
    op.create_index("ix_jobs_visibility", "jobs", ["visibility"])


def downgrade() -> None:
    op.drop_index("ix_jobs_visibility", table_name="jobs")
    op.drop_index("ix_jobs_approval_status", table_name="jobs")
    op.drop_index("ix_jobs_hiring_manager_id", table_name="jobs")
    op.drop_index("ix_jobs_recruiter_id", table_name="jobs")

    op.drop_column("jobs", "approval_status")
    op.drop_column("jobs", "visibility")
    op.drop_column("jobs", "hiring_manager_id")
    op.drop_column("jobs", "recruiter_id")
    op.drop_column("jobs", "vacancies_count")
    op.drop_column("jobs", "country")
    op.drop_column("jobs", "education_requirements")
    op.drop_column("jobs", "experience_requirements")
    op.drop_column("jobs", "preferred_skills")
    op.drop_column("jobs", "required_qualifications")
    op.drop_column("jobs", "responsibilities")
