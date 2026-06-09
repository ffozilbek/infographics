"""
Marketplace Infografik Bot v11
==============================
Yangi: Tariflar, Balans, Namunalar tugmalari
/start — faqat til tanlash
Tariflar — pastdagi tugmadan
"""

import os
import io
import re
import base64
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from prompts import (
    analyze_product, check_copyright,
    get_infographic_prompt_system, write_infographic_prompt,
    write_promo_prompts,
    gen_infographics_parallel, gen_promos_parallel,
    gen_card_step1, gen_card_step2,
    set_client as set_prompts_client,
)
from aiogram import Bot, Dispatcher, Router, types, F, BaseMiddleware
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    BufferedInputFile, InputMediaPhoto, FSInputFile,
    InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton, BotCommand,
)
from aiogram.enums import ParseMode
from openai import OpenAI
from PIL import Image
from aiohttp import web
import payment
import database as db

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LOG_CHAT_ID = os.getenv("LOG_CHAT_ID", "")      # Log kanal ID (-100xxxxxxxxxx)
ARCHIVE_CHAT_ID = os.getenv("ARCHIVE_CHAT_ID", "")  # Arxiv kanal ID (-100xxxxxxxxxx)
if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
    raise ValueError("TELEGRAM_BOT_TOKEN va OPENAI_API_KEY .env faylda bo'lishi kerak!")

# Asosiy papka (bot.py joylashgan joy)
BASE_DIR = Path(__file__).parent
TARIFF_IMAGE = BASE_DIR / "images" / "tarif.jpg"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)
set_prompts_client(client)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
router = Router()
executor = ThreadPoolExecutor(max_workers=4)
user_tasks = {}

# ── Sozlamalar cache (DB ga har safar murojaat qilmaslik uchun) ──
_settings_cache: dict[int, dict] = {}
_tariffs_cache: list = []  # DB dan yuklangan tariflar

async def get_settings(uid: int) -> dict:
    if uid not in _settings_cache:
        _settings_cache[uid] = await db.get_user_settings(uid)
    return _settings_cache[uid]

async def set_setting(uid: int, field: str, value):
    await db.set_user_setting(uid, field, value)
    if uid in _settings_cache:
        _settings_cache[uid][field] = value
    else:
        _settings_cache[uid] = await db.get_user_settings(uid)

async def load_tariffs():
    """DB dan tariflarni yuklash"""
    global _tariffs_cache
    _tariffs_cache = await db.get_all_tariffs()
    logger.info(f"Tariflar yuklandi: {len(_tariffs_cache)} ta")

def get_tariff_price(tariff_id: int) -> int:
    for t in _tariffs_cache:
        if t["tariff_id"] == tariff_id:
            return t["price"]
    return {1: 7000, 2: 12000, 3: 17000, 4: 25000}.get(tariff_id, 0)

def get_tariff_name(tariff_id: int, lang: str = "uz") -> str:
    for t in _tariffs_cache:
        if t["tariff_id"] == tariff_id:
            return t[f"name_{lang}"]
    return {1: "Infografika", 2: "Infografika + Matn",
            3: "Infografika + Reklama", 4: "To'liq paket"}.get(tariff_id, "")

def get_active_tariffs() -> list:
    return [t for t in _tariffs_cache if t.get("is_active", True)]

async def get_tariff_keyboard() -> InlineKeyboardMarkup:
    """DB dan tarif nomlar va narxlar bilan keyboard"""
    tariffs = get_active_tariffs()
    emojis = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣"}
    buttons = []
    for t in tariffs:
        tid = t["tariff_id"]
        emoji = emojis.get(tid, "🔹")
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {t['name_uz']} — {t['price']:,} so'm",
            callback_data=f"tariff_{tid}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ══════════════════════════════════════════════════════════════════
# TILLAR
# ══════════════════════════════════════════════════════════════════

ADMIN_USERNAME = "karimovsherali"

TEXTS = {
    "uz": {
        "welcome": (
            "🎨 <b>Marketplace Infografik Bot</b>\n\n"
            "🇺🇿 Bu bot mahsulot rasmini professional infografik rasmga aylantiradi.\n"
            "🇷🇺 Этот бот превращает фото товара в профессиональную инфографику.\n\n"
            "Tilni tanlang / Выберите язык 👇"
        ),
        "choose_text_lang": "📝 Infografik va matnlar qaysi tilda bo'lsin?",
        "lang_done": "✅ <b>Til saqlandi!</b>\n\n📸 Endi mahsulot rasmini yuboring yoki pastdagi tugmalardan foydalaning.",
        "choose_tariff": "📦 <b>Tarifni tanlang:</b>",
        "tariff_set": "✅ <b>Tarif tanlandi: {name}</b>\n💰 Narxi: <b>{price} so'm</b>",
        "busy": "⏳ Oldingi rasmingiz hali tayyor bo'lmadi. Kuting...",
        "error": "❌ <b>Xatolik yuz berdi</b>",
        "error_billing": "🪲 Texnik xatolik yuz berdi. Adminlar buni tez orada to'g'irlaydi. Nosozlik uchun uzr so'raymiz!",
        "error_rate": "⏱ Juda ko'p so'rov. 1 daqiqadan keyin urinib ko'ring.",
        "error_safety": "🚫 Rasm safety filtriga tushdi. Boshqa rasm yuboring.",
        "error_copyright": "⚠️ <b>Litsenziyalangan personaj aniqlandi:</b> <code>{keyword}</code>\n\nBoshqa rasm yuboring.",
        "error_no_tariff": "⚠️ Avval tarifni tanlang! Pastdagi 📦 <b>Tariflar</b> tugmasini bosing.",
        "help": (
            "📖 <b>Yordam</b>\n\n"
            "🔹 📦 <b>Tariflar</b> — tarif tanlash\n"
            "🔹 💰 <b>Balans</b> — balansingizni ko'rish\n"
            "🔹 📋 <b>Namunalar</b> — namuna rasmlarni ko'rish\n"
            "🔹 🌐 <b>Tilni o'zgartirish</b>\n\n"
            "📸 Mahsulot rasmini yuboring — bot ishlaydi!\n\n"
             f"🆘 Yordam kerak bo'lsa <a href='https://t.me/{ADMIN_USERNAME}'>admin</a> ga yozing."
        ),
        "done_infographic": "✅ <b>Infografik rasmlar tayyor!</b>",
        "done_promo": "✅ <b>Tavsif rasmlari tayyor!</b>",
        "done_text": "✅ <b>Kartochka matnlari tayyor!</b>",
        "send_photo": "📸 Menga <b>mahsulot rasmini</b> yuboring!",
        "ready_with_tariff": "✅ <b>Hammasi tayyor!</b>\n\n📦 Joriy tarif: <b>{tariff}</b>\n💰 Narxi: <b>{price} so'm</b>\n\n📸 Mahsulot rasmini yuboring!\n\n💡 Tarifni o'zgartirish — 📦 Tariflar tugmasini bosing.",
        "balance": "💰 <b>Balansingiz:</b> {amount} so'm",
        "balance_topup": "💳 Balansni to'ldirish",
        "balance_topup_soon": "🔜 To'lov tizimi tez orada qo'shiladi!",
        "samples": "📋 <b>Namunalar</b>\n\nKo'rmoqchi bo'lgan tarif namunasini tanlang:",
        "samples_soon": "🔜 Namunalar tez orada qo'shiladi!",
        "tariff_names": {1: "Infografika", 2: "Infografika + Matn", 3: "Infografika + Reklama rasmlar", 4: "To'liq paket"},
        # Buttons
        "btn_tariffs": "📦 Tariflar",
        "btn_balance": "💰 Balans",
        "btn_samples": "📋 Namunalar",
        "btn_settings": "🌐 Tilni o'zgartirish",
        "btn_help": "❓ Yordam",
        # Progress
        "progress": [
            {"bar": "▓▓░░░░░░░░", "pct": "15%", "stage": "🔍 Mahsulot tahlil qilinmoqda..."},
            {"bar": "▓▓▓░░░░░░░", "pct": "25%", "stage": "💡 Professional infografik sotuvni 40% ga oshiradi!"},
            {"bar": "▓▓▓▓▓░░░░░", "pct": "45%", "stage": "📸 AI mahsulotga mos dizayn tanlaydi"},
            {"bar": "▓▓▓▓▓▓░░░░", "pct": "55%", "stage": "🏪 Rasm internet do'konlar standartiga mos bo'ladi"},
            {"bar": "▓▓▓▓▓▓▓░░░", "pct": "70%", "stage": "⏱️ Biroz kuting..."},
            {"bar": "▓▓▓▓▓▓▓▓░░", "pct": "85%", "stage": "📦 Natijalar tayyorlanmoqda..."},
            {"bar": "▓▓▓▓▓▓▓▓▓░", "pct": "95%", "stage": "✅ Deyarli tayyor!"},
        ],
    },
    "ru": {
        "welcome": (
            "🎨 <b>Marketplace Инфографик Бот</b>\n\n"
            "🇺🇿 Bu bot mahsulot rasmini professional infografik rasmga aylantiradi.\n"
            "🇷🇺 Этот бот превращает фото товара в профессиональную инфографику.\n\n"
            "Tilni tanlang / Выберите язык 👇"
        ),
        "choose_text_lang": "📝 На каком языке инфографика и тексты?",
        "lang_done": "✅ <b>Язык сохранён!</b>\n\n📸 Отправьте фото товара или используйте кнопки внизу.",
        "choose_tariff": "📦 <b>Выберите тариф:</b>",
        "tariff_set": "✅ <b>Тариф выбран: {name}</b>\n💰 Стоимость: <b>{price} сум</b>",
        "busy": "⏳ Предыдущее фото обрабатывается...",
        "error": "❌ <b>Произошла ошибка</b>",
        "error_billing": "🪲 Произошла техническая ошибка. Администраторы скоро её исправят. Приносим извинения за неудобства.",
        "error_rate": "⏱ Слишком много запросов.",
        "error_safety": "🚫 Фото заблокировано фильтром.",
        "error_copyright": "⚠️ <b>Лицензированный персонаж:</b> <code>{keyword}</code>",
        "error_no_tariff": "⚠️ Сначала выберите тариф! Нажмите 📦 <b>Тарифы</b> внизу.",
        "help": (
            "📖 <b>Помощь</b>\n\n"
            "🔹 📦 <b>Тарифы</b> — выбрать тариф\n"
            "🔹 💰 <b>Баланс</b> — проверить баланс\n"
            "🔹 📋 <b>Примеры</b> — посмотреть примеры\n"
            "🔹 🌐 <b>Сменить язык</b>\n\n"
            "📸 Отправьте фото товара — бот начнёт работу!\n\n"
             f"🆘 Если вам нужна помощь, напишите <a href='https://t.me/{ADMIN_USERNAME}'>администратору</a>."
        ),
        "done_infographic": "✅ <b>Инфографика готова!</b>",
        "done_promo": "✅ <b>Рекламные фото готовы!</b>",
        "done_text": "✅ <b>Тексты для карточки готовы!</b>",
        "send_photo": "📸 Отправьте <b>фото товара</b>!",
        "ready_with_tariff": "✅ <b>Всё готово!</b>\n\n📦 Текущий тариф: <b>{tariff}</b>\n💰 Стоимость: <b>{price} сум</b>\n\n📸 Отправьте фото товара!\n\n💡 Сменить тариф — кнопка 📦 Тарифы.",
        "balance": "💰 <b>Ваш баланс:</b> {amount} сум",
        "balance_topup": "💳 Пополнить баланс",
        "balance_topup_soon": "🔜 Система оплаты будет добавлена скоро!",
        "samples": "📋 <b>Примеры</b>\n\nВыберите тариф для просмотра примера:",
        "samples_soon": "🔜 Примеры будут добавлены скоро!",
        "tariff_names": {1: "Инфографика", 2: "Инфографика + Текст", 3: "Инфографика + Рекл. фото", 4: "Полный пакет"},
        "btn_tariffs": "📦 Тарифы",
        "btn_balance": "💰 Баланс",
        "btn_samples": "📋 Примеры",
        "btn_settings": "🌐 Сменить язык",
        "btn_help": "❓ Помощь",
        "progress": [
            {"bar": "▓▓░░░░░░░░", "pct": "15%", "stage": "🔍 Анализ товара..."},
            {"bar": "▓▓▓░░░░░░░", "pct": "25%", "stage": "💡 Инфографика увеличивает продажи на 40%!"},
            {"bar": "▓▓▓▓▓░░░░░", "pct": "45%", "stage": "📸 ИИ подбирает подходящий дизайн"},
            {"bar": "▓▓▓▓▓▓░░░░", "pct": "55%", "stage": "🏪 Фото соответствует стандартам маркетплейсов"},
            {"bar": "▓▓▓▓▓▓▓░░░", "pct": "70%", "stage": "⏱️ Подождите немного..."},
            {"bar": "▓▓▓▓▓▓▓▓░░", "pct": "85%", "stage": "📦 Подготовка результатов..."},
            {"bar": "▓▓▓▓▓▓▓▓▓░", "pct": "95%", "stage": "✅ Почти готово!"},
        ],
    },
}

def t(settings: dict, key, **kw):
    """settings dict bilan ishlatiladi (await get_settings(uid) natijasi)"""
    lang = settings.get("ui_lang", "uz")
    txt = TEXTS.get(lang, TEXTS["uz"]).get(key, key)
    return txt.format(**kw) if isinstance(txt, str) and kw else txt

def t_uid(uid, key, **kw):
    """Cache dan sync o'qish (faqat cache to'ldirilgan bo'lsa)"""
    settings = _settings_cache.get(uid, {"ui_lang": "uz"})
    return t(settings, key, **kw)

def get_progress(settings: dict, step):
    lang = settings.get("ui_lang", "uz")
    stages = TEXTS.get(lang, TEXTS["uz"])["progress"]
    s = stages[min(step, len(stages)-1)]
    tariff = settings.get("tariff", 0)
    tariff_name = get_tariff_name(tariff, lang)
    price = get_tariff_price(tariff)
    tip = s.get("tip", "")
    tip_line = f"\n\n{tip}" if tip else ""
    return f"🎨 <b>Ishlanmoqda</b>  |  📦 {tariff_name} ({price:,} so'm)\n\n{s['bar']}  {s['pct']}\n\n{s['stage']}{tip_line}"

def get_reply_keyboard(settings: dict):
    lang = settings.get("ui_lang", "uz")
    tx = TEXTS.get(lang, TEXTS["uz"])
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=tx["btn_tariffs"]), KeyboardButton(text=tx["btn_balance"]), KeyboardButton(text=tx["btn_samples"])],
        [KeyboardButton(text=tx["btn_settings"]), KeyboardButton(text=tx["btn_help"])],
    ], resize_keyboard=True)


# ══════════════════════════════════════════════════════════════════
# TAHLIL
# ══════════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════════
# YORDAMCHILAR
# ══════════════════════════════════════════════════════════════════

async def tg_log(text: str):
    """Kanal/gruppaga log yuborish"""
    if not LOG_CHAT_ID:
        return
    try:
        await bot.send_message(
            chat_id=int(LOG_CHAT_ID),
            text=text,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"tg_log xatolik: {e}")


class LoggingMiddleware(BaseMiddleware):
    """Barcha xabar va callback larni kanalga yozadi"""

    async def __call__(self, handler, event, data):
        try:
            user = None
            text_info = ""

            if isinstance(event, types.Message):
                user = event.from_user
                if event.text:
                    text_info = f"💬 <b>Xabar:</b> {event.text[:80]}"
                elif event.photo:
                    text_info = "🖼 <b>Rasm yuborildi</b>"
                elif event.document:
                    text_info = "📎 <b>Fayl yuborildi</b>"
                else:
                    text_info = "📨 <b>Boshqa turdagi xabar</b>"

            elif isinstance(event, types.CallbackQuery):
                user = event.from_user
                text_info = f"🔘 <b>Tugma:</b> <code>{event.data}</code>"

            if user and text_info:
                uid = user.id
                name = user.full_name or user.username or "—"
                uname = f"@{user.username}" if user.username else "username yo'q"
                await tg_log(
                    f"{text_info}\n"
                    f"👤 {name} ({uname})\n"
                    f"🆔 <code>{uid}</code>"
                )
        except Exception as e:
            logger.warning(f"LoggingMiddleware xatolik: {e}")

        return await handler(event, data)


async def tg_archive_photo(photo_file_id: str, caption: str = ""):
    """Arxiv kanalga rasm yuborish"""
    if not ARCHIVE_CHAT_ID:
        return
    try:
        await bot.send_photo(
            chat_id=int(ARCHIVE_CHAT_ID),
            photo=photo_file_id,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"tg_archive_photo xatolik: {e}")


async def tg_archive_bytes(image_bytes: bytes, filename: str, caption: str = ""):
    """Arxiv kanalga bytes dan rasm yuborish"""
    if not ARCHIVE_CHAT_ID:
        return
    try:
        await bot.send_photo(
            chat_id=int(ARCHIVE_CHAT_ID),
            photo=BufferedInputFile(file=image_bytes, filename=filename),
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"tg_archive_bytes xatolik: {e}")


async def tg_archive_text(text: str):
    """Arxiv kanalga matn yuborish"""
    if not ARCHIVE_CHAT_ID:
        return
    try:
        await bot.send_message(
            chat_id=int(ARCHIVE_CHAT_ID),
            text=text,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"tg_archive_text xatolik: {e}")


async def update_progress(wait_msg, uid, stop):
    step = 0
    while not stop.is_set():
        try:
            settings = await get_settings(uid)
            await wait_msg.edit_text(get_progress(settings, step), parse_mode=ParseMode.HTML)
        except: pass
        step += 1
        try: await asyncio.wait_for(stop.wait(), timeout=7); break
        except asyncio.TimeoutError: continue

async def send_long(chat_id, text, parse_mode=ParseMode.HTML):
    MAX = 4000
    if len(text) <= MAX:
        try:
            await bot.send_message(chat_id, text, parse_mode=parse_mode)
        except Exception as e:
            logger.warning(f"send_long HTML error: {e}")
            # HTML teglarni tozalab qayta yuborish
            clean = re.sub(r'<[^>]+>', '', text)
            await bot.send_message(chat_id, clean)
        return

    chunks = []
    while text:
        if len(text) <= MAX:
            chunks.append(text)
            break
        # Ajratish joyini topish — teglar ichida bo'lmasligi uchun
        cut = text.rfind('\n\n', 0, MAX)
        if cut == -1:
            cut = text.rfind('\n', 0, MAX)
        if cut == -1:
            cut = MAX
        chunks.append(text[:cut])
        text = text[cut:].lstrip('\n')

    for chunk in chunks:
        # Ochilgan <pre> teglarni yopish
        open_pre = chunk.count('<pre>') - chunk.count('</pre>')
        if open_pre > 0:
            chunk += '</pre>' * open_pre
        # Yopilgan <pre> tegi boshida — ochish
        close_pre = chunk.count('</pre>') - chunk.count('<pre>')
        if close_pre > 0:
            chunk = '<pre>' * close_pre + chunk

        try:
            await bot.send_message(chat_id, chunk, parse_mode=parse_mode)
        except Exception as e:
            logger.warning(f"send_long chunk error: {e}")
            clean = re.sub(r'<[^>]+>', '', chunk)
            await bot.send_message(chat_id, clean)

async def send_images(message, variants, label, prefix="v"):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S'); uid = message.from_user.id
    if len(variants) >= 2:
        mg = [
            InputMediaPhoto(media=BufferedInputFile(file=variants[0], filename=f"{prefix}1_{uid}_{ts}.jpg"), caption=label, parse_mode=ParseMode.HTML),
            InputMediaPhoto(media=BufferedInputFile(file=variants[1], filename=f"{prefix}2_{uid}_{ts}.jpg")),
        ]
        await message.answer_media_group(media=mg)
    elif variants:
        await message.answer_photo(photo=BufferedInputFile(file=variants[0], filename=f"{prefix}_{uid}_{ts}.jpg"), caption=label, parse_mode=ParseMode.HTML)
    settings = await get_settings(uid)
    dl = "💾 Yuklab olish" if settings.get("ui_lang") == "uz" else "💾 Скачать"
    for i, v in enumerate(variants):
        await message.answer_document(document=BufferedInputFile(file=v, filename=f"{prefix}_{i+1}_{uid}_{ts}.jpg"), caption=f"{dl} {i+1}")

async def send_card_texts(message, card, full_uz, full_ru):
    uid = message.from_user.id
    settings = await get_settings(uid)
    lang = settings.get("ui_lang", "uz")

    def clean(t):
        t = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', t)
        t = re.sub(r'^#{1,6}\s*', '', t, flags=re.MULTILINE)
        return t

    def clean_feat(t):
        t = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', t)
        t = re.sub(r'^-\s+', '', t, flags=re.MULTILINE)
        t = re.sub(r'^#{1,6}\s*', '', t, flags=re.MULTILINE)
        return t

    feat_uz = [l.strip() for l in clean_feat(card['feat_uz']).split('\n') if l.strip()]
    feat_ru = [l.strip() for l in clean_feat(card['feat_ru']).split('\n') if l.strip()]
    full_uz, full_ru = clean(full_uz), clean(full_ru)

    if lang == "uz":
        n,s,d,f = "1. Tovar nomi","2. Tovar qisqacha tavsifi","3. Tovar tavsifi","4. Tovar xususiyatlari"
    else:
        n,s,d,f = "1. Название товара","2. Краткое описание товара","3. Описание товара","4. Характеристики товара"

    msg1 = (f"{t(settings,'done_text')}\n\n📌 <b>{n}</b>\n\n"
            f"🇺🇿 ({len(card['name_uz'])} belgi):\n<pre>{card['name_uz']}</pre>\n"
            f"🇷🇺 ({len(card['name_ru'])} belgi):\n<pre>{card['name_ru']}</pre>\n\n"
            f"📝 <b>{s}</b>\n\n"
            f"🇺🇿 ({len(card['short_uz'])} belgi):\n<pre>{card['short_uz']}</pre>\n"
            f"🇷🇺 ({len(card['short_ru'])} belgi):\n<pre>{card['short_ru']}</pre>")
    await send_long(message.chat.id, msg1)
    await send_long(message.chat.id, f"📄 <b>{d}</b>\n\n🇺🇿 ({len(full_uz)} belgi):\n<pre>{full_uz}</pre>")
    await send_long(message.chat.id, f"🇷🇺 ({len(full_ru)} belgi):\n<pre>{full_ru}</pre>")

    feat_msg = f"🏷 <b>{f}</b>\n\n🇺🇿:\n\n"
    for line in feat_uz: feat_msg += f"<pre>{line}</pre>\n"
    feat_msg += "\n🇷🇺:\n\n"
    for line in feat_ru: feat_msg += f"<pre>{line}</pre>\n"
    await send_long(message.chat.id, feat_msg)


# ══════════════════════════════════════════════════════════════════
# TELEGRAM HANDLERLARI
# ══════════════════════════════════════════════════════════════════

# ── /start — faqat til tanlash ───────────────────────────────────
@router.message(CommandStart())
async def cmd_start(msg: types.Message):
    uid = msg.from_user.id
    settings = await get_settings(uid)
    # Yangi user bo'lsa log
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT created_at, updated_at FROM users WHERE user_id=$1", uid)
    is_new = row is None or (row["created_at"] and row["updated_at"] and
             abs((row["updated_at"] - row["created_at"]).total_seconds()) < 5)
    await db.ensure_user(uid, username=msg.from_user.username, full_name=msg.from_user.full_name)
    if is_new:
        uname = f"@{msg.from_user.username}" if msg.from_user.username else "username yo'q"
        name = msg.from_user.full_name or "—"
        await tg_log(
            f"👤 <b>Yangi foydalanuvchi</b>\n"
            f"ID: <code>{uid}</code>\n"
            f"Ism: {name}\n"
            f"Username: {uname}"
        )
    # Til allaqachon tanlangan bo'lsa — to'g'ridan-to'g'ri reply keyboard
    if settings.get("ui_lang") and settings.get("text_lang"):
        lang = settings.get("ui_lang", "uz")
        tariff = settings.get("tariff", 0)
        if tariff:
            tariff_name = get_tariff_name(tariff, lang)
            price = get_tariff_price(tariff)
            if lang == "uz":
                tariff_line = f"\n📦 Joriy tarif: <b>{tariff_name}</b> — {price:,} so'm"
            else:
                tariff_line = f"\n📦 Текущий тариф: <b>{tariff_name}</b> — {price:,} сум"
        else:
            if lang == "uz":
                tariff_line = "\n⚠️ Tarif tanlanmagan — 📦 Tariflar tugmasini bosing"
            else:
                tariff_line = "\n⚠️ Тариф не выбран — нажмите 📦 Тарифы"

        first_name = msg.from_user.first_name or msg.from_user.username or ""
        name_part = f", {first_name}" if first_name else ""
        if lang == "uz":
            greet = f"👋 <b>Xush kelibsiz{name_part}!</b>{tariff_line}\n\n📸 Mahsulot rasmini yuboring yoki tugmalardan foydalaning."
        else:
            greet = f"👋 <b>Добро пожаловать{name_part}!</b>{tariff_line}\n\n📸 Отправьте фото товара или используйте кнопки."
        await msg.answer(greet, parse_mode=ParseMode.HTML, reply_markup=get_reply_keyboard(settings))
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_ui_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ui_ru"),
    ]])
    await msg.answer(t(settings, "welcome"), parse_mode=ParseMode.HTML, reply_markup=kb)

@router.callback_query(F.data.startswith("lang_ui_"))
async def cb_ui(cb: CallbackQuery):
    uid = cb.from_user.id
    await set_setting(uid, "ui_lang", cb.data.replace("lang_ui_", ""))
    await cb.answer()
    settings = await get_settings(uid)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_text_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_text_ru"),
    ]])
    await cb.message.edit_text(t(settings, "choose_text_lang"), parse_mode=ParseMode.HTML, reply_markup=kb)

@router.callback_query(F.data.startswith("lang_text_"))
async def cb_text(cb: CallbackQuery):
    uid = cb.from_user.id
    # DB dan to'g'ridan-to'g'ri tekshirish (cache xato berishi mumkin)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        db_row = await conn.fetchrow("SELECT text_lang FROM users WHERE user_id=$1", uid)
    is_first_setup = db_row is None or not db_row["text_lang"]
    await set_setting(uid, "text_lang", cb.data.replace("lang_text_", ""))
    await cb.answer()

    settings = await get_settings(uid)
    chat_id = cb.message.chat.id
    lang = settings.get("ui_lang", "uz")

    try:
        await cb.message.delete()
    except Exception:
        pass

    # Birinchi marta kirgan bo'lsa — welcome bonus
    if is_first_setup:
        bonus = get_tariff_price(1)  # 1-tarif narxi
        await db.add_balance(uid, bonus, "welcome_bonus")
        name = (cb.from_user.first_name or cb.from_user.username or "Foydalanuvchi").strip()
        if lang == "uz":
            bonus_text = (
                f"🎉 <b>Xush kelibsiz, {name}!</b>\n\n"
                f"🎁 Sizga <b>{bonus:,} so'm</b> sovg'a berildi!\n"
                f"Bu 1 ta infografik yaratish uchun yetarli.\n\n"
                f"📸 Mahsulot rasmini yuboring va sinab ko'ring!"
            )
        else:
            bonus_text = (
                f"🎉 <b>Добро пожаловать, {name}!</b>\n\n"
                f"🎁 Вам подарено <b>{bonus:,} сум</b>!\n"
                f"Этого хватит на 1 инфографику.\n\n"
                f"📸 Отправьте фото товара и попробуйте!"
            )
        await bot.send_message(chat_id=chat_id, text=bonus_text,
                               parse_mode=ParseMode.HTML,
                               reply_markup=get_reply_keyboard(settings))
    else:
        if lang == "uz":
            ready_text = "✅ <b>Til saqlandi!</b>\n\nQuyidagi tugmalardan foydalaning."
        else:
            ready_text = "✅ <b>Язык сохранён!</b>\n\nИспользуйте кнопки ниже."
        await bot.send_message(chat_id=chat_id, text=ready_text,
                               parse_mode=ParseMode.HTML,
                               reply_markup=get_reply_keyboard(settings))

    # Keyin tarif tanlash inline keyboard
    tariff_kb = await get_tariff_keyboard()
    if TARIFF_IMAGE.exists():
        try:
            img = Image.open(TARIFF_IMAGE)
            if max(img.size) > 1280:
                img.thumbnail((1280, 1280), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=90)
                buf.seek(0)
                photo_file = BufferedInputFile(file=buf.read(), filename="tarif.jpg")
            else:
                photo_file = FSInputFile(TARIFF_IMAGE)
        except Exception:
            photo_file = FSInputFile(TARIFF_IMAGE)

        await bot.send_photo(
            chat_id=chat_id,
            photo=photo_file,
            caption=t(settings, "choose_tariff"),
            parse_mode=ParseMode.HTML,
            reply_markup=tariff_kb,
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=t(settings, "choose_tariff"),
            parse_mode=ParseMode.HTML,
            reply_markup=tariff_kb,
        )


# ── 📦 Tariflar ─────────────────────────────────────────────────
@router.message(F.text.in_(["📦 Tariflar", "📦 Тарифы"]))
async def btn_tariffs(msg: types.Message):
    uid = msg.from_user.id
    tariff_kb = await get_tariff_keyboard()
    if TARIFF_IMAGE.exists():
        try:
            img = Image.open(TARIFF_IMAGE)
            if max(img.size) > 1280:
                img.thumbnail((1280, 1280), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=90)
                buf.seek(0)
                photo_file = BufferedInputFile(file=buf.read(), filename="tarif.jpg")
            else:
                photo_file = FSInputFile(TARIFF_IMAGE)
        except Exception:
            photo_file = FSInputFile(TARIFF_IMAGE)
        await msg.answer_photo(photo=photo_file, caption=t(await get_settings(uid), "choose_tariff"), parse_mode=ParseMode.HTML, reply_markup=tariff_kb)
    else:
        await msg.answer(t(await get_settings(uid), "choose_tariff"), parse_mode=ParseMode.HTML, reply_markup=tariff_kb)

@router.callback_query(F.data.startswith("tariff_"))
async def cb_tariff(cb: CallbackQuery):
    uid = cb.from_user.id
    tariff_num = int(cb.data.replace("tariff_", ""))
    await set_setting(uid, "tariff", tariff_num)
    settings = await get_settings(uid)
    lang = settings.get("ui_lang", "uz")
    tariff_name = get_tariff_name(tariff_num, lang)
    tariff_price = f"{get_tariff_price(tariff_num):,}"
    await cb.answer()

    try:
        await cb.message.edit_caption(
            caption=t(settings, "tariff_set", name=tariff_name, price=tariff_price),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        try:
            await cb.message.edit_text(
                t(settings, "tariff_set", name=tariff_name, price=tariff_price),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await bot.send_message(
                chat_id=cb.message.chat.id,
                text=t(settings, "tariff_set", name=tariff_name, price=tariff_price),
                parse_mode=ParseMode.HTML,
            )

    await bot.send_message(
        chat_id=cb.message.chat.id,
        text=t(settings, "ready_with_tariff", tariff=tariff_name, price=tariff_price),
        parse_mode=ParseMode.HTML,
        reply_markup=get_reply_keyboard(settings),
    )


# ── 💰 Balans ───────────────────────────────────────────────────
# Foydalanuvchi to'ldirish summasi kutilmoqda
user_topup_state = {}  # {uid: True} — summa kutilmoqda

@router.message(F.text.in_(["💰 Balans", "💰 Баланс"]))
async def btn_balance(msg: types.Message):
    uid = msg.from_user.id
    balance = await db.get_balance(uid)
    settings = await get_settings(uid)
    lang = settings.get("ui_lang", "uz")

    if lang == "uz":
        text = f"💰 <b>Balansingiz:</b> {balance:,} so'm"
    else:
        text = f"💰 <b>Ваш баланс:</b> {balance:,} сум"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Balansni to'ldirish" if lang == "uz" else "💳 Пополнить баланс", callback_data="topup_start")],
    ])
    await msg.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(F.data == "topup_start")
async def cb_topup_start(cb: CallbackQuery):
    uid = cb.from_user.id
    settings = await get_settings(uid)
    lang = settings.get("ui_lang", "uz")
    user_topup_state[uid] = True
    await cb.answer()

    if lang == "uz":
        text = "💳 To'ldirish summasini yozing (so'mda):\n\n<i>Masalan: 50000</i>"
    else:
        text = "💳 Введите сумму пополнения (в сумах):\n\n<i>Например: 50000</i>"

    await cb.message.answer(text, parse_mode=ParseMode.HTML)


# ── 📋 Namunalar ────────────────────────────────────────────────
@router.message(F.text.in_(["📋 Namunalar", "📋 Примеры"]))
async def btn_samples(msg: types.Message):
    uid = msg.from_user.id
    settings = await get_settings(uid)
    lang = settings.get("ui_lang", "uz")
    sample_label = "namuna" if lang == "uz" else "пример"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"1️⃣ {get_tariff_name(1, lang)} — {sample_label}", callback_data="sample_1")],
        [InlineKeyboardButton(text=f"2️⃣ {get_tariff_name(2, lang)} — {sample_label}", callback_data="sample_2")],
        [InlineKeyboardButton(text=f"3️⃣ {get_tariff_name(3, lang)} — {sample_label}", callback_data="sample_3")],
        [InlineKeyboardButton(text=f"4️⃣ {get_tariff_name(4, lang)} — {sample_label}", callback_data="sample_4")],
    ])
    await msg.answer(t(settings, "samples"), parse_mode=ParseMode.HTML, reply_markup=kb)

@router.callback_query(F.data.startswith("sample_"))
async def cb_sample(cb: CallbackQuery):
    uid = cb.from_user.id
    tariff_num = int(cb.data.replace("sample_", ""))
    settings = await get_settings(uid)
    lang = settings.get("ui_lang", "uz")
    await cb.answer()

    samples_dir = BASE_DIR / "images" / "samples"
    sample_images = sorted(samples_dir.glob(f"tarif{tariff_num}_*.jpg"))

    if not sample_images:
        no_sample = "🔜 Bu tarif uchun namunalar hali qo'shilmagan." if lang == "uz" else "🔜 Примеры для этого тарифа ещё не добавлены."
        await cb.message.answer(no_sample)
        return

    if len(sample_images) >= 2:
        media = [
            InputMediaPhoto(
                media=FSInputFile(sample_images[0]),
                caption=f"📋 {'Namuna' if lang == 'uz' else 'Пример'} — {get_tariff_name(tariff_num, lang)}",
                parse_mode=ParseMode.HTML,
            ),
        ]
        for img in sample_images[1:4]:
            media.append(InputMediaPhoto(media=FSInputFile(img)))
        await cb.message.answer_media_group(media=media)
    else:
        await cb.message.answer_photo(
            photo=FSInputFile(sample_images[0]),
            caption=f"📋 {'Namuna' if lang == 'uz' else 'Пример'} — {get_tariff_name(tariff_num, lang)}",
            parse_mode=ParseMode.HTML,
        )

    from samples import get_sample_messages
    messages = get_sample_messages(tariff_num)
    if messages:
        for msg_text in messages:
            await send_long(cb.message.chat.id, msg_text)


# ── ⚙️ Sozlamalar ───────────────────────────────────────────────
@router.message(F.text.in_(["🌐 Tilni o'zgartirish", "🌐 Сменить язык"]))
async def btn_settings(msg: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_ui_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ui_ru"),
    ]])
    await msg.answer("🌐 Tilni tanlang / Выберите язык:", reply_markup=kb)

@router.message(Command("settings"))
async def cmd_settings(msg: types.Message): await btn_settings(msg)

# ── ❓ Yordam ────────────────────────────────────────────────────
@router.message(F.text.in_(["❓ Yordam", "❓ Помощь"]))
async def btn_help(msg: types.Message):
    settings = await get_settings(msg.from_user.id)
    await msg.answer(t(settings, "help"), parse_mode=ParseMode.HTML)

@router.message(Command("help"))
async def cmd_help(msg: types.Message):
    settings = await get_settings(msg.from_user.id)
    await msg.answer(t(settings, "help"), parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════
# ASOSIY: Rasm qabul qilish
# ══════════════════════════════════════════════════════════════════

@router.message(F.photo)
async def handle_photo(message: types.Message):
    uid = message.from_user.id
    settings = await get_settings(uid)

    # Til tekshiruv
    if not settings.get("text_lang"):
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_ui_uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ui_ru"),
        ]])
        await message.answer("⚙️ Avval tilni tanlang:", reply_markup=kb)
        return

    # Tarif tekshiruv
    tariff = settings.get("tariff", 0)
    if tariff == 0:
        await message.answer(t(settings, "error_no_tariff"), parse_mode=ParseMode.HTML)
        return

    lang = settings.get("ui_lang", "uz")
    tariff_name = get_tariff_name(tariff, lang)
    price = get_tariff_price(tariff)
    balance = await db.get_balance(uid)

    # Tasdiqlash — qaysi tarif va narx
    if lang == "uz":
        confirm_text = (
            f"📦 <b>Tarif:</b> {tariff_name}\n"
            f"💰 <b>Narxi:</b> {price:,} so'm\n"
            f"💳 <b>Balansingiz:</b> {balance:,} so'm\n\n"
            f"Davom etish uchun <b>Boshlash</b> ni bosing."
        )
        confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Boshlash", callback_data=f"confirm_photo_{message.message_id}")],
            [InlineKeyboardButton(text="📦 Tarifni almashtirish", callback_data="change_tariff_from_photo")],
        ])
    else:
        confirm_text = (
            f"📦 <b>Тариф:</b> {tariff_name}\n"
            f"💰 <b>Стоимость:</b> {price:,} сум\n"
            f"💳 <b>Ваш баланс:</b> {balance:,} сум\n\n"
            f"Нажмите <b>Начать</b> для продолжения."
        )
        confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Начать", callback_data=f"confirm_photo_{message.message_id}")],
            [InlineKeyboardButton(text="📦 Сменить тариф", callback_data="change_tariff_from_photo")],
        ])

    # Photo file_id ni saqlash (confirm kelganda ishlatish uchun)
    photo_file_id = message.photo[-1].file_id
    user_tasks[f"pending_{uid}"] = photo_file_id

    await message.answer(confirm_text, parse_mode=ParseMode.HTML, reply_markup=confirm_kb)
    return


@router.callback_query(F.data == "change_tariff_from_photo")
async def cb_change_tariff_from_photo(cb: CallbackQuery):
    uid = cb.from_user.id
    user_tasks.pop(f"pending_{uid}", None)
    await cb.answer()
    await cb.message.delete()
    tariff_kb = await get_tariff_keyboard()
    settings = await get_settings(uid)
    if TARIFF_IMAGE.exists():
        try:
            img = Image.open(TARIFF_IMAGE)
            if max(img.size) > 1280:
                img.thumbnail((1280, 1280), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=90)
                buf.seek(0)
                photo_file = BufferedInputFile(file=buf.read(), filename="tarif.jpg")
            else:
                photo_file = FSInputFile(TARIFF_IMAGE)
        except Exception:
            photo_file = FSInputFile(TARIFF_IMAGE)
        await cb.message.answer_photo(photo=photo_file, caption=t(settings, "choose_tariff"),
                                      parse_mode=ParseMode.HTML, reply_markup=tariff_kb)
    else:
        await cb.message.answer(t(settings, "choose_tariff"),
                                parse_mode=ParseMode.HTML, reply_markup=tariff_kb)


@router.callback_query(F.data.startswith("confirm_photo_"))
async def cb_confirm_photo(cb: CallbackQuery):
    uid = cb.from_user.id
    photo_file_id = user_tasks.pop(f"pending_{uid}", None)
    if not photo_file_id:
        await cb.answer("Rasm topilmadi, qayta yuboring." if (await get_settings(uid)).get("ui_lang") == "uz" else "Фото не найдено, отправьте снова.")
        await cb.message.delete()
        return
    await cb.answer()
    await cb.message.delete()

    # Fake message yaratib handle_photo_process chaqirish
    settings = await get_settings(uid)
    lang = settings.get("ui_lang", "uz")
    tariff = settings.get("tariff", 0)
    price = get_tariff_price(tariff)
    balance = await db.get_balance(uid)

    # Balans tekshiruv
    if balance < price:
        if lang == "uz":
            text = (
                f"❌ <b>Balans yetarli emas!</b>\n\n"
                f"💰 Narxi: <b>{price:,} so'm</b>\n"
                f"💳 Balansingiz: <b>{balance:,} so'm</b>\n"
                f"💰 Yetishmaydi: <b>{price - balance:,} so'm</b>"
            )
        else:
            text = (
                f"❌ <b>Недостаточно средств!</b>\n\n"
                f"💰 Стоимость: <b>{price:,} сум</b>\n"
                f"💳 Баланс: <b>{balance:,} сум</b>\n"
                f"💰 Не хватает: <b>{price - balance:,} сум</b>"
            )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Balansni to'ldirish" if lang == "uz" else "💳 Пополнить баланс",
                                  callback_data="topup_start")],
        ])
        await cb.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if user_tasks.get(uid):
        await cb.message.answer("⏳ Oldingi rasm hali tayyor bo'lmadi." if lang == "uz" else "⏳ Предыдущее фото обрабатывается.")
        return

    # Rasmni yuklab olish va process qilish
    await process_photo(cb.message, uid, photo_file_id, settings)


async def process_photo(message: types.Message, uid: int, photo_file_id: str, settings: dict):
    """Rasmni qayta ishlash — confirm dan keyin chaqiriladi"""
    lang = settings.get("ui_lang", "uz")
    tariff = settings.get("tariff", 0)
    text_lang = settings.get("text_lang", "ru")
    price = get_tariff_price(tariff)

    if user_tasks.get(uid):
        await message.answer(t(settings, "busy"))
        return

    user_tasks[uid] = True

    stop = asyncio.Event()
    wait_msg = await message.answer(get_progress(settings, 0), parse_mode=ParseMode.HTML)
    progress = asyncio.create_task(update_progress(wait_msg, uid, stop))

    try:
        file = await bot.get_file(photo_file_id)
        raw = await bot.download_file(file.file_path)
        image_bytes = raw.read()
        logger.info(f"Rasm: user={uid}, tariff={tariff}, bytes={len(image_bytes)}")

        # 1. Tahlil
        analysis = analyze_product(image_bytes)
        cr = check_copyright(analysis)
        if cr:
            stop.set(); await progress
            await wait_msg.edit_text(t(settings, "error_copyright", keyword=cr), parse_mode=ParseMode.HTML)
            return

        # 2. Infografik (tariflar 1-4)
        inf_prompt = write_infographic_prompt(analysis, text_lang)
        infographics = await gen_infographics_parallel(image_bytes, inf_prompt)

        # 3. Tavsif rasmlari (tariflar 3, 4)
        promos = []
        if tariff in (3, 4):
            promo_prompts = write_promo_prompts(analysis, text_lang)
            promos = await gen_promos_parallel(image_bytes, promo_prompts)

        # 4. Kartochka matnlari (tariflar 2, 4)
        card = None; full_uz = full_ru = ""
        if tariff in (2, 4):
            card = gen_card_step1(image_bytes, text_lang)
            ctx = f"Tovar: {card['name_uz']}\nXususiyat: {card['feat_uz']}"
            full_uz, full_ru = gen_card_step2(image_bytes, text_lang, ctx)

        stop.set(); await progress

        # Balansdan yechish
        await db.deduct_balance(uid, price)
        if uid in _settings_cache:
            _settings_cache[uid]["balance"] = await db.get_balance(uid)
        new_balance = await db.get_balance(uid)
        logger.info(f"Balans yechildi: user={uid}, -{price}, qoldi={new_balance}")

        # Buyurtma logi
        uname = f"@{message.from_user.username}" if message.from_user.username else "username yo'q"
        await tg_log(
            f"🛒 <b>Yangi buyurtma</b>\n"
            f"👤 User: <code>{uid}</code> ({uname})\n"
            f"📦 Tarif: {get_tariff_name(tariff, 'uz')}\n"
            f"💰 Narx: {price:,} so'm\n"
            f"💳 Qolgan balans: {new_balance:,} so'm"
        )

        try: await wait_msg.delete()
        except: pass

        # ── Arxivga yuborish ─────────────────────────────────────
        uname_str = f"@{message.from_user.username}" if message.from_user.username else str(uid)
        name_str = message.from_user.full_name or uname_str
        tariff_name = get_tariff_name(tariff, "uz")

        # Original rasm
        await tg_archive_photo(
            photo_file_id,
            caption=f"📥 <b>Original rasm</b>\n👤 {name_str} ({uname_str}) | 📦 {tariff_name}"
        )
        # Infografikalar
        for i, img in enumerate(infographics, 1):
            await tg_archive_bytes(img, f"infographic_{uid}_{i}.jpg",
                caption=f"🖼 <b>Infografika {i}</b> | 👤 {name_str}" if i == 1 else "")
        # Promo rasmlar
        for i, img in enumerate(promos, 1):
            await tg_archive_bytes(img, f"promo_{uid}_{i}.jpg",
                caption=f"🎯 <b>Promo {i}</b> | 👤 {name_str}" if i == 1 else "")
        # Kartochka matni
        if card:
            await tg_archive_text(
                f"📝 <b>Kartochka matni</b> | 👤 {name_str} ({uname_str})\n\n"
                f"🇺🇿 <b>Nomi:</b> {card.get('name_uz', '')}\n"
                f"🇷🇺 <b>Название:</b> {card.get('name_ru', '')}\n\n"
                f"🇺🇿 <b>Qisqa tavsif:</b>\n{card.get('short_uz', '')}\n\n"
                f"🇷🇺 <b>Краткое описание:</b>\n{card.get('short_ru', '')}\n\n"
                f"🇺🇿 <b>Xususiyatlar:</b>\n{card.get('feat_uz', '')}\n\n"
                f"🇷🇺 <b>Характеристики:</b>\n{card.get('feat_ru', '')}"
            )

        # Natijalar
        await send_images(message, infographics, t(settings, "done_infographic"), "infographic")
        if promos:
            await send_images(message, promos, t(settings, "done_promo"), "promo")
        if card:
            await send_card_texts(message, card, full_uz, full_ru)

        if lang == "uz":
            fin = (
                f"✅ <b>Tayyor!</b>\n\n"
                f"💰 Yechildi: {price:,} so'm\n"
                f"💰 Qolgan balans: {new_balance:,} so'm\n\n"
                "🔄 Yana rasm yuboring!"
            )
        else:
            fin = (
                f"✅ <b>Готово!</b>\n\n"
                f"💰 Списано: {price:,} сум\n"
                f"💰 Остаток: {new_balance:,} сум\n\n"
                "🔄 Отправьте ещё фото!"
            )
        await message.answer(fin, parse_mode=ParseMode.HTML)

    except Exception as e:
        stop.set(); await progress
        logger.error(f"Xatolik: user={uid}, error={e}")
        await tg_log(
            f"❌ <b>Xatolik</b>\n"
            f"👤 User: <code>{uid}</code>\n"
            f"📦 Tarif: {tariff}\n"
            f"🔴 <code>{str(e)[:300]}</code>"
        )
        err = str(e).lower()
        if "billing" in err or "quota" in err: em = t(settings, "error_billing")
        elif "rate_limit" in err: em = t(settings, "error_rate")
        elif "moderation" in err or "safety" in err: em = t(settings, "error_safety")
        else: em = f"<code>{str(e)[:300]}</code>"
        await wait_msg.edit_text(f"{t(settings, 'error')}\n\n{em}", parse_mode=ParseMode.HTML)

    finally:
        user_tasks.pop(uid, None)


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(msg: types.Message):
    btn_texts = ["📦 Tariflar", "📦 Тарифы", "💰 Balans", "💰 Баланс",
                 "📋 Namunalar", "📋 Примеры", "🌐 Tilni o'zgartirish", "🌐 Сменить язык",
                 "❓ Yordam", "❓ Помощь"]
    if msg.text in btn_texts: return

    uid = msg.from_user.id
    settings = await get_settings(uid)
    lang = settings.get("ui_lang", "uz")

    # To'ldirish summasi kutilmoqda
    if user_topup_state.get(uid):
        user_topup_state.pop(uid, None)

        amount_text = msg.text.strip().replace(" ", "").replace(",", "").replace(".", "")

        if not amount_text.isdigit():
            if lang == "uz":
                await msg.answer("❌ Faqat raqam kiriting.\n\n<i>Masalan: 50000</i>", parse_mode=ParseMode.HTML)
            else:
                await msg.answer("❌ Введите только число.\n\n<i>Например: 50000</i>", parse_mode=ParseMode.HTML)
            return

        amount = int(amount_text)

        if amount < 1000:
            if lang == "uz":
                await msg.answer("❌ Minimal summa: 1,000 so'm", parse_mode=ParseMode.HTML)
            else:
                await msg.answer("❌ Минимальная сумма: 1,000 сум", parse_mode=ParseMode.HTML)
            return

        if amount > 10_000_000:
            if lang == "uz":
                await msg.answer("❌ Maksimal summa: 10,000,000 so'm", parse_mode=ParseMode.HTML)
            else:
                await msg.answer("❌ Максимальная сумма: 10,000,000 сум", parse_mode=ParseMode.HTML)
            return

        pay_url = payment.generate_payment_link(uid, amount)

        if lang == "uz":
            text = (
                f"💳 <b>To'lov:</b> {amount:,} so'm\n\n"
                "Pastdagi tugmani bosib Click orqali to'lang.\n"
                "To'lov muvaffaqiyatli bo'lgandan keyin balansingiz avtomatik to'ldiriladi."
            )
        else:
            text = (
                f"💳 <b>Оплата:</b> {amount:,} сум\n\n"
                "Нажмите кнопку ниже для оплаты через Click.\n"
                "После успешной оплаты баланс пополнится автоматически."
            )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Click orqali to'lash", url=pay_url)],
        ])
        await msg.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    await msg.answer(t(settings, "send_photo"), parse_mode=ParseMode.HTML)

@router.message(F.document)
async def handle_doc(msg: types.Message):
    if msg.document.mime_type and msg.document.mime_type.startswith("image/"):
        await msg.answer("📸 Rasmni oddiy rasm sifatida yuboring!")
    else:
        settings = await get_settings(msg.from_user.id)
        await msg.answer(t(settings, "send_photo"), parse_mode=ParseMode.HTML)


# ── Ishga tushirish ──────────────────────────────────────────────
async def notify_payment(user_id: int, amount: int, new_balance: int):
    """To'lov bo'lganda foydalanuvchiga xabar yuborish"""
    settings = await get_settings(user_id)
    lang = settings.get("ui_lang", "uz")
    if lang == "uz":
        text = (
            f"✅ <b>To'lov qabul qilindi!</b>\n\n"
            f"💰 To'langan: {amount:,} so'm\n"
            f"💰 Joriy balans: {new_balance:,} so'm"
        )
    else:
        text = (
            f"✅ <b>Оплата принята!</b>\n\n"
            f"💰 Оплачено: {amount:,} сум\n"
            f"💰 Текущий баланс: {new_balance:,} сум"
        )
    try:
        await bot.send_message(user_id, text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Payment notify error: {e}")

    # To'lov logi
    await tg_log(
        f"💳 <b>To'lov keldi</b>\n"
        f"👤 User: <code>{user_id}</code>\n"
        f"💰 Miqdor: {amount:,} so'm\n"
        f"💳 Yangi balans: {new_balance:,} so'm"
    )


async def main():
    # DB jadvallarni yaratish
    await db.init_db()
    # Tariflarni DB dan yuklash
    await load_tariffs()

    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())
    dp.include_router(router)
    await bot.set_my_commands([
        BotCommand(command="start", description="Boshlash / Запустить"),
        BotCommand(command="settings", description="Sozlamalar / Настройки"),
        BotCommand(command="help", description="Yordam / Помощь"),
    ])

    # Payment modulga bot ni ulash
    payment.set_bot(bot, notify_payment, reload_tariffs_callback=load_tariffs)

    logger.info("=" * 50)
    logger.info("🚀 Marketplace Bot v13 — PostgreSQL + Click to'lov")
    logger.info(f"📁 Tarif rasmi: {TARIFF_IMAGE} ({'✅' if TARIFF_IMAGE.exists() else '❌'})")
    logger.info(f"💳 Click: service={payment.CLICK_SERVICE_ID}")
    logger.info("=" * 50)

    await bot.delete_webhook(drop_pending_updates=True)

    # Web server (Click callback uchun) + Bot polling birga
    web_app = payment.create_web_app()
    runner = web.AppRunner(web_app)
    await runner.setup()

    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Web server: port {port}")

    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())