import asyncio
import os
import sys
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser.setup import create_browser
from config.settings import settings
from utils.logger import logger

async def test_scrapers():
    os.makedirs("artifacts", exist_ok=True)
    
    # Force headless=False to test headed bypass
    playwright = await async_playwright().start()
    
    # Use standard args but headless=False
    from browser.setup import CHROMIUM_ARGS
    
    # Try finding custom path
    import platform
    executable_path = os.getenv("PLAYWRIGHT_CHROMIUM_PATH")
    if not executable_path and platform.machine() in ("aarch64", "arm64"):
        for path in ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome"]:
            if os.path.exists(path):
                executable_path = path
                break
                
    launch_kwargs = {
        "headless": False,
        "args": CHROMIUM_ARGS,
    }
    if executable_path:
        launch_kwargs["executable_path"] = executable_path
        
    logger.info(f"Launching browser in HEADED mode (headless=False)... Path: {executable_path}")
    browser = await playwright.chromium.launch(**launch_kwargs)
    
    try:
        context = await browser.new_context()
        page = await context.new_page()
        
        # Get user agent
        ua = await page.evaluate("navigator.userAgent")
        logger.info(f"Headed browser User-Agent: {ua}")
        
        # Test Naukri
        logger.info("Navigating to Naukri login page in headed mode...")
        await page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(4)
        n_title = await page.title()
        logger.info(f"Naukri Title: {n_title}")
        
        # Test Monster
        logger.info("Navigating to Monster login page in headed mode...")
        await page.goto("https://www.foundit.in/rio/login", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(4)
        m_title = await page.title()
        logger.info(f"Monster Title: {m_title}")
        
    except Exception as e:
        logger.error(f"Headed test failed: {e}")
    finally:
        await browser.close()
        await playwright.stop()

if __name__ == "__main__":
    asyncio.run(test_scrapers())
