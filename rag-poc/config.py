"""Configuration for the RAG POC loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """RAG POC configuration."""

    # Knowledge base Git repo
    KB_GIT_REPO_URL: str = os.getenv("KB_GIT_REPO_URL", "")
    KB_GIT_BRANCH: str = os.getenv("KB_GIT_BRANCH", "master")
    KB_GIT_SSH_KEY: str = os.getenv("KB_GIT_SSH_KEY", "")
    KB_LOCAL_DIR: str = os.getenv("KB_LOCAL_DIR", "./knowledge-base")

    # Ollama
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_CHAT_MODEL: str = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b")
    OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    # ChromaDB
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    CHROMA_COLLECTION_NAME: str = os.getenv("CHROMA_COLLECTION_NAME", "knowledge_base")
