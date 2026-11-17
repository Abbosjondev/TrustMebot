from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..config import Settings
from ..errors import (DocGuardError, ImageTooLargeError, ImageTooSmallError,
                      InvalidImageError)
from ..service import ProtectionService
from . import texts
from . import keyboards
from .runner import JobRunner
from .states import ProtectStates, VerifyStates

log = logging.getLogger(__name__)
router = Router(name="docguard")

IMAGE = F.photo | F.document.mime_type.startswith("image/")


@dataclass(frozen=True)
class FileRef:
    file_id: str
    size: int | None


def _file_ref(message: Message) -> FileRef | None:
    if message.photo:
        best = message.photo[-1]
        return FileRef(best.file_id, best.file_size)
    doc = message.document
    if doc and (doc.mime_type or "").startswith("image/"):
        return FileRef(doc.file_id, doc.file_size)
    return None


async def _download(bot: Bot, ref: FileRef, settings: Settings) -> bytes:
    if ref.size and ref.size > settings.max_file_bytes:
        raise _FileTooBig
    buf = io.BytesIO()
    await bot.download(ref.file_id, destination=buf)
    data = buf.getvalue()
    if len(data) > settings.max_file_bytes:
        raise _FileTooBig
    return data


class _FileTooBig(Exception):
    pass


async def _reply_error(message: Message, exc: Exception, settings: Settings,
                       service: ProtectionService) -> None:
    if isinstance(exc, _FileTooBig):
        text = texts.TOO_BIG_FILE.format(mb=settings.max_file_bytes // (1024 * 1024))
    elif isinstance(exc, ImageTooLargeError):
        text = texts.TOO_LARGE_IMAGE
    elif isinstance(exc, ImageTooSmallError):
        text = texts.TOO_SMALL_IMAGE.format(px=service.params.min_side)
    elif isinstance(exc, InvalidImageError):
        text = texts.INVALID_IMAGE
    elif isinstance(exc, DocGuardError):
        text = str(exc)
    else:
        log.exception("Kutilmagan xato", exc_info=exc)
        text = texts.UNEXPECTED
    await message.answer(text)


# --------------------------------------------------------------------------- menu actions
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.START, reply_markup=keyboards.main())


async def _show_help(message: Message) -> None:
    await message.answer(texts.HELP)


async def _start_verify(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(VerifyStates.waiting_image)
    await message.answer(texts.ASK_VERIFY, reply_markup=keyboards.cancel())


async def _show_records(message: Message, service: ProtectionService) -> None:
    records = service.repo.list_records(message.from_user.id, 10)
    if not records:
        await message.answer(texts.NO_RECORDS)
        return
    lines = [f"{service.local_time(r.created_at):%d.%m.%Y %H:%M} — {escape(r.label)}" for r in records]
    await message.answer("🗂 <b>Oxirgi muhrlar</b>\n\n" + "\n".join(lines))


@router.message(F.text == keyboards.VERIFY)
async def menu_verify(message: Message, state: FSMContext) -> None:
    await _start_verify(message, state)


@router.message(F.text == keyboards.RECORDS)
async def menu_records(message: Message, service: ProtectionService) -> None:
    await _show_records(message, service)


@router.message(F.text == keyboards.HELP)
async def menu_help(message: Message) -> None:
    await _show_help(message)


@router.callback_query(F.data == keyboards.PROTECT_CALLBACK)
async def callback_protect(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    data = await state.get_data()
    refs = data.get("pending", [])
    if not refs:
        if query.message:
            await query.message.answer("Rasm topilmadi. Qaytadan rasm yuboring.")
        return
    if not query.message:
        return
    label = data.get("label")
    if label:
        await state.set_state(ProtectStates.waiting_visible)
        await query.message.edit_reply_markup(reply_markup=None)
        await query.message.answer(texts.ASK_VISIBLE, reply_markup=keyboards.visible_choice())
    else:
        await state.set_state(ProtectStates.waiting_label)
        await query.message.edit_reply_markup(reply_markup=None)
        await query.message.answer(texts.ASK_LABEL, reply_markup=keyboards.cancel())


@router.callback_query(F.data == keyboards.VERIFY_CALLBACK)
async def callback_verify(query: CallbackQuery, state: FSMContext, bot: Bot,
                          service: ProtectionService, runner: JobRunner,
                          settings: Settings) -> None:
    await query.answer()
    data = await state.get_data()
    refs = [FileRef(**ref) for ref in data.get("pending", [])]
    if not refs:
        if query.message:
            await query.message.answer("Rasm topilmadi. Qaytadan rasm yuboring.")
        return
    if not query.message:
        return
    await state.clear()
    await query.message.edit_reply_markup(reply_markup=None)
    await _verify_all(query.message, refs, query.from_user.id, bot, service, runner, settings)


@router.callback_query(F.data.in_({
    keyboards.VISIBLE_YES_CALLBACK,
    keyboards.VISIBLE_NO_CALLBACK,
}))
async def callback_visible_choice(query: CallbackQuery, state: FSMContext, bot: Bot,
                                  service: ProtectionService, runner: JobRunner,
                                  settings: Settings) -> None:
    await query.answer()
    data = await state.get_data()
    refs = [FileRef(**ref) for ref in data.get("pending", [])]
    label = data.get("label")
    if not refs or not label:
        if query.message:
            await query.message.answer("Ma'lumot topilmadi. Qaytadan rasm yuboring.")
        return
    if not query.message:
        return
    visible = query.data == keyboards.VISIBLE_YES_CALLBACK
    await state.clear()
    await query.message.edit_reply_markup(reply_markup=None)
    await _protect_all(query.message, refs, label, query.from_user.id, bot, service, runner,
                       settings, visible)


@router.callback_query(F.data == keyboards.CANCEL_CALLBACK)
async def callback_cancel(query: CallbackQuery, state: FSMContext) -> None:
    await query.answer()
    await state.clear()
    if query.message:
        await query.message.edit_reply_markup(reply_markup=None)
        await query.message.answer(texts.CANCELLED)


# --------------------------------------------------------------------------- verify flow
@router.message(VerifyStates.waiting_image, IMAGE)
async def on_verify_image(message: Message, state: FSMContext, bot: Bot, service: ProtectionService,
                          runner: JobRunner, settings: Settings) -> None:
    ref = _file_ref(message)
    assert ref is not None
    await state.clear()
    await _verify_all(message, [ref], message.from_user.id, bot, service, runner, settings)


@router.message(VerifyStates.waiting_image)
async def on_verify_wrong_input(message: Message) -> None:
    await message.answer(texts.NOT_AN_IMAGE, reply_markup=keyboards.cancel())


# --------------------------------------------------------------------------- protect flow
@router.message(ProtectStates.waiting_label, F.text, ~F.text.startswith("/"))
async def on_label(message: Message, state: FSMContext, bot: Bot, service: ProtectionService,
                   runner: JobRunner, settings: Settings) -> None:
    label = (message.text or "").strip()
    if not label:
        await message.answer(texts.LABEL_EMPTY)
        return
    await state.update_data(label=label)
    await state.set_state(ProtectStates.waiting_visible)
    await message.answer(texts.ASK_VISIBLE, reply_markup=keyboards.visible_choice())


@router.message(IMAGE)
async def on_image(message: Message, state: FSMContext, bot: Bot, service: ProtectionService,
                   runner: JobRunner, settings: Settings) -> None:
    ref = _file_ref(message)
    assert ref is not None
    current = await state.get_state()
    data = await state.get_data() if current in {
        ProtectStates.waiting_action.state,
        ProtectStates.waiting_label.state,
    } else {}
    pending = list(data.get("pending", []))
    pending.append({"file_id": ref.file_id, "size": ref.size})
    caption = (message.caption or "").strip()
    group_id = message.media_group_id
    await state.set_state(ProtectStates.waiting_action)
    await state.update_data(pending=pending, group_id=group_id, label=caption or data.get("label"))

    same_album = group_id is not None and group_id == data.get("group_id")
    if not same_album:
        await message.answer(texts.CHOOSE_ACTION, reply_markup=keyboards.protect_or_verify())


@router.message(ProtectStates.waiting_label)
async def on_label_wrong_input(message: Message) -> None:
    await message.answer("Iltimos, izohni matn ko'rinishida yozing.",
                         reply_markup=keyboards.cancel())


@router.message(F.document)
async def on_non_image_document(message: Message) -> None:
    await message.answer(texts.NOT_AN_IMAGE)


@router.message(F.text & ~F.text.startswith("/"))
async def on_plain_text(message: Message) -> None:
    await message.answer("Rasm yuboring — men unga ko'rinmas muhr qo'yaman.",
                         reply_markup=keyboards.main())


# --------------------------------------------------------------------------- helpers
async def _protect_all(message: Message, refs: list[FileRef], label: str, owner_id: int,
                       bot: Bot, service: ProtectionService, runner: JobRunner,
                       settings: Settings, visible: bool) -> None:
    status_msg = await message.answer(texts.WORKING)
    try:
        for i, ref in enumerate(refs, start=1):
            try:
                await bot.send_chat_action(message.chat.id, "upload_document")
                data = await _download(bot, ref, settings)
                result = await runner.run(service.protect, data,
                                          owner_id=owner_id, label=label,
                                          visible=visible)
            except Exception as exc:  # noqa: BLE001
                await _reply_error(message, exc, settings, service)
                continue
            name = f"himoyalangan_{result.created_at:%Y%m%d_%H%M%S}_{i}.jpg"
            await message.answer_document(BufferedInputFile(result.jpeg, filename=name),
                                          caption=texts.protected_caption(result))
    finally:
        await _safe_delete(status_msg)


async def _verify_all(message: Message, refs: list[FileRef], owner_id: int, bot: Bot,
                      service: ProtectionService, runner: JobRunner, settings: Settings) -> None:
    status_msg = await message.answer(texts.WORKING)
    try:
        for ref in refs:
            try:
                data = await _download(bot, ref, settings)
                result = await runner.run(service.verify, data, owner_id=owner_id)
            except Exception as exc:  # noqa: BLE001
                await _reply_error(message, exc, settings, service)
                continue
            await message.answer(texts.verify_text(result, service.local_time))
    finally:
        await _safe_delete(status_msg)


async def _safe_delete(msg: Message) -> None:
    try:
        await msg.delete()
    except TelegramAPIError:
        log.exception("Xabarni o'chirishda xato")
