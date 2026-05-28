"""Human behaviour simulation — type, click, scroll, delay."""

import asyncio
import random
from typing import Optional

from playwright.async_api import ElementHandle, Page, TimeoutError as PlaywrightTimeout

from config.settings import settings
from utils.logger import logger

_TYPING_DELAY_MIN_MS = 60
_TYPING_DELAY_MAX_MS = 220
_MICRO_PAUSE_PROB = 0.04
_MICRO_PAUSE_MIN = 0.2
_MICRO_PAUSE_MAX = 0.6
_SHORT_DELAY_MIN = 0.3
_SHORT_DELAY_MAX = 1.2
_DEFAULT_SELECTOR_TIMEOUT = 15000


async def delay(min_s: Optional[float] = None, max_s: Optional[float] = None) -> None:
    """Sleep for a random duration between min_s and max_s seconds."""
    lo = min_s if min_s is not None else settings.min_delay_seconds
    hi = max_s if max_s is not None else settings.max_delay_seconds
    await asyncio.sleep(random.uniform(lo, hi))


async def short_delay() -> None:
    """Brief pause (0.3-1.2s) used between micro-actions."""
    await asyncio.sleep(random.uniform(_SHORT_DELAY_MIN, _SHORT_DELAY_MAX))


async def human_type(page: Page, selector: str, text: str) -> None:
    """Type text character-by-character at human-like speeds.

    Never uses page.fill() directly — that is instant and easily detected.
    """
    try:
        await page.click(selector, timeout=_DEFAULT_SELECTOR_TIMEOUT)
        await short_delay()
        await page.fill(selector, "")
        await asyncio.sleep(random.uniform(0.1, 0.3))
        for char in text:
            delay_ms = random.randint(_TYPING_DELAY_MIN_MS, _TYPING_DELAY_MAX_MS)
            await page.type(selector, char, delay=delay_ms)
            if random.random() < _MICRO_PAUSE_PROB:
                await asyncio.sleep(random.uniform(_MICRO_PAUSE_MIN, _MICRO_PAUSE_MAX))
    except PlaywrightTimeout:
        logger.warning(f"human_type timeout for selector: {selector}")
    except Exception as e:
        logger.error(f"human_type error on '{selector}': {e}")


async def human_click(page: Page, selector: str, timeout: int = _DEFAULT_SELECTOR_TIMEOUT) -> bool:
    """Click an element at a random coordinate within its bounding box."""
    try:
        element: Optional[ElementHandle] = await page.wait_for_selector(selector, timeout=timeout)
        if not element:
            logger.warning(f"human_click element not found: {selector}")
            return False

        await element.scroll_into_view_if_needed()
        import asyncio
        await asyncio.sleep(0.3)

        box = await element.bounding_box()
        if box:
            x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
            y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
            steps = random.randint(8, 20)
            await page.mouse.move(x, y, steps=steps)
            await short_delay()
            await page.mouse.click(x, y)
        else:
            await element.click()
        return True
    except PlaywrightTimeout:
        logger.warning(f"human_click timeout for: {selector}")
        return False
    except Exception as e:
        logger.error(f"human_click error on '{selector}': {e}")
        return False


async def scroll_page(page: Page) -> None:
    """Scroll the page in variable increments to simulate reading."""
    num_scrolls = random.randint(2, 5)
    for _ in range(num_scrolls):
        scroll_px = random.randint(100, 350)
        await page.evaluate(f"window.scrollBy(0, {scroll_px})")
        await asyncio.sleep(random.uniform(0.4, 1.5))
        if random.random() < 0.30:
            back_px = random.randint(30, 100)
            await page.evaluate(f"window.scrollBy(0, -{back_px})")
            await asyncio.sleep(random.uniform(0.3, 0.8))


async def simulate_reading(page: Page) -> None:
    """Simulate a human reading the page before taking action."""
    await asyncio.sleep(random.uniform(1.5, 4.0))
    await scroll_page(page)
