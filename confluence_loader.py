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


def fetch_attachments(page_id: str) -> list[dict]:
    """
    Fetch attachment metadata for a page.

    Returns list of attachment dicts with keys: title, downloadUrl, fileSize, mediaType.
    """
    attachments = []
    start = 0
    limit = 50

    while True:
        url = (
            f"{Config.CONFLUENCE_URL}/rest/api/content/{page_id}/child/attachment"
            f"?start={start}&limit={limit}"
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

        attachments.extend(results)
        start += limit

        if data.get("size", 0) < limit:
            break

    return attachments


def download_attachment(download_path: str) -> bytes | None:
    """
    Download an attachment binary from Confluence.

    Args:
        download_path: The relative download URL from the attachment metadata
                       (e.g., /download/attachments/12345/image.png)

    Returns:
        File content as bytes, or None if download fails.
    """
    url = f"{Config.CONFLUENCE_URL}{download_path}"
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {Config.CONFLUENCE_PAT}"},
            timeout=60,
            stream=True,
        )
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
        print(f"    WARNING: Failed to download attachment: {e}")
        return None
