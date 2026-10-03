"""Make order contact optional."""

import sqlalchemy as sa

from alembic import op

revision = "0002_optional_contact"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("orders", "contact_name", existing_type=sa.String(length=200), nullable=True)
    op.alter_column("orders", "contact_phone", existing_type=sa.String(length=30), nullable=True)


def downgrade() -> None:
    op.alter_column("orders", "contact_name", existing_type=sa.String(length=200), nullable=False)
    op.alter_column("orders", "contact_phone", existing_type=sa.String(length=30), nullable=False)
