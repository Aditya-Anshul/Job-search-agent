"""Playwright stealth browser factory — create_browser() and create_context()."""

import random
from typing import Tuple

from fake_useragent import UserAgent
from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from config.settings import settings
from utils.logger import logger

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
]

CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-extensions",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-default-apps",
    "--disable-gpu",
    "--window-size=1920,1080",
]

_STEALTH_JS = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5], configurable: true });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en-GB', 'en'], configurable: true });
    window.chrome = { runtime: { id: 'no-extension', getManifest: () => ({}) } };
    const _origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (p) => (
        p.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : _origQuery(p)
    );
    Object.defineProperty(navigator, 'userAgentData', { get: () => undefined, configurable: true });
"""


async def create_browser() -> Tuple[Playwright, Browser]:
    """Launch a stealth Chromium browser with anti-detection flags."""
    import os
    import platform

    playwright = await async_playwright().start()

    # 1. If explicit path is provided, use it directly
    executable_path = os.getenv("PLAYWRIGHT_CHROMIUM_PATH")
    if executable_path:
        logger.info(f"Stealth Browser: Using custom Chromium path from environment: {executable_path}")
        browser = await playwright.chromium.launch(
            headless=settings.headless,
            args=CHROMIUM_ARGS,
            executable_path=executable_path,
        )
        logger.debug(f"Browser Chromium launched: headless={settings.headless}")
        return playwright, browser

    # 2. Try default Playwright launch (uses downloaded Playwright binary)
    try:
        browser = await playwright.chromium.launch(
            headless=settings.headless,
            args=CHROMIUM_ARGS,
        )
        logger.debug(f"Browser Chromium launched via Playwright default: headless={settings.headless}")
        return playwright, browser
    except Exception as default_err:
        logger.info(f"Default Playwright launch failed: {default_err}. Scanning system for system-wide Chromium/Chrome...")

    # 3. System-wide scan fallback for all architectures
    system = platform.system().lower()
    machine = platform.machine().lower()
    detected_path = None

    if system == "linux":
        for path in [
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/google-chrome-beta",
            "/usr/bin/google-chrome-unstable",
            "/snap/bin/chromium",
            "/var/lib/flatpak/exports/bin/org.chromium.Chromium",
        ]:
            if os.path.exists(path):
                detected_path = path
                break
    elif system == "darwin":  # macOS
        for path in [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]:
            if os.path.exists(path):
                detected_path = path
                break
    elif system == "windows":
        for path in [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        ]:
            if os.path.exists(path):
                detected_path = path
                break

    if detected_path:
        logger.info(f"Stealth Browser: Successfully detected system browser ({system}/{machine}): {detected_path}")
        browser = await playwright.chromium.launch(
            headless=settings.headless,
            args=CHROMIUM_ARGS,
            executable_path=detected_path,
        )
        logger.debug(f"Browser Chromium launched: headless={settings.headless}")
        return playwright, browser
    else:
        # Re-raise the original Playwright error if no system browser was found
        logger.error("Stealth Browser: No system-wide Chromium/Chrome found. Please install Chromium or set PLAYWRIGHT_CHROMIUM_PATH.")
        raise default_err




async def create_context(browser: Browser, storage_state: str = None) -> BrowserContext:
    """Create a fresh stealth BrowserContext with random UA and viewport.

    Each call creates an isolated context — never share contexts between platforms.
    """
    default_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    try:
        ua = UserAgent(os=["windows", "macos"], browsers=["chrome", "edge"])
        user_agent = ua.random
    except Exception as e:
        logger.warning(f"fake-useragent failed: {e}. Using robust default User-Agent.")
        user_agent = default_ua

    viewport = random.choice(VIEWPORTS)

    context = await browser.new_context(
        viewport=viewport,
        user_agent=user_agent,
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        extra_http_headers={"Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8"},
        storage_state=storage_state,
    )

    await context.add_init_script(script=_STEALTH_JS)

    logger.debug(
        f"Browser context created: UA={user_agent[:50]}... "
        f"viewport={viewport['width']}x{viewport['height']}"
    )
    return context
