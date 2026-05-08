"""
Marketplace Infografik Bot v8
==============================
Tezlashtirish:
1. Tahlil + Prompt bitta call da (~10 sek tejash)
2. quality: "low" (~2-3x tezroq)
3. 2 ta variant parallel generatsiya (asyncio, ~30-40 sek tejash)
4. Progress bar + bosqichlar animatsiya

Narx: ~$0.014 per so'rov (2 variant, gpt-image-2 low)
"""

import os
import io
import base64
import logging
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    BufferedInputFile,
    InputMediaPhoto,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand,
)
from aiogram.enums import ParseMode
from openai import OpenAI
from PIL import Image

# ── Sozlamalar ───────────────────────────────────────────────────
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

# Thread pool for parallel API calls
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
            "Bu bot mahsulot rasmingizni professional marketplace\n"
            "infografik rasmga aylantirib beradi.\n\n"
            "📸 <b>Qanday ishlaydi:</b>\n"
            "1. Mahsulot rasmini yuboring\n"
            "2. AI mahsulotni tahlil qiladi\n"
            "3. 2 ta variant tayyorlab beradi\n\n"
            "📐 Rasm: 3:4 (marketplace standart)\n"
            "🏪 Uzum, Wildberries uchun tayyor\n\n"
            "Boshlash uchun interfeys tilini tanlang 👇"
        ),
        "choose_text_lang": "📝 Infografik ichidagi yozuvlar qaysi tilda bo'lsin?",
        "setup_done": (
            "✅ <b>Sozlamalar saqlandi!</b>\n\n"
            "Endi menga mahsulot rasmini yuboring — "
            "men uni infografik rasmga aylantirib beraman.\n\n"
            "📸 Rasmni oddiy rasm sifatida yuboring"
        ),
        "photo_received": "🎨 <b>Rasmingiz qabul qilindi!</b>",
        "done": "✅ <b>2 ta variant tayyor!</b>\n\n📐 Marketplace uchun tayyor\n🔄 Yana rasm yuboring!",
        "done_single": "✅ <b>Infografik tayyor!</b>\n🔄 Yana rasm yuboring!",
        "download": "💾 Yuklab olish",
        "send_photo": "📸 Menga <b>mahsulot rasmini</b> yuboring!",
        "send_as_photo": "📸 Rasmni <b>fayl sifatida emas</b>, oddiy rasm sifatida yuboring!",
        "busy": "⏳ Oldingi rasmingiz hali tayyor bo'lmadi. Kuting...",
        "error": "❌ <b>Xatolik yuz berdi</b>",
        "error_billing": "💳 OpenAI hisobida mablag' yetarli emas.",
        "error_rate": "⏱ Juda ko'p so'rov. 1 daqiqadan keyin urinib ko'ring.",
        "error_safety": "🚫 Rasm safety filtriga tushdi. Boshqa rasm yuboring.",
        "error_copyright": (
            "⚠️ <b>Litsenziyalangan personaj aniqlandi</b>\n\n"
            "🔍 Aniqlangan: <code>{keyword}</code>\n\n"
            "OpenAI copyright personajlar (Disney, Marvel, Pokemon va h.k.) "
            "bilan infografik yaratishni taqiqlaydi.\n\n"
            "📸 Copyright personajsiz mahsulot rasmini yuboring."
        ),
        "help": (
            "📖 <b>Yordam</b>\n\n"
            "🔹 Mahsulot rasmini yuboring\n"
            "🔹 AI tahlil + infografik yaratadi\n"
            "🔹 ~40-60 soniyada 2 ta variant tayyor\n\n"
            "⚙️ Sozlamalar — tilni o'zgartirish\n"
            "⚠️ Bir vaqtda bitta rasm yuboring"
        ),
        # Progress bar bosqichlari
        "progress": [
            {"bar": "▓▓░░░░░░░░", "pct": "15%", "stage": "🔍 Mahsulot tahlil qilinmoqda...", "tip": "💡 Professional infografik sotuvni 40% ga oshiradi!"},
            {"bar": "▓▓▓▓░░░░░░", "pct": "35%", "stage": "✏️ Dizayn prompti yaratilmoqda...", "tip": "📸 AI mahsulotga mos rang va uslub tanlaydi"},
            {"bar": "▓▓▓▓▓░░░░░", "pct": "50%", "stage": "🎨 Fon va kompozitsiya tanlanmoqda...", "tip": "🏪 Rasm Uzum Market standartiga mos bo'ladi"},
            {"bar": "▓▓▓▓▓▓░░░░", "pct": "60%", "stage": "🖼 Infografik generatsiya qilinmoqda...", "tip": "⏱ Taxminan 30 soniya qoldi..."},
            {"bar": "▓▓▓▓▓▓▓░░░", "pct": "70%", "stage": "✨ Matn va elementlar joylashtirilmoqda...", "tip": "📝 Yozuvlar imlo xatosiz bo'ladi"},
            {"bar": "▓▓▓▓▓▓▓▓░░", "pct": "80%", "stage": "🔧 Sifat tekshirilmoqda...", "tip": "🎯 2 ta variant tayyorlanmoqda"},
            {"bar": "▓▓▓▓▓▓▓▓▓░", "pct": "90%", "stage": "📦 Rasmlar tayyorlanmoqda...", "tip": "✅ Deyarli tayyor!"},
        ],
    },
    "ru": {
        "welcome": (
            "🎨 <b>Marketplace Инфографик Бот</b>\n\n"
            "Этот бот превращает фото товара в профессиональную\n"
            "инфографику для маркетплейса.\n\n"
            "📸 <b>Как это работает:</b>\n"
            "1. Отправьте фото товара\n"
            "2. ИИ проанализирует товар\n"
            "3. Подготовит 2 варианта\n\n"
            "📐 Размер: 3:4 (стандарт маркетплейса)\n"
            "🏪 Готово для Uzum, Wildberries\n\n"
            "Для начала выберите язык интерфейса 👇"
        ),
        "choose_text_lang": "📝 На каком языке должен быть текст на инфографике?",
        "setup_done": (
            "✅ <b>Настройки сохранены!</b>\n\n"
            "Теперь отправьте мне фото товара — "
            "я превращу его в инфографику.\n\n"
            "📸 Отправьте фото как обычное изображение"
        ),
        "photo_received": "🎨 <b>Фото получено!</b>",
        "done": "✅ <b>2 варианта готовы!</b>\n\n📐 Готово для маркетплейса\n🔄 Отправьте ещё фото!",
        "done_single": "✅ <b>Инфографика готова!</b>\n🔄 Отправьте ещё фото!",
        "download": "💾 Скачать",
        "send_photo": "📸 Отправьте мне <b>фото товара</b>!",
        "send_as_photo": "📸 Отправьте как <b>обычное фото</b>, не как файл!",
        "busy": "⏳ Предыдущее фото ещё обрабатывается. Подождите...",
        "error": "❌ <b>Произошла ошибка</b>",
        "error_billing": "💳 Недостаточно средств на счёте OpenAI.",
        "error_rate": "⏱ Слишком много запросов. Попробуйте через минуту.",
        "error_safety": "🚫 Фото заблокировано фильтром. Отправьте другое фото.",
        "error_copyright": (
            "⚠️ <b>Обнаружен лицензированный персонаж</b>\n\n"
            "🔍 Найдено: <code>{keyword}</code>\n\n"
            "OpenAI запрещает генерацию с персонажами "
            "(Disney, Marvel, Pokemon и др.).\n\n"
            "📸 Отправьте фото без лицензированных персонажей."
        ),
        "help": (
            "📖 <b>Помощь</b>\n\n"
            "🔹 Отправьте фото товара\n"
            "🔹 ИИ анализирует + создаёт инфографику\n"
            "🔹 2 варианта за ~40-60 секунд\n\n"
            "⚙️ Настройки — сменить язык\n"
            "⚠️ Отправляйте по одному фото"
        ),
        "progress": [
            {"bar": "▓▓░░░░░░░░", "pct": "15%", "stage": "🔍 Анализ товара...", "tip": "💡 Качественная инфографика увеличивает продажи на 40%!"},
            {"bar": "▓▓▓▓░░░░░░", "pct": "35%", "stage": "✏️ Создание промпта...", "tip": "📸 ИИ подбирает цвета и стиль под товар"},
            {"bar": "▓▓▓▓▓░░░░░", "pct": "50%", "stage": "🎨 Выбор фона и композиции...", "tip": "🏪 Изображение будет соответствовать стандартам Uzum Market"},
            {"bar": "▓▓▓▓▓▓░░░░", "pct": "60%", "stage": "🖼 Генерация инфографики...", "tip": "⏱ Примерно 30 секунд..."},
            {"bar": "▓▓▓▓▓▓▓░░░", "pct": "70%", "stage": "✨ Размещение текста и элементов...", "tip": "📝 Тексты без орфографических ошибок"},
            {"bar": "▓▓▓▓▓▓▓▓░░", "pct": "80%", "stage": "🔧 Проверка качества...", "tip": "🎯 Готовятся 2 варианта"},
            {"bar": "▓▓▓▓▓▓▓▓▓░", "pct": "90%", "stage": "📦 Подготовка изображений...", "tip": "✅ Почти готово!"},
        ],
    },
}


def t(user_id: int, key: str, **kwargs) -> str:
    lang = user_settings.get(user_id, {}).get("ui_lang", "uz")
    text = TEXTS.get(lang, TEXTS["uz"]).get(key, key)
    if isinstance(text, str) and kwargs:
        text = text.format(**kwargs)
    return text


def get_text_lang(user_id: int) -> str:
    return user_settings.get(user_id, {}).get("text_lang", "ru")


def get_progress(user_id: int, step: int) -> str:
    lang = user_settings.get(user_id, {}).get("ui_lang", "uz")
    stages = TEXTS.get(lang, TEXTS["uz"])["progress"]
    idx = min(step, len(stages) - 1)
    s = stages[idx]
    return (
        f"🎨 <b>Infografik yaratilmoqda</b>\n\n"
        f"{s['bar']}  {s['pct']}\n\n"
        f"{s['stage']}\n\n"
        f"{s['tip']}"
    )


# ══════════════════════════════════════════════════════════════════
# 1-BOSQICH: Mahsulotni tahlil qilish (alohida call)
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
- Decorative elements:

7. Key Selling Points:
- Main marketing message:
- Target audience:

IMPORTANT:
- Do NOT hallucinate brand details if not visible
- If brand IS visible, write it EXACTLY as shown — do NOT translate
- Keep descriptions short and precise
- Focus on visual and structural analysis only"""


def analyze_product(image_bytes: bytes) -> str:
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"}},
                {"type": "text", "text": ANALYSIS_PROMPT},
            ],
        }],
        max_tokens=1000,
        temperature=0.3,
    )
    analysis = response.choices[0].message.content.strip()
    logger.info(f"Analysis done ({len(analysis)} chars)")
    return analysis


# ══════════════════════════════════════════════════════════════════
# 2-BOSQICH: Tahlil asosida generation prompt yozish (alohida call)
# ══════════════════════════════════════════════════════════════════

def get_prompt_writer_system(text_lang: str) -> str:
    if text_lang == "uz":
        lang_rule = "ALL text on the infographic must be in UZBEK language with PERFECT spelling."
        banned = """BANNED: "aksiya", "bepul", "buyurtma berish", "sotib olish", "keshbek", "yangilik", "new", "asl nusxa", "sotuv", "sale", "chegirma", "trend", "top", "xit", "eng yaxshi", "1-raqamli", "arzon", "foydali narx"."""
    else:
        lang_rule = "ALL text on the infographic must be in RUSSIAN language with PERFECT spelling."
        banned = """BANNED: "акция", "бесплатно", "заказать", "купить", "кешбэк", "новинка", "new", "оригинал", "распродажа", "sale", "скидка", "тренд", "топ", "хит", "лучший", "№1", "лидер продаж", "дёшево", "выгодная цена"."""

    return f"""You are an expert marketplace infographic prompt engineer.

You will receive a structured product analysis. Based on it, write a DETAILED image generation prompt in English.

YOUR OUTPUT MUST BE ONLY THE PROMPT TEXT. No explanations, no markdown, no backticks.

Write the prompt following this structure:

---

Create a high-end product infographic advertisement based on the following analysis:

[INSERT THE FULL ANALYSIS HERE]

Requirements:
- Clean, modern, minimalistic advertising design
- Perfect, readable typography (NO distorted or broken text)
- Correct grammar and professional wording

Design details:
- Background: improved style (more realistic, more depth)
- Lighting: soft studio lighting with realistic reflections
- Product: ultra-realistic, sharp, slightly tilted for depth
- Colors: consistent palette, premium look

Text:
{lang_rule}
- Put every text element in "quotes" for accurate rendering
- Keep SHORT: 2-4 words titles, 5-8 words descriptions
- NO CapsLock except brand names
- NO emoji in image text

Features:
- 3-4 feature points with minimal icons on LEFT side
- Each: icon + bold title + short description
- VERTICALLY arranged (list style)
- NO bottom 3 blocks/cards

Layout (3:4 portrait):
- Product as hero image (center/right, ~50-60%)
- Headline top-left, large bold text
- Subheadline below, smaller
- Features list on left side
- Badge (volume/size) on right if applicable
- Clean bottom with closing tagline

Extras:
- Subtle realistic elements depending on product
- Marketplace compliant (Uzum, Wildberries style)

Quality:
- Ultra realistic, commercial advertising quality
- No artifacts, no text distortion, no misspellings

⚠️ UZUM MARKET RULES:
{banned}
- NO comparative/superlative claims
- NO excessive punctuation
- Brand names in ORIGINAL form — NEVER translate
- Do NOT add brand names that are NOT in the analysis

CRITICAL:
1. ALL text spelled PERFECTLY
2. Put all text in "quotes"
3. NEVER add brand names not mentioned in analysis
4. NEVER use banned words
"""


def write_generation_prompt(analysis: str, text_lang: str) -> str:
    system = get_prompt_writer_system(text_lang)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Based on this product analysis, write the image generation prompt:\n\n{analysis}"},
        ],
        max_tokens=2000,
        temperature=0.7,
    )
    prompt = response.choices[0].message.content.strip()
    logger.info(f"Prompt written ({len(prompt)} chars)")
    return prompt


# ── Copyright tekshiruv ──────────────────────────────────────────
COPYRIGHT_KEYWORDS = [
    "disney", "stitch", "angel", "mickey", "minnie", "frozen", "elsa",
    "marvel", "spider-man", "spiderman", "avengers", "iron man",
    "dc comics", "batman", "superman", "wonder woman",
    "pokemon", "pikachu", "naruto", "dragon ball", "goku",
    "hello kitty", "sanrio", "pixar", "toy story", "finding nemo",
    "star wars", "nintendo", "mario", "sonic", "peppa pig",
    "paw patrol", "barbie", "transformers", "lego",
    "looney tunes", "tom and jerry", "spongebob",
]


def check_copyright(prompt: str) -> str | None:
    lower = prompt.lower()
    for keyword in COPYRIGHT_KEYWORDS:
        if keyword in lower:
            return keyword
    return None


# ══════════════════════════════════════════════════════════════════
# PARALLEL RASM GENERATSIYA (gpt-image-2, low)
# ══════════════════════════════════════════════════════════════════

def _generate_single(image_bytes: bytes, prompt: str) -> bytes:
    """Bitta variant generatsiya (sync, thread ichida ishlaydi)"""
    image_file = io.BytesIO(image_bytes)
    image_file.name = "product.jpg"

    response = client.images.edit(
        model="gpt-image-2",
        image=[image_file],
        prompt=prompt,
        n=1,
        size="1056x1408",
        quality="low",
    )

    png_bytes = base64.b64decode(response.data[0].b64_json)
    # PNG → JPEG kompressiya
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    jpg_buf = io.BytesIO()
    img.save(jpg_buf, format="JPEG", quality=90, optimize=True)
    jpg_buf.seek(0)
    return jpg_buf.read()


async def generate_variants_parallel(image_bytes: bytes, prompt: str) -> list[bytes]:
    """2 ta variantni PARALLEL generatsiya qiladi"""
    loop = asyncio.get_event_loop()

    # 2 ta so'rovni parallel yuborish
    task1 = loop.run_in_executor(executor, _generate_single, image_bytes, prompt)
    task2 = loop.run_in_executor(executor, _generate_single, image_bytes, prompt)

    results = await asyncio.gather(task1, task2, return_exceptions=True)

    variants = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Variant {i+1} xatolik: {result}")
        else:
            variants.append(result)
            logger.info(f"Variant {i+1} tayyor ({len(result)} bytes)")

    if not variants:
        # Ikkala variant ham xato — birinchi xatoni raise
        raise results[0]

    return variants


# ══════════════════════════════════════════════════════════════════
# PROGRESS BAR YANGILASH
# ══════════════════════════════════════════════════════════════════

async def update_progress(wait_msg, user_id: int, stop_event: asyncio.Event):
    """Har 7 sekundda progress barni yangilaydi"""
    step = 0
    while not stop_event.is_set():
        try:
            text = get_progress(user_id, step)
            await wait_msg.edit_text(text, parse_mode=ParseMode.HTML)
        except Exception:
            pass
        step += 1
        # 7 sekund kutish yoki stop signal
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=7)
            break
        except asyncio.TimeoutError:
            continue


# ══════════════════════════════════════════════════════════════════
# TELEGRAM HANDLERLARI
# ══════════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    welcome = (
        "🎨 <b>Marketplace Infografik Bot</b>\n\n"
        "🇺🇿 Bu bot mahsulot rasmini professional infografik rasmga aylantiradi.\n"
        "🇷🇺 Этот бот превращает фото товара в профессиональную инфографику.\n\n"
        "Tilni tanlang / Выберите язык 👇"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_ui_uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ui_ru"),
        ]
    ])
    await message.answer(welcome, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(F.data.startswith("lang_ui_"))
async def choose_ui_lang(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = callback.data.replace("lang_ui_", "")
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id]["ui_lang"] = lang
    await callback.answer()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_text_uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_text_ru"),
        ]
    ])
    await callback.message.edit_text(
        t(user_id, "choose_text_lang"),
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("lang_text_"))
async def choose_text_lang(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = callback.data.replace("lang_text_", "")
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id]["text_lang"] = lang
    await callback.answer()

    reply_kb = get_reply_keyboard(user_id)
    await callback.message.edit_text(
        t(user_id, "setup_done"),
        parse_mode=ParseMode.HTML,
    )
    await callback.message.answer(
        t(user_id, "send_photo"),
        parse_mode=ParseMode.HTML,
        reply_markup=reply_kb,
    )


def get_reply_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    lang = user_settings.get(user_id, {}).get("ui_lang", "uz")
    if lang == "ru":
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="❓ Помощь")]],
            resize_keyboard=True,
        )
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⚙️ Sozlamalar"), KeyboardButton(text="❓ Yordam")]],
        resize_keyboard=True,
    )


@router.message(Command("settings"))
async def cmd_settings(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_ui_uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ui_ru"),
        ]
    ])
    await message.answer("🌐 Tilni tanlang / Выберите язык:", reply_markup=kb)


@router.message(F.text.in_(["⚙️ Sozlamalar", "⚙️ Настройки"]))
async def btn_settings(message: types.Message):
    await cmd_settings(message)


@router.message(F.text.in_(["❓ Yordam", "❓ Помощь"]))
async def btn_help(message: types.Message):
    await message.answer(t(message.from_user.id, "help"), parse_mode=ParseMode.HTML)


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(t(message.from_user.id, "help"), parse_mode=ParseMode.HTML)


# ── ASOSIY: Rasm qabul qilish ───────────────────────────────────
@router.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id

    if user_id not in user_settings or "text_lang" not in user_settings.get(user_id, {}):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_ui_uz"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ui_ru"),
            ]
        ])
        await message.answer("⚙️ Avval tilni tanlang / Сначала выберите язык:", reply_markup=kb)
        return

    if user_tasks.get(user_id):
        await message.answer(t(user_id, "busy"))
        return

    user_tasks[user_id] = True
    user_msg_id = message.message_id

    # Boshlang'ich progress
    wait_msg = await message.answer(
        get_progress(user_id, 0),
        parse_mode=ParseMode.HTML,
    )

    # Progress yangilash taskini boshlash
    stop_progress = asyncio.Event()
    progress_task = asyncio.create_task(update_progress(wait_msg, user_id, stop_progress))

    try:
        # Rasmni yuklash
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        raw = await bot.download_file(file.file_path)
        image_bytes = raw.read()
        logger.info(f"Rasm: user={user_id}, bytes={len(image_bytes)}")

        # 1-bosqich: Tahlil
        text_lang = get_text_lang(user_id)
        analysis = analyze_product(image_bytes)
        logger.info(f"Analysis:\n{analysis}")

        # Copyright tekshiruv
        copyright_match = check_copyright(analysis)
        if copyright_match:
            stop_progress.set()
            await progress_task
            logger.warning(f"Copyright: {copyright_match}, user={user_id}")
            await wait_msg.edit_text(
                t(user_id, "error_copyright", keyword=copyright_match),
                parse_mode=ParseMode.HTML,
            )
            return

        # 2-bosqich: Prompt
        prompt = write_generation_prompt(analysis, text_lang)
        logger.info(f"Prompt:\n{prompt}")

        # 2-bosqich: 2 ta variant PARALLEL generatsiya
        variants = await generate_variants_parallel(image_bytes, prompt)

        # Progress to'xtatish
        stop_progress.set()
        await progress_task

        logger.info(f"{len(variants)} variant: user={user_id}")

        # Natijalarni yuborish
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if len(variants) >= 2:
            media_group = [
                InputMediaPhoto(
                    media=BufferedInputFile(file=variants[0], filename=f"v1_{user_id}_{timestamp}.jpg"),
                    caption=t(user_id, "done"),
                    parse_mode=ParseMode.HTML,
                ),
                InputMediaPhoto(
                    media=BufferedInputFile(file=variants[1], filename=f"v2_{user_id}_{timestamp}.jpg"),
                ),
            ]
            await message.answer_media_group(media=media_group)

            for i, variant in enumerate(variants):
                await message.answer_document(
                    document=BufferedInputFile(file=variant, filename=f"infographic_{i+1}_{user_id}_{timestamp}.jpg"),
                    caption=f"{t(user_id, 'download')} — Variant {i+1}",
                )
        else:
            await message.answer_photo(
                photo=BufferedInputFile(file=variants[0], filename=f"inf_{user_id}_{timestamp}.jpg"),
                caption=t(user_id, "done_single"),
                parse_mode=ParseMode.HTML,
            )
            await message.answer_document(
                document=BufferedInputFile(file=variants[0], filename=f"infographic_{user_id}_{timestamp}.jpg"),
                caption=t(user_id, "download"),
            )

        # Original rasmni o'chirish
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=user_msg_id)
        except Exception:
            pass

        await wait_msg.delete()

    except Exception as e:
        stop_progress.set()
        await progress_task

        logger.error(f"Xatolik: user={user_id}, error={e}")
        err_str = str(e).lower()

        if "billing" in err_str or "quota" in err_str or "insufficient" in err_str:
            error_msg = t(user_id, "error_billing")
        elif "rate_limit" in err_str:
            error_msg = t(user_id, "error_rate")
        elif "moderation" in err_str or "safety" in err_str or "content_policy" in err_str:
            error_msg = t(user_id, "error_safety")
        else:
            error_msg = f"<code>{str(e)[:300]}</code>"

        await wait_msg.edit_text(
            f"{t(user_id, 'error')}\n\n{error_msg}",
            parse_mode=ParseMode.HTML,
        )

    finally:
        user_tasks.pop(user_id, None)


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: types.Message):
    text = message.text
    if text in ["⚙️ Sozlamalar", "⚙️ Настройки", "❓ Yordam", "❓ Помощь"]:
        return  # Bu handlerlar yuqorida ishlaydi
    await message.answer(t(message.from_user.id, "send_photo"), parse_mode=ParseMode.HTML)


@router.message(F.document)
async def handle_document(message: types.Message):
    doc = message.document
    if doc.mime_type and doc.mime_type.startswith("image/"):
        user_id = message.from_user.id

        if user_id not in user_settings or "text_lang" not in user_settings.get(user_id, {}):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_ui_uz"),
                    InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ui_ru"),
                ]
            ])
            await message.answer("⚙️ Avval tilni tanlang:", reply_markup=kb)
            return

        if user_tasks.get(user_id):
            await message.answer(t(user_id, "busy"))
            return

        user_tasks[user_id] = True
        stop_progress = asyncio.Event()
        wait_msg = await message.answer(get_progress(user_id, 0), parse_mode=ParseMode.HTML)
        progress_task = asyncio.create_task(update_progress(wait_msg, user_id, stop_progress))

        try:
            file = await bot.get_file(doc.file_id)
            raw = await bot.download_file(file.file_path)
            image_bytes = raw.read()

            text_lang = get_text_lang(user_id)
            analysis = analyze_product(image_bytes)

            copyright_match = check_copyright(analysis)
            if copyright_match:
                stop_progress.set()
                await progress_task
                await wait_msg.edit_text(t(user_id, "error_copyright", keyword=copyright_match), parse_mode=ParseMode.HTML)
                return

            prompt = write_generation_prompt(analysis, text_lang)

            variants = await generate_variants_parallel(image_bytes, prompt)
            stop_progress.set()
            await progress_task

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            if len(variants) >= 2:
                media_group = [
                    InputMediaPhoto(
                        media=BufferedInputFile(file=variants[0], filename=f"v1_{user_id}_{timestamp}.jpg"),
                        caption=t(user_id, "done"),
                        parse_mode=ParseMode.HTML,
                    ),
                    InputMediaPhoto(
                        media=BufferedInputFile(file=variants[1], filename=f"v2_{user_id}_{timestamp}.jpg"),
                    ),
                ]
                await message.answer_media_group(media=media_group)
                for i, v in enumerate(variants):
                    await message.answer_document(
                        document=BufferedInputFile(file=v, filename=f"infographic_{i+1}_{user_id}_{timestamp}.jpg"),
                        caption=f"{t(user_id, 'download')} — Variant {i+1}",
                    )
            else:
                await message.answer_photo(
                    photo=BufferedInputFile(file=variants[0], filename=f"inf_{user_id}.jpg"),
                    caption=t(user_id, "done_single"),
                    parse_mode=ParseMode.HTML,
                )

            try:
                await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            except Exception:
                pass
            await wait_msg.delete()

        except Exception as e:
            stop_progress.set()
            await progress_task
            logger.error(f"Xatolik: user={user_id}, error={e}")
            err_str = str(e).lower()
            if "billing" in err_str or "quota" in err_str:
                error_msg = t(user_id, "error_billing")
            elif "moderation" in err_str or "safety" in err_str:
                error_msg = t(user_id, "error_safety")
            else:
                error_msg = f"<code>{str(e)[:300]}</code>"
            await wait_msg.edit_text(f"{t(user_id, 'error')}\n\n{error_msg}", parse_mode=ParseMode.HTML)
        finally:
            user_tasks.pop(user_id, None)
    else:
        await message.answer(t(message.from_user.id, "send_as_photo"), parse_mode=ParseMode.HTML)


# ── Ishga tushirish ──────────────────────────────────────────────
async def main():
    dp.include_router(router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Botni boshlash / Запустить бота"),
        BotCommand(command="settings", description="Til sozlamalari / Настройки языка"),
        BotCommand(command="help", description="Yordam / Помощь"),
    ])

    logger.info("=" * 50)
    logger.info("🚀 Marketplace Infografik Bot v8")
    logger.info("📊 Tahlil: gpt-4o-mini (alohida)")
    logger.info("📊 Prompt: gpt-4o-mini (alohida)")
    logger.info("📊 Rasm: gpt-image-2 (low, parallel)")
    logger.info("📐 Output: 1056x1408 (3:4)")
    logger.info("🔢 Variantlar: 2 ta (parallel)")
    logger.info("🌐 Tillar: UZ / RU")
    logger.info("💰 Narx: ~$0.014 per so'rov")
    logger.info("=" * 50)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())