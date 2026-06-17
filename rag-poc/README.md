# RAG POC — Local Knowledge Base Q&A

A fully local Retrieval-Augmented Generation system that answers questions from your Confluence-synced knowledge base. No external API calls, no token costs.

## Stack

- **LLM:** Ollama (Llama 3.1 8B)
- **Embeddings:** Ollama (nomic-embed-text)
- **Vector Store:** ChromaDB (file-based, persistent)
- **Data Source:** Markdown files from the Confluence sync pipeline

## Prerequisites

1. **Ollama** installed and running:

```bash
# macOS
brew install ollama
ollama serve

# Pull the models
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

2. **Python 3.10+** with dependencies:

```bash
pip install -r requirements.txt
```

3. **SSH key** with read access to the knowledge base GitLab repo.

## Usage

### 1. Pull the knowledge base from GitLab

Clones (or updates) the Markdown repo using your SSH key:

```bash
python kb_pull.py
```

To force a fresh clone:

```bash
python kb_pull.py --fresh
```

### 2. Ingest into the vector store

Chunks all Markdown files, embeds them, and stores vectors in ChromaDB:

```bash
python ingest.py
```

To re-ingest from scratch (clears the vector store first):

```bash
python ingest.py --reset
```

### 3. Query

Single question:

```bash
python query.py "How do we deploy to production?"
```

Interactive chat mode:

```bash
python query.py --interactive
```

With verbose output (shows retrieved chunks and similarity scores):

```bash
python query.py -v "What is our incident response process?"
```

## Configuration

Copy `.env.example` to `.env` and adjust:

| Variable | Default | Description |
|----------|---------|-------------|
| `KB_GIT_REPO_URL` | — | SSH URL of the knowledge base GitLab repo |
| `KB_GIT_BRANCH` | `master` | Branch to pull |
| `KB_GIT_SSH_KEY` | `~/.ssh/id_rsa` | Path to SSH private key for GitLab |
| `KB_LOCAL_DIR` | `./knowledge-base` | Where to clone the repo locally |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_CHAT_MODEL` | `llama3.1:8b` | Model for answer generation |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Model for embeddings |
| `CHROMA_PERSIST_DIR` | `./chroma_db` | Where ChromaDB stores vectors |
| `CHROMA_COLLECTION_NAME` | `knowledge_base` | ChromaDB collection name |

## How it works

```
┌─────────────────────────────────────────────────────┐
│                  INGESTION                           │
│                                                     │
│  Markdown files → Chunker → Ollama Embed → ChromaDB │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                    QUERY                             │
│                                                     │
│  Question → Ollama Embed → ChromaDB search          │
│          → Top-K chunks + Question → Ollama Chat    │
│          → Answer with sources                      │
└─────────────────────────────────────────────────────┘
```

## Hardware Requirements

- **Minimum:** 16 GB RAM (8B model, quantized)
- **Recommended:** 32 GB RAM or GPU with 8+ GB VRAM
- Expect 2-5 second response times on CPU, <1 second with GPU
