"""
Функции форматирования текста для бота
"""
from typing import List, Optional, Tuple


def _get_risk_label(avg_rating: Optional[float], ratings_count: int) -> Tuple[str, str]:
    if not avg_rating:
        return "🟢", "Нейтральный риск (нет оценок)"
    if avg_rating >= 4.5:
        return "🟢", f"Низкий риск (рейтинг {avg_rating})"
    if avg_rating >= 3.0:
        return "🟡", f"Средний риск (рейтинг {avg_rating})"
    return "🔴", f"Высокий риск (рейтинг {avg_rating})"


def format_employments_list_for_master(employments: List[dict]) -> str:
    if not employments:
        return "Пока нет данных о вашем сотрудничестве с компаниями."

    lines = []
    for e in employments:
        line = f"• {e['company_name']} ({e['company_public_id']})"
        if e["status"] == "accepted":
            line += " — работает"
        elif e["status"] == "leave_requested":
            line += " — запрос на увольнение"
        elif e["status"] == "ended":
            line += " — сотрудничество завершено"
        if e.get("position"):
            line += f", должность: {e['position']}"
        lines.append(line)
    return "\n".join(lines)


def format_reviews_list_for_master(reviews: List[dict]) -> str:
    if not reviews:
        return "Пока по вам нет отзывов."

    lines = []
    for r in reviews:
        rating = f" ⭐ {r['rating']}" if r.get("rating") else ""
        lines.append(
            f"• {r['company_name']} ({r['company_public_id']}){rating}: "
            f"{r['text'][:100]}{'...' if len(r['text']) > 100 else ''}"
        )
    return "\n".join(lines)


def format_master_public_profile(master: dict, reviews: List[dict], rating: Optional[dict] = None) -> str:
    lines = [f"Исполнитель: {master['full_name']} ({master['public_id']})"]
    if master.get("phone"):
        lines.append(f"Телефон (если он доступен): {master['phone']}")
    rating = rating or {}
    emoji, risk_text = _get_risk_label(rating.get("avg_rating"), rating.get("ratings_count", 0))
    if rating.get("ratings_count"):
        lines.append(f"Рейтинг: {rating['avg_rating']} ({rating['ratings_count']} отзывов)")
    lines.append(f"Фактор риска: {emoji} {risk_text}")
    lines.append("")

    if not reviews:
        lines.append("Пока по этому исполнителю нет отзывов от компаний.")
    else:
        lines.append("Отзывы компаний:")
        for r in reviews:
            company_name = r["company_name"]
            company_public_id = r["company_public_id"]
            text = r["text"].strip()
            if len(text) > 300:
                text = text[:300] + "..."
            created_at = r.get("created_at") or ""
            lines.append(f"• {company_name} ({company_public_id}): {text}")
            if created_at:
                lines.append(f"  ⏱ {created_at}")
            lines.append("")

    return "\n".join(lines).strip()


def format_master_profile(master: dict, rating: Optional[dict] = None) -> str:
    lines = ["Ваш профиль исполнителя:"]
    lines.append(f"👤 ФИО: {master['full_name']}")
    lines.append(f"ID: {master['public_id']}")
    rating = rating or {}
    emoji, risk_text = _get_risk_label(rating.get("avg_rating"), rating.get("ratings_count", 0))
    if rating.get("ratings_count"):
        lines.append(f"Рейтинг: {rating['avg_rating']} ({rating['ratings_count']} отзывов)")
    lines.append(f"Фактор риска: {emoji} {risk_text}")
    if master.get("phone"):
        lines.append(f"Телефон: {master['phone']}")
    if master.get("passport"):
        passport = master["passport"]
        masked = "***" + passport[-4:] if len(passport) > 4 else "***"
        locked = bool(master.get("passport_locked"))
        status = "подтверждён компанией" if locked else "ещё не подтверждён компанией"
        lines.append(
            f"Паспорт: {masked} ({status}, полностью хранится в системе, но не показывается целиком)"
        )
    if master.get("blocked"):
        lines.append("Статус: 🚫 профиль заблокирован администратором")
    else:
        lines.append("Статус: ✅ профиль активен")
    return "\n".join(lines)


def format_company_profile(company: dict) -> str:
    lines = ["Профиль компании:"]

    lines.append(f"🏢 {company['name']}")
    lines.append(f"ID компании: {company['public_id']}")
    lines.append(f"Город: {company['city'] or 'не указан'}")
    lines.append(f"Телефон ответственного: {company['responsible_phone']}")
    if company.get("blocked"):
        lines.append("Статус: 🚫 профиль заблокирован администратором")
    else:
        lines.append("Статус: ✅ профиль активен")

    if company.get("subscription_until"):
        from datetime import datetime
        try:
            until_dt = datetime.fromisoformat(company["subscription_until"])
            lines.append(f"Подписка активна до: {until_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        except ValueError:
            lines.append("Подписка: есть, но дата некорректна (обратитесь в поддержку).")
    else:
        lines.append("Подписка: отсутствует.")

    return "\n".join(lines)


def format_review_detail(review: dict) -> str:
    lines = []
    lines.append(
        f"Отзыв компании {review['company_name']} ({review['company_public_id']}) "
        f"по исполнителю {review['master_full_name']} ({review['master_public_id']}):"
    )
    lines.append("")
    if review.get("rating"):
        lines.append(f"Оценка: {review['rating']}")
        lines.append("")
    lines.append(review["text"])
    if review.get("created_at"):
        lines.append("")
        lines.append(f"Создан: {review['created_at']}")
    return "\n".join(lines)


def format_employment_reviews(employment: dict, reviews: List[dict]) -> str:
    lines = [
        f"История отзывов по сотрудничеству с {employment['full_name']} ({employment['master_public_id']})",
        f"Компания: {employment['company_name']} ({employment['company_public_id']})",
        "",
    ]

    if not reviews:
        lines.append("По данному сотрудничеству пока нет отзывов.")
        return "\n".join(lines)

    for r in reviews:
        company_name = r["company_name"]
        company_public_id = r["company_public_id"]
        text = r["text"].strip()
        if len(text) > 300:
            text = text[:300] + "..."
        created_at = r.get("created_at") or ""
        rating = f" ⭐ {r['rating']}" if r.get("rating") else ""
        lines.append(f"• {company_name}{rating}: {text}")
        if created_at:
            lines.append(f"  ⏱ {created_at}")
        lines.append("")

    return "\n".join(lines).strip()

