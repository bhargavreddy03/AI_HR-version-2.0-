"""Add application submission, tracking, consent, and idempotency fields to job_applications.

Revision ID: 005_app_submission
Revises: 004_candidate_portal
Create Date: 2026-11-09 18:35:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005_app_submission"
down_revision: Union[str, None] = "004_candidate_portal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_applications",
        sa.Column("resume_version_applied", sa.Integer(), nullable=True),
    )
    op.add_column(
        "job_applications",
        sa.Column(
            "answers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "job_applications",
        sa.Column(
            "consent_records",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "job_applications",
        sa.Column(
            "timeline",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "job_applications",
        sa.Column("idempotency_key", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_job_applications_idempotency_key",
        "job_applications",
        ["idempotency_key"],
        unique=False,
    )
    op.add_column(
        "job_applications",
        sa.Column(
            "audit_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_job_applications_idempotency_key", table_name="job_applications")
    op.drop_column("job_applications", "audit_metadata")
    op.drop_column("job_applications", "idempotency_key")
    op.drop_column("job_applications", "timeline")
    op.drop_column("job_applications", "consent_records")
    op.drop_column("job_applications", "answers")
    op.drop_column("job_applications", "resume_version_applied")
