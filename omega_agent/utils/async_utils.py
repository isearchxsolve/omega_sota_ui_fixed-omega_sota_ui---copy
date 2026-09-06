"""Async helpers."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, TypeVar

T = TypeVar("T")


class OmegaRecursionGuard:
    """Prevent infinite recursion in agent loops."""

    def __init__(self, max_depth: int = 50):
        self.depth = 0
        self.max_depth = max_depth

    def __enter__(self) -> "OmegaRecursionGuard":
        self.depth += 1
        if self.depth > self.max_depth:
            raise RecursionError(f"OMEGA recursion exceeded {self.max_depth}")
        return self

    def __exit__(self, *args) -> None:
        self.depth -= 1


async def run_with_timeout(coro, timeout: float):
    return await asyncio.wait_for(coro, timeout=timeout)


@asynccontextmanager
async def semaphore_limit(semaphore: asyncio.Semaphore) -> AsyncIterator[None]:
    await semaphore.acquire()
    try:
        yield
    finally:
        semaphore.release()


async def retry_async(
    fn: Callable[..., T],
    max_retries: int = 3,
    backoff: float = 1.0,
    *args,
    **kwargs,
) -> T:
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                await asyncio.sleep(backoff * attempt)
    raise last_error  # type: ignore[misc]
