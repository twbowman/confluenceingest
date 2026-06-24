"""
Query the RAG system: retrieve relevant chunks and generate an answer via Ollama.

Usage:
    python query.py "How do we deploy services?"
    python query.py --interactive    # Chat loop
"""

import argparse

import chromadb
import ollama

from config import Config


SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on the company's internal knowledge base.

Rules:
- Answer ONLY based on the provided context. If the context doesn't contain enough information, say so.
- Cite your sources by referencing the document title and providing the source URL when available.
- Be concise and direct.
- If multiple documents are relevant, synthesize the information.
"""


def get_collection() -> chromadb.Collection:
    """Connect to the existing ChromaDB collection."""
    client = chromadb.PersistentClient(path=Config.CHROMA_PERSIST_DIR)
    return client.get_collection(name=Config.CHROMA_COLLECTION_NAME)


def retrieve(question: str, n_results: int = 5) -> list[dict]:
    """Embed the question and retrieve the most relevant chunks."""
    collection = get_collection()

    # Embed the question
    response = ollama.embed(
        model=Config.OLLAMA_EMBED_MODEL,
        input=question,
    )
    query_embedding = response["embeddings"][0]

    # Query ChromaDB
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    # Format results
    chunks = []
    for i in range(len(results["ids"][0])):
        chunks.append(
            {
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            }
        )

    return chunks


def build_prompt(question: str, chunks: list[dict]) -> str:
    """Build the context-augmented prompt for the LLM."""
    context_parts = []

    for i, chunk in enumerate(chunks, 1):
        meta = chunk["metadata"]
        source_info = f"[Source: {meta.get('title', 'Unknown')}]"
        if meta.get("source_url"):
            source_info += f" ({meta['source_url']})"

        context_parts.append(f"--- Document {i} {source_info} ---\n{chunk['text']}")

    context = "\n\n".join(context_parts)

    return f"""Context from the knowledge base:

{context}

---

Question: {question}"""


def generate_answer(question: str, chunks: list[dict]) -> str:
    """Send the augmented prompt to Ollama and return the response."""
    user_prompt = build_prompt(question, chunks)

    response = ollama.chat(
        model=Config.OLLAMA_CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    return response["message"]["content"]


def ask(question: str, n_results: int = 5, verbose: bool = False) -> str:
    """Full RAG pipeline: retrieve → generate."""
    # Retrieve relevant chunks
    chunks = retrieve(question, n_results=n_results)

    if verbose:
        print(f"\n  Retrieved {len(chunks)} chunks:")
        for i, chunk in enumerate(chunks, 1):
            meta = chunk["metadata"]
            print(
                f"    {i}. {meta.get('title', '?')} (distance: {chunk['distance']:.4f})"
            )
        print()

    # Generate answer
    answer = generate_answer(question, chunks)
    return answer


def interactive_loop():
    """Run an interactive chat loop."""
    print("=" * 60)
    print("RAG POC — Interactive Query")
    print("=" * 60)
    print(f"  Chat model: {Config.OLLAMA_CHAT_MODEL}")
    print(f"  Embed model: {Config.OLLAMA_EMBED_MODEL}")
    print()
    print("Type your question (or 'quit' to exit):")
    print()

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break

        print("\nSearching knowledge base...")
        answer = ask(question, verbose=True)
        print(f"\nAssistant: {answer}\n")
        print("-" * 40)
        print()


def main():
    parser = argparse.ArgumentParser(description="Query the RAG knowledge base")
    parser.add_argument("question", nargs="?", help="Question to ask")
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Run in interactive chat mode",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show retrieved chunks and distances",
    )
    parser.add_argument(
        "--results",
        "-n",
        type=int,
        default=5,
        help="Number of chunks to retrieve (default: 5)",
    )
    args = parser.parse_args()

    if args.interactive:
        interactive_loop()
    elif args.question:
        answer = ask(args.question, n_results=args.results, verbose=args.verbose)
        print(answer)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
