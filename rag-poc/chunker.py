"""
Chunk Markdown documents by headings for embedding.

Splits each Markdown file into chunks at heading boundaries (## and ###),
preserving the document title and frontmatter metadata with each chunk.
"""

import re
from pathlib import Path
from typing import Generator

import frontmatter


def parse_document(file_path: Path) -> dict:
    """Parse a Markdown file into frontmatter metadata and body content."""
    text = file_path.read_text(encoding="utf-8")
    post = frontmatter.loads(text)

    return {
        "metadata": dict(post.metadata),
        "body": post.content,
        "file_path": str(file_path),
    }


def split_by_headings(body: str, max_chunk_tokens: int = 512) -> list[str]:
    """
    Split Markdown body into chunks at heading boundaries.

    If a section exceeds max_chunk_tokens (rough estimate: 1 token ≈ 4 chars),
    it gets split further at paragraph boundaries.
    """
    # Split on ## or ### headings, keeping the heading with its section
    sections = re.split(r"(?=^#{2,3}\s)", body, flags=re.MULTILINE)

    chunks = []
    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Rough token estimate (1 token ≈ 4 characters)
        estimated_tokens = len(section) // 4

        if estimated_tokens <= max_chunk_tokens:
            chunks.append(section)
        else:
            # Split large sections by paragraphs
            paragraphs = section.split("\n\n")
            current_chunk = ""

            for para in paragraphs:
                if len((current_chunk + "\n\n" + para)) // 4 > max_chunk_tokens and current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = para
                else:
                    current_chunk = current_chunk + "\n\n" + para if current_chunk else para

            if current_chunk.strip():
                chunks.append(current_chunk.strip())

    return chunks


def chunk_document(file_path: Path) -> list[dict]:
    """
    Parse and chunk a single Markdown document.

    Returns a list of chunk dicts, each with:
      - text: the chunk content
      - metadata: frontmatter fields + chunk index + file path
    """
    doc = parse_document(file_path)
    body = doc["body"]
    metadata = doc["metadata"]

    sections = split_by_headings(body)

    if not sections:
        # If no headings found, treat the whole body as one chunk
        sections = [body] if body.strip() else []

    chunks = []
    title = metadata.get("title", file_path.stem)

    for i, section_text in enumerate(sections):
        chunk_metadata = {
            "title": title,
            "space": metadata.get("space", ""),
            "source_url": metadata.get("source_url", ""),
            "labels": ", ".join(metadata.get("labels", [])),
            "parent": metadata.get("parent", ""),
            "file_path": doc["file_path"],
            "chunk_index": i,
        }

        # Prepend title for context in embedding
        text_for_embedding = f"# {title}\n\n{section_text}"

        chunks.append(
            {
                "text": text_for_embedding,
                "metadata": chunk_metadata,
            }
        )

    return chunks


def chunk_knowledge_base(kb_dir: str) -> Generator[dict, None, None]:
    """
    Walk the knowledge base directory and yield chunks from all Markdown files.

    Yields chunk dicts with text and metadata.
    """
    kb_path = Path(kb_dir)

    if not kb_path.exists():
        raise FileNotFoundError(f"Knowledge base directory not found: {kb_dir}")

    md_files = list(kb_path.rglob("*.md"))
    print(f"Found {len(md_files)} Markdown file(s) in {kb_dir}")

    for file_path in sorted(md_files):
        try:
            chunks = chunk_document(file_path)
            for chunk in chunks:
                yield chunk
        except Exception as e:
            print(f"  WARNING: Failed to process {file_path}: {e}")
            continue
