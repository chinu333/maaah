"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    """Central configuration – every value comes from .env or defaults."""

    # --- Azure OpenAI ---
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_chat_deployment: str = "gpt-4o"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"

    # --- Azure AI Search ---
    azure_search_endpoint: str = ""
    azure_search_index_name: str = "maaah-rag-index"

    # --- RAG ---
    rag_chunk_size: int = 1000
    rag_chunk_overlap: int = 200

    # --- NASA ---
    nasa_api_key: str = "DEMO_KEY"
    nasa_api_url: str = "https://api.nasa.gov"

    # --- Azure Maps (Weather agent) ---
    azure_maps_subscription_key: str = ""
    azure_maps_client_id: str = ""

    # --- TomTom (Traffic agent) ---
    tomtom_maps_api_key: str = ""

    # --- LangSmith ---
    langsmith_api_key: str = ""
    langchain_tracing_v2: bool = True
    langchain_project: str = "maaah"

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    request_timeout: int = 120

    # --- Data ---
    data_dir: str = str(DATA_DIR)
    max_upload_size_mb: int = 50

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()


def ensure_data_dir() -> Path:
    """Create the data directory if it does not exist and return its path."""
    path = Path(get_settings().data_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path
