"""BaseScraper ABC and JobListing dataclass — the scraper contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

from playwright.async_api import BrowserContext


@dataclass
class JobListing:
    """Structured representation of a single job listing from any platform.

    The id field must be platform-prefixed (e.g. 'naukri_12345') to ensure
    global uniqueness across platforms in the SQLite jobs table.
    """

    id: str
    platform: str
    title: str
    company: str = ""
    location: str = ""
    url: str = ""
    description: str = ""
    salary: str = "Not disclosed"
    experience_required: str = ""
    posted_date: str = ""
    is_easy_apply: bool = False


class BaseScraper(ABC):
    """Abstract base class that all platform scrapers must implement."""

    platform: str = ""

    @abstractmethod
    async def login(self, context: BrowserContext) -> bool:
        """Log into the platform. Returns True if login succeeded."""
        ...

    @abstractmethod
    async def scrape_jobs(self, context: BrowserContext) -> List[JobListing]:
        """Scrape job listings for all configured keywords."""
        ...
