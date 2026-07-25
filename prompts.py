"""
prompts.py — Barcha AI prompt va matn generatsiya funksiyalari
==============================================================
⚠️  FAQAT SHU FAYLNI O'ZGARTIRING — bot.py ga tegmang!
"""

import asyncio
import base64
import io
import json
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

   ⚠️ EACH BENEFIT MUST BE GROUNDED IN ONE OF TWO THINGS — not in vague generic marketing filler:
   (a) A SPECIFIC VISUAL DETAIL you can actually see in THIS image — a particular color, texture,
       pose, expression, material finish, proportion, or construction detail.
   (b) A GENUINE USE-CASE SPECIFIC TO THIS EXACT PRODUCT TYPE — the real, specific way this kind of
       product is actually used or valued. Think about what this product type is genuinely FOR.
       e.g. for a collectible figure: "kolleksiyangizga qo'shimcha", "ish stoli/javon uchun dekor
       buyumi" — these are genuine because collecting/displaying is literally what figures are for.
       e.g. for a plush toy: comfort during sleep/play, a companion for a specific age group.
       This is DIFFERENT from generic filler: a real use-case is specific to what this product
       category IS FOR, while filler is a vague claim that could describe literally any object.
   ⚠️ GENERIC FILLER IS FORBIDDEN — vague claims that could apply to almost ANY small product,
   regardless of category, and say nothing about what THIS product actually is or does. Test:
   "would this exact sentence still make sense for a completely different, unrelated product?"
   If yes, it's filler — rewrite it. Examples of filler to avoid unless the image gives a concrete
   reason for it (e.g. only call something "compact" if it's visibly unusually small or foldable):
   "oson saqlash" / "легко хранить" (unless visibly foldable/tiny), "yengil va ko'chirish oson" /
   "лёгкий, удобно носить" (unless visibly miniature), "qiziqarli ko'rinish" / "интересный вид",
   "rang-barang ko'rinishi bilan jalb qiladi" / "яркий, привлекает внимание" — these say nothing
   specific about the product itself.
   Note "ideal sovg'a" / "идеальный подарок" and "mukammal do'st" / "идеальный друг" ARE acceptable
   as genuine use-case benefits (rule b) for toys/figures/gift items specifically, since gifting and
   companionship are real reasons people buy this category — just don't use them for every product.
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
   GRAMMAR: must be a complete, grammatically valid phrase in the target language.
   For Uzbek: a verbless statement takes the NOMINATIVE case — never attach -ni / -ga / -da / -dan
   to the subject noun. WRONG: "Suvni har doim tayyor". RIGHT: "Suv har doim tayyor".

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

def analyze_product(image_bytes, text_lang="uz", user_title=None, user_features=None):
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    lang_note = (
        "Write Feature benefits (section 4) and Headline (section 7) directly in UZBEK — natural marketplace Uzbek, NOT English."
        if text_lang == "uz" else
        "Write Feature benefits (section 4) and Headline (section 7) directly in RUSSIAN — natural conversational Russian, NOT English."
    )
    lang_full = "Uzbek" if text_lang == "uz" else "Russian"
    user_hint = ""
    if user_title:
        user_hint += (
            f"\n\nUSER-PROVIDED PRODUCT NAME (use this as the basis for section 1 'Product type' "
            f"and section 7 'Headline Concept' — adapt to the required format/length, don't ignore it. "
            f"Write it in {lang_full} — translate first if it's given in another language): {user_title}"
        )
    if user_features:
        user_hint += (
            f"\n\nUSER-PROVIDED FEATURES (incorporate these into section 4 'Key Product Features' "
            f"as customer benefits, rewritten in the required style — don't ignore them. "
            f"Write them in {lang_full} — translate first if given in another language): {user_features}"
        )
    r = _client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": [
{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
{"type": "text", "text": ANALYSIS_PROMPT + f"\n\nLANGUAGE NOTE: {lang_note}" + user_hint},
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

def get_infographic_prompt_system(text_lang, allow_brand=False, include_badges=True):
    if include_badges:
        badge_layout_block = """- Badge block on the right side: 1-3 spec badges stacked VERTICALLY
  inside one rounded container, separated by thin divider lines
- Each badge: large number + unit on top, small label underneath
- If the product is sold in SEVERAL size/volume options, give EACH option its own badge
  (e.g. "886 L / 183x51 sm" and "3853 L / 305x76 sm") — never merge them into one line

⚠️ BADGE LABELS — NEVER INVENT MEANING:
- A badge label must state ONLY what the source data actually says.
- If two volumes are listed as ALTERNATIVE SIZE OPTIONS of the same product, both badges
  describe the SAME kind of measurement. Label them identically (e.g. both "SUV HAJMI"),
  or label each with its physical size, or use no label at all.
- FORBIDDEN: inventing two DIFFERENT meanings for two option values.
  WRONG: "886 L / SUV HAJMI" + "3853 L / TO'LIQ HAJMI"  ← fabricated distinction
  RIGHT: "886 L / 183x51 SM" + "3853 L / 305x76 SM"
  RIGHT: "886 L" + "3853 L" with a single shared caption "HAJMI TANLANADI"
- If you do not know what a number means, print the number with its unit and NO label.
  Never guess a label to fill the space.

⚠️ BADGE VALUES — NEVER DERIVE, ONLY COPY:
- A badge may contain ONLY a value that is written EXPLICITLY in the analysis or in the
  user's text. Copy it, never compute it.
- Model codes, article numbers, part numbers and SKUs are IDENTIFIERS, NOT specs.
  NEVER decode them into a spec value, even if the digits look meaningful.
  WRONG: user wrote "Artel 3216 E, 3618 E, 4218 E, 32L va 36L" -> badges "32 L", "36 L", "42 L"
         (42 was invented by reading the model code "4218 E" — forbidden)
  RIGHT: badges "32 L", "36 L" only — those are the volumes the user actually stated
- If the count of model codes does not match the count of stated specs, DO NOT balance them.
  Show only what was stated and leave the rest out.
- Never round, convert, average or extrapolate a number.

⚠️ BADGE CAPTION — WRITE IT ONCE:
- When several badges share the same caption, print that caption ONCE for the whole block
  (above or below the stack), never repeated on every badge.
  WRONG: "32 L / HAJMI TANLANADI", "36 L / HAJMI TANLANADI", "42 L / HAJMI TANLANADI"
  RIGHT: caption "HAJMI TANLANADI" once, then the values "32 L" and "36 L" beneath it
- Clean bottom section with closing tagline"""
    else:
        badge_layout_block = """- NO badge block, NO spec numbers, NO stat callouts anywhere on the image.
  This product has no user-provided title/features and no confirmed numeric specs,
  so the layout is HEADLINE + FEATURE LIST + PRODUCT IMAGE ONLY — nothing else.
- Do NOT add an age range, height, weight, capacity, wattage, volume, or any other
  number you were not explicitly given. If you don't have real data, leave that
  space empty rather than filling it with a plausible-looking badge.
- Clean bottom section with closing tagline"""
    if allow_brand:
        brand_rule_1 = "- If the product analysis mentions a visible brand name, or the user explicitly provided the product name/title, you MAY use that EXACT brand/product name as-is (do not invent, do not translate it) — but do not add any OTHER brand name not present in the analysis or user input."
        brand_rule_2 = "3. Brand name allowed ONLY if it was given in the analysis (visible on product) or by the user — otherwise NO brand names"
    else:
        brand_rule_1 = "- NEVER put any brand name or logo text on the image"
        brand_rule_2 = "3. ABSOLUTELY NO BRAND NAMES anywhere on the image"
    if text_lang == "uz":
        lang_instruction = "ALL text on the infographic must be in UZBEK language with PERFECT spelling."
        banned = 'BANNED: "aksiya", "bepul", "chegirma", "top", "xit", "yangilik", "eng yaxshi", "arzon".'
        copywriting_rules = """
UZBEK GRAMMAR — HARD REQUIREMENT (check EVERY line before output):
1. CASE SUFFIXES: a verbless nominal statement uses the NOMINATIVE (bosh kelishik).
   Do NOT attach -ni / -ga / -da / -dan / -ning to the subject when there is no verb.
   WRONG: "Suvni har doim tayyor"   RIGHT: "Suv har doim tayyor"
   WRONG: "Kiyimni tez quriydi"     RIGHT: "Kiyim tez quriydi"
   -ni is ONLY valid with a real verb: "Suvni iching", "Kiyimni yuving".
2. SUBJECT-PREDICATE AGREEMENT: third person singular predicate takes -adi / -ydi.
   WRONG: "Oyoq charchamaysiz"      RIGHT: "Oyoq charchamaydi"
3. LATIN APOSTROPHES: use o' and g' (with apostrophe), never o` / ģ / ŏ.
   Correct: "qulaylik", "ko'rinish", "o'lcham", "yog'och", "bo'yicha".
4. NO word-by-word English calques. If the phrase cannot be said out loud
   naturally by an Uzbek speaker, rewrite it from scratch.
5. Headline may be ALL CAPS, but the grammar underneath must still be valid —
   capitalisation never excuses a wrong suffix.

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
RUSSIAN GRAMMAR — HARD REQUIREMENT (check EVERY line before output):
1. CASE: a verbless nominal statement uses the NOMINATIVE.
   WRONG: "Воду всегда готова"   RIGHT: "Вода всегда готова"
2. AGREEMENT: adjective/predicate must agree with the noun in gender and number.
   WRONG: "Вода горячий"         RIGHT: "Вода горячая"
3. Use ё where required, no Latin letters mixed into Cyrillic words.
4. NO word-by-word English calques — rewrite unnatural phrases from scratch.

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
- Keep SHORT: 2-4 words titles (HARD LIMIT — 4 words max, never 5+), 5-8 words descriptions
- A feature title must fit on ONE or TWO lines. If it needs 3+ lines, it is too long — cut it down
- Move any extra meaning into the description line below, not into the title
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
{badge_layout_block}

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
{brand_rule_1}

CRITICAL RULES:
1. ALL text spelled PERFECTLY
2. Put all text in "quotes"
{brand_rule_2}
4. NEVER use banned words
5. Use product type + key feature as headline
6. NEVER translate text that is printed/written on the product
7. Any text visible on the product must be kept in original language or omitted entirely — NEVER translated
"""


# ══════════════════════════════════════════════════════════════════
# GRAMMATIKA TEKSHIRUVI (rasmga tushadigan matnlar uchun)
# ══════════════════════════════════════════════════════════════════
# Sabab: prompt yozadigan model o'zbekcha matnni ba'zan noto'g'ri kelishikda
# beradi (masalan "SUVNI HAR DOIM TAYYOR" — fe'l yo'q, demak bosh kelishik
# kerak edi). gpt-image-2 esa berilgan matnni so'zma-so'z chizadi, ya'ni xato
# to'g'ridan-to'g'ri rasmga tushib qoladi. Shuning uchun rasm generatsiyasidan
# OLDIN qo'shtirnoq ichidagi barcha matnlarni alohida tekshirib chiqamiz.

_QUOTED_RE = re.compile(r'"([^"\n]{2,90})"')

PROOFREAD_SYSTEM = {
    "uz": """Sen o'zbek tili (lotin yozuvi) bo'yicha professional korrektorsan.
Senga marketpleys infografikasiga chizib qo'yiladigan qisqa matnlar ro'yxati beriladi.
Har birini grammatik jihatdan to'g'irlab, XUDDI SHU FORMATDA qaytar.

TEKSHIRADIGAN XATOLAR:
1. Kelishik qo'shimchalari. Fe'lsiz, holat bildiruvchi gapda ot BOSH KELISHIKDA bo'ladi —
   -ni / -ga / -da / -dan / -ning qo'shimchalari ortiqcha.
   XATO: "SUVNI HAR DOIM TAYYOR"  ->  TO'G'RI: "SUV HAR DOIM TAYYOR"
   XATO: "Kiyimni tez quriydi"    ->  TO'G'RI: "Kiyim tez quriydi"
   -ni faqat haqiqiy fe'l bilan keladi: "Suvni iching" — bu to'g'ri.
2. Ega va kesim moslashuvi: "Oyoq charchamaysiz" -> "Oyoq charchamaydi".
3. Apostroflar: o' va g' to'g'ri yozilsin (o` , ģ , ŏ emas).
4. Imlo xatolari va so'zma-so'z tarjima hidi keladigan g'aliz iboralar.

QAT'IY QOIDALAR:
- Ma'noni O'ZGARTIRMA, yangi so'z QO'SHMA, matnni uzaytirma yoki qisqartirma.
- ⚠️ HARF REGISTRINI MUTLAQO O'ZGARTIRMA. Kirish matni qanday yozilgan bo'lsa,
  javob ham AYNAN shunday yozilsin. Kichik harfni katta harfga aylantirma,
  kattasini kichikka aylantirma. Bu sening vazifang EMAS.
  Kirish: "Oson o'rnatish"  ->  Javob: "Oson o'rnatish"  (BUZILMASIN)
  XATO javob: "OSON O'RNATISH"
- ⚠️ APOSTROFNI O'ZBOSHIMCHALIK BILAN QO'SHMA. Ayniqsa quyidagi juftliklarga
  e'tibor ber — ular BUTUNLAY boshqa ma'no beradi:
    olish  (получение, dam olish)   ≠   o'lish  (смерть)
    olim   (olim, ilmiy xodim)      ≠   o'lim   (o'lim)
    oldi   (oldi)                   ≠   o'ldi   (vafot etdi)
  "dam olish" HAR DOIM apostrofsiz yoziladi. "dam o'lish" — og'ir xato.
- Raqam, o'lchov birligi, model kodi, brend nomi (masalan "1350 BT", "LM-TE2503",
  "0.5 L/soat") — TEGMA, o'zgarishsiz qaytar.
- Matn o'zbekcha bo'lmasa (inglizcha dizayn izohi, ruscha matn) — o'zgarishsiz qaytar.
- Matn allaqachon to'g'ri bo'lsa — aynan o'zini qaytar.

JAVOB FORMATI: faqat raqamlangan qatorlar, boshqa hech narsa yozma.
Kirish nechta qator bo'lsa, chiqish ham AYNAN shuncha qator bo'lsin.
1. <to'g'irlangan matn>
2. <to'g'irlangan matn>""",

    "ru": """Ты профессиональный корректор русского языка.
Тебе даётся список коротких текстов, которые будут напечатаны на инфографике маркетплейса.
Исправь грамматику и верни В ТОМ ЖЕ ФОРМАТЕ.

ЧТО ПРОВЕРЯТЬ:
1. Падеж: в предложении без глагола существительное стоит в ИМЕНИТЕЛЬНОМ падеже.
   НЕВЕРНО: "ВОДУ ВСЕГДА ГОТОВА"  ->  ВЕРНО: "ВОДА ВСЕГДА ГОТОВА"
2. Согласование в роде и числе: "Вода горячий" -> "Вода горячая".
3. Опечатки, пропущенные ё, латиница внутри кириллических слов.
4. Кальки с английского — переписать естественно.

СТРОГИЕ ПРАВИЛА:
- НЕ меняй смысл, НЕ добавляй слов, не удлиняй и не сокращай текст.
- Если текст В ВЕРХНЕМ РЕГИСТРЕ — ответ тоже в верхнем регистре.
- Числа, единицы измерения, коды моделей, названия брендов ("1350 Вт",
  "LM-TE2503") — НЕ ТРОГАЙ.
- Если текст не на русском (английская дизайн-инструкция) — верни без изменений.
- Если текст уже корректен — верни его как есть.

ФОРМАТ ОТВЕТА: только нумерованные строки, ничего больше.
Сколько строк на входе — РОВНО столько же на выходе.
1. <исправленный текст>
2. <исправленный текст>""",
}


# Apostrof qo'shilishi so'zning ma'nosini butunlay o'zgartiradigan juftliklar.
# Chapdagi — to'g'ri so'z, o'ngdagi — apostrof qo'shilgan XATO varianti.
_DANGEROUS_PAIRS = [
    ("olish", "o'lish"),
    ("olim", "o'lim"),
    ("oldi", "o'ldi"),
    ("oladi", "o'ladi"),
    ("olgan", "o'lgan"),
    ("olsin", "o'lsin"),
    ("olamiz", "o'lamiz"),
]


def _has_dangerous_apostrophe(old_t: str, new_t: str) -> bool:
    """Korrektor xavfli apostrof qo'shib yubordimi?"""
    o, n = old_t.lower(), new_t.lower()
    for safe, danger in _DANGEROUS_PAIRS:
        if danger in n and danger not in o:
            return True
    return False


def proofread_image_text(prompt: str, text_lang: str) -> str:
    """Promptdagi qo'shtirnoq ichidagi matnlarni grammatik tekshiruvdan o'tkazadi.

    Xatolik yuz bersa original promptni o'zgarishsiz qaytaradi (fail-open) —
    generatsiya hech qachon proofread tufayli to'xtab qolmasin.
    """
    if not prompt:
        return prompt

    # Takrorlanmaydigan, tartibi saqlangan ro'yxat
    seen, items = set(), []
    for m in _QUOTED_RE.finditer(prompt):
        t = m.group(1).strip()
        if not t or t in seen:
            continue
        # Sof raqam/o'lchov — tekshirishga hojat yo'q
        if not re.search(r"[A-Za-z\u0400-\u04FF]{3,}", t):
            continue
        seen.add(t)
        items.append(t)

    if not items:
        return prompt

    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(items))
    try:
        r = _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": PROOFREAD_SYSTEM.get(text_lang, PROOFREAD_SYSTEM["uz"])},
                {"role": "user", "content": numbered},
            ],
            max_tokens=1200, temperature=0,
        )
        raw = r.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"proofread_image_text xatolik: {e} — original prompt ishlatiladi")
        return prompt

    fixed = []
    for line in raw.splitlines():
        line = line.strip()
        m = re.match(r"^\d+\s*[.)]\s*(.+)$", line)
        if m:
            fixed.append(m.group(1).strip().strip('"'))

    # Qatorlar soni mos kelmasa — ishonchsiz, tegmaymiz
    if len(fixed) != len(items):
        logger.warning(
            f"proofread: qator soni mos emas ({len(fixed)} != {len(items)}) — o'zgarishsiz qoldirildi"
        )
        return prompt

    changed = 0
    for old_t, new_t in zip(items, fixed):
        if not new_t or new_t == old_t:
            continue

        # (a) Uzunlik keskin o'zgargan — model matnni qayta yozib yuborgan
        if abs(len(new_t) - len(old_t)) > max(12, len(old_t) * 0.5):
            logger.warning(f"proofread RAD: '{old_t}' -> '{new_t}' (uzunlik farqi)")
            continue

        # (b) Faqat harf registri o'zgargan — bu grammatik tuzatish emas.
        #     Registrni infografika prompti belgilaydi, korrektor emas.
        if new_t.lower() == old_t.lower():
            logger.warning(f"proofread RAD: '{old_t}' -> '{new_t}' (faqat registr)")
            continue

        # (c) Xavfli apostrof qo'shilishi. Masalan "dam olish" -> "dam o'lish".
        #     Model registrni o'zgartirayotganda shu xatoni qiladi va natija
        #     grammatik jihatdan to'g'ri, lekin ma'no jihatdan halokatli bo'ladi.
        if _has_dangerous_apostrophe(old_t, new_t):
            logger.warning(f"proofread RAD: '{old_t}' -> '{new_t}' (xavfli apostrof)")
            continue

        prompt = prompt.replace(f'"{old_t}"', f'"{new_t}"')
        changed += 1
        logger.info(f"proofread tuzatdi: '{old_t}' -> '{new_t}'")

    logger.info(f"proofread: {len(items)} matn tekshirildi, {changed} ta tuzatildi")
    return prompt


EXTRACT_SPECS_SYSTEM = """You are a strict data extraction tool. You do NOT write marketing copy, you do NOT
invent anything, you do NOT compute anything. You ONLY pull out what is literally written in the input text.

You will receive a product TITLE and/or FEATURES text written by a seller. Extract ONLY what is explicitly
stated, into this exact JSON shape:

{
  "headline_material": "<short phrase from the title capturing product type + key selling point, or empty string>",
  "subtitle_material": "<brand name and/or model code if literally present in the title, or empty string>",
  "badges": [
    {"value": "<number + unit EXACTLY as written, e.g. '32 L', '5.1 ML', '220 gramm'>"}
  ],
  "features": ["<short feature point derived from the features text>", "..."]
}

HARD RULES:
1. "badges" may ONLY contain values that are a number + unit LITERALLY present in the title or features text.
   NEVER compute, round, average, or derive a number. NEVER decode a model/article code (e.g. "4218 E") into
   a spec value. NEVER invent a plausible value for the product category (age range, height, weight, etc.)
   if it is not literally written in the text.
2. "badges" array length is capped at 3. If the text contains MORE than 3 explicit numeric specs, keep ONLY
   the 3 most purchase-relevant ones — prioritize in this order: volume/capacity > size/dimensions > weight
   > power/wattage > count/quantity > other. Drop identifiers (model codes, SKUs, article numbers) entirely —
   they are never badges.
3. If the text contains ZERO explicit numeric specs, "badges" MUST be an empty array []. Do not fill it with
   anything, ever.
4. "headline_material" and "subtitle_material" come ONLY from the title text (if given). If no title given,
   both are empty strings.
5. "features" come ONLY from the features text (if given), split into short standalone points. If no features
   given, this is an empty array.
6. Output ONLY the JSON object, nothing else — no markdown fences, no explanation."""


def extract_structured_specs(user_title=None, user_features=None):
    """
    Foydalanuvchi yozgan xom title/feature matnini tahlil qilib, faqat matnda
    so'zma-so'z mavjud narsalarni struktura (dict) shaklida ajratib beradi.
    Hech narsa o'ylab topilmaydi — badge soni shu yerda 3 tagacha cheklanadi.
    Xatolik yuz bersa fail-safe: bo'sh struktura qaytadi (badge'siz, xavfsiz holat).
    """
    empty = {"headline_material": "", "subtitle_material": "", "badges": [], "features": []}
    if not user_title and not user_features:
        return empty

    parts = []
    if user_title:
        parts.append(f"TITLE:\n{user_title}")
    if user_features:
        parts.append(f"FEATURES:\n{user_features}")
    user_content = "\n\n".join(parts)

    try:
        r = _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": EXTRACT_SPECS_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            max_tokens=600, temperature=0,
        )
        raw = r.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        data = json.loads(raw)
    except Exception as e:
        logger.warning(f"extract_structured_specs xatolik: {e} — bo'sh struktura qaytariladi (fail-safe)")
        return empty

    # Kod darajasida qo'shimcha xavfsizlik — 3 tadan ortiq badge hech qachon o'tmasin,
    # struktura JSON formatiga mos kelmasa ham funksiya baribir yiqilmasin.
    badges = data.get("badges") or []
    if not isinstance(badges, list):
        badges = []
    badges = [b for b in badges if isinstance(b, dict) and b.get("value")][:3]

    features = data.get("features") or []
    if not isinstance(features, list):
        features = []

    return {
        "headline_material": str(data.get("headline_material") or ""),
        "subtitle_material": str(data.get("subtitle_material") or ""),
        "badges": badges,
        "features": [str(f) for f in features],
    }


def write_infographic_prompt(analysis, text_lang, allow_brand=False, user_title=None, user_features=None):
    lang_name = "Uzbek" if text_lang == "uz" else "Russian"

    # 1-bosqich: xom title/feature matnidan faqat haqiqatan mavjud narsalarni
    # ajratib olamiz (badge soni bu yerda allaqachon max 3 ga cheklangan).
    specs = extract_structured_specs(user_title, user_features)
    include_badges = len(specs["badges"]) > 0

    user_override = ""
    if specs["headline_material"] or specs["subtitle_material"]:
        user_override += (
            f"\n\n⚠️ MANDATORY HEADLINE OVERRIDE — use this pre-extracted material (already verified against "
            f"the user's original text, do not add anything beyond it):\n"
            f"- MAIN HEADLINE (large, bold, 2-5 words) should be based on: \"{specs['headline_material']}\"\n"
            + (f"- SUBTITLE (smaller text, ONE line) should be based on: \"{specs['subtitle_material']}\"\n" if specs["subtitle_material"] else "")
            + f"Adapt wording/length to fit the required format, but do not introduce new claims. "
            f"All of this text MUST be entirely in {lang_name} — translate first if the source was in another language."
        )
    if specs["features"]:
        features_str = "; ".join(specs["features"])
        user_override += (
            f"\n\n⚠️ MANDATORY FEATURES OVERRIDE: The 3-4 feature list items on the infographic MUST be "
            f"based on these pre-extracted feature points, preserving their meaning (rewrite into the "
            f"required short style; do NOT replace them with unrelated generic features, do NOT add new "
            f"ones beyond what's listed here): {features_str}\n"
            f"All feature text MUST be entirely in {lang_name} — translate first if the source was in another language."
        )
    if include_badges:
        badge_values = ", ".join(f"\"{b['value']}\"" for b in specs["badges"])
        user_override += (
            f"\n\n⚠️ MANDATORY BADGE OVERRIDE: create EXACTLY {len(specs['badges'])} badge(s) — no more, no "
            f"fewer — using ONLY these pre-verified values, copied exactly as given: {badge_values}\n"
            f"These are already filtered and capped at 3 — never render more than {len(specs['badges'])} "
            f"badges even if the analysis text below seems to suggest other numbers. Stack them vertically "
            f"if there is more than one. If the values represent ALTERNATIVE VARIANTS (e.g. size/volume "
            f"options the buyer chooses between), write ONE shared caption for the whole block instead of "
            f"a different label per badge. Do NOT invent a label if you're unsure what the number means — "
            f"showing the value with its unit and no label is correct. All badge text MUST be entirely in "
            f"{lang_name} — translate the unit/label if needed, but never change the numeric value."
        )

    r = _client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": get_infographic_prompt_system(text_lang, allow_brand=allow_brand, include_badges=include_badges)},
            {"role": "user", "content": f"Based on this product analysis, write the image generation prompt:\n\n{analysis}{user_override}"},
        ],
        max_tokens=2000, temperature=0.7,
    )
    prompt = r.choices[0].message.content.strip()
    logger.info(f"Infographic prompt: {len(prompt)} chars, badges={'on (' + str(len(specs['badges'])) + ')' if include_badges else 'off'}")
    prompt = proofread_image_text(prompt, text_lang)
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

def write_promo_prompts(analysis, text_lang, allow_brand=False, user_title=None, user_features=None):
    """2 ta FARQLI tavsif rasm prompti yozadi"""
    lang_name = "Uzbek" if text_lang == "uz" else "Russian"
    user_override = ""
    if user_title:
        user_override += (
            f"\n\n⚠️ This is the user-provided product name/title: \"{user_title}\"\n"
            f"Do NOT cram this entire text as-is into the headline if it's long/technical (brand + model code + "
            f"volume/size etc). Instead extract the catchy product-type/benefit part for the main headline "
            f"(short, 2-5 words), and put brand/model code as a smaller subtitle and any numeric spec "
            f"(volume/size) as a small badge — only if that info is actually present. Preserve meaning. "
            f"All text on the image MUST be entirely in {lang_name} — if this is written in a different "
            f"language, TRANSLATE it into {lang_name} first."
        )
    if user_features:
        user_override += (
            f"\n\n⚠️ Feature callouts must be based on these user-provided features, preserving their meaning "
            f"(don't invent unrelated ones). All text on the image MUST be entirely in {lang_name} — if this "
            f"is written in a different language, TRANSLATE it into {lang_name} first: \"{user_features}\""
        )
    if allow_brand:
        promo_brand_rule = "- Brand name allowed ONLY if it was given in the analysis (visible on product) or explicitly provided by the user — use it exactly as given, do not invent or translate it"
    else:
        promo_brand_rule = "- ABSOLUTELY NO brand names or logos on the image — brand names cause product blocking\n- Use product type and features instead of brand name"
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
{promo_brand_rule}
- Square 1:1 format
- Ultra realistic, commercial advertising quality
- All text in {lang_name}, in "quotes", short and impactful
- Text must sound like a real marketplace seller wrote it — not a translator
- NO banned words (акция/aksiya, скидка/chegirma, лучший/eng yaxshi, топ/top, хит/xit, бесплатно/bepul)"""},
{"role": "user", "content": f"Write 2 COMPLETELY DIFFERENT promo image prompts for:\n\n{analysis}{user_override}"},
],
        max_tokens=2000, temperature=0.8,
)
    raw = r.choices[0].message.content.strip()
    parts = re.split(r'---PROMPT2---|---', raw)
    prompts = [p.strip() for p in parts if p.strip()]
    logger.info(f"Promo prompts: {len(prompts)} generated")
    prompts = [proofread_image_text(p, text_lang) for p in prompts]
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

def gen_card_step1(image_bytes, text_lang, user_title=None, user_features=None, allow_brand=False):
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    brand_note = (
        "If a brand name is clearly visible on the product or was given by the user, you may include it exactly as given. "
        if allow_brand else "NO brand names. "
    )
    instruction = f"Generate product name (70-90 chars), SEO keywords (300-390 chars), and features list. {brand_note}"
    if user_title:
        instruction += (
            f"\n\nFoydalanuvchi taklif qilgan mahsulot nomi (buni asos qilib oling, "
            f"70-90 belgi formatiga moslab qayta yozing, ikkala tilda ham (name_uz va name_ru) — "
            f"agar matn boshqa tilda yozilgan bo'lsa, avval kerakli tilga TARJIMA qiling, "
            f"tillarni aralashtirmang): {user_title}"
        )
    if user_features:
        instruction += (
            f"\n\nFoydalanuvchi ko'rsatgan xususiyatlar (bularni albatta ANIQ PARAMETR "
            f"formatida ro'yxatga kiriting, ikkala tilda ham (feat_uz va feat_ru) — "
            f"agar matn boshqa tilda yozilgan bo'lsa, avval kerakli tilga TARJIMA qiling, "
            f"tillarni aralashtirmang): {user_features}"
        )
    r = _client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": CARD_TEXT_SYSTEM.get(text_lang, CARD_TEXT_SYSTEM["ru"])},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                {"type": "text", "text": instruction},
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

def gen_card_step2(image_bytes, text_lang, context, allow_brand=False):
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    brand_instr = "" if allow_brand else " Brend nomini qo'shma."
    r = _client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": DESCRIPTION_SYSTEM.get(text_lang, DESCRIPTION_SYSTEM["ru"])},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
                {"type": "text", "text": f"Mahsulot:\n{context}\n\nUZUN tavsif yoz, har tilda KAMIDA 1500 belgi, 10-12 paragraf.{brand_instr}"},
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
# FOYDALANUVCHI KIRITGAN SARLAVHA/XUSUSIYAT VALIDATSIYASI (v2)
# ══════════════════════════════════════════════════════════════════

def validate_user_text(text: str, kind: str, text_lang: str = "uz") -> tuple[bool, str]:
    """
    Foydalanuvchi yozgan sarlavha/xususiyat matnini tekshiradi.
    kind: "title" yoki "features"
    Qaytaradi: (is_valid, error_message_yoki_bosh_qator)
    """
    text = (text or "").strip()

    # Tezkor heuristika — juda qisqa yoki juda uzun matnni AI'gacha filtrlaymiz
    if len(text) < 2:
        msg = "Matn juda qisqa. Iltimos, mahsulot haqida to'liqroq yozing." if text_lang == "uz" \
            else "Текст слишком короткий. Пожалуйста, напишите подробнее о товаре."
        return False, msg
    if len(text) > 500:
        msg = "Matn juda uzun (max 500 belgi). Iltimos, qisqartiring." if text_lang == "uz" \
            else "Текст слишком длинный (макс. 500 симв). Пожалуйста, сократите."
        return False, msg

    kind_label = "mahsulot nomi/sarlavhasi" if kind == "title" else "mahsulot xususiyatlari"
    check_prompt = f"""Foydalanuvchi Telegram bot orqali {kind_label} sifatida quyidagi matnni yozdi:

"{text}"

Bu matn haqiqatan ham mahsulot {('nomi' if kind == 'title' else 'xususiyati/tavsifi')} sifatida mantiqiy va foydalanish mumkinmi?
Quyidagi holatlarda INVALID deb belgilang: bema'ni/random belgilar, haqoratli so'zlar, reklama/spam, mahsulotga umuman aloqasi yo'q matn (masalan siyosat, boshqa mavzu), yoki bo'sh mazmun.
Agar matn oddiy, qisqa bo'lsa ham mantiqiy mahsulot nomi/xususiyati bo'lsa — VALID deb belgilang (qisqa bo'lishi muammo emas).

Faqat shu formatda javob bering, boshqa hech narsa yozmang:
VALID
yoki
INVALID: <qisqa sabab, foydalanuvchiga tushunarli tilda>"""

    try:
        r = _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": check_prompt}],
            max_tokens=100, temperature=0,
        )
        result = r.choices[0].message.content.strip()
        if result.upper().startswith("VALID"):
            return True, ""
        reason = result.split(":", 1)[1].strip() if ":" in result else result
        return False, reason
    except Exception as e:
        logger.warning(f"validate_user_text xatolik: {e} — matn qabul qilinadi (fail-open)")
        return True, ""  # AI xato bersa, foydalanuvchini bloklamaymiz


# ══════════════════════════════════════════════════════════════════
# FOYDALANUVCHI MATNINI OLDINDAN TARJIMA QILISH (v2)
# ══════════════════════════════════════════════════════════════════
# Sabab: agar tarjimani rasm-prompt yozadigan modelga topshirsak, u ba'zida
# to'liq tarjima qilmasdan, original tildagi so'zlarni boshqa alifboga
# fonetik o'girib qo'yadi (masalan o'zbekcha lotin -> kirillcha, tarjima
# qilinmagan holda). Shuning uchun bu yerda ALOHIDA, aniq tarjima so'rovi
# bilan matnni oldindan tozalab olamiz.

def translate_user_text(text: str, target_lang: str) -> str:
    """
    Foydalanuvchi yozgan matnni target_lang ('uz' yoki 'ru') tiliga tarjima qiladi.
    Agar matn allaqachon o'sha tilda bo'lsa, deyarli o'zgarishsiz qaytadi.
    """
    text = (text or "").strip()
    if not text:
        return text
    target_name = "Uzbek (Latin script)" if target_lang == "uz" else "Russian"
    grammar_note = (
        ' The result must be grammatically correct Uzbek: in a verbless nominal phrase the noun '
        'stays in the nominative case — never attach -ni / -ga / -da to it '
        '(WRONG: "Suvni har doim tayyor", RIGHT: "Suv har doim tayyor"). '
        "Use proper Latin apostrophes: o' and g'."
        if target_lang == "uz" else
        ' The result must be grammatically correct Russian (correct case and gender agreement).'
    )
    prompt = (
        f'Translate the following product-related text into {target_name}. '
        f'If it is already in {target_name}, just clean it up slightly (fix typos) and return as-is.'
        f'{grammar_note} '
        f'Return ONLY the translated text, nothing else — no quotes, no explanation, no original text:\n\n{text}'
    )
    try:
        r = _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300, temperature=0.2,
        )
        result = r.choices[0].message.content.strip().strip('"')
        return result if result else text
    except Exception as e:
        logger.warning(f"translate_user_text xatolik: {e} — original matn ishlatiladi")
        return text