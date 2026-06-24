"""
Pull the knowledge base Git repo from GitLab using SSH key authentication.

Clones (or pulls latest) the Markdown knowledge base so the ingestion
pipeline has fresh data to index.

Usage:
    python kb_pull.py          # Clone or pull latest
    python kb_pull.py --fresh  # Remove existing clone and re-clone
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from config import Config


def _git_env() -> dict:
    """Build environment variables for git commands with SSH key."""
    env = os.environ.copy()
    if Config.KB_GIT_SSH_KEY:
        ssh_key_path = os.path.expanduser(Config.KB_GIT_SSH_KEY)
        env["GIT_SSH_COMMAND"] = f"ssh -i {ssh_key_path} -o StrictHostKeyChecking=accept-new"
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
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result


def pull_knowledge_base(fresh: bool = False) -> Path:
    """
    Clone or update the knowledge base repo.

    If the repo already exists locally, pulls latest changes.
    If --fresh is specified, removes the existing clone and re-clones.

    Returns the path to the local knowledge base directory.
    """
    local_dir = Path(Config.KB_LOCAL_DIR)

    if not Config.KB_GIT_REPO_URL:
        raise ValueError("KB_GIT_REPO_URL not configured. Set it in your .env file.")

    print("=" * 60)
    print("Knowledge Base — Git Pull")
    print("=" * 60)
    print(f"  Repo:   {Config.KB_GIT_REPO_URL}")
    print(f"  Branch: {Config.KB_GIT_BRANCH}")
    print(f"  Local:  {local_dir.resolve()}")
    print()

    # Fresh clone requested — remove existing
    if fresh and local_dir.exists():
        print("  Removing existing clone (--fresh)...")
        shutil.rmtree(local_dir)

    # If the repo already exists locally, just pull
    if local_dir.exists() and (local_dir / ".git").exists():
        print("  Pulling latest changes...")
        _run_git(["fetch", "origin"], str(local_dir))
        _run_git(["reset", "--hard", f"origin/{Config.KB_GIT_BRANCH}"], str(local_dir))
        print("  Up to date.")
    else:
        # Clone fresh
        print("  Cloning repository...")
        local_dir.parent.mkdir(parents=True, exist_ok=True)

        _run_git(
            [
                "clone",
                "--branch",
                Config.KB_GIT_BRANCH,
                Config.KB_GIT_REPO_URL,
                str(local_dir),
            ],
            cwd=str(local_dir.parent),
        )
        print("  Clone complete.")

    # Count files
    md_files = list(local_dir.rglob("*.md"))
    print(f"  Markdown files found: {len(md_files)}")

    return local_dir


def main():
    parser = argparse.ArgumentParser(description="Pull the knowledge base repo from GitLab")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Remove existing clone and re-clone from scratch",
    )
    args = parser.parse_args()

    pull_knowledge_base(fresh=args.fresh)


if __name__ == "__main__":
    main()
