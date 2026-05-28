"""JoinDevOpsApplicator — application submission on JoinDevOps.com."""

from playwright.async_api import BrowserContext

from agent.cover_letter import truncate_for_form
from applicators.base import BaseApplicator, try_click_one, ExternalRedirectException
from browser.human import delay, human_type, simulate_reading
from config.settings import settings
from scrapers.base import JobListing
from utils.logger import logger

PLATFORM_NAME = "joindevops"

APPLY_SELECTORS = [
    "button:has-text('Apply')",
    "a:has-text('Apply')",
    ".apply-btn",
    "button[class*='apply']",
    "a[href*='apply']",
]

EMAIL_SELECTORS = [
    "input[type='email']",
    "input[name='email']",
    "input[placeholder*='email' i]",
]

COVER_SELECTORS = [
    "textarea",
    "textarea[name='message']",
    "textarea[name='coverLetter']",
    "textarea[placeholder*='cover' i]",
    "textarea[placeholder*='message' i]",
]

SUBMIT_SELECTORS = [
    "button[type='submit']",
    "button:has-text('Submit')",
    "button:has-text('Send')",
    "input[type='submit']",
]


class JoinDevOpsApplicator(BaseApplicator):
    """Applies to job listings on JoinDevOps.com."""

    platform: str = PLATFORM_NAME

    async def apply(self, context: BrowserContext, job: JobListing, cover_letter: str, profile: dict = None) -> bool:
        if not job.url:
            logger.warning(f"JoinDevOps no URL for job: {job.title}")
            return False

        page = await context.new_page()
        try:
            await page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
            await simulate_reading(page)

            # Check if it's already an external link
            if "joindevops.com" not in page.url:
                logger.warning(f"JoinDevOps job URL is already external: {page.url}")
                raise ExternalRedirectException(f"Job URL is already external: {page.url}")

            clicked = await try_click_one(page, APPLY_SELECTORS, timeout=5000)
            if not clicked:
                logger.warning(f"JoinDevOps apply button not found: {job.title}")
                return False

            await delay(3, 5)
            
            # Re-check URL after click
            if "joindevops.com" not in page.url:
                logger.info(f"JoinDevOps redirected to external site: {page.url[:60]}... Skipping.")
                raise ExternalRedirectException(f"Redirected to external site: {page.url}")

            # Internal form handling with retries
            max_retries = 3
            for attempt in range(max_retries):
                inputs = await page.query_selector_all("input[type='text'], input[type='email'], textarea")
                if not inputs:
                    break

                for el in inputs:
                    try:
                        if await el.is_visible():
                            label = await el.evaluate("el => el.getAttribute('name') || el.placeholder || ''")
                            tag_name = await el.evaluate("el => el.tagName.toLowerCase()")
                            if "email" in label.lower():
                                await el.fill(settings.joindevops_email or settings.naukri_email or "candidate@example.com")
                            elif "message" in label.lower() or "cover" in label.lower() or tag_name == "textarea":
                                 await el.fill(truncate_for_form(cover_letter))
                            else:
                                from llm import get_llm
                                llm = get_llm()
                                prompt = f"Candidate Profile: {profile}\nQuestion: {label}\nShort Answer (Return ONLY answer):"
                                resp = await llm.complete(prompt)
                                await el.fill(resp.content.strip())
                    except Exception:
                        continue

                # Upload tailored resume if any file upload input is present
                try:
                    file_inputs = await page.query_selector_all("input[type='file']")
                    for fi in file_inputs:
                        if await fi.is_visible():
                            resume_path = profile.get("temp_resume_path") or settings.resume_pdf_path
                            import os
                            if resume_path and os.path.exists(resume_path):
                                abs_path = os.path.abspath(resume_path)
                                logger.info(f"JoinDevOps: Uploading resume file from: {abs_path}")
                                await fi.set_input_files(abs_path)
                                await delay(1, 2)
                except Exception as e:
                    logger.debug(f"JoinDevOps file upload handling error: {e}")

                await delay(1, 2)
                submitted = await try_click_one(page, SUBMIT_SELECTORS, timeout=5000)
                await delay(2, 3)
                
                # Check for errors on the page
                error = await page.evaluate('() => document.querySelector(".error, .invalid, .alert-danger")?.innerText')
                if not error:
                    if submitted:
                        logger.success(f"JoinDevOps internal application submitted: {job.title}")
                        return True
                    break
                
                logger.warning(f"JoinDevOps application error (attempt {attempt+1}): {error}")
                await delay(1, 2)

            return False
        except Exception as e:
            logger.error(f"JoinDevOps apply error for '{job.title}': {e}")
            return False
        finally:
            await page.close()
