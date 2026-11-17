from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

VERIFY = "🔍 Tekshirish"
PROTECT = "🛡 Himoyalash"
RECORDS = "🗂 Muhrlar ro'yxati"
HELP = "❓ Yordam"

VERIFY_CALLBACK = "action:verify"
PROTECT_CALLBACK = "action:protect"
VISIBLE_YES_CALLBACK = "action:visible:yes"
VISIBLE_NO_CALLBACK = "action:visible:no"
CANCEL_CALLBACK = "action:cancel"


def main() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=VERIFY)],
            [KeyboardButton(text=RECORDS), KeyboardButton(text=HELP)],
        ],
        resize_keyboard=True,
    )


def protect_or_verify() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=PROTECT, callback_data=PROTECT_CALLBACK),
                InlineKeyboardButton(text=VERIFY, callback_data=VERIFY_CALLBACK),
            ],
        ]
    )


def visible_choice() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha", callback_data=VISIBLE_YES_CALLBACK),
                InlineKeyboardButton(text="🚫 Yo'q", callback_data=VISIBLE_NO_CALLBACK),
            ],
        ]
    )


def cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✖️ Bekor qilish", callback_data=CANCEL_CALLBACK)]
        ]
    )
