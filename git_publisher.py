"""
Manage the knowledge base Git repository lifecycle.

Flow:
1. pull_kb_repo()  — Clone the remote KB repo to a local working directory
2. (sync writes files into that directory)
3. push_kb_repo()  — Commit and push changes back to remote
4. cleanup_kb_repo() — Remove the local clone (optional)
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


def _run_git(args: list[str], cwd: str, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run a git command in the specified directory."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
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


def get_clone_dir() -> Path:
    """Get the path where the KB repo will be cloned."""
    return Path(Config.OUTPUT_DIR)


def get_space_dir(space_key: str) -> Path:
    """Get the space-specific subdirectory within the KB repo."""
    return get_clone_dir() / space_key.lower()


def pull_kb_repo() -> Path:
    """
    Clone the remote knowledge base repo to the local working directory.

    This should be called FIRST, before fetching from Confluence, so that
    the .sync-state.json from the repo is available for incremental detection.

    Returns the path to the cloned repo directory.
    """
    clone_dir = get_clone_dir()

    if not Config.KB_GIT_REPO_URL:
        # No git repo configured — just ensure the output dir exists
        clone_dir.mkdir(parents=True, exist_ok=True)
        return clone_dir

    print("\nPulling knowledge base repo...")

    # Clean up any existing clone
    if clone_dir.exists():
        shutil.rmtree(clone_dir)

    clone_dir.parent.mkdir(parents=True, exist_ok=True)

    # Try cloning with the configured branch
    try:
        _run_git(
            ["clone", "--branch", Config.KB_GIT_BRANCH,
             Config.KB_GIT_REPO_URL, str(clone_dir)],
            cwd=str(clone_dir.parent),
        )
        print(f"  Cloned {Config.KB_GIT_REPO_URL} ({Config.KB_GIT_BRANCH})")
    except RuntimeError:
        # Branch might not exist — try default branch
        try:
            _run_git(
                ["clone", Config.KB_GIT_REPO_URL, str(clone_dir)],
                cwd=str(clone_dir.parent),
            )
            print(f"  Cloned {Config.KB_GIT_REPO_URL} (default branch)")
        except RuntimeError:
            # Truly empty repo — init fresh
            clone_dir.mkdir(parents=True, exist_ok=True)
            _run_git(["init"], str(clone_dir))
            _run_git(["remote", "add", "origin", Config.KB_GIT_REPO_URL], str(clone_dir))
            _run_git(["checkout", "-b", Config.KB_GIT_BRANCH], str(clone_dir))
            print(f"  Initialized new repo (remote appears empty)")

    # Set git author config
    _run_git(["config", "user.name", Config.KB_GIT_AUTHOR_NAME], str(clone_dir))
    _run_git(["config", "user.email", Config.KB_GIT_AUTHOR_EMAIL], str(clone_dir))

    return clone_dir


def push_kb_repo(stats: dict) -> bool:
    """
    Commit and push any changes in the knowledge base repo.

    Should be called AFTER sync has written files into the cloned directory.

    Returns True if changes were pushed, False if nothing to push.
    """
    clone_dir = get_clone_dir()

    if not Config.KB_GIT_REPO_URL:
        print("\n  KB_GIT_REPO_URL not configured — skipping git push")
        return False

    print("\nPushing knowledge base to remote...")

    # Stage all changes
    _run_git(["add", "-A"], str(clone_dir))

    # Check if there's anything to commit
    if not _has_changes(str(clone_dir)):
        print("  No changes to push — remote is already up to date")
        return False

    # Commit
    commit_message = (
        f"Sync from Confluence: "
        f"+{stats.get('created', 0)} created, "
        f"~{stats.get('updated', 0)} updated"
    )
    _run_git(["commit", "-m", commit_message], str(clone_dir))
    print(f"  Committed: {commit_message}")

    # Push — use increased timeout and buffer for large initial syncs
    # Set a larger HTTP post buffer (500MB) to handle large pushes
    _run_git(["config", "http.postBuffer", "524288000"], str(clone_dir))

    max_retries = 3
    push_timeout = 600  # 10 minutes for large pushes

    for attempt in range(1, max_retries + 1):
        try:
            _run_git(
                ["push", "-u", "origin", Config.KB_GIT_BRANCH],
                str(clone_dir),
                timeout=push_timeout,
            )
            print(f"  Pushed to {Config.KB_GIT_REPO_URL} ({Config.KB_GIT_BRANCH})")
            break
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            error_msg = str(e)
            is_timeout = isinstance(e, subprocess.TimeoutExpired) or "timeout" in error_msg.lower()
            is_size_issue = any(
                word in error_msg.lower()
                for word in ["large", "size", "exceeded", "pack"]
            )

            if attempt < max_retries and is_timeout:
                print(
                    f"  Push attempt {attempt}/{max_retries} timed out — retrying "
                    f"(timeout: {push_timeout}s)..."
                )
                push_timeout += 300  # Add 5 more minutes each retry
                continue
            elif is_size_issue:
                print(
                    f"  WARNING: Push failed — likely due to large file size.\n"
                    f"  Check for attachments exceeding the remote's file size limit.\n"
                    f"  Consider increasing ATTACHMENT_MAX_SIZE_MB or using Git LFS.\n"
                    f"  Error: {error_msg}"
                )
                break
            elif is_timeout:
                print(
                    f"  WARNING: Push timed out after {max_retries} attempts.\n"
                    f"  The initial sync may be too large for a single push.\n"
                    f"  Try running with fewer spaces or pushing manually:\n"
                    f"    cd {clone_dir} && git push -u origin {Config.KB_GIT_BRANCH}"
                )
                break
            else:
                raise

    return True


def cleanup_kb_repo():
    """Remove the local clone of the knowledge base repo."""
    clone_dir = get_clone_dir()
    if clone_dir.exists():
        shutil.rmtree(clone_dir)
        print("  Cleaned up local clone")
