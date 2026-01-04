import asyncio
import logging
from contextlib import closing
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

try:
    import config
except RuntimeError as e:
    print("=" * 60)
    print("ОШИБКА КОНФИГУРАЦИИ!")
    print("=" * 60)
    print(str(e))
    print()
    print("Создайте файл .env в корне проекта со следующим содержимым:")
    print("  BOT_TOKEN=your_telegram_bot_token")
    print("  PASSPORT_SECRET=your_passport_secret")
    print("  ADMINS=your_telegram_id")
    print("  PAYMENT_CARD=0000 0000 0000 0000")
    print("  DB_PATH=bot.db")
    print("  LOG_LEVEL=INFO")
    print()
    print("Важно: PASSPORT_SECRET обязателен. Если раньше паспорта шифровались через BOT_TOKEN,")
    print("необходимо выполнить миграцию данных после установки PASSPORT_SECRET.")
    print()
    input("Нажмите Enter для выхода...")
    exit(1)

from states import get_state, pop_state, set_state, clear_expired_states
from utils import (
    format_company_profile,
    format_employment_reviews,
    format_master_admin_profile,
    format_master_profile,
    format_master_public_profile,
    format_review_detail,
    format_reviews_list_for_master,
    format_employments_list_for_master,
    validate_phone,
    validate_passport,
    validate_public_id,
    validate_full_name,
    validate_company_name,
)
from db import (
    auto_close_leave_requests,
    can_master_appeal_review,
    company_has_active_subscription,
    init_db,
    create_company,
    create_employment,
    create_master,
    create_review,
    create_review_appeal,
    delete_review,
    end_employment,
    get_active_appeal_for_review_and_master,
    get_company_by_id,
    get_company_by_public_id,
    get_company_by_user,
    get_company_employments,
    get_company_ended_employments,
    get_company_requests_count,
    get_current_employment,
    get_employment_by_id,
    get_master_by_id,
    get_master_by_public_id,
    get_master_by_user,
    get_or_create_user,
    get_pending_company_appeals,
    get_pending_employments_for_company,
    get_review_appeal_by_id,
    get_review_by_id,
    get_reviews_for_employment,
    get_reviews_for_master,
    get_user,
    has_any_current_employment,
    has_pending_or_active_employment,
    has_pending_request_for_company,
    set_company_blocked,
    set_company_subscription,
    set_employment_accepted,
    set_employment_leave_requested,
    set_employment_rejected,
    set_master_blocked,
    set_master_passport_locked,
    set_user_phone,
    set_user_role,
    update_master_profile,
    update_review_appeal_admin_decision,
    update_review_appeal_company_response,
    get_conn,
    cancel_employment_leave_request,
    get_pending_leave_requests_for_company,
    get_master_rating,
)
from keyboards import (
    admin_appeal_actions_kb,
    admin_appeals_list_kb,
    admin_company_detail_kb,
    admin_company_list_kb,
    admin_main_kb,
    admin_master_detail_kb,
    admin_masters_list_kb,
    appeal_button_kb,
    company_appeal_actions_kb,
    company_appeals_kb,
    company_employee_actions_kb,
    company_employees_kb,
    company_ended_employees_kb,
    company_ended_list_button_kb,
    company_ended_employee_actions_kb,
    company_menu_kb,
    company_request_actions_kb,
    company_requests_kb,
    company_subscription_plans_kb,
    company_leave_requests_kb,
    company_leave_request_actions_kb,
    master_menu_kb,
    master_review_actions_kb,
    master_reviews_kb,
    role_keyboard,
    viewer_menu_kb,
    master_leave_request_kb,
    master_open_review_kb,
    master_appeal_proof_kb,
)
# Настройка логирования
try:
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger(__name__)

    bot = Bot(config.BOT_TOKEN)
    dp = Dispatcher()
except Exception as e:
    print("=" * 60)
    print("ОШИБКА ПРИ ИНИЦИАЛИЗАЦИИ БОТА!")
    print("=" * 60)
    print(f"Ошибка: {e}")
    print()
    print("Проверьте:")
    print("  1. Файл .env создан и содержит BOT_TOKEN")
    print("  2. BOT_TOKEN корректен (получен от @BotFather)")
    print("  3. Все зависимости установлены: pip install -r requirements.txt")
    print()
    import traceback
    traceback.print_exc()
    input("Нажмите Enter для выхода...")
    exit(1)

# ==========================
# КОНСТАНТЫ КНОПКИ НАЗАД
# ==========================

BACK_TEXT = "⬅️ Назад"


def back_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BACK_TEXT)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def rating_choice_kb():
    keyboard = [
        [KeyboardButton(text=str(i)) for i in range(1, 6)],
        [KeyboardButton(text=BACK_TEXT)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def ensure_admin_access(target, *, alert: bool = True) -> bool:
    user_id = target.from_user.id
    if user_id in config.ADMIN_IDS:
        return True
    if isinstance(target, CallbackQuery):
        await target.answer("Нет доступа.", show_alert=alert)
    else:
        await target.answer("Нет доступа.")
    return False


def ensure_company_can_act(company: dict, require_subscription: bool = True) -> Optional[str]:
    if company.get("blocked"):
        return "Ваш профиль компании заблокирован администратором. Обратитесь в поддержку."
    if require_subscription and not company_has_active_subscription(company):
        return (
            "У компании нет активной подписки или она истекла.\n\n"
            "Оформите или продлите подписку через пункт «Подписка и оплата» в меню."
        )
    return None


async def submit_master_appeal(
    *,
    reply_message: Message,
    tg_id: int,
    review_id: int,
    reason: str,
    master: dict,
    review: dict,
    photo_message_ids: Optional[list[int]] = None,
    photo_chat_id: Optional[int] = None,
):
    appeal_id = create_review_appeal(
        review_id=review_id,
        master_id=master["id"],
        company_id=review["company_id"],
        reason=reason,
    )

    if photo_message_ids and photo_chat_id:
        with closing(get_conn()) as conn, conn:
            conn.execute(
                "UPDATE review_appeals SET master_files_message_id = ? WHERE id = ?",
                (photo_message_ids[0], appeal_id),
            )

    pop_state(tg_id)
    await reply_message.answer(
        "Ваша жалоба отправлена компании и администратору.\n"
        "Компания должна предоставить ответ и доказательства. "
        "Если она этого не сделает, отзыв может быть удалён.",
        reply_markup=ReplyKeyboardRemove(),
    )

    company = get_company_by_id(review["company_id"])
    if company:
        text = (
            f"Исполнитель {master['full_name']} ({master['public_id']}) "
            f"подал жалобу на отзыв #{review_id}.\n\n"
            f"Текст жалобы:\n{reason}\n\n"
            "Зайдите в раздел «Жалобы на отзывы» в меню компании, чтобы ответить."
        )
        try:
            await bot.send_message(
                company["tg_id"],
                text,
                reply_markup=company_appeal_actions_kb(appeal_id),
            )
            if photo_message_ids and photo_chat_id:
                for message_id in photo_message_ids:
                    try:
                        await bot.copy_message(
                            company["tg_id"],
                            from_chat_id=photo_chat_id,
                            message_id=message_id,
                        )
                    except Exception:
                        logger.exception(
                            "Не удалось переслать фото компании по жалобе %s",
                            appeal_id,
                        )
        except Exception:
            logger.exception("Не удалось уведомить компанию %s о жалобе", company["id"])

    for admin_id in config.ADMIN_IDS:
        try:
            admin_text = (
                f"Новая жалоба #{appeal_id} на отзыв:\n\n"
                f"Исполнитель: {master['full_name']} ({master['public_id']})\n"
                f"Компания: {company['name'] if company else 'не найдена'}\n\n"
                f"Текст отзыва:\n{review['text']}\n\n"
                f"Жалоба исполнителя:\n{reason}"
            )
            await bot.send_message(
                admin_id,
                admin_text,
                reply_markup=admin_appeal_actions_kb(appeal_id),
            )
            if photo_message_ids and photo_chat_id:
                for message_id in photo_message_ids:
                    try:
                        await bot.copy_message(
                            admin_id,
                            from_chat_id=photo_chat_id,
                            message_id=message_id,
                        )
                    except Exception:
                        logger.exception(
                            "Не удалось переслать фото админу %s по жалобе %s",
                            admin_id,
                            appeal_id,
                        )
        except Exception:
            logger.exception("Не удалось уведомить админа %s о жалобе %s", admin_id, appeal_id)


def auto_review_appeals_maintenance():
    """Отслеживание жалоб: напоминание через 3 дня и автоудаление через 5 дней."""
    now = datetime.utcnow()
    three_days_ago = now - timedelta(days=3)
    five_days_ago = now - timedelta(days=5)

    with closing(get_conn()) as conn, conn:
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
            WHERE ra.status = 'pending_company_response'
            """
        )
        appeals = [dict(row) for row in c.fetchall()]

    for appeal in appeals:
        try:
            created_at = datetime.fromisoformat(appeal["created_at"])
        except (TypeError, ValueError):
            continue

        reminder_sent_at = appeal.get("reminder_sent_at")
        if not reminder_sent_at and created_at <= three_days_ago:
            company = get_company_by_id(appeal.get("company_id"))
            if company:
                text = (
                    f"Напоминание по жалобе #{appeal['id']} на отзыв по исполнителю "
                    f"{appeal['master_full_name']} ({appeal['master_public_id']}):\n\n"
                    f"Текст отзыва:\n{appeal['review_text']}\n\n"
                    "Пожалуйста, ответьте на жалобу и при необходимости приложите доказательства."
                )
                try:
                    asyncio.create_task(bot.send_message(company["tg_id"], text))
                except Exception:
                    logger.exception(
                        "Не удалось отправить напоминание компании по жалобе %s",
                        appeal["id"],
                    )

            with closing(get_conn()) as conn, conn:
                conn.execute(
                    """
                    UPDATE review_appeals
                    SET reminder_sent_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        datetime.utcnow().isoformat(timespec="seconds"),
                        datetime.utcnow().isoformat(timespec="seconds"),
                        appeal["id"],
                    ),
                )

        if created_at <= five_days_ago:
            review_id = appeal["review_id"]
            delete_review(review_id)
            with closing(get_conn()) as conn, conn:
                conn.execute(
                    """
                    UPDATE review_appeals
                    SET status = 'auto_removed_review', updated_at = ?, final_decision_at = ?
                    WHERE id = ?
                    """,
                    (
                        datetime.utcnow().isoformat(timespec="seconds"),
                        datetime.utcnow().isoformat(timespec="seconds"),
                        appeal["id"],
                    ),
                )

            master = get_master_by_id(appeal["master_id"])
            if master:
                text = (
                    "Ваша жалоба на отзыв была рассмотрена автоматически, "
                    "так как компания не предоставила ответ в течение 5 дней.\n\n"
                    "Отзыв был удалён."
                )
                try:
                    asyncio.create_task(bot.send_message(master["tg_id"], text))
                except Exception:
                    logger.exception(
                        "Не удалось уведомить мастера %s об автоудалении отзыва",
                        master["id"],
                    )

# ==========================
# СЕРВИСНЫЕ ХЕЛПЕРЫ
# ==========================


# ==========================
# КОМАНДЫ
# ==========================


@dp.message(Command("start"))
async def cmd_start(message: Message):
    get_or_create_user(message)
    text = (
        "👋 Добро пожаловать в «Белый список».\n\n"
        "Это сервис, который помогает компаниям нанимать безопасно и защищаться от мошенников.\n\n"
        "Как это работает:\n"
        "• Исполнитель регистрируется и прикрепляется к компании.\n"
        "• Компания подтверждает, что человек действительно у неё работал и сверяет паспорт.\n"
        "• После работы компания может оставить честный отзыв.\n"
        "• Клиент может проверить исполнителя по его ID.\n\n"
        "Для начала выберите вашу роль:"
    )
    await message.answer(text, reply_markup=role_keyboard())


@dp.message(Command("role"))
async def cmd_role(message: Message):
    await message.answer("Выберите вашу роль:", reply_markup=role_keyboard())


@dp.message(Command("info"))
async def cmd_info(message: Message):
    user = get_user(message.from_user.id) or get_or_create_user(message)
    role = user["role"]

    if role == "master":
        text = (
            "Информация для исполнителя:\n\n"
            "• Вы регистрируетесь, указываете свои данные и паспорт.\n"
            "• Получаете уникальный ID исполнителя.\n"
            "• Можете отправлять запросы компаниям, чтобы они добавили вас в команду и подтвердили паспорт.\n"
            "• Компании, к которым вы прикреплены, могут оставлять по вам отзывы.\n"
            "• Клиенты могут проверить вас по этому ID и увидеть отзывы.\n\n"
            "Это помогает формировать вашу репутацию и повышать доверие к вам."
        )
    elif role == "company":
        text = (
            "Информация для компании:\n\n"
            "• Вы регистрируете профиль компании.\n"
            "• Исполнители отправляют вам запросы на прикрепление.\n"
            "• Вы сверяете паспорт исполнителя и подтверждаете его в сервисе.\n"
            "• По завершении сотрудничества оставляете по нему честный отзыв.\n"
            "• Перед наймом нового исполнителя вы можете проверить его историю.\n\n"
            "Сервис помогает отсеивать мошенников и неблагонадёжных исполнителей."
        )
    else:
        text = (
            "Информация для обычных пользователей:\n\n"
            "• Вы можете проверить исполнителя по его ID.\n"
            "• Увидеть историю его сотрудничества с компаниями и отзывы.\n"
            "• Это помогает вам принимать более безопасные решения при выборе исполнителя."
        )

    await message.answer(text)


# ==========================
# ОБРАБОТКА ВЫБОРА РОЛИ
# ==========================


@dp.callback_query(F.data == "role_master")
async def cb_role_master(callback: CallbackQuery):
    tg_id = callback.from_user.id
    set_user_role(tg_id, "master")
    user = get_user(tg_id) or get_or_create_user(callback.message)
    _ = user["first_name"] or ""
    master = get_master_by_user(tg_id)
    if master:
        await callback.message.answer(
            "Ваш личный кабинет исполнителя:", reply_markup=master_menu_kb()
        )
    else:
        await callback.message.answer(
            "Вы выбрали роль исполнителя.\nДавайте зарегистрируем вас.\n\n"
            "Введите ваше ФИО:",
            reply_markup=back_kb(),
        )
        set_state(tg_id, "master_register_full_name")


@dp.callback_query(F.data == "role_company")
async def cb_role_company(callback: CallbackQuery):
    tg_id = callback.from_user.id
    set_user_role(tg_id, "company")
    company = get_company_by_user(tg_id)
    if company:
        await callback.message.answer(
            "Личный кабинет компании:",
            reply_markup=company_menu_kb(company["id"]),
        )
    else:
        await callback.message.answer(
            "Вы выбрали роль компании.\nДавайте зарегистрируем вашу компанию.\n\n"
            "Введите название компании:",
            reply_markup=back_kb(),
        )
        set_state(tg_id, "company_enter_name")


@dp.callback_query(F.data == "role_viewer")
async def cb_role_viewer(callback: CallbackQuery):
    tg_id = callback.from_user.id
    set_user_role(tg_id, "viewer")
    user = get_user(tg_id) or get_or_create_user(callback.message)
    if not user.get("phone"):
        await callback.message.answer(
            "Вы выбрали роль обычного пользователя.\n\n"
            "Чтобы мы могли при необходимости связаться с вами,\n"
            "пожалуйста, отправьте ваш номер телефона:",
            reply_markup=back_kb(),
        )
        set_state(tg_id, "viewer_enter_phone")
    else:
        await callback.message.answer(
            "Вы выбрали роль обычного пользователя.",
        )
        await callback.message.answer(
            "Меню для пользователей:", reply_markup=viewer_menu_kb()
        )


# ==========================
# МАСТЕР — КАБИНЕТ
# ==========================


@dp.callback_query(F.data == "master_profile")
async def cb_master_profile(callback: CallbackQuery):
    tg_id = callback.from_user.id
    master = get_master_by_user(tg_id)
    if not master:
        await callback.message.answer(
            "Вы ещё не зарегистрированы как исполнитель. Используйте /role и выберите «Я исполнитель»."
        )
        return
    rating = get_master_rating(master["id"])
    await callback.message.answer(format_master_profile(master, rating))
    await callback.message.answer("Меню исполнителя:", reply_markup=master_menu_kb())


@dp.callback_query(F.data == "master_edit_profile")
async def cb_master_edit_profile(callback: CallbackQuery):
    tg_id = callback.from_user.id
    master = get_master_by_user(tg_id)
    if not master:
        await callback.message.answer(
            "Вы ещё не зарегистрированы как исполнитель. Используйте /role и выберите «Я исполнитель»."
        )
        return

    await callback.message.answer(
        "Введите новое ФИО (или отправьте '-' чтобы оставить без изменений):",
        reply_markup=back_kb(),
    )
    set_state(
        tg_id,
        "master_edit_full_name",
        master_id=master["id"],
        full_name=master["full_name"],
        phone=master.get("phone"),
        passport=master.get("passport"),
        passport_locked=bool(master.get("passport_locked")),
    )


@dp.callback_query(F.data == "master_reviews")
async def cb_master_reviews(callback: CallbackQuery):
    tg_id = callback.from_user.id
    master = get_master_by_user(tg_id)
    if not master:
        await callback.message.answer(
            "Вы ещё не зарегистрированы как исполнитель."
        )
        return

    reviews = get_reviews_for_master(master["id"])
    await callback.message.answer(format_reviews_list_for_master(reviews))
    if reviews:
        await callback.message.answer(
            "Вы можете открыть подробный отзыв и подать жалобу при необходимости:",
            reply_markup=master_reviews_kb(reviews),
        )


@dp.callback_query(F.data.startswith("master_review_"))
async def cb_master_review_detail(callback: CallbackQuery):
    tg_id = callback.from_user.id
    master = get_master_by_user(tg_id)
    if not master:
        await callback.message.answer("Вы ещё не зарегистрированы как исполнитель.")
        return

    try:
        review_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректный формат данных.")
        return

    review = get_review_by_id(review_id)
    if not review or review["master_id"] != master["id"]:
        await callback.message.answer("Отзыв не найден или не относится к вам.")
        return

    await callback.message.answer(
        format_review_detail(review),
        reply_markup=master_review_actions_kb(review_id),
    )


@dp.callback_query(F.data == "master_appeal_skip_proof")
async def cb_master_appeal_skip_proof(callback: CallbackQuery):
    await callback.answer()
    tg_id = callback.from_user.id
    state = get_state(tg_id)
    
    if not state or state.action != "master_appeal_proof":
        await callback.message.answer("Ошибка: состояние не найдено. Попробуйте начать заново.")
        return
    
    review_id = state.data["review_id"]
    reason = state.data["reason"]

    master = get_master_by_user(tg_id)
    review = get_review_by_id(review_id)

    if not master or not review:
        await callback.message.answer("Не удалось найти данные по отзыву. Попробуйте позже.")
        pop_state(tg_id)
        return

    await submit_master_appeal(
        reply_message=callback.message,
        tg_id=tg_id,
        review_id=review_id,
        reason=reason,
        master=master,
        review=review,
    )


@dp.callback_query(F.data == "master_appeal_finish_proof")
async def cb_master_appeal_finish_proof(callback: CallbackQuery):
    await callback.answer()
    tg_id = callback.from_user.id
    state = get_state(tg_id)

    if not state or state.action != "master_appeal_proof":
        await callback.message.answer("Ошибка: состояние не найдено. Попробуйте начать заново.")
        return

    review_id = state.data["review_id"]
    reason = state.data["reason"]
    photo_message_ids = state.data.get("photo_message_ids") or []
    photo_chat_id = state.data.get("photo_chat_id")

    if not photo_message_ids:
        await callback.message.answer(
            "Вы ещё не отправили фото. Отправьте фото или нажмите «Пропустить».",
            reply_markup=master_appeal_proof_kb(),
        )
        return

    master = get_master_by_user(tg_id)
    review = get_review_by_id(review_id)

    if not master or not review:
        await callback.message.answer("Не удалось найти данные по отзыву. Попробуйте позже.")
        pop_state(tg_id)
        return

    await submit_master_appeal(
        reply_message=callback.message,
        tg_id=tg_id,
        review_id=review_id,
        reason=reason,
        master=master,
        review=review,
        photo_message_ids=photo_message_ids,
        photo_chat_id=photo_chat_id,
    )


@dp.callback_query(F.data.startswith("master_appeal_"))
async def cb_master_appeal_review(callback: CallbackQuery):
    
    tg_id = callback.from_user.id
    master = get_master_by_user(tg_id)
    if not master:
        await callback.message.answer("Вы ещё не зарегистрированы как исполнитель.")
        return

    try:
        review_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректный формат данных.")
        return

    review = get_review_by_id(review_id)
    if not review or review["master_id"] != master["id"]:
        await callback.message.answer("Отзыв не найден или не относится к вам.")
        return

    if not can_master_appeal_review(review, master["id"]):
        await callback.message.answer(
            "Сейчас нельзя подать жалобу по этому отзыву.\n"
            "Возможно, прошло более 14 дней, уже есть активная жалоба или превышен лимит попыток."
        )
        return

    await callback.message.answer(
        "Опишите, пожалуйста, с чем вы не согласны в отзыве и почему.\n"
        "Это сообщение будет направлено компании и администратору.",
        reply_markup=back_kb(),
    )
    set_state(
        tg_id,
        "master_appeal_reason",
        review_id=review_id,
    )


@dp.callback_query(F.data == "master_link_company")
async def cb_master_link_company(callback: CallbackQuery):
    tg_id = callback.from_user.id
    master = get_master_by_user(tg_id)
    if not master:
        await callback.message.answer(
            "Вы ещё не зарегистрированы как исполнитель."
        )
        return
    if has_any_current_employment(master["id"]):
        await callback.message.answer(
            "Сначала завершите текущее сотрудничество.\n"
            "Вы уже числитесь в одной из компаний и не можете прикрепиться к другой."
        )
        return

    await callback.message.answer(
        "Введите публичный ID компании (например, C-123456), к которой хотите прикрепиться:",
        reply_markup=back_kb(),
    )
    set_state(tg_id, "master_link_company_enter_id")


@dp.callback_query(F.data == "master_request_leave")
async def cb_master_request_leave(callback: CallbackQuery):
    tg_id = callback.from_user.id
    master = get_master_by_user(tg_id)
    if not master:
        await callback.message.answer("Вы ещё не зарегистрированы как исполнитель.")
        return

    employment = get_current_employment(master["id"])
    if not employment:
        await callback.message.answer(
            "Сейчас вы не числитесь ни в одной компании."
        )
        return

    if employment["status"] == "leave_requested":
        await callback.message.answer(
            "Вы уже отправили запрос на увольнение. Ожидайте реакции компании.",
            reply_markup=master_leave_request_kb(employment["id"]),
        )
        return

    set_employment_leave_requested(employment["id"])
    await callback.message.answer(
        "Запрос на увольнение отправлен компании.\n"
        "Если компания не отреагирует в течение 2 дней, система автоматически завершит сотрудничество.",
        reply_markup=master_leave_request_kb(employment["id"]),
    )

    company = get_company_by_id(employment["company_id"])
    if company:
        text = (
            f"Исполнитель {master['full_name']} ({master['public_id']}) "
            f"запросил увольнение.\n"
            "Зайдите в раздел «Запросы» в меню компании, чтобы подтвердить или отменить запрос."
        )
        try:
            await bot.send_message(
                company["tg_id"],
                text,
                reply_markup=company_leave_request_actions_kb(employment["id"]),
            )
        except Exception:
            logger.exception("Не удалось уведомить компанию %s о запросе на увольнение", company["id"])


@dp.callback_query(F.data.startswith("master_cancel_leave_"))
async def cb_master_cancel_leave(callback: CallbackQuery):
    tg_id = callback.from_user.id
    master = get_master_by_user(tg_id)
    if not master:
        await callback.message.answer("Вы ещё не зарегистрированы как исполнитель.")
        return

    try:
        employment_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    employment = get_employment_by_id(employment_id)
    if not employment or employment["master_id"] != master["id"]:
        await callback.message.answer("Сотрудничество не найдено.")
        return

    if employment["status"] != "leave_requested":
        await callback.message.answer("Запрос на увольнение уже обработан.")
        return

    if not cancel_employment_leave_request(employment_id):
        await callback.message.answer("Не удалось отменить запрос. Попробуйте позже.")
        return

    await callback.message.answer(
        "Запрос на увольнение отменён. Вы продолжаете числиться в компании.",
        reply_markup=master_menu_kb(),
    )

    company = get_company_by_id(employment["company_id"])
    if company:
        try:
            await bot.send_message(
                company["tg_id"],
                f"Исполнитель {employment['full_name']} ({employment['master_public_id']}) "
                "отменил запрос на увольнение.",
            )
        except Exception:
            logger.exception("Не удалось уведомить компанию %s об отмене увольнения", company["id"])


@dp.callback_query(F.data == "master_support")
async def cb_master_support(callback: CallbackQuery):
    await callback.message.answer(
        "Поддержка исполнителей:\n\n"
        "Если у вас есть вопросы или спорные ситуации, вы можете написать администратору.\n"
        "Пока для связи используется этот же чат — опишите проблему, и администратор увидит ваше сообщение."
    )


# ==========================
# КОМПАНИЯ — КАБИНЕТ
# ==========================


@dp.callback_query(F.data == "company_profile")
async def cb_company_profile(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer(
            "Вы ещё не зарегистрированы как компания. Используйте /role и выберите «Я компания»."
        )
        return
    await callback.message.answer(format_company_profile(company))
    await callback.message.answer("Меню компании:", reply_markup=company_menu_kb(company["id"]))


@dp.callback_query(F.data == "company_edit_profile")
async def cb_company_edit_profile(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    await callback.message.answer(
        "Введите новое название компании (или '-' чтобы оставить без изменений):",
        reply_markup=back_kb(),
    )
    set_state(
        tg_id,
        "company_edit_name",
        company_id=company["id"],
        name=company["name"],
        city=company.get("city"),
        phone=company.get("responsible_phone"),
    )


@dp.callback_query(F.data == "company_employees")
async def cb_company_employees(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    msg = ensure_company_can_act(company, require_subscription=False)
    if msg:
        await callback.message.answer(msg)
        return

    employments = get_company_employments(company["id"])
    if not employments:
        await callback.message.answer("У вас пока нет прикреплённых исполнителей.")
    else:
        await callback.message.answer(
            "Ваши исполнители:", reply_markup=company_employees_kb(employments)
        )

    ended_exists = bool(get_company_ended_employments(company["id"], limit=1))
    if ended_exists:
        await callback.message.answer(
            "Ниже вы можете посмотреть уволенных сотрудников:",
            reply_markup=company_ended_list_button_kb(),
        )


@dp.callback_query(F.data.startswith("company_employee_"))
async def cb_company_employee_detail(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    msg = ensure_company_can_act(company, require_subscription=False)
    if msg:
        await callback.message.answer(msg)
        return

    try:
        employment_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректный формат данных.")
        return

    employment = get_employment_by_id(employment_id)
    if not employment or employment["company_id"] != company["id"]:
        await callback.message.answer("Сотрудник не найден.")
        return

    lines = [
        f"Исполнитель: {employment['full_name']} ({employment['master_public_id']})",
        f"Должность: {employment['position'] or 'не указана'}",
        f"Статус: {employment['status']}",
    ]
    if employment.get("started_at"):
        lines.append(f"Начал работать: {employment['started_at']}")
    if employment.get("ended_at"):
        lines.append(f"Закончил работать: {employment['ended_at']}")

    if employment["status"] == "ended":
        keyboard = company_ended_employee_actions_kb(employment_id)
    else:
        keyboard = company_employee_actions_kb(employment_id)

    await callback.message.answer("\n".join(lines), reply_markup=keyboard)


@dp.callback_query(F.data.startswith("company_ended_employee_"))
async def cb_company_ended_employee_detail(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    msg = ensure_company_can_act(company, require_subscription=False)
    if msg:
        await callback.message.answer(msg)
        return

    try:
        employment_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректный формат данных.")
        return

    employment = get_employment_by_id(employment_id)
    if not employment or employment["company_id"] != company["id"] or employment["status"] != "ended":
        await callback.message.answer("Уволенный сотрудник не найден.")
        return

    lines = [
        f"Исполнитель: {employment['full_name']} ({employment['master_public_id']})",
        f"Должность: {employment['position'] or 'не указана'}",
        f"Сотрудничество завершено: {employment.get('ended_at') or '-'}",
    ]
    await callback.message.answer(
        "\n".join(lines),
        reply_markup=company_ended_employee_actions_kb(employment_id),
    )


@dp.callback_query(F.data.startswith("company_end_"))
async def cb_company_end_employment(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    msg = ensure_company_can_act(company, require_subscription=False)
    if msg:
        await callback.message.answer(msg)
        return

    try:
        employment_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    employment = get_employment_by_id(employment_id)
    if not employment or employment["company_id"] != company["id"] or employment["status"] == "ended":
        await callback.message.answer("Сотрудничество не найдено или уже завершено.")
        return

    end_employment(employment_id)
    await callback.message.answer("Сотрудничество завершено.")

    master = get_master_by_id(employment["master_id"])
    if master:
        try:
            await bot.send_message(
                master["tg_id"],
                f"Компания {company['name']} завершила сотрудничество с вами.",
            )
        except Exception:
            logger.exception("Не удалось уведомить мастера %s о завершении сотрудничества", master["id"])


@dp.callback_query(F.data.startswith("company_employment_reviews_"))
async def cb_company_employment_reviews(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    msg = ensure_company_can_act(company, require_subscription=False)
    if msg:
        await callback.message.answer(msg)
        return

    try:
        employment_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    employment = get_employment_by_id(employment_id)
    if not employment or employment["company_id"] != company["id"]:
        await callback.message.answer("Сотрудничество не найдено.")
        return

    reviews = get_reviews_for_employment(employment_id)
    await callback.message.answer(format_employment_reviews(employment, reviews))


@dp.callback_query(F.data.startswith("company_review_"))
async def cb_company_review_employment(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    msg = ensure_company_can_act(company, require_subscription=False)
    if msg:
        await callback.message.answer(msg)
        return

    try:
        employment_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    employment = get_employment_by_id(employment_id)
    if not employment or employment["company_id"] != company["id"]:
        await callback.message.answer("Сотрудничество не найдено.")
        return

    await callback.message.answer(
        "Выберите оценку исполнителю (1 — плохо, 5 — отлично):",
        reply_markup=rating_choice_kb(),
    )
    set_state(
        tg_id,
        "company_review_rating",
        employment_id=employment_id,
        master_id=employment["master_id"],
        company_id=company["id"],
    )


@dp.callback_query(F.data == "company_view_requests")
async def cb_company_view_requests(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    msg = ensure_company_can_act(company, require_subscription=False)
    if msg:
        await callback.message.answer(msg)
        return

    hire_requests = get_pending_employments_for_company(company["id"])
    leave_requests = get_pending_leave_requests_for_company(company["id"])

    if not hire_requests and not leave_requests:
        await callback.message.answer("У вас нет новых запросов от исполнителей.")
        return

    if hire_requests:
        await callback.message.answer(
            "Запросы на прикрепление исполнителей:",
            reply_markup=company_requests_kb(hire_requests),
        )

    if leave_requests:
        await callback.message.answer(
            "Запросы на увольнение исполнителей:",
            reply_markup=company_leave_requests_kb(leave_requests),
        )


@dp.callback_query(F.data.regexp(r"^company_request_\d+$"))
async def cb_company_request_detail(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    msg = ensure_company_can_act(company, require_subscription=False)
    if msg:
        await callback.message.answer(msg)
        return

    try:
        employment_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    employment = get_employment_by_id(employment_id)
    if not employment or employment["company_id"] != company["id"]:
        await callback.message.answer("Запрос не найден.")
        return

    passport = employment.get("passport") or "не указан"
    lines = [
        f"Исполнитель: {employment['full_name']} ({employment['master_public_id']})",
        f"Должность: {employment['position'] or 'не указана'}",
        "",
        f"Паспорт, указанный исполнителем: {passport}",
        "",
        "Сверьте эти данные с паспортом исполнителя и выберите действие ниже:",
    ]
    await callback.message.answer(
        "\n".join(lines),
        reply_markup=company_request_actions_kb(employment_id),
    )


@dp.callback_query(F.data.regexp(r"^company_leave_request_\d+$"))
async def cb_company_leave_request_detail(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    try:
        employment_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    employment = get_employment_by_id(employment_id)
    if (
        not employment
        or employment["company_id"] != company["id"]
        or employment["status"] != "leave_requested"
    ):
        await callback.message.answer("Запрос не найден или уже обработан.")
        return

    requested_at = employment.get("leave_requested_at") or "не указано"
    text = (
        f"Исполнитель: {employment['full_name']} ({employment['master_public_id']})\n"
        f"Должность: {employment['position'] or 'не указана'}\n"
        f"Запрос на увольнение отправлен: {requested_at}\n\n"
        "Выберите действие:"
    )
    await callback.message.answer(
        text,
        reply_markup=company_leave_request_actions_kb(employment_id),
    )


@dp.callback_query(F.data.startswith("company_leave_request_accept_"))
async def cb_company_leave_request_accept(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    try:
        employment_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    employment = get_employment_by_id(employment_id)
    if (
        not employment
        or employment["company_id"] != company["id"]
        or employment["status"] != "leave_requested"
    ):
        await callback.message.answer("Запрос не найден или уже обработан.")
        return

    end_employment(employment_id)
    await callback.message.answer(
        "Запрос на увольнение подтверждён. Сотрудничество завершено.\n\n"
        "Хотите оставить отзыв об этом исполнителе?"
    )
    set_state(
        tg_id,
        "company_review_prompt_after_leave",
        employment_id=employment_id,
        master_id=employment["master_id"],
        company_id=company["id"],
    )

    master = get_master_by_id(employment["master_id"])
    if master:
        try:
            await bot.send_message(
                master["tg_id"],
                f"Компания {company['name']} завершила сотрудничество по вашему запросу на увольнение.",
            )
        except Exception:
            logger.exception("Не удалось уведомить мастера %s о подтверждении увольнения", master["id"])


@dp.callback_query(F.data.startswith("company_leave_request_decline_"))
async def cb_company_leave_request_decline(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    try:
        employment_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    employment = get_employment_by_id(employment_id)
    if (
        not employment
        or employment["company_id"] != company["id"]
        or employment["status"] != "leave_requested"
    ):
        await callback.message.answer("Запрос не найден или уже обработан.")
        return

    if not cancel_employment_leave_request(employment_id):
        await callback.message.answer("Не удалось отменить запрос. Попробуйте позже.")
        return

    await callback.message.answer("Запрос на увольнение отменён. Сотрудник остаётся в компании.")

    master = get_master_by_id(employment["master_id"])
    if master:
        try:
            await bot.send_message(
                master["tg_id"],
                f"Компания {company['name']} отклонила ваш запрос на увольнение.",
            )
        except Exception:
            logger.exception("Не удалось уведомить мастера %s об отклонении увольнения", master["id"])


@dp.callback_query(F.data.startswith("company_request_accept_"))
async def cb_company_request_accept(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    msg = ensure_company_can_act(company, require_subscription=False)
    if msg:
        await callback.message.answer(msg)
        return

    try:
        employment_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    employment = get_employment_by_id(employment_id)
    if not employment or employment["company_id"] != company["id"]:
        await callback.message.answer("Запрос не найден.")
        return

    set_employment_accepted(employment_id)

    master_id = employment["master_id"]
    master = get_master_by_id(master_id)
    if master:
        if not master.get("passport_locked"):
            set_master_passport_locked(master_id, True)
        try:
            await bot.send_message(
                master["tg_id"],
                f"Компания {company['name']} приняла ваш запрос на сотрудничество.\n"
                "Вы теперь числитесь в их команде.",
            )
        except Exception:
            logger.exception("Не удалось отправить уведомление мастеру о подтверждении запроса")

    await callback.message.answer("Запрос подтверждён, паспорт совпадает, исполнитель добавлен в вашу компанию.")


@dp.callback_query(F.data.startswith("company_request_reject_"))
async def cb_company_request_reject(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    msg = ensure_company_can_act(company, require_subscription=False)
    if msg:
        await callback.message.answer(msg)
        return

    try:
        employment_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    employment = get_employment_by_id(employment_id)
    if not employment or employment["company_id"] != company["id"]:
        await callback.message.answer("Запрос не найден.")
        return

    await callback.message.answer(
        "Напишите причину отказа (это сообщение увидит исполнитель):",
        reply_markup=back_kb(),
    )
    set_state(
        tg_id,
        "company_request_reject_reason",
        employment_id=employment_id,
        company_id=company["id"],
    )


@dp.callback_query(F.data.startswith("company_ended_list_"))
async def cb_company_ended_list(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    msg = ensure_company_can_act(company, require_subscription=False)
    if msg:
        await callback.message.answer(msg)
        return

    try:
        offset = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    per_page = 10
    slice_size = per_page + 1
    ended = get_company_ended_employments(company["id"], limit=slice_size, offset=offset)
    if not ended:
        if offset == 0:
            await callback.message.answer("У вас пока нет уволенных сотрудников.")
        else:
            await callback.message.answer("Больше уволенных сотрудников нет.")
        return

    has_more = len(ended) > per_page
    shown = ended[:per_page]
    next_offset = offset + per_page if has_more else None

    await callback.message.answer(
        f"Уволенные сотрудники (с {offset + 1}-го):",
        reply_markup=company_ended_employees_kb(shown, next_offset),
    )


@dp.callback_query(F.data == "company_check_master")
async def cb_company_check_master(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    await callback.message.answer(
        "Введите ID исполнителя (например, M-123456), которого хотите проверить:",
        reply_markup=back_kb(),
    )
    set_state(
        tg_id,
        "company_check_master_enter_id",
    )


@dp.callback_query(F.data == "company_change_passport")
async def cb_company_change_passport_root(callback: CallbackQuery):
    # На всякий случай, если где-то будет вызываться без employment_id
    await callback.message.answer("Выберите исполнителя в разделе «Мои сотрудники», чтобы изменить паспорт.")


@dp.callback_query(F.data.startswith("company_change_passport_"))
async def cb_company_change_passport(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    msg = ensure_company_can_act(company)
    if msg:
        await callback.message.answer(msg)
        return

    try:
        employment_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    employment = get_employment_by_id(employment_id)
    if not employment or employment["company_id"] != company["id"]:
        await callback.message.answer("Сотрудничество не найдено.")
        return

    master = get_master_by_id(employment["master_id"])
    if not master:
        await callback.message.answer("Исполнитель не найден.")
        return

    current_passport = master.get("passport") or "не указан"
    await callback.message.answer(
        f"Текущие паспортные данные исполнителя в системе: {current_passport}\n\n"
        "Введите новые паспортные данные (серия и номер), которые вы видите в документе:",
        reply_markup=back_kb(),
    )
    set_state(
        tg_id,
        "company_change_passport_enter",
        master_id=master["id"],
    )


@dp.callback_query(F.data == "company_view_appeals")
async def cb_company_view_appeals(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    msg = ensure_company_can_act(company)
    if msg:
        await callback.message.answer(msg)
        return

    appeals = get_pending_company_appeals(company["id"])
    if not appeals:
        await callback.message.answer("По вашим отзывам нет активных жалоб от исполнителей.")
        return

    await callback.message.answer(
        "Жалобы исполнителей на отзывы:",
        reply_markup=company_appeals_kb(appeals),
    )


@dp.callback_query(F.data.startswith("company_appeal_"))
async def cb_company_appeal_detail(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    msg = ensure_company_can_act(company)
    if msg:
        await callback.message.answer(msg)
        return

    data = callback.data.split("_")
    if len(data) == 3 and data[1] == "appeal":
        try:
            appeal_id = int(data[2])
        except ValueError:
            await callback.message.answer("Некорректные данные.")
            return
        appeal = get_review_appeal_by_id(appeal_id)
        if not appeal or appeal["company_id"] != company["id"]:
            await callback.message.answer("Жалоба не найдена.")
            return

        text = (
            f"Жалоба #{appeal['id']} по отзыву:\n\n"
            f"Исполнитель: {appeal['master_full_name']} ({appeal['master_public_id']})\n"
            f"Компания: {appeal.get('company_name') or 'не указана'} "
            f"({appeal.get('company_public_id') or '-'})\n\n"
            f"Текст отзыва:\n{appeal['review_text']}\n\n"
            f"Жалоба исполнителя:\n{appeal.get('master_comment') or 'не указано'}\n\n"
            "Вы можете отправить комментарий и при необходимости приложить файлы (фото/сканы документов)."
        )

        await callback.message.answer(
            text,
            reply_markup=company_appeal_actions_kb(appeal_id),
        )
    elif len(data) == 4 and data[1] == "appeal" and data[2] == "respond":
        try:
            appeal_id = int(data[3])
        except ValueError:
            await callback.message.answer("Некорректные данные.")
            return

        appeal = get_review_appeal_by_id(appeal_id)
        if not appeal or appeal["company_id"] != company["id"]:
            await callback.message.answer("Жалоба не найдена.")
            return

        await callback.message.answer(
            "Отправьте одно сообщение, в котором:\n"
            "• Напишете ваш комментарий по ситуации;\n"
            "• Прикрепите файлы с доказательствами (если есть).\n\n"
            "Это сообщение мы передадим администратору вместе с жалобой исполнителя.",
            reply_markup=back_kb(),
        )
        set_state(
            tg_id,
            "company_appeal_respond",
            appeal_id=appeal_id,
            company_tg_chat_id=callback.message.chat.id,
        )


@dp.callback_query(F.data == "company_subscription")
async def cb_company_subscription(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    lines = [
        "Подписка для компаний:",
        "",
        f"Базовая стоимость — {config.PRICE_PER_MONTH} ₽ в месяц.",
        "",
        "Доступные варианты:",
        f"• 1 месяц — {config.calc_subscription_price(1)} ₽",
        f"• 3 месяца — {config.calc_subscription_price(3)} ₽ (скидка 5%)",
        f"• 6 месяцев — {config.calc_subscription_price(6)} ₽ (скидка 10%)",
        f"• 12 месяцев — {config.calc_subscription_price(12)} ₽ (скидка 15%)",
        "",
        "Оплата осуществляется переводом на карту:",
        f"{config.PAYMENT_CARD}",
        "",
        "Выберите срок подписки:",
    ]
    await callback.message.answer(
        "\n".join(lines),
        reply_markup=company_subscription_plans_kb(),
    )


@dp.callback_query(F.data.startswith("company_sub_plan_"))
async def cb_company_sub_plan(callback: CallbackQuery):
    tg_id = callback.from_user.id
    company = get_company_by_user(tg_id)
    if not company:
        await callback.message.answer("Вы ещё не зарегистрированы как компания.")
        return

    try:
        months = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    if months not in config.PLAN_DISCOUNTS:
        await callback.message.answer("Некорректный срок подписки.")
        return

    amount = config.calc_subscription_price(months)

    await callback.answer()
    await callback.message.answer(
        f"Вы выбрали подписку на {months} мес.\n"
        f"Стоимость: {amount} ₽.\n\n"
        f"Переведите эту сумму на карту:\n{config.PAYMENT_CARD}\n\n"
        "После оплаты отправьте в ответ на это сообщение ОДНО сообщение со скриншотом/фото чека "
        "и, при желании, текстовым комментарием.\n\n"
        "Мы передадим это администратору для проверки и выдачи подписки.",
        reply_markup=back_kb(),
    )
    set_state(
        tg_id,
        "company_send_payment_proof",
        company_id=company["id"],
        months=months,
    )


@dp.callback_query(F.data == "company_support")
async def cb_company_support(callback: CallbackQuery):
    await callback.message.answer(
        "Поддержка компаний:\n\n"
        "Если у вас есть вопросы по сервису, оплате подписки или спорным ситуациям, "
        "просто опишите проблему в этом чате — администратор увидит ваше сообщение."
    )


# ==========================
# ОБЫЧНЫЙ ПОЛЬЗОВАТЕЛЬ — КАБИНЕТ
# ==========================


@dp.callback_query(F.data == "viewer_check_master")
async def cb_viewer_check_master(callback: CallbackQuery):
    await callback.message.answer(
        "Введите ID исполнителя (например, M-123456), которого хотите проверить:",
        reply_markup=back_kb(),
    )
    set_state(
        callback.from_user.id,
        "viewer_check_master_enter_id",
    )


@dp.callback_query(F.data == "viewer_about")
async def cb_viewer_about(callback: CallbackQuery):
    await callback.message.answer(
        "«Белый список» — это сервис, который помогает компаниям и клиентам проверять исполнителей.\n\n"
        "Если вам нужно вызвать мастера, вы можете запросить у него ID в этом сервисе и проверить, "
        "работал ли он с компаниями и какие по нему есть отзывы."
    )


# ==========================
# АДМИН — КАБИНЕТ
# ==========================


@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if not await ensure_admin_access(message, alert=False):
        return
    await message.answer(
        "Админ-панель:",
        reply_markup=admin_main_kb(),
    )


@dp.callback_query(F.data == "admin_companies")
async def cb_admin_companies(callback: CallbackQuery):
    if not await ensure_admin_access(callback):
        return

    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT * FROM companies ORDER BY id DESC"
        )
        companies = [dict(row) for row in c.fetchall()]

    if not companies:
        await callback.message.answer("Компаний пока нет.")
        return

    await callback.message.answer(
        "Список компаний:",
        reply_markup=admin_company_list_kb(companies),
    )


@dp.callback_query(F.data.startswith("admin_company_"))
async def cb_admin_company_detail(callback: CallbackQuery):
    if not await ensure_admin_access(callback):
        return

    try:
        company_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    company = get_company_by_id(company_id)
    if not company:
        await callback.message.answer("Компания не найдена.")
        return

    await callback.message.answer(
        format_company_profile(company),
        reply_markup=admin_company_detail_kb(company_id, bool(company.get("blocked"))),
    )


@dp.callback_query(F.data.startswith("admin_block_company_"))
async def cb_admin_block_company(callback: CallbackQuery):
    if not await ensure_admin_access(callback):
        return

    try:
        company_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    set_company_blocked(company_id, True)
    await callback.message.answer("Компания заблокирована.")


@dp.callback_query(F.data.startswith("admin_unblock_company_"))
async def cb_admin_unblock_company(callback: CallbackQuery):
    if not await ensure_admin_access(callback):
        return

    try:
        company_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    set_company_blocked(company_id, False)
    await callback.message.answer("Компания разблокирована.")


@dp.callback_query(F.data.startswith("admin_give_sub_"))
async def cb_admin_give_sub(callback: CallbackQuery):
    if not await ensure_admin_access(callback):
        return

    try:
        company_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    await callback.message.answer(
        "Введите срок подписки в месяцах (числом, например 1, 3, 6, 12):",
        reply_markup=back_kb(),
    )
    set_state(
        callback.from_user.id,
        "admin_give_sub_months",
        company_id=company_id,
    )


@dp.callback_query(F.data == "admin_masters")
async def cb_admin_masters(callback: CallbackQuery):
    if not await ensure_admin_access(callback):
        return

    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT * FROM masters ORDER BY id DESC"
        )
        masters = [dict(row) for row in c.fetchall()]

    if not masters:
        await callback.message.answer("Мастеров пока нет.")
        return

    await callback.message.answer(
        "Список исполнителей:",
        reply_markup=admin_masters_list_kb(masters),
    )


@dp.callback_query(F.data.startswith("admin_master_"))
async def cb_admin_master_detail(callback: CallbackQuery):
    if not await ensure_admin_access(callback):
        return

    try:
        master_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    master = get_master_by_id(master_id)
    if not master:
        await callback.message.answer("Исполнитель не найден.")
        return

    await callback.message.answer(
        format_master_admin_profile(master, get_master_rating(master_id)),
        reply_markup=admin_master_detail_kb(master_id, bool(master.get("blocked"))),
    )


@dp.callback_query(F.data.startswith("admin_block_master_"))
async def cb_admin_block_master(callback: CallbackQuery):
    if not await ensure_admin_access(callback):
        return

    try:
        master_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    set_master_blocked(master_id, True)
    await callback.message.answer("Исполнитель заблокирован.")


@dp.callback_query(F.data.startswith("admin_unblock_master_"))
async def cb_admin_unblock_master(callback: CallbackQuery):
    if not await ensure_admin_access(callback):
        return

    try:
        master_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.message.answer("Некорректные данные.")
        return

    set_master_blocked(master_id, False)
    await callback.message.answer("Исполнитель разблокирован.")


@dp.callback_query(F.data == "admin_appeals")
async def cb_admin_appeals(callback: CallbackQuery):
    if not await ensure_admin_access(callback):
        return

    with closing(get_conn()) as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT ra.*, r.text as review_text,
                   m.full_name as master_full_name, m.public_id as master_public_id,
                   c2.name as company_name, c2.public_id as company_public_id
            FROM review_appeals ra
            JOIN reviews r ON ra.review_id = r.id
            JOIN masters m ON ra.master_id = m.id
            LEFT JOIN companies c2 ON ra.company_id = c2.id
            ORDER BY ra.id DESC
        """
        )
        appeals = [dict(row) for row in c.fetchall()]

    if not appeals:
        await callback.message.answer("Жалоб пока нет.")
        return

    await callback.message.answer(
        "Жалобы на отзывы:",
        reply_markup=admin_appeals_list_kb(appeals),
    )


@dp.callback_query(F.data.startswith("admin_appeal_"))
async def cb_admin_appeal_detail(callback: CallbackQuery):
    if not await ensure_admin_access(callback):
        return

    data = callback.data.split("_")
    if len(data) == 3:
        try:
            appeal_id = int(data[2])
        except ValueError:
            await callback.message.answer("Некорректные данные.")
            return

        appeal = get_review_appeal_by_id(appeal_id)
        if not appeal:
            await callback.message.answer("Жалоба не найдена.")
            return

        company_name = appeal.get("company_name") or "не указана"
        company_public_id = appeal.get("company_public_id") or "-"

        lines = [
            f"Жалоба #{appeal['id']}",
            "",
            f"Исполнитель: {appeal['master_full_name']} ({appeal['master_public_id']})",
            f"Компания: {company_name} ({company_public_id})",
            "",
            "Текст отзыва:",
            appeal["review_text"],
            "",
            "Жалоба исполнителя:",
            appeal.get("master_comment") or "не указано",
            "",
            "Комментарий компании:",
            appeal.get("company_comment") or "не указано",
        ]
        await callback.message.answer(
            "\n".join(lines),
            reply_markup=admin_appeal_actions_kb(appeal_id),
        )
    elif len(data) == 4 and data[2] in ("keep", "delete"):
        try:
            appeal_id = int(data[3])
        except ValueError:
            await callback.message.answer("Некорректные данные.")
            return

        appeal = get_review_appeal_by_id(appeal_id)
        if not appeal:
            await callback.message.answer("Жалоба не найдена.")
            return

        if data[2] == "keep":
            update_review_appeal_admin_decision(
                appeal_id,
                "kept_review",
                "Администратор оставил отзыв без изменений.",
            )
            await callback.message.answer(
                "Решение: отзыв оставлен, жалоба отклонена."
            )
        else:
            delete_review(appeal["review_id"])
            update_review_appeal_admin_decision(
                appeal_id,
                "deleted_review",
                "Администратор удалил отзыв по результатам рассмотрения жалобы.",
            )
            await callback.message.answer(
                "Решение: отзыв удалён, жалоба удовлетворена."
            )
    elif len(data) == 4 and data[2] == "comment":
        try:
            appeal_id = int(data[3])
        except ValueError:
            await callback.message.answer("Некорректные данные.")
            return

        appeal = get_review_appeal_by_id(appeal_id)
        if not appeal:
            await callback.message.answer("Жалоба не найдена.")
            return

        await callback.message.answer(
            "Напишите комментарий для исполнителя.\n"
            "Он будет отправлен ему вместе с итоговым решением по жалобе.",
            reply_markup=back_kb(),
        )
        set_state(
            callback.from_user.id,
            "admin_appeal_comment_text",
            appeal_id=appeal_id,
        )


# ==========================
# ОБРАБОТКА ТЕКСТОВ С СОСТОЯНИЯМИ
# ==========================


@dp.message()
async def generic_message_handler(message: Message):
    tg_id = message.from_user.id
    user = get_user(tg_id) or get_or_create_user(message)
    _role = user["role"]

    state = get_state(tg_id)
    if not state:
        await message.answer(
            "Я пока не понимаю это сообщение.\n"
            "Используйте /start или /role для начала работы."
        )
        return

    # Обработка кнопки «Назад»
    if message.text and message.text.strip() == BACK_TEXT:
        pop_state(tg_id)
        await message.answer(
            "Действие отменено. Вы вернулись в главное состояние.\n"
            "Используйте /start или /role, чтобы начать заново.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    action = state.action
    if action.startswith("admin_") and tg_id not in config.ADMIN_IDS:
        pop_state(tg_id)
        await message.answer("Нет доступа.")
        return

    # === Регистрация исполнителя ===
    if action == "master_register_full_name":
        full_name = message.text.strip()
        is_valid, error_msg = validate_full_name(full_name)
        if not is_valid:
            await message.answer(f"❌ {error_msg}\n\nПопробуйте ещё раз:")
            return
        
        await message.answer(
            "Введите ваш номер телефона:",
            reply_markup=back_kb(),
        )
        set_state(tg_id, "master_register_phone", full_name=full_name)
        return

    if action == "master_register_phone":
        phone = message.text.strip()
        is_valid, error_msg = validate_phone(phone)
        if not is_valid:
            await message.answer(f"❌ {error_msg}\n\nПопробуйте ещё раз:")
            return
        
        full_name = state.data["full_name"]
        await message.answer(
            "Укажите серию и номер паспорта:",
            reply_markup=back_kb(),
        )
        set_state(
            tg_id,
            "master_register_passport",
            full_name=full_name,
            phone=phone,
        )
        return

    if action == "master_register_passport":
        passport = message.text.strip()
        is_valid, error_msg = validate_passport(passport)
        if not is_valid:
            await message.answer(f"❌ {error_msg}\n\nПопробуйте ещё раз:")
            return
        
        full_name = state.data["full_name"]
        phone = state.data["phone"]

        master = create_master(tg_id, full_name, phone, passport)
        pop_state(tg_id)

        await message.answer(
            "Вы зарегистрированы как исполнитель ✅",
            reply_markup=ReplyKeyboardRemove(),
        )
        rating = get_master_rating(master["id"])
        await message.answer(format_master_profile(master, rating))
        await message.answer(
            "Ваш личный кабинет:", reply_markup=master_menu_kb()
        )
        return

    # === Мастер – ввод ID компании для прикрепления ===
    if action == "master_link_company_enter_id":
        company_id_text = message.text.strip().upper()
        is_valid, error_msg = validate_public_id(company_id_text)
        if not is_valid:
            await message.answer(f"❌ {error_msg}\n\nПопробуйте ещё раз:")
            return
        
        master = get_master_by_user(tg_id)
        if not master:
            await message.answer("Вы ещё не зарегистрированы как исполнитель.")
            pop_state(tg_id)
            return

        company = get_company_by_public_id(company_id_text)
        if not company:
            await message.answer("Компания с таким ID не найдена.")
            pop_state(tg_id)
            return

        if has_pending_or_active_employment(master["id"], company["id"]):
            await message.answer(
                "У вас уже есть запрос или активное сотрудничество с этой компанией."
            )
            pop_state(tg_id)
            return

        if has_any_current_employment(master["id"]):
            await message.answer(
                "Сначала завершите текущее сотрудничество.\n"
                "Вы уже числитесь в одной из компаний и не можете прикрепиться к другой."
            )
            pop_state(tg_id)
            return

        await message.answer(
            f"Компания найдена: {company['name']} ({company['public_id']}).\n"
            "Введите вашу должность (например, «мастер по ремонту техники»):",
            reply_markup=back_kb(),
        )
        set_state(
            tg_id,
            "master_enter_position",
            master_id=master["id"],
            company_id=company["id"],
        )
        return

    if action == "master_enter_position":
        position = message.text.strip()
        master_id = state.data["master_id"]
        company_id = state.data["company_id"]

        if has_any_current_employment(master_id):
            await message.answer(
                "Сначала завершите текущее сотрудничество.\n"
                "Вы уже числитесь в одной из компаний и не можете прикрепиться к другой."
            )
            pop_state(tg_id)
            return

        if has_pending_or_active_employment(master_id, company_id):
            await message.answer(
                "У вас уже есть запрос или активное сотрудничество с этой компанией."
            )
            pop_state(tg_id)
            return

        create_employment(master_id, company_id, position)
        pop_state(tg_id)
        await message.answer(
            "Запрос отправлен компании. Ожидайте подтверждения.\n"
            "Вы получите уведомление в этом чате, когда компания отреагирует.",
            reply_markup=ReplyKeyboardRemove(),
        )

        master = get_master_by_id(master_id)
        company = get_company_by_id(company_id)
        if company:
            try:
                await bot.send_message(
                    company["tg_id"],
                    (
                        "Новый запрос на сотрудничество:\n"
                        f"Исполнитель: {master['full_name']} ({master['public_id']})\n"
                        f"Должность: {position or 'не указана'}\n\n"
                        "Перейдите в раздел «Запросы», чтобы подтвердить или отклонить."
                    ),
                )
            except Exception:
                logger.exception("Не удалось уведомить компанию %s о новом запросе", company_id)
        return

    # === Регистрация компании ===
    if action == "company_enter_name":
        name = message.text.strip()
        is_valid, error_msg = validate_company_name(name)
        if not is_valid:
            await message.answer(f"❌ {error_msg}\n\nПопробуйте ещё раз:")
            return
        
        await message.answer(
            "Введите город (можно пропустить, отправив -):",
            reply_markup=back_kb(),
        )
        set_state(tg_id, "company_enter_city", name=name)
        return

    if action == "company_enter_city":
        city_raw = message.text.strip()
        city = None if city_raw == "-" else city_raw
        name = state.data["name"]

        await message.answer(
            "Введите номер ответственного лица (телефон для связи):",
            reply_markup=back_kb(),
        )
        set_state(
            tg_id,
            "company_enter_responsible_phone",
            name=name,
            city=city,
        )
        return

    if action == "company_enter_responsible_phone":
        phone = message.text.strip()
        is_valid, error_msg = validate_phone(phone)
        if not is_valid:
            await message.answer(f"❌ {error_msg}\n\nПопробуйте ещё раз:")
            return
        
        name = state.data["name"]
        city = state.data["city"]

        company = create_company(tg_id, name, city, phone)
        pop_state(tg_id)

        await message.answer(
            "Компания зарегистрирована ✅",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(format_company_profile(company))
        await message.answer(
            "Личный кабинет компании:", reply_markup=company_menu_kb(company["id"])
        )
        return

    # === Компания редактирует название ===
    if action == "company_edit_name":
        new_name = message.text.strip()
        if new_name != "-":
            is_valid, error_msg = validate_company_name(new_name)
            if not is_valid:
                await message.answer(f"❌ {error_msg}\n\nПопробуйте ещё раз:")
                return

        company_id = state.data["company_id"]
        company = get_company_by_user(tg_id)
        if not company or company["id"] != company_id:
            await message.answer("Ошибка контекста компании. Попробуйте начать заново.")
            pop_state(tg_id)
            return

        final_name = state.data["name"] if new_name == "-" else new_name
        with closing(get_conn()) as conn, conn:
            conn.execute(
                "UPDATE companies SET name = ? WHERE id = ?",
                (final_name, company_id),
            )

        pop_state(tg_id)
        updated_company = get_company_by_id(company_id)
        await message.answer(
            "Название компании обновлено.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer(
            format_company_profile(updated_company),
            reply_markup=company_menu_kb(company_id),
        )
        return

    # === Регистрация обычного пользователя (телефон) ===
    if action == "viewer_enter_phone":
        phone = message.text.strip()
        is_valid, error_msg = validate_phone(phone)
        if not is_valid:
            await message.answer(f"❌ {error_msg}\n\nПопробуйте ещё раз:")
            return
        
        set_user_phone(tg_id, phone)
        pop_state(tg_id)
        await message.answer(
            "Телефон сохранён. Теперь вы можете проверять исполнителей по ID.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await message.answer("Меню:", reply_markup=viewer_menu_kb())
        return

    # === Проверка исполнителя по ID (для зрителя / компании) ===
    if action == "viewer_check_master_enter_id":
        public_id = message.text.strip().upper()
        is_valid, error_msg = validate_public_id(public_id)
        if not is_valid:
            await message.answer(f"❌ {error_msg}\n\nПопробуйте ещё раз:")
            return
        
        master = get_master_by_public_id(public_id)
        if not master:
            await message.answer("Исполнитель с таким ID не найден.")
            pop_state(tg_id)
            return

        reviews = get_reviews_for_master(master["id"])
        rating_info = get_master_rating(master["id"])
        text = format_master_public_profile(master, reviews, rating_info)
        pop_state(tg_id)
        await message.answer(text, reply_markup=ReplyKeyboardRemove())
        return

    if action == "company_check_master_enter_id":
        public_id = message.text.strip().upper()
        is_valid, error_msg = validate_public_id(public_id)
        if not is_valid:
            await message.answer(f"❌ {error_msg}\n\nПопробуйте ещё раз:")
            return
        
        company = get_company_by_user(tg_id)
        if not company:
            await message.answer("Вы ещё не зарегистрированы как компания.")
            pop_state(tg_id)
            return

        msg = ensure_company_can_act(company, require_subscription=False)
        if msg:
            await message.answer(msg)
            pop_state(tg_id)
            return

        master = get_master_by_public_id(public_id)
        if not master:
            await message.answer("Исполнитель с таким ID не найден.")
            pop_state(tg_id)
            return

        reviews = get_reviews_for_master(master["id"])
        rating_info = get_master_rating(master["id"])
        text = format_master_public_profile(master, reviews, rating_info)
        pop_state(tg_id)
        await message.answer(text, reply_markup=ReplyKeyboardRemove())
        return

    # === Компания пишет отзыв по сотруднику ===
    if action == "company_review_rating":
        rating_raw = message.text.strip()
        if rating_raw not in {"1", "2", "3", "4", "5"}:
            await message.answer("Используйте кнопки с оценкой от 1 до 5.")
            return
        rating_value = int(rating_raw)

        await message.answer(
            "Напишите, пожалуйста, ваш отзыв по этому исполнителю.\n"
            "Укажите, как проходило сотрудничество, были ли проблемы, порекомендовали бы вы его другим.",
            reply_markup=back_kb(),
        )
        set_state(
            tg_id,
            "company_review_text",
            employment_id=state.data["employment_id"],
            master_id=state.data["master_id"],
            company_id=state.data["company_id"],
            rating=rating_value,
        )
        return

    if action == "company_request_reject_reason":
        reason = message.text.strip()
        if not reason:
            await message.answer("Причина отказа не может быть пустой. Укажите текст:")
            return
        company_id = state.data["company_id"]
        employment_id = state.data["employment_id"]

        company = get_company_by_user(tg_id)
        if not company or company["id"] != company_id:
            await message.answer("Ошибка контекста компании. Попробуйте начать заново.")
            pop_state(tg_id)
            return

        employment = get_employment_by_id(employment_id)
        if not employment or employment["company_id"] != company_id:
            await message.answer("Запрос не найден.")
            pop_state(tg_id)
            return

        set_employment_rejected(employment_id)
        pop_state(tg_id)
        await message.answer("Запрос отклонён. Исполнителю отправлено сообщение.", reply_markup=ReplyKeyboardRemove())

        master = get_master_by_id(employment["master_id"])
        if master:
            try:
                await bot.send_message(
                    master["tg_id"],
                    f"Компания {company['name']} отклонила ваш запрос на сотрудничество.\n"
                    f"Причина: {reason}",
                )
            except Exception:
                logger.exception("Не удалось отправить уведомление мастеру о несоответствии паспорта")
        return

    if action == "company_review_prompt_after_leave":
        answer = message.text.strip().lower()
        company_id = state.data["company_id"]
        master_id = state.data["master_id"]
        employment_id = state.data["employment_id"]

        if answer not in ("да", "нет", "yes", "no", "y", "n"):
            await message.answer("Ответьте «Да» или «Нет». Хотите оставить отзыв?")
            return

        if answer in ("да", "yes", "y"):
            await message.answer(
                "Выберите оценку исполнителю (1 — плохо, 5 — отлично):",
                reply_markup=rating_choice_kb(),
            )
            set_state(
                tg_id,
                "company_review_rating",
                employment_id=employment_id,
                master_id=master_id,
                company_id=company_id,
            )
        else:
            pop_state(tg_id)
            await message.answer("Хорошо, отзыв можно будет оставить позже в разделе «Уволенные сотрудники».")
        return

    if action == "company_review_text":
        text_body = message.text.strip()
        company_id = state.data["company_id"]
        master_id = state.data["master_id"]
        employment_id = state.data["employment_id"]
        rating_value = state.data.get("rating")

        company = get_company_by_user(tg_id)
        if not company or company["id"] != company_id:
            await message.answer("Ошибка контекста компании. Попробуйте начать заново.")
            pop_state(tg_id)
            return

        msg = ensure_company_can_act(company)
        if msg:
            await message.answer(msg)
            pop_state(tg_id)
            return

        review_id = create_review(
            company_id=company_id,
            master_id=master_id,
            employment_id=employment_id,
            text=text_body,
            rating=rating_value,
        )
        pop_state(tg_id)
        await message.answer("Отзыв сохранён ✅", reply_markup=ReplyKeyboardRemove())

        master = get_master_by_id(master_id)
        if master:
            snippet = text_body[:200]
            rating_text = f"Оценка: {rating_value:g}" if rating_value is not None else ""
            try:
                await bot.send_message(
                    master["tg_id"],
                    (
                        f"Компания {company['name']} оставила по вам отзыв.\n"
                        f"{rating_text}\n\n"
                        f"{snippet}{'...' if len(text_body) > 200 else ''}"
                    ).strip(),
                    reply_markup=master_open_review_kb(review_id),
                )
            except Exception:
                logger.exception("Не удалось уведомить мастера %s о новом отзыве", master_id)
        return

    # === Мастер обосновывает жалобу (СТАДИЯ 1: описание) ===
    if action == "master_appeal_reason":
        # Получаем только текст
        reason = message.text.strip() if message.text else ""
        
        # Проверка на видео
        if message.video or message.video_note:
            await message.answer(
                "❌ Видео не поддерживаются. Пожалуйста, отправьте только текст."
            )
            return
        
        # Если есть фото на первой стадии - просим только текст
        if message.photo:
            await message.answer(
                "Пожалуйста, сначала опишите причину жалобы текстом. "
                "Фото можно будет приложить на следующем шаге."
            )
            return
        
        # Если нет текста - просим текст
        if not reason:
            await message.answer(
                "Пожалуйста, опишите причину жалобы текстом."
            )
            return
        
        review_id = state.data["review_id"]

        master = get_master_by_user(tg_id)
        review = get_review_by_id(review_id)

        if not master or not review:
            await message.answer("Не удалось найти данные по отзыву. Попробуйте позже.")
            pop_state(tg_id)
            return

        if not can_master_appeal_review(review, master["id"]):
            await message.answer(
                "Сейчас нельзя подать жалобу по этому отзыву.\n"
                "Возможно, прошло более 14 дней, уже есть активная жалоба или превышен лимит попыток."
            )
            pop_state(tg_id)
            return

        existing_appeal = get_active_appeal_for_review_and_master(review_id, master["id"])
        if existing_appeal:
            await message.answer(
                "У вас уже есть активная жалоба по этому отзыву.\n"
                "Дождитесь решения по существующей жалобе."
            )
            pop_state(tg_id)
            return

        # Сохраняем описание и переходим к стадии доказательств
        set_state(
            tg_id,
            "master_appeal_proof",
            review_id=review_id,
            reason=reason,
            photo_message_ids=[],
        )
        
        await message.answer(
            "Описание сохранено.\n\n"
            "Теперь вы можете приложить до 5 фото в качестве доказательств "
            "(можно отправлять по одному) или нажмите «Пропустить», если доказательств нет.",
            reply_markup=master_appeal_proof_kb(),
        )
        return

    # === Мастер прикладывает доказательства (СТАДИЯ 2: фото) ===
    if action == "master_appeal_proof":
        review_id = state.data["review_id"]
        reason = state.data["reason"]

        master = get_master_by_user(tg_id)
        review = get_review_by_id(review_id)

        if not master or not review:
            await message.answer("Не удалось найти данные по отзыву. Попробуйте позже.")
            pop_state(tg_id)
            return

        # Если пришёл текст вместо фото - напоминаем
        if message.text and not message.photo:
            await message.answer(
                "На этом этапе нужно отправить фото (до 5 штук) в качестве доказательств "
                "или нажмите кнопку «Пропустить», если доказательств нет.",
                reply_markup=master_appeal_proof_kb(),
            )
            return

        # Проверка на видео
        if message.video or message.video_note:
            await message.answer(
                "❌ Видео не поддерживаются. Пожалуйста, отправьте только фото (до 5 штук) или нажмите «Пропустить».",
                reply_markup=master_appeal_proof_kb(),
            )
            return
        
        # Проверка количества фото
        if message.photo:
            photo_message_ids = state.data.get("photo_message_ids") or []
            if len(photo_message_ids) >= 5:
                await message.answer(
                    "❌ Можно отправить максимум 5 фото. Нажмите «Готово» или «Пропустить».",
                    reply_markup=master_appeal_proof_kb(),
                )
                return
        else:
            # Если нет фото - напоминаем
            await message.answer(
                "Пожалуйста, отправьте фото (до 5 штук) в качестве доказательств "
                "или нажмите кнопку «Пропустить», если доказательств нет.",
                reply_markup=master_appeal_proof_kb(),
            )
            return

        photo_message_ids = state.data.get("photo_message_ids") or []
        photo_message_ids.append(message.message_id)

        if len(photo_message_ids) < 5:
            set_state(
                tg_id,
                "master_appeal_proof",
                review_id=review_id,
                reason=reason,
                photo_message_ids=photo_message_ids,
                photo_chat_id=message.chat.id,
            )
            await message.answer(
                "Фото получено. Можете отправить ещё или нажмите «Готово».",
                reply_markup=master_appeal_proof_kb(),
            )
            return

        await submit_master_appeal(
            reply_message=message,
            tg_id=tg_id,
            review_id=review_id,
            reason=reason,
            master=master,
            review=review,
            photo_message_ids=photo_message_ids,
            photo_chat_id=message.chat.id,
        )
        return

    # === Компания отвечает на жалобу, присылая комментарий и файлы ===
    if action == "company_appeal_respond":
        appeal_id = state.data["appeal_id"]
        company_tg_chat_id = state.data["company_tg_chat_id"]

        appeal = get_review_appeal_by_id(appeal_id)
        if not appeal:
            await message.answer("Жалоба не найдена, попробуйте позже.")
            pop_state(tg_id)
            return

        company_comment = message.caption or message.text or "Комментарий не указан."
        files_message_id = message.message_id if message.content_type != "text" else None

        update_review_appeal_company_response(
            appeal_id,
            comment=company_comment,
            files_message_id=files_message_id,
        )
        pop_state(tg_id)

        for admin_id in config.ADMIN_IDS:
            try:
                appeal = get_review_appeal_by_id(appeal_id)
                meta = (
                    f"Новая информация по жалобе #{appeal_id}:\n"
                    f"Исполнитель: {appeal['master_full_name']} ({appeal['master_public_id']})\n"
                    f"Компания: {appeal.get('company_name') or 'не указана'} "
                    f"({appeal.get('company_public_id') or '-'})\n\n"
                    f"Текст отзыва:\n{appeal['review_text']}\n\n"
                    f"Жалоба исполнителя:\n{appeal.get('master_comment') or 'не указано'}\n\n"
                    f"Комментарий компании:\n{company_comment}\n\n"
                    "Ниже прикреплены отправленные компанией материалы (если были)."
                )
                try:
                    await bot.send_message(
                        admin_id,
                        meta,
                        reply_markup=admin_appeal_actions_kb(appeal_id),
                    )
                    await bot.copy_message(
                        admin_id,
                        from_chat_id=company_tg_chat_id,
                        message_id=files_message_id or message.message_id,
                    )
                except Exception:
                        logger.exception(
                            "Не удалось переслать материалы по жалобе %s админу %s",
                            appeal_id,
                            admin_id,
                        )
            except Exception:
                logger.exception("Ошибка при уведомлении админов о жалобе %s", appeal_id)

        await message.answer(
            "Ваш комментарий и материалы отправлены администратору.\n"
            "Жалоба перейдёт в стадию рассмотрения.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # === Админ выдаёт подписку (ввод месяцев) ===
    if action == "admin_give_sub_months":
        try:
            months = int(message.text.strip())
        except ValueError:
            await message.answer("Введите число месяцев (например, 1, 3, 6, 12).")
            return

        company_id = state.data["company_id"]
        set_company_subscription(company_id, months)
        pop_state(tg_id)
        await message.answer(
            f"Подписка на {months} мес. выдана компании с ID {company_id}.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # === Админ пишет комментарий по жалобе ===
    if action == "admin_appeal_comment_text":
        appeal_id = state.data["appeal_id"]
        comment = message.text.strip()

        appeal = get_review_appeal_by_id(appeal_id)
        if not appeal:
            await message.answer("Жалоба не найдена.")
            pop_state(tg_id)
            return

        update_review_appeal_admin_decision(
            appeal_id,
            appeal["status"],
            comment,
        )
        pop_state(tg_id)

        master = get_master_by_id(appeal["master_id"])
        if master:
            try:
                await bot.send_message(
                    master["tg_id"],
                    f"Комментарий администратора по вашей жалобе #{appeal_id}:\n\n{comment}",
                )
            except Exception:
                logger.exception(
                    "Не удалось отправить комментарий мастеру по жалобе %s",
                    appeal_id,
                )

        await message.answer("Комментарий сохранён и отправлен исполнителю.", reply_markup=ReplyKeyboardRemove())
        return

    # === Компания отправляет чек об оплате подписки ===
    if action == "company_send_payment_proof":
        company_id = state.data["company_id"]
        months = state.data["months"]

        company = get_company_by_id(company_id)
        if not company or company["tg_id"] != tg_id:
            await message.answer("Контекст компании потерян, попробуйте оформить подписку заново.")
            pop_state(tg_id)
            return

        for admin_id in config.ADMIN_IDS:
            text = (
                f"Компания {company['name']} ({company['public_id']}) отправила чек на оплату подписки.\n"
                f"Срок: {months} мес.\n\n"
                "Ниже пересылаю сообщение с чеком."
            )
            try:
                await bot.send_message(admin_id, text)
                await bot.copy_message(
                    chat_id=admin_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
            except Exception:
                logger.exception("Не удалось переслать чек админу")

        pop_state(tg_id)

        await message.answer(
            "Ваш чек и данные по оплате отправлены администратору.\n"
            "После проверки подписка будет выдана, и вы получите уведомление в этом чате.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # === Компания меняет паспорт исполнителя ===
    if action == "company_change_passport_enter":
        new_passport = message.text.strip()
        is_valid, error_msg = validate_passport(new_passport)
        if not is_valid:
            await message.answer(f"❌ {error_msg}\n\nПопробуйте ещё раз:")
            return
        
        master_id = state.data["master_id"]

        company = get_company_by_user(tg_id)
        if not company:
            await message.answer("Вы больше не зарегистрированы как компания.")
            pop_state(tg_id)
            return

        msg = ensure_company_can_act(company)
        if msg:
            await message.answer(msg)
            pop_state(tg_id)
            return

        with closing(get_conn()) as conn, conn:
            conn.execute(
                "UPDATE masters SET passport = ?, passport_locked = 1 WHERE id = ?",
                (new_passport, master_id),
            )

        pop_state(tg_id)

        master = get_master_by_id(master_id)
        if master:
            try:
                await bot.send_message(
                    master["tg_id"],
                    f"Компания {company['name']} обновила ваши паспортные данные в системе."
                )
            except Exception:
                logger.exception("Не удалось уведомить мастера об изменении паспорта компанией")

        await message.answer(
            "Паспортные данные исполнителя обновлены и залочены для изменения со стороны мастера.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # === Мастер редактирует профиль (ФИО / телефон / паспорт) ===
    if action == "master_edit_full_name":
        master_id = state.data["master_id"]
        new_full_name = message.text.strip()
        if new_full_name != "-":
            is_valid, error_msg = validate_full_name(new_full_name)
            if not is_valid:
                await message.answer(f"❌ {error_msg}\n\nПопробуйте ещё раз:")
                return
            state.data["full_name"] = new_full_name

        await message.answer(
            "Введите новый номер телефона (или '-' чтобы оставить без изменений):",
            reply_markup=back_kb(),
        )
        set_state(
            tg_id,
            "master_edit_phone",
            **state.data,
        )
        return

    if action == "master_edit_phone":
        master_id = state.data["master_id"]
        new_phone = message.text.strip()
        if new_phone != "-":
            is_valid, error_msg = validate_phone(new_phone)
            if not is_valid:
                await message.answer(f"❌ {error_msg}\n\nПопробуйте ещё раз:")
                return
            state.data["phone"] = new_phone

        passport_locked = bool(state.data.get("passport_locked"))
        if passport_locked:
            with closing(get_conn()) as conn, conn:
                conn.execute(
                    "UPDATE masters SET full_name = ?, phone = ? WHERE id = ?",
                    (state.data["full_name"], state.data["phone"], master_id),
                )
            pop_state(tg_id)
            master = get_master_by_id(master_id)
            await message.answer(
                "Профиль обновлён (паспорт изменить может только компания).",
                reply_markup=ReplyKeyboardRemove(),
            )
            rating = get_master_rating(master_id)
            await message.answer(format_master_profile(master, rating))
            return
        else:
            await message.answer(
                "Введите новые паспортные данные (или '-' чтобы оставить без изменений):",
                reply_markup=back_kb(),
            )
            set_state(
                tg_id,
                "master_edit_passport",
                **state.data,
            )
            return

    if action == "master_edit_passport":
        master_id = state.data["master_id"]
        new_passport = message.text.strip()
        if new_passport != "-":
            is_valid, error_msg = validate_passport(new_passport)
            if not is_valid:
                await message.answer(f"❌ {error_msg}\n\nПопробуйте ещё раз:")
                return
            state.data["passport"] = new_passport

        with closing(get_conn()) as conn, conn:
            conn.execute(
                "UPDATE masters SET full_name = ?, phone = ?, passport = ? WHERE id = ?",
                (state.data["full_name"], state.data["phone"], state.data["passport"], master_id),
            )

        pop_state(tg_id)
        master = get_master_by_id(master_id)
        await message.answer("Профиль обновлён.", reply_markup=ReplyKeyboardRemove())
        rating = get_master_rating(master_id)
        await message.answer(format_master_profile(master, rating))
        return

    # Если дошли до сюда — что-то не учли
    await message.answer(
        "Похоже, я не понял, что вы хотели сделать.\n"
        "Попробуйте воспользоваться командами /start или /role."
    )


# ==========================
# ЗАПУСК
# ==========================


async def maintenance_worker():
    """Фоновая задача: регулярно выполняет обслуживание базы (увольнения, жалобы, очистка состояний)."""
    while True:
        try:
            closed_employments = auto_close_leave_requests()
            for employment in closed_employments:
                try:
                    await bot.send_message(
                        employment["master_tg_id"],
                        (
                            "Система автоматически завершила сотрудничество по вашему запросу "
                            "на увольнение, так как компания не ответила в течение 2 дней.\n\n"
                            f"Компания: {employment['company_name']} ({employment['company_public_id']})"
                        ),
                    )
                except Exception:
                    logger.exception(
                        "Не удалось уведомить мастера %s об авто-увольнении",
                        employment["master_id"],
                    )

                try:
                    await bot.send_message(
                        employment["company_tg_id"],
                        (
                            "Система автоматически завершила сотрудничество по запросу на увольнение, "
                            "так как вы не ответили в течение 2 дней.\n\n"
                            f"Исполнитель: {employment['master_full_name']} "
                            f"({employment['master_public_id']})"
                        ),
                    )
                except Exception:
                    logger.exception(
                        "Не удалось уведомить компанию %s об авто-увольнении",
                        employment["company_id"],
                    )
            auto_review_appeals_maintenance()
            clear_expired_states(max_age_hours=24)  # Очистка состояний старше 24 часов
        except Exception:
            logger.exception("Ошибка в задаче обслуживания (maintenance_worker)")
        await asyncio.sleep(3600)


async def main():
    try:
        logger.info("Инициализация базы данных...")
        init_db()
        logger.info("База данных инициализирована")
        
        logger.info("Запуск фоновых задач...")
        asyncio.create_task(maintenance_worker())
        
        logger.info("Запуск бота...")
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.exception("Критическая ошибка при работе бота")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБот остановлен")
    except Exception as e:
        print("\n" + "=" * 60)
        print("КРИТИЧЕСКАЯ ОШИБКА!")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        print("\nПроверьте логи выше для деталей")
        input("\nНажмите Enter для выхода...")
