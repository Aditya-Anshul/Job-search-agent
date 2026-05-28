"""LinkedInScraper — login and job card scraping for LinkedIn."""

import asyncio
from typing import List
from urllib.parse import quote_plus

from playwright.async_api import BrowserContext, TimeoutError as PlaywrightTimeout

from browser.human import delay, human_type, simulate_reading
from config.settings import settings
from scrapers.base import BaseScraper, JobListing
from utils.logger import logger

PLATFORM_NAME = "linkedin"
LOGIN_URL = "https://www.linkedin.com/login"
SEARCH_BASE = "https://www.linkedin.com/jobs/search/"
MAX_CARDS_PER_KEYWORD = 25


class LinkedInScraper(BaseScraper):
    """Scraper for LinkedIn job listings."""

    platform: str = PLATFORM_NAME

    async def login(self, context: BrowserContext) -> bool:
        """Log into LinkedIn.com with stored credentials."""
        page = await context.new_page()
        try:
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            if "feed" in page.url:
                logger.info("LinkedIn already logged in.")
                return True

            # Handle common overlays/interceptors
            await asyncio.sleep(2)
            try:
                # 1. Check for "Sign in using another account" or "Cancel sign in"
                another_btn = await page.query_selector("button:has-text('Sign in using another account'), button:has-text('Cancel sign in'), .cancel-button")
                if another_btn and await another_btn.is_visible():
                    await another_btn.click()
                    await asyncio.sleep(2)
                
                # 2. Dismiss "LinkedIn is better on the app" if it appears
                dismiss_btn = await page.query_selector("button[aria-label='Dismiss'], .modal__dismiss")
                if dismiss_btn and await dismiss_btn.is_visible():
                    await dismiss_btn.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

            # Wait for fields (try direct IDs first as they are stable)
            try:
                await page.wait_for_selector("#username", timeout=30000)
            except Exception:
                if "feed" in page.url:
                    return True
                # If still not found, try to force navigate to the 'sign in another account' page
                await page.goto("https://www.linkedin.com/checkpoint/rm/sign-in-another-account", wait_until="domcontentloaded")
                try:
                    await page.wait_for_selector("#username", timeout=15000)
                except Exception:
                    logger.error(f"LinkedIn login fields not found even after redirect. URL={page.url}")
                    await page.screenshot(path="artifacts/linkedin_login_failed_final.png")
                    return False

            # Fill credentials with clearing
            email_sel = "#username"
            pwd_sel = "#password"
            
            await page.click(email_sel)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(settings.linkedin_email or "", delay=70)
            await asyncio.sleep(0.5)

            await page.click(pwd_sel)
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(settings.linkedin_password or "", delay=70)
            await asyncio.sleep(0.5)

            # Click Login
            submit_sel = 'button[type="submit"], button[aria-label="Sign in"]'
            await page.click(submit_sel)
            
            await delay(5, 10)
            
            if "checkpoint" in page.url:
                logger.warning("LinkedIn security checkpoint detected. Manual intervention might be needed.")
                await page.screenshot(path="artifacts/linkedin_checkpoint.png")
                await asyncio.sleep(20) 

            if "feed" in page.url or "jobs" in page.url:
                logger.success(f"LinkedIn login completed: {page.url[:80]}")
                return True
            else:
                logger.warning(f"LinkedIn login might have failed. URL={page.url}")
                await page.screenshot(path="artifacts/linkedin_login_failed_final.png")
                return False

        except Exception as e:
            logger.error(f"LinkedIn login exception: {e}")
            return False
        finally:
            await page.close()

    async def scrape_jobs(self, context: BrowserContext) -> List[JobListing]:
        """Scrape LinkedIn jobs for all keywords in settings."""
        all_listings = []
        page = await context.new_page()
        
        # Set a shorter freshness for testing or use settings
        freshness_seconds = settings.job_freshness_days * 24 * 3600

        try:
            for keyword in settings.job_roles_list:
                for location in settings.job_locations_list:
                    logger.info(f"LinkedIn scraping: '{keyword}' in '{location}'")
                    
                    # f_AL=true is for Easy Apply
                    # f_TPR=r{seconds} is for date posted
                    search_url = (
                        f"{SEARCH_BASE}?keywords={quote_plus(keyword)}"
                        f"&location={quote_plus(location)}"
                        f"&f_AL=true"
                        f"&f_TPR=r{freshness_seconds}"
                    )
                    
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=40000)
                    await delay(3, 5)
                    
                    # Scroll to load more cards
                    for _ in range(3):
                        await page.evaluate("window.scrollBy(0, 800)")
                        await asyncio.sleep(1)

                    # Extract job cards
                    # LinkedIn job cards usually have class 'job-card-container' or are in a list
                    cards = await page.query_selector_all(".jobs-search-results-list__list-item, .job-card-container")
                    logger.info(f"LinkedIn found {len(cards)} cards for {keyword}")

                    count = 0
                    for card in cards:
                        if count >= MAX_CARDS_PER_KEYWORD:
                            break
                        
                        try:
                            # Extract details from card
                            title_el = await card.query_selector(".job-card-list__title, .job-card-container__link, a[data-control-id]")
                            if not title_el:
                                continue
                            
                            title = (await title_el.inner_text()).strip()
                            url = await title_el.get_attribute("href")
                            if url and not url.startswith("http"):
                                url = "https://www.linkedin.com" + url
                            
                            # Clean up URL (remove tracking params)
                            if url and "?" in url:
                                url = url.split("?")[0]

                            company_el = await card.query_selector(".job-card-container__company-name, .job-card-container__primary-description")
                            company = (await company_el.inner_text()).strip() if company_el else "Unknown"
                            
                            # Blacklist filter
                            is_blacklisted = False
                            for b_company in settings.blacklist_companies_list:
                                if b_company.lower() in company.lower():
                                    is_blacklisted = True
                                    break
                            
                            if is_blacklisted:
                                logger.debug(f"LinkedIn skipping blacklisted company: {company}")
                                continue

                            location_el = await card.query_selector(".job-card-container__metadata-item")
                            location_str = (await location_el.inner_text()).strip() if location_el else location

                            # Create ID
                            job_id = ""
                            if url:
                                # Extract job ID from URL like /jobs/view/123456/
                                import re
                                match = re.search(r'/view/(\d+)', url)
                                if match:
                                    job_id = f"linkedin_{match.group(1)}"
                            
                            if not job_id:
                                # Fallback ID
                                import hashlib
                                job_id = f"linkedin_{hashlib.md_bytes((title+company).encode()).hex()[:10]}"

                            all_listings.append(JobListing(
                                id=job_id,
                                platform=PLATFORM_NAME,
                                title=title,
                                company=company,
                                location=location_str,
                                url=url,
                                is_easy_apply=True
                            ))
                            count += 1
                        except Exception as e:
                            logger.debug(f"Error parsing LinkedIn card: {e}")
                            continue

            return all_listings
        except Exception as e:
            logger.error(f"LinkedIn scrape error: {e}")
            return all_listings
        finally:
            await page.close()
