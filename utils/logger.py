"""Loguru logger configuration + clean_json() utility for LLM response parsing."""

import re
import sys
from pathlib import Path

from loguru import logger

# Ensure logs directory exists
Path("logs").mkdir(exist_ok=True)


def configure_logger() -> None:
    """Configure the Loguru logger handlers for stdout and rotating file."""
    # Remove all existing handlers
    logger.remove()

    # Colourised stdout at INFO level
    logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
            "<level>{message}</level>"
        ),
        level="INFO",
        colorize=True,
        enqueue=True,
    )

    # Debug-level daily rotating file with 7-day retention
    logger.add(
        "logs/job_agent_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="7 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        enqueue=True,
    )


# Perform initial setup on import
configure_logger()


def clean_json(text: str) -> str:
    """Strip markdown code fences from LLM responses before JSON parsing.

    Args:
        text: Raw LLM response string, possibly containing markdown fences.

    Returns:
        Clean string with fences removed, ready for json.loads().
    """
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()
