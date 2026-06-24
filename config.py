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
    CONFLUENCE_SPACE_KEYS: list[str] = [
        key.strip() for key in os.getenv("CONFLUENCE_SPACE_KEY", "").split(",") if key.strip()
    ]
    CONFLUENCE_PAGE_IDS: list[str] = [
        pid.strip() for pid in os.getenv("CONFLUENCE_PAGE_IDS", "").split(",") if pid.strip()
    ]

    # Output — base directory; each space gets a subdirectory under this
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "./knowledge-base")

    # Attachments
    ATTACHMENTS_DIR: str = os.getenv("ATTACHMENTS_DIR", "attachments")
    # Max attachment size in MB — files larger than this will be skipped with a warning
    ATTACHMENT_MAX_SIZE_MB: int = int(os.getenv("ATTACHMENT_MAX_SIZE_MB", "50"))

    # Knowledge base Git repo
    KB_GIT_REPO_URL: str = os.getenv("KB_GIT_REPO_URL", "")
    KB_GIT_BRANCH: str = os.getenv("KB_GIT_BRANCH", "master")
    KB_GIT_SSH_KEY: str = os.getenv("KB_GIT_SSH_KEY", "")
    KB_GIT_AUTHOR_NAME: str = os.getenv("KB_GIT_AUTHOR_NAME", "confluence-sync")
    KB_GIT_AUTHOR_EMAIL: str = os.getenv("KB_GIT_AUTHOR_EMAIL", "confluence-sync@mycompany.com")
