"""Add candidate notification enhancements, preferences, and privacy requests.

Revision ID: 006_candidate_settings_privacy
Revises: 005_app_submission
Create Date: 2026-11-09 20:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006_candidate_settings_privacy"
down_revision: Union[str, None] = "005_app_submission"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enhance candidate_notifications table
    op.add_column(
        "candidate_notifications",
        sa.Column("event_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "candidate_notifications",
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "candidate_notifications",
        sa.Column(
            "email_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "candidate_notifications",
        sa.Column(
            "email_status",
            sa.String(length=50),
            nullable=False,
            server_default="not_configured",
        ),
    )

    # 2. Enhance candidate_preferences table
    op.add_column(
        "candidate_preferences",
        sa.Column(
            "notification_preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='{"email_application_updates": true, "email_interview_alerts": true, "email_job_recommendations": false, "in_app_alerts": true, "digest_frequency": "instant"}',
        ),
    )
    op.add_column(
        "candidate_preferences",
        sa.Column(
            "privacy_preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='{"profile_visibility": "applied_only", "allow_ai_matching": true, "data_retention_months": 24}',
        ),
    )

    # 3. Create candidate_privacy_requests table
    op.create_table(
        "candidate_privacy_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("request_type", sa.String(length=50), nullable=False, index=True),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="pending",
            index=True,
        ),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("candidate_privacy_requests")
    op.drop_column("candidate_preferences", "privacy_preferences")
    op.drop_column("candidate_preferences", "notification_preferences")
    op.drop_column("candidate_notifications", "email_status")
    op.drop_column("candidate_notifications", "email_sent")
    op.drop_column("candidate_notifications", "payload")
    op.drop_column("candidate_notifications", "event_type")
