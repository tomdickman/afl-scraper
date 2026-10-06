"""add Hands Oval venue

Revision ID: a4d9c2e71b30
Revises: b6df0c4a1e92
Create Date: 2026-10-06 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a4d9c2e71b30"
down_revision: str | Sequence[str] | None = "b6df0c4a1e92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO venue (id, name, city, state, country, latitude, longitude)
        VALUES (
          'Hands Oval', 'Hands Oval', 'Bunbury', 'Western Australia',
          'Australia', -33.34616, 115.64297
        )
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    """Hands Oval is retained because loaded games may reference it."""
