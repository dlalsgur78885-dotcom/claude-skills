"""template_channel_id_on_delete_set_null

Revision ID: a403ca460fac
Revises: 645d17ebc6a9
Create Date: 2026-05-24 15:11:25.026433

Change carousel_templates.channel_id FK from default (NO ACTION = RESTRICT)
to ON DELETE SET NULL, so deleting a benchmark channel no longer cascades
into deleting its templates — the templates survive as orphans with
channel_id=NULL.

The API layer (channels._purge_channel_children) also explicitly UPDATE…
SET channel_id=NULL before deleting a channel — that's the primary guard
because SQLite PRAGMA foreign_keys is OFF by default in this app's
connections. This FK rule is defense-in-depth for any future env where
FK enforcement is turned on.

SQLite can't ALTER a FK in place. batch_alter_table rebuilds the table;
naming_convention here is required because the original FK was created
without a name (autogenerate-emitted FK), and batch's drop_constraint
needs a name to target.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a403ca460fac'
down_revision: Union[str, None] = '645d17ebc6a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NAMING = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}
_FK_NAME = "fk_carousel_templates_channel_id_benchmark_channels"


def upgrade() -> None:
    with op.batch_alter_table(
        "carousel_templates", schema=None, naming_convention=_NAMING
    ) as batch_op:
        batch_op.drop_constraint(_FK_NAME, type_="foreignkey")
        batch_op.create_foreign_key(
            _FK_NAME,
            "benchmark_channels", ["channel_id"], ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "carousel_templates", schema=None, naming_convention=_NAMING
    ) as batch_op:
        batch_op.drop_constraint(_FK_NAME, type_="foreignkey")
        batch_op.create_foreign_key(
            _FK_NAME,
            "benchmark_channels", ["channel_id"], ["id"],
        )
