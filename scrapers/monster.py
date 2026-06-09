"""MonsterScraper — login and job card scraping for Monster India."""

import asyncio
import re
from typing import List, Optional
from urllib.parse import quote_plus

from playwright.async_api import BrowserContext, TimeoutError as PlaywrightTimeout

from browser.human import delay, human_click, human_type, simulate_reading
from config.settings import settings
from scrapers.base import BaseScraper, JobListing
from utils.logger import logger

PLATFORM_NAME = "monster"
LOGIN_URL = "https://www.foundit.in/rio/login"
SEARCH_BASE = "https://www.foundit.in"
MAX_CARDS_PER_KEYWORD = 15


class MonsterScraper(BaseScraper):
    """Scraper for Foundit.in (formerly Monster India) job listings."""

    platform: str = PLATFORM_NAME

    async def login(self, context: BrowserContext) -> bool:
        """Log into Foundit.in with stored credentials."""
        page = await context.new_page()
        try:
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
            await delay(3, 5)

            # Check if already logged in (redirected to home/dashboard or other page)
            if any(k in page.url for k in ("dashboard", "home", "seeker", "profile", "account")):
                logger.success("Foundit already logged in")
                return True

            # Check for Akamai bot detection block
            title = await page.title()
            body_text = await page.inner_text("body")
            if "access denied" in title.lower() or "you don't have permission to access" in body_text.lower():
                logger.error(
                    "\n" + "!" * 80 + "\n"
                    "⚠️  FOUNDIT/MONSTER ACCESS DENIED: Akamai Bot Detection blocked the request (HTTP 403).\n"
                    "Foundit/Monster uses strict browser fingerprinting that blocks automated headless browsers.\n\n"
                    "👉 TO RESOLVE:\n"
                    "   1. Update your .env file to set: HEADLESS=false\n"
                    "   2. If running inside a headless server (VPS or Android UserLAnd), install Xvfb:\n"
                    "      sudo apt update && sudo apt install -y xvfb\n"
                    "      And run the agent using: xvfb-run python main.py\n" +
                    "!" * 80 + "\n"
                )
                return False

            # Handle cookie consent
            for sel in ["button#onetrust-accept-btn-handler", ".cookie-accept", "#accept-recommended-btn-handler", ".btn-accept", "button:has-text('Okay')"]:
                try:
                    btn = await page.query_selector(sel)
                    if btn:
                        await btn.click()
                        await asyncio.sleep(1)
                        break
                except Exception:
                    pass

            # Click standard password form switch
            pwd_span_sel = "span:has-text('Login via Password'), .text-brand-primary"
            pwd_span = await page.query_selector(pwd_span_sel)
            if pwd_span:
                logger.info("Foundit: Clicking 'Login via Password' switch...")
                await pwd_span.click()
                await delay(2, 3)

            email_sel = "input[name='userName'], input[type='text'], input[name='email'], input[type='email']"
            pwd_sel = "input[type='password'], input[name='password']"
            
            if await page.query_selector(email_sel):
                await human_type(page, email_sel, settings.monster_email or "")
                await human_type(page, pwd_sel, settings.monster_password or "")
                await delay(1.0, 2.0)
                await human_click(page, "button[type='submit'], #loginSubmit, button:has-text('Login')")
                await delay(5, 8)

            if any(k in page.url for k in ("dashboard", "home", "seeker", "profile", "account")):
                logger.success("Foundit login successful")
                return True

            logger.warning(f"Foundit login state uncertain — URL: {page.url}")
            return True # Proceed anyway
        except Exception as e:
            logger.error(f"Foundit login failed: {e}")
            return False
        finally:
            await page.close()

    async def scrape_jobs(self, context: BrowserContext) -> List[JobListing]:
        """Scrape job listings for all configured role keywords."""
        all_listings: List[JobListing] = []
        keywords = settings.job_roles_list

        for keyword in keywords:
            kw_enc = quote_plus(keyword)
            # Use the SRP results URL which is more reliable for bots
            url = f"{SEARCH_BASE}/srp/results?query={kw_enc}"
            listings = await self._scrape_keyword(context, keyword, url)
            all_listings.extend(listings)
            await delay(3, 6)

        logger.info(f"Foundit total scraped: {len(all_listings)} listings across {len(keywords)} keywords")
        return all_listings

    async def _scrape_keyword(self, context: BrowserContext, keyword: str, url: str) -> List[JobListing]:
        page = await context.new_page()
        listings: List[JobListing] = []
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            await simulate_reading(page)

            # Foundit job cards
            cards = await page.query_selector_all(
                "[class*='cardContainer'], div.srpResultCard, [class*='JobCard'], .job-card"
            )
            
            cards = cards[:MAX_CARDS_PER_KEYWORD]
            logger.info(f"Foundit {len(cards)} cards found for: {keyword}")

            for card in cards:
                listing = await self._parse_card(card)
                if listing:
                    listings.append(listing)
        except PlaywrightTimeout:
            logger.error(f"Foundit timeout loading search for: {keyword}")
        except Exception as e:
            logger.error(f"Foundit scrape error for '{keyword}': {e}")
        finally:
            await page.close()
        return listings

    async def _parse_card(self, card) -> Optional[JobListing]:
        try:
            # Foundit.in modern selectors
            title_el = await card.query_selector(".jobTitle, [class*='jobTitle'], h2, .title")
            if not title_el:
                return None

            title = (await title_el.text_content()).strip()
            
            # Fetch job id from container id attribute
            job_id = await card.get_attribute("id")
            if not job_id:
                # Fallback: hash the title
                import hashlib
                job_id = hashlib.md5(title.encode()).hexdigest()[:12]
                href = ""
            else:
                href = f"https://www.foundit.in/job/{job_id}"

            # Company
            company_el = await card.query_selector(".companyName, [class*='companyName'], .company")
            company = (await company_el.text_content()).strip() if company_el else "Unknown"

            # Location
            location_el = await card.query_selector(".location, [class*='location']")
            location = (await location_el.text_content()).strip() if location_el else "India"

            # Clean extra whitespaces/newlines
            company = " ".join(company.split())
            location = " ".join(location.split())

            prefixed_id = f"monster_{job_id}"

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
            logger.debug(f"Foundit card parse error: {e}")
            return None
