from typing import List, Optional

from aiogram.utils.keyboard import InlineKeyboardBuilder

from db import get_company_requests_count, get_company_leave_requests_count


def role_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Я исполнитель", callback_data="role_master")
    kb.button(text="Я компания", callback_data="role_company")
    kb.button(text="Я обычный пользователь", callback_data="role_viewer")
    kb.adjust(1)
    return kb.as_markup()


def master_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Мой профиль", callback_data="master_profile")
    kb.button(text="Изменить профиль", callback_data="master_edit_profile")
    kb.button(text="Отправить запрос в компанию", callback_data="master_link_company")
    kb.button(text="Запросить увольнение", callback_data="master_request_leave")
    kb.button(text="Мои отзывы", callback_data="master_reviews")
    kb.button(text="Поддержка", callback_data="master_support")
    kb.adjust(1)
    return kb.as_markup()


def company_menu_kb(company_id: Optional[int] = None):
    kb = InlineKeyboardBuilder()
    kb.button(text="Профиль компании", callback_data="company_profile")
    kb.button(text="Изменить профиль", callback_data="company_edit_profile")
    kb.button(text="Мои сотрудники", callback_data="company_employees")
    kb.button(text="Проверить сотрудника по ID", callback_data="company_check_master")

    label = "Запросы"
    if company_id is not None:
        total = get_company_requests_count(company_id)
        total += get_company_leave_requests_count(company_id)
        if total > 0:
            label = f"Запросы ({total})"
    kb.button(text=label, callback_data="company_view_requests")

    kb.button(text="Жалобы на отзывы", callback_data="company_view_appeals")
    kb.button(text="Подписка и оплата", callback_data="company_subscription")
    kb.button(text="Поддержка", callback_data="company_support")
    kb.adjust(1)
    return kb.as_markup()


def viewer_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Проверить исполнителя по ID", callback_data="viewer_check_master")
    kb.button(text="О сервисе", callback_data="viewer_about")
    kb.adjust(1)
    return kb.as_markup()


def company_requests_kb(requests: List[dict]):
    kb = InlineKeyboardBuilder()
    for r in requests:
        text = f"{r['full_name']} ({r['master_public_id']}) — {r['position'] or 'без должности'}"
        kb.button(
            text=text,
            callback_data=f"company_request_{r['id']}",
        )
    kb.adjust(1)
    return kb.as_markup()


def company_leave_requests_kb(requests: List[dict]):
    kb = InlineKeyboardBuilder()
    for r in requests:
        text = f"{r['full_name']} ({r['master_public_id']}) — запрос увольнения"
        kb.button(
            text=text,
            callback_data=f"company_leave_request_{r['id']}",
        )
    kb.adjust(1)
    return kb.as_markup()


def company_request_actions_kb(employment_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Паспорт совпадает, принять", callback_data=f"company_request_accept_{employment_id}")
    kb.button(text="❌ Паспорт не совпадает, отклонить", callback_data=f"company_request_reject_{employment_id}")
    kb.adjust(1)
    return kb.as_markup()


def company_employees_kb(employments: List[dict]):
    kb = InlineKeyboardBuilder()
    for e in employments:
        status_label = "работает"
        if e["status"] == "leave_requested":
            status_label = "запрос увольнения"
        text = f"{e['full_name']} ({e['master_public_id']}) — {status_label}"
        kb.button(
            text=text,
            callback_data=f"company_employee_{e['id']}",
        )
    kb.adjust(1)
    return kb.as_markup()


def company_ended_list_button_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Уволенные сотрудники", callback_data="company_ended_list_0")
    kb.adjust(1)
    return kb.as_markup()


def company_ended_employees_kb(employments: List[dict], next_offset: Optional[int] = None):
    kb = InlineKeyboardBuilder()
    for e in employments:
        ended_at = e.get("ended_at") or "-"
        text = f"{e['full_name']} ({e['master_public_id']}) — завершено {ended_at}"
        kb.button(
            text=text,
            callback_data=f"company_ended_employee_{e['id']}",
        )
    if next_offset is not None:
        kb.button(text="Показать ещё", callback_data=f"company_ended_list_{next_offset}")
    kb.adjust(1)
    return kb.as_markup()


def company_employee_actions_kb(employment_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✍ Оставить отзыв", callback_data=f"company_review_{employment_id}")
    kb.button(text="📄 История отзывов", callback_data=f"company_employment_reviews_{employment_id}")
    kb.button(text="✅ Завершить сотрудничество", callback_data=f"company_end_{employment_id}")
    kb.button(text="📝 Изменить паспорт исполнителя", callback_data=f"company_change_passport_{employment_id}")
    kb.adjust(1)
    return kb.as_markup()


def company_ended_employee_actions_kb(employment_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✍ Оставить/изменить отзыв", callback_data=f"company_review_{employment_id}")
    kb.button(text="📄 История отзывов", callback_data=f"company_employment_reviews_{employment_id}")
    kb.adjust(1)
    return kb.as_markup()


def master_leave_request_kb(employment_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Отменить запрос на увольнение",
        callback_data=f"master_cancel_leave_{employment_id}",
    )
    kb.adjust(1)
    return kb.as_markup()


def master_reviews_kb(reviews: List[dict]):
    kb = InlineKeyboardBuilder()
    for r in reviews:
        text = f"{r['company_name']} ({r['company_public_id']})"
        kb.button(
            text=text,
            callback_data=f"master_review_{r['id']}",
        )
    kb.adjust(1)
    return kb.as_markup()


def master_review_actions_kb(review_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✉ Подать жалобу на отзыв", callback_data=f"master_appeal_{review_id}")
    kb.adjust(1)
    return kb.as_markup()


def master_open_review_kb(review_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="Открыть отзыв", callback_data=f"master_review_{review_id}")
    kb.button(text="✉ Подать жалобу", callback_data=f"master_appeal_{review_id}")
    kb.adjust(1)
    return kb.as_markup()


def company_appeals_kb(appeals: List[dict]):
    kb = InlineKeyboardBuilder()
    for a in appeals:
        text = f"Жалоба #{a['id']} по {a['master_full_name']} ({a['master_public_id']})"
        kb.button(
            text=text,
            callback_data=f"company_appeal_{a['id']}",
        )
    kb.adjust(1)
    return kb.as_markup()


def company_appeal_actions_kb(appeal_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(
        text="📎 Отправить комментарий и материалы",
        callback_data=f"company_appeal_respond_{appeal_id}",
    )
    kb.adjust(1)
    return kb.as_markup()


def master_appeal_skip_proof_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Пропустить (без доказательств)", callback_data="master_appeal_skip_proof")
    kb.adjust(1)
    return kb.as_markup()


def master_appeal_proof_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Готово", callback_data="master_appeal_finish_proof")
    kb.button(text="Пропустить (без доказательств)", callback_data="master_appeal_skip_proof")
    kb.adjust(1)
    return kb.as_markup()


def company_leave_request_actions_kb(employment_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Подтвердить увольнение",
        callback_data=f"company_leave_request_accept_{employment_id}",
    )
    kb.button(
        text="↩️ Отменить запрос",
        callback_data=f"company_leave_request_decline_{employment_id}",
    )
    kb.adjust(1)
    return kb.as_markup()


def admin_main_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Список компаний", callback_data="admin_companies")
    kb.button(text="Список мастеров", callback_data="admin_masters")
    kb.button(text="Жалобы на отзывы", callback_data="admin_appeals")
    kb.adjust(1)
    return kb.as_markup()


def admin_company_list_kb(companies: List[dict]):
    kb = InlineKeyboardBuilder()
    for c in companies:
        label = c["name"] or "Без названия"
        if c.get("blocked"):
            label += " (🚫 блок)"
        kb.button(
            text=label,
            callback_data=f"admin_company_{c['id']}",
        )
    kb.adjust(1)
    return kb.as_markup()


def admin_company_detail_kb(company_id: int, blocked: bool):
    kb = InlineKeyboardBuilder()
    if blocked:
        kb.button(text="✅ Разблокировать", callback_data=f"admin_unblock_company_{company_id}")
    else:
        kb.button(text="🚫 Заблокировать", callback_data=f"admin_block_company_{company_id}")
    kb.button(text="📅 Выдать подписку", callback_data=f"admin_give_sub_{company_id}")
    kb.adjust(1)
    return kb.as_markup()


def admin_masters_list_kb(masters: List[dict]):
    kb = InlineKeyboardBuilder()
    for m in masters:
        label = m["full_name"] or "Без имени"
        if m.get("blocked"):
            label += " (🚫 блок)"
        kb.button(
            text=label,
            callback_data=f"admin_master_{m['id']}",
        )
    kb.adjust(1)
    return kb.as_markup()


def admin_master_detail_kb(master_id: int, blocked: bool):
    kb = InlineKeyboardBuilder()
    if blocked:
        kb.button(text="✅ Разблокировать", callback_data=f"admin_unblock_master_{master_id}")
    else:
        kb.button(text="🚫 Заблокировать", callback_data=f"admin_block_master_{master_id}")
    kb.adjust(1)
    return kb.as_markup()


def admin_appeals_list_kb(appeals: List[dict]):
    kb = InlineKeyboardBuilder()
    for a in appeals:
        label = f"#{a['id']} {a['master_full_name']} / {a['company_name'] or 'не указано'}"
        kb.button(
            text=label,
            callback_data=f"admin_appeal_{a['id']}",
        )
    kb.adjust(1)
    return kb.as_markup()


def admin_appeal_actions_kb(appeal_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Оставить отзыв, жалобу отклонить",
        callback_data=f"admin_appeal_keep_{appeal_id}",
    )
    kb.button(
        text="🗑 Удалить отзыв, жалобу удовлетворить",
        callback_data=f"admin_appeal_delete_{appeal_id}",
    )
    kb.button(
        text="✉ Написать комментарий мастеру",
        callback_data=f"admin_appeal_comment_{appeal_id}",
    )
    kb.adjust(1)
    return kb.as_markup()


def company_subscription_plans_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="1 месяц", callback_data="company_sub_plan_1")
    kb.button(text="3 месяца", callback_data="company_sub_plan_3")
    kb.button(text="6 месяцев", callback_data="company_sub_plan_6")
    kb.button(text="12 месяцев", callback_data="company_sub_plan_12")
    kb.adjust(2)
    return kb.as_markup()


def admin_subscription_plans_kb(company_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="1 месяц", callback_data=f"admin_set_sub_{company_id}_1")
    kb.button(text="3 месяца", callback_data=f"admin_set_sub_{company_id}_3")
    kb.button(text="6 месяцев", callback_data=f"admin_set_sub_{company_id}_6")
    kb.button(text="12 месяцев", callback_data=f"admin_set_sub_{company_id}_12")
    kb.button(text="❌ Снять подписку", callback_data=f"admin_set_sub_{company_id}_0")
    kb.adjust(2)
    return kb.as_markup()


def appeal_button_kb(review_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="Обжаловать отзыв", callback_data=f"master_appeal_{review_id}")
    kb.adjust(1)
    return kb.as_markup()
