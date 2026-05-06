"""
Marketplace Infografik Bot v7
==============================
Yangi funksiyalar:
- Interfeys tili tanlash (O'zbek / Rus)
- Infografik ichidagi yozuvlar tilini tanlash
- Yuklab olish tugmasi
- User yuklagan rasm o'chiriladi (hajm tejash)
- Qisqacha bot tavsifi 2 tilda

Narx: ~$0.085 per so'rov (2 variant, gpt-image-2 medium)
"""

import os
import io
import base64
import logging
from datetime import datetime

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

# ── Foydalanuvchi holatlari ──────────────────────────────────────
user_tasks = {}       # {user_id: True} — rasm qayta ishlanmoqda
user_settings = {}    # {user_id: {"ui_lang": "uz"/"ru", "text_lang": "uz"/"ru"}}


# ══════════════════════════════════════════════════════════════════
# TILLAR (UI matnlari)
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
        "choose_text_lang": (
            "📝 Infografik ichidagi yozuvlar qaysi tilda bo'lsin?"
        ),
        "setup_done": (
            "✅ <b>Sozlamalar saqlandi!</b>\n\n"
            "Endi menga mahsulot rasmini yuboring — "
            "men uni infografik rasmga aylantirib beraman.\n\n"
            "📸 Rasmni oddiy rasm sifatida yuboring"
        ),
        "photo_received": "🎨 <b>Rasmingiz qabul qilindi!</b>",
        "step_analysis": "⏳ 1/3 — Mahsulot tahlil qilinmoqda...",
        "step_prompt": "✅ Tahlil tayyor\n⏳ 2/3 — Prompt yaratilmoqda...",
        "step_generating": "✅ Prompt tayyor\n⏳ 3/3 — 2 ta variant yaratilmoqda...\n\n⏱ 30-60 soniya",
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
            "🔹 AI 3 bosqichda ishlaydi\n"
            "🔹 30-60 soniyada 2 ta variant tayyor\n\n"
            "⚙️ /settings — tilni o'zgartirish\n"
            "⚠️ Bir vaqtda bitta rasm yuboring"
        ),
        "settings_updated": "✅ Til o'zgartirildi!",
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
        "choose_text_lang": (
            "📝 На каком языке должен быть текст на инфографике?"
        ),
        "setup_done": (
            "✅ <b>Настройки сохранены!</b>\n\n"
            "Теперь отправьте мне фото товара — "
            "я превращу его в инфографику.\n\n"
            "📸 Отправьте фото как обычное изображение"
        ),
        "photo_received": "🎨 <b>Фото получено!</b>",
        "step_analysis": "⏳ 1/3 — Анализ товара...",
        "step_prompt": "✅ Анализ готов\n⏳ 2/3 — Создание промпта...",
        "step_generating": "✅ Промпт готов\n⏳ 3/3 — Генерация 2 вариантов...\n\n⏱ 30-60 секунд",
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
            "OpenAI запрещает генерацию инфографики с персонажами "
            "(Disney, Marvel, Pokemon и др.).\n\n"
            "📸 Отправьте фото товара без лицензированных персонажей."
        ),
        "help": (
            "📖 <b>Помощь</b>\n\n"
            "🔹 Отправьте фото товара\n"
            "🔹 ИИ работает в 3 этапа\n"
            "🔹 2 варианта за 30-60 секунд\n\n"
            "⚙️ /settings — сменить язык\n"
            "⚠️ Отправляйте по одному фото"
        ),
        "settings_updated": "✅ Язык изменён!",
    },
}


def t(user_id: int, key: str, **kwargs) -> str:
    """Foydalanuvchi tiliga mos matn qaytaradi"""
    lang = user_settings.get(user_id, {}).get("ui_lang", "uz")
    text = TEXTS.get(lang, TEXTS["uz"]).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text


def get_text_lang(user_id: int) -> str:
    """Infografik ichidagi yozuvlar tilini qaytaradi"""
    return user_settings.get(user_id, {}).get("text_lang", "ru")


# ══════════════════════════════════════════════════════════════════
# 1-BOSQICH: Mahsulotni tahlil qilish
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
List all visible feature points:
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
- Do not hallucinate brand details if not visible
- If brand name IS visible, write it EXACTLY as shown (do NOT translate or modify brand names)
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


def check_copyright(analysis: str) -> str | None:
    lower = analysis.lower()
    for keyword in COPYRIGHT_KEYWORDS:
        if keyword in lower:
            return keyword
    return None


# ══════════════════════════════════════════════════════════════════
# 2-BOSQICH: Generation prompt yozish
# ══════════════════════════════════════════════════════════════════

def get_prompt_writer_system(text_lang: str) -> str:
    """Tanlangan tilga mos prompt writer system"""

    if text_lang == "uz":
        lang_instruction = """Text:
- ALL text on the infographic must be in UZBEK language
- ALL Uzbek text must have PERFECT spelling — ZERO errors allowed
- Put every Uzbek text element in "quotes" in the prompt for accurate rendering
- Keep it short, clean, and impactful
- Use bold modern sans-serif font, high contrast, easy to read"""
        banned_words = """
BANNED WORDS (Uzum Market rules — never use in any text):
- "aksiya", "bepul", "buyurtma berish", "sotib olish", "keshbek"
- "yangilik", "new", "asl nusxa", "sotuv", "sale", "chegirma", "trend", "top", "xit"
BANNED PHRASES:
- "eng yaxshi", "1-raqamli", "savdo lideri", "bozorda o'xshashi yo'q"
- "arzon", "foydali narx", "hamyonbop"
"""
    else:
        lang_instruction = """Text:
- ALL text on the infographic must be in RUSSIAN language
- ALL Russian text must have PERFECT spelling — ZERO errors allowed
- Put every Russian text element in "quotes" in the prompt for accurate rendering
- Keep it short, clean, and impactful
- Use bold modern sans-serif font, high contrast, easy to read"""
        banned_words = """
BANNED WORDS (Uzum Market rules — never use in any text):
- "акция", "бесплатно", "заказать", "купить", "кешбэк"
- "новинка", "new", "оригинал", "распродажа", "sale", "скидка", "тренд", "топ", "хит"
BANNED PHRASES:
- "лучший", "лучше чем", "№1", "лидер продаж", "нет аналогов", "все выбирают"
- "дёшево", "выгодная цена", "доступная цена"
"""

    return f"""You are an expert marketplace infographic prompt engineer.

You will receive a structured product analysis. Based on it, write a DETAILED image generation prompt in English.

YOUR OUTPUT MUST BE ONLY THE PROMPT TEXT. No explanations, no markdown, no backticks, no preamble.

Write the prompt following this EXACT structure:

---

Create a high-end product infographic advertisement based on the following analysis:

[INSERT THE FULL ANALYSIS HERE - copy all 7 sections exactly]

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

{lang_instruction}

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
{banned_words}
OTHER RULES:
- NO CapsLock except for brand names, model names
- NO emoji in text on the image
- NO excessive punctuation
- Brand names must be kept in ORIGINAL form — NEVER translate brand names

---

CRITICAL RULES:
1. Insert the FULL analysis into the prompt
2. ALL text must be spelled PERFECTLY — marketplace will reject if even one letter is wrong
3. Put all text in "quotes" for accurate rendering
4. NO bottom 3 usage blocks/cards — use vertical feature list instead
5. Keep text SHORT (2-4 words for titles, 5-8 words for descriptions)
6. NEVER translate brand names
7. NEVER use banned words/phrases listed above
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


# ══════════════════════════════════════════════════════════════════
# 3-BOSQICH: Rasm generatsiya (gpt-image-2)
# ══════════════════════════════════════════════════════════════════

def generate_variants(image_bytes: bytes, prompt: str) -> list[bytes]:
    image_file = io.BytesIO(image_bytes)
    image_file.name = "product.png"
    response = client.images.edit(
        model="gpt-image-2",
        image=[image_file],
        prompt=prompt,
        n=2,
        size="1056x1408",
        quality="low",
    )
    results = [base64.b64decode(item.b64_json) for item in response.data]
    logger.info(f"{len(results)} variant tayyor")
    return results


# ══════════════════════════════════════════════════════════════════
# TELEGRAM HANDLERLARI
# ══════════════════════════════════════════════════════════════════

# ── /start ───────────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(message: types.Message):
    # 2 tildagi welcome + til tanlash tugmalari
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


# ── UI til tanlash callback ──────────────────────────────────────
@router.callback_query(F.data.startswith("lang_ui_"))
async def choose_ui_lang(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = callback.data.replace("lang_ui_", "")  # "uz" or "ru"

    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id]["ui_lang"] = lang

    await callback.answer()

    # Infografik yozuvlar tilini so'rash
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


# ── Infografik yozuvlar tili callback ────────────────────────────
@router.callback_query(F.data.startswith("lang_text_"))
async def choose_text_lang(callback: CallbackQuery):
    user_id = callback.from_user.id
    lang = callback.data.replace("lang_text_", "")

    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id]["text_lang"] = lang

    await callback.answer()

    # Reply keyboard — doim ko'rinadigan tugmalar
    reply_kb = get_reply_keyboard(user_id)

    await callback.message.edit_text(
        t(user_id, "setup_done"),
        parse_mode=ParseMode.HTML,
    )
    # Reply keyboard alohida xabarda yuboriladi (edit_text da ishlamaydi)
    await callback.message.answer(
        t(user_id, "send_photo"),
        parse_mode=ParseMode.HTML,
        reply_markup=reply_kb,
    )


def get_reply_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Foydalanuvchi tiliga mos reply keyboard"""
    lang = user_settings.get(user_id, {}).get("ui_lang", "uz")
    if lang == "ru":
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="❓ Помощь")],
            ],
            resize_keyboard=True,
        )
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚙️ Sozlamalar"), KeyboardButton(text="❓ Yordam")],
        ],
        resize_keyboard=True,
    )


# ── /settings ────────────────────────────────────────────────────
@router.message(Command("settings"))
async def cmd_settings(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_ui_uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ui_ru"),
        ]
    ])
    await message.answer(
        "🌐 Tilni tanlang / Выберите язык:",
        reply_markup=kb,
    )


# ── Reply keyboard tugmalari handlerlari ─────────────────────────
@router.message(F.text.in_(["⚙️ Sozlamalar", "⚙️ Настройки"]))
async def btn_settings(message: types.Message):
    await cmd_settings(message)


@router.message(F.text.in_(["❓ Yordam", "❓ Помощь"]))
async def btn_help(message: types.Message):
    await message.answer(t(message.from_user.id, "help"), parse_mode=ParseMode.HTML)


# ── /help ────────────────────────────────────────────────────────
@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(t(message.from_user.id, "help"), parse_mode=ParseMode.HTML)


# ── Rasm qabul qilish ───────────────────────────────────────────
@router.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id

    # Til sozlanmagan bo'lsa, /start ga yo'naltirish
    if user_id not in user_settings or "text_lang" not in user_settings.get(user_id, {}):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang_ui_uz"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ui_ru"),
            ]
        ])
        await message.answer(
            "⚙️ Avval tilni tanlang / Сначала выберите язык:",
            reply_markup=kb,
        )
        return

    if user_tasks.get(user_id):
        await message.answer(t(user_id, "busy"))
        return

    user_tasks[user_id] = True
    user_msg_id = message.message_id  # O'chirish uchun saqlash

    wait_msg = await message.answer(
        f"{t(user_id, 'photo_received')}\n\n{t(user_id, 'step_analysis')}",
        parse_mode=ParseMode.HTML,
    )

    try:
        # Rasmni yuklash
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        raw = await bot.download_file(file.file_path)
        image_bytes = raw.read()
        logger.info(f"Rasm: user={user_id}, bytes={len(image_bytes)}")

        # 1-bosqich: Tahlil
        analysis = analyze_product(image_bytes)
        logger.info(f"Analysis:\n{analysis}")

        # Copyright tekshiruv
        copyright_match = check_copyright(analysis)
        if copyright_match:
            logger.warning(f"Copyright: {copyright_match}, user={user_id}")
            await wait_msg.edit_text(
                t(user_id, "error_copyright", keyword=copyright_match),
                parse_mode=ParseMode.HTML,
            )
            return

        await wait_msg.edit_text(
            f"{t(user_id, 'photo_received')}\n\n{t(user_id, 'step_prompt')}",
            parse_mode=ParseMode.HTML,
        )

        # 2-bosqich: Prompt
        text_lang = get_text_lang(user_id)
        prompt = write_generation_prompt(analysis, text_lang)
        logger.info(f"Prompt:\n{prompt}")

        await wait_msg.edit_text(
            f"{t(user_id, 'photo_received')}\n\n{t(user_id, 'step_generating')}",
            parse_mode=ParseMode.HTML,
        )

        # 3-bosqich: Generatsiya
        variants = generate_variants(image_bytes, prompt)
        logger.info(f"{len(variants)} variant: user={user_id}")

        # Natijalarni yuborish
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        download_text = t(user_id, "download")

        if len(variants) >= 2:
            # 2 ta variantni media group sifatida yuborish
            media_group = [
                InputMediaPhoto(
                    media=BufferedInputFile(file=variants[0], filename=f"v1_{user_id}_{timestamp}.png"),
                    caption=t(user_id, "done"),
                    parse_mode=ParseMode.HTML,
                ),
                InputMediaPhoto(
                    media=BufferedInputFile(file=variants[1], filename=f"v2_{user_id}_{timestamp}.png"),
                ),
            ]
            await message.answer_media_group(media=media_group)

            # Yuklab olish tugmalari (alohida fayllar sifatida)
            for i, variant in enumerate(variants):
                doc_file = BufferedInputFile(
                    file=variant,
                    filename=f"infographic_{i+1}_{user_id}_{timestamp}.png",
                )
                await message.answer_document(
                    document=doc_file,
                    caption=f"{download_text} — Variant {i+1}",
                )
        else:
            await message.answer_photo(
                photo=BufferedInputFile(file=variants[0], filename=f"inf_{user_id}_{timestamp}.png"),
                caption=t(user_id, "done_single"),
                parse_mode=ParseMode.HTML,
            )
            doc_file = BufferedInputFile(file=variants[0], filename=f"infographic_{user_id}_{timestamp}.png")
            await message.answer_document(document=doc_file, caption=download_text)

        # User yuklagan rasmni o'chirish (hajm tejash)
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=user_msg_id)
        except Exception:
            pass  # O'chira olmasa ham davom etadi

        # Kutish xabarini o'chirish
        await wait_msg.delete()

    except Exception as e:
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


# ── Matn xabarlari ──────────────────────────────────────────────
@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: types.Message):
    await message.answer(t(message.from_user.id, "send_photo"), parse_mode=ParseMode.HTML)


# ── Fayl sifatida yuborilgan rasmlar ─────────────────────────────
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
        wait_msg = await message.answer(
            f"{t(user_id, 'photo_received')}\n\n{t(user_id, 'step_analysis')}",
            parse_mode=ParseMode.HTML,
        )

        try:
            file = await bot.get_file(doc.file_id)
            raw = await bot.download_file(file.file_path)
            image_bytes = raw.read()

            analysis = analyze_product(image_bytes)

            copyright_match = check_copyright(analysis)
            if copyright_match:
                await wait_msg.edit_text(
                    t(user_id, "error_copyright", keyword=copyright_match),
                    parse_mode=ParseMode.HTML,
                )
                return

            await wait_msg.edit_text(f"{t(user_id, 'photo_received')}\n\n{t(user_id, 'step_prompt')}", parse_mode=ParseMode.HTML)

            text_lang = get_text_lang(user_id)
            prompt = write_generation_prompt(analysis, text_lang)

            await wait_msg.edit_text(f"{t(user_id, 'photo_received')}\n\n{t(user_id, 'step_generating')}", parse_mode=ParseMode.HTML)

            variants = generate_variants(image_bytes, prompt)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            if len(variants) >= 2:
                media_group = [
                    InputMediaPhoto(
                        media=BufferedInputFile(file=variants[0], filename=f"v1_{user_id}_{timestamp}.png"),
                        caption=t(user_id, "done"),
                        parse_mode=ParseMode.HTML,
                    ),
                    InputMediaPhoto(
                        media=BufferedInputFile(file=variants[1], filename=f"v2_{user_id}_{timestamp}.png"),
                    ),
                ]
                await message.answer_media_group(media=media_group)
                for i, v in enumerate(variants):
                    await message.answer_document(
                        document=BufferedInputFile(file=v, filename=f"infographic_{i+1}_{user_id}_{timestamp}.png"),
                        caption=f"{t(user_id, 'download')} — Variant {i+1}",
                    )
            else:
                await message.answer_photo(
                    photo=BufferedInputFile(file=variants[0], filename=f"inf_{user_id}.png"),
                    caption=t(user_id, "done_single"),
                    parse_mode=ParseMode.HTML,
                )

            try:
                await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            except Exception:
                pass

            await wait_msg.delete()

        except Exception as e:
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

    # Bot menu buyruqlarini o'rnatish
    await bot.set_my_commands([
        BotCommand(command="start", description="Botni boshlash / Запустить бота"),
        BotCommand(command="settings", description="Til sozlamalari / Настройки языка"),
        BotCommand(command="help", description="Yordam / Помощь"),
    ])

    logger.info("=" * 50)
    logger.info("🚀 Marketplace Infografik Bot v7")
    logger.info("📊 Tahlil: gpt-4o-mini")
    logger.info("📊 Prompt: gpt-4o-mini")
    logger.info("📊 Rasm: gpt-image-2 (medium)")
    logger.info("📐 Output: 1056x1408 (3:4)")
    logger.info("🔢 Variantlar: 2 ta")
    logger.info("🌐 Tillar: UZ / RU")
    logger.info("💰 Narx: ~$0.085 per so'rov")
    logger.info("=" * 50)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())