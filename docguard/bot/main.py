from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from ..config import Settings
from ..service import ProtectionService
from ..storage import Repository
from .handlers import router
from .runner import JobRunner


async def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env(require_token=True)

    repo = Repository(settings.db_path)
    service = ProtectionService(settings, repo)
    runner = JobRunner(settings.max_workers)

    token = settings.bot_token
    if token is None:
        raise RuntimeError("Bot token is required")
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage(), service=service, runner=runner, settings=settings)
    dp.include_router(router)

    logging.getLogger(__name__).info("Bot running (params=%s)", service.params.fingerprint())
    try:
        await dp.start_polling(bot)
    finally:
        runner.shutdown()
        repo.close()
        await bot.session.close()
