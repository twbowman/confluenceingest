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

    # Knowledge base Git repo
    KB_GIT_REPO_URL: str = os.getenv("KB_GIT_REPO_URL", "")
    KB_GIT_BRANCH: str = os.getenv("KB_GIT_BRANCH", "main")
    KB_GIT_SSH_KEY: str = os.getenv("KB_GIT_SSH_KEY", "")
    KB_GIT_AUTHOR_NAME: str = os.getenv("KB_GIT_AUTHOR_NAME", "confluence-sync")
    KB_GIT_AUTHOR_EMAIL: str = os.getenv("KB_GIT_AUTHOR_EMAIL", "confluence-sync@mycompany.com")
