"""add_is_video_to_collected_posts

Revision ID: c7f2a1d94b30
Revises: a403ca460fac
Create Date: 2026-08-08 07:20:00.000000

Reels are now collected (previously dropped by a slide_count < 2 filter), but
they arrive as a single cover image, so slide_count alone cannot tell a reel
from a one-photo post. This flag makes the distinction explicit for the /posts
list and any UI labelling.

server_default='0' so the column backfills existing rows as False without a
separate UPDATE — every pre-existing row is a carousel or a still photo.

Note: production predates this Alembic setup (it boots with
Base.metadata.create_all and has no alembic_version table), so the column was
added there by hand with the equivalent ALTER. This revision exists so a fresh
DB — or prod once its image is rebuilt with the migration runner — lands on the
same schema.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c7f2a1d94b30'
down_revision: Union[str, None] = 'a403ca460fac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('collected_posts', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_video', sa.Boolean(), nullable=False, server_default='0')
        )


def downgrade() -> None:
    with op.batch_alter_table('collected_posts', schema=None) as batch_op:
        batch_op.drop_column('is_video')
