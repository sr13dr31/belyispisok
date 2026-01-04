import calendar
import json
import secrets
import sqlite3
import string
from contextlib import closing
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from config import DB_PATH
from security import decrypt_passport, encrypt_passport


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_conn()) as conn, conn:
        c = conn.cursor()

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                tg_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                role TEXT,
                phone TEXT
            )
        """
        )

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                city TEXT,
                responsible_phone TEXT,
                public_id TEXT,
                created_at TEXT NOT NULL,
                subscription_until TEXT,
                subscription_level TEXT,
                kyc_status TEXT,
                blocked INTEGER DEFAULT 0
            )
        """
        )

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS masters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                public_id TEXT,
                phone TEXT,
                passport TEXT,
                created_at TEXT NOT NULL,
                blocked INTEGER DEFAULT 0,
                notes TEXT,
                passport_locked INTEGER DEFAULT 0
            )
        """
        )

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS employments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                master_id INTEGER NOT NULL,
                company_id INTEGER NOT NULL,
                position TEXT,
                started_at TEXT,
                ended_at TEXT,
                status TEXT,
                risk_level TEXT,
                recommendation TEXT,
                risk_reason TEXT,
                leave_requested_at TEXT
            )
        """
        )

        # Миграции
        for ddl in (
            "ALTER TABLE users ADD COLUMN phone TEXT",
            "ALTER TABLE masters ADD COLUMN passport TEXT",
            "ALTER TABLE masters ADD COLUMN passport_locked INTEGER DEFAULT 0",
            "ALTER TABLE companies ADD COLUMN subscription_until TEXT",
            "ALTER TABLE companies ADD COLUMN subscription_level TEXT",
            "ALTER TABLE companies ADD COLUMN created_at TEXT",
            "ALTER TABLE companies ADD COLUMN kyc_status TEXT",
            "ALTER TABLE companies ADD COLUMN blocked INTEGER DEFAULT 0",
            "ALTER TABLE masters ADD COLUMN blocked INTEGER DEFAULT 0",
            "ALTER TABLE masters ADD COLUMN notes TEXT",
            "ALTER TABLE masters ADD COLUMN created_at TEXT",
            "ALTER TABLE employments ADD COLUMN leave_requested_at TEXT",
        ):
            try:
                c.execute(ddl)
            except sqlite3.OperationalError:
                pass

        now = utc_now_iso()
        c.execute("UPDATE companies SET created_at = ? WHERE created_at IS NULL", (now,))
        c.execute("UPDATE masters SET created_at = ? WHERE created_at IS NULL", (now,))
        c.execute("UPDATE companies SET kyc_status = 'pending' WHERE kyc_status IS NULL")

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                master_id INTEGER NOT NULL,
                company_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                employment_id INTEGER,
                rating INTEGER
            )
        """
        )
        for ddl in (
            "ALTER TABLE reviews ADD COLUMN employment_id INTEGER",
            "ALTER TABLE reviews ADD COLUMN rating INTEGER",
        ):
            try:
                c.execute(ddl)
            except sqlite3.OperationalError:
                pass

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS review_appeals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id INTEGER NOT NULL,
                master_id INTEGER NOT NULL,
                company_id INTEGER,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                master_comment TEXT,
                company_comment TEXT,
                company_files_message_id INTEGER,
                master_files_message_id INTEGER,
                admin_comment TEXT,
                reminder_sent_at TEXT,
                final_decision_at TEXT,
                attempts_count INTEGER DEFAULT 0
            )
        """
        )
        for ddl in (
            "ALTER TABLE review_appeals ADD COLUMN reminder_sent_at TEXT",
            "ALTER TABLE review_appeals ADD COLUMN final_decision_at TEXT",
            "ALTER TABLE review_appeals ADD COLUMN attempts_count INTEGER DEFAULT 0",
            "ALTER TABLE review_appeals ADD COLUMN master_files_message_id INTEGER",
            "ALTER TABLE review_appeals ADD COLUMN master_comment TEXT",
        ):
            try:
                c.execute(ddl)
            except sqlite3.OperationalError:
                pass

        # Таблица для состояний пользователей (state machine)
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS user_states (
                tg_id INTEGER PRIMARY KEY,
                action TEXT NOT NULL,
                data TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """
        )

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT
            )
        """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                description TEXT
            )
        """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_role_permissions (
                role_id INTEGER NOT NULL,
                permission_id INTEGER NOT NULL,
                PRIMARY KEY (role_id, permission_id),
                FOREIGN KEY (role_id) REFERENCES admin_roles(id),
                FOREIGN KEY (permission_id) REFERENCES admin_permissions(id)
            )
        """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role_id INTEGER NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                last_login_at TEXT,
                FOREIGN KEY (role_id) REFERENCES admin_roles(id)
            )
        """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER,
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id TEXT,
                meta_json TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (actor_id) REFERENCES admin_users(id)
            )
        """
        )
        seed_admin_roles_permissions(conn)


# Helpers ---------------------------------------------------------------------


DEFAULT_ADMIN_PERMISSIONS: Tuple[Tuple[str, str], ...] = (
    ("admin.view_dashboard", "Доступ к главной панели"),
    ("admin.manage_admins", "Управление администраторами и ролями"),
    ("companies.view", "Просмотр компаний"),
    ("companies.manage", "Управление компаниями"),
    ("masters.view", "Просмотр исполнителей"),
    ("masters.manage", "Управление исполнителями"),
    ("appeals.view", "Просмотр споров и апелляций"),
    ("appeals.resolve", "Решение споров и апелляций"),
    ("kyc.verify", "Верификация исполнителей и компаний"),
    ("finance.view", "Просмотр финансовых данных"),
    ("finance.manage", "Управление подписками и платежами"),
    ("support.view", "Просмотр обращений поддержки"),
    ("support.manage", "Операции поддержки и ручные правки"),
    ("analytics.view", "Просмотр аналитики"),
    ("audit.view", "Просмотр журнала действий"),
    ("data.export", "Экспорт данных"),
)

DEFAULT_ADMIN_ROLES: Tuple[Tuple[str, str], ...] = (
    ("SuperAdmin", "Полный доступ"),
    ("Compliance", "Юрист и комплаенс"),
    ("DisputeModerator", "Модератор споров"),
    ("KYCOperator", "KYC оператор"),
    ("Finance", "Финансы"),
    ("Support", "Поддержка"),
    ("Analyst", "Аналитик (только чтение)"),
)

DEFAULT_ADMIN_ROLE_PERMISSIONS: Dict[str, Tuple[str, ...]] = {
    "SuperAdmin": tuple(code for code, _ in DEFAULT_ADMIN_PERMISSIONS),
    "Compliance": (
        "admin.view_dashboard",
        "companies.view",
        "companies.manage",
        "masters.view",
        "appeals.view",
        "audit.view",
        "data.export",
    ),
    "DisputeModerator": (
        "admin.view_dashboard",
        "appeals.view",
        "appeals.resolve",
        "audit.view",
    ),
    "KYCOperator": (
        "admin.view_dashboard",
        "companies.view",
        "masters.view",
        "masters.manage",
        "kyc.verify",
        "audit.view",
    ),
    "Finance": (
        "admin.view_dashboard",
        "companies.view",
        "finance.view",
        "finance.manage",
        "audit.view",
    ),
    "Support": (
        "admin.view_dashboard",
        "companies.view",
        "masters.view",
        "support.view",
        "support.manage",
        "audit.view",
    ),
    "Analyst": (
        "admin.view_dashboard",
        "analytics.view",
    ),
}


def _row(row) -> Optional[Dict]:
    return dict(row) if row else None


def seed_admin_roles_permissions(conn: sqlite3.Connection) -> None:
    c = conn.cursor()
    c.executemany(
        "INSERT OR IGNORE INTO admin_roles (name, description) VALUES (?, ?)",
        DEFAULT_ADMIN_ROLES,
    )
    c.executemany(
        "INSERT OR IGNORE INTO admin_permissions (code, description) VALUES (?, ?)",
        DEFAULT_ADMIN_PERMISSIONS,
    )
    c.execute("SELECT id, name FROM admin_roles")
    roles = {row["name"]: row["id"] for row in c.fetchall()}
    c.execute("SELECT id, code FROM admin_permissions")
    permissions = {row["code"]: row["id"] for row in c.fetchall()}
    assignments = []
    for role_name, permission_codes in DEFAULT_ADMIN_ROLE_PERMISSIONS.items():
        role_id = roles.get(role_name)
        if not role_id:
            continue
        for code in permission_codes:
            permission_id = permissions.get(code)
            if permission_id:
                assignments.append((role_id, permission_id))
    c.executemany(
        "INSERT OR IGNORE INTO admin_role_permissions (role_id, permission_id) VALUES (?, ?)",
        assignments,
    )


def _migrate_legacy_passport(master_id: int, passport: Optional[str]) -> None:
    if not passport:
        return
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "UPDATE masters SET passport = ? WHERE id = ?",
            (encrypt_passport(passport), master_id),
        )


def _decrypt_passport_field(data: Optional[Dict], key: str = "passport") -> Optional[Dict]:
    if data and data.get(key):
        decrypted, legacy = decrypt_passport(data[key])
        data[key] = decrypted
        if legacy and data.get("id"):
            _migrate_legacy_passport(data["id"], decrypted)
    return data


def _decrypt_passport_in_list(items: List[Dict], key: str = "passport") -> List[Dict]:
    for item in items:
        if item.get(key):
            decrypted, legacy = decrypt_passport(item[key])
            item[key] = decrypted
            if legacy and item.get("id"):
                _migrate_legacy_passport(item["id"], decrypted)
    return items


def migrate_legacy_passports(limit: Optional[int] = None) -> int:
    migrated = 0
    with closing(get_conn()) as conn, conn:
        c = conn.cursor()
        query = "SELECT id, passport FROM masters WHERE passport IS NOT NULL AND passport != ''"
        params: List[Any] = []
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        c.execute(query, params)
        for row in c.fetchall():
            decrypted, legacy = decrypt_passport(row["passport"])
            if legacy and decrypted:
                conn.execute(
                    "UPDATE masters SET passport = ? WHERE id = ?",
                    (encrypt_passport(decrypted), row["id"]),
                )
                migrated += 1
    return migrated


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _add_months(base: datetime, months: int) -> datetime:
    year = base.year + (base.month - 1 + months) // 12
    month = ((base.month - 1 + months) % 12) + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return base.replace(year=year, month=month, day=day)


def generate_public_id(prefix: str, length: int = 6) -> str:
    alphabet = string.digits
    while True:
        random_part = "".join(secrets.choice(alphabet) for _ in range(length))
        public_id = f"{prefix}-{random_part}"
        with closing(get_conn()) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT 1 FROM masters WHERE public_id = ? UNION SELECT 1 FROM companies WHERE public_id = ?",
                (public_id, public_id),
            )
            if not c.fetchone():
                return public_id


# Users -----------------------------------------------------------------------


def get_or_create_user(message: Any) -> dict:
    tg_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    with closing(get_conn()) as conn, conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
        row = c.fetchone()
        if row:
            return dict(row)

        c.execute(
            """
            INSERT INTO users (tg_id, username, first_name, role)
            VALUES (?, ?, ?, NULL)
        """,
            (tg_id, username, first_name),
        )
        return {
            "tg_id": tg_id,
            "username": username,
            "first_name": first_name,
            "role": None,
            "phone": None,
        }


def set_user_role(tg_id: int, role: str):
    with closing(get_conn()) as conn, conn:
        conn.execute("UPDATE users SET role = ? WHERE tg_id = ?", (role, tg_id))


def get_user(tg_id: int) -> Optional[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
        return _row(c.fetchone())


def set_user_phone(tg_id: int, phone: str):
    with closing(get_conn()) as conn, conn:
        conn.execute("UPDATE users SET phone = ? WHERE tg_id = ?", (phone, tg_id))


# Companies & Masters ---------------------------------------------------------


def _serialize_master(row) -> Optional[dict]:
    return _decrypt_passport_field(_row(row))


def create_company(tg_id: int, name: str, city: Optional[str], responsible_phone: Optional[str]) -> dict:
    public_id = generate_public_id("C")
    created_at = utc_now_iso()
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            INSERT INTO companies (tg_id, name, city, responsible_phone, public_id, created_at, kyc_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (tg_id, name, city, responsible_phone, public_id, created_at, "pending"),
        )
        c = conn.cursor()
        c.execute("SELECT * FROM companies WHERE rowid = last_insert_rowid()")
        return dict(c.fetchone())


def create_master(tg_id: int, full_name: str, phone: Optional[str], passport: Optional[str]) -> dict:
    public_id = generate_public_id("M")
    created_at = utc_now_iso()
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            INSERT INTO masters (tg_id, full_name, phone, passport, public_id, passport_locked, created_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """,
            (tg_id, full_name, phone, encrypt_passport(passport), public_id, created_at),
        )
        c = conn.cursor()
        c.execute("SELECT * FROM masters WHERE rowid = last_insert_rowid()")
        return _serialize_master(c.fetchone())


def get_company_by_user(tg_id: int) -> Optional[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM companies WHERE tg_id = ?", (tg_id,))
        return _row(c.fetchone())


def get_master_by_user(tg_id: int) -> Optional[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM masters WHERE tg_id = ?", (tg_id,))
        return _serialize_master(c.fetchone())


def get_company_by_public_id(public_id: str) -> Optional[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM companies WHERE public_id = ?", (public_id,))
        return _row(c.fetchone())


def get_master_by_public_id(public_id: str) -> Optional[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM masters WHERE public_id = ?", (public_id,))
        return _serialize_master(c.fetchone())


def get_company_by_id(company_id: int) -> Optional[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM companies WHERE id = ?", (company_id,))
        return _row(c.fetchone())


def get_master_by_id(master_id: int) -> Optional[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM masters WHERE id = ?", (master_id,))
        return _serialize_master(c.fetchone())


def get_company_requests_count(company_id: int) -> int:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT COUNT(*)
            FROM employments
            WHERE company_id = ? AND status = 'pending_company_confirm'
        """,
            (company_id,),
        )
        (count,) = c.fetchone()
        return count


def get_company_leave_requests_count(company_id: int) -> int:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT COUNT(*)
            FROM employments
            WHERE company_id = ? AND status = 'leave_requested'
            """,
            (company_id,),
        )
        (count,) = c.fetchone()
        return count


def company_has_active_subscription(company: dict) -> bool:
    sub_until = company.get("subscription_until")
    if not sub_until:
        return False
    try:
        dt = datetime.fromisoformat(sub_until)
    except ValueError:
        return False
    return dt >= datetime.utcnow()


def set_company_subscription(company_id: int, months: int, level: str = "basic"):
    with closing(get_conn()) as conn, conn:
        if months <= 0:
            conn.execute(
                "UPDATE companies SET subscription_until = NULL, subscription_level = NULL WHERE id = ?",
                (company_id,),
            )
            return

        c = conn.cursor()
        c.execute(
            "SELECT subscription_until FROM companies WHERE id = ?",
            (company_id,),
        )
        row = c.fetchone()
        now = datetime.utcnow()
        if row and row["subscription_until"]:
            try:
                current_until = datetime.fromisoformat(row["subscription_until"])
            except ValueError:
                current_until = now
        else:
            current_until = now

        base = current_until if current_until >= now else now
        new_until = _add_months(base, months)

        conn.execute(
            """
            UPDATE companies
            SET subscription_until = ?, subscription_level = ?
            WHERE id = ?
        """,
            (new_until.isoformat(timespec="seconds"), level, company_id),
        )


def set_company_blocked(company_id: int, blocked: bool):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "UPDATE companies SET blocked = ? WHERE id = ?",
            (1 if blocked else 0, company_id),
        )


def set_master_blocked(master_id: int, blocked: bool):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "UPDATE masters SET blocked = ? WHERE id = ?",
            (1 if blocked else 0, master_id),
        )


def set_master_passport_locked(master_id: int, locked: bool):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "UPDATE masters SET passport_locked = ? WHERE id = ?",
            (1 if locked else 0, master_id),
        )


def update_master_profile(
    master_id: int,
    *,
    full_name: Optional[str] = None,
    phone: Optional[str] = None,
    passport: Optional[str] = None,
    passport_locked: Optional[bool] = None,
):
    sets = []
    params: List[Any] = []

    if full_name is not None:
        sets.append("full_name = ?")
        params.append(full_name)
    if phone is not None:
        sets.append("phone = ?")
        params.append(phone)
    if passport is not None:
        sets.append("passport = ?")
        params.append(encrypt_passport(passport))
    if passport_locked is not None:
        sets.append("passport_locked = ?")
        params.append(1 if passport_locked else 0)

    if not sets:
        return

    params.append(master_id)
    with closing(get_conn()) as conn, conn:
        conn.execute(f"UPDATE masters SET {', '.join(sets)} WHERE id = ?", params)


# Employments -----------------------------------------------------------------


def get_company_employments(company_id: int) -> List[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT e.*, m.full_name, m.public_id as master_public_id
            FROM employments e
            JOIN masters m ON e.master_id = m.id
            WHERE e.company_id = ? AND e.status IN ('accepted', 'leave_requested')
            ORDER BY e.id DESC
        """,
            (company_id,),
        )
        return [dict(row) for row in c.fetchall()]


def get_company_ended_employments(
    company_id: int, limit: Optional[int] = None, offset: int = 0
) -> List[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        params: List[Any] = [company_id]
        query = """
            SELECT e.*, m.full_name, m.public_id as master_public_id
            FROM employments e
            JOIN masters m ON e.master_id = m.id
            WHERE e.company_id = ? AND e.status = 'ended'
            ORDER BY datetime(e.ended_at) DESC, e.id DESC
        """
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        c.execute(query, params)
        return [dict(row) for row in c.fetchall()]


def get_master_employments(master_id: int) -> List[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT e.*, c.name as company_name, c.public_id as company_public_id
            FROM employments e
            JOIN companies c ON e.company_id = c.id
            WHERE e.master_id = ?
            ORDER BY e.id DESC
        """,
            (master_id,),
        )
        return [dict(row) for row in c.fetchall()]


def get_current_employment(master_id: int) -> Optional[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT e.*, c.name as company_name, c.public_id as company_public_id
            FROM employments e
            JOIN companies c ON e.company_id = c.id
            WHERE e.master_id = ?
              AND e.status IN ('accepted', 'leave_requested')
              AND (e.ended_at IS NULL OR e.ended_at = '')
            ORDER BY e.id DESC
            LIMIT 1
        """,
            (master_id,),
        )
        return _row(c.fetchone())


def auto_close_leave_requests() -> List[dict]:
    now = datetime.utcnow()
    threshold = now - timedelta(days=2)
    now_iso = now.isoformat(timespec="seconds")
    threshold_iso = threshold.isoformat(timespec="seconds")

    with closing(get_conn()) as conn, conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT e.id,
                   e.master_id,
                   e.company_id,
                   e.position,
                   e.leave_requested_at,
                   m.tg_id AS master_tg_id,
                   m.full_name AS master_full_name,
                   m.public_id AS master_public_id,
                   c.tg_id AS company_tg_id,
                   c.name AS company_name,
                   c.public_id AS company_public_id
            FROM employments e
            JOIN masters m ON e.master_id = m.id
            JOIN companies c ON e.company_id = c.id
            WHERE e.status = 'leave_requested'
              AND e.leave_requested_at IS NOT NULL
              AND e.leave_requested_at <= ?
              AND (e.ended_at IS NULL OR e.ended_at = '')
            """,
            (threshold_iso,),
        )
        rows = [dict(row) for row in c.fetchall()]
        if rows:
            ids = [row["id"] for row in rows]
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"""
                UPDATE employments
                SET status = 'ended', ended_at = ?
                WHERE id IN ({placeholders})
                """,
                (now_iso, *ids),
            )
        return rows


def has_any_current_employment(master_id: int) -> bool:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT 1
            FROM employments
            WHERE master_id = ?
              AND status IN ('accepted', 'leave_requested')
              AND (ended_at IS NULL OR ended_at = '')
        """,
            (master_id,),
        )
        return c.fetchone() is not None


def has_pending_or_active_employment(master_id: int, company_id: int) -> bool:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT 1
            FROM employments
            WHERE master_id = ?
              AND company_id = ?
              AND status IN ('pending_company_confirm', 'accepted', 'leave_requested')
              AND (ended_at IS NULL OR ended_at = '')
        """,
            (master_id, company_id),
        )
        return c.fetchone() is not None


def has_pending_request_for_company(master_id: int, company_id: int) -> bool:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT 1
            FROM employments
            WHERE master_id = ?
              AND company_id = ?
              AND status = 'pending_company_confirm'
        """,
            (master_id, company_id),
        )
        return c.fetchone() is not None


def create_employment(master_id: int, company_id: int, position: str):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            INSERT INTO employments (master_id, company_id, position, status)
            VALUES (?, ?, ?, 'pending_company_confirm')
        """,
            (master_id, company_id, position),
        )


def get_pending_employments_for_company(company_id: int) -> List[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT e.*, m.full_name, m.public_id as master_public_id
            FROM employments e
            JOIN masters m ON e.master_id = m.id
            WHERE e.company_id = ? AND e.status = 'pending_company_confirm'
            ORDER BY e.id DESC
        """,
            (company_id,),
        )
        return [dict(row) for row in c.fetchall()]


def get_pending_leave_requests_for_company(company_id: int) -> List[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT e.*, m.full_name, m.public_id as master_public_id
            FROM employments e
            JOIN masters m ON e.master_id = m.id
            WHERE e.company_id = ? AND e.status = 'leave_requested'
            ORDER BY e.leave_requested_at ASC, e.id DESC
            """,
            (company_id,),
        )
        return [dict(row) for row in c.fetchall()]


def get_employment_by_id(employment_id: int) -> Optional[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT e.*,
                   m.full_name,
                   m.public_id as master_public_id,
                   m.passport,
                   m.passport_locked,
                   c.name as company_name,
                   c.public_id as company_public_id
            FROM employments e
            JOIN masters m ON e.master_id = m.id
            JOIN companies c ON e.company_id = c.id
            WHERE e.id = ?
        """,
            (employment_id,),
        )
        row = c.fetchone()
        data = _row(row)
        if data and data.get("passport"):
            decrypted, legacy = decrypt_passport(data["passport"])
            data["passport"] = decrypted
            if legacy and data.get("master_id"):
                _migrate_legacy_passport(data["master_id"], decrypted)
        return data


def set_employment_accepted(employment_id: int):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            UPDATE employments
            SET status = 'accepted', started_at = COALESCE(started_at, ?)
            WHERE id = ?
        """,
            (utc_now_iso(), employment_id),
        )


def set_employment_rejected(employment_id: int):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            UPDATE employments
            SET status = 'rejected'
            WHERE id = ?
        """,
            (employment_id,),
        )


def set_employment_leave_requested(employment_id: int):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            UPDATE employments
            SET status = 'leave_requested', leave_requested_at = ?
            WHERE id = ?
        """,
            (utc_now_iso(), employment_id),
        )


def cancel_employment_leave_request(employment_id: int) -> bool:
    with closing(get_conn()) as conn, conn:
        cursor = conn.execute(
            """
            UPDATE employments
            SET status = 'accepted', leave_requested_at = NULL
            WHERE id = ? AND status = 'leave_requested'
            """,
            (employment_id,),
        )
        return cursor.rowcount > 0


def end_employment(employment_id: int):
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            UPDATE employments
            SET status = 'ended', ended_at = ?
            WHERE id = ?
        """,
            (utc_now_iso(), employment_id),
        )


# Reviews ---------------------------------------------------------------------


def create_review(
    company_id: int,
    master_id: int,
    employment_id: Optional[int],
    text: str,
    rating: Optional[int] = None,
):
    with closing(get_conn()) as conn, conn:
        cursor = conn.execute(
            """
            INSERT INTO reviews (master_id, company_id, text, created_at, employment_id, rating)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (master_id, company_id, text, utc_now_iso(), employment_id, rating),
        )
        review_id = cursor.lastrowid
    update_master_rating(master_id)
    return review_id


def get_reviews_for_master(master_id: int) -> List[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT r.*, c.name as company_name, c.public_id as company_public_id
            FROM reviews r
            JOIN companies c ON r.company_id = c.id
            WHERE r.master_id = ?
            ORDER BY r.id DESC
        """,
            (master_id,),
        )
        return [dict(row) for row in c.fetchall()]


def get_master_rating(master_id: int) -> dict:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT AVG(rating) as avg_rating, COUNT(rating) as ratings_count
            FROM reviews
            WHERE master_id = ? AND rating IS NOT NULL
            """,
            (master_id,),
        )
        row = c.fetchone()
        if not row or row["ratings_count"] == 0:
            return {"avg_rating": None, "ratings_count": 0}
        return {
            "avg_rating": round(row["avg_rating"] or 0, 2),
            "ratings_count": row["ratings_count"],
        }


def update_master_rating(master_id: int):
    # Упрощённо: пока только заглушка для последующей оптимизации
    # (хранение средней оценки в таблице masters если потребуется)
    # Сейчас функция просто существует для совместимости.
    get_master_rating(master_id)


def get_reviews_for_employment(employment_id: int) -> List[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT r.*, c.name as company_name, c.public_id as company_public_id
            FROM reviews r
            JOIN companies c ON r.company_id = c.id
            WHERE r.employment_id = ?
            ORDER BY r.id DESC
        """,
            (employment_id,),
        )
        return [dict(row) for row in c.fetchall()]


def get_review_by_id(review_id: int) -> Optional[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT r.*, m.full_name as master_full_name, m.public_id as master_public_id,
                   c.name as company_name, c.public_id as company_public_id
            FROM reviews r
            JOIN masters m ON r.master_id = m.id
            JOIN companies c ON r.company_id = c.id
            WHERE r.id = ?
        """,
            (review_id,),
        )
        return _row(c.fetchone())


# Appeals ---------------------------------------------------------------------


def _get_attempts_count(review_id: int, master_id: int) -> int:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT MAX(attempts_count) as attempts
            FROM review_appeals
            WHERE review_id = ? AND master_id = ?
        """,
            (review_id, master_id),
        )
        row = c.fetchone()
        return row["attempts"] or 0 if row else 0


def create_review_appeal(review_id: int, master_id: int, company_id: Optional[int], reason: str) -> int:
    attempts = _get_attempts_count(review_id, master_id) + 1
    now = utc_now_iso()
    with closing(get_conn()) as conn, conn:
        cursor = conn.execute(
            """
            INSERT INTO review_appeals (
                review_id, master_id, company_id, status,
                created_at, updated_at, company_comment, company_files_message_id,
                admin_comment, reminder_sent_at, final_decision_at, attempts_count, master_comment
            )
            VALUES (?, ?, ?, 'pending_company_response', ?, ?, NULL, NULL, NULL, NULL, NULL, ?, ?)
        """,
            (
                review_id,
                master_id,
                company_id,
                now,
                now,
                attempts,
                reason,
            ),
        )
        return cursor.lastrowid


def get_active_appeal_for_review_and_master(review_id: int, master_id: int) -> Optional[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT * FROM review_appeals
            WHERE review_id = ?
              AND master_id = ?
              AND status IN ('pending_company_response', 'pending_admin_review')
            ORDER BY id DESC
            LIMIT 1
        """,
            (review_id, master_id),
        )
        return _row(c.fetchone())


def can_master_appeal_review(review: dict, master_id: int) -> bool:
    try:
        created_at = datetime.fromisoformat(review["created_at"])
    except (TypeError, ValueError):
        return False

    if datetime.utcnow() - created_at > timedelta(days=14):
        return False

    if _get_attempts_count(review["id"], master_id) >= 3:
        return False

    if get_active_appeal_for_review_and_master(review["id"], master_id):
        return False

    return True


def get_pending_company_appeals(company_id: int) -> List[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT ra.*, r.text as review_text, r.created_at as review_created_at,
                   m.full_name as master_full_name, m.public_id as master_public_id
            FROM review_appeals ra
            JOIN reviews r ON ra.review_id = r.id
            JOIN masters m ON ra.master_id = m.id
            WHERE ra.company_id = ?
              AND ra.status = 'pending_company_response'
            ORDER BY ra.id DESC
        """,
            (company_id,),
        )
        return [dict(row) for row in c.fetchall()]


def get_review_appeal_by_id(appeal_id: int) -> Optional[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT ra.*, r.text as review_text, r.created_at as review_created_at,
                   m.full_name as master_full_name, m.public_id as master_public_id,
                   c2.name as company_name, c2.public_id as company_public_id
            FROM review_appeals ra
            JOIN reviews r ON ra.review_id = r.id
            JOIN masters m ON ra.master_id = m.id
            LEFT JOIN companies c2 ON ra.company_id = c2.id
            WHERE ra.id = ?
        """,
            (appeal_id,),
        )
        return _row(c.fetchone())


def update_review_appeal_company_response(appeal_id: int, comment: Optional[str], files_message_id: Optional[int]):
    now = utc_now_iso()
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            UPDATE review_appeals
            SET company_comment = ?,
                company_files_message_id = ?,
                status = 'pending_admin_review',
                updated_at = ?
            WHERE id = ?
        """,
            (comment, files_message_id, now, appeal_id),
        )


def update_review_appeal_admin_decision(appeal_id: int, status: str, admin_comment: Optional[str]):
    now = utc_now_iso()
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            UPDATE review_appeals
            SET status = ?, admin_comment = ?, updated_at = ?, final_decision_at = ?
            WHERE id = ?
        """,
            (status, admin_comment, now, now, appeal_id),
        )


def delete_review(review_id: int):
    with closing(get_conn()) as conn, conn:
        conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))


# Admin panel -----------------------------------------------------------------


def list_admin_roles() -> List[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM admin_roles ORDER BY name")
        return [dict(row) for row in c.fetchall()]


def list_admin_permissions() -> List[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM admin_permissions ORDER BY code")
        return [dict(row) for row in c.fetchall()]


def get_admin_user_by_username(username: str) -> Optional[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT au.*, ar.name as role_name
            FROM admin_users au
            JOIN admin_roles ar ON ar.id = au.role_id
            WHERE au.username = ?
        """,
            (username,),
        )
        return _row(c.fetchone())


def get_admin_user_by_id(admin_id: int) -> Optional[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT au.*, ar.name as role_name
            FROM admin_users au
            JOIN admin_roles ar ON ar.id = au.role_id
            WHERE au.id = ?
        """,
            (admin_id,),
        )
        return _row(c.fetchone())


def list_admin_users() -> List[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT au.*, ar.name as role_name
            FROM admin_users au
            JOIN admin_roles ar ON ar.id = au.role_id
            ORDER BY au.id DESC
        """
        )
        return [dict(row) for row in c.fetchall()]


def get_role_permissions(role_id: int) -> List[str]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT ap.code
            FROM admin_role_permissions arp
            JOIN admin_permissions ap ON ap.id = arp.permission_id
            WHERE arp.role_id = ?
            ORDER BY ap.code
        """,
            (role_id,),
        )
        return [row["code"] for row in c.fetchall()]


def create_admin_user(username: str, password_hash: str, role_id: int) -> int:
    now = utc_now_iso()
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            INSERT INTO admin_users (username, password_hash, role_id, is_active, created_at)
            VALUES (?, ?, ?, 1, ?)
        """,
            (username, password_hash, role_id, now),
        )
        c = conn.cursor()
        c.execute("SELECT last_insert_rowid()")
        (new_id,) = c.fetchone()
        return int(new_id)


def set_admin_user_active(admin_id: int, is_active: bool) -> None:
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "UPDATE admin_users SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, admin_id),
        )


def set_admin_user_role(admin_id: int, role_id: int) -> None:
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "UPDATE admin_users SET role_id = ? WHERE id = ?",
            (role_id, admin_id),
        )


def update_admin_last_login(admin_id: int) -> None:
    now = utc_now_iso()
    with closing(get_conn()) as conn, conn:
        conn.execute("UPDATE admin_users SET last_login_at = ? WHERE id = ?", (now, admin_id))


def log_admin_action(
    actor_id: Optional[int],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    now = utc_now_iso()
    meta_json = json.dumps(meta or {}, ensure_ascii=False)
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            INSERT INTO admin_audit_log (
                actor_id, action, entity_type, entity_id, meta_json, ip_address, user_agent, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (actor_id, action, entity_type, entity_id, meta_json, ip_address, user_agent, now),
        )


def list_audit_log(limit: int = 100, offset: int = 0) -> List[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT al.*, au.username as actor_username
            FROM admin_audit_log al
            LEFT JOIN admin_users au ON au.id = al.actor_id
            ORDER BY al.id DESC
            LIMIT ? OFFSET ?
        """,
            (limit, offset),
        )
        return [dict(row) for row in c.fetchall()]


def list_companies_admin(search: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        query = "SELECT * FROM companies"
        params: List[Any] = []
        if search:
            if search.isdigit():
                query += " WHERE id = ? OR name LIKE ? OR public_id LIKE ?"
                params.extend([int(search), f"%{search}%", f"%{search}%"])
            else:
                query += " WHERE name LIKE ? OR public_id LIKE ?"
                params.extend([f"%{search}%", f"%{search}%"])
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        c.execute(query, params)
        return [dict(row) for row in c.fetchall()]


def list_masters_admin(search: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        query = "SELECT * FROM masters"
        params: List[Any] = []
        if search:
            if search.isdigit():
                query += " WHERE id = ? OR full_name LIKE ? OR public_id LIKE ?"
                params.extend([int(search), f"%{search}%", f"%{search}%"])
            else:
                query += " WHERE full_name LIKE ? OR public_id LIKE ?"
                params.extend([f"%{search}%", f"%{search}%"])
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        c.execute(query, params)
        return _decrypt_passport_in_list([dict(row) for row in c.fetchall()])


def list_review_appeals_admin(status: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        query = """
            SELECT ra.*, r.text as review_text,
                   m.full_name as master_full_name, m.public_id as master_public_id,
                   c2.name as company_name, c2.public_id as company_public_id
            FROM review_appeals ra
            JOIN reviews r ON ra.review_id = r.id
            JOIN masters m ON ra.master_id = m.id
            LEFT JOIN companies c2 ON ra.company_id = c2.id
        """
        params: List[Any] = []
        if status:
            query += " WHERE ra.status = ?"
            params.append(status)
        query += " ORDER BY ra.id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        c.execute(query, params)
        return [dict(row) for row in c.fetchall()]


def update_company_blocked(company_id: int, blocked: bool) -> None:
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "UPDATE companies SET blocked = ? WHERE id = ?",
            (1 if blocked else 0, company_id),
        )


def update_master_blocked(master_id: int, blocked: bool) -> None:
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "UPDATE masters SET blocked = ? WHERE id = ?",
            (1 if blocked else 0, master_id),
        )


def update_master_notes(master_id: int, notes: Optional[str]) -> None:
    with closing(get_conn()) as conn, conn:
        conn.execute("UPDATE masters SET notes = ? WHERE id = ?", (notes, master_id))


def update_master_passport_locked(master_id: int, locked: bool) -> None:
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "UPDATE masters SET passport_locked = ? WHERE id = ?",
            (1 if locked else 0, master_id),
        )


def update_company_subscription(company_id: int, level: Optional[str], until: Optional[str]) -> None:
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            UPDATE companies SET subscription_level = ?, subscription_until = ?
            WHERE id = ?
        """,
            (level, until, company_id),
        )


def update_company_kyc_status(company_id: int, kyc_status: str) -> None:
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            UPDATE companies SET kyc_status = ?
            WHERE id = ?
        """,
            (kyc_status, company_id),
        )


def get_admin_dashboard_stats() -> dict:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        now = datetime.utcnow()
        day_ago = (now - timedelta(days=1)).isoformat(timespec="seconds")
        week_ago = (now - timedelta(days=7)).isoformat(timespec="seconds")
        today = now.date().isoformat()
        c.execute("SELECT COUNT(*) FROM companies")
        (companies_count,) = c.fetchone()
        c.execute("SELECT COUNT(*) FROM masters")
        (masters_count,) = c.fetchone()
        c.execute("SELECT COUNT(*) FROM review_appeals WHERE status = 'pending_admin_review'")
        (pending_appeals,) = c.fetchone()
        c.execute("SELECT COUNT(*) FROM admin_users WHERE is_active = 1")
        (active_admins,) = c.fetchone()
        c.execute("SELECT COUNT(*) FROM companies WHERE created_at >= ?", (day_ago,))
        (companies_day,) = c.fetchone()
        c.execute("SELECT COUNT(*) FROM companies WHERE created_at >= ?", (week_ago,))
        (companies_week,) = c.fetchone()
        c.execute("SELECT COUNT(*) FROM masters WHERE created_at >= ?", (day_ago,))
        (masters_day,) = c.fetchone()
        c.execute("SELECT COUNT(*) FROM masters WHERE created_at >= ?", (week_ago,))
        (masters_week,) = c.fetchone()
        c.execute(
            """
            SELECT COUNT(*)
            FROM employments
            WHERE status IN ('pending_company_confirm', 'accepted', 'leave_requested')
        """
        )
        (collab_in_process,) = c.fetchone()
        c.execute("SELECT COUNT(*) FROM employments WHERE status = 'ended'")
        (collab_completed,) = c.fetchone()
        c.execute(
            """
            SELECT
                SUM(CASE WHEN rating <= 2 THEN 1 ELSE 0 END) as high,
                SUM(CASE WHEN rating = 3 THEN 1 ELSE 0 END) as medium,
                SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END) as low
            FROM reviews
            WHERE rating IS NOT NULL AND created_at >= ?
        """,
            (week_ago,),
        )
        signals_row = c.fetchone()
        employer_signals = {
            "high": signals_row["high"] or 0,
            "medium": signals_row["medium"] or 0,
            "low": signals_row["low"] or 0,
        }
        c.execute(
            """
            SELECT created_at
            FROM review_appeals
            WHERE status = 'pending_admin_review'
        """
        )
        overdue_cutoff = now - timedelta(hours=48)
        overdue_appeals = 0
        for row in c.fetchall():
            created_at = row["created_at"]
            if not created_at:
                continue
            try:
                created_at_dt = datetime.fromisoformat(created_at)
            except ValueError:
                continue
            if created_at_dt <= overdue_cutoff:
                overdue_appeals += 1
        c.execute(
            """
            SELECT COUNT(*)
            FROM companies
            WHERE subscription_until IS NOT NULL
              AND subscription_until != ''
              AND subscription_until >= ?
        """,
            (today,),
        )
        (active_subscriptions,) = c.fetchone()
        c.execute(
            """
            SELECT COUNT(*)
            FROM companies
            WHERE subscription_until IS NOT NULL
              AND subscription_until != ''
              AND subscription_until < ?
        """,
            (today,),
        )
        (overdue_subscriptions,) = c.fetchone()
        return {
            "companies": companies_count,
            "masters": masters_count,
            "pending_appeals": pending_appeals,
            "active_admins": active_admins,
            "new_registrations": {
                "companies_day": companies_day,
                "companies_week": companies_week,
                "masters_day": masters_day,
                "masters_week": masters_week,
            },
            "collaboration_requests": {
                "in_process": collab_in_process,
                "completed": collab_completed,
            },
            "employer_signals": employer_signals,
            "appeals": {
                "open": pending_appeals,
                "overdue": overdue_appeals,
                "sla_hours": 48,
            },
            "suspicious_activity": {
                "multiple_accounts": 0,
                "anomalous_checks": 0,
                "negative_spike": 0,
            },
            "payments": {
                "active_subscriptions": active_subscriptions,
                "overdue_subscriptions": overdue_subscriptions,
                "mrr": None,
            },
        }
