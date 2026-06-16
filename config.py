"""Configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration from .env file."""

    # Confluence
    CONFLUENCE_URL: str = os.getenv("CONFLUENCE_URL", "")
    CONFLUENCE_USERNAME: str = os.getenv("CONFLUENCE_USERNAME", "")
    CONFLUENCE_API_TOKEN: str = os.getenv("CONFLUENCE_API_TOKEN", "")
    CONFLUENCE_SPACE_KEY: str = os.getenv("CONFLUENCE_SPACE_KEY", "")
    CONFLUENCE_PAGE_IDS: list[str] = [
        pid.strip()
        for pid in os.getenv("CONFLUENCE_PAGE_IDS", "").split(",")
        if pid.strip()
    ]

    # Output
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "./knowledge-base")
