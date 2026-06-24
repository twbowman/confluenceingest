"""
Confluence → Markdown sync tool.

Exports Confluence pages to a tool-agnostic Markdown knowledge base with
YAML frontmatter metadata. Organizes files in a directory structure that
mirrors the Confluence page hierarchy, namespaced by space key.

Supports multiple spaces in a single run — each gets its own subdirectory.

Flow:
    1. Pull (clone) the knowledge base Git repo from GitLab
    2. For each configured space:
       a. Fetch pages from Confluence
       b. Convert and write changed pages into <repo>/<space_key>/
    3. Commit and push all changes back to GitLab
    4. Clean up the local clone (unless --keep-local)

Usage:
    python sync.py             # Full sync of all configured spaces
    python sync.py --dry-run   # Show what would be synced without writing
    python sync.py --no-push   # Sync files but skip git push
    python sync.py --keep-local # Keep the local clone after pushing
"""

import argparse
import re
import json
from pathlib import Path
from datetime import datetime

from config import Config
from confluence_loader import fetch_pages, fetch_attachments, download_attachment
from converter import convert_page
from git_publisher import (
    pull_kb_repo,
    push_kb_repo,
    cleanup_kb_repo,
    get_space_dir,
    get_clone_dir,
)


def build_file_path(page: dict, space_dir: str, parent_ids: set) -> Path:
    """
    Build the output file path preserving page hierarchy as directories.

    - Parent pages (those with children) → <page-title>/index.md
    - Leaf pages (no children) → <page-title>.md

    This is compatible with MkDocs, Docusaurus, and similar doc tools.
    """
    ancestors = [ancestor["title"] for ancestor in page.get("ancestors", [])]
    title = page["title"]

    # Build path segments from ancestors + page title
    segments = ancestors + [title]

    # Sanitize each segment for filesystem use
    safe_segments = []
    for segment in segments:
        safe = re.sub(r"[^\w\s-]", "", segment).strip()
        safe = re.sub(r"[\s]+", "-", safe).lower()
        if safe:
            safe_segments.append(safe)

    if not safe_segments:
        safe_segments = [page["id"]]

    is_parent = page["id"] in parent_ids

    if is_parent:
        # Parent page → directory with index.md
        dir_path = Path(space_dir).joinpath(*safe_segments)
        return dir_path / "index.md"
    else:
        # Leaf page → named .md file in parent directory
        filename = safe_segments.pop() + ".md"
        dir_path = (
            Path(space_dir).joinpath(*safe_segments)
            if safe_segments
            else Path(space_dir)
        )
        return dir_path / filename


def get_attachments_dir(space_key: str) -> Path:
    """
    Get the attachments directory for a space within the KB repo.

    Structure: <output_dir>/<space_key>/attachments/<page_id>/filename.ext
    Each space has its own attachments directory, in anticipation of
    future blob storage migration (one bucket per space).
    """
    return get_space_dir(space_key) / Config.ATTACHMENTS_DIR


def download_page_attachments(
    page_id: str,
    page_title: str,
    space_key: str,
    previous_attachments: dict,
    dry_run: bool = False,
    force: bool = False,
) -> tuple[list[str], dict]:
    """
    Download attachments for a page, skipping unchanged files.

    Compares attachment versions against previous sync state to avoid
    re-downloading identical files.

    Args:
        page_id: Confluence page ID
        page_title: Page title for logging
        space_key: Space key (for directory structure)
        previous_attachments: Dict of {filename: {version, size}} from last sync
        dry_run: If True, log what would be downloaded without writing files
        force: If True, download all regardless of version

    Returns:
        Tuple of (list of downloaded filenames, dict of new attachment state)
    """
    attachments = fetch_attachments(page_id)
    if not attachments:
        return [], {}

    downloaded = []
    new_attachment_state = {}
    page_attach_dir = get_attachments_dir(space_key) / page_id
    max_bytes = Config.ATTACHMENT_MAX_SIZE_MB * 1024 * 1024

    for att in attachments:
        filename = att.get("title", "unknown")
        file_size = att.get("extensions", {}).get("fileSize", 0)
        att_version = att.get("version", {}).get("number", 0)
        download_url = att.get("_links", {}).get("download", "")

        # Check if attachment has changed since last sync
        prev = previous_attachments.get(filename, {})
        if not force and prev.get("version") == att_version:
            # Unchanged — keep the previous state, skip download
            new_attachment_state[filename] = prev
            continue

        # Check size limit
        if file_size and int(file_size) > max_bytes:
            print(
                f"      WARNING: Skipping {filename} — "
                f"size {int(file_size) / 1024 / 1024:.1f}MB exceeds "
                f"{Config.ATTACHMENT_MAX_SIZE_MB}MB limit"
            )
            continue

        if dry_run:
            print(f"      WOULD DOWNLOAD: {filename} (v{att_version})")
            downloaded.append(filename)
            new_attachment_state[filename] = {
                "version": att_version,
                "size": int(file_size) if file_size else 0,
            }
            continue

        # Download the file
        content = download_attachment(download_url)
        if content is None:
            continue

        # Check actual download size
        if len(content) > max_bytes:
            print(
                f"      WARNING: Skipping {filename} — "
                f"downloaded size {len(content) / 1024 / 1024:.1f}MB exceeds "
                f"{Config.ATTACHMENT_MAX_SIZE_MB}MB limit"
            )
            continue

        # Write to disk
        page_attach_dir.mkdir(parents=True, exist_ok=True)
        file_path = page_attach_dir / filename
        file_path.write_bytes(content)
        downloaded.append(filename)
        new_attachment_state[filename] = {
            "version": att_version,
            "size": len(content),
        }
        print(
            f"      ATTACHMENT: {filename} v{att_version} ({len(content) / 1024:.0f} KB)"
        )

    return downloaded, new_attachment_state


def load_sync_state(space_dir: str) -> dict:
    """Load the previous sync state to enable incremental updates."""
    state_file = Path(space_dir) / ".sync-state.json"
    if state_file.exists():
        return json.loads(state_file.read_text(encoding="utf-8"))
    return {}


def save_sync_state(space_dir: str, state: dict):
    """Persist sync state for future incremental runs."""
    state_file = Path(space_dir) / ".sync-state.json"
    state_file.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def generate_kb_readme(space_keys: list[str], stats: dict):
    """
    Generate a README.md for the knowledge base repo describing the layout,
    spaces, and how to map them back to Confluence.
    """
    confluence_url = Config.CONFLUENCE_URL or "https://your-confluence-instance.com"
    last_sync = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

    spaces_table = "\n".join(
        f"| `{key.lower()}/` | {key} | [{key}]({confluence_url}/display/{key}) |"
        for key in space_keys
    )

    readme_content = f"""# Knowledge Base

Auto-generated Markdown knowledge base synced from Confluence.

**Source:** {confluence_url}
**Last sync:** {last_sync}

## Spaces

| Directory | Space Key | Confluence Link |
|-----------|-----------|-----------------|
{spaces_table}

## Repository Layout

```
knowledge-base/
├── README.md                          ← This file (auto-generated)
├── <space_key>/                       ← One directory per Confluence space
│   ├── .sync-state.json               ← Tracks page versions for incremental sync
│   ├── attachments/                   ← All attachments for pages in this space
│   │   └── <page_id>/                 ← Attachments grouped by page ID
│   │       ├── screenshot.png
│   │       └── document.pdf
│   ├── <parent-page>/                 ← Pages with children become directories
│   │   ├── index.md                   ← Parent page content
│   │   ├── child-page.md             ← Leaf child pages (named files)
│   │   └── another-child/            ← Child that also has children
│   │       ├── index.md
│   │       └── grandchild-page.md
│   └── leaf-page.md                   ← Top-level leaf pages (no children)
└── ...
```

## Mapping to Confluence

### Pages

Each Markdown file corresponds to a Confluence page. The YAML frontmatter at the top contains:

```yaml
id: "12345"                    # Confluence page ID
title: Page Title              # Original page title
space: ENG                     # Space key
source_url: https://...        # Direct link back to Confluence
last_modified: "2026-..."      # When the page was last edited in Confluence
version: 7                     # Confluence page version number
```

To find the original Confluence page, use the `source_url` in the frontmatter or navigate to:
`{confluence_url}/pages/<id>`

### Attachments

Attachments are stored under `<space_key>/attachments/<page_id>/`. The page ID in the path
corresponds to the `id` field in the markdown frontmatter.

To find attachments for a specific page in Confluence:
`{confluence_url}/pages/viewpageattachments.action?pageId=<page_id>`

### Directory Structure

The directory hierarchy mirrors the Confluence page tree:
- Top-level pages become direct children of the space directory
- Child pages nest in subdirectories named after their parent

Example: A page at **Engineering > Infrastructure > Deployment Runbook** in Confluence:
- If "Deployment Runbook" has children → `eng/engineering/infrastructure/deployment-runbook/index.md`
- If "Deployment Runbook" is a leaf page → `eng/engineering/infrastructure/deployment-runbook.md`

## Sync Behavior

- **Incremental:** Only pages that have changed in Confluence since the last sync are re-exported
- **Attachment versioning:** Only new or updated attachments are downloaded
- **Force sync:** Running with `--force` re-exports all pages regardless of version state
- **State tracking:** Each space has a `.sync-state.json` that tracks page and attachment versions

## Conversion Notes

Some Confluence macros have no static Markdown equivalent (e.g., `jira`, `children`, `include`,
`recently-updated`). When a macro cannot be converted, an HTML comment is left in the raw Markdown:

```html
<!-- Confluence macro: children (no static content) -->
```

These comments are invisible in rendered Markdown but visible in the raw `.md` files. You can
search for them to identify pages with incomplete conversions:

```bash
grep -r "Confluence macro:" <space_key>/
```

## Consuming This Data

| Use Case | Approach |
|----------|----------|
| RAG pipeline | Parse `.md` files, extract frontmatter for metadata, chunk content, embed |
| Static docs site | Point MkDocs/Docusaurus at the space directories |
| Full-text search | Index with Elasticsearch, Meilisearch, or Typesense |
| AI assistants | Feed markdown + frontmatter as context |

---

*This README is regenerated on each sync run.*
"""

    readme_path = get_clone_dir() / "README.md"
    readme_path.write_text(readme_content.strip() + "\n", encoding="utf-8")


def sync_space(
    space_key: str, dry_run: bool = False, force: bool = False, force_all: bool = False
) -> dict:
    """
    Sync a single Confluence space into its subdirectory.

    Args:
        force: Re-convert all pages regardless of version (converter fix scenario)
        force_all: Re-convert pages AND re-download all attachments

    Returns stats dict with created/updated/unchanged/skipped counts.
    """
    space_dir = str(get_space_dir(space_key))
    Path(space_dir).mkdir(parents=True, exist_ok=True)

    # Load sync state from the cloned repo (or empty if first run)
    previous_state = load_sync_state(space_dir)

    # Fetch pages from Confluence
    print(f"\n  Fetching pages from Confluence space: {space_key}...")
    pages = fetch_pages(space_key)
    print(f"  Found {len(pages)} page(s)")

    if not pages:
        return {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0}

    # Determine which pages are parents (have children)
    # A page is a parent if any other page lists it in its ancestors
    parent_ids = set()
    for page in pages:
        for ancestor in page.get("ancestors", []):
            parent_ids.add(ancestor["id"])

    new_state = {}
    stats = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0}

    # force or force_all both skip page version checks
    skip_page_version = force or force_all

    for page in pages:
        page_id = page["id"]
        title = page["title"]
        version = page.get("version", {}).get("number", 0)

        # Check if page has changed since last sync (skip if --force or --force-all)
        prev = previous_state.get(page_id, {})
        if not skip_page_version and prev.get("version") == version:
            stats["unchanged"] += 1
            new_state[page_id] = prev
            continue

        # Convert to Markdown
        content = convert_page(page, space_key)
        if not content:
            print(f"    SKIP (no content): {title}")
            stats["skipped"] += 1
            continue

        # Download attachments for this page (version-aware, skips unchanged)
        prev_attachments = prev.get("attachments", {})
        downloaded_attachments, new_attachment_state = download_page_attachments(
            page_id,
            title,
            space_key,
            previous_attachments=prev_attachments,
            dry_run=dry_run,
            force=force_all,
        )

        # Rewrite attachment path placeholders in the markdown
        # Path is relative to the KB repo root: /<space_key>/attachments/<page_id>
        attachments_rel_path = (
            f"/{space_key.lower()}/{Config.ATTACHMENTS_DIR}/{page_id}"
        )
        content = content.replace("%%ATTACHMENT_PATH%%", attachments_rel_path)

        # Replace attachment list macro placeholder with actual file listing
        if "KBATTACHMENTLIST" in content:
            all_attachments = list(new_attachment_state.keys())
            if all_attachments:
                att_lines = ["\n**Attachments:**\n"]
                for filename in sorted(all_attachments):
                    att_lines.append(
                        f"- [{filename}]({attachments_rel_path}/{filename})"
                    )
                content = content.replace(
                    "KBATTACHMENTLIST", "\n".join(att_lines) + "\n"
                )
            else:
                content = content.replace("KBATTACHMENTLIST", "")

        # Determine output path within the space directory
        file_path = build_file_path(page, space_dir, parent_ids)

        # Detect create vs update
        action = "UPDATE" if file_path.exists() else "CREATE"
        if action == "CREATE":
            stats["created"] += 1
        else:
            stats["updated"] += 1

        print(f"    {action}: {title} → {file_path.relative_to(space_dir)}")

        if not dry_run:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

        # Track state
        new_state[page_id] = {
            "version": version,
            "title": title,
            "file_path": str(file_path),
            "attachments": new_attachment_state,
            "synced_at": datetime.now().isoformat(),
        }

    # Save sync state into the space directory
    if not dry_run:
        save_sync_state(space_dir, new_state)

    return stats


def sync(
    dry_run: bool = False,
    push: bool = True,
    keep_local: bool = False,
    force: bool = False,
    force_all: bool = False,
    space: str = None,
):
    """Run the Confluence → Markdown sync for all configured spaces."""
    print("=" * 60)
    print("Confluence → Markdown Sync")
    print("=" * 60)

    space_keys = [space.upper()] if space else Config.CONFLUENCE_SPACE_KEYS
    if not space_keys:
        raise ValueError(
            "Set CONFLUENCE_SPACE_KEY in your .env (comma-separated for multiple spaces)"
        )

    print(f"\nSpaces to sync: {', '.join(space_keys)}")

    if force_all:
        print(
            "  (FORCE ALL — re-converting all pages and re-downloading all attachments)"
        )
    elif force:
        print("  (FORCE — ignoring sync state, re-converting all pages)")

    # Step 1: Pull (clone) the knowledge base repo from GitLab
    if not dry_run and push:
        pull_kb_repo()

    # Cleanup: remove legacy root-level attachments/ dir (migrated to per-space)
    legacy_attachments = get_clone_dir() / "attachments"
    if legacy_attachments.exists() and legacy_attachments.is_dir():
        import shutil

        shutil.rmtree(legacy_attachments)
        print("  Removed legacy root-level attachments/ directory (now per-space)")

    if dry_run:
        print("  (DRY RUN — no files will be written)\n")

    # Step 2: Sync each space
    total_stats = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0}

    for space_key in space_keys:
        print(f"\n{'─' * 60}")
        print(f"Syncing space: {space_key}")
        print(f"{'─' * 60}")

        stats = sync_space(space_key, dry_run=dry_run, force=force, force_all=force_all)

        for key in total_stats:
            total_stats[key] += stats[key]

        print(
            f"  Space {space_key}: +{stats['created']} created, ~{stats['updated']} updated, "
            f"={stats['unchanged']} unchanged, -{stats['skipped']} skipped"
        )

    # Summary
    print(f"\n{'═' * 60}")
    print("All spaces synced:")
    print(f"  Spaces:    {len(space_keys)}")
    print(f"  Created:   {total_stats['created']}")
    print(f"  Updated:   {total_stats['updated']}")
    print(f"  Unchanged: {total_stats['unchanged']}")
    print(f"  Skipped:   {total_stats['skipped']}")
    print(f"{'═' * 60}")

    # Step 3: Generate KB repo README
    if not dry_run:
        generate_kb_readme(space_keys, total_stats)

    # Step 4: Commit and push to GitLab (single commit for all spaces)
    if (
        not dry_run
        and push
        and (total_stats["created"] > 0 or total_stats["updated"] > 0)
    ):
        push_kb_repo(total_stats)
    elif not push:
        print("\n  Git push skipped (--no-push)")

    # Step 5: Cleanup
    if not dry_run and push and not keep_local:
        cleanup_kb_repo()
    elif keep_local:
        print(f"\n  Local clone retained at: {Config.OUTPUT_DIR}")


def main():
    parser = argparse.ArgumentParser(description="Sync Confluence pages to Markdown")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without writing files",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Sync files locally but skip pushing to the knowledge base git repo",
    )
    parser.add_argument(
        "--keep-local",
        action="store_true",
        help="Keep the cloned knowledge base repo on disk after pushing (skip cleanup)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-convert all pages regardless of sync state (use after converter changes)",
    )
    parser.add_argument(
        "--force-all",
        action="store_true",
        help="Re-convert all pages AND re-download all attachments (full rebuild)",
    )
    parser.add_argument(
        "--space",
        type=str,
        help="Sync only this space key (overrides .env list, useful for testing)",
    )
    args = parser.parse_args()
    sync(
        dry_run=args.dry_run,
        push=not args.no_push,
        keep_local=args.keep_local,
        force=args.force,
        force_all=args.force_all,
        space=args.space,
    )


if __name__ == "__main__":
    main()
