"""populate teams

Revision ID: e802604cdd17
Revises: 8f6c140192f2
Create Date: 2026-01-23 22:22:04.880682

"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e802604cdd17"
down_revision: Union[str, Sequence[str], None] = "8f6c140192f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    sql_path = Path(__file__).parents[2] / "data/init_teams.sql"
    sql = sql_path.resolve().read_text()

    op.execute(sql)


def downgrade() -> None:
    op.execute("TRUNCATE TABLE team RESTART IDENTITY CASCADE")
