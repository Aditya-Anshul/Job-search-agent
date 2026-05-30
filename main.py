"""Entry point — APScheduler cron setup and keep-alive loop."""

import asyncio
import os
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Force current working directory to the project directory containing main.py
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from agent.orchestrator import run_agent
from config.settings import settings
from utils.logger import logger

load_dotenv()


async def main() -> None:
    """Application entry point.

    Creates required directories, sets up APScheduler, optionally runs
    immediately if RUN_NOW=true, then enters a keep-alive loop.
    """
    for d in ["data", "logs", "resume/uploads", "artifacts", "temp"]:
        Path(d).mkdir(parents=True, exist_ok=True)

    # ── SSL Certificate Diagnostic Check ──────────────────────────────────────
    try:
        import urllib.request
        import ssl
        # Check standard HTTPS connectivity to LLM APIs
        urllib.request.urlopen("https://generativelanguage.googleapis.com", timeout=5)
    except ssl.SSLCertVerificationError as ssl_err:
        logger.error(
            "\n" + "!" * 80 + "\n"
            "⚠️  CRITICAL SSL DIAGNOSTIC WARNING\n"
            "Secure HTTPS request to Gemini API failed due to SSL Certificate Verification error.\n"
            "This is very common in Android UserLAnd or Termux PRoot Ubuntu containers due to missing system CA certificates.\n\n"
            "👉 TO RESOLVE: Please run this command in your Ubuntu console to install root certificates:\n"
            "   sudo apt update && sudo apt install -y ca-certificates && sudo update-ca-certificates\n"
            "!" * 80 + "\n"
        )
    except Exception:
        pass

    logger.info("=" * 60)
    logger.info("Job Agent starting up...")
    logger.info(f"Job Agent LLM provider: {settings.llm_provider}")
    logger.info("Job Agent Scheduled: 3 times daily (09:00, 13:00, 17:00) Asia/Kolkata")
    logger.info(f"Job Agent Match threshold: {settings.match_threshold}%")
    logger.info(f"Job Agent Max applications per run: {settings.max_applications_per_run}")
    logger.info("=" * 60)

    scheduler = AsyncIOScheduler(timezone=settings.run_timezone)
    scheduler.add_job(
        run_agent,
        CronTrigger(hour="9,13,17", minute=0, timezone=settings.run_timezone),
        id="job_agent_thrice_daily",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()

    next_run = scheduler.get_job("job_agent_thrice_daily").next_run_time
    logger.info(f"Job Agent next scheduled run: {next_run}")

    run_now = os.getenv("RUN_NOW", "false").lower() == "true"
    if run_now:
        logger.info("Job Agent RUN_NOW=true detected — executing immediately...")
        await run_agent()
    else:
        logger.info(
            "Job Agent waiting for scheduled run. "
            "Set RUN_NOW=true to run immediately."
        )

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Job Agent shutting down gracefully...")
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
