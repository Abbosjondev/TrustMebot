"""CPU-og‘ir ishlarni event loop'ni bloklamasdan bajarish + bir vaqtdagi ishlar sonini cheklash."""

from __future__ import annotations

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

T = TypeVar("T")


class JobRunner:
    """numpy GIL ni asosan qo'yib yuboradi, shuning uchun thread pool yetarli.

    Yuklama oshsa, ProcessPoolExecutor ga o'tish mumkin (service obyektini har bir
    jarayonda alohida yaratish kerak bo'ladi).
    """

    def __init__(self, max_workers: int) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="docguard")
        self._sem = asyncio.Semaphore(max_workers * 2)   # navbat chegarasi: RAM himoyasi

    async def run(self, fn: Callable[..., T], *args, **kwargs) -> T:
        async with self._sem:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._pool, functools.partial(fn, *args, **kwargs))

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
