from aiogram.fsm.state import State, StatesGroup


class ProtectStates(StatesGroup):
    waiting_action = State()  # rasm olindi, himoyalash yoki tekshirish tanlovi kutilmoqda
    waiting_label = State()   # rasm olindi, izoh kutilmoqda
    waiting_visible = State()  # izoh olindi, vizual yozuv tanlovi kutilmoqda


class VerifyStates(StatesGroup):
    waiting_image = State()   # Tekshirish tugmasi bosildi, rasm kutilmoqda
