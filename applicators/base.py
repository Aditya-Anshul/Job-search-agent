"""BaseApplicator ABC and try_click_one() waterfall helper."""

from abc import ABC, abstractmethod
from typing import List

from playwright.async_api import BrowserContext, Page

from browser.human import human_click
from scrapers.base import JobListing
from utils.logger import logger


class ExternalRedirectException(Exception):
    """Exception raised when an application redirects to an external website."""
    def __init__(self, message: str = "Redirected to external company website"):
        self.message = message
        super().__init__(self.message)


class BaseApplicator(ABC):
    """Abstract base class for all platform-specific applicators."""

    platform: str = ""

    @abstractmethod
    async def apply(
        self,
        context: BrowserContext,
        job: JobListing,
        cover_letter: str,
        profile: dict = None,
    ) -> bool:
        """Submit an application for the given job listing.

        Returns True on success, False on any failure.
        """
        ...


async def try_click_one(page: Page, selectors: List[str], timeout: int = 3000) -> bool:
    """Try a list of CSS selectors in order, clicking the first one found."""
    for selector in selectors:
        try:
            logger.debug(f"Trying to click selector: {selector}")
            result = await human_click(page, selector, timeout=timeout)
            if result:
                logger.info(f"Successfully clicked: {selector}")
                return True
        except Exception:
            continue
    return False
