# skriptolog_bot.py
# MVP Telegram-бот «Скриптолог»

import os
import csv
import time
from dataclasses import dataclass, field
from typing import Dict, List

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CSV_PATH = os.environ.get("CSV_PATH", "skritolog_notes.csv")

(WAIT_FREE_TEXT, WAIT_CLIENT_NAME, WAIT_SUMMARY) = range(3)

SITUATIONS = [
    ("not_interested", "Неинтересно / я ничего не оставлял"),
    ("busy_later", "Сейчас занят, давайте позже"),
    ("dont_need", "Ничего не нужно"),
    ("self_search", "Я сам смотрю (ЦИАН/Авито)"),
    ("other_agent", "Мне уже звонили / я с агентом"),
    ("expensive", "Дорого / цены кусаются"),
    ("think_later", "Подумаю / перезвоните позже"),
    ("no_mortgage", "Нет одобрения / ставки высокие"),
    ("just_browsing", "Пока присматриваюсь"),
    ("send_whatsapp", "Пришлите в WhatsApp/почту"),
]

RESPONSES: Dict[str, List[Dict[str, str]]] = {
    "not_interested": [
        {
            "hook": "Понимаю, звонков сейчас много.",
            "clar": "Чтобы не отвлекать — на что ориентируемся: район и бюджет?",
            "frame": "У нас прямой доступ к закрытым предложениям от застройщиков, без лишнего шума.",
            "close": "Соберу 3 точных варианта и пришлю сегодня до 17:00 — подойдёт?",
        },
        {
            "hook": "Всё ок, я коротко и по делу.",
            "clar": "Для себя или под инвестицию?",
            "frame": "Покажу только то, что совпадает по критериям, без рассылок.",
            "close": "Если ничего не подойдёт — больше не беспокою. Договорились?",
        },
    ],
    "busy_later": [
        {
            "hook": "Понимаю — время ценно.",
            "clar": "Когда удобно 5 минут связи: сегодня 18:00 или завтра 11:00?",
            "frame": "Я подготовлю 2–3 варианта под ваши параметры, чтобы разговор был быстрым.",
            "close": "Фиксируем слот?",
        }
    ],
    "dont_need": [
        {
            "hook": "Слушаю вас.",
            "clar": "Скажите, если бы смотрели — какой район/бюджет был бы комфортен?",
            "frame": "Задам ещё 1–2 вопроса и честно скажу, есть ли что-то стоящее.",
            "close": "Если не актуально — закроем диалог без спама. Ок?",
        }
    ],
    "self_search": [
        {
            "hook": "Отлично, что сравниваете.",
            "clar": "Можно ссылку на лот? Проверю идентичность по корпусу/этажу/отделке.",
            "frame": "Часто цена расходится из‑за нюансов. Я добиваюсь паритета или бонусов.",
            "close": "Если это точное совпадение — согласуем ту же цену или лучше.",
        }
    ],
    "other_agent": [
        {
            "hook": "Понимаю, комфорт с агентом важен.",
            "clar": "Что для вас критично в работе: скорость, глубина подбора или переговоры по цене?",
            "frame": "Могу точечно добить условия — без смены агента, если так вам спокойнее.",
            "close": "Проверю 2 позиции по условиям, вернусь с чёткими цифрами — удобно?",
        }
    ],
    "expensive": [
        {
            "hook": "Согласен, цены в Москве непростые.",
            "clar": "Какой коридор бюджета комфортен сейчас?",
            "frame": "У нас есть акции/рассрочки от застройщиков, которых нет в открытых базах.",
            "close": "Покажу два пути: A) строго в бюджете; Б) класс выше со скидкой. Что ближе?",
        }
    ],
    "think_later": [
        {
            "hook": "Это взвешенное решение — всё ок.",
            "clar": "Какая дата комфортна, чтобы вернуться к разговору?",
            "frame": "За 4 недели по вашему сегменту цены слегка росли — лучше зафиксировать 2–3 лота в избранном.",
            "close": "Подключу уведомление о снижении цены и новых корпусах — сделать?",
        }
    ],
    "no_mortgage": [
        {
            "hook": "Понимаю про ставки.",
            "clar": "Какой первый взнос комфортен?",
            "frame": "Посчитаю субсидии застройщика и поэтапный платёж, плюс альтернативные банки.",
            "close": "Пришлю 2 расчёта сегодня. Оставим ориентир по бюджету и сроку?",
        }
    ],
    "just_browsing": [
        {
            "hook": "Замечательно — смотреть с умом всегда лучше.",
            "clar": "Для себя или под инвестицию? И сколько минут до метро комфортно?",
            "frame": "Соберу лёгкую подборку без навязчивости — 3 лучших варианта.",
            "close": "Скину сегодня до 17:00, а короткий созвон на 5 минут сделаем?",
        }
    ],
    "send_whatsapp": [
        {
            "hook": "Конечно, пришлю.",
            "clar": "Чтобы не грузить, выберу 3 точных. Семья/инвестиция и коридор бюджета?",
            "frame": "Так подборка попадёт в цель, без воды.",
            "close": "Отправлю и отмечу 2 минуты на обратную связь — когда удобно?",
        }
    ],
}

KEYWORDS: Dict[str, List[str]] = {
    "not_interested": ["неинтересно", "ничего не оставлял", "кто вы", "зачем звоните"],
    "busy_later": ["занят", "перезвоните", "позже"],
    "dont_need": ["не нужно", "не нужен", "не актуально"],
    "self_search": ["сам смотрю", "циан", "avito", "авито"],
    "other_agent": ["уже звонили", "другой агент", "есть агент"],
    "expensive": ["дорого", "цены кусаются", "дороговато", "дорогая"],
    "think_later": ["подумаю", "через месяц", "позже решу"],
    "no_mortgage": ["ипотека", "ставка", "не одобрили", "нет одобрения"],
    "just_browsing": ["присматриваюсь", "смотрю пока"],
    "send_whatsapp": ["whatsapp", "ватсап", "почту", "email", "e-mail"],
}

@dataclass
class SessionNote:
    user_id: int
    client_name: str = "—"
    entries: List[Dict[str, str]] = field(default_factory=list)

SESSIONS: Dict[int, SessionNote] = {}

def top_keyboard():
    rows = []
    row = []
    for i, (_, title) in enumerate(SITUATIONS, 1):
        row.append(KeyboardButton(f"{i}. {title}"))
        if i % 2 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([KeyboardButton("Свободный ввод фразы клиента")])
    rows.append([KeyboardButton("Итоги разговора")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def classify(text: str) -> str:
    t = text.lower()
    best_key = "not_interested"
    best_hits = 0
    for key, kws in KEYWORDS.items():
        hits = sum(1 for w in kws if w in t)
        if hits > best_hits:
            best_hits = hits
            best_key = key
    return best_key

def format_response_block(v: Dict[str, str]) -> str:
    return (
        f"— {v['hook']}\n"
        f"— {v['clar']}\n"
        f"— {v['frame']}\n"
        f"— {v['close']}"
    )

def build_variants(sit_key: str) -> List[str]:
    variants = []
    for v in RESPONSES.get(sit_key, []):
        variants.append(format_response_block(v))
    if not variants:
        variants.append("— Понял вас.\n— Уточню 1–2 момента, чтобы предложить точнее.\n— Подберу без лишних сообщений.\n— Пришлю 2–3 варианта сегодня — удобно?")
    return variants

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_session(update.effective_user.id)
    await update.message.reply_text(
        "Скриптолог на связи. Выберите ситуацию или введите фразу клиента.",
        reply_markup=top_keyboard(),
    )
    return WAIT_FREE_TEXT

def ensure_session(user_id: int) -> SessionNote:
    if user_id not in SESSIONS:
        SESSIONS[user_id] = SessionNote(user_id=user_id)
    return SESSIONS[user_id]

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id

    if text.startswith("Итоги"):
        await update.message.reply_text("Как зовут клиента? (для конспекта)")
        return WAIT_CLIENT_NAME

    if text.startswith("Свободный"):
        await update.message.reply_text("Напишите фразу клиента целиком.")
        return WAIT_FREE_TEXT

    try:
        idx = int(text.split(".")[0]) - 1
        sit_key, sit_title = SITUATIONS[idx]
    except Exception:
        sit_key = classify(text)
        sit_title = dict(SITUATIONS).get(sit_key, sit_key)

    variants = build_variants(sit_key)
    best = variants[0]

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Ещё вариант", callback_data=f"more:{sit_key}")],
        [InlineKeyboardButton("Копировать лучший", callback_data="copy")],
        [InlineKeyboardButton("Итоги разговора", callback_data="summary")],
    ])

    await update.message.reply_text(
        f"<b>{sit_title}</b>\n\n{best}",
        parse_mode="HTML",
        reply_markup=kb,
    )
    return WAIT_FREE_TEXT

async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id

    sit_key = classify(text)
    sit_title = dict(SITUATIONS).get(sit_key, sit_key)
    variants = build_variants(sit_key)
    best = variants[0]

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Ещё вариант", callback_data=f"more:{sit_key}")],
        [InlineKeyboardButton("Копировать лучший", callback_data="copy")],
        [InlineKeyboardButton("Итоги разговора", callback_data="summary")],
    ])

    await update.message.reply_text(
        f"<b>{sit_title}</b>\n\n{best}",
        parse_mode="HTML",
        reply_markup=kb,
    )
    return WAIT_FREE_TEXT

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("more:"):
        sit_key = query.data.split(":", 1)[1]
        variants = build_variants(sit_key)
        text = variants[1] if len(variants) > 1 else variants[0]
        await query.edit_message_text(text)
        return

    if query.data == "copy":
        await query.edit_message_text("Текст скопирован — используйте в звонке. Нажмите ‘Итоги разговора’, когда будете готовы.")
        return

    if query.data == "summary":
        await query.edit_message_text("Как зовут клиента? (для конспекта)")
        return WAIT_CLIENT_NAME

async def ask_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Коротко: что важнее всего для клиента? (1–2 фразы)")
    return WAIT_SUMMARY

async def build_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    important = update.message.text.strip()

    ts = int(time.time())
    row = {
        "timestamp": ts,
        "agent_id": update.effective_user.id,
        "client_name": "-",  # упрощённо: имя можно запросить отдельной командой
        "important": important,
        "entries": important,  # в MVP пишем краткий итог
    }

    file_exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    await update.message.reply_text(
        "Готово. Конспект сохранён. Продолжим? Выберите ситуацию или введите фразу клиента.",
        reply_markup=top_keyboard(),
    )
    return WAIT_FREE_TEXT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ок, вернёмся позже. Наберите /start, чтобы продолжить.")
    return ConversationHandler.END

def main():
    if not BOT_TOKEN:
        raise RuntimeError("Установите BOT_TOKEN в .env")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAIT_FREE_TEXT: [
                MessageHandler(filters.Regex("^(Итоги разговора)$"), handle_menu),
                MessageHandler(filters.Regex("^(Свободный ввод фразы клиента)$"), handle_menu),
                MessageHandler(filters.Regex("^([1-9]|10)\\..*"), handle_menu),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text),
            ],
            WAIT_CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_name)],
            WAIT_SUMMARY: [MessageHandler(filters.TEXT & ~filters.COMMAND, build_summary)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(on_callback))

    print("Skriptolog запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
