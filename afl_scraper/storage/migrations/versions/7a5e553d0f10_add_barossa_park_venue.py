"""add barossa park venue

Revision ID: 7a5e553d0f10
Revises: e802604cdd17
Create Date: 2026-04-07 18:49:10.087540

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a5e553d0f10'
down_revision: Union[str, Sequence[str], None] = 'e802604cdd17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO venue (id, name, city, state, country, latitude, longitude)
        VALUES ('Barossa Oval', 'Barossa Park', 'Lyndoch', 'South Australia', 'Australia', -34.598422, 138.885746)
        ON CONFLICT (id) DO NOTHING;
    """)

def downgrade() -> None:
    """No downgrade path, venue added to initial venues too"""
    pass
