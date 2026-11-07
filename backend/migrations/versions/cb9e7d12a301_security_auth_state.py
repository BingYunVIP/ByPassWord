"""Persist single-use authentication state and installation ownership.

Revision ID: cb9e7d12a301
Revises: 8295d6f562e1
"""

from alembic import op
import sqlalchemy as sa

from app.models.base import UTCDateTime

revision = "cb9e7d12a301"
down_revision = "8295d6f562e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive migration: existing wrapped keys and encrypted records are untouched.
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("credential_version", sa.Integer(), server_default="0", nullable=False))
        batch.add_column(sa.Column("two_factor_version", sa.Integer(), server_default="0", nullable=False))
        batch.add_column(sa.Column("recovery_auth_hash", sa.Text(), nullable=True))
        batch.add_column(sa.Column("totp_last_step", sa.Integer(), nullable=True))
    with op.batch_alter_table("refresh_tokens") as batch:
        batch.add_column(sa.Column("session_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("credential_version", sa.Integer(), server_default="0", nullable=False))
        batch.create_index("ix_refresh_tokens_session_id", ["session_id"])
    op.create_table(
        "auth_challenges",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("two_factor_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", UTCDateTime(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("consumed_at", UTCDateTime(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
    )
    op.create_index("ix_auth_challenges_user_id", "auth_challenges", ["user_id"])
    op.create_table(
        "installation_owner",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
    )
    connection = op.get_bind()
    owner = connection.execute(sa.text("SELECT id FROM users ORDER BY created_at, id LIMIT 1")).scalar()
    if owner:
        connection.execute(sa.text("INSERT INTO installation_owner (id, owner_user_id) VALUES (1, :owner)"), {"owner": owner})


def downgrade() -> None:
    op.drop_table("installation_owner")
    op.drop_index("ix_auth_challenges_user_id", table_name="auth_challenges")
    op.drop_table("auth_challenges")
    with op.batch_alter_table("refresh_tokens") as batch:
        batch.drop_index("ix_refresh_tokens_session_id")
        batch.drop_column("credential_version")
        batch.drop_column("session_id")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("totp_last_step")
        batch.drop_column("recovery_auth_hash")
        batch.drop_column("two_factor_version")
        batch.drop_column("credential_version")
