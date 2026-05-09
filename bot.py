"""
Marketplace Infografik Bot v10
==============================
4 ta tarif — avvalgi ishlagan promptlar qaytarilgan, tavsif rasmlari yaxshilangan
"""

import os
import io
import re
import base64
import logging
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    BufferedInputFile, InputMediaPhoto,
    InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton, BotCommand,
)
from aiogram.enums import ParseMode
from openai import OpenAI
from PIL import Image

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
    raise ValueError("TELEGRAM_BOT_TOKEN va OPENAI_API_KEY .env faylda bo'lishi kerak!")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
router = Router()
executor = ThreadPoolExecutor(max_workers=4)
user_tasks = {}
user_settings = {}


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
        "choose_tariff": (
            "📦 <b>Tarifni tanlang:</b>\n\n"
            "1️⃣ <b>Infografika</b> — 2 ta infografik rasm\n"
            "2️⃣ <b>Infografika + Matn</b> — 2 infografik + kartochka matnlari\n"
            "3️⃣ <b>Infografika + Tavsif rasmlari</b> — 2 infografik + 2 reklama rasm\n"
            "4️⃣ <b>To'liq paket</b> — 2 infografik + 2 reklama rasm + matnlar"
        ),
        "setup_done": "✅ <b>Sozlamalar saqlandi!</b>\n\n📸 Endi mahsulot rasmini yuboring!",
        "busy": "⏳ Oldingi rasmingiz hali tayyor bo'lmadi. Kuting...",
        "error": "❌ <b>Xatolik yuz berdi</b>",
        "error_billing": "💳 OpenAI hisobida mablag' yetarli emas.",
        "error_rate": "⏱ Juda ko'p so'rov. 1 daqiqadan keyin urinib ko'ring.",
        "error_safety": "🚫 Rasm safety filtriga tushdi. Boshqa rasm yuboring.",
        "error_copyright": "⚠️ <b>Litsenziyalangan personaj aniqlandi:</b> <code>{keyword}</code>\n\nBoshqa rasm yuboring.",
        "help": "📖 <b>Yordam</b>\n\n🔹 Mahsulot rasmini yuboring\n🔹 Tanlangan tarifga mos natija tayyor bo'ladi\n\n⚙️ Sozlamalar — til/tarif o'zgartirish",
        "done_infographic": "✅ <b>Infografik rasmlar tayyor!</b>",
        "done_promo": "✅ <b>Tavsif rasmlari tayyor!</b>",
        "done_text": "✅ <b>Kartochka matnlari tayyor!</b>",
        "send_photo": "📸 Menga <b>mahsulot rasmini</b> yuboring!",
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
        "choose_tariff": (
            "📦 <b>Выберите тариф:</b>\n\n"
            "1️⃣ <b>Инфографика</b> — 2 варианта инфографики\n"
            "2️⃣ <b>Инфографика + Текст</b> — 2 инфографики + тексты карточки\n"
            "3️⃣ <b>Инфографика + Рекл. фото</b> — 2 инфографики + 2 рекламных фото\n"
            "4️⃣ <b>Полный пакет</b> — 2 инфографики + 2 рекл. фото + тексты"
        ),
        "setup_done": "✅ <b>Настройки сохранены!</b>\n\n📸 Отправьте фото товара!",
        "busy": "⏳ Предыдущее фото обрабатывается...",
        "error": "❌ <b>Произошла ошибка</b>",
        "error_billing": "💳 Недостаточно средств на счёте OpenAI.",
        "error_rate": "⏱ Слишком много запросов. Попробуйте через минуту.",
        "error_safety": "🚫 Фото заблокировано фильтром.",
        "error_copyright": "⚠️ <b>Лицензированный персонаж:</b> <code>{keyword}</code>\n\nОтправьте другое фото.",
        "help": "📖 <b>Помощь</b>\n\n🔹 Отправьте фото товара\n🔹 Результат зависит от тарифа\n\n⚙️ Настройки — сменить язык/тариф",
        "done_infographic": "✅ <b>Инфографика готова!</b>",
        "done_promo": "✅ <b>Рекламные фото готовы!</b>",
        "done_text": "✅ <b>Тексты для карточки готовы!</b>",
        "send_photo": "📸 Отправьте <b>фото товара</b>!",
        "progress": [
            {"bar": "▓▓░░░░░░░░", "pct": "15%", "stage": "🔍 Анализ товара...", "tip": "💡 Качественная инфографика увеличивает продажи на 40%!"},
            {"bar": "▓▓▓░░░░░░░", "pct": "25%", "stage": "✏️ Создание промпта...", "tip": "📸 ИИ подбирает стиль под товар"},
            {"bar": "▓▓▓▓▓░░░░░", "pct": "45%", "stage": "🎨 Генерация инфографики...", "tip": "🏪 Изображение под стандарты Uzum Market"},
            {"bar": "▓▓▓▓▓▓░░░░", "pct": "55%", "stage": "🖼 Рекламные фото...", "tip": "⏱ Подождите немного..."},
            {"bar": "▓▓▓▓▓▓▓░░░", "pct": "70%", "stage": "✏️ Тексты карточки...", "tip": "📝 Тексты на 2 языках"},
            {"bar": "▓▓▓▓▓▓▓▓░░", "pct": "85%", "stage": "📝 Полное описание...", "tip": "🎯 Подробное описание 3000+ символов"},
            {"bar": "▓▓▓▓▓▓▓▓▓░", "pct": "95%", "stage": "📦 Подготовка...", "tip": "✅ Почти готово!"},
        ],
    },
}

def t(uid, key, **kw):
    lang = user_settings.get(uid, {}).get("ui_lang", "uz")
    txt = TEXTS.get(lang, TEXTS["uz"]).get(key, key)
    return txt.format(**kw) if isinstance(txt, str) and kw else txt

def get_text_lang(uid): return user_settings.get(uid, {}).get("text_lang", "ru")
def get_tariff(uid): return user_settings.get(uid, {}).get("tariff", 1)

def get_progress(uid, step):
    lang = user_settings.get(uid, {}).get("ui_lang", "uz")
    stages = TEXTS.get(lang, TEXTS["uz"])["progress"]
    s = stages[min(step, len(stages)-1)]
    return f"🎨 <b>Ishlanmoqda</b>\n\n{s['bar']}  {s['pct']}\n\n{s['stage']}\n\n{s['tip']}"


# ══════════════════════════════════════════════════════════════════
# 1. TAHLIL (avvalgi ishlagan versiya)
# ══════════════════════════════════════════════════════════════════

ANALYSIS_PROMPT = """You are a professional product designer and advertising analyst.
Analyze the provided image carefully and extract structured information.
Return ONLY structured output in this format:

1. Product Info:
- Product type:
- Brand (if visible):
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
- NEVER include any brand names in your analysis — skip brand entirely
- Write "Brand: not applicable" for the brand field
- Focus only on product type, features, colors, materials
- Keep descriptions short and precise
- Focus on visual and structural analysis only"""

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
# 2. INFOGRAFIK PROMPT (avvalgi ishlagan versiya — to'liq)
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
- NEVER put any brand name or logo text on the image — this is CRITICAL
- Wrong brand name = product gets BLOCKED on marketplace
- Instead of brand name, use product type or feature as headline

CRITICAL RULES:
1. ALL text spelled PERFECTLY
2. Put all text in "quotes"
3. ABSOLUTELY NO BRAND NAMES anywhere on the image — not in headline, not in badge, not anywhere
4. NEVER use banned words
5. Use product type + key feature as headline instead of brand (e.g., "Акустическая гитара" not "Kabat")
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
# 3. INFOGRAFIK GENERATSIYA
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
# 4. TAVSIF RASMLARI (2 ta, har xil xususiyat)
# ══════════════════════════════════════════════════════════════════

def write_promo_prompts(analysis, text_lang):
    """2 ta FARQLI tavsif rasm prompti yozadi"""
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
- Different color scheme
- Different layout and composition
- Different text and headlines

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
- NO banned words (акция, скидка, лучший, топ, хит, бесплатно)"""},
            {"role": "user", "content": f"Write 2 COMPLETELY DIFFERENT promo image prompts for:\n\n{analysis}"},
        ],
        max_tokens=2000, temperature=0.8,
    )
    raw = r.choices[0].message.content.strip()
    parts = re.split(r'---PROMPT2---|---', raw)
    prompts = [p.strip() for p in parts if p.strip()]
    logger.info(f"Promo prompts: {len(prompts)} generated")
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
# 5. KARTOCHKA MATNLARI (2 bosqichli, avvalgi ishlagan versiya)
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
XUSUSIYATLARI_UZ: [texnik list, har biri yangi qatorda, "Xususiyat: qiymat" formatda]
XUSUSIYATLARI_RU: [texnik list, har biri yangi qatorda, "Параметр: значение" formatda]

📌 TOVAR NOMI (70-90 belgi):
- Sxema: Tovar turi + Brend (agar bor) + Kalit xususiyatlar
- Kamida 3 so'z, xaridor qidiradigan so'zlar
- 70 belgidan KAM bo'lmasin, 90 dan oshmasin
- Misol: "Skovorda antiyopishmas qoplama 24 sm, shisha qopqoq bilan, gazga mos, alyuminiy korpus"

📝 QISQACHA TAVSIF — SEO KALIT SO'ZLAR (300-390 belgi):
Jumla emas, vergul bilan ajratilgan kalit so'zlar. KAMIDA 20 ta. 300 belgidan KAM bo'lmasin.
Misol: "skovorda, qozon, antiyopishmas, kukmara, oshxona idishi, gazga mos, pishirish uchun, yog'siz pishirish, granit qoplama, shisha qopqoq, oson yuvish, chidamli idish, uy uchun skovorda, non stick pan, professional oshpaz idishi, kundalik foydalanish, sovg'a uchun idish, zamonaviy oshxona"

🏷 XUSUSIYATLAR — texnik list:
Misol:
"Turi: skovorda
Diametr: 24 sm
Qoplama: antiyopishmas granit
Korpus: alyuminiy
Qopqoq: shisha
Tutqich: bakelitli
Maqsad: gazli va elektr plitalarga mos
Og'irlik: taxminan 1,2 kg"

🚫 Stop-so'zlar: aksiya, bepul, chegirma, top, xit, eng yaxshi, arzon
🚫 Brend nomini UMUMAN ishlatma — tovar nomi va tasvirda brend bo'lmasin""",

    "ru": """Ты помощник, который пишет тексты карточек Uzum Market.
Проанализируй фото и напиши 3 текста (полное описание пишется отдельно).

ФОРМАТ:
TOVAR_NOMI_UZ: [70-90 символов]
TOVAR_NOMI_RU: [70-90 символов]
---
QISQACHA_TAVSIF_UZ: [300-390 символов, SEO ключевые слова через запятую, МИНИМУМ 20 слов]
QISQACHA_TAVSIF_RU: [300-390 символов, SEO ключевые слова через запятую, МИНИМУМ 20 слов]
---
XUSUSIYATLARI_UZ: [технический список, каждый на новой строке, "Параметр: значение"]
XUSUSIYATLARI_RU: [технический список, каждый на новой строке, "Параметр: значение"]

📌 НАЗВАНИЕ (70-90 символов):
- Схема: Тип + Бренд (если есть) + Ключевые характеристики
- Минимум 3 слова, НЕ МЕНЬШЕ 70 символов
- Пример: "Сковорода с антипригарным покрытием 24 см, стеклянная крышка, для газа, алюминиевый корпус"

📝 КРАТКОЕ — SEO ключевые слова (300-390 символов):
Не предложения, а слова через запятую. МИНИМУМ 20 штук. НЕ МЕНЬШЕ 300 символов.
Пример: "сковорода, казан, антипригарная, kukmara, кухонная посуда, для газа, готовка, без масла, гранитное покрытие, стеклянная крышка, легко моется, прочная посуда, домашняя сковорода, non stick pan, профессиональная посуда, ежедневное использование, подарок, современная кухня"

🏷 ХАРАКТЕРИСТИКИ — технический список:
Пример:
"Тип: сковорода
Диаметр: 24 см
Покрытие: антипригарное гранитное
Корпус: алюминий
Крышка: стеклянная
Ручка: бакелитовая
Назначение: газовые и электроплиты
Вес: около 1,2 кг"

🚫 Стоп-слова: акция, бесплатно, скидка, топ, хит, лучший, дёшево
🚫 НИКОГДА не используй названия брендов — ни в названии, ни в описании""",
}

DESCRIPTION_SYSTEM = {
    "uz": """Sen Uzum Market uchun UZUN tovar tavsifi yozuvchisisan.
FAQAT to'liq tavsif yoz, 2 tilda.

JAVOB FORMATI:
TAVSIF_UZ:
[o'zbekcha tavsif]

TAVSIF_RU:
[ruscha tavsif]

📄 QOIDALAR:
- Har bir tildagi tavsif KAMIDA 1500 belgi (jami 3000+)
- KAMIDA 10-12 paragraf, har biri 3-4 jumla
- Paragraflar orasida bo'sh qator
- Tabiiy, odam yozgandek, sodda tilda yoz
- Bold ishlatma

PARAGRAFLAR:
1. Umumiy tavsif — nima uchun va kimga
2. Material va sifati batafsil
3. O'lcham, hajm, texnik xususiyatlar
4. Dizayn va tashqi ko'rinish
5. Qulayliklari kundalik foydalanishda
6. Kimga mos — maqsadli auditoriya
7. Sovg'a sifatida qo'llash
8. Saqlash va parvarishlash maslahatlar
9. Boshqa o'xshashlardan farqi
10. Qadoqlash va yetkazib berish
11. Qo'shimcha foydalanish usullari
12. Yakuniy xulosa va tavsiya

⚠️ 1500 BELGIDAN KAM = XATO. Uzunroq yoz.
🚫 Stop-so'zlar taqiqlangan. Brend nomini UMUMAN qo'shma.""",

    "ru": """Ты пишешь ДЛИННЫЕ описания товаров для Uzum Market.
Только полное описание, на 2 языках.

ФОРМАТ:
TAVSIF_UZ:
[узбекский]

TAVSIF_RU:
[русский]

📄 ПРАВИЛА:
- Каждое описание МИНИМУМ 1500 символов (итого 3000+)
- МИНИМУМ 10-12 абзацев по 3-4 предложения
- Между абзацами пустая строка
- Естественно, простым языком
- Без жирного выделения

АБЗАЦЫ:
1. Общее описание — что это и для кого
2. Материал и качество подробно
3. Размер, объём, технические параметры
4. Дизайн и внешний вид
5. Удобство в повседневном использовании
6. Целевая аудитория
7. Как подарок
8. Хранение и уход
9. Отличия от аналогов
10. Упаковка и доставка
11. Дополнительные способы использования
12. Итоговый вывод и рекомендация

⚠️ МЕНЬШЕ 1500 СИМВОЛОВ = ОШИБКА. Пиши длиннее.
🚫 Стоп-слова запрещены. НИКОГДА не добавляй названия брендов.""",
}

def gen_card_step1(image_bytes, text_lang):
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": CARD_TEXT_SYSTEM.get(text_lang, CARD_TEXT_SYSTEM["ru"])},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                {"type": "text", "text": "Generate product name (70-90 chars), SEO keywords (300-390 chars, 20+ words), and technical features list."},
            ]},
        ],
        max_tokens=2000, temperature=0.5,
    )
    raw = r.choices[0].message.content.strip()
    logger.info(f"Card step1: {len(raw)} chars")
    result = {"name_uz": "", "name_ru": "", "short_uz": "", "short_ru": "", "feat_uz": "", "feat_ru": ""}
    for section in raw.split("---"):
        s = section.strip()
        if "TOVAR_NOMI_UZ:" in s and "TOVAR_NOMI_RU:" in s:
            p = s.split("TOVAR_NOMI_RU:"); result["name_uz"] = p[0].replace("TOVAR_NOMI_UZ:","").strip(); result["name_ru"] = p[1].strip()
        elif "QISQACHA_TAVSIF_UZ:" in s and "QISQACHA_TAVSIF_RU:" in s:
            p = s.split("QISQACHA_TAVSIF_RU:"); result["short_uz"] = p[0].replace("QISQACHA_TAVSIF_UZ:","").strip(); result["short_ru"] = p[1].strip()
        elif "XUSUSIYATLARI_UZ:" in s and "XUSUSIYATLARI_RU:" in s:
            p = s.split("XUSUSIYATLARI_RU:"); result["feat_uz"] = p[0].replace("XUSUSIYATLARI_UZ:","").strip(); result["feat_ru"] = p[1].strip()
    return result

def gen_card_step2(image_bytes, text_lang, context):
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": DESCRIPTION_SYSTEM.get(text_lang, DESCRIPTION_SYSTEM["ru"])},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                {"type": "text", "text": f"Mahsulot:\n{context}\n\nUZUN tavsif yoz, har tilda KAMIDA 1500 belgi, 10-12 paragraf."},
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
        await bot.send_message(chat_id, text, parse_mode=parse_mode); return
    chunks = []
    while text:
        if len(text) <= MAX: chunks.append(text); break
        cut = text.rfind('\n\n', 0, MAX)
        if cut == -1: cut = text.rfind('\n', 0, MAX)
        if cut == -1: cut = MAX
        chunks.append(text[:cut]); text = text[cut:].lstrip('\n')
    for chunk in chunks:
        try: await bot.send_message(chat_id, chunk, parse_mode=parse_mode)
        except: await bot.send_message(chat_id, chunk)

async def send_images(message, variants, label, prefix="v"):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    uid = message.from_user.id
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

def get_reply_keyboard(uid):
    lang = user_settings.get(uid, {}).get("ui_lang", "uz")
    if lang == "ru":
        return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="❓ Помощь")]], resize_keyboard=True)
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⚙️ Sozlamalar"), KeyboardButton(text="❓ Yordam")]], resize_keyboard=True)

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
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1️⃣ Infografika", callback_data="tariff_1")],
        [InlineKeyboardButton(text="2️⃣ Infografika + Matn", callback_data="tariff_2")],
        [InlineKeyboardButton(text="3️⃣ Infografika + Reklama rasmlar", callback_data="tariff_3")],
        [InlineKeyboardButton(text="4️⃣ To'liq paket", callback_data="tariff_4")],
    ])
    await cb.message.edit_text(t(uid, "choose_tariff"), parse_mode=ParseMode.HTML, reply_markup=kb)

@router.callback_query(F.data.startswith("tariff_"))
async def cb_tariff(cb: CallbackQuery):
    uid = cb.from_user.id
    if uid not in user_settings: user_settings[uid] = {}
    user_settings[uid]["tariff"] = int(cb.data.replace("tariff_", ""))
    await cb.answer()
    await cb.message.edit_text(t(uid, "setup_done"), parse_mode=ParseMode.HTML)
    await cb.message.answer(t(uid, "send_photo"), parse_mode=ParseMode.HTML, reply_markup=get_reply_keyboard(uid))

@router.message(Command("settings"))
async def cmd_settings(msg: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_ui_uz"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ui_ru"),
    ]])
    await msg.answer("🌐 Tilni tanlang / Выберите язык:", reply_markup=kb)

@router.message(F.text.in_(["⚙️ Sozlamalar", "⚙️ Настройки"]))
async def btn_settings(msg): await cmd_settings(msg)
@router.message(F.text.in_(["❓ Yordam", "❓ Помощь"]))
async def btn_help(msg): await msg.answer(t(msg.from_user.id, "help"), parse_mode=ParseMode.HTML)
@router.message(Command("help"))
async def cmd_help(msg): await msg.answer(t(msg.from_user.id, "help"), parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════════
# ASOSIY: Rasm qabul qilish
# ══════════════════════════════════════════════════════════════════

@router.message(F.photo)
async def handle_photo(message: types.Message):
    uid = message.from_user.id
    if uid not in user_settings or "tariff" not in user_settings.get(uid, {}):
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_ui_uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ui_ru"),
        ]])
        await message.answer("⚙️ Avval sozlamalarni tanlang:", reply_markup=kb)
        return

    if user_tasks.get(uid):
        await message.answer(t(uid, "busy")); return

    user_tasks[uid] = True
    tariff = get_tariff(uid)
    text_lang = get_text_lang(uid)
    user_msg_id = message.message_id

    stop = asyncio.Event()
    wait_msg = await message.answer(get_progress(uid, 0), parse_mode=ParseMode.HTML)
    progress = asyncio.create_task(update_progress(wait_msg, uid, stop))

    try:
        # Rasmni yuklash
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

        # 2. Infografik prompt + generatsiya (tariflar 1-4)
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

        # Progress stop
        stop.set(); await progress

        # ── NATIJALAR ────────────────────────────────────────────
        await send_images(message, infographics, t(uid, "done_infographic"), "infographic")

        if promos:
            await send_images(message, promos, t(uid, "done_promo"), "promo")

        if card:
            await send_card_texts(message, card, full_uz, full_ru)

        # Original rasm o'chirish
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
async def handle_text(msg):
    if msg.text in ["⚙️ Sozlamalar", "⚙️ Настройки", "❓ Yordam", "❓ Помощь"]: return
    await msg.answer(t(msg.from_user.id, "send_photo"), parse_mode=ParseMode.HTML)

@router.message(F.document)
async def handle_doc(msg):
    if msg.document.mime_type and msg.document.mime_type.startswith("image/"):
        await msg.answer("📸 Rasmni oddiy rasm sifatida yuboring!")
    else:
        await msg.answer(t(msg.from_user.id, "send_photo"), parse_mode=ParseMode.HTML)

async def main():
    dp.include_router(router)
    await bot.set_my_commands([
        BotCommand(command="start", description="Boshlash / Запустить"),
        BotCommand(command="settings", description="Sozlamalar / Настройки"),
        BotCommand(command="help", description="Yordam / Помощь"),
    ])
    logger.info("=" * 50)
    logger.info("🚀 Marketplace Bot v10 — 4 tarif")
    logger.info("📊 Infografik: 1104x1472 (3:4), gpt-image-2 low")
    logger.info("📊 Tavsif rasm: 1024x1024, gpt-image-2 low")
    logger.info("📊 Matn: gpt-4o-mini (2 step)")
    logger.info("=" * 50)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())