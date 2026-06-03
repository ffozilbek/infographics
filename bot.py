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
user_settings = {}  # {uid: {"ui_lang", "text_lang", "tariff", "balance"}}


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
        "tariff_set": "✅ <b>Tarif tanlandi: {name}</b>\n\n📸 Endi mahsulot rasmini yuboring!",
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
        "ready_with_tariff": "✅ <b>Hammasi tayyor!</b>\n\n📦 Joriy tarif: <b>{tariff}</b>\n\n📸 Mahsulot rasmini yuboring — bot ishlaydi!\n\n💡 Tarifni o'zgartirish uchun 📦 Tariflar tugmasini bosing.",
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
        "tariff_set": "✅ <b>Тариф выбран: {name}</b>\n\n📸 Отправьте фото товара!",
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
        "ready_with_tariff": "✅ <b>Всё готово!</b>\n\n📦 Текущий тариф: <b>{tariff}</b>\n\n📸 Отправьте фото товара — бот начнёт работу!\n\n💡 Сменить тариф — кнопка 📦 Тарифы внизу.",
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

def t(uid, key, **kw):
    lang = user_settings.get(uid, {}).get("ui_lang", "uz")
    txt = TEXTS.get(lang, TEXTS["uz"]).get(key, key)
    return txt.format(**kw) if isinstance(txt, str) and kw else txt

def get_text_lang(uid): return user_settings.get(uid, {}).get("text_lang", "ru")
def get_tariff(uid): return user_settings.get(uid, {}).get("tariff", 0)
def get_balance(uid): return payment.get_balance(uid)

def get_progress(uid, step):
    lang = user_settings.get(uid, {}).get("ui_lang", "uz")
    stages = TEXTS.get(lang, TEXTS["uz"])["progress"]
    s = stages[min(step, len(stages)-1)]
    tariff = get_tariff(uid)
    names = TEXTS.get(lang, TEXTS["uz"])["tariff_names"]
    tariff_name = names.get(tariff, "")
    return f"🎨 <b>Ishlanmoqda</b>  |  📦 {tariff_name}\n\n{s['bar']}  {s['pct']}\n\n{s['stage']}\n\n{s['tip']}"

def get_reply_keyboard(uid):
    lang = user_settings.get(uid, {}).get("ui_lang", "uz")
    tx = TEXTS.get(lang, TEXTS["uz"])
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=tx["btn_tariffs"]), KeyboardButton(text=tx["btn_balance"]), KeyboardButton(text=tx["btn_samples"])],
        [KeyboardButton(text=tx["btn_settings"]), KeyboardButton(text=tx["btn_help"])],
    ], resize_keyboard=True)


# ══════════════════════════════════════════════════════════════════
# TAHLIL
# ══════════════════════════════════════════════════════════════════

ANALYSIS_PROMPT = """You are a professional product designer and advertising analyst.
Analyze the provided image carefully and extract structured information.
Return ONLY structured output in this format:

1. Product Info:
- Product type:
- Brand: not applicable
- Category:

2. Visual Style:
- Background type (gradient, texture, environment):
- Main colors (primary, secondary):
- Lighting style (soft, dramatic, studio, natural):
- Overall mood (premium, minimal, energetic, etc.):

3. Composition:
- Product position (left, right, center):
- Camera angle (front, tilted, top view, perspective):
- Depth (flat or 3D look):
- Spacing (minimal, dense):

4. Typography:
- Headline text:
- Subheadline text:
- Font style (modern, bold, thin, sans-serif):
- Text alignment:

5. Features Section:
- Feature 1:
- Feature 2:
- Feature 3:
- Feature 4:

6. Design Elements:
- Icons (type and style):
- Decorative elements (water drops, glow, particles, etc.):

7. Key Selling Points:
- Main marketing message:
- Target audience (if inferable):

IMPORTANT:
- NEVER include any brand names — always write "Brand: not applicable"
- If product has text/labels printed on it, write them EXACTLY as shown in original language — do NOT translate
- Focus only on product type, features, colors, materials
- Keep descriptions short and precise"""

def analyze_product(image_bytes):
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
            {"type": "text", "text": ANALYSIS_PROMPT},
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
    else:
        lang_instruction = "ALL text on the infographic must be in RUSSIAN language with PERFECT spelling."
        banned = 'BANNED: "акция", "бесплатно", "скидка", "топ", "хит", "новинка", "лучший", "дёшево".'

    return f"""You are an expert marketplace infographic prompt engineer.

You will receive a structured product analysis. Based on it, write a DETAILED image generation prompt in English.

YOUR OUTPUT MUST BE ONLY THE PROMPT TEXT. No explanations, no markdown, no backticks.

Write the prompt following this structure:

---

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
- NO CapsLock
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
6. NEVER translate text that is printed/written on the product — if product has "Coffee Time" written on it, do NOT write "Kofe vaqti" or any translation. Either keep it exactly or don't include it.
7. Any text visible on the product (labels, prints, engravings) must be kept in original language or omitted entirely — NEVER translated
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
    lang_name = "Uzbek" if text_lang == "uz" else "Russian"
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"""You create prompts for product PROMOTIONAL DETAIL images for marketplace product pages.

These are NOT infographics. These are DETAIL/FEATURE images that show specific product features up close.

Write EXACTLY 2 prompts, separated by the line: ---PROMPT2---

⚠️ THE 2 PROMPTS MUST BE COMPLETELY DIFFERENT:
- Different feature/benefit highlighted
- Different scene/background/setting
- Different layout and composition
- Different text and headlines
- BUT the product itself must look EXACTLY THE SAME in both — same colors, same shape, same design

PROMPT 1 should focus on the product's PRIMARY FEATURE (e.g., material quality, main function, key technology).
Show the product in USE or being DEMONSTRATED. Include:
- Bold headline in {lang_name} describing THIS feature (in "quotes")
- The product shown from a specific angle highlighting this feature
- Color blocks, icons, visual hierarchy
- Feature callouts with icons and short {lang_name} text
- Lifestyle or demonstration scene
- Professional advertising quality

PROMPT 2 should focus on a COMPLETELY DIFFERENT FEATURE (e.g., convenience, durability, design, versatility).
Show the product in a DIFFERENT context/setting. Include:
- Different bold headline in {lang_name} (in "quotes") — NOT similar to Prompt 1
- Different angle, different background
- Different feature callouts
- Different icons and visual elements
- BUT product colors and appearance must remain IDENTICAL to the original

⚠️ CRITICAL PRODUCT RULES FOR BOTH PROMPTS:
- Product must look EXACTLY like the reference image
- NEVER change product colors — if product is blue, it stays blue in both images
- NEVER add patterns, decorations, or modifications to the product
- NEVER make the product more colorful or vibrant than the original
- Keep the product realistic and true to the reference

Both prompts:
- Keep the EXACT same product from reference image, DO NOT modify
- ABSOLUTELY NO brand names or logos on the image
- Use product type and features instead of brand name
- If product has text printed on it (like "Coffee Time"), keep it exactly as is — NEVER translate it
- Square 1:1 format
- Ultra realistic, commercial advertising quality
- All text in {lang_name}, in "quotes", short and impactful
- NO banned words (акция, скидка, лучший, топ, хит, бесплатно)"""},
            {"role": "user", "content": f"Write 2 COMPLETELY DIFFERENT promo image prompts for:\n\n{analysis}"},
        ],
        max_tokens=2000, temperature=0.8,
    )
    raw = r.choices[0].message.content.strip()
    parts = re.split(r'---PROMPT2---|---', raw)
    prompts = [p.strip() for p in parts if p.strip()]
    logger.info(f"Promo prompts: {len(prompts)}")
    return prompts[:2] if len(prompts) >= 2 else [prompts[0], prompts[0]] if prompts else ["", ""]

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
    for section in raw.split("---"):
        s = section.strip()
        if "TOVAR_NOMI_UZ:" in s and "TOVAR_NOMI_RU:" in s:
            p = s.split("TOVAR_NOMI_RU:"); result["name_uz"]=p[0].replace("TOVAR_NOMI_UZ:","").strip(); result["name_ru"]=p[1].strip()
        elif "QISQACHA_TAVSIF_UZ:" in s and "QISQACHA_TAVSIF_RU:" in s:
            p = s.split("QISQACHA_TAVSIF_RU:"); result["short_uz"]=p[0].replace("QISQACHA_TAVSIF_UZ:","").strip(); result["short_ru"]=p[1].strip()
        elif "XUSUSIYATLARI_UZ:" in s and "XUSUSIYATLARI_RU:" in s:
            p = s.split("XUSUSIYATLARI_RU:"); result["feat_uz"]=p[0].replace("XUSUSIYATLARI_UZ:","").strip(); result["feat_ru"]=p[1].strip()
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
        try: await wait_msg.edit_text(get_progress(uid, step), parse_mode=ParseMode.HTML)
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
    dl = "💾 Yuklab olish" if user_settings.get(uid, {}).get("ui_lang") == "uz" else "💾 Скачать"
    for i, v in enumerate(variants):
        await message.answer_document(document=BufferedInputFile(file=v, filename=f"{prefix}_{i+1}_{uid}_{ts}.jpg"), caption=f"{dl} {i+1}")

async def send_card_texts(message, card, full_uz, full_ru):
    uid = message.from_user.id
    lang = user_settings.get(uid, {}).get("ui_lang", "uz")
    feat_uz = [l.strip() for l in card['feat_uz'].split('\n') if l.strip()]
    feat_ru = [l.strip() for l in card['feat_ru'].split('\n') if l.strip()]
    clean = lambda t: re.sub(r'\*\*(.+?)\*\*', r'\1', t)
    full_uz, full_ru = clean(full_uz), clean(full_ru)

    if lang == "uz":
        n,s,d,f = "1. Tovar nomi","2. Tovar qisqacha tavsifi","3. Tovar tavsifi","4. Tovar xususiyatlari"
    else:
        n,s,d,f = "1. Название товара","2. Краткое описание товара","3. Описание товара","4. Характеристики товара"

    msg1 = (f"{t(uid,'done_text')}\n\n📌 <b>{n}</b>\n\n"
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
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_ui_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ui_ru"),
    ]])
    await msg.answer(t(msg.from_user.id, "welcome"), parse_mode=ParseMode.HTML, reply_markup=kb)

@router.callback_query(F.data.startswith("lang_ui_"))
async def cb_ui(cb: CallbackQuery):
    uid = cb.from_user.id
    if uid not in user_settings: user_settings[uid] = {}
    user_settings[uid]["ui_lang"] = cb.data.replace("lang_ui_", "")
    await cb.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_text_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_text_ru"),
    ]])
    await cb.message.edit_text(t(uid, "choose_text_lang"), parse_mode=ParseMode.HTML, reply_markup=kb)

@router.callback_query(F.data.startswith("lang_text_"))
async def cb_text(cb: CallbackQuery):
    uid = cb.from_user.id
    if uid not in user_settings: user_settings[uid] = {}
    user_settings[uid]["text_lang"] = cb.data.replace("lang_text_", "")

    await cb.answer()

    chat_id = cb.message.chat.id
    tariff_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1️⃣ Infografika", callback_data="tariff_1")],
        [InlineKeyboardButton(text="2️⃣ Infografika + Matn", callback_data="tariff_2")],
        [InlineKeyboardButton(text="3️⃣ Infografika + Reklama rasmlar", callback_data="tariff_3")],
        [InlineKeyboardButton(text="4️⃣ To'liq paket", callback_data="tariff_4")],
    ])

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
            caption=t(uid, "choose_tariff"),
            parse_mode=ParseMode.HTML,
            reply_markup=tariff_kb,
        )
    else:
        try:
            await cb.message.edit_text(
                t(uid, "choose_tariff"),
                parse_mode=ParseMode.HTML,
                reply_markup=tariff_kb,
            )
        except Exception:
            await bot.send_message(
                chat_id=chat_id,
                text=t(uid, "choose_tariff"),
                parse_mode=ParseMode.HTML,
                reply_markup=tariff_kb,
            )


# ── 📦 Tariflar ─────────────────────────────────────────────────
@router.message(F.text.in_(["📦 Tariflar", "📦 Тарифы"]))
async def btn_tariffs(msg: types.Message):
    uid = msg.from_user.id
    tariff_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1️⃣ Infografika", callback_data="tariff_1")],
        [InlineKeyboardButton(text="2️⃣ Infografika + Matn", callback_data="tariff_2")],
        [InlineKeyboardButton(text="3️⃣ Infografika + Reklama rasmlar", callback_data="tariff_3")],
        [InlineKeyboardButton(text="4️⃣ To'liq paket", callback_data="tariff_4")],
    ])
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
        await msg.answer_photo(photo=photo_file, caption=t(uid, "choose_tariff"), parse_mode=ParseMode.HTML, reply_markup=tariff_kb)
    else:
        await msg.answer(t(uid, "choose_tariff"), parse_mode=ParseMode.HTML, reply_markup=tariff_kb)

@router.callback_query(F.data.startswith("tariff_"))
async def cb_tariff(cb: CallbackQuery):
    uid = cb.from_user.id
    if uid not in user_settings: user_settings[uid] = {}
    tariff_num = int(cb.data.replace("tariff_", ""))
    user_settings[uid]["tariff"] = tariff_num
    lang = user_settings.get(uid, {}).get("ui_lang", "uz")
    names = TEXTS[lang]["tariff_names"]
    tariff_name = names.get(tariff_num, "")
    await cb.answer()

    # Avvalgi xabarni yangilash
    try:
        await cb.message.edit_caption(
            caption=t(uid, "tariff_set", name=tariff_name),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        try:
            await cb.message.edit_text(
                t(uid, "tariff_set", name=tariff_name),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await bot.send_message(
                chat_id=cb.message.chat.id,
                text=t(uid, "tariff_set", name=tariff_name),
                parse_mode=ParseMode.HTML,
            )

    # Joriy tarif ko'rsatilgan xabar + reply keyboard
    await bot.send_message(
        chat_id=cb.message.chat.id,
        text=t(uid, "ready_with_tariff", tariff=tariff_name),
        parse_mode=ParseMode.HTML,
        reply_markup=get_reply_keyboard(uid),
    )


# ── 💰 Balans ───────────────────────────────────────────────────
@router.message(F.text.in_(["💰 Balans", "💰 Баланс"]))
async def btn_balance(msg: types.Message):
    uid = msg.from_user.id
    balance = get_balance(uid)
    lang = user_settings.get(uid, {}).get("ui_lang", "uz")

    if lang == "uz":
        text = (
            f"💰 <b>Balansingiz:</b> {balance:,} so'm\n\n"
            "To'ldirish uchun summani tanlang 👇"
        )
    else:
        text = (
            f"💰 <b>Ваш баланс:</b> {balance:,} сум\n\n"
            "Выберите сумму для пополнения 👇"
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="10,000 so'm", callback_data="topup_10000"),
            InlineKeyboardButton(text="25,000 so'm", callback_data="topup_25000"),
        ],
        [
            InlineKeyboardButton(text="50,000 so'm", callback_data="topup_50000"),
            InlineKeyboardButton(text="100,000 so'm", callback_data="topup_100000"),
        ],
    ])
    await msg.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(F.data.startswith("topup_"))
async def cb_topup(cb: CallbackQuery):
    uid = cb.from_user.id
    amount = int(cb.data.replace("topup_", ""))
    lang = user_settings.get(uid, {}).get("ui_lang", "uz")

    # Click to'lov linki
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

    await cb.answer()
    await cb.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)


# ── 📋 Namunalar ────────────────────────────────────────────────
@router.message(F.text.in_(["📋 Namunalar", "📋 Примеры"]))
async def btn_samples(msg: types.Message):
    uid = msg.from_user.id
    lang = user_settings.get(uid, {}).get("ui_lang", "uz")
    names = TEXTS[lang]["tariff_names"]
    sample_label = "namuna" if lang == "uz" else "пример"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"1️⃣ {names[1]} — {sample_label}", callback_data="sample_1")],
        [InlineKeyboardButton(text=f"2️⃣ {names[2]} — {sample_label}", callback_data="sample_2")],
        [InlineKeyboardButton(text=f"3️⃣ {names[3]} — {sample_label}", callback_data="sample_3")],
        [InlineKeyboardButton(text=f"4️⃣ {names[4]} — {sample_label}", callback_data="sample_4")],
    ])
    await msg.answer(t(uid, "samples"), parse_mode=ParseMode.HTML, reply_markup=kb)

@router.callback_query(F.data.startswith("sample_"))
async def cb_sample(cb: CallbackQuery):
    uid = cb.from_user.id
    tariff_num = int(cb.data.replace("sample_", ""))
    lang = user_settings.get(uid, {}).get("ui_lang", "uz")
    text_lang = get_text_lang(uid)
    await cb.answer()

    samples_dir = BASE_DIR / "images" / "samples"

    # Namuna rasmlarni topish (tarif1_1.jpg, tarif1_2.jpg, ...)
    sample_images = sorted(samples_dir.glob(f"tarif{tariff_num}_*.jpg"))

    if not sample_images:
        no_sample = "🔜 Bu tarif uchun namunalar hali qo'shilmagan." if lang == "uz" else "🔜 Примеры для этого тарифа ещё не добавлены."
        await cb.message.answer(no_sample)
        return

    # Rasmlarni yuborish
    if len(sample_images) >= 2:
        media = [
            InputMediaPhoto(
                media=FSInputFile(sample_images[0]),
                caption=f"📋 {'Namuna' if lang == 'uz' else 'Пример'} — {TEXTS[lang]['tariff_names'][tariff_num]}",
                parse_mode=ParseMode.HTML,
            ),
        ]
        for img in sample_images[1:4]:  # max 4 ta rasm
            media.append(InputMediaPhoto(media=FSInputFile(img)))
        await cb.message.answer_media_group(media=media)
    else:
        await cb.message.answer_photo(
            photo=FSInputFile(sample_images[0]),
            caption=f"📋 {'Namuna' if lang == 'uz' else 'Пример'} — {TEXTS[lang]['tariff_names'][tariff_num]}",
            parse_mode=ParseMode.HTML,
        )

    # Namuna textlar (tarif 2 va 4 uchun) — real format
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
    await msg.answer(t(msg.from_user.id, "help"), parse_mode=ParseMode.HTML)

@router.message(Command("help"))
async def cmd_help(msg: types.Message): await msg.answer(t(msg.from_user.id, "help"), parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════
# ASOSIY: Rasm qabul qilish
# ══════════════════════════════════════════════════════════════════

@router.message(F.photo)
async def handle_photo(message: types.Message):
    uid = message.from_user.id

    # Til tekshiruv
    if uid not in user_settings or "text_lang" not in user_settings.get(uid, {}):
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_ui_uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ui_ru"),
        ]])
        await message.answer("⚙️ Avval tilni tanlang:", reply_markup=kb)
        return

    # Tarif tekshiruv
    tariff = get_tariff(uid)
    if tariff == 0:
        await message.answer(t(uid, "error_no_tariff"), parse_mode=ParseMode.HTML)
        return

    if user_tasks.get(uid):
        await message.answer(t(uid, "busy")); return

    user_tasks[uid] = True
    text_lang = get_text_lang(uid)
    user_msg_id = message.message_id

    stop = asyncio.Event()
    wait_msg = await message.answer(get_progress(uid, 0), parse_mode=ParseMode.HTML)
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
            await wait_msg.edit_text(t(uid, "error_copyright", keyword=cr), parse_mode=ParseMode.HTML)
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

        # Natijalar
        await send_images(message, infographics, t(uid, "done_infographic"), "infographic")
        if promos:
            await send_images(message, promos, t(uid, "done_promo"), "promo")
        if card:
            await send_card_texts(message, card, full_uz, full_ru)

        try: await bot.delete_message(chat_id=message.chat.id, message_id=user_msg_id)
        except: pass
        await wait_msg.delete()

        fin = "🔄 Yana rasm yuboring!" if user_settings.get(uid, {}).get("ui_lang") == "uz" else "🔄 Отправьте ещё фото!"
        await message.answer(fin)

    except Exception as e:
        stop.set(); await progress
        logger.error(f"Xatolik: user={uid}, error={e}")
        err = str(e).lower()
        if "billing" in err or "quota" in err: em = t(uid, "error_billing")
        elif "rate_limit" in err: em = t(uid, "error_rate")
        elif "moderation" in err or "safety" in err: em = t(uid, "error_safety")
        else: em = f"<code>{str(e)[:300]}</code>"
        await wait_msg.edit_text(f"{t(uid, 'error')}\n\n{em}", parse_mode=ParseMode.HTML)

    finally:
        user_tasks.pop(uid, None)


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(msg: types.Message):
    btn_texts = ["📦 Tariflar", "📦 Тарифы", "💰 Balans", "💰 Баланс",
                 "📋 Namunalar", "📋 Примеры", "⚙️ Sozlamalar", "⚙️ Настройки",
                 "❓ Yordam", "❓ Помощь"]
    if msg.text in btn_texts: return
    await msg.answer(t(msg.from_user.id, "send_photo"), parse_mode=ParseMode.HTML)

@router.message(F.document)
async def handle_doc(msg: types.Message):
    if msg.document.mime_type and msg.document.mime_type.startswith("image/"):
        await msg.answer("📸 Rasmni oddiy rasm sifatida yuboring!")
    else:
        await msg.answer(t(msg.from_user.id, "send_photo"), parse_mode=ParseMode.HTML)


# ── Ishga tushirish ──────────────────────────────────────────────
async def notify_payment(user_id: int, amount: int, new_balance: int):
    """To'lov bo'lganda foydalanuvchiga xabar yuborish"""
    lang = user_settings.get(user_id, {}).get("ui_lang", "uz")
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
    dp.include_router(router)
    await bot.set_my_commands([
        BotCommand(command="start", description="Boshlash / Запустить"),
        BotCommand(command="settings", description="Sozlamalar / Настройки"),
        BotCommand(command="help", description="Yordam / Помощь"),
    ])

    # Payment modulga bot ni ulash
    payment.set_bot(bot, notify_payment)

    logger.info("=" * 50)
    logger.info("🚀 Marketplace Bot v12 — Click to'lov bilan")
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