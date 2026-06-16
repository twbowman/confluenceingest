"""Configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration from .env file."""

    # Confluence
    CONFLUENCE_URL: str = os.getenv("CONFLUENCE_URL", "")
    CONFLUENCE_PAT: str = os.getenv("CONFLUENCE_PAT", "")
    CONFLUENCE_SPACE_KEY: str = os.getenv("CONFLUENCE_SPACE_KEY", "")
    CONFLUENCE_PAGE_IDS: list[str] = [
        pid.strip()
        for pid in os.getenv("CONFLUENCE_PAGE_IDS", "").split(",")
        if pid.strip()
    ]

    # Output
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "./knowledge-base")
