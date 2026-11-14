"""存量库表的幂等补丁（MVP 未上 Alembic 前，在 init_db 中执行）。"""
from __future__ import annotations

from sqlalchemy import inspect, text

_UK_NAME = "uk_users_platform_openid"


def migrate_users_platform(engine) -> None:
    """为 users 增加 platform、放宽 openid、改为 (platform, openid) 唯一，并回填存量。

    新库由 create_all 直接建出目标结构，本函数应呈幂等、可重复执行。
    存量微信用户回填 platform='weixin'；openid 以 h5_ 开头的回填为 h5。
    """
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return

    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            _migrate_sqlite(conn)
        else:
            _migrate_server(conn, dialect)

    # 约束补齐后再回填一次，避免迁移过程中漏网
    with engine.begin() as conn:
        _backfill_platform(conn)


def _backfill_platform(conn) -> None:
    conn.execute(
        text(
            "UPDATE users SET platform = 'h5' "
            "WHERE openid LIKE 'h5_%' AND (platform IS NULL OR platform = '' OR platform = 'weixin')"
        )
    )
    conn.execute(
        text(
            "UPDATE users SET platform = 'weixin' "
            "WHERE platform IS NULL OR platform = ''"
        )
    )


def _column_names(conn, table: str) -> set[str]:
    insp = inspect(conn)
    return {c["name"] for c in insp.get_columns(table)}


def _unique_on_openid_only(conn, table: str = "users") -> list[str]:
    insp = inspect(conn)
    names: list[str] = []
    for uq in insp.get_unique_constraints(table):
        cols = list(uq.get("column_names") or [])
        if cols == ["openid"] and uq.get("name"):
            names.append(uq["name"])
    for idx in insp.get_indexes(table):
        cols = list(idx.get("column_names") or [])
        if idx.get("unique") and cols == ["openid"] and idx.get("name"):
            if idx["name"] not in names:
                names.append(idx["name"])
    return names


def _has_platform_openid_unique(conn, table: str = "users") -> bool:
    insp = inspect(conn)
    wanted = {"platform", "openid"}
    for uq in insp.get_unique_constraints(table):
        if set(uq.get("column_names") or []) == wanted:
            return True
    for idx in insp.get_indexes(table):
        if idx.get("unique") and set(idx.get("column_names") or []) == wanted:
            return True
    return False


def _sqlite_needs_rebuild(conn) -> bool:
    cols = _column_names(conn, "users")
    if "platform" not in cols:
        return True
    if _unique_on_openid_only(conn):
        return True
    if not _has_platform_openid_unique(conn):
        return True
    return False


def _migrate_sqlite(conn) -> None:
    if not _sqlite_needs_rebuild(conn):
        return

    cols = _column_names(conn, "users")
    platform_expr = "platform" if "platform" in cols else "'weixin'"
    conn.execute(
        text(
            """
            CREATE TABLE users_platform_mig (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                openid VARCHAR(128) NOT NULL,
                unionid VARCHAR(128),
                platform VARCHAR(16) NOT NULL DEFAULT 'weixin',
                username VARCHAR(32) NOT NULL,
                avatar_text VARCHAR(4) NOT NULL,
                avatar_color VARCHAR(7) NOT NULL,
                last_login_at DATETIME,
                status INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                CONSTRAINT uk_users_platform_openid UNIQUE (platform, openid),
                CONSTRAINT uq_users_username UNIQUE (username)
            )
            """
        )
    )
    conn.execute(
        text(
            f"""
            INSERT INTO users_platform_mig (
                id, openid, unionid, platform, username,
                avatar_text, avatar_color, last_login_at,
                status, created_at, updated_at
            )
            SELECT
                id, openid, unionid,
                CASE
                    WHEN openid LIKE 'h5_%' THEN 'h5'
                    WHEN {platform_expr} IS NULL OR {platform_expr} = '' THEN 'weixin'
                    ELSE {platform_expr}
                END,
                username, avatar_text, avatar_color, last_login_at,
                status, created_at, updated_at
            FROM users
            """
        )
    )
    conn.execute(text("DROP TABLE users"))
    conn.execute(text("ALTER TABLE users_platform_mig RENAME TO users"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_platform ON users (platform)"))


def _migrate_server(conn, dialect: str) -> None:
    cols = {c["name"]: c for c in inspect(conn).get_columns("users")}
    if "platform" not in cols:
        if dialect in ("mysql", "mariadb"):
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN platform VARCHAR(16) NOT NULL DEFAULT 'weixin'"
                )
            )
        elif dialect == "postgresql":
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN platform VARCHAR(16) NOT NULL DEFAULT 'weixin'"
                )
            )
        else:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN platform VARCHAR(16) NOT NULL DEFAULT 'weixin'"
                )
            )
        conn.execute(text("CREATE INDEX ix_users_platform ON users (platform)"))

    # 放宽 openid / unionid 长度（MySQL 需要 MODIFY；SQLite 已在 rebuild 中处理）
    if dialect in ("mysql", "mariadb"):
        conn.execute(text("ALTER TABLE users MODIFY openid VARCHAR(128) NOT NULL"))
        conn.execute(text("ALTER TABLE users MODIFY unionid VARCHAR(128) NULL"))
    elif dialect == "postgresql":
        conn.execute(text("ALTER TABLE users ALTER COLUMN openid TYPE VARCHAR(128)"))
        conn.execute(text("ALTER TABLE users ALTER COLUMN unionid TYPE VARCHAR(128)"))

    for name in _unique_on_openid_only(conn):
        _drop_index_or_constraint(conn, dialect, name)

    if not _has_platform_openid_unique(conn):
        if dialect in ("mysql", "mariadb"):
            conn.execute(
                text(
                    f"ALTER TABLE users ADD UNIQUE KEY {_UK_NAME} (platform, openid)"
                )
            )
        else:
            conn.execute(
                text(
                    f"ALTER TABLE users ADD CONSTRAINT {_UK_NAME} UNIQUE (platform, openid)"
                )
            )


def _drop_index_or_constraint(conn, dialect: str, name: str) -> None:
    if dialect in ("mysql", "mariadb"):
        conn.execute(text(f"ALTER TABLE users DROP INDEX `{name}`"))
    elif dialect == "postgresql":
        conn.execute(text(f'ALTER TABLE users DROP CONSTRAINT IF EXISTS "{name}"'))
        conn.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
    else:
        conn.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
