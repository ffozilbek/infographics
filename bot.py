"""
Marketplace Infografik Bot v6
==============================
1-bosqich: GPT-4o-mini — mahsulotni structured tahlil qiladi (~$0.002)
2-bosqich: GPT-4o-mini — tahlil asosida generation prompt yozadi (~$0.001)
3-bosqich: gpt-image-2 — 2 ta variant generatsiya (medium, 1080x1440) (~$0.082)
Jami: ~$0.085 per so'rov (2 ta variant)
"""

import os
import io
import base64
import logging
import asyncio
from datetime import datetime

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import BufferedInputFile, InputMediaPhoto
from aiogram.enums import ParseMode
from openai import OpenAI
from PIL import Image

# ── Sozlamalar ───────────────────────────────────────────────────
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY:
    raise ValueError(
        "TELEGRAM_BOT_TOKEN va OPENAI_API_KEY .env faylda bo'lishi kerak!"
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
router = Router()

user_tasks = {}


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
- Keep descriptions short and precise
- Focus on visual and structural analysis only"""


def analyze_product(image_bytes: bytes) -> str:
    """1-bosqich: mahsulotni tahlil qiladi"""

    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": "high",
                        },
                    },
                    {
                        "type": "text",
                        "text": ANALYSIS_PROMPT,
                    },
                ],
            },
        ],
        max_tokens=1000,
        temperature=0.3,
    )

    analysis = response.choices[0].message.content.strip()
    logger.info(f"Analysis done ({len(analysis)} chars)")
    return analysis


# ══════════════════════════════════════════════════════════════════
# 2-BOSQICH: Tahlil asosida generation prompt yozish
# ══════════════════════════════════════════════════════════════════

PROMPT_WRITER_SYSTEM = """You are an expert marketplace infographic prompt engineer.

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

Text:
- ALL text must be in RUSSIAN language
- ALL Russian text must have PERFECT spelling — ZERO errors allowed
- Put every Russian text element in "quotes" in the prompt for accurate rendering
- Rewrite text professionally if needed (do NOT copy with errors)
- Keep it short, clean, and impactful
- Use bold modern sans-serif font, high contrast, easy to read

Features:
- Show 3-4 feature points with minimal icons on the LEFT side
- Each feature: icon + bold Russian title + short Russian description below
- Features arranged VERTICALLY (list style), not horizontally
- NO bottom 3 blocks/cards — use feature list instead

Layout (1080x1440, 3:4 portrait):
- Product as hero image (center/right, ~50-60% of image)
- Headline top-left, large bold text
- Subheadline below headline, smaller
- Features list on the left side, vertically arranged
- Badge (if applicable) on the right side
- Clean bottom section with closing tagline

Extras:
- Add subtle realistic elements (e.g. water drops, particles, glow, leaves, steam — depending on product)
- Maintain balanced spacing and alignment
- Marketplace compliant (Uzum, Wildberries style)

Quality:
- Ultra realistic
- 4K commercial advertising quality
- No artifacts, no text distortion, no misspellings

---

CRITICAL RULES:
1. Insert the FULL analysis into the prompt
2. ALL Russian text must be spelled PERFECTLY — marketplace will reject if even one letter is wrong
3. Put all Russian text in "quotes" for accurate rendering
4. NO bottom 3 usage blocks/cards — use vertical feature list instead
5. Keep Russian text SHORT (2-4 words for titles, 5-8 words for descriptions)
6. Feature descriptions should be simple common Russian words only
"""


def write_generation_prompt(analysis: str) -> str:
    """2-bosqich: tahlil asosida generation prompt yozadi"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": PROMPT_WRITER_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Based on this product analysis, write the image generation prompt:\n\n"
                    f"{analysis}"
                ),
            },
        ],
        max_tokens=2000,
        temperature=0.7,
    )

    prompt = response.choices[0].message.content.strip()
    logger.info(f"Generation prompt written ({len(prompt)} chars)")
    return prompt


# ══════════════════════════════════════════════════════════════════
# 3-BOSQICH: 2 ta variant generatsiya (gpt-image-2)
# ══════════════════════════════════════════════════════════════════

# Moderation filtriga tushishi mumkin bo'lgan so'zlar
SAFETY_REPLACEMENTS = {
    "ultra-realistic": "high-quality",
    "ultra realistic": "high-quality",
    "4K": "high resolution",
    "hyper-realistic": "high-quality",
    "photorealistic": "professional photography",
    "skin": "surface",
    "body": "product body",
    "naked": "",
    "bare": "plain",
    "sexy": "stylish",
    "tight": "fitted",
    "revealing": "open",
}


def sanitize_prompt(prompt: str) -> str:
    """Promptdan safety filtriga tushishi mumkin so'zlarni tozalaydi"""
    result = prompt
    for old, new in SAFETY_REPLACEMENTS.items():
        result = result.replace(old, new)
    return result


def generate_variants(image_bytes: bytes, prompt: str) -> list[bytes]:
    """2 ta variantni generatsiya qiladi, moderation xatosida retry"""

    max_retries = 3

    for attempt in range(max_retries):
        try:
            image_file = io.BytesIO(image_bytes)
            image_file.name = "product.png"

            current_prompt = prompt if attempt == 0 else sanitize_prompt(prompt)

            # 2-urinishda promptni yanada soddalashtirish
            if attempt >= 2:
                current_prompt = (
                    "Create a clean, professional marketplace product infographic. "
                    "Show the product from the reference image with a modern gradient background. "
                    "Add product features in Russian text on the left side. "
                    "Layout: 3:4 portrait, premium advertising style. "
                    "Clean typography, minimal icons, marketplace compliant design."
                )

            response = client.images.edit(
                model="gpt-image-2",
                image=[image_file],
                prompt=current_prompt,
                n=2,
                size="1056x1408",
                quality="medium",
            )

            results = []
            for item in response.data:
                results.append(base64.b64decode(item.b64_json))

            logger.info(f"{len(results)} ta variant tayyor (attempt {attempt+1})")
            return results

        except Exception as e:
            err_str = str(e).lower()
            if "moderation" in err_str or "safety" in err_str:
                logger.warning(f"Moderation block, attempt {attempt+1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    continue
            raise

    raise Exception("Rasm generatsiya bo'lmadi — safety filter")


# ══════════════════════════════════════════════════════════════════
# TELEGRAM HANDLERLARI
# ══════════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "🎨 <b>Marketplace Infografik Bot</b>\n\n"
        "Menga mahsulot rasmini yuboring — AI uni professional\n"
        "marketplace infografik rasmga aylantirib beradi!\n\n"
        "📸 <b>Qanday ishlaydi:</b>\n"
        "1. Mahsulot rasmini yuboring\n"
        "2. AI mahsulotni batafsil tahlil qiladi\n"
        "3. Individual prompt generatsiya qiladi\n"
        "4. <b>2 ta variant</b> tayyorlab beradi!\n\n"
        "📐 Rasm: 1080x1440 (3:4)\n"
        "🏪 Uzum, Wildberries uchun tayyor\n"
        "✅ Rus tilidagi yozuvlar imlo xatosiz",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Yordam</b>\n\n"
        "🔹 Mahsulot rasmini yuboring\n"
        "🔹 AI 3 bosqichda ishlaydi:\n"
        "   → Tahlil → Prompt → 2 ta Infografik\n"
        "🔹 60-90 soniyada tayyor\n"
        "🔹 1080x1440 (3:4 marketplace format)\n\n"
        "⚠️ Bir vaqtda bitta rasm yuboring\n"
        "📸 Sifatli rasm = sifatli natija",
        parse_mode=ParseMode.HTML,
    )


@router.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id

    if user_tasks.get(user_id):
        await message.answer("⏳ Oldingi rasmingiz hali tayyor bo'lmadi. Kuting...")
        return

    user_tasks[user_id] = True

    wait_msg = await message.answer(
        "🎨 <b>Rasmingiz qabul qilindi!</b>\n\n"
        "⏳ 1/4 — Mahsulot tahlil qilinmoqda...",
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

        await wait_msg.edit_text(
            "🎨 <b>Rasmingiz qabul qilindi!</b>\n\n"
            "✅ Mahsulot tahlil qilindi\n"
            "⏳ 2/3 — Prompt yaratilmoqda...",
            parse_mode=ParseMode.HTML,
        )

        # 2-bosqich: Prompt
        prompt = write_generation_prompt(analysis)
        logger.info(f"Prompt:\n{prompt}")

        await wait_msg.edit_text(
            "🎨 <b>Rasmingiz qabul qilindi!</b>\n\n"
            "✅ Mahsulot tahlil qilindi\n"
            "✅ Prompt tayyor\n"
            "⏳ 3/3 — 2 ta variant yaratilmoqda...\n\n"
            "⏱ Bu 30-60 soniya vaqt olishi mumkin",
            parse_mode=ParseMode.HTML,
        )

        # 3-bosqich: 2 ta variantni BITTA so'rovda generatsiya
        variants = generate_variants(image_bytes, prompt)
        logger.info(f"{len(variants)} variant tayyor: user={user_id}")

        # Natijalarni yuborish (media group sifatida)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if len(variants) >= 2:
            media_group = [
                InputMediaPhoto(
                    media=BufferedInputFile(
                        file=variants[0],
                        filename=f"variant_1_{user_id}_{timestamp}.png",
                    ),
                    caption=(
                        "✅ <b>2 ta variant tayyor!</b>\n\n"
                        "📐 O'lcham: 1056x1408 (3:4)\n"
                        "🏪 Marketplace uchun tayyor\n\n"
                        "💾 Yoqqanini yuklab oling\n"
                        "🔄 Yana rasm yuboring!"
                    ),
                    parse_mode=ParseMode.HTML,
                ),
                InputMediaPhoto(
                    media=BufferedInputFile(
                        file=variants[1],
                        filename=f"variant_2_{user_id}_{timestamp}.png",
                    ),
                ),
            ]
            await message.answer_media_group(media=media_group)
        else:
            await message.answer_photo(
                photo=BufferedInputFile(
                    file=variants[0],
                    filename=f"infographic_{user_id}_{timestamp}.png",
                ),
                caption="✅ <b>Infografik tayyor!</b>\n📐 1056x1408 (3:4)\n🔄 Yana rasm yuboring!",
                parse_mode=ParseMode.HTML,
            )

        await wait_msg.delete()

    except Exception as e:
        logger.error(f"Xatolik: user={user_id}, error={e}")

        error_text = "❌ <b>Xatolik yuz berdi</b>\n\n"
        err_str = str(e).lower()

        if "billing" in err_str or "quota" in err_str or "insufficient" in err_str:
            error_text += "💳 OpenAI hisobida mablag' yetarli emas."
        elif "rate_limit" in err_str:
            error_text += "⏱ Juda ko'p so'rov. 1 daqiqadan keyin urinib ko'ring."
        elif "content_policy" in err_str or "moderation" in err_str or "safety" in err_str:
            error_text += "🚫 Rasm yoki prompt safety filtriga tushdi.\nBoshqa rasm yuboring yoki qayta urinib ko'ring."
        elif "size" in err_str or "dimension" in err_str:
            error_text += "📐 Rasm o'lchami qo'llab-quvvatlanmaydi."
        else:
            error_text += f"<code>{str(e)[:300]}</code>"

        await wait_msg.edit_text(error_text, parse_mode=ParseMode.HTML)

    finally:
        user_tasks.pop(user_id, None)


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: types.Message):
    await message.answer(
        "📸 Menga <b>mahsulot rasmini</b> yuboring!",
        parse_mode=ParseMode.HTML,
    )


@router.message(F.document)
async def handle_document(message: types.Message):
    doc = message.document
    if doc.mime_type and doc.mime_type.startswith("image/"):
        user_id = message.from_user.id
        if user_tasks.get(user_id):
            await message.answer("⏳ Kuting...")
            return

        user_tasks[user_id] = True
        wait_msg = await message.answer("🎨 Qayta ishlanmoqda...", parse_mode=ParseMode.HTML)

        try:
            file = await bot.get_file(doc.file_id)
            raw = await bot.download_file(file.file_path)
            image_bytes = raw.read()

            analysis = analyze_product(image_bytes)
            await wait_msg.edit_text("✅ Tahlil tayyor\n⏳ Prompt yaratilmoqda...")

            prompt = write_generation_prompt(analysis)
            await wait_msg.edit_text("✅ Prompt tayyor\n⏳ 2 ta variant yaratilmoqda...")

            variants = generate_variants(image_bytes, prompt)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            if len(variants) >= 2:
                media_group = [
                    InputMediaPhoto(
                        media=BufferedInputFile(file=variants[0], filename=f"v1_{user_id}_{timestamp}.png"),
                        caption="✅ <b>2 ta variant tayyor!</b>\n📐 1056x1408 (3:4)",
                        parse_mode=ParseMode.HTML,
                    ),
                    InputMediaPhoto(
                        media=BufferedInputFile(file=variants[1], filename=f"v2_{user_id}_{timestamp}.png"),
                    ),
                ]
                await message.answer_media_group(media=media_group)
            else:
                await message.answer_photo(
                    photo=BufferedInputFile(file=variants[0], filename=f"inf_{user_id}.png"),
                    caption="✅ <b>Tayyor!</b>\n📐 1056x1408 (3:4)",
                    parse_mode=ParseMode.HTML,
                )

            await wait_msg.delete()

        except Exception as e:
            logger.error(f"Xatolik: user={user_id}, error={e}")
            await wait_msg.edit_text(f"❌ Xatolik: {str(e)[:300]}")
        finally:
            user_tasks.pop(user_id, None)
    else:
        await message.answer("📸 Rasm yuboring!", parse_mode=ParseMode.HTML)


# ── Ishga tushirish ──────────────────────────────────────────────
async def main():
    dp.include_router(router)

    logger.info("=" * 50)
    logger.info("🚀 Marketplace Infografik Bot v6")
    logger.info("📊 Tahlil: gpt-4o-mini")
    logger.info("📊 Prompt: gpt-4o-mini")
    logger.info("📊 Rasm: gpt-image-2 (medium)")
    logger.info("📐 Output: 1080x1440 (3:4)")
    logger.info("🔢 Variantlar: 2 ta")
    logger.info("💰 Narx: ~$0.085 per so'rov (2 variant)")
    logger.info("=" * 50)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())