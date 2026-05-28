"""Master agent orchestrator — run_agent() coordinates all layers per run."""

import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Type

from agent.cover_letter import generate_cover_letter
from agent.matcher import match_job
from applicators.base import BaseApplicator, ExternalRedirectException
from applicators.joindevops import JoinDevOpsApplicator
from applicators.linkedin import LinkedInApplicator
from applicators.monster import MonsterApplicator
from applicators.naukri import NaukriApplicator
from browser.setup import create_browser, create_context
from config.settings import settings
from database.models import Job, RunHistory
from database.repository import repo
from llm import get_llm
from notifications.telegram_bot import notify
from resume.parser import get_resume_text
from scrapers.base import BaseScraper, JobListing
from scrapers.joindevops import JoinDevOpsScraper
from scrapers.linkedin import LinkedInScraper
from scrapers.monster import MonsterScraper
from scrapers.naukri import NaukriScraper
from utils.logger import clean_json, logger

# ── Platform registry ─────────────────────────────────────────────
# Add new platforms here without modifying any other file
SCRAPERS: Dict[str, Tuple[Type[BaseScraper], Type[BaseApplicator]]] = {
    "linkedin": (LinkedInScraper, LinkedInApplicator),
    "naukri": (NaukriScraper, NaukriApplicator),
    "monster": (MonsterScraper, MonsterApplicator),
    "joindevops": (JoinDevOpsScraper, JoinDevOpsApplicator),
}

_PROFILE_SYSTEM = "Extract resume data. Return only JSON. No explanation, no markdown."

_DEFAULT_PROFILE: dict = {
    "name": "Candidate",
    "email": "",
    "phone": "",
    "skills": [],
    "experience_years": settings.experience_years,
    "current_role": "DevOps Engineer",
    "education": "",
    "certifications": [],
    "summary": "",
}


async def _extract_profile(resume_text: str) -> dict:
    """Extract structured candidate profile from resume text via LLM."""
    prompt = (
        f"Extract the candidate profile from this resume text. "
        f"Return ONLY a valid JSON object with these keys: "
        f"name, email, phone, skills (array), experience_years (number), "
        f"current_role, education, certifications (array), summary. "
        f"Resume: {resume_text[:4000]}\n\n"
        f"Return ONLY the JSON object — no explanation, no markdown backticks."
    )
    try:
        llm = get_llm()
        resp = await llm.complete(prompt, system=_PROFILE_SYSTEM)
        clean = clean_json(resp.content)
        profile = json.loads(clean)
        logger.info(
            f"Orchestrator profile extracted: {profile.get('name', 'Unknown')} "
            f"({profile.get('experience_years', 0)} yrs, "
            f"{len(profile.get('skills', []))} skills)"
        )
        return profile
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Orchestrator profile extraction failed: {e} — using defaults")
        return _DEFAULT_PROFILE.copy()


async def _process_listing(
    listing: JobListing,
    context,
    applicator: BaseApplicator,
    profile: dict,
    resume_text: str,
    seen_ids: set,
    stats: dict,
    applied_count: list,
    redirected_jobs_list: list,
    failed_jobs_list: list,
) -> None:
    """Process a single job listing: dedupe -> match -> cover letter -> apply -> notify."""
    # Cross-run deduplication
    if repo.job_exists(listing.id):
        logger.debug(f"Orchestrator already seen: {listing.id}")
        return

    # Within-run deduplication
    if listing.id in seen_ids:
        logger.debug(f"Orchestrator duplicate within run: {listing.id}")
        return
    seen_ids.add(listing.id)

    # Application cap check
    if applied_count[0] >= settings.max_applications_per_run:
        logger.info(f"Orchestrator max applications reached ({settings.max_applications_per_run})")
        return

    # Save to DB as 'discovered'
    job_row = Job(
        id=listing.id,
        platform=listing.platform,
        title=listing.title,
        company=listing.company,
        location=listing.location,
        description=listing.description,
        url=listing.url,
        salary=listing.salary,
        experience_required=listing.experience_required,
        posted_date=listing.posted_date,
        is_easy_apply=listing.is_easy_apply,
    )
    repo.save_job(job_row)

    # Skip easy-apply check if configured
    if settings.apply_easy_apply_only and not listing.is_easy_apply:
        repo.update_job_status(listing.id, "skipped")
        stats["skipped"] += 1
        return

    # LLM match scoring
    match = await match_job(
        job_title=listing.title,
        job_description=listing.description or listing.title,
        profile=profile,
        resume_text=resume_text,
    )
    score = match.get("score", 0)
    recommendation = match.get("recommendation", "skip")

    repo.update_job_status(
        listing.id,
        "matched" if score >= settings.match_threshold else "skipped",
        match_score=float(score),
        match_reasons=json.dumps(match.get("reasons", [])),
        missing_skills=json.dumps(match.get("missing_skills", [])),
    )

    if score < settings.match_threshold or recommendation == "skip":
        stats["skipped"] += 1
        logger.debug(f"Orchestrator skipped (score={score}): {listing.title}")
        return

    stats["matched"] += 1

    # Generate tailored resume dynamically inside temp folder
    temp_resume_path = f"temp/tailored_resume_{listing.id}.docx"
    profile["temp_resume_path"] = temp_resume_path

    try:
        from resume.generator import generate_tailored_resume
        resume_ok = await generate_tailored_resume(
            job_title=listing.title,
            job_description=listing.description or listing.title,
            profile=profile,
            output_path=temp_resume_path
        )
        if not resume_ok:
            logger.warning("Could not generate tailored resume — falling back to standard profile resume.")
            if "temp_resume_path" in profile:
                del profile["temp_resume_path"]

        # Generate cover letter
        cover_letter = await generate_cover_letter(
            job_title=listing.title,
            company=listing.company or "the company",
            job_description=listing.description or "",
            profile=profile,
        )
        repo.update_job_status(listing.id, "matched", cover_letter=cover_letter)

        # Submit application
        applied = await applicator.apply(context=context, job=listing, cover_letter=cover_letter, profile=profile)

        if applied:
            applied_count[0] += 1
            stats["applied"] += 1
            repo.update_job_status(listing.id, "applied", applied_at=datetime.now(timezone.utc))
            await _notify_application(listing, match, score)
        else:
            stats["failed"] += 1
            repo.update_job_status(listing.id, "failed")
            failed_jobs_list.append({
                "Company": listing.company or "Unknown",
                "Position": listing.title,
                "URL": listing.url or "N/A",
                "Platform": listing.platform,
                "Reason": "Verification failed or application button not responsive"
            })
    except ExternalRedirectException as e:
        stats["skipped"] += 1
        repo.update_job_status(listing.id, "redirected")
        redirected_jobs_list.append({
            "Company": listing.company or "Unknown",
            "Position": listing.title,
            "URL": listing.url or "N/A",
            "Platform": listing.platform,
            "Details": str(e)
        })
        logger.info(f"Skipped external redirect job: {listing.title} @ {listing.company}")
    except Exception as e:
        stats["failed"] += 1
        repo.update_job_status(listing.id, "failed")
        failed_jobs_list.append({
            "Company": listing.company or "Unknown",
            "Position": listing.title,
            "URL": listing.url or "N/A",
            "Platform": listing.platform,
            "Reason": str(e)
        })
        logger.error(f"Application failed with error for {listing.title}: {e}")
    finally:
        # Guarantee removal of temporary tailored resume file to save storage
        import os
        # if os.path.exists(temp_resume_path):
        #     try:
        #         os.remove(temp_resume_path)
        #         logger.info(f"Deleted temporary tailored resume: {temp_resume_path}")
        #     except Exception as del_err:
        #         logger.warning(f"Could not delete temporary tailored resume {temp_resume_path}: {del_err}")
        # if "temp_resume_path" in profile:
        #     del profile["temp_resume_path"]


async def _notify_application(listing: JobListing, match: dict, score: int) -> None:
    """Send a Telegram notification for a successful application."""
    reasons = match.get("reasons", [])[:2]
    reasons_text = "\n".join(f"✅ {r}" for r in reasons) if reasons else ""

    msg = (
        f"📨 *Application Sent!*\n"
        f"🏢 *{listing.company}*\n"
        f"💼 {listing.title}\n"
        f"📍 {listing.location or 'N/A'}\n"
        f"💰 {listing.salary or 'N/A'}\n"
        f"⭐ Match Score: {score}/100\n"
    )
    if reasons_text:
        msg += f"{reasons_text}\n"
    if listing.url:
        msg += f"🔗 [View Job]({listing.url})"

    await notify(msg)


async def run_agent() -> None:
    """Master agent loop — called by APScheduler at configured hour daily.

    Sequence:
    1. Parse resume -> extract candidate profile via LLM
    2. For each platform: login -> scrape -> match -> cover letter -> apply -> notify
    3. Save RunHistory -> send Telegram summary
    """
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("Orchestrator *** AGENT RUN STARTING ***")
    logger.info("=" * 60)

    stats: dict = {"discovered": 0, "matched": 0, "applied": 0, "failed": 0, "skipped": 0}
    platforms_scraped: List[str] = []
    run_status = "partial"

    # Phase 1: Resume parsing
    resume_text = ""
    profile = _DEFAULT_PROFILE.copy()

    try:
        resume_text = get_resume_text(settings.resume_pdf_path, settings.resume_docx_path)
        profile = await _extract_profile(resume_text)
        profile["raw_resume_text"] = resume_text
        repo.save_profile(profile)
    except FileNotFoundError as e:
        logger.error(f"Orchestrator resume not found: {e}")
        await notify(
            f"❌ *Run Failed*\n"
            f"🔴 Error: Resume file not found\n"
            f"💡 Fix: Add `resume.pdf` or `resume.docx` to `resume/uploads/`"
        )
        _save_run(stats, platforms_scraped, time.time() - start_time, "failed", str(e))
        return

    # Phase 2: Platform loop
    seen_ids: set = set()
    redirected_jobs_list = []
    failed_jobs_list = []

    for platform_name, (ScraperClass, ApplicatorClass) in SCRAPERS.items():
        logger.info(f"Orchestrator Platform: {platform_name.upper()}")
        
        # Reset the application count per platform so it tests each platform
        applied_count = [0]

        playwright = None
        browser = None
        context = None

        try:
            playwright, browser = await create_browser()
            
            # Use saved session storage state if exists
            import os
            session_dir = "data/sessions"
            os.makedirs(session_dir, exist_ok=True)
            session_path = os.path.join(session_dir, f"{platform_name}.json")
            
            if os.path.exists(session_path):
                logger.info(f"Orchestrator: Loading saved session for {platform_name} from {session_path}")
                context = await create_context(browser, storage_state=session_path)
            else:
                context = await create_context(browser)
                
            scraper = ScraperClass()
            applicator = ApplicatorClass()

            logged_in = await scraper.login(context)
            if logged_in:
                # Save session state after successful login
                try:
                    await context.storage_state(path=session_path)
                    logger.info(f"Orchestrator: Saved session state for {platform_name} to {session_path}")
                except Exception as save_err:
                    logger.warning(f"Orchestrator: Could not save session state for {platform_name}: {save_err}")
            if not logged_in:
                logger.error(f"Orchestrator login failed for {platform_name} — skipping")
                continue

            listings = await scraper.scrape_jobs(context)
            stats["discovered"] += len(listings)
            platforms_scraped.append(platform_name)

            logger.info(f"Orchestrator {platform_name}: {len(listings)} listings found")

            for listing in listings:
                if applied_count[0] >= settings.max_applications_per_run:
                    logger.info("Orchestrator application cap reached — stopping")
                    break
                await _process_listing(
                    listing=listing,
                    context=context,
                    applicator=applicator,
                    profile=profile,
                    resume_text=resume_text,
                    seen_ids=seen_ids,
                    stats=stats,
                    applied_count=applied_count,
                    redirected_jobs_list=redirected_jobs_list,
                    failed_jobs_list=failed_jobs_list,
                )

        except Exception as e:
            logger.error(f"Orchestrator platform {platform_name} failed: {e}")
        finally:
            for resource in [context, browser, playwright]:
                if resource:
                    try:
                        if hasattr(resource, 'close'):
                            await resource.close()
                        elif hasattr(resource, 'stop'):
                            await resource.stop()
                    except Exception:
                        pass

    # Phase 3: Wrap-up
    duration = time.time() - start_time

    if stats["applied"] > 0:
        run_status = "success"
    elif platforms_scraped:
        run_status = "partial"
    else:
        run_status = "failed"

    # Generate Excel report after run
    _generate_excel_report(redirected_jobs_list, failed_jobs_list)

    # Send email report if recipient email exists
    recipient = settings.linkedin_email or settings.naukri_email or settings.monster_email or settings.joindevops_email
    if recipient:
        from notifications.email_sender import send_email_with_report
        await send_email_with_report(recipient, "data/job_applications_report.xlsx")

    _save_run(stats, platforms_scraped, duration, run_status)
    await notify(_build_summary(stats, platforms_scraped, duration))

    _cleanup_temp_files()

    logger.success(
        f"Orchestrator run complete in {duration/60:.1f} min — "
        f"applied={stats['applied']}, skipped={stats['skipped']}, "
        f"discovered={stats['discovered']}"
    )
    logger.info("=" * 60)


def _build_summary(stats: dict, platforms: List[str], duration: float) -> str:
    platforms_str = ", ".join(p.capitalize() for p in platforms) or "None"
    return (
        f"🤖 *Job Agent Run Complete*\n"
        f"⏱ Duration: {duration/60:.1f} min\n"
        f"🌐 Platforms: {platforms_str}\n"
        f"🔍 Discovered: {stats['discovered']}\n"
        f"✅ Matched: {stats['matched']}\n"
        f"📨 Applied: {stats['applied']}\n"
        f"⏭️ Skipped: {stats['skipped']}\n"
        f"❌ Failed: {stats['failed']}"
    )


def _save_run(
    stats: dict,
    platforms: List[str],
    duration: float,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    run = RunHistory(
        jobs_discovered=stats.get("discovered", 0),
        jobs_matched=stats.get("matched", 0),
        jobs_applied=stats.get("applied", 0),
        jobs_failed=stats.get("failed", 0),
        jobs_skipped=stats.get("skipped", 0),
        platforms_scraped=json.dumps(platforms),
        duration_seconds=duration,
        status=status,
        error_message=error_message,
    )
    repo.save_run(run)


def _generate_excel_report(redirected_jobs: list, failed_jobs: list) -> None:
    """Generate Excel report with two tabs: Redirected and Failed."""
    try:
        import pandas as pd
        import os

        # Ensure directory exists
        os.makedirs("data", exist_ok=True)
        report_path = "data/job_applications_report.xlsx"

        # Create DataFrames
        df_redirected = pd.DataFrame(redirected_jobs)
        df_failed = pd.DataFrame(failed_jobs)

        # Ensure correct columns if lists are empty
        if df_redirected.empty:
            df_redirected = pd.DataFrame(columns=["Company", "Position", "URL", "Platform", "Details"])
        if df_failed.empty:
            df_failed = pd.DataFrame(columns=["Company", "Position", "URL", "Platform", "Reason"])

        # Write to Excel with two sheets
        with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
            df_redirected.to_excel(writer, sheet_name="Redirected", index=False)
            df_failed.to_excel(writer, sheet_name="Failed Applications", index=False)

        logger.success(f"Successfully generated Excel report: {report_path}")
    except Exception as e:
        logger.error(f"Failed to generate Excel report: {e}")


def _cleanup_temp_files() -> None:
    """Remove temporary files from 'temp/', screenshots from 'artifacts/', Excel reports, and log files to save space."""
    import os
    import shutil
    from pathlib import Path

    logger.info("Starting post-run cleanup of temporary files, reports, and logs...")

    # 1. Clean temp directory (tailored resumes)
    temp_dir = Path("temp")
    if temp_dir.exists() and temp_dir.is_dir():
        for item in temp_dir.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                    logger.debug(f"Deleted temp file: {item}")
                elif item.is_dir():
                    shutil.rmtree(item)
                    logger.debug(f"Deleted temp dir: {item}")
            except Exception as e:
                logger.warning(f"Failed to delete temp item {item}: {e}")

    # 2. Clean artifacts directory (screenshots and other transient files)
    artifacts_dir = Path("artifacts")
    if artifacts_dir.exists() and artifacts_dir.is_dir():
        for item in artifacts_dir.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                    logger.debug(f"Deleted artifact file: {item}")
                elif item.is_dir():
                    shutil.rmtree(item)
                    logger.debug(f"Deleted artifact dir: {item}")
            except Exception as e:
                logger.warning(f"Failed to delete artifact item {item}: {e}")

    # 3. Clean temporary Excel reports from data/
    report_file = Path("data/job_applications_report.xlsx")
    if report_file.exists() and report_file.is_file():
        try:
            report_file.unlink()
            logger.debug(f"Deleted Excel report: {report_file}")
        except Exception as e:
            logger.warning(f"Failed to delete Excel report {report_file}: {e}")

    # 4. Clean logs directory (requires releasing loguru file handler lock)
    logs_dir = Path("logs")
    if logs_dir.exists() and logs_dir.is_dir():
        try:
            # Temporarily remove all logger handlers to release the file lock on log files
            from loguru import logger as loguru_logger
            loguru_logger.remove()

            for item in logs_dir.iterdir():
                try:
                    if item.is_file():
                        item.unlink()
                except Exception:
                    pass
        except Exception as logger_err:
            pass
        finally:
            # Re-initialize logging handlers so subsequent messages can be logged
            from utils.logger import configure_logger
            configure_logger()

    logger.info("Post-run cleanup of temporary files, reports, and logs completed.")
