"""NaukriApplicator — automated application submission on Naukri.com."""

from playwright.async_api import BrowserContext

from agent.cover_letter import truncate_for_form
from applicators.base import BaseApplicator, try_click_one, ExternalRedirectException
from browser.human import delay, human_type, simulate_reading
from scrapers.base import JobListing
from utils.logger import logger

PLATFORM_NAME = "naukri"

APPLY_SELECTORS = [
    "button#apply-button",
    "button.apply-button",
    "a[title='Apply']",
    "button:has-text('Apply')",
    ".apply-btn",
    "a.apply-btn",
    "button[class*='apply']",
]

COVER_LETTER_SELECTORS = [
    "textarea[name='coverLetter']",
    "textarea#coverLetter",
    "textarea.cover-letter",
    "textarea[placeholder*='cover']",
    "textarea",
]

SUBMIT_SELECTORS = [
    "button:has-text('Submit')",
    "button:has-text('Confirm')",
    "button:has-text('Send Application')",
    "button:has-text('Save')",
    "button[type='submit']",
    ".submit-btn",
]

class NaukriApplicator(BaseApplicator):
    """Applies to job listings on Naukri.com."""

    platform: str = PLATFORM_NAME

    async def apply(self, context: BrowserContext, job: JobListing, cover_letter: str, profile: dict = None) -> bool:
        page = await context.new_page()
        try:
            await page.goto(job.url, wait_until="domcontentloaded", timeout=30000)
            await simulate_reading(page)

            # Check if it's an external job before clicking
            for sel in APPLY_SELECTORS:
                btn = await page.query_selector(sel)
                if btn:
                    text = await btn.inner_text()
                    if "company site" in text.lower():
                        logger.warning(f"Naukri skipping external job: {job.title}")
                        raise ExternalRedirectException("Skipped: Redirects to external company website")
                    break

            clicked = await try_click_one(page, APPLY_SELECTORS, timeout=5000)
            if not clicked:
                logger.warning(f"Naukri apply button not found for: {job.title}")
                return False

            await delay(2, 3)
            
            # Check if clicked redirected us to an external site
            if "naukri.com" not in page.url:
                logger.warning(f"Naukri redirected to external site: {page.url}")
                raise ExternalRedirectException(f"Redirected to external site: {page.url}")
            
            # Check if it was a 1-click apply (button text changes to 'Applied')
            # Or if a modal appeared
            has_modal = await page.query_selector(".apply-message, .bot-sheet, .modal, .chatbot, .drawer, [class*='chat']")
            
            if has_modal:
                await self._handle_questionnaire(page, profile)
            
            await self._fill_cover_letter(page, cover_letter)
            await delay(1, 2)
            
            # Upload tailored resume if any file upload input is present
            try:
                file_inputs = await page.query_selector_all("input[type='file']")
                for fi in file_inputs:
                    if await fi.is_visible():
                        resume_path = profile.get("temp_resume_path") or settings.resume_pdf_path
                        import os
                        if resume_path and os.path.exists(resume_path):
                            abs_path = os.path.abspath(resume_path)
                            logger.info(f"Naukri: Uploading resume file from: {abs_path}")
                            await fi.set_input_files(abs_path)
                            await delay(1, 2)
            except Exception as e:
                logger.debug(f"Naukri file upload handling error: {e}")

            submitted = await try_click_one(page, SUBMIT_SELECTORS, timeout=5000)
            await delay(2, 3)

            # Verification step: check if success message is present or button text is 'Applied'
            success_indicators = [
                ".apply-message-success",
                ".success-msg",
                "text='successfully applied'",
                "text='Applied successfully'",
                "button:has-text('Applied')"
            ]
            is_success = False
            for ind in success_indicators:
                if await page.query_selector(ind):
                    is_success = True
                    break
            
            # Check if modal is still open after everything
            still_has_modal = False
            try:
                modals = await page.query_selector_all(".apply-message, .bot-sheet, .modal, .chatbot, .drawer, [class*='chat']")
                for m in modals:
                    if await m.is_visible():
                        still_has_modal = True
                        break
            except Exception:
                pass
            
            if still_has_modal and not is_success:
                 logger.warning(f"Naukri application verification failed (modal still open) for: {job.title}")
                 await page.screenshot(path=f"artifacts/naukri_failed_{job.id}.png")
                 return False

            if not is_success and not submitted and not has_modal:
                 # If no confirmation, no submit button clicked, and no modal, it might have failed
                 logger.warning(f"Naukri application verification failed for: {job.title}")
                 await page.screenshot(path=f"artifacts/naukri_failed_{job.id}.png")
                 return False

            logger.success(f"Naukri applied {job.title} @ {job.company}")
            return True
        except Exception as e:
            logger.error(f"Naukri apply error for '{job.title}': {e}")
            return False
        finally:
            await page.close()

    async def _handle_questionnaire(self, page, profile: dict) -> bool:
        """Dynamically answers chatbot/modal questions using the LLM with error resolution."""
        from llm import get_llm
        import asyncio
        llm = get_llm()
        if not profile:
            return False
            
        logger.info("Naukri bot-sheet/questionnaire detected — attempting automated answers")
        
        max_questions = 10
        max_retries_per_question = 3
        
        for _ in range(max_questions):
            await asyncio.sleep(1.5)
            
            input_sels = ["input[type='text']", "input[type='number']", "textarea", "[contenteditable='true']", ".textArea"]
            visible_input = None
            
            # Find visible inputs
            for sel in input_sels:
                els = await page.query_selector_all(sel)
                for el in els:
                    if await el.is_visible():
                        visible_input = el
                        break
                if visible_input:
                    break
                    
            if not visible_input:
                break # No more text inputs found
            
            # Error detection on Naukri questionnaire
            # Naukri errors usually show up as .err-msg or inside the chatbot bubbles
            error_msg = await page.evaluate('''() => {
                const err = document.querySelector('.error, .err-msg, .validation-error');
                return err ? err.innerText : '';
            }''')

            modal_text = await page.evaluate('''() => {
                const modal = document.querySelector('.apply-message, .bot-sheet, .modal, .chatbot, .drawer');
                return modal ? modal.innerText : '';
            }''')
            
            if not modal_text:
                break
                
            previous_val = await visible_input.input_value()

            for attempt in range(max_retries_per_question):
                prompt = (
                    f"Candidate Profile: {profile}\n\n"
                    f"A Naukri application form asks a mandatory question. Recent text from modal:\n"
                    f"{modal_text[-800:]}\n\n"
                )
                
                if error_msg:
                    prompt += f"CRITICAL: Previous answer was '{previous_val}', but Naukri showed this ERROR: '{error_msg}'.\n"
                    prompt += "Provide a corrected answer that resolves the error (e.g. number only if requested).\n"

                prompt += (
                    f"What is the exact short answer (e.g. '3', 'Yes', 'India') to type into the input field? "
                    f"Return ONLY the exact text to type, nothing else."
                )
                
                resp = await llm.complete(prompt)
                answer = resp.content.strip()
                
                if error_msg and ("number" in error_msg.lower() or "decimal" in error_msg.lower()):
                     import re
                     cleaned = re.sub(r'[^\d.]', '', answer)
                     if cleaned: answer = cleaned

                logger.debug(f"Naukri answering questionnaire with: {answer}")
                await visible_input.fill("")
                await visible_input.click()
                await page.keyboard.type(answer)
                await asyncio.sleep(0.5)
                
                # Try to click the Save button
                save_btn = await page.query_selector("button:has-text('Save'), button:has-text('Submit'), .save-button")
                if save_btn and await save_btn.is_visible():
                    await save_btn.click()
                else:
                    await page.keyboard.press("Enter")
                
                await asyncio.sleep(1.5)
                
                # Check if error persists
                error_msg = await page.evaluate('''() => {
                    const err = document.querySelector('.error, .err-msg, .validation-error');
                    return err ? err.innerText : '';
                }''')
                if not error_msg:
                    break
                logger.warning(f"Naukri question retry {attempt+1} due to: {error_msg}")

        return True

    async def _fill_cover_letter(self, page, cover_letter: str) -> bool:
        letter_text = truncate_for_form(cover_letter)
        for selector in COVER_LETTER_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el:
                    await human_type(page, selector, letter_text)
                    return True
            except Exception:
                continue
        return False
