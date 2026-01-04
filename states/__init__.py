"""
Управление состояниями пользователей (state machine)
"""
from .state_manager import (
    get_state,
    pop_state,
    set_state,
    clear_expired_states,
)

__all__ = [
    "get_state",
    "pop_state",
    "set_state",
    "clear_expired_states",
]

