import calendar
import secrets
import sqlite3
import string
from contextlib import closing
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

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

        for ddl in (
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_public_id ON companies(public_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_masters_public_id ON masters(public_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_tg_id ON companies(tg_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_masters_tg_id ON masters(tg_id)",
        ):
            try:
                c.execute(ddl)
            except (sqlite3.OperationalError, sqlite3.IntegrityError):
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
            CREATE TABLE IF NOT EXISTS company_verifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                required_info TEXT,
                last_action_at TEXT,
                passport_photo_file_id TEXT,
                passport_video_file_id TEXT,
                passport_video_deleted_at TEXT
            )
        """
        )

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """
        )


# Helpers ---------------------------------------------------------------------



def _row(row) -> Optional[Dict]:
    return dict(row) if row else None



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


def set_company_kyc_status(company_id: int, status: str):
    with closing(get_conn()) as conn, conn:
        conn.execute("UPDATE companies SET kyc_status = ? WHERE id = ?", (status, company_id))


def create_company_verification(
    company_id: int,
    passport_photo_file_id: str,
    passport_video_file_id: str,
) -> dict:
    created_at = utc_now_iso()
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            INSERT INTO company_verifications (
                company_id,
                status,
                created_at,
                updated_at,
                last_action_at,
                passport_photo_file_id,
                passport_video_file_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                company_id,
                "WAITING",
                created_at,
                created_at,
                created_at,
                passport_photo_file_id,
                passport_video_file_id,
            ),
        )
        c = conn.cursor()
        c.execute("SELECT * FROM company_verifications WHERE rowid = last_insert_rowid()")
        data = _row(c.fetchone())
    set_company_kyc_status(company_id, "waiting")
    return data


def get_company_verification_by_company_id(company_id: int) -> Optional[dict]:
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT * FROM company_verifications
            WHERE company_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """,
            (company_id,),
        )
        return _row(c.fetchone())


def update_company_verification_status(
    verification_id: int,
    status: str,
    *,
    admin_id: Optional[int] = None,
    reason: Optional[str] = None,
) -> Optional[dict]:
    updated_at = utc_now_iso()
    with closing(get_conn()) as conn, conn:
        video_deleted_at = None
        clear_video = status in {"APPROVED", "DECLINED"}
        if clear_video:
            video_deleted_at = updated_at
        conn.execute(
            """
            UPDATE company_verifications
            SET status = ?,
                updated_at = ?,
                last_action_at = ?,
                passport_video_file_id = CASE WHEN ? THEN NULL ELSE passport_video_file_id END,
                passport_video_deleted_at = COALESCE(passport_video_deleted_at, ?)
            WHERE id = ?
        """,
            (status, updated_at, updated_at, 1 if clear_video else 0, video_deleted_at, verification_id),
        )
        c = conn.cursor()
        c.execute("SELECT * FROM company_verifications WHERE id = ?", (verification_id,))
        data = _row(c.fetchone())
        if data and admin_id is not None and reason:
            log_admin_action(
                admin_id=admin_id,
                entity_type="company_verification",
                entity_id=verification_id,
                action=f"status_{status.lower()}",
                reason=reason,
            )
        if data and status in {"APPROVED", "DECLINED"}:
            set_company_kyc_status(data["company_id"], status.lower())
        return data


def log_admin_action(
    *,
    admin_id: int,
    entity_type: str,
    entity_id: int,
    action: str,
    reason: str,
):
    created_at = utc_now_iso()
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            INSERT INTO action_log (admin_id, entity_type, entity_id, action, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (admin_id, entity_type, entity_id, action, reason, created_at),
        )


def log_company_document_view(
    *,
    admin_id: int,
    verification_id: int,
    reason: str,
):
    log_admin_action(
        admin_id=admin_id,
        entity_type="company_verification",
        entity_id=verification_id,
        action="view_passport_photo",
        reason=reason,
    )


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
                reminder_sent_at, final_decision_at, attempts_count, master_comment
            )
            VALUES (?, ?, ?, 'pending_company_response', ?, ?, NULL, NULL, NULL, NULL, ?, ?)
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
              AND status = 'pending_company_response'
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
                status = 'company_responded',
                updated_at = ?,
                final_decision_at = ?
            WHERE id = ?
        """,
            (comment, files_message_id, now, now, appeal_id),
        )


def delete_review(review_id: int):
    with closing(get_conn()) as conn, conn:
        conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
