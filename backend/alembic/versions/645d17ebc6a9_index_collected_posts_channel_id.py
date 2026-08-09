"""index_collected_posts_channel_id

Revision ID: 645d17ebc6a9
Revises: accaf9738eb4
Create Date: 2026-05-24 13:03:10.270751

Adds an index on collected_posts.channel_id so /posts?channel=... filters
hit an index instead of full-scanning the table. SQLite does not implicitly
index foreign-key columns.

The autogenerate output also flagged unrelated drift (INTEGER↔Boolean,
REAL↔Float, VARCHAR(500)↔String(1000)) between the manual-ALTER pre-Alembic
schema and the current model declarations. Those are intentionally left out
of this revision — they're cosmetic in SQLite (same affinity) and the
String(1000) length change belongs in its own deliberate migration.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '645d17ebc6a9'
down_revision: Union[str, None] = 'accaf9738eb4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('collected_posts', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_collected_posts_channel_id'),
            ['channel_id'],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('collected_posts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_collected_posts_channel_id'))
