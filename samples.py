"""
Namuna textlar — har bir tarif uchun
=====================================
Bu faylga bot orqali yasalgan eng chiroyli natijalarni joylashtirasiz.

Qo'llanma:
1. Botda tarif 2 yoki 4 ni tanlang
2. Mahsulot rasmini yuboring
3. Bot matnlarni generatsiya qiladi
4. Yoqqan natijani shu faylga nusxa qiling
5. Har bir tarif uchun UZ va RU versiyasi kerak

FORMAT: Oddiy string, Telegram HTML teglar bilan (<b>, <pre>)
"""

# ══════════════════════════════════════════════════════════════════
# TARIF 2: Infografika + Matn — namuna textlar
# ══════════════════════════════════════════════════════════════════

TARIF2_SAMPLE = """📌 <b>1. Tovar nomi</b>

🇺🇿: UZ
<pre>Chiroyli naqshli keramika chashka, qizil tutqich bilan, o'ziga xos dizayn</pre>

🇷🇺: RU
<pre>Красочная керамическая кружка с красной ручкой, уникальный дизайн</pre>

━━━━━━━━━━━━━━━━━━━━

📝 <b>2. Tovar qisqacha tavsifi</b>

🇺🇿: UZ
<pre>Chiroyli naqshli chashka, keramika, qizil tutqich, ichimliklar uchun, uy dekoratsiyasi, maxsus dizayn, qulay tutqich, zamonaviy uslub, ichimliklar, chashka, chashka sotib olish, chashka narxi, chashka dizayni, chashka sotilishi, chashka ishlab chiqarish, chashkalar, chashka to'plami, chashka tanlovi, chashka yangiliklari, chashka sifatlari</pre>

🇷🇺: RU
<pre>Красочная кружка, керамика, красная ручка, для напитков, домашний декор, уникальный дизайн, удобная ручка, современный стиль, напитки, покупка кружки, цена кружки, дизайн кружки, продажа кружек, производство кружек, набор кружек, выбор кружек, новости кружек, качества кружек</pre>

━━━━━━━━━━━━━━━━━━━━

📄 <b>3. Tovar tavsifi</b>

🇺🇿: UZ
<pre>Chiroyli naqshli keramika chashka, zamonaviy dizayni bilan har bir uyda o'ziga xos joy egallaydi. Ushbu chashka nafaqat ichimliklaringizni ichish uchun, balki uy dekoratsiyasi sifatida ham foydalanish uchun juda mos keladi. Uning o'ziga xos naqshlari va qizil tutqichi bu chashkani yanada jozibador qiladi. Har bir detali bilan sifatli keramika materialidan tayyorlangan, bu chashka sizga uzoq muddat xizmat qiladi.

Chashkaning hajmi 300 ml bo'lib, bu uni har xil ichimliklar uchun juda qulay qiladi. Qahva, choy yoki boshqa ichimliklar uchun mukammal, hatto sovuq ichimliklar uchun ham foydalanishingiz mumkin. Qizil tutqich, dizaynning o'ziga xosligini ta'kidlaydi va qulay tutish imkonini beradi, bu esa ichimliklarni ichish jarayonini yanada yoqimli qiladi.

Dizayn jihatidan, chashka zamonaviy uslubga ega bo'lib, har qanday ichimliklar uchun mos keladi. Uning naqshli dizayni nafaqat ko'rinishi, balki hissiyoti bilan ham ajralib turadi. Har bir naqshda tabiiy elementlar, gullar va o'simliklar tasvirlangan, bu esa chashkani yanada jozibador qiladi. Ushbu chashka har qanday joyda, xonada yoki ofisda mukammal ko'rinishga ega.

Ushbu keramika chashka yuvish uchun juda mos keladi, bu esa uning parvarishlashini osonlashtiradi. Siz uni oddiy yuvish vositalari bilan yuvishingiz mumkin, shuningdek, idish yuvish mashinasida ham yuvish mumkin. Shunday qilib, siz chashkadan foydalanishni yanada qulay va oson qilasiz. Uning mustahkam tuzilishi, har qanday zarbaga bardosh berish uchun mo'ljallangan, bu esa uni uzoq muddatli foydalanish uchun ideal qiladi.

Chashka o'ziga xos ko'rinishi bilan har qanday muhitda ajralib turadi. U nafaqat ichimliklar uchun, balki mehmonlar uchun sovg'a sifatida ham juda mos keladi. O'ziga xos dizayni va ranglari bilan, bu chashka har qanday odamni xursand qiladi. Shuningdek, u kichik va yengil bo'lib, har qanday joyga olib yurish uchun qulay.

Qadoqlash jihatidan, chashka ehtiyotkorlik bilan qadoqlangan, bu esa uning transporti davomida shikastlanishining oldini oladi. Siz uni o'zingizga yoki yaqinlaringizga sovg'a sifatida osongina olib kelishingiz mumkin. Uning narxi ham juda qulay, shuning uchun har kim o'ziga bunday chashka sotib olish imkoniyatiga ega.

Xulosa qilib aytganda, ushbu naqshli keramika chashka har qanday ichimliklar uchun mukammal tanlovdir. U nafaqat zamonaviy dizayni va qulayligi bilan, balki sifatli materiali bilan ham ajralib turadi. Har bir detali bilan o'ylangan ushbu chashka, sizning uy dekoratsiyangizga ajoyib qo'shimcha bo'ladi. Uni sotib olish orqali siz nafaqat ichimliklaringizni ichasiz, balki har bir ichimlikda go'zallikni his qilasiz.</pre>

🇷🇺: RU
<pre>Красивый керамический кружка с уникальным дизайном станет неотъемлемой частью любого дома. Эта кружка подходит не только для питья, но и как элемент декора. Ее оригинальные узоры и красная ручка делают кружку еще более привлекательной. Изготовленная из качественного керамического материала, эта кружка обеспечит вам долговечность и надежность.

Объем кружки составляет 300 мл, что делает ее идеальной для различных напитков. Подходит как для кофе, так и для чая, а также для холодных напитков. Красная ручка подчеркивает уникальность дизайна и обеспечивает удобный захват, что делает процесс питья еще более приятным.

С точки зрения дизайна, кружка имеет современный стиль и отлично подходит для любых напитков. Ее узорный дизайн выделяется не только внешним видом, но и ощущениями. На каждом узоре изображены природные элементы, цветы и растения, что делает кружку еще более привлекательной. Эта кружка будет прекрасно смотреться в любом месте, будь то комната или офис.

Керамическая кружка легко поддается мытью, что упрощает ее уход. Вы можете мыть ее обычными моющими средствами, а также в посудомоечной машине. Таким образом, использование кружки становится еще более удобным и простым. Ее прочная конструкция предназначена для выдерживания любых ударов, что делает ее идеальной для долговечного использования.

Кружка выделяется своим оригинальным внешним видом в любой среде. Она идеально подходит не только для напитков, но и как подарок для гостей. С своим уникальным дизайном и цветами, эта кружка порадует любого. Кроме того, она маленькая и легкая, что делает ее удобной для переноски.

С точки зрения упаковки, кружка аккуратно упакована, что предотвращает повреждения во время транспортировки. Вы можете легко взять ее с собой или подарить близким. Ее цена также очень доступна, поэтому каждый может позволить себе такую кружку.

В заключение, эта узорная керамическая кружка — отличный выбор для любых напитков. Она выделяется не только своим современным дизайном и удобством, но и качественным материалом. Каждая деталь продумана, и эта кружка станет замечательным дополнением к вашему домашнему декору. Покупая ее, вы не только будете пить напитки, но и наслаждаться красотой в каждом глотке.</pre>

━━━━━━━━━━━━━━━━━━━━

🏷 <b>4. Tovar xususiyatlari</b>

🇺🇿: UZ
<pre>Turi: chashka</pre>
<pre>Material:keramika</pre>
<pre>Rang: oq, qizil</pre>
<pre>Dizayn: gullar bilan bezatilgan</pre>
<pre>Tutqich: qulay va o'ziga xos</pre>
<pre>Hajmi: standart</pre>
<pre>Qulaylik: oson ushlash</pre>
<pre>Og'irlik: taxminan 300 g</pre>

🇷🇺: RU
<pre>Тип: чашка</pre>
<pre>Материал: керамика</pre>
<pre>Цвет: белый</pre>
<pre>Дизайн: украшена цветами</pre>
<pre>Ручка: удобная и уникальная</pre>
<pre>Размер: стандартный</pre>
<pre>Удобство: легкость удержания</pre>
<pre>Вес: примерно 300 г</pre>"""


# ══════════════════════════════════════════════════════════════════
# TARIF 4: To'liq paket — namuna textlar (tarif 2 bilan bir xil)
# ══════════════════════════════════════════════════════════════════

TARIF4_SAMPLE = TARIF2_SAMPLE


# ══════════════════════════════════════════════════════════════════
# NAMUNALARNI OLISH FUNKSIYASI
# ══════════════════════════════════════════════════════════════════

def get_sample_text(tariff: int) -> str | None:
    """Tarif raqamiga mos namuna textni qaytaradi (ikkala tilda birgalikda)"""
    samples = {
        2: TARIF2_SAMPLE,
        4: TARIF4_SAMPLE,
    }
    return samples.get(tariff)