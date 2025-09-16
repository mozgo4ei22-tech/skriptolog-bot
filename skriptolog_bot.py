# ===== FILE: skriptolog_bot.py =====
# Telegram-бот «Скриптолог» v4 — гибкие ответы + слоты + шаблоны + конспект
# Запуск локально: pip install -r requirements.txt && python skriptolog_bot.py
# Для Render как Background Worker: Build: pip install -r requirements.txt; Start: python skriptolog_bot.py

import os, csv, time, re, random
from dataclasses import dataclass, field
from typing import Dict, List

from dotenv import load_dotenv
from rapidfuzz import fuzz

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

(WAIT_FREE_TEXT, WAIT_SUMMARY) = range(2)

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

KEYWORDS: Dict[str, List[str]] = {
    "not_interested": ["неинтерес", "ничего не оставлял", "кто вы", "зачем звоните"],
    "busy_later": ["занят", "перезвон", "позже", "через", "после"],
    "dont_need": ["не нужно", "не нужен", "не актуал"],
    "self_search": ["сам смотрю", "циан", "avito", "авито"],
    "other_agent": ["уже звонили", "другой агент", "есть агент"],
    "expensive": ["дорого", "кусают", "дороговато", "дорогая", "цены"],
    "think_later": ["подумаю", "через месяц", "позже решу"],
    "no_mortgage": ["ипотек", "ставк", "не одобрили", "нет одобрения", "банк"],
    "just_browsing": ["присматриваюсь", "смотрю пока", "пока смотрю"],
    "send_whatsapp": ["whatsapp", "ватсап", "почту", "email", "e-mail", "электрон"],
}

DISTRICT_PAT = re.compile(r"(цao|сао|свао|вао|ювао|юао|юзао|зао|сзао|зелао|нао|тинао|новая москва)", re.I)
TONES = ["мягкий","уверенный","эксперт"]
TONE_PHRASES = {
    "мягкий": {
        "hook": ["Понимаю вас.", "Всё ок, давайте спокойно посмотрим."],
        "ask": ["Чуть уточню, чтобы попасть в цель:", "Задам 1–2 коротких вопроса:"],
        "close": ["Соберу 3 точных варианта и пришлю сегодня — подойдёт?", "Договоримся на короткий созвон на 5 минут?"],
    },
    "уверенный": {
        "hook": ["Сделаем быстро и по делу.", "Возьму на себя подбор, чтобы вы не тратили время."],
        "ask": ["Проверьте, верно ли понимаю:", "Уточню ключевые параметры:"],
        "close": ["Покажу 2 сильных варианта, согласуем время связи.", "Зафиксирую слот на сегодня 18:00 — удобно?"],
    },
    "эксперт": {
        "hook": ["Сфокусируемся на факторах, что реально влияют на цену.", "Соберу выборку с акциями и корректной сопоставимостью."],
        "ask": ["Нужны 3 параметра:", "Подтвердите ключевые границы:"],
        "close": ["Отправлю сравнение на 1 экран + рекомендацию. Ок?", "Сделаю бенчмарк и выйду с цифрами."],
    },
}

INTENT_LIB: Dict[str, Dict[str, List[str]]] = {
    "not_interested": {"frame": ["Работаю по новостройкам Москвы, без лишних рассылок. Подберу ровно под {goal}."]},
    "busy_later": {"frame": ["Подготовлю 2–3 варианта под {budget} {district} {rooms} и свяжемся {time}."]},
    "dont_need": {"frame": ["Если будете смотреть, ориентир по бюджету {budget} и до метро {metro} — так попаду точнее."]},
    "self_search": {"frame": ["Часто цена «гуляет» из‑за корпуса/этажа/отделки. Пришлите ссылку — проверю и добьюсь паритета."]},
    "other_agent": {"frame": ["Останемся в вашей связке: точечно улучшу условия без смены агента — так комфортнее."]},
    "expensive": {"frame": ["Есть акции и поэтапный платёж у застройщиков. Покажу путь «строго в {budget}» и «класс выше со скидкой»."]},
    "think_later": {"frame": ["За месяц в сегменте мог быть рост. Зафиксируем 2–3 лота и включим уведомления по цене."]},
    "no_mortgage": {"frame": ["Посчитаю субсидии и альтернативные банки под первый взнос. Срок одобрения учтём."]},
    "just_browsing": {"frame": ["Соберу лёгкую подборку: 3 лучших по {goal} и {metro}."]},
    "send_whatsapp": {"frame": ["Пришлю 3 точных варианта в WhatsApp. Чтобы не грузить, уточню 2 момента и попаду в цель."]},
}

@dataclass
class SessionNote:
    user_id: int
    tone: str = "уверенный"
    entries: List[Dict[str, str]] = field(default_factory=list)

SESSIONS: Dict[int, SessionNote] = {}

def ensure_session(uid: int) -> SessionNote:
    if uid not in SESSIONS:
        SESSIONS[uid] = SessionNote(user_id=uid)
    return SESSIONS[uid]

# ===== Извлечение слотов из свободной речи =====

def extract_slots(text: str) -> Dict[str, str]:
    t = text.lower()
    slots: Dict[str, str] = {}
    m = re.search(r"(\d{1,3})(?:[.,](\d))?\s*(?:-|–|до)?\s*(\d{1,3})?\s*(?:млн|млн\.|миллиона|млн руб|млн₽)?", t)
    if m:
        left, right = m.group(1), m.group(3)
        slots["budget"] = (f"{left}–{right} млн" if right else f"до {left} млн")
    if "студ" in t:
        slots["rooms"] = "студия"
    else:
        m = re.search(r"([1-5])\s*к", t)
        if m:
            slots["rooms"] = f"{m.group(1)}к"
    m = re.search(r"(?:до|не более|макс)\s*(\d{1,2})\s*мин", t)
    if m:
        slots["metro"] = f"≤{m.group(1)} мин"
    if "сегодня" in t or "вечер" in t:
        slots["time"] = "сегодня"
    elif "завтра" in t:
        slots["time"] = "завтра"
    elif "выходн" in t:
        slots["time"] = "на выходных"
    elif "через" in t:
        m = re.search(r"через\s+(\d+)\s*(дн|нед|мес)", t)
        if m:
            unit = {"дн":"дн.","нед":"нед.","мес":"мес."}[m.group(2)]
            slots["time"] = f"через {m.group(1)} {unit}"
    md = DISTRICT_PAT.search(t)
    if md:
        slots["district"] = md.group(0).upper().replace("ЦAO","ЦАО")
    if "инвест" in t or "сдач" in t:
        slots["goal"] = "инвестиция"
    elif "для себя" in t or "жив" in t:
        slots["goal"] = "для себя"
    return slots

# ===== Классификация интента =====

def detect_intent(text: str) -> str:
    t = text.lower()
    best_key, best_hits = "not_interested", 0
    for key, kws in KEYWORDS.items():
        hits = sum(1 for w in kws if w in t)
        if hits > best_hits:
            best_key, best_hits = key, hits
    if best_hits > 0:
        return best_key
    # fuzzy запасной
    best_key, best_score = "not_interested", 0
    for key, kws in KEYWORDS.items():
        for w in kws:
            score = fuzz.partial_ratio(t, w)
            if score > best_score:
                best_key, best_score = key, score
    return best_key

# ===== Сборка ответа =====

def compose_reply(intent: str, tone: str, slots: Dict[str, str]) -> str:
    pack = TONE_PHRASES.get(tone, TONE_PHRASES["уверенный"])
    hook = random.choice(pack["hook"]) 
    ask = random.choice(pack["ask"]) 
    frame_tpl = random.choice(INTENT_LIB.get(intent, {}).get("frame", ["Подберу точечно под ваш запрос."]))
    def s(k): return slots.get(k)
    frame = frame_tpl.format(budget=s("budget"), rooms=s("rooms"), district=s("district"), metro=s("metro"), goal=s("goal"), time=s("time"))
    close = random.choice(pack["close"]) 
    return f"— {hook}\n— {ask}\n— {frame}\n— {close}"

# ===== UI =====

def top_keyboard(tone: str):
    rows, row = [], []
    for i, (_, title) in enumerate(SITUATIONS, 1):
        row.append(KeyboardButton(f"{i}. {title}"))
        if i % 2 == 0:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([KeyboardButton("Свободный ввод фразы клиента")])
    rows.append([KeyboardButton("Итоги разговора")])
    rows.append([KeyboardButton(f"Тон: {tone}")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

# ===== Handlers =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = ensure_session(update.effective_user.id)
    await update.message.reply_text("Скриптолог v4 на связи. Выберите ситуацию или введите фразу клиента.", reply_markup=top_keyboard(s.tone))
    return WAIT_FREE_TEXT

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    s = ensure_session(uid)

    if text.startswith("Итоги"):
        await update.message.reply_text("Коротко: итог разговора (1–2 фразы):")
        return WAIT_SUMMARY

    if text.startswith("Тон:"):
        idx = TONES.index(s.tone)
        s.tone = TONES[(idx + 1) % len(TONES)]
        await update.message.reply_text(f"Тон переключён: {s.tone}", reply_markup=top_keyboard(s.tone))
        return WAIT_FREE_TEXT

    if text.startswith("Свободный"):
        await update.message.reply_text("Напишите фразу клиента целиком.")
        return WAIT_FREE_TEXT

    try:
        idx = int(text.split(".")[0]) - 1
        intent, title = SITUATIONS[idx]
    except Exception:
        intent = detect_intent(text)
        title = dict(SITUATIONS).get(intent, intent)

    slots = extract_slots(text)
    reply = compose_reply(intent, s.tone, slots)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Ещё вариант", callback_data=f"more:{intent}")],
        [InlineKeyboardButton("Итоги разговора", callback_data="summary")],
        [InlineKeyboardButton("Тон ⟳", callback_data="tone")],
    ])

    s.entries.append({"client": text, "intent": intent, "reply": reply})
    await update.message.reply_text(f"<b>{title}</b>\n\n{reply}", parse_mode="HTML", reply_markup=kb)
    return WAIT_FREE_TEXT

async def handle_free(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    s = ensure_session(uid)

    intent = detect_intent(text)
    slots = extract_slots(text)
    reply = compose_reply(intent, s.tone, slots)
    title = dict(SITUATIONS).get(intent, intent)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Ещё вариант", callback_data=f"more:{intent}")],
        [InlineKeyboardButton("Итоги разговора", callback_data="summary")],
        [InlineKeyboardButton("Тон ⟳", callback_data="tone")],
    ])

    s.entries.append({"client": text, "intent": intent, "reply": reply})
    await update.message.reply_text(f"<b>{title}</b>\n\n{reply}", parse_mode="HTML", reply_markup=kb)
    return WAIT_FREE_TEXT

async def on_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    s = ensure_session(uid)

    if q.data.startswith("more:"):
        intent = q.data.split(":",1)[1]
        # Возьмём слоты из последнего совпадающего запроса
        slots = {}
        for e in reversed(s.entries):
            if e["intent"] == intent:
                slots = extract_slots(e["client"]); break
        reply = compose_reply(intent, s.tone, slots)
        await q.edit_message_text(reply)
        return

    if q.data == "tone":
        idx = TONES.index(s.tone)
        s.tone = TONES[(idx + 1) % len(TONES)]
        await q.edit_message_text(f"Тон переключён: {s.tone}")
        return

    if q.data == "summary":
        await q.edit_message_text("Коротко: итог разговора (1–2 фразы):")
        return WAIT_SUMMARY

async def build_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s = ensure_session(uid)
    summary = update.message.text.strip()

    ts = int(time.time())
    last = s.entries[-5:]
    entries_text = parts = []
for e in last:
    clean_reply = e['reply'].replace("\n", " ")
    parts.append(f"[{e['intent']}] {e['client']} => {clean_reply}")
entries_text = " || ".join(parts)

    row = {"timestamp": ts, "agent_id": uid, "summary": summary, "entries": entries_text}
    file_exists = os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists: writer.writeheader()
        writer.writerow(row)

    await update.message.reply_text("Готово. Конспект сохранён. Продолжим? /start", reply_markup=top_keyboard(s.tone))
    return WAIT_FREE_TEXT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ок, вернёмся позже. Наберите /start, чтобы продолжить.")
    return ConversationHandler.END

# ===== main =====

def main():
    if not BOT_TOKEN:
        raise RuntimeError("Установите BOT_TOKEN в .env или в Environment Variables")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAIT_FREE_TEXT: [
                MessageHandler(filters.Regex("^(Итоги разговора)$"), handle_menu),
                MessageHandler(filters.Regex("^(Свободный ввод фразы клиента)$"), handle_menu),
                MessageHandler(filters.Regex("^([1-9]|10)\..*"), handle_menu),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free),
            ],
            WAIT_SUMMARY: [MessageHandler(filters.TEXT & ~filters.COMMAND, build_summary)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(on_cb))

    print("Skriptolog v4 запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()

