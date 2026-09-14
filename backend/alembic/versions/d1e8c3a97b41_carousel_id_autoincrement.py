"""캐러셀 id 를 AUTOINCREMENT 로 — 번호 재사용 막기

Revision ID: d1e8c3a97b41
Revises: c7f2a1d94b30
Create Date: 2026-09-02

## 왜

SQLite 는 AUTOINCREMENT 가 없으면 새 id 를 `max(id)+1` 로 준다. 그래서 **가장 최근
캐러셀을 지우면 다음에 만드는 것이 그 번호를 그대로 다시 쓴다.** 번호는 제작 이력·편집
링크·대화에 남는데, 가리키는 대상이 조용히 바뀐다.

실제로 벌어진 일 — 제작 이력엔 13건이 적혀 있는데 남은 캐러셀은 5개뿐이었고, 438 번이
서로 다른 회차 세 곳에 적혀 있었다. 2026-09-02 에 439 번이 다른 캐러셀로 덮이는 것을
직접 재현했다.

## 어떻게

SQLite 는 기존 컬럼에 AUTOINCREMENT 를 붙일 수 없어 **테이블을 다시 만든다**
(새 테이블 → 복사 → 교체). 행을 복사하면 sqlite_sequence 가 최고값으로 세팅되므로
다음 번호는 그 위에서 이어진다.

이미 AUTOINCREMENT 면 아무것도 하지 않는다. SQLite 가 아니면 건너뛴다
(다른 DB 는 시퀀스를 쓰므로 이 문제가 없다).
"""

from alembic import op
import sqlalchemy as sa

revision = "d1e8c3a97b41"
down_revision = "c7f2a1d94b30"
branch_labels = None
depends_on = None

TABLE = "generated_carousels"

# 컬럼 순서까지 기존 테이블과 같아야 INSERT ... SELECT 가 안전하다.
COLUMNS = (
    "id, user_id, source_post_id, title, canvas_data, "
    "template_id, status, created_at, updated_at"
)

NEW_TABLE_SQL = f"""
CREATE TABLE {TABLE}__new (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    source_post_id INTEGER,
    title VARCHAR(500) NOT NULL,
    canvas_data JSON NOT NULL,
    template_id VARCHAR(100) NOT NULL,
    status VARCHAR(9) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users (id),
    FOREIGN KEY(source_post_id) REFERENCES collected_posts (id)
)
"""


def _already_autoincrement(bind) -> bool:
    row = bind.execute(sa.text(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=:t"
    ), {"t": TABLE}).fetchone()
    return bool(row) and "AUTOINCREMENT" in (row[0] or "").upper()


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    if _already_autoincrement(bind):
        return

    before = bind.execute(sa.text(f"SELECT count(*) FROM {TABLE}")).scalar()

    # 교체하는 동안 FK 검사를 끈다 — 켜 두면 DROP 에서 걸린다.
    op.execute("PRAGMA foreign_keys=OFF")
    op.execute(NEW_TABLE_SQL)
    op.execute(f"INSERT INTO {TABLE}__new ({COLUMNS}) SELECT {COLUMNS} FROM {TABLE}")
    op.execute(f"DROP TABLE {TABLE}")
    op.execute(f"ALTER TABLE {TABLE}__new RENAME TO {TABLE}")
    op.execute("PRAGMA foreign_keys=ON")

    after = bind.execute(sa.text(f"SELECT count(*) FROM {TABLE}")).scalar()
    if before != after:
        raise RuntimeError(f"캐러셀 행 수가 달라졌습니다: {before} → {after}")


def downgrade() -> None:
    """AUTOINCREMENT 만 떼고 되돌린다(번호 재사용 문제가 다시 생긴다)."""
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    if not _already_autoincrement(bind):
        return

    op.execute("PRAGMA foreign_keys=OFF")
    op.execute(NEW_TABLE_SQL.replace("PRIMARY KEY AUTOINCREMENT", "PRIMARY KEY"))
    op.execute(f"INSERT INTO {TABLE}__new ({COLUMNS}) SELECT {COLUMNS} FROM {TABLE}")
    op.execute(f"DROP TABLE {TABLE}")
    op.execute(f"ALTER TABLE {TABLE}__new RENAME TO {TABLE}")
    op.execute("PRAGMA foreign_keys=ON")
