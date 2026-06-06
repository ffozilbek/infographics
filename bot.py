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
from aiogram import Bot, Dispatcher, Router, types, F
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
if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
    raise ValueError("TELEGRAM_BOT_TOKEN va OPENAI_API_KEY .env faylda bo'lishi kerak!")

# Asosiy papka (bot.py joylashgan joy)
BASE_DIR = Path(__file__).parent
TARIFF_IMAGE = BASE_DIR / "images" / "tarif.jpg"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)
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
        "error_billing": "💳 OpenAI hisobida mablag' yetarli emas.",
        "error_rate": "⏱ Juda ko'p so'rov. 1 daqiqadan keyin urinib ko'ring.",
        "error_safety": "🚫 Rasm safety filtriga tushdi. Boshqa rasm yuboring.",
        "error_copyright": "⚠️ <b>Litsenziyalangan personaj aniqlandi:</b> <code>{keyword}</code>\n\nBoshqa rasm yuboring.",
        "error_no_tariff": "⚠️ Avval tarifni tanlang! Pastdagi 📦 <b>Tariflar</b> tugmasini bosing.",
        "help": (
            "📖 <b>Yordam</b>\n\n"
            "🔹 📦 <b>Tariflar</b> — tarif tanlash\n"
            "🔹 💰 <b>Balans</b> — balansingizni ko'rish\n"
            "🔹 📋 <b>Namunalar</b> — namuna rasmlarni ko'rish\n"
            "🔹 ⚙️ <b>Sozlamalar</b> — til o'zgartirish\n\n"
            "📸 Mahsulot rasmini yuboring — bot ishlaydi!"
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
        "btn_settings": "⚙️ Sozlamalar",
        "btn_help": "❓ Yordam",
        # Progress
        "progress": [
            {"bar": "▓▓░░░░░░░░", "pct": "15%", "stage": "🔍 Mahsulot tahlil qilinmoqda...", "tip": "💡 Professional infografik sotuvni 40% ga oshiradi!"},
            {"bar": "▓▓▓░░░░░░░", "pct": "25%", "stage": "✏️ Prompt yaratilmoqda...", "tip": "📸 AI mahsulotga mos dizayn tanlaydi"},
            {"bar": "▓▓▓▓▓░░░░░", "pct": "45%", "stage": "🎨 Infografik yaratilmoqda...", "tip": "🏪 Rasm Uzum Market standartiga mos bo'ladi"},
            {"bar": "▓▓▓▓▓▓░░░░", "pct": "55%", "stage": "🖼 Tavsif rasmlari yaratilmoqda...", "tip": "⏱ Biroz kuting..."},
            {"bar": "▓▓▓▓▓▓▓░░░", "pct": "70%", "stage": "✏️ Kartochka matnlari tayyorlanmoqda...", "tip": "📝 Matnlar 2 tilda tayyorlanmoqda"},
            {"bar": "▓▓▓▓▓▓▓▓░░", "pct": "85%", "stage": "📝 To'liq tavsif yozilmoqda...", "tip": "🎯 3000+ belgilik batafsil tavsif"},
            {"bar": "▓▓▓▓▓▓▓▓▓░", "pct": "95%", "stage": "📦 Natijalar tayyorlanmoqda...", "tip": "✅ Deyarli tayyor!"},
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
        "error_billing": "💳 Недостаточно средств на счёте OpenAI.",
        "error_rate": "⏱ Слишком много запросов.",
        "error_safety": "🚫 Фото заблокировано фильтром.",
        "error_copyright": "⚠️ <b>Лицензированный персонаж:</b> <code>{keyword}</code>",
        "error_no_tariff": "⚠️ Сначала выберите тариф! Нажмите 📦 <b>Тарифы</b> внизу.",
        "help": (
            "📖 <b>Помощь</b>\n\n"
            "🔹 📦 <b>Тарифы</b> — выбрать тариф\n"
            "🔹 💰 <b>Баланс</b> — проверить баланс\n"
            "🔹 📋 <b>Примеры</b> — посмотреть примеры\n"
            "🔹 ⚙️ <b>Настройки</b> — сменить язык\n\n"
            "📸 Отправьте фото товара — бот начнёт работу!"
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
        "btn_settings": "⚙️ Настройки",
        "btn_help": "❓ Помощь",
        "progress": [
            {"bar": "▓▓░░░░░░░░", "pct": "15%", "stage": "🔍 Анализ товара...", "tip": "💡 Инфографика увеличивает продажи на 40%!"},
            {"bar": "▓▓▓░░░░░░░", "pct": "25%", "stage": "✏️ Создание промпта...", "tip": "📸 ИИ подбирает стиль"},
            {"bar": "▓▓▓▓▓░░░░░", "pct": "45%", "stage": "🎨 Генерация инфографики...", "tip": "🏪 Под стандарты Uzum Market"},
            {"bar": "▓▓▓▓▓▓░░░░", "pct": "55%", "stage": "🖼 Рекламные фото...", "tip": "⏱ Подождите..."},
            {"bar": "▓▓▓▓▓▓▓░░░", "pct": "70%", "stage": "✏️ Тексты карточки...", "tip": "📝 На 2 языках"},
            {"bar": "▓▓▓▓▓▓▓▓░░", "pct": "85%", "stage": "📝 Полное описание...", "tip": "🎯 3000+ символов"},
            {"bar": "▓▓▓▓▓▓▓▓▓░", "pct": "95%", "stage": "📦 Подготовка...", "tip": "✅ Почти готово!"},
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
    return f"🎨 <b>Ishlanmoqda</b>  |  📦 {tariff_name} ({price:,} so'm)\n\n{s['bar']}  {s['pct']}\n\n{s['stage']}\n\n{s['tip']}"

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

ANALYSIS_PROMPT = """You are a marketplace product analyst specializing in Uzum Market, Wildberries, and Ozon.
Analyze the provided product image and extract structured information for infographic creation.
Return ONLY structured output in this exact format:

1. Product Info:
- Product type (specific, e.g. "men's running shoes", not just "shoes"):
- Category (choose ONE: Footwear | Clothing | Electronics | Home Appliance | Food & Drink | Beauty & Care | Sports & Outdoor | Kids | Home & Garden | Other):
- Brand (if visible on product):

2. Visual Style:
- Background type (gradient, texture, environment):
- Primary color:
- Secondary color:
- Lighting style (soft, dramatic, studio, natural):
- Overall mood (premium, minimal, energetic, etc.):

3. Composition:
- Product position (left, right, center):
- Camera angle (front, tilted, top view, perspective):
- Depth (flat or 3D look):

4. Key Product Features — write as CUSTOMER BENEFITS in the TARGET LANGUAGE (Uzbek or Russian, as specified in the request):
   Think: "What does the buyer GAIN? What problem does this solve?"
   DO NOT write physical attribute labels. Write what the customer experiences.
   BAD (physical label, English): "Patterned materials", "Supportive structure", "Functional design"
   GOOD (customer benefit, Uzbek): "Kun bo'yi oyoq charchamaydi", "Terga chidamli mato", "Ko'z tortuvchi ko'rinish"
   GOOD (customer benefit, Russian): "Ноги не устают весь день", "Не промокает под дождём", "Выглядит стильно всегда"
- Feature 1 benefit:
- Feature 2 benefit:
- Feature 3 benefit:
- Feature 4 benefit:

5. Target Customer:
- Who buys this (age, lifestyle, need):
- Main purchase motivation:

6. Design Elements:
- Decorative elements suitable for this product:

7. Headline Concept (in TARGET LANGUAGE, customer-focused, 2-4 words):

RULES:
- NEVER add brand names unless clearly visible on the product itself
- If brand IS visible on product, write it EXACTLY as shown — NEVER translate
- Feature benefits must say what the customer GAINS, not what the product HAS
- Keep descriptions short and precise
- Features and Headline must be written in TARGET LANGUAGE (Uzbek or Russian, as specified in each request)
- Think like a marketplace copywriter on Uzum/Wildberries, not a product engineer"""

def analyze_product(image_bytes, text_lang="uz"):
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    lang_note = (
        "Write Feature benefits (section 4) and Headline (section 7) directly in UZBEK — natural marketplace Uzbek, NOT English."
        if text_lang == "uz" else
        "Write Feature benefits (section 4) and Headline (section 7) directly in RUSSIAN — natural conversational Russian, NOT English."
    )
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": [
{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
{"type": "text", "text": ANALYSIS_PROMPT + f"\n\nLANGUAGE NOTE: {lang_note}"},
]}],
        max_tokens=1000, temperature=0.3,
)
    result = r.choices[0].message.content.strip()
    logger.info(f"Analysis: {len(result)} chars")
    return result
COPYRIGHT_KEYWORDS = [
    "disney", "stitch", "angel", "mickey", "minnie", "frozen", "elsa",
    "marvel", "spider-man", "spiderman", "avengers", "iron man",
    "dc comics", "batman", "superman", "pokemon", "pikachu",
    "naruto", "dragon ball", "hello kitty", "sanrio", "pixar",
    "star wars", "nintendo", "mario", "sonic", "peppa pig",
    "paw patrol", "barbie", "transformers", "lego", "spongebob",
]

def check_copyright(text):
    lower = text.lower()
    for kw in COPYRIGHT_KEYWORDS:
        if kw in lower: return kw
    return None


# ══════════════════════════════════════════════════════════════════
# INFOGRAFIK PROMPT (avvalgi ishlagan to'liq versiya)
# ══════════════════════════════════════════════════════════════════

def get_infographic_prompt_system(text_lang):
    if text_lang == "uz":
        lang_instruction = "ALL text on the infographic must be in UZBEK language with PERFECT spelling."
        banned = 'BANNED: "aksiya", "bepul", "chegirma", "top", "xit", "yangilik", "eng yaxshi", "arzon".'
        copywriting_rules = """
UZBEK MARKETPLACE COPYWRITING — STRICTLY ENFORCE:
The feature titles and descriptions MUST sound like a native Uzbek marketplace seller wrote them.
DO NOT translate from English. Think in Uzbek from the start.

UNIVERSAL BAD → GOOD examples (apply to ANY category):
- "Naqshli materiallar"        → "Uzoq xizmat qiladi"
- "Zamonaviy dizayn"           → "Ko'z tortuvchi ko'rinish"
- "Yuqori sifatli mahsulot"    → "Bir marta olib, yillab ishlating"
- "Funksional xususiyatlar"    → "Har kuni ishonchli yordamchi"
- "Qo'llab-quvvatlovchi tuzilma" → "Ishonchli va mustahkam"

CATEGORY-SPECIFIC NATURAL UZBEK PATTERNS:
Footwear:     "Kun bo'yi oyoq charchamaydi", "Tez quriydi", "Oyoq nafas oladi"
Clothing:     "Har kuni kiysa bo'ladi", "Issiq saqlaydi", "Formasi ketmaydi"
Electronics:  "Bir zaryadda kun o'tadi", "Tez ulashadi", "Ko'z toliqtirmaydi"
Home Appl.:   "Oilangizga qulaylik", "Tez va oson tayyorlaydi", "Kuchni tejaydi"
Food & Drink: "Toza va tabiiy", "Vitaminlarga boy", "Oilaga foydali"
Beauty & Care:"Teri yumshoq bo'ladi", "Tez singib ketadi", "Allergiya yo'q"
Sports:       "Chidamlilikni oshiradi", "Harakatni erkinlashtiradi", "Terlashni kamaytiradi"
Kids:         "Xavfsiz materiallar", "Bolalar sevib o'ynaydi", "Uzoq xizmat qiladi"
Home & Garden:"Uyni yarqiratadi", "Oson tozalanadi", "Uzoq davom etadi"

TEST before finalising any text: "O'zbekiston bozorida sotuvchi shunday yozarmi?"
If NO → rewrite."""
    else:
        lang_instruction = "ALL text on the infographic must be in RUSSIAN language with PERFECT spelling."
        banned = 'BANNED: "акция", "бесплатно", "скидка", "топ", "хит", "новинка", "лучший", "дёшево".'
        copywriting_rules = """
RUSSIAN MARKETPLACE COPYWRITING — STRICTLY ENFORCE:
The feature titles and descriptions MUST sound like a native Russian Wildberries/Ozon seller wrote them.
DO NOT translate from English. Think in Russian from the start.

UNIVERSAL BAD → GOOD examples (apply to ANY category):
- "Узорчатый материал"          → "Прослужит не один сезон"
- "Современный дизайн"          → "Выглядишь стильно всегда"
- "Высококачественный продукт"  → "Купил однажды — пользуешься годами"
- "Функциональные характеристики" → "Всё продумано для вас"
- "Поддерживающая конструкция"  → "Надёжно и без лишних усилий"

CATEGORY-SPECIFIC NATURAL RUSSIAN PATTERNS:
Footwear:     "Ноги не устают весь день", "Не промокает под дождём", "Комфорт с первого шага"
Clothing:     "Греет до −30°C", "Форма не садится", "Носи каждый день"
Electronics:  "Заряда хватит на весь день", "Подключается за секунды", "Глаза не устают"
Home Appl.:   "Готовит быстро и легко", "Экономит электроэнергию", "Семья будет довольна"
Food & Drink: "Без консервантов и красителей", "Богато витаминами", "Натуральный состав"
Beauty & Care:"Кожа становится мягче", "Быстро впитывается", "Гипоаллергенный состав"
Sports:       "Выдерживает интенсивные нагрузки", "Свобода движений", "Меньше потоотделения"
Kids:         "Безопасные материалы", "Дети в восторге", "Выдержит любые игры"
Home & Garden:"Блеск без усилий", "Легко мыть", "Служит долго"

TEST before finalising any text: "Так написал бы реальный продавец на Wildberries?"
If NO → rewrite."""

    return f"""You are a marketplace infographic prompt engineer for Uzum Market, Wildberries, and Ozon.
You will receive a structured product analysis. Based on it, write a DETAILED image generation prompt in English.
YOUR OUTPUT MUST BE ONLY THE PROMPT TEXT. No explanations, no markdown, no backticks.
{copywriting_rules}

IMPORTANT — USE CATEGORY FROM ANALYSIS:
The analysis includes a "Category" field. Use it to select the most relevant copywriting patterns above.
If category is "Footwear" — use Footwear patterns. If "Electronics" — use Electronics patterns. And so on.
NEVER use footwear-specific language for food or electronics, and vice versa.

---

Write the prompt following this structure:

Create a high-end product infographic advertisement based on the following analysis:

[INSERT THE FULL ANALYSIS HERE]

Requirements:
- Keep the same composition and layout style
- Maintain similar visual hierarchy (headline, features, product placement)
- Use a clean, modern, minimalistic advertising design
- Ensure perfect, readable typography (NO distorted or broken text)
- Use correct grammar and professional wording

Design details:
- Background: recreate similar style but improved (more realistic, more depth)
- Lighting: soft studio lighting with realistic reflections
- Product: ultra-realistic, sharp, slightly tilted for depth
- Colors: consistent palette, premium look

Text:
{lang_instruction}
- Put every text element in "quotes" for accurate rendering
- Keep SHORT: 2-4 words titles, 5-8 words descriptions
- Headline: ALWAYS in ALL CAPS (e.g., "SPORT POYABZAL", "TEZKOR BLENDER")
- Feature titles and descriptions: Sentence case (first letter capital only)
- NO emoji in image text

Features:
- Show 3-4 feature points with minimal icons on the LEFT side
- Each feature: icon + bold title + short description below
- Features arranged VERTICALLY (list style), not horizontally
- NO bottom 3 blocks/cards — use feature list instead

Layout (3:4 portrait):
- Product as hero image (center/right, ~50-60% of image)
- Headline top-left, large bold text
- Subheadline below headline, smaller
- Features list on the left side, vertically arranged
- Badge (if applicable) on the right side
- Clean bottom section with closing tagline

Extras:
- Add subtle realistic elements depending on product
- Maintain balanced spacing and alignment
- Marketplace compliant (Uzum, Wildberries style)

Quality:
- Ultra realistic
- 4K commercial advertising quality
- No artifacts, no text distortion, no misspellings

⚠️ UZUM MARKET RULES (MANDATORY):
{banned}
- NO comparative/superlative claims
- NO excessive punctuation
- NEVER put any brand name or logo text on the image
- Instead of brand name, use product type or feature as headline

CRITICAL RULES:
1. ALL text spelled PERFECTLY
2. Put all text in "quotes"
3. ABSOLUTELY NO BRAND NAMES anywhere on the image
4. NEVER use banned words
5. Use product type + key feature as headline
6. NEVER translate text that is printed/written on the product
7. Any text visible on the product must be kept in original language or omitted entirely — NEVER translated
"""


def write_infographic_prompt(analysis, text_lang):
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": get_infographic_prompt_system(text_lang)},
            {"role": "user", "content": f"Based on this product analysis, write the image generation prompt:\n\n{analysis}"},
        ],
        max_tokens=2000, temperature=0.7,
    )
    prompt = r.choices[0].message.content.strip()
    logger.info(f"Infographic prompt: {len(prompt)} chars")
    return prompt


# ══════════════════════════════════════════════════════════════════
# INFOGRAFIK GENERATSIYA
# ══════════════════════════════════════════════════════════════════

def _gen_infographic(image_bytes, prompt):
    f = io.BytesIO(image_bytes); f.name = "product.jpg"
    r = client.images.edit(model="gpt-image-2", image=[f], prompt=prompt, n=1, size="1104x1472", quality="low")
    png = base64.b64decode(r.data[0].b64_json)
    img = Image.open(io.BytesIO(png)).convert("RGB")
    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=90, optimize=True); buf.seek(0)
    return buf.read()

async def gen_infographics_parallel(image_bytes, prompt):
    loop = asyncio.get_event_loop()
    t1 = loop.run_in_executor(executor, _gen_infographic, image_bytes, prompt)
    t2 = loop.run_in_executor(executor, _gen_infographic, image_bytes, prompt)
    results = await asyncio.gather(t1, t2, return_exceptions=True)
    variants = [r for r in results if not isinstance(r, Exception)]
    if not variants: raise results[0]
    return variants


# ══════════════════════════════════════════════════════════════════
# TAVSIF RASMLARI (2 ta, har xil)
# ══════════════════════════════════════════════════════════════════

def write_promo_prompts(analysis, text_lang):
    """2 ta FARQLI tavsif rasm prompti yozadi"""
    lang_name = "Uzbek" if text_lang == "uz" else "Russian"
    if text_lang == "uz":
        copy_rules = """
UZBEK COPYWRITING FOR PROMO IMAGES:
- Write benefit headlines, NOT feature labels
- BAD: "Maxsus material" → GOOD: "Terga chidamli, qulay kiyish"
- BAD: "Zamonaviy dizayn" → GOOD: "Har kuni chiroyli ko'rinish"
- BAD: "Funksional tuzilma" → GOOD: "Kun bo'yi charchamasdan yurish"
- Tone: Warm, direct Uzbek — like a trusted seller, not a translator
- TEST: "O'zbekiston bozorida sotuvchi shunday yozarmi?" — Yo'q bo'lsa, qayta yoz"""
    else:
        copy_rules = """
RUSSIAN COPYWRITING FOR PROMO IMAGES:
- Write benefit headlines, NOT feature labels
- BAD: "Специальный материал" → GOOD: "Не потеет, дышит весь день"
- BAD: "Современный дизайн" → GOOD: "Выглядишь стильно каждый день"
- BAD: "Поддерживающая конструкция" → GOOD: "Ноги не устают с утра до вечера"
- Tone: Conversational Russian — like a top Wildberries seller, not a translator
- TEST: "Так написал бы реальный продавец на Wildberries?" — Нет? Перепиши"""
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
{"role": "system", "content": f"""You create prompts for product PROMOTIONAL DETAIL images for marketplace product pages.
These are NOT infographics. These are DETAIL/FEATURE images that show specific product features up close.
Write EXACTLY 2 prompts, separated by the line: ---PROMPT2---
⚠️ THE 2 PROMPTS MUST BE COMPLETELY DIFFERENT:
- Different feature/benefit highlighted
- Different scene/background/setting
- Different color scheme
- Different layout and composition
- Different text and headlines
{copy_rules}
PROMPT 1 should focus on the product's PRIMARY FEATURE (e.g., material quality, main function, key technology).
Show the product in USE or being DEMONSTRATED. Include:
- Bold headline in {lang_name} describing THIS feature (in "quotes") — must sound natural, not translated
- The product shown from a specific angle highlighting this feature
- Color blocks, icons, visual hierarchy
- Feature callouts with icons and short {lang_name} text
- Lifestyle or demonstration scene
- Professional advertising quality
PROMPT 2 should focus on a COMPLETELY DIFFERENT FEATURE (e.g., convenience, durability, design, versatility).
Show the product in a DIFFERENT context/setting. Include:
- Different bold headline in {lang_name} (in "quotes") — NOT similar to Prompt 1, must sound natural
- Different angle, different background, different mood
- Different color palette
- Different feature callouts
- Different icons and visual elements
Both prompts:
- Keep the EXACT same product from reference image, DO NOT modify
- ABSOLUTELY NO brand names or logos on the image — brand names cause product blocking
- Use product type and features instead of brand name
- Square 1:1 format
- Ultra realistic, commercial advertising quality
- All text in {lang_name}, in "quotes", short and impactful
- Text must sound like a real marketplace seller wrote it — not a translator
- NO banned words (акция/aksiya, скидка/chegirma, лучший/eng yaxshi, топ/top, хит/xit, бесплатно/bepul)"""},
{"role": "user", "content": f"Write 2 COMPLETELY DIFFERENT promo image prompts for:\n\n{analysis}"},
],
        max_tokens=2000, temperature=0.8,
)
    raw = r.choices[0].message.content.strip()
    parts = re.split(r'---PROMPT2---|---', raw)
    prompts = [p.strip() for p in parts if p.strip()]
    logger.info(f"Promo prompts: {len(prompts)} generated")
    return prompts[:2] if len(prompts) >= 2 else [prompts[0], prompts[0]] if prompts else ["", ""]
# ▲▲▲ PATCH 3 end ▲▲▲

def _gen_promo(image_bytes, prompt):
    f = io.BytesIO(image_bytes); f.name = "product.jpg"
    r = client.images.edit(model="gpt-image-2", image=[f], prompt=prompt, n=1, size="1024x1024", quality="low")
    png = base64.b64decode(r.data[0].b64_json)
    img = Image.open(io.BytesIO(png)).convert("RGB")
    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=90, optimize=True); buf.seek(0)
    return buf.read()

async def gen_promos_parallel(image_bytes, prompts):
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(executor, _gen_promo, image_bytes, p) for p in prompts]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if not isinstance(r, Exception)]


# ══════════════════════════════════════════════════════════════════
# KARTOCHKA MATNLARI (2 bosqichli)
# ══════════════════════════════════════════════════════════════════

CARD_TEXT_SYSTEM = {
    "uz": """Sen Uzum Market sellerlariga tovar kartochkasi matnlarini yozib beradigan yordamchisan.
Rasmni tahlil qilib 3 ta matn tayyorla (to'liq tavsif EMAS, u alohida yoziladi).

JAVOB FORMATI:
TOVAR_NOMI_UZ: [70-90 belgi]
TOVAR_NOMI_RU: [70-90 belgi]
---
QISQACHA_TAVSIF_UZ: [300-390 belgi, SEO kalit so'zlar vergul bilan, KAMIDA 20 ta kalit so'z]
QISQACHA_TAVSIF_RU: [300-390 belgi, SEO kalit so'zlar vergul bilan, KAMIDA 20 ta kalit so'z]
---
XUSUSIYATLARI_UZ: [texnik list, har biri yangi qatorda, ANIQ parametr nomi bilan]
XUSUSIYATLARI_RU: [texnik list, har biri yangi qatorda, ANIQ parametr nomi bilan]

📌 TOVAR NOMI (70-90 belgi): Tovar turi + Kalit xususiyatlar, kamida 3 so'z, 70 dan KAM bo'lmasin
📝 QISQACHA TAVSIF (300-390 belgi): SEO kalit so'zlar vergul bilan, KAMIDA 20 ta, 300 dan KAM bo'lmasin

🏷 XUSUSIYATLAR FORMATI (MUHIM!):
Har bir qator ANIQ PARAMETR NOMI bilan boshlanishi SHART.
"Xususiyat" so'zini kalit sifatida ISHLATMA — bu XATO.

✅ TO'G'RI:
Turi: skovorda
Material: alyuminiy
Rang: qora
Diametr: 24 sm
Hajm: 2 litr
Og'irlik: 1,2 kg
Qoplama: antiyopishmas
Maqsad: gazli plita uchun

❌ XATO:
Xususiyat: alyuminiy
Xususiyat: qora
Xususiyat: 24 sm

Kalit nomlar: Turi, Material, Rang, O'lcham, Hajm, Og'irlik, Diametr, Balandlik, Uzunlik, Kenglik, Qoplama, Korpus, Maqsad, Mamlakat, Komplekt, Parvarish, Shakl, Stil, Soni

🚫 Stop-so'zlar: aksiya, bepul, chegirma, top, xit, eng yaxshi, arzon
🚫 Brend nomini UMUMAN ishlatma""",

    "ru": """Ты помощник для карточек Uzum Market. Проанализируй фото, напиши 3 текста.

ФОРМАТ:
TOVAR_NOMI_UZ: [70-90 символов]
TOVAR_NOMI_RU: [70-90 символов]
---
QISQACHA_TAVSIF_UZ: [300-390 символов, SEO ключевые слова через запятую, МИНИМУМ 20]
QISQACHA_TAVSIF_RU: [300-390 символов, SEO ключевые слова через запятую, МИНИМУМ 20]
---
XUSUSIYATLARI_UZ: [технический список, каждый на новой строке, с КОНКРЕТНЫМ названием параметра]
XUSUSIYATLARI_RU: [технический список, каждый на новой строке, с КОНКРЕТНЫМ названием параметра]

📌 НАЗВАНИЕ (70-90 символов): Тип + Характеристики, минимум 3 слова, НЕ МЕНЬШЕ 70
📝 КРАТКОЕ (300-390 символов): SEO слова через запятую, МИНИМУМ 20, НЕ МЕНЬШЕ 300

🏷 ФОРМАТ ХАРАКТЕРИСТИК (ВАЖНО!):
Каждая строка начинается с КОНКРЕТНОГО НАЗВАНИЯ параметра.
Слово "Характеристика" в качестве ключа — ЗАПРЕЩЕНО.

✅ ПРАВИЛЬНО:
Тип: сковорода
Материал: алюминий
Цвет: чёрный
Диаметр: 24 см
Объём: 2 литра
Вес: 1,2 кг
Покрытие: антипригарное
Назначение: для газовых плит

❌ НЕПРАВИЛЬНО:
Характеристика: алюминий
Характеристика: чёрный
Характеристика: 24 см

Названия ключей: Тип, Материал, Цвет, Размер, Объём, Вес, Диаметр, Высота, Длина, Ширина, Покрытие, Корпус, Назначение, Страна, Комплект, Уход, Форма, Стиль, Количество

🚫 Стоп-слова: акция, бесплатно, скидка, топ, хит, лучший, дёшево
🚫 НИКОГДА не используй названия брендов""",
}

DESCRIPTION_SYSTEM = {
    "uz": """Sen Uzum Market uchun UZUN tovar tavsifi yozuvchisisan.
FAQAT to'liq tavsif yoz, 2 tilda.

JAVOB FORMATI:
TAVSIF_UZ:
[o'zbekcha tavsif]

TAVSIF_RU:
[ruscha tavsif]

Har bir tildagi tavsif KAMIDA 1500 belgi, 10-12 paragraf, har biri 3-4 jumla.
Paragraflar: umumiy, material, o'lcham, dizayn, qulaylik, auditoriya, sovg'a, parvarishlash, farqlari, qadoqlash, qo'shimcha, xulosa.

⚠️ 1500 BELGIDAN KAM = XATO. Bold ishlatma. Brend nomini qo'shma.
🚫 Stop-so'zlar taqiqlangan.""",

    "ru": """Ты пишешь ДЛИННЫЕ описания для Uzum Market. Только описание, на 2 языках.

ФОРМАТ:
TAVSIF_UZ:
[узбекский]

TAVSIF_RU:
[русский]

Каждое МИНИМУМ 1500 символов, 10-12 абзацев по 3-4 предложения.
Абзацы: общее, материал, размер, дизайн, удобство, аудитория, подарок, уход, отличия, упаковка, доп., вывод.

⚠️ МЕНЬШЕ 1500 = ОШИБКА. Без жирного. Без брендов.
🚫 Стоп-слова запрещены.""",
}

def gen_card_step1(image_bytes, text_lang):
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": CARD_TEXT_SYSTEM.get(text_lang, CARD_TEXT_SYSTEM["ru"])},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                {"type": "text", "text": "Generate product name (70-90 chars), SEO keywords (300-390 chars), and features list. NO brand names."},
            ]},
        ],
        max_tokens=2000, temperature=0.5,
    )
    raw = r.choices[0].message.content.strip()
    logger.info(f"Card step1: {len(raw)} chars")
    result = {"name_uz":"","name_ru":"","short_uz":"","short_ru":"","feat_uz":"","feat_ru":""}

    def extract_between(text, start_key, end_key=None):
        """start_key dan end_key gacha matnni ajratib oladi"""
        if start_key not in text:
            return ""
        after = text.split(start_key, 1)[1].strip()
        if end_key and end_key in after:
            after = after.split(end_key, 1)[0]
        return after.strip()

    # --- bo'yicha bo'lish o'rniga to'g'ridan-to'g'ri key search
    if "TOVAR_NOMI_UZ:" in raw:
        result["name_uz"] = extract_between(raw, "TOVAR_NOMI_UZ:", "TOVAR_NOMI_RU:").split("\n")[0].strip()
    if "TOVAR_NOMI_RU:" in raw:
        result["name_ru"] = extract_between(raw, "TOVAR_NOMI_RU:", "---").split("\n")[0].strip()
        if not result["name_ru"]:
            result["name_ru"] = extract_between(raw, "TOVAR_NOMI_RU:", "QISQACHA").split("\n")[0].strip()
    if "QISQACHA_TAVSIF_UZ:" in raw:
        result["short_uz"] = extract_between(raw, "QISQACHA_TAVSIF_UZ:", "QISQACHA_TAVSIF_RU:").strip()
    if "QISQACHA_TAVSIF_RU:" in raw:
        result["short_ru"] = extract_between(raw, "QISQACHA_TAVSIF_RU:", "---").strip()
        if not result["short_ru"]:
            result["short_ru"] = extract_between(raw, "QISQACHA_TAVSIF_RU:", "XUSUSIYATLARI").strip()
    if "XUSUSIYATLARI_UZ:" in raw:
        result["feat_uz"] = extract_between(raw, "XUSUSIYATLARI_UZ:", "XUSUSIYATLARI_RU:").strip()
    if "XUSUSIYATLARI_RU:" in raw:
        result["feat_ru"] = extract_between(raw, "XUSUSIYATLARI_RU:", "---").strip()
        if not result["feat_ru"]:
            # oxirigacha olish
            result["feat_ru"] = extract_between(raw, "XUSUSIYATLARI_RU:").strip()

    logger.info(f"Card parsed: name_uz={len(result['name_uz'])}, feat_uz={len(result['feat_uz'])}, feat_ru={len(result['feat_ru'])}")
    return result

def gen_card_step2(image_bytes, text_lang, context):
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": DESCRIPTION_SYSTEM.get(text_lang, DESCRIPTION_SYSTEM["ru"])},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                {"type": "text", "text": f"Mahsulot:\n{context}\n\nUZUN tavsif yoz, har tilda KAMIDA 1500 belgi, 10-12 paragraf. Brend nomini qo'shma."},
            ]},
        ],
        max_tokens=4000, temperature=0.6,
    )
    raw = r.choices[0].message.content.strip()
    logger.info(f"Card step2: {len(raw)} chars")
    if "TAVSIF_RU:" in raw:
        p = raw.split("TAVSIF_RU:")
        return p[0].replace("TAVSIF_UZ:","").strip(), p[1].strip()
    return raw, raw


# ══════════════════════════════════════════════════════════════════
# YORDAMCHILAR
# ══════════════════════════════════════════════════════════════════

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
    feat_uz = [l.strip() for l in card['feat_uz'].split('\n') if l.strip()]
    feat_ru = [l.strip() for l in card['feat_ru'].split('\n') if l.strip()]
    clean = lambda t: re.sub(r'\*\*(.+?)\*\*', r'\1', t)
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
    settings = await get_settings(msg.from_user.id)
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
    await set_setting(uid, "text_lang", cb.data.replace("lang_text_", ""))
    await cb.answer()

    settings = await get_settings(uid)
    chat_id = cb.message.chat.id
    tariff_kb = await get_tariff_keyboard()

    # Til tanlagandan keyin darhol tarif tanlash
    if TARIFF_IMAGE.exists():
        try:
            await cb.message.delete()
        except Exception:
            pass
        # Rasmni Telegram limitiga moslashtirish
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
        try:
            await cb.message.edit_text(
                t(settings, "choose_tariff"),
                parse_mode=ParseMode.HTML,
                reply_markup=tariff_kb,
            )
        except Exception:
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
@router.message(F.text.in_(["⚙️ Sozlamalar", "⚙️ Настройки"]))
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

    # Balans tekshiruv
    lang = settings.get("ui_lang", "uz")
    price = get_tariff_price(tariff)
    balance = await db.get_balance(uid)
    if balance < price:
        if lang == "uz":
            text = (
                f"❌ <b>Balans yetarli emas!</b>\n\n"
                f"📦 Tarif: <b>{get_tariff_name(tariff, 'uz')}</b>\n"
                f"💰 Narxi: <b>{price:,} so'm</b>\n"
                f"💰 Balansingiz: <b>{balance:,} so'm</b>\n"
                f"💰 Yetishmaydi: <b>{price - balance:,} so'm</b>\n\n"
                "Balansni to'ldiring 👇"
            )
        else:
            text = (
                f"❌ <b>Недостаточно средств!</b>\n\n"
                f"📦 Тариф: <b>{get_tariff_name(tariff, 'ru')}</b>\n"
                f"💰 Стоимость: <b>{price:,} сум</b>\n"
                f"💰 Ваш баланс: <b>{balance:,} сум</b>\n"
                f"💰 Не хватает: <b>{price - balance:,} сум</b>\n\n"
                "Пополните баланс 👇"
            )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Balansni to'ldirish" if lang == "uz" else "💳 Пополнить баланс", callback_data="topup_start")],
        ])
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if user_tasks.get(uid):
        await message.answer(t(settings, "busy")); return

    user_tasks[uid] = True
    text_lang = settings.get("text_lang", "ru")
    user_msg_id = message.message_id

    stop = asyncio.Event()
    wait_msg = await message.answer(get_progress(settings, 0), parse_mode=ParseMode.HTML)
    progress = asyncio.create_task(update_progress(wait_msg, uid, stop))

    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
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
        # Cache yangilash
        if uid in _settings_cache:
            _settings_cache[uid]["balance"] = await db.get_balance(uid)
        new_balance = await db.get_balance(uid)
        logger.info(f"Balans yechildi: user={uid}, -{price}, qoldi={new_balance}")

        # Natijalar
        await send_images(message, infographics, t(settings, "done_infographic"), "infographic")
        if promos:
            await send_images(message, promos, t(settings, "done_promo"), "promo")
        if card:
            await send_card_texts(message, card, full_uz, full_ru)

        try: await bot.delete_message(chat_id=message.chat.id, message_id=user_msg_id)
        except: pass
        await wait_msg.delete()

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
                 "📋 Namunalar", "📋 Примеры", "⚙️ Sozlamalar", "⚙️ Настройки",
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


async def main():
    # DB jadvallarni yaratish
    await db.init_db()
    # Tariflarni DB dan yuklash
    await load_tariffs()

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