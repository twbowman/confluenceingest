"""
Ingestion pipeline: chunk Markdown docs, embed via Ollama, store in ChromaDB.

Usage:
    python ingest.py              # Ingest all documents
    python ingest.py --reset      # Clear the vector store and re-ingest everything
"""

import argparse
import hashlib
import shutil

import chromadb
import ollama

from config import Config
from chunker import chunk_knowledge_base


def get_chroma_client() -> chromadb.ClientAPI:
    """Create a persistent ChromaDB client."""
    return chromadb.PersistentClient(path=Config.CHROMA_PERSIST_DIR)


def get_or_create_collection(client: chromadb.ClientAPI) -> chromadb.Collection:
    """Get or create the knowledge base collection."""
    return client.get_or_create_collection(
        name=Config.CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def generate_chunk_id(chunk: dict) -> str:
    """Generate a stable ID for a chunk based on file path and chunk index."""
    key = f"{chunk['metadata']['file_path']}::{chunk['metadata']['chunk_index']}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def embed_text(text: str) -> list[float]:
    """Generate an embedding for a text string using Ollama."""
    response = ollama.embed(
        model=Config.OLLAMA_EMBED_MODEL,
        input=text,
    )
    return response["embeddings"][0]


def ingest(reset: bool = False):
    """Run the full ingestion pipeline."""
    print("=" * 60)
    print("RAG POC — Ingestion Pipeline")
    print("=" * 60)
    print(f"  Knowledge base: {Config.KB_LOCAL_DIR}")
    print(f"  Embed model:    {Config.OLLAMA_EMBED_MODEL}")
    print(f"  Vector store:   {Config.CHROMA_PERSIST_DIR}")
    print()

    # Reset if requested
    if reset:
        print("  Resetting vector store...")
        shutil.rmtree(Config.CHROMA_PERSIST_DIR, ignore_errors=True)

    # Set up ChromaDB
    client = get_chroma_client()
    collection = get_or_create_collection(client)

    existing_count = collection.count()
    print(f"  Existing vectors in store: {existing_count}")
    print()

    # Chunk all documents
    print("Chunking documents...")
    chunks = list(chunk_knowledge_base(Config.KB_LOCAL_DIR))
    print(f"  Total chunks: {len(chunks)}")
    print()

    if not chunks:
        print("No chunks to ingest. Check your KNOWLEDGE_BASE_DIR path.")
        return

    # Embed and store
    print("Embedding and storing chunks...")
    batch_size = 50
    stored = 0

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]

        ids = [generate_chunk_id(c) for c in batch]
        documents = [c["text"] for c in batch]
        metadatas = [c["metadata"] for c in batch]

        # Embed the batch
        embeddings = []
        for doc in documents:
            embedding = embed_text(doc)
            embeddings.append(embedding)

        # Upsert into ChromaDB
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        stored += len(batch)
        print(f"  Stored {stored}/{len(chunks)} chunks", end="\r")

    print(f"\n\nDone. {stored} chunks embedded and stored.")
    print(f"  Collection now has {collection.count()} vectors.")


def main():
    parser = argparse.ArgumentParser(
        description="Ingest knowledge base into vector store"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear the vector store and re-ingest from scratch",
    )
    args = parser.parse_args()
    ingest(reset=args.reset)


if __name__ == "__main__":
    main()
