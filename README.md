# Confluence → Markdown Knowledge Base Sync

<!-- Test change to verify GitHub push -->

Exports Confluence pages to a tool-agnostic Markdown knowledge base. Pages are converted to clean Markdown with YAML frontmatter metadata, organized in a directory structure that mirrors the Confluence page hierarchy.

The exported Markdown corpus is designed to be consumed by any downstream tool — RAG pipelines, static site generators, search indexes, or future platforms — without coupling to Confluence.

## Architecture

```
Confluence Space
    │
    ▼
┌──────────────────────────┐
│  sync.py                 │
│  • Fetches pages via API │
│  • Converts to Markdown  │
│  • Preserves hierarchy   │
│  • Tracks changes        │
└──────────────────────────┘
    │
    ▼
knowledge-base/
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
```

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in:
- `CONFLUENCE_URL` — your instance base URL (e.g., `https://wiki.mycompany.com`)
- `CONFLUENCE_PAT` — Personal Access Token (generate in Confluence under Profile → Personal Access Tokens)
- `CONFLUENCE_SPACE_KEY` — space to export (e.g., `ENG`)
- `OUTPUT_DIR` — where to write the Markdown files (default: `./knowledge-base`)

### 3. Run the sync

```bash
# Full sync — exports pages and pushes to knowledge base repo
python sync.py

# Preview without writing files or pushing
python sync.py --dry-run

# Sync locally but don't push to git
python sync.py --no-push
```

## Output Format

Each page becomes a Markdown file with YAML frontmatter:

```markdown
---
id: "12345"
title: Deployment Runbook
space: ENG
source_url: https://your-org.atlassian.net/wiki/spaces/ENG/pages/12345
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

The tool tracks page versions in `.sync-state.json`. On subsequent runs, only pages that have changed in Confluence are re-exported. This keeps sync fast for large spaces.

## Git Publishing

After syncing, the tool automatically commits and pushes changes to a separate Git repository configured via `KB_GIT_REPO_URL`. This gives you:

- Full version history of your knowledge base
- Diffs showing what changed between syncs
- A clean separation between the sync tooling repo and the knowledge base content repo
- A git-native data source for downstream consumers (RAG, docs sites, search)

On first run, the tool initializes the output directory as a git repo connected to the remote. On subsequent runs, it pulls latest, commits new changes, and pushes.

Set `--no-push` to sync locally without publishing, or omit `KB_GIT_REPO_URL` from your `.env` to disable git publishing entirely.

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
