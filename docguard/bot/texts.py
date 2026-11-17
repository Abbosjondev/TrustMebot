"""Barcha foydalanuvchi matnlari bir joyda (HTML parse_mode)."""

from __future__ import annotations

from html import escape

from ..core.metadata import MetadataReport
from ..service import ProtectResult, VerifyResult, VerifyStatus

START = (
    "👋 <b>TrustMe bot</b> — rasmlaringizga <b>raqamli muhr</b> qo'yishda yordam beradi.\n\n"
    "Biror rasmni kimgadir yuborishdan oldin shu yerga yuboring. "
    "Bot rasmdan GPS va kamera, qurilma malumotlarini o'chiradi, rasmga muhr joylaydi "
    "va tayyor rasm faylini qaytaradi.\n\n"
    "<b>Qanday ishlatiladi</b>\n"
    "1. Rasmni yuboring.\n"
    "2. Rasm uchun izoh yozing, masalan: "
    "<i>Bu rasm Azizga tegishli, 01.11.2025</i>\n"
    "3. Qaytgan <b>faylni(rasm)</b>ni olib ishlating.\n\n"
    "“Tekshirish” orqali rasmni tekshirish mumki: bot muhrni o'qib, "
    "sizga javob beradi.\n\n"
    "Boshqaruv uchun pastdagi tugmalardan foydalaning; rasm yuborgach, amalni tanlang."
)

HELP = (
    "<b>Yordam</b>\n\n"
    "• Rasmga izoh (caption) yozib yuborsangiz, bot izohni muhr sifatida ishlatadi.\n"
    "• Bir nechta rasm yuborsangiz (albom), izoh hammasiga qo'llanadi.\n"
    "• “Tekshirish” — rasmdagi muhrni o'qish.\n"
    "• “Muhrlar ro'yxati” — oxirgi 10 ta muhr.\n\n"
    "<b>Muhim</b>\n"
    "• Muhr kuchli blur, juda qattiq qirqish yoki qayta chizishda zaiflashishi mumkin — "
    "100% kafolat berilmaydi.\n"
    "• Bot rasmlarni saqlamaydi: faqat muhr ID si va sizning izohingiz saqlanadi."
)

ASK_LABEL = (
    "✍️ Bu rasm uchun <b>muhr matnini</b> yuboring:\n\n"
    "<i>Masalan: Bu rasm Azizga tegishli, 01.11.2025</i>"
)
ASK_LABEL_MORE = "📥 Qo'shimcha rasm qabul qilindi (jami: {n}). Izohni yozing."
CHOOSE_ACTION = "📷 Rasm uchun amalni tanlang:"
ASK_VISIBLE = "🏷 Ko'rinadigan yozuv qo'shilsinmi?"
ASK_VERIFY = (
    "🔍 Tekshirmoqchi bo'lgan rasmni yuboring (fayl sifatida yuborsangiz aniqlik oshishi mumkin)."
)
CANCELLED = "Bekor qilindi."
NOTHING_TO_CANCEL = "Bekor qilinadigan amal yo'q."
WORKING = "⏳ Ishlanmoqda…"
LABEL_EMPTY = "Izoh bo'sh bo'lishi mumkin emas. Iltimos, matn yozing."
NOT_AN_IMAGE = "Faqat rasm qabul qilinadi (JPG, PNG, WebP…). PDF yoki boshqa fayllar hozircha qo'llab-quvvatlanmaydi."
TOO_BIG_FILE = "Fayl juda katta ({mb} MB gacha qo'llab quvvatlanadi)."
TOO_LARGE_IMAGE = "Rasm o'lchami juda katta. Iltimos, kichikroq variantini yuboring."
TOO_SMALL_IMAGE = "Rasm juda kichik — muhr qo'yish uchun kamida {px} px kerak."
INVALID_IMAGE = "Rasmni o'qib bo'lmadi. Fayl buzilgan yoki rasm emas."
DOWNLOAD_FAILED = "Faylni yuklab olib bo'lmadi. Qaytadan urinib ko'ring."
UNEXPECTED = "Kutilmagan xato yuz berdi. Qaytadan urinib ko'ring."
NO_RECORDS = "Hozircha muhrlar yo'q."


def _removed_items(m: MetadataReport) -> list[str]:
    items = []
    if m.has_gps:
        items.append("GPS koordinatalar")
    if m.camera:
        items.append(f"telefon modeli ({escape(m.camera)})")
    if m.captured_at:
        items.append("suratga olingan vaqt")
    if m.has_icc or m.has_xmp or m.has_comment or (m.has_exif and not items):
        items.append("boshqa texnik ma'lumotlar")
    return items


def protected_caption(r: ProtectResult) -> str:
    lines = ["✅ <b>Himoyalandi</b>\n", f"🔖 Muhr: <b>{escape(r.label)}</b>"]
    removed = _removed_items(r.metadata)
    lines.append("🧹 o'chirildi: " + ", ".join(removed) if removed else "🧹 Metama'lumot topilmadi")
    if r.visible_applied:
        lines.append("🏷 Ko'rinadigan yozuv qo'shildi")
    return "\n".join(lines)


def verify_text(r: VerifyResult, local_time) -> str:
    ex = r.extract
    if r.status is VerifyStatus.OWN and r.record:
        when = local_time(r.record.created_at)
        level = "yuqori" if ex.confidence >= 0.75 else "o'rtacha" if ex.confidence >= 0.4 else "past"
        return (
            "🚨 <b>Muhr topildi!</b>\n\n"
            f"🔖 {escape(r.record.label)}\n"
            f"🕒 Qo'yilgan vaqt: {when:%d.%m.%Y %H:%M}\n"
            f"📶 Signal sifati: {level} ({ex.confidence:.0%})"
        )
    if r.status is VerifyStatus.FOREIGN:
        return "ℹ️ Rasmda bu bot qo'ygan muhr bor, lekin u <b>sizga</b> tegishli emas."
    if r.status is VerifyStatus.UNKNOWN_ID:
        return ("⚠️ Muhr o'qildi, lekin mos yozuv yo'q.")
    return (
        "❔ <b>Muhr topilmadi.</b>\n\n"
        "Mumkin sabablar: rasmda muhr yo'q; rasm juda kuchli qirqilgan, xiralashtirilgan yoki "
        "qayta chizilgan (skrinshot/foto);"
        "Imkon bo'lsa, eng yuqori sifatli nusxasini fayl sifatida yuboring."
    )
