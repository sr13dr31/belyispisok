"""
Управление состояниями пользователей в БД
"""
import json
from contextlib import closing
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from db import get_conn, utc_now_iso


@dataclass
class PendingState:
    action: str
    data: Dict[str, Any]


def set_state(tg_id: int, action: str, **data):
    """
    Устанавливает состояние для пользователя.
    Состояние сохраняется в БД.
    """
    now = utc_now_iso()
    data_json = json.dumps(data, ensure_ascii=False)
    
    with closing(get_conn()) as conn, conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO user_states (tg_id, action, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (tg_id, action, data_json, now, now),
        )


def get_state(tg_id: int) -> Optional[PendingState]:
    """
    Получает текущее состояние пользователя из БД.
    """
    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT action, data FROM user_states WHERE tg_id = ?",
            (tg_id,),
        )
        row = c.fetchone()
        if not row:
            return None
        
        try:
            data = json.loads(row["data"]) if row["data"] else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        
        return PendingState(action=row["action"], data=data)


def pop_state(tg_id: int) -> Optional[PendingState]:
    """
    Получает и удаляет состояние пользователя из БД.
    """
    state = get_state(tg_id)
    if state:
        with closing(get_conn()) as conn, conn:
            conn.execute("DELETE FROM user_states WHERE tg_id = ?", (tg_id,))
    return state


def clear_expired_states(max_age_hours: int = 24):
    """
    Удаляет устаревшие состояния (старше max_age_hours часов).
    """
    threshold = datetime.utcnow() - timedelta(hours=max_age_hours)
    threshold_iso = threshold.isoformat(timespec="seconds")
    
    with closing(get_conn()) as conn, conn:
        conn.execute(
            "DELETE FROM user_states WHERE created_at < ?",
            (threshold_iso,),
        )

