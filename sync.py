"""
Confluence → Markdown sync tool.

Exports Confluence pages to a tool-agnostic Markdown knowledge base with
YAML frontmatter metadata. Organizes files in a directory structure that
mirrors the Confluence page hierarchy, namespaced by space key.

Flow:
    1. Pull (clone) the knowledge base Git repo from GitLab
    2. Fetch pages from Confluence
    3. Convert and write changed pages into <repo>/<space_key>/
    4. Commit and push changes back to GitLab
    5. Clean up the local clone (unless --keep-local)

Usage:
    python sync.py             # Full sync of configured space
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
from confluence_loader import fetch_pages
from converter import convert_page
from git_publisher import pull_kb_repo, push_kb_repo, cleanup_kb_repo, get_space_dir


def build_file_path(page: dict, space_dir: str) -> Path:
    """
    Build the output file path preserving page hierarchy as directories.

    Example: Engineering > Infrastructure > Deployment →
             knowledge-base/eng/engineering/infrastructure/deployment.md
    """
    ancestors = [ancestor["title"] for ancestor in page.get("ancestors", [])]
    title = page["title"]

    # Build path segments from ancestors + page title
    segments = ancestors + [title]

    # Sanitize each segment for filesystem use
    safe_segments = []
    for segment in segments:
        safe = re.sub(r'[^\w\s-]', '', segment).strip()
        safe = re.sub(r'[\s]+', '-', safe).lower()
        if safe:
            safe_segments.append(safe)

    if not safe_segments:
        safe_segments = [page["id"]]

    # Final segment is the filename
    filename = safe_segments.pop() + ".md"
    dir_path = Path(space_dir).joinpath(*safe_segments) if safe_segments else Path(space_dir)

    return dir_path / filename


def load_sync_state(space_dir: str) -> dict:
    """Load the previous sync state to enable incremental updates."""
    state_file = Path(space_dir) / ".sync-state.json"
    if state_file.exists():
        return json.loads(state_file.read_text(encoding="utf-8"))
    return {}


def save_sync_state(space_dir: str, state: dict):
    """Persist sync state for future incremental runs."""
    state_file = Path(space_dir) / ".sync-state.json"
    state_file.write_text(
        json.dumps(state, indent=2, default=str), encoding="utf-8"
    )


def sync(dry_run: bool = False, push: bool = True, keep_local: bool = False):
    """Run the Confluence → Markdown sync."""
    print("=" * 60)
    print("Confluence → Markdown Sync")
    print("=" * 60)

    # Step 1: Pull (clone) the knowledge base repo from GitLab
    # This gives us the .sync-state.json for incremental change detection
    if not dry_run and push:
        pull_kb_repo()

    # Resolve the space-specific directory within the KB repo
    space_dir = str(get_space_dir())
    Path(space_dir).mkdir(parents=True, exist_ok=True)

    # Step 2: Load sync state from the cloned repo (or empty if first run)
    previous_state = load_sync_state(space_dir)

    # Step 3: Fetch pages from Confluence
    print("\nFetching pages from Confluence...")
    pages = fetch_pages()
    print(f"  Found {len(pages)} page(s)")

    if not pages:
        print("Nothing to sync.")
        if not dry_run and push and not keep_local:
            cleanup_kb_repo()
        return

    space_key = Config.CONFLUENCE_SPACE_KEY
    new_state = {}
    stats = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0}

    print(f"\nSyncing space '{space_key}' to: {space_dir}/")
    if dry_run:
        print("  (DRY RUN — no files will be written)\n")
    else:
        print()

    # Step 4: Convert and write changed pages
    for page in pages:
        page_id = page["id"]
        title = page["title"]
        version = page.get("version", {}).get("number", 0)

        # Check if page has changed since last sync
        prev = previous_state.get(page_id, {})
        if prev.get("version") == version:
            stats["unchanged"] += 1
            new_state[page_id] = prev
            continue

        # Convert to Markdown
        content = convert_page(page, space_key)
        if not content:
            print(f"  SKIP (no content): {title}")
            stats["skipped"] += 1
            continue

        # Determine output path within the space directory
        file_path = build_file_path(page, space_dir)

        # Detect create vs update
        action = "UPDATE" if file_path.exists() else "CREATE"
        if action == "CREATE":
            stats["created"] += 1
        else:
            stats["updated"] += 1

        print(f"  {action}: {title} → {file_path.relative_to(space_dir)}")

        if not dry_run:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

        # Track state
        new_state[page_id] = {
            "version": version,
            "title": title,
            "file_path": str(file_path),
            "synced_at": datetime.now().isoformat(),
        }

    # Save sync state into the space directory
    if not dry_run:
        save_sync_state(space_dir, new_state)

    # Summary
    print(f"\n{'─' * 60}")
    print("Sync complete:")
    print(f"  Space:     {space_key}")
    print(f"  Created:   {stats['created']}")
    print(f"  Updated:   {stats['updated']}")
    print(f"  Unchanged: {stats['unchanged']}")
    print(f"  Skipped:   {stats['skipped']}")
    print(f"{'─' * 60}")

    # Step 5: Commit and push to GitLab
    if not dry_run and push and (stats["created"] > 0 or stats["updated"] > 0):
        push_kb_repo(stats)
    elif not push:
        print("\n  Git push skipped (--no-push)")

    # Step 6: Cleanup
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
    args = parser.parse_args()
    sync(dry_run=args.dry_run, push=not args.no_push, keep_local=args.keep_local)


if __name__ == "__main__":
    main()
