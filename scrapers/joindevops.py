"""JoinDevOpsScraper — public job listings from JoinDevOps.com."""

import asyncio
import hashlib
from typing import List, Optional

from playwright.async_api import BrowserContext, TimeoutError as PlaywrightTimeout

from browser.human import delay, simulate_reading
from config.settings import settings
from scrapers.base import BaseScraper, JobListing
from utils.logger import logger

PLATFORM_NAME = "joindevops"
JOBS_URL = "https://jobs.joindevops.com/jobs"
LOGIN_URL = "https://joindevops.com/login"
MAX_CARDS = 15


class JoinDevOpsScraper(BaseScraper):
    """Scraper for JoinDevOps.com public job listings."""

    platform: str = PLATFORM_NAME

    async def login(self, context: BrowserContext) -> bool:
        """JoinDevOps doesn't require login for public access as per user."""
        return True

    async def scrape_jobs(self, context: BrowserContext) -> List[JobListing]:
        """Scrape job listings from the JoinDevOps jobs page."""
        page = await context.new_page()
        listings: List[JobListing] = []
        try:
            await page.goto(JOBS_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            await simulate_reading(page)

            # JBoard.io card selectors
            cards = await page.query_selector_all(".job-listings-item")
            cards = cards[:MAX_CARDS]
            logger.info(f"JoinDevOps {len(cards)} cards found")

            for card in cards:
                listing = await self._parse_card(card)
                if listing:
                    listings.append(listing)
        except Exception as e:
            logger.error(f"JoinDevOps scrape failed: {e}")
        finally:
            await page.close()

        logger.info(f"JoinDevOps total parsed: {len(listings)} listings")
        return listings

    async def _parse_card(self, card) -> Optional[JobListing]:
        try:
            title_el = await card.query_selector(".job-details-link")
            if not title_el:
                return None
            
            # Title is in h3 inside the link
            h3 = await title_el.query_selector("h3")
            title = (await h3.inner_text()).strip() if h3 else (await title_el.inner_text()).strip()
            
            href = await title_el.get_attribute("href") or ""
            if href and not href.startswith("http"):
                href = f"https://jobs.joindevops.com{href}"

            if not href: return None

            import hashlib
            job_id = hashlib.md5(href.encode()).hexdigest()[:12]
            prefixed_id = f"joindevops_{job_id}"

            # Company and Location are in job-info-link-item links
            info_links = await card.query_selector_all(".job-info-link-item")
            company = "JoinDevOps Partner"
            location = "Remote"
            
            if len(info_links) > 0:
                company = (await info_links[0].inner_text()).strip()
            if len(info_links) > 2:
                # Usually: [Company] • [Job Type] • [Location]
                location = (await info_links[2].inner_text()).strip()
            elif len(info_links) > 1:
                location = (await info_links[1].inner_text()).strip()

            return JobListing(
                id=prefixed_id,
                platform=PLATFORM_NAME,
                title=title,
                company=company,
                location=location,
                url=href,
                is_easy_apply=True,
            )
        except Exception as e:
            logger.debug(f"JoinDevOps card parse error: {e}")
            return None
