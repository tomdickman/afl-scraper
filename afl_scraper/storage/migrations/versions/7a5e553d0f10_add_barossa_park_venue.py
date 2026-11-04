"""add barossa park venue

Revision ID: 7a5e553d0f10
Revises: e802604cdd17
Create Date: 2026-04-07 18:49:10.087540

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a5e553d0f10"
down_revision: str | Sequence[str] | None = "e802604cdd17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO venue (id, name, city, state, country, latitude, longitude)
        VALUES ('Barossa Oval', 'Barossa Park', 'Lyndoch', 'South Australia', 'Australia', -34.598422, 138.885746)
        ON CONFLICT (id) DO NOTHING;
    """
    )


def downgrade() -> None:
    """No downgrade path, venue added to initial venues too"""
    pass
