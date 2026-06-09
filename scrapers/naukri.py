"""NaukriScraper — login and job card scraping for Naukri.com."""

import asyncio
import re
from typing import List, Optional
from urllib.parse import quote_plus

from playwright.async_api import BrowserContext, TimeoutError as PlaywrightTimeout

from browser.human import delay, human_click, human_type, simulate_reading
from config.settings import settings
from scrapers.base import BaseScraper, JobListing
from utils.logger import logger

PLATFORM_NAME = "naukri"
LOGIN_URL = "https://www.naukri.com/nlogin/login"
SEARCH_BASE = "https://www.naukri.com"
MAX_CARDS_PER_KEYWORD = 15


class NaukriScraper(BaseScraper):
    """Scraper for Naukri.com job listings."""

    platform: str = PLATFORM_NAME

    async def login(self, context: BrowserContext) -> bool:
        """Log into Naukri.com with stored credentials.

        Confirmed live DOM selectors (inspected 2026-05-12):
          - email:    input#usernameField  (placeholder: 'Enter Email ID / Username')
          - password: input#passwordField  (placeholder: 'Enter Password')
          - button:   button[type='submit'] with text 'Login'
        Page stays at https://www.naukri.com/nlogin/login (no redirect in fresh session)
        """
        page = await context.new_page()
        try:
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # Check if already logged in (redirected away from login page)
            if "nlogin" not in page.url and "mnj/login" not in page.url:
                logger.info(f"Naukri already logged in. URL={page.url}")
                return True

            # Check for Akamai bot detection block
            title = await page.title()
            body_text = await page.inner_text("body")
            if "access denied" in title.lower() or "you don't have permission to access" in body_text.lower():
                logger.error(
                    "\n" + "!" * 80 + "\n"
                    "⚠️  NAUKRI ACCESS DENIED: Akamai Bot Detection blocked the request (HTTP 403).\n"
                    "Naukri uses strict browser fingerprinting that blocks automated headless browsers.\n\n"
                    "👉 TO RESOLVE:\n"
                    "   1. Update your .env file to set: HEADLESS=false\n"
                    "   2. If running inside a headless server (VPS or Android UserLAnd), install Xvfb:\n"
                    "      sudo apt update && sudo apt install -y xvfb\n"
                    "      And run the agent using: xvfb-run python main.py\n" +
                    "!" * 80 + "\n"
                )
                return False

            # Define potential selectors for credentials fields (resilient fallbacks)
            email_selectors = ["input#usernameField", "input[placeholder*='Email']", "input[placeholder*='Username']", "input[name='email']", "input[type='email']", "input[type='text']"]
            password_selectors = ["input#passwordField", "input[placeholder*='Password']", "input[name='password']", "input[type='password']"]
            submit_selectors = ['button[type="submit"]', "button:has-text('Login')", "button.btn-primary", ".login-button"]

            # Wait for any of the email input selectors to appear
            email_selector = None
            for sel in email_selectors:
                try:
                    await page.wait_for_selector(sel, timeout=3000, state="attached")
                    email_selector = sel
                    break
                except Exception:
                    continue

            if not email_selector:
                logger.warning(f"Naukri email/username field not found. Trying alternate login URL...")
                if "mnj" in page.url or "nlogin" not in page.url:
                    await page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded", timeout=20000)
                    await asyncio.sleep(3)
                    for sel in email_selectors:
                        try:
                            await page.wait_for_selector(sel, timeout=3000, state="attached")
                            email_selector = sel
                            break
                        except Exception:
                            continue

            if not email_selector:
                logger.error("Naukri login fields could not be resolved. Please verify if the login page layout changed.")
                await page.screenshot(path="artifacts/naukri_login_failed.png")
                return False

            # Dismiss cookie/consent if present
            try:
                await page.click("button#onetrust-accept-btn-handler", timeout=2000)
                await asyncio.sleep(1)
            except Exception:
                pass

            # Fill credentials using human-like typing
            email_el = await page.query_selector(email_selector)
            await email_el.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.3)
            await page.keyboard.type(settings.naukri_email or "", delay=80)
            logger.debug("Naukri email typed")
            await asyncio.sleep(0.5)

            # Resolve password field
            password_selector = None
            for sel in password_selectors:
                if await page.query_selector(sel):
                    password_selector = sel
                    break

            if not password_selector:
                logger.error("Naukri password field not found.")
                return False

            pwd_el = await page.query_selector(password_selector)
            await pwd_el.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.3)
            await page.keyboard.type(settings.naukri_password or "", delay=80)
            logger.debug("Naukri password typed")
            await asyncio.sleep(0.5)

            # Click the Login button
            submit_selector = None
            for sel in submit_selectors:
                if await page.query_selector(sel):
                    submit_selector = sel
                    break

            if not submit_selector:
                logger.error("Naukri login submit button not found.")
                return False

            await page.click(submit_selector)
            logger.debug("Naukri login button clicked")



            await delay(5, 8)
            current_url = page.url
            logger.info(f"Naukri post-login URL: {current_url}")

            # Still on login page = failed
            if "nlogin" in current_url or "mnj/login" in current_url:
                logger.warning("Naukri still on login page — check credentials")
                return False

            logger.success(f"Naukri login completed: {current_url[:80]}")
            return True

        except Exception as e:
            logger.error(f"Naukri login exception: {e}")
            return False
        finally:
            await page.close()

    async def scrape_profile(self, page) -> dict:
        """Scrape profile details from Naukri.com logged in profile page."""
        profile_data = {}
        try:
            logger.info("Naukri: Navigating to profile page...")
            await page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)

            # 1. Experience
            exp_el = await page.query_selector(".expVal, .experience, span[class*='exp'], span:has-text('Year')")
            if exp_el:
                exp_text = await exp_el.text_content()
                profile_data["experience_raw"] = exp_text.strip()
                # Parse years and months
                import re
                years_match = re.search(r'(\d+)\s*(?:Year|yr)s?', exp_text, re.IGNORECASE)
                months_match = re.search(r'(\d+)\s*(?:Month|mo)s?', exp_text, re.IGNORECASE)
                years = int(years_match.group(1)) if years_match else 0
                months = int(months_match.group(1)) if months_match else 0
                profile_data["experience_years"] = round(years + (months / 12.0), 1)
                logger.info(f"Naukri Profile: Found experience '{exp_text.strip()}' -> parsed as {profile_data['experience_years']} years")

            # 2. Key Skills
            skills_els = await page.query_selector_all(".keySkills .chip, .skill-chip, [class*='skill'] .chip, span.tag, .keySkills span")
            skills = []
            for sel in skills_els:
                text = (await sel.text_content()).strip()
                if text and text not in skills:
                    skills.append(text)
            if skills:
                profile_data["skills"] = skills
                logger.info(f"Naukri Profile: Found {len(skills)} skills: {skills[:5]}...")

            # 3. Designation/Current Role
            role_el = await page.query_selector(".infoCard .title, .infoCard h1, .designation, [class*='designation']")
            if role_el:
                role = (await role_el.text_content()).strip()
                profile_data["current_role"] = role
                logger.info(f"Naukri Profile: Found current role '{role}'")

            # 4. Name
            name_el = await page.query_selector(".infoCard .name, .userName, [class*='name']")
            if name_el:
                name = (await name_el.text_content()).strip()
                profile_data["name"] = name
                logger.info(f"Naukri Profile: Found name '{name}'")

        except Exception as e:
            logger.error(f"Naukri profile scraping failed: {e}")
        return profile_data

    async def scrape_jobs(self, context: BrowserContext) -> List[JobListing]:
        """Scrape job listings for all configured role keywords."""
        all_listings: List[JobListing] = []
        keywords = settings.job_roles_list[:4]
        exp = int(settings.experience_years)
        freshness = settings.job_freshness_days

        for keyword in keywords:
            kw_enc = quote_plus(keyword.lower().replace(" ", "-"))
            url = (
                f"{SEARCH_BASE}/{kw_enc}-jobs"
                f"?experience={exp}&jobAge={freshness}"
            )
            listings = await self._scrape_keyword(context, keyword, url)
            all_listings.extend(listings)
            await delay(3, 6)

        logger.info(f"Naukri total scraped: {len(all_listings)} listings across {len(keywords)} keywords")
        return all_listings

    async def _scrape_keyword(self, context: BrowserContext, keyword: str, url: str) -> List[JobListing]:
        page = await context.new_page()
        listings: List[JobListing] = []
        try:
            logger.info(f"Naukri navigating to search URL: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Wait for job cards to render (React SPA)
            try:
                await page.wait_for_selector(".srp-jobtuple-wrapper", timeout=10000)
            except Exception:
                logger.warning(f"Naukri .srp-jobtuple-wrapper not found initially, trying fallback...")
                try:
                    await page.wait_for_selector("[data-job-id]", timeout=5000)
                except Exception as e:
                    logger.warning(f"Naukri job cards failed to load within timeout. Title: {await page.title()}")
                    # Dump a small snippet of the body to understand what rendered
                    body = await page.inner_html("body")
                    logger.info(f"Naukri page body snippet: {body[:1000]}")

            # Confirmed working selector from live DOM inspection (2026-05-12)
            cards = await page.query_selector_all(
                ".srp-jobtuple-wrapper, [data-job-id], .cust-job-tuple"
            )
            # Deduplicate by element handle
            seen = set()
            unique_cards = []
            for card in cards:
                try:
                    job_id_attr = await card.get_attribute("data-job-id")
                    card_class = await card.get_attribute("class") or ""
                    key = job_id_attr or id(card)
                    if key not in seen:
                        seen.add(key)
                        unique_cards.append(card)
                except Exception:
                    unique_cards.append(card)
            
            cards = unique_cards[:MAX_CARDS_PER_KEYWORD]
            logger.info(f"Naukri {len(cards)} cards found for: {keyword}")

            for card in cards:
                listing = await self._parse_card(card)
                if listing:
                    listings.append(listing)
                else:
                    logger.debug("Naukri failed to parse a card.")
        except PlaywrightTimeout:
            logger.error(f"Naukri timeout loading search for: {keyword}")
        except Exception as e:
            logger.error(f"Naukri scrape error for '{keyword}': {e}")
        finally:
            await page.close()
        return listings

    async def _parse_card(self, card) -> Optional[JobListing]:
        try:
            # Get job ID from data attribute (most reliable)
            job_id_attr = await card.get_attribute("data-job-id") or ""

            # Title — confirmed selectors from live DOM
            title_el = await card.query_selector(
                "a.title, .cust-job-tuple a[title], a[href*='job-listings'], "
                ".srp-jobtuple-wrapper a, .sjw__tuple a, h2 a, a[class*='title']"
            )
            if not title_el:
                return None

            title = (await title_el.inner_text()).strip()
            if not title:
                return None

            href = await title_el.get_attribute("href") or ""
            if href and not href.startswith("http"):
                href = f"https://www.naukri.com{href}"

            # Use data-job-id if available, else extract from URL
            if job_id_attr:
                job_id = job_id_attr
            else:
                match = re.search(r"-(\d+)$", href)
                job_id = match.group(1) if match else href.split("/")[-1][:20]
            prefixed_id = f"naukri_{job_id}"

            company_el = await card.query_selector(
                "a.comp-name, .companyInfo a, a[class*='comp-name'], "
                ".sjw__tuple a[class*='company'], [class*='company-name']"
            )
            company = (await company_el.inner_text()).strip() if company_el else "Unknown"

            location_el = await card.query_selector(
                ".locWdth, li.loc, span.locWdth, .sjw__tuple [class*='loc'], "
                "[class*='location'], .location"
            )
            location = (await location_el.inner_text()).strip() if location_el else ""

            salary_el = await card.query_selector(
                ".salary, li.salary, [class*='salary'], .pac"
            )
            salary = (await salary_el.inner_text()).strip() if salary_el else "Not disclosed"

            exp_el = await card.query_selector(
                ".expwdth, li.exp, span.expwdth, [class*='exp']"
            )
            experience = (await exp_el.inner_text()).strip() if exp_el else ""

            easy_el = await card.query_selector(
                "[class*='easy-apply'], a[title*='Easy'], button[class*='apply']"
            )

            return JobListing(
                id=prefixed_id,
                platform=PLATFORM_NAME,
                title=title,
                company=company,
                location=location,
                url=href,
                salary=salary,
                experience_required=experience,
                is_easy_apply=bool(easy_el),
            )
        except Exception as e:
            logger.debug(f"Naukri card parse error: {e}")
            return None
