"""
prompts.py — Barcha AI prompt va matn generatsiya funksiyalari
==============================================================
⚠️  FAQAT SHU FAYLNI O'ZGARTIRING — bot.py ga tegmang!
"""

import asyncio
import base64
import io
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI
from PIL import Image

logger = logging.getLogger(__name__)

# client bot.py dan import qilinadi
_client = None
executor = ThreadPoolExecutor(max_workers=4)

def set_client(client):
    global _client
    _client = client

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
- Think like a marketplace copywriter on Uzum/Wildberries, not a product engineer

CRITICAL — PRODUCT IDENTITY:
- First identify WHAT THE ACTUAL PRODUCT IS (the physical object being sold)
- If the product is a mousepad/mat/rug/poster/pillow/phone case WITH A PRINTED IMAGE on it:
  * Product type = the physical object (e.g., "gaming mousepad", "decorative rug", "wall poster")
  * The printed image/pattern on it = just a design feature, NOT the product itself
  * Features should describe the PHYSICAL OBJECT: material, size, surface, non-slip base, etc.
  * DO NOT describe the printed image as if it were a separate product
- Example: A mousepad with soldiers printed on it → Product = mousepad, Design = military theme
- Example: A mug with a cat printed on it → Product = ceramic mug, Design = cat pattern"""

def analyze_product(image_bytes, text_lang="uz"):
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    lang_note = (
        "Write Feature benefits (section 4) and Headline (section 7) directly in UZBEK — natural marketplace Uzbek, NOT English."
        if text_lang == "uz" else
        "Write Feature benefits (section 4) and Headline (section 7) directly in RUSSIAN — natural conversational Russian, NOT English."
    )
    r = _client.chat.completions.create(
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
    r = _client.chat.completions.create(
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
    r = _client.images.edit(model="gpt-image-2", image=[f], prompt=prompt, n=1, size="1104x1472", quality="low")
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
    r = _client.chat.completions.create(
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
    r = _client.images.edit(model="gpt-image-2", image=[f], prompt=prompt, n=1, size="1024x1024", quality="low")
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
QISQACHA_TAVSIF_UZ: [300-390 belgi]
QISQACHA_TAVSIF_RU: [300-390 belgi]
---
XUSUSIYATLARI_UZ: [texnik list, har biri yangi qatorda]
XUSUSIYATLARI_RU: [texnik list, har biri yangi qatorda]

📌 TOVAR NOMI (70-90 belgi):
- Tovar turi + asosiy xususiyatlar, kamida 3 so'z
- 70 belgidan KAM bo'lmasin, 90 dan OSHMASIN

📝 QISQACHA TAVSIF — FAQAT kalit so'zlar, vergul bilan ajratilgan (300-390 belgi):
- Har bir kalit so'z vergul bilan ajratiladi
- KAMIDA 20 ta kalit so'z
- 300 belgidan KAM bo'lmasin, 390 dan OSHMASIN
- Hech qanday gap qurilmasi, izoh, belgilash YO'Q — faqat so'zlar va vergul
- ** yoki *** yoki # kabi belgilar MUTLAQO TAQIQLANGAN

✅ TO'G'RI NAMUNA:
Chiroyli naqshli chashka, keramika, qizil tutqich, ichimliklar uchun, uy dekoratsiyasi, maxsus dizayn, qulay tutqich, zamonaviy uslub, ichimliklar, chashka, chashka sotib olish, chashka narxi, chashka dizayni, chashka sotilishi, chashka ishlab chiqarish, chashkalar, chashka to'plami, chashka tanlovi, chashka yangiliklari, chashka sifatlari

❌ XATO:
**Chashka** - keramika material, qizil tutqich bilan...
- Qulay tutqich
- Zamonaviy dizayn

🏷 XUSUSIYATLAR FORMATI:
- Har bir qator: "Parametr nomi: qiymat" shaklida
- "Xususiyat" so'zini kalit sifatida ISHLATMA
- ** yoki *** yoki boshqa markdown belgilari TAQIQLANGAN — oddiy matn

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
**Material**: alyuminiy
***Rang***: qora
- Diametr: 24 sm

Kalit nomlar: Turi, Material, Rang, O'lcham, Hajm, Og'irlik, Diametr, Balandlik, Uzunlik, Kenglik, Qoplama, Korpus, Maqsad, Mamlakat, Komplekt, Parvarish, Shakl, Stil, Soni

🚫 Stop-so'zlar: aksiya, bepul, chegirma, top, xit, eng yaxshi, arzon
🚫 Brend nomini UMUMAN ishlatma
🚫 Hech qanday markdown: **, ***, ##, - list TAQIQLANGAN""",

    "ru": """Ты помощник для карточек Uzum Market. Проанализируй фото, напиши 3 текста.

ФОРМАТ:
TOVAR_NOMI_UZ: [70-90 символов]
TOVAR_NOMI_RU: [70-90 символов]
---
QISQACHA_TAVSIF_UZ: [300-390 символов]
QISQACHA_TAVSIF_RU: [300-390 символов]
---
XUSUSIYATLARI_UZ: [технический список, каждый на новой строке]
XUSUSIYATLARI_RU: [технический список, каждый на новой строке]

📌 НАЗВАНИЕ (70-90 символов):
- Тип товара + ключевые характеристики, минимум 3 слова
- НЕ МЕНЬШЕ 70 символов, НЕ БОЛЬШЕ 90

📝 КРАТКОЕ ОПИСАНИЕ — ТОЛЬКО ключевые слова через запятую (300-390 символов):
- Каждое ключевое слово через запятую
- МИНИМУМ 20 ключевых слов
- НЕ МЕНЬШЕ 300 символов, НЕ БОЛЬШЕ 390
- Никаких предложений, пояснений, форматирования — только слова и запятые
- ** или *** или # и другие символы СТРОГО ЗАПРЕЩЕНЫ

✅ ПРАВИЛЬНЫЙ ПРИМЕР:
Красивая кружка с узором, керамика, красная ручка, для напитков, декор дома, особый дизайн, удобная ручка, современный стиль, напитки, кружка, купить кружку, цена кружки, дизайн кружки, кружки оптом, производство кружек, набор кружек, выбор кружек, новинки кружек, качество кружек, кружка керамическая

❌ НЕПРАВИЛЬНО:
**Кружка** - керамический материал, красная ручка...
- Удобная ручка
- Современный дизайн

🏷 ФОРМАТ ХАРАКТЕРИСТИК:
- Каждая строка: "Название параметра: значение"
- Слово "Характеристика" как ключ — ЗАПРЕЩЕНО
- ** или *** и любой markdown — СТРОГО ЗАПРЕЩЕНЫ, только обычный текст

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
**Материал**: алюминий
***Цвет***: чёрный
- Диаметр: 24 см

Названия ключей: Тип, Материал, Цвет, Размер, Объём, Вес, Диаметр, Высота, Длина, Ширина, Покрытие, Корпус, Назначение, Страна, Комплект, Уход, Форма, Стиль, Количество

🚫 Стоп-слова: акция, бесплатно, скидка, топ, хит, лучший, дёшево
🚫 НИКОГДА не используй названия брендов
🚫 Никакого markdown: **, ***, ##, - списки ЗАПРЕЩЕНЫ""",
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
    r = _client.chat.completions.create(
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
    r = _client.chat.completions.create(
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