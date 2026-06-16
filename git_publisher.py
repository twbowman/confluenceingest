"""Publish the knowledge base directory to a separate Git repository."""

import subprocess
from pathlib import Path

from config import Config


def _run_git(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    """Run a git command in the specified directory."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed:\n{result.stderr.strip()}"
        )
    return result


def _is_git_repo(path: str) -> bool:
    """Check if the directory is already a git repository."""
    git_dir = Path(path) / ".git"
    return git_dir.exists()


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


def init_kb_repo(output_dir: str):
    """
    Initialize the knowledge base directory as a git repo connected to the
    remote KB repository. Clones if empty, or sets up remote if already exists.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if _is_git_repo(output_dir):
        # Already initialized — ensure remote is correct
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=output_dir,
            capture_output=True,
            text=True,
        )
        current_remote = result.stdout.strip()
        if current_remote != Config.KB_GIT_REPO_URL:
            _run_git(["remote", "set-url", "origin", Config.KB_GIT_REPO_URL], output_dir)
            print(f"  Updated remote to: {Config.KB_GIT_REPO_URL}")

        # Pull latest to avoid conflicts
        try:
            _run_git(["pull", "origin", Config.KB_GIT_BRANCH, "--rebase"], output_dir)
            print("  Pulled latest from remote")
        except RuntimeError:
            # May fail if remote is empty (first push) — that's fine
            pass

        return

    # Check if the output dir already has files (from a previous sync without git)
    existing_files = list(output_path.iterdir())

    if existing_files:
        # Directory has content but no git — init and connect to remote
        _run_git(["init"], output_dir)
        _run_git(["remote", "add", "origin", Config.KB_GIT_REPO_URL], output_dir)
        _run_git(
            ["config", "user.name", Config.KB_GIT_AUTHOR_NAME], output_dir
        )
        _run_git(
            ["config", "user.email", Config.KB_GIT_AUTHOR_EMAIL], output_dir
        )
        print(f"  Initialized git repo in {output_dir}")
    else:
        # Empty directory — clone the remote repo into it
        # Clone into a temp name then move contents (git clone won't clone into non-empty dir)
        parent = output_path.parent
        temp_dir = parent / ".kb-clone-temp"

        try:
            subprocess.run(
                ["git", "clone", "--branch", Config.KB_GIT_BRANCH,
                 Config.KB_GIT_REPO_URL, str(temp_dir)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            # Move .git and any existing content into output_dir
            if (temp_dir / ".git").exists():
                import shutil
                for item in temp_dir.iterdir():
                    dest = output_path / item.name
                    if dest.exists():
                        if dest.is_dir():
                            shutil.rmtree(dest)
                        else:
                            dest.unlink()
                    shutil.move(str(item), str(dest))
                temp_dir.rmdir()
                print(f"  Cloned {Config.KB_GIT_REPO_URL} into {output_dir}")
        except (RuntimeError, subprocess.TimeoutExpired):
            # Remote might be empty — just init fresh
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir)
            _run_git(["init"], output_dir)
            _run_git(["remote", "add", "origin", Config.KB_GIT_REPO_URL], output_dir)
            print(f"  Initialized new git repo in {output_dir} (remote appears empty)")

        # Set author config
        _run_git(
            ["config", "user.name", Config.KB_GIT_AUTHOR_NAME], output_dir
        )
        _run_git(
            ["config", "user.email", Config.KB_GIT_AUTHOR_EMAIL], output_dir
        )


def publish_kb(output_dir: str, stats: dict) -> bool:
    """
    Commit and push any changes in the knowledge base directory to the remote repo.

    Returns True if changes were pushed, False if there was nothing to push.
    """
    if not Config.KB_GIT_REPO_URL:
        print("\n  KB_GIT_REPO_URL not configured — skipping git publish")
        return False

    print("\nPublishing knowledge base to git...")

    # Ensure repo is initialized
    init_kb_repo(output_dir)

    # Stage all changes
    _run_git(["add", "-A"], output_dir)

    # Check if there's anything to commit
    if not _has_changes(output_dir):
        print("  No changes to publish")
        return False

    # Build commit message from sync stats
    commit_message = (
        f"Sync from Confluence: "
        f"+{stats.get('created', 0)} created, "
        f"~{stats.get('updated', 0)} updated"
    )

    _run_git(["commit", "-m", commit_message], output_dir)
    print(f"  Committed: {commit_message}")

    # Push to remote
    _run_git(["push", "-u", "origin", Config.KB_GIT_BRANCH], output_dir)
    print(f"  Pushed to {Config.KB_GIT_REPO_URL} ({Config.KB_GIT_BRANCH})")

    return True
