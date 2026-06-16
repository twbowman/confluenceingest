"""Fetch pages from Confluence via REST API using Bearer token (PAT) authentication."""

import requests
from config import Config


def _get_headers() -> dict:
    """Build request headers with Bearer token authentication."""
    return {
        "Authorization": f"Bearer {Config.CONFLUENCE_PAT}",
        "Accept": "application/json",
    }


def fetch_pages_from_space(space_key: str) -> list[dict]:
    """Fetch all pages from a Confluence space using the REST API."""
    pages = []
    start = 0
    limit = 50

    while True:
        url = (
            f"{Config.CONFLUENCE_URL}/rest/api/content"
            f"?spaceKey={space_key}"
            f"&type=page"
            f"&expand=body.storage,metadata.labels,ancestors,version"
            f"&start={start}&limit={limit}"
        )
        response = requests.get(
            url,
            headers=_get_headers(),
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        if not results:
            break

        pages.extend(results)
        start += limit

        if data.get("size", 0) < limit:
            break

    return pages


def fetch_pages_by_ids(page_ids: list[str]) -> list[dict]:
    """Fetch specific pages by their IDs."""
    pages = []
    for page_id in page_ids:
        url = (
            f"{Config.CONFLUENCE_URL}/rest/api/content/{page_id}"
            f"?expand=body.storage,metadata.labels,ancestors,version"
        )
        response = requests.get(
            url,
            headers=_get_headers(),
            timeout=30,
        )
        response.raise_for_status()
        pages.append(response.json())

    return pages


def fetch_pages(space_key: str) -> list[dict]:
    """
    Fetch pages for the given space key.

    Returns raw Confluence page objects with body, metadata, ancestors, and version.
    """
    if Config.CONFLUENCE_PAGE_IDS:
        print(f"  Fetching {len(Config.CONFLUENCE_PAGE_IDS)} specific page(s)...")
        return fetch_pages_by_ids(Config.CONFLUENCE_PAGE_IDS)

    print(f"  Fetching all pages from space: {space_key}...")
    return fetch_pages_from_space(space_key)
