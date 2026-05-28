"""LinkedInApplicator — automates the 'Easy Apply' flow on LinkedIn."""

import asyncio
from typing import List

from playwright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeout

from applicators.base import BaseApplicator, try_click_one, ExternalRedirectException
from browser.human import delay, human_click, human_type, simulate_reading
from scrapers.base import JobListing
from utils.logger import logger

PLATFORM_NAME = "linkedin"

APPLY_SELECTORS = [
    "button.jobs-apply-button",
    "button.jobs-apply-button--top-card",
    "button.apply-button",
    "a.jobs-apply-button",
    "a[aria-label*='Apply to this job']",
    "button[aria-label*='Apply to this job']",
    "#topbar-apply",
    "button:has-text('Easy Apply')",
    "button:has-text('Apply')",
    "a:has-text('Apply')",
]

NEXT_SELECTORS = [
    "button[aria-label='Continue to next step']",
    "button:has-text('Next')",
    "button:has-text('Review')",
]

SUBMIT_SELECTORS = [
    "button[aria-label='Submit application']",
    "button:has-text('Submit application')",
]

DISMISS_SELECTORS = [
    "button[aria-label='Dismiss']",
    "button:has-text('Discard')",
]


class LinkedInApplicator(BaseApplicator):
    """Applies to job listings on LinkedIn using Easy Apply."""

    platform: str = PLATFORM_NAME

    async def apply(self, context: BrowserContext, job: JobListing, cover_letter: str, profile: dict = None) -> bool:
        page = await context.new_page()
        try:
            logger.info(f"LinkedIn applying to: {job.url}")
            await page.goto(job.url, wait_until="domcontentloaded", timeout=40000)
            await delay(2, 4)
            await simulate_reading(page)

            # Check if already applied
            applied_status = await page.query_selector(".artdeco-inline-feedback--success, button:has-text('Applied')")
            if applied_status:
                logger.info(f"LinkedIn already applied to: {job.title}")
                return True

            # Click Easy Apply
            clicked = await try_click_one(page, APPLY_SELECTORS, timeout=10000)
            if not clicked:
                # Emergency fallback: try direct click on any button with apply in class
                try:
                    await page.click("button[class*='apply-button']", timeout=5000)
                    clicked = True
                except Exception:
                    logger.warning(f"LinkedIn Easy Apply button not found for: {job.title}")
                    await page.screenshot(path="artifacts/linkedin_apply_button_missing.png")
                    return False

            await delay(2, 4)
            
            # Check if clicked redirected us to an external site
            if "linkedin.com" not in page.url:
                logger.warning(f"LinkedIn redirected to external site: {page.url}")
                raise ExternalRedirectException(f"Redirected to external site: {page.url}")

            # Multi-step application modal with retry logic
            max_steps = 15
            max_retries = 5
            for step in range(max_steps):
                logger.debug(f"LinkedIn application step {step+1}")
                
                # Outer retry loop for the current step (handling validation errors)
                for attempt in range(max_retries):
                    # 1. Answer/Fix questions on the current step
                    await self._handle_questions(page, profile)
                    
                    # 2. Try to click Next/Review/Submit
                    # Note: We check Submit first as it might be on the same step as questions
                    submitted = await try_click_one(page, SUBMIT_SELECTORS, timeout=2000)
                    if submitted:
                        await delay(4, 6)
                        success = await page.query_selector("li-icon[type='success-pebble'], :has-text('Application submitted')")
                        if success:
                            logger.success(f"LinkedIn applied {job.title} @ {job.company}")
                            return True
                        else:
                            # Check if submission failed due to errors (e.g. captcha or hidden field)
                            errors = await page.query_selector_all(".artdeco-inline-feedback--error")
                            if errors:
                                logger.warning(f"LinkedIn submit failed on attempt {attempt+1}. Resolving errors...")
                                continue # Retry this step
                            return True # Assume success if no clear error

                    next_clicked = await try_click_one(page, NEXT_SELECTORS, timeout=3000)
                    if next_clicked:
                        await delay(1, 2)
                        
                        # Handle "Follow Company" checkbox if it appears on the review step
                        try:
                            follow_chk = await page.query_selector("input#follow-company-checkbox")
                            if follow_chk and await follow_chk.is_visible():
                                is_checked = await follow_chk.is_checked()
                                if is_checked != settings.follow_companies:
                                    # Click label to toggle
                                    await page.click("label[for='follow-company-checkbox']")
                                    logger.debug(f"LinkedIn {'un' if not settings.follow_companies else ''}followed company.")
                        except Exception:
                            pass

                        # Check if we actually moved forward or stayed on the same step due to errors
                        errors = await page.query_selector_all(".artdeco-inline-feedback--error")
                        if errors:
                            logger.warning(f"LinkedIn step validation failed on attempt {attempt+1}. Resolving errors...")
                            # Stay in retry loop for this step
                        else:
                            break # Success, move to next 'step' in outer loop
                    else:
                        # If no next and no submit, check for errors one last time
                        errors = await page.query_selector_all(".artdeco-inline-feedback--error")
                        if not errors:
                            break # End of flow?
                        logger.warning(f"LinkedIn stuck on step {step+1} with errors. Attempt {attempt+1}")

                else:
                    logger.error(f"LinkedIn failed to resolve step {step+1} after {max_retries} retries.")
                    await page.screenshot(path=f"artifacts/linkedin_retry_failed_{job.id}.png")
                    break

            # Final check for success
            success = await page.query_selector("li-icon[type='success-pebble'], :has-text('Application submitted')")
            if success:
                logger.success(f"LinkedIn applied {job.title} @ {job.company}")
                return True

            logger.warning(f"LinkedIn application flow ended without clear success for: {job.title}")
            return False

        except Exception as e:
            logger.error(f"LinkedIn apply error for '{job.title}': {e}")
            return False
        finally:
            await page.close()

    async def _handle_questions(self, page: Page, profile: dict):
        """Answers form fields in the LinkedIn Easy Apply modal."""
        if not profile:
            return

        # 1. Text inputs & Textareas
        inputs = await page.query_selector_all("input[type='text'], input[type='number'], textarea, input:not([type])")
        for el in inputs:
            try:
                if await el.is_visible():
                    val = await el.input_value()
                    
                    # Check for error associated with this field
                    # Error is usually in a sibling or parent artdeco-inline-feedback--error
                    parent_group = await el.evaluate_handle("el => el.closest('.jobs-easy-apply-form-section__grouping, .jobs-easy-apply-form-element')")
                    error_el = await parent_group.query_selector(".artdeco-inline-feedback--error") if parent_group else None
                    error_text = await error_el.inner_text() if error_el else ""
                    
                    if not val or val.strip() == "" or error_text:
                        if error_text:
                            logger.info(f"LinkedIn field error detected: {error_text.strip()}")
                        
                        label_text = ""
                        # Try aria-label
                        label_text = await el.get_attribute("aria-label") or ""
                        if not label_text:
                            # Try finding a label element
                            id_attr = await el.get_attribute("id")
                            if id_attr:
                                label_el = await page.query_selector(f"label[for='{id_attr}']")
                                if label_el:
                                    label_text = await label_el.inner_text()
                        
                        if not label_text:
                            # Try finding preceding span or p
                            label_text = await el.evaluate("el => { \
                                let prev = el.previousElementSibling; \
                                if (prev && prev.innerText) return prev.innerText; \
                                let parent = el.parentElement; \
                                if (parent && parent.innerText) return parent.innerText.split('\\n')[0]; \
                                return ''; \
                            }")
                        
                        if label_text:
                            logger.info(f"Answering/Fixing text question: {label_text.strip()[:40]}...")
                            answer = await self._get_ai_answer(label_text, profile, error_text, val)
                            
                            # If it's a numeric field or error says 'decimal', try to clean the answer
                            is_numeric = await el.get_attribute("type") == "number" or "number" in error_text.lower() or "decimal" in error_text.lower()
                            if is_numeric:
                                # Strip everything except digits and dot
                                import re
                                cleaned = re.sub(r'[^\d.]', '', answer)
                                if cleaned: answer = cleaned

                            await el.fill(answer)
                            await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug(f"Error handling input field: {e}")
                continue

        # 2. Radio buttons (Yes/No, choices)
        fieldsets = await page.query_selector_all("fieldset")
        logger.info(f"Found {len(fieldsets)} fieldsets for radio/choices.")
        for fs in fieldsets:
            try:
                if await fs.is_visible():
                    legend = await fs.query_selector("legend")
                    question_text = await legend.inner_text() if legend else "Question"
                    
                    # Check if any radio is already checked
                    checked = await fs.query_selector("input[type='radio']:checked")
                    if not checked:
                        # Get labels for all options
                        labels = await fs.query_selector_all("label")
                        options = []
                        for lbl in labels:
                            options.append(await lbl.inner_text())
                        
                        if options:
                            logger.info(f"Answering radio question: {question_text.strip()[:40]}...")
                            answer = await self._get_ai_answer(f"{question_text}. Options: {', '.join(options)}", profile)
                        
                        # Find best matching option
                        best_option = None
                        for lbl in labels:
                            lbl_text = await lbl.inner_text()
                            if answer.lower() in lbl_text.lower() or lbl_text.lower() in answer.lower():
                                best_option = lbl
                                break
                        
                        if best_option:
                            await best_option.click()
                            await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug(f"Error handling radio fieldset: {e}")
                continue

        # 3. Select dropdowns
        selects = await page.query_selector_all("select")
        logger.info(f"Found {len(selects)} dropdowns.")
        for sel in selects:
            try:
                if await sel.is_visible():
                    # Check if already selected (not the default/first index if it's 'Select')
                    idx = await sel.evaluate("el => el.selectedIndex")
                    if idx <= 0:
                        # Try direct label
                        label_el = await page.query_selector(f"label[for='{await sel.get_attribute('id')}']")
                        label_text = await label_el.inner_text() if label_el else ""
                        
                        if not label_text:
                            # Try preceding text
                            label_text = await sel.evaluate("el => { \
                                let prev = el.previousElementSibling; \
                                if (prev && prev.innerText) return prev.innerText; \
                                let parent = el.parentElement; \
                                if (parent && parent.innerText) return parent.innerText.split('\\n')[0]; \
                                return 'Question'; \
                            }")

                        # Get options
                        options = await sel.query_selector_all("option")
                        opt_texts = []
                        for opt in options:
                            t = await opt.inner_text()
                            if t.strip() and "select" not in t.lower():
                                opt_texts.append(t.strip())
                        
                        if opt_texts:
                            logger.info(f"Answering dropdown: {label_text.strip()[:40]}...")
                            answer = await self._get_ai_answer(f"{label_text}. Options: {', '.join(opt_texts)}", profile)
                            
                            # Select best match
                            for t in opt_texts:
                                if answer.lower() in t.lower() or t.lower() in answer.lower():
                                    await sel.select_option(label=t)
                                    break
                            await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug(f"Error handling select dropdown: {e}")
                continue

        # 4. Checkboxes (Privacy, Agreements)
        checkboxes = await page.query_selector_all("input[type='checkbox']")
        for cb in checkboxes:
            try:
                if await cb.is_visible() and not await cb.is_checked():
                    # Look for error or just check it if it's mandatory
                    # Usually mandatory ones are on the last page
                    logger.info(f"Checking mandatory checkbox...")
                    # Click the checkbox (sometimes clicking the label is better)
                    await cb.click()
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug(f"Error handling checkbox: {e}")
                continue

        # 5. File upload inputs (Resume / CV)
        file_inputs = await page.query_selector_all("input[type='file']")
        for fi in file_inputs:
            try:
                if await fi.is_visible():
                    resume_path = profile.get("temp_resume_path") or settings.resume_pdf_path
                    import os
                    if resume_path and os.path.exists(resume_path):
                        abs_path = os.path.abspath(resume_path)
                        logger.info(f"LinkedIn: Uploading resume file from: {abs_path}")
                        await fi.set_input_files(abs_path)
                        await asyncio.sleep(2)
            except Exception as e:
                logger.debug(f"LinkedIn file upload handling error: {e}")

    async def _get_ai_answer(self, question: str, profile: dict, error_text: str = "", previous_val: str = "") -> str:
        """Helper to get answer from LLM."""
        from llm import get_llm
        llm = get_llm()
        
        prompt = f"Candidate Profile: {profile}\n\n"
        prompt += f"Question from LinkedIn job application: {question}\n\n"
        
        if error_text:
            prompt += f"CRITICAL: LinkedIn showed this ERROR for my previous answer '{previous_val}': '{error_text.strip()}'.\n"
            prompt += "Please provide a corrected answer. "
            if "decimal" in error_text.lower() or "number" in error_text.lower() or "numeric" in error_text.lower():
                prompt += "IMPORTANT: Provide ONLY a numeric value (e.g., '10' or '10.5'). DO NOT include any text, currency, or units like 'LPA', 'days', or 'years'.\n"
        
        prompt += (
            "Provide a short, accurate answer based on the profile. "
            "If it's a Yes/No question, answer only 'Yes' or 'No'. "
            "If it asks for years of experience, provide a number. "
            "If it asks for a salary, provide a number (e.g. 15 for 15 LPA). "
            "Return ONLY the answer text, no explanation."
        )
        
        resp = await llm.complete(prompt)
        return resp.content.strip().replace('"', '')
