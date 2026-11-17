from __future__ import annotations

import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from ..config import Settings
from ..errors import ConfigError
from ..service import ProtectionService
from ..storage import Repository
from .handlers import router
from .runner import JobRunner


async def _run_webhook(settings: Settings, bot: Bot, dp: Dispatcher) -> None:
    base_url = settings.webhook_base_url
    if not base_url:
        raise ConfigError("WEBHOOK_BASE_URL webhook rejimi uchun kerak")
    if not settings.webhook_secret:
        raise ConfigError("WEBHOOK_SECRET webhook rejimi uchun kerak")
    if not base_url.startswith("https://"):
        raise ConfigError("WEBHOOK_BASE_URL HTTPS bilan boshlanishi kerak")
    path = settings.webhook_path
    if not path.startswith("/"):
        raise ConfigError("WEBHOOK_PATH / bilan boshlanishi kerak")

    app = web.Application()
    webhook = SimpleRequestHandler(dispatcher=dp, bot=bot,
                                   secret_token=settings.webhook_secret)
    webhook.register(app, path=path)
    setup_application(app, dp, bot=bot)

    app_runner = web.AppRunner(app)
    await app_runner.setup()
    site = web.TCPSite(app_runner, settings.webhook_host, settings.webhook_port)
    await site.start()
    webhook_url = f"{base_url.rstrip('/')}{path}"
    await bot.set_webhook(webhook_url, secret_token=settings.webhook_secret,
                          drop_pending_updates=True)
    logging.getLogger(__name__).info(
        "Webhook running at %s (listen=%s:%s)",
        webhook_url,
        settings.webhook_host,
        settings.webhook_port,
    )
    try:
        await asyncio.Event().wait()
    finally:
        await bot.delete_webhook()
        await app_runner.cleanup()


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
        if settings.webhook_base_url:
            await _run_webhook(settings, bot, dp)
        else:
            await dp.start_polling(bot)
    finally:
        runner.shutdown()
        repo.close()
        await bot.session.close()
