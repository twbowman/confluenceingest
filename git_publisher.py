"""
Publish the knowledge base to a remote Git repository via SSH.

Flow:
1. Clone the remote knowledge base repo to a temporary directory
2. Copy the synced Markdown files into the clone
3. Commit and push changes
4. Clean up the temporary clone (unless --keep-local is set)
"""

import os
import shutil
import subprocess
from pathlib import Path

from config import Config


def _git_env() -> dict:
    """Build environment variables for git commands, including SSH key if configured."""
    env = os.environ.copy()
    if Config.KB_GIT_SSH_KEY:
        env["GIT_SSH_COMMAND"] = (
            f"ssh -i {Config.KB_GIT_SSH_KEY} -o StrictHostKeyChecking=accept-new"
        )
    return env


def _run_git(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    """Run a git command in the specified directory."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        env=_git_env(),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed:\n{result.stderr.strip()}"
        )
    return result


def _has_changes(cwd: str) -> bool:
    """Check if there are any uncommitted changes (staged or unstaged)."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return bool(result.stdout.strip())


def _clone_kb_repo(clone_dir: Path) -> bool:
    """
    Clone the remote knowledge base repo into clone_dir.

    Returns True if cloned successfully, False if remote is empty/new.
    """
    if clone_dir.exists():
        shutil.rmtree(clone_dir)

    try:
        _run_git(
            ["clone", "--branch", Config.KB_GIT_BRANCH,
             Config.KB_GIT_REPO_URL, str(clone_dir)],
            cwd=str(clone_dir.parent),
        )
        print(f"  Cloned {Config.KB_GIT_REPO_URL} ({Config.KB_GIT_BRANCH})")
        return True
    except RuntimeError:
        # Branch or repo might not exist yet — clone without branch, or init fresh
        try:
            _run_git(
                ["clone", Config.KB_GIT_REPO_URL, str(clone_dir)],
                cwd=str(clone_dir.parent),
            )
            print(f"  Cloned {Config.KB_GIT_REPO_URL} (default branch)")
            return True
        except RuntimeError:
            # Truly empty repo — init fresh and set remote
            clone_dir.mkdir(parents=True, exist_ok=True)
            _run_git(["init"], str(clone_dir))
            _run_git(["remote", "add", "origin", Config.KB_GIT_REPO_URL], str(clone_dir))
            _run_git(["checkout", "-b", Config.KB_GIT_BRANCH], str(clone_dir))
            print(f"  Initialized new repo (remote appears empty)")
            return False


def _copy_files_to_clone(source_dir: str, clone_dir: Path):
    """
    Copy synced Markdown files from the output directory into the cloned repo.

    Replaces all content in the clone (except .git) with the current sync output.
    This ensures deleted pages are also removed from the repo.
    """
    # Remove all existing content in clone (except .git)
    for item in clone_dir.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    # Copy all files from source into clone
    source_path = Path(source_dir)
    for item in source_path.iterdir():
        dest = clone_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    print(f"  Copied files from {source_dir} into clone")


def publish_kb(output_dir: str, stats: dict, keep_local: bool = False) -> bool:
    """
    Clone the remote KB repo, copy in synced files, commit, push, and clean up.

    Args:
        output_dir: Path to the local directory containing synced Markdown files.
        stats: Dict with sync stats (created, updated counts) for the commit message.
        keep_local: If True, keep the cloned repo on disk after pushing.

    Returns True if changes were pushed, False if there was nothing to push.
    """
    if not Config.KB_GIT_REPO_URL:
        print("\n  KB_GIT_REPO_URL not configured — skipping git publish")
        return False

    print("\nPublishing knowledge base to git...")

    # Determine clone location
    clone_dir = Path(output_dir).parent / ".kb-repo"

    # Step 1: Clone the remote repo
    print("  Pulling remote knowledge base repo...")
    _clone_kb_repo(clone_dir)

    # Step 2: Set git author config
    _run_git(["config", "user.name", Config.KB_GIT_AUTHOR_NAME], str(clone_dir))
    _run_git(["config", "user.email", Config.KB_GIT_AUTHOR_EMAIL], str(clone_dir))

    # Step 3: Copy synced files into the clone
    _copy_files_to_clone(output_dir, clone_dir)

    # Step 4: Stage all changes
    _run_git(["add", "-A"], str(clone_dir))

    # Step 5: Check if there's anything to commit
    if not _has_changes(str(clone_dir)):
        print("  No changes to publish — remote is already up to date")
        if not keep_local:
            shutil.rmtree(clone_dir)
            print("  Cleaned up local clone")
        return False

    # Step 6: Commit
    commit_message = (
        f"Sync from Confluence: "
        f"+{stats.get('created', 0)} created, "
        f"~{stats.get('updated', 0)} updated"
    )
    _run_git(["commit", "-m", commit_message], str(clone_dir))
    print(f"  Committed: {commit_message}")

    # Step 7: Push
    _run_git(["push", "-u", "origin", Config.KB_GIT_BRANCH], str(clone_dir))
    print(f"  Pushed to {Config.KB_GIT_REPO_URL} ({Config.KB_GIT_BRANCH})")

    # Step 8: Cleanup
    if keep_local:
        print(f"  Local clone retained at: {clone_dir}")
    else:
        shutil.rmtree(clone_dir)
        print("  Cleaned up local clone")

    return True
