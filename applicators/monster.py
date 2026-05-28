"""MonsterApplicator — automated application submission on Monster India."""

import asyncio
from playwright.async_api import BrowserContext

from agent.cover_letter import truncate_for_form
from applicators.base import BaseApplicator, try_click_one, ExternalRedirectException
from browser.human import delay, human_type, simulate_reading
from scrapers.base import JobListing
from utils.logger import logger

PLATFORM_NAME = "monster"

APPLY_SELECTORS = [
    "button#applyBtn",
    ".ds-button.button-primary-filled",
    "button:has-text('Apply')",
    "a:has-text('Apply')",
    "[data-testid='apply-button']",
    "button:has-text('Apply Now')",
    "button:has-text('Quick Apply')",
]

NEXT_SELECTORS = [
    "button:has-text('Continue')",
    "button:has-text('Next')",
    "button:has-text('Apply')",
    ".btn-next",
]

SUBMIT_SELECTORS = [
    "button:has-text('Submit')",
    "button:has-text('Apply')",
    "button:has-text('Submit application')",
    ".btn-submit",
]

class MonsterApplicator(BaseApplicator):
    """Applies to job listings on Monster.com."""

    platform: str = PLATFORM_NAME

    async def apply(self, context: BrowserContext, job: JobListing, cover_letter: str, profile: dict = None) -> bool:
        logger.info(f"Monster: Starting application process for job: '{job.title}' @ '{job.company}'")
        logger.info(f"Monster: Target job URL: {job.url}")
        
        page = await context.new_page()
        try:
            logger.info("Monster: Opening a new page and navigating to job URL...")
            await page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
            logger.info(f"Monster: Page loaded. Current URL in address bar: {page.url}")
            
            # Anti-bot check & Blank page detection
            logger.info("Monster: Extracting page body text to inspect for Cloudflare/CAPTCHA blocking screens...")
            body_text = await page.inner_text("body")
            if not body_text.strip():
                logger.warning("Monster: Page body is empty! This might indicate a blank page or bot detection blockage.")
            elif "captcha" in body_text.lower() or "cloudflare" in body_text.lower() or "please verify" in body_text.lower():
                logger.error("Monster: WARNING! CAPTCHA, Cloudflare, or anti-bot challenge page detected!")
            else:
                logger.info("Monster: Page text successfully validated. Simulating realistic human reading delay...")
            
            await simulate_reading(page)

            # Check if it's already applied
            logger.info("Monster: Scanning page for 'Applied' indicators...")
            already_applied = await page.query_selector("button:has-text('Applied'), .applied-state")
            if already_applied:
                applied_txt = await already_applied.inner_text()
                logger.info(f"Monster: Already applied state detected. Button text found: '{applied_txt}'. Skipping.")
                return True
            
            # Log all button text on the page to see what's available
            try:
                buttons = await page.query_selector_all("button, a.btn, input[type='button'], input[type='submit']")
                logger.info(f"Monster: Located {len(buttons)} total interactive button/link elements on the page.")
                for i, btn in enumerate(buttons[:15]):
                    txt = (await btn.inner_text() or "").strip()
                    visible = await btn.is_visible()
                    logger.debug(f"  - Button {i}: Text='{txt}', Visible={visible}")
            except Exception as e:
                logger.warning(f"Monster: Failed to inspect page buttons: {e}")

            # Foundit special: sometimes we need to click the card to see the apply button in the JD section
            logger.info("Monster: Attempting to locate and click 'Apply' button...")
            clicked = await try_click_one(page, APPLY_SELECTORS, timeout=5000)
            if not clicked:
                logger.info("Monster: Apply button not found immediately. Trying to click job title on page to expand JD panel...")
                title_sel = f"text='{job.title}'"
                try:
                    title_btn = await page.query_selector(title_sel)
                    if title_btn:
                        logger.info(f"Monster: Found job title element with text '{job.title}'. Clicking it...")
                        await title_btn.click()
                        await asyncio.sleep(2)
                        logger.info("Monster: Re-attempting to find and click Apply button...")
                        clicked = await try_click_one(page, APPLY_SELECTORS, timeout=5000)
                        if clicked:
                            logger.info("Monster: Successfully clicked Apply button after job title click!")
                    else:
                        logger.warning(f"Monster: Job title text element '{title_sel}' was not found on the page.")
                except Exception as click_err:
                    logger.error(f"Monster: Error while expanding JD via job title click: {click_err}")

            if not clicked:
                logger.warning(f"Monster: Foundit apply button not found for: '{job.title}'.")
                screenshot_path = f"artifacts/monster_missing_apply_{job.id}.png"
                try:
                    await page.screenshot(path=screenshot_path)
                    logger.info(f"Monster: Saved debug screenshot to: {screenshot_path}")
                except Exception as sc_err:
                    logger.error(f"Monster: Failed to capture screenshot: {sc_err}")
                return False

            logger.info("Monster: Apply button clicked successfully. Pausing for page load...")
            await delay(3, 5)
            logger.info(f"Monster: Current URL after clicking apply: {page.url}")
            
            # Check if we were redirected to an external site
            current_url = page.url
            if "foundit.in" not in current_url and "monster" not in current_url:
                logger.warning(f"Monster: Foundit redirected to external site: {current_url}")
                raise ExternalRedirectException(f"Redirected to external site: {current_url}")

            # Internal monster application flow
            max_steps = 6
            max_retries_per_step = 3
            logger.info(f"Monster: Starting internal form handler (allowing up to {max_steps} multi-page steps)...")
            
            for step in range(max_steps):
                logger.info(f"Monster: Processing form Step {step+1} of {max_steps}...")
                for attempt in range(max_retries_per_step):
                    logger.info(f"  - Step {step+1}, Attempt {attempt+1}: Filling form input fields...")
                    # Fill visible fields and handle errors
                    await self._handle_monster_form(page, profile, cover_letter)
                    
                    # Try to move forward
                    submit_btn = await page.query_selector("button:has-text('Submit')")
                    if submit_btn:
                        logger.info("  - Found a visible 'Submit' button! Clicking submit...")
                        submitted = await try_click_one(page, SUBMIT_SELECTORS, timeout=3000)
                        if submitted:
                            logger.info("  - Clicked 'Submit' successfully. Waiting for submission processing...")
                            await delay(2, 3)
                            # Verify success
                            success_indicators = ["text='Application Sent'", "text='Success'", "text='Applied'"]
                            for ind in success_indicators:
                                if await page.query_selector(ind):
                                    logger.success(f"Monster application submitted and verified successfully for: {job.title}")
                                    return True
                            logger.warning("  - Submitted but success indicators were not immediately found on page. Continuing...")
                    
                    logger.info("  - Searching for Next/Continue/Proceed buttons to move to next step...")
                    next_btn = await try_click_one(page, NEXT_SELECTORS, timeout=3000)
                    if not next_btn:
                        logger.info("  - No 'Next' or 'Continue' buttons found. Form may be finished or requires manual interaction.")
                        break
                    
                    logger.info("  - Clicked 'Next'/'Continue' successfully.")
                    await delay(1, 2)
                    
                    # Error detection: Monster often uses .error-message or specific classes
                    logger.info("  - Evaluating page state to detect any active form validation error messages...")
                    error_msg = await page.evaluate('''() => {
                        const err = document.querySelector('.error, .invalid, [class*="error"], [class*="invalid"]');
                        return err ? err.innerText : "";
                    }''')
                    
                    if not error_msg:
                        logger.info("  - No form validation errors detected on page. Proceeding to next step.")
                        break # Step successful, move to next step
                    
                    logger.warning(f"  - Monster step {step+1} form error detected (attempt {attempt+1}): {error_msg}")
                    await delay(1, 2)

            # Verification
            logger.info("Monster: Executing final check for application success indicators...")
            success_selectors = [
                "text='Application Sent'", "text='Success'", "text='Applied'",
                "text='Thank you for applying'", "text='Application received'",
                ".applied-state", "[class*='Success']"
            ]
            for sel in success_selectors:
                if await page.query_selector(sel):
                    logger.success(f"Monster applied successfully: {job.title} @ {job.company}")
                    return True
            
            logger.warning("Monster: None of the success indicators were detected. Application might have failed or is in an unknown state.")
            screenshot_path = f"artifacts/monster_unknown_end_state_{job.id}.png"
            try:
                await page.screenshot(path=screenshot_path)
                logger.info(f"Monster: Saved end-of-run state screenshot to: {screenshot_path}")
            except Exception:
                pass
            return False
        except Exception as e:
            logger.error(f"Monster: Apply exception encountered for '{job.title}': {e}")
            screenshot_path = f"artifacts/monster_exception_{job.id}.png"
            try:
                await page.screenshot(path=screenshot_path)
                logger.info(f"Monster: Saved exception state screenshot to: {screenshot_path}")
            except Exception:
                pass
            return False
        finally:
            logger.info("Monster: Closing page to wrap up applicator run.")
            await page.close()

    async def _handle_monster_form(self, page, profile: dict, cover_letter: str):
        """Fill visible form fields on Monster's internal application with error awareness."""
        logger.info("Monster Form: Scanning page for file upload/resume inputs...")
        try:
            file_inputs = await page.query_selector_all("input[type='file']")
            logger.info(f"Monster Form: Located {len(file_inputs)} total file inputs.")
            for fi in file_inputs:
                if await fi.is_visible():
                    resume_path = profile.get("temp_resume_path") or settings.resume_pdf_path
                    import os
                    if resume_path and os.path.exists(resume_path):
                        abs_path = os.path.abspath(resume_path)
                        logger.info(f"Monster Form: Uploading resume file from: {abs_path}")
                        await fi.set_input_files(abs_path)
                        import asyncio
                        await asyncio.sleep(2)
                    else:
                        logger.warning(f"Monster Form: Resume path '{resume_path}' does not exist on disk!")
        except Exception as e:
            logger.error(f"Monster Form: File upload handling error: {e}")

        logger.info("Monster Form: Scanning page for text, numeric, and textarea input elements...")
        inputs = await page.query_selector_all("input[type='text'], input[type='number'], textarea")
        logger.info(f"Monster Form: Located {len(inputs)} input fields.")
        
        # Check for error text on the page to provide context to LLM
        page_error = await page.evaluate('''() => {
            const err = document.querySelector('.error, .invalid, [class*="error"]');
            return err ? err.innerText : "";
        }''')
        if page_error:
            logger.warning(f"Monster Form: Active page validation error present: '{page_error}'")

        for el in inputs:
            try:
                if await el.is_visible():
                    val = await el.input_value()
                    label = await el.evaluate("el => el.getAttribute('aria-label') || el.placeholder || el.name || ''")
                    logger.info(f"  - Found input field: label/placeholder='{label}', current_val='{val}'")
                    # Only fill if empty or there's an error on the page
                    if not val or page_error:
                        if "resume" in label.lower() or "cv" in label.lower() or "file" in label.lower():
                            logger.info(f"  - Skipping file-type text field: '{label}'")
                            continue 
                        
                        if "message" in label.lower() or "cover" in label.lower():
                            logger.info(f"  - Filling cover letter into field '{label}'...")
                            try:
                                await el.fill(truncate_for_form(cover_letter))
                            except Exception as fill_err:
                                if "not editable" in str(fill_err).lower() or "readonly" in str(fill_err).lower():
                                    logger.info("    - Field is not editable. Attempting to set value via JavaScript...")
                                    import json
                                    escaped_letter = json.dumps(truncate_for_form(cover_letter))
                                    await el.evaluate(f"el => {{ el.value = {escaped_letter}; el.dispatchEvent(new Event('input', {{ bubbles: true }})); el.dispatchEvent(new Event('change', {{ bubbles: true }})); }}")
                                    logger.info("    - Value set via JS successfully!")
                                else:
                                    raise fill_err
                        else:
                            from llm import get_llm
                            llm = get_llm()
                            prompt = f"Candidate Profile: {profile}\nQuestion: {label}\n"
                            if page_error:
                                prompt += f"IMPORTANT: Previous input might have failed. Page error: {page_error}\n"
                            prompt += "Short Answer (Return ONLY answer):"
                            logger.info(f"  - Querying LLM to answer custom form question '{label}'...")
                            resp = await llm.complete(prompt)
                            ans = resp.content.strip()
                            logger.info(f"  - LLM suggested answer: '{ans}'. Filling...")
                            try:
                                await el.fill(ans)
                            except Exception as fill_err:
                                if "not editable" in str(fill_err).lower() or "readonly" in str(fill_err).lower():
                                    logger.info("    - Field is not editable. Attempting to set value via JavaScript...")
                                    import json
                                    escaped_ans = json.dumps(ans)
                                    await el.evaluate(f"el => {{ el.value = {escaped_ans}; el.dispatchEvent(new Event('input', {{ bubbles: true }})); el.dispatchEvent(new Event('change', {{ bubbles: true }})); }}")
                                    logger.info("    - Value set via JS successfully!")
                                else:
                                    raise fill_err
            except Exception as fill_err:
                logger.error(f"  - Failed to handle field: {fill_err}")
                continue
