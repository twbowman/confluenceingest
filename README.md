# Confluence → Markdown Knowledge Base Sync

Exports Confluence pages to a tool-agnostic Markdown knowledge base and publishes it to a separate Git repository (GitLab via SSH). Pages are converted to clean Markdown with YAML frontmatter metadata, organized in a directory structure that mirrors the Confluence page hierarchy.

The exported Markdown corpus is designed to be consumed by any downstream tool — RAG pipelines, static site generators, search indexes, or future platforms — without coupling to Confluence.

## Architecture

```
Confluence Space (wiki.mycompany.com)
    │
    ▼
┌──────────────────────────────────┐
│  sync.py                         │
│  • Fetches pages via REST API    │
│  • Converts to Markdown          │
│  • Preserves page hierarchy      │
│  • Tracks changes incrementally  │
└──────────────────────────────────┘
    │
    ▼
knowledge-base/ (local working directory)
├── engineering/
│   ├── infrastructure/
│   │   ├── deployment-runbook.md
│   │   └── monitoring-setup.md
│   └── onboarding/
│       └── new-engineer-guide.md
├── product/
│   └── feature-specs/
│       └── search-v2.md
└── .sync-state.json
    │
    ▼
┌──────────────────────────────────┐
│  git_publisher.py                │
│  • Clones remote KB repo (SSH)   │
│  • Copies synced files into it   │
│  • Commits and pushes            │
│  • Cleans up local clone         │
└──────────────────────────────────┘
    │
    ▼
GitLab: git@gitlab.mycompany.com:your-org/knowledge-base.git
```

## Setup

### 1. Install uv (recommended) and set up environment

[uv](https://docs.astral.sh/uv/) handles virtual environments and package installation in a single, fast tool.

```bash
# Install uv (if you don't have it)
brew install uv

# Create and activate a virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt
```

<details>
<summary>Alternative: pip + venv</summary>

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
</details>

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in:

**Confluence:**
- `CONFLUENCE_URL` — your instance base URL (e.g., `https://wiki.mycompany.com`)
- `CONFLUENCE_PAT` — Personal Access Token (generate in Confluence under Profile → Personal Access Tokens)
- `CONFLUENCE_SPACE_KEY` — space to export (e.g., `ENG`)

**Output:**
- `OUTPUT_DIR` — local working directory for synced Markdown (default: `./knowledge-base`)

**Knowledge Base Git Repo (GitLab):**
- `KB_GIT_REPO_URL` — SSH URL of the knowledge base repo (e.g., `git@gitlab.mycompany.com:your-org/knowledge-base.git`)
- `KB_GIT_SSH_KEY` — path to the SSH private key for authentication (e.g., `~/.ssh/id_rsa`)
- `KB_GIT_BRANCH` — branch to push to (default: `main`)
- `KB_GIT_AUTHOR_NAME` — git commit author name (default: `confluence-sync`)
- `KB_GIT_AUTHOR_EMAIL` — git commit author email (default: `confluence-sync@mycompany.com`)

### 3. Run the sync

```bash
# Full sync — export pages, push to GitLab, clean up local clone
python sync.py

# Preview what would be synced (no files written, no git operations)
python sync.py --dry-run

# Sync locally but don't push to git
python sync.py --no-push

# Push to git but keep the local clone on disk (for inspection/debugging)
python sync.py --keep-local

# Force re-convert all pages (ignores sync state — use after converter changes)
python sync.py --force

# Force re-convert all pages AND re-download all attachments (full rebuild)
python sync.py --force-all
```

## How It Works

1. **Fetch** — Pulls pages from Confluence via REST API using a Personal Access Token
2. **Convert** — Transforms Confluence storage format (XHTML + macros) to clean Markdown with YAML frontmatter
3. **Write** — Saves Markdown files locally, organized by page hierarchy
4. **Publish** — Clones the remote KB repo via SSH, replaces content with the latest sync, commits, and pushes
5. **Cleanup** — Removes the temporary local clone (unless `--keep-local` is set)

The publish step clones fresh each run, so the machine running this tool stays stateless. No persistent local repo is required.

## Output Format

Each page becomes a Markdown file with YAML frontmatter:

```markdown
---
id: "12345"
title: Deployment Runbook
space: ENG
source_url: https://wiki.mycompany.com/pages/12345
last_modified: "2026-05-20T14:30:00Z"
last_author: Jane Doe
version: 7
labels:
  - deployment
  - runbook
  - production
breadcrumb:
  - Engineering
  - Infrastructure
parent: Infrastructure
---

# Deployment Runbook

## Pre-deployment Checklist

...
```

## Incremental Sync

The tool tracks page versions in `.sync-state.json`. On subsequent runs, only pages that have changed in Confluence since the last sync are re-exported. This keeps sync fast for large spaces.

## Git Publishing

After syncing, the tool publishes to a separate Git repository on GitLab via SSH:

1. Clones the remote knowledge base repo into a temporary directory
2. Replaces all content (except `.git`) with the latest synced files
3. Commits with a descriptive message (e.g., `Sync from Confluence: +3 created, ~1 updated`)
4. Pushes to the configured branch
5. Removes the local clone

This gives you:
- Full version history of your knowledge base in GitLab
- Diffs showing exactly what changed between syncs
- Clean separation between the sync tooling repo (GitHub) and the content repo (GitLab)
- A git-native data source for downstream consumers

**Disable git publishing** by omitting `KB_GIT_REPO_URL` from your `.env` or using `--no-push`.

## Downstream Consumers

The exported knowledge base is intentionally simple — Markdown files in directories. Any tool that can read files can consume it:

| Consumer | How |
|----------|-----|
| RAG pipeline | Read `.md` files, parse frontmatter for metadata, chunk, embed |
| Static docs site | Point MkDocs/Docusaurus/Hugo at the directory |
| Full-text search | Index with Elasticsearch, Meilisearch, or Typesense |
| Git-based workflow | Store in a repo, get versioning, PRs, and diffs for free |

## What Gets Converted

| Confluence Feature | Markdown Output |
|--------------------|-----------------|
| Headings | ATX headings (`#`, `##`, `###`) |
| Code blocks | Fenced code blocks |
| Info/Note/Warning panels | Blockquotes with labels |
| Tables | Markdown tables |
| Lists | Bullet/numbered lists |
| Expand macros | Content flattened inline |
| TOC macro | Removed (let renderers handle it) |
| Images | Stripped (attachment support TBD) |
| Confluence-specific XML | Removed |

## Project Structure

```
├── README.md              # This file
├── requirements.txt       # Python dependencies
├── .env.example           # Configuration template
├── .gitignore
├── config.py              # Loads settings from .env
├── confluence_loader.py   # Fetches pages from Confluence REST API (PAT auth)
├── converter.py           # HTML → Markdown conversion + YAML frontmatter
├── git_publisher.py       # Clone → copy → commit → push → cleanup (SSH)
└── sync.py                # Orchestrates the full pipeline
```
