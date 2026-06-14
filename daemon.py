"""Lightweight scheduler daemon — checks time and spawns main.py as a subprocess to prevent memory leaks and container crashes."""

import asyncio
import os
import sys
import time
import platform
import shutil
import subprocess
from datetime import datetime
import pytz

# Add current folder to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.settings import settings
from utils.logger import logger

# Configured schedule from settings / defaults
SCHEDULED_HOURS = [9, 13, 17]  # 09:00, 13:00, 17:00
TZ = pytz.timezone(settings.run_timezone or "Asia/Kolkata")

def trigger_run():
    """Spawn python main.py in a separate subprocess with RUN_NOW=true."""
    logger.info("=" * 60)
    logger.info("Daemon: Triggering Job Agent run...")
    logger.info("=" * 60)

    # 1. Base command
    cmd = [sys.executable, "main.py"]

    # 2. Check if we should prepend xvfb-run
    # If on Linux and headed mode (headless=False) is configured
    is_linux = platform.system().lower() == "linux"
    is_headed = not settings.headless
    
    if is_linux and is_headed:
        if shutil.which("xvfb-run"):
            logger.info("Daemon: Linux headed mode detected. Prepended 'xvfb-run -a' to automation context.")
            cmd = ["xvfb-run", "-a", "--server-args=-screen 0 1920x1080x24"] + cmd
        else:
            logger.warning("Daemon: Headless is false but 'xvfb-run' is not installed! Subprocess might crash if no display is available.")

    # 3. Environment variables
    env = os.environ.copy()
    env["RUN_NOW"] = "true"

    try:
        # Spawn the subprocess and stream logs directly
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Stream the stdout/stderr to the console in real-time
        for line in process.stdout:
            print(line.rstrip())
            
        process.wait()
        logger.info("=" * 60)
        logger.info(f"Daemon: Job Agent run subprocess completed with exit code: {process.returncode}")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"Daemon: Failed to execute Job Agent subprocess: {e}")

async def run_daemon():
    logger.info("=" * 60)
    logger.info("Job Agent daemon scheduler active...")
    logger.info(f"Timezone: {TZ.zone}")
    logger.info(f"Scheduled Hours: {SCHEDULED_HOURS} (at minute 00)")
    logger.info("=" * 60)

    # Handle immediate startup execution flag
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("--now", "-now", "now"):
        logger.info("Daemon: immediate start flag --now detected.")
        trigger_run()

    last_trigger_hour = -1

    while True:
        try:
            # Get current time in target timezone
            now = datetime.now(TZ)
            current_hour = now.hour
            current_minute = now.minute

            # Trigger only if current hour is scheduled, minute is 00, and we haven't already run this hour
            if current_hour in SCHEDULED_HOURS and current_minute == 0:
                if last_trigger_hour != current_hour:
                    logger.info(f"Daemon: Scheduled trigger hit at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    trigger_run()
                    last_trigger_hour = current_hour
            else:
                # Reset hour tracker when minute moves past 0
                if current_minute != 0:
                    last_trigger_hour = -1

            # Sleep for 30 seconds before checking time again
            await asyncio.sleep(30)

        except (KeyboardInterrupt, SystemExit):
            logger.info("Daemon shutting down gracefully...")
            break
        except Exception as e:
            logger.error(f"Daemon loop encountered an error: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        asyncio.run(run_daemon())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Daemon exited.")
