"""
Конфигурация бота "Белый список"
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Основные настройки
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "bot.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Администраторы
ADMIN_IDS = {
    int(x.strip()) for x in os.getenv("ADMINS", "").split(",") if x.strip().isdigit()
}

# Настройки подписок
PRICE_PER_MONTH = 790  # базовая цена за 1 месяц
PLAN_DISCOUNTS = {
    1: 0.0,   # без скидки
    3: 0.05,  # 5%
    6: 0.10,  # 10%
    12: 0.15, # 15%
}
PAYMENT_CARD = os.getenv("PAYMENT_CARD", "0000 0000 0000 0000")  # карта для перевода

# Валидация
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")


def calc_subscription_price(months: int) -> int:
    """
    Считает стоимость подписки с учётом скидки.
    Возвращает целое количество рублей.
    """
    base = PRICE_PER_MONTH * months
    discount = PLAN_DISCOUNTS.get(months, 0.0)
    return int(round(base * (1 - discount)))
