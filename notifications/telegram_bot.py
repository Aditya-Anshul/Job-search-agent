"""Telegram notification client — notify() sends messages to the configured chat."""

from typing import Optional

from telegram import Bot
from telegram.constants import ParseMode

from config.settings import settings
from utils.logger import logger

_bot: Optional[Bot] = None


def _get_bot() -> Optional[Bot]:
    """Initialise and return the Telegram Bot singleton."""
    global _bot
    if _bot is None and settings.telegram_bot_token:
        try:
            _bot = Bot(token=settings.telegram_bot_token)
        except Exception as e:
            logger.error(f"Telegram failed to initialise bot: {e}")
    return _bot


async def notify(message: str) -> None:
    """Send a message to the configured Telegram chat.

    Gracefully skips if Telegram is not configured — notifications
    are non-critical and must never crash the agent run.
    """
    bot = _get_bot()

    if not bot:
        logger.warning("Telegram bot not configured — skipping notification")
        return

    if not settings.telegram_chat_id:
        logger.warning("Telegram TELEGRAM_CHAT_ID not set — skipping notification")
        return

    try:
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False,
        )
        logger.debug("Telegram message sent successfully")
    except Exception as e:
        logger.error(f"Telegram send_message failed: {e}")
