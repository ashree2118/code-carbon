import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BACKEND_DIR / ".env")


def _parse_origins(value: str) -> list[str]:
    return [origin.strip() for origin in value.split(",") if origin.strip()]


class Settings:
    api_title: str = "Carbon Footprint Optimizer API"
    api_version: str = "0.2.0"
    cors_origins: list[str] = _parse_origins(
        os.getenv("CORS_ORIGINS", "http://localhost:3000")
    )

    # Execution
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(1 * 1024 * 1024)))
    execution_timeout_seconds: float = float(
        os.getenv("EXECUTION_TIMEOUT_SECONDS", "5")
    )
    max_output_bytes: int = int(os.getenv("MAX_OUTPUT_BYTES", str(256 * 1024)))

    # Carbon measurement. The offline tracker uses the grid carbon intensity of
    # this country (ISO 3166-1 alpha-3) instead of looking up the location over
    # the network, which would otherwise be counted as program run time.
    codecarbon_country_iso_code: str = os.getenv("CODECARBON_COUNTRY_ISO_CODE", "IND")
    comparison_runs: int = int(os.getenv("COMPARISON_RUNS", "3"))

    # RAG
    chroma_db_dir: str = os.getenv("CHROMA_DB_DIR", str(BACKEND_DIR / "chroma_db"))
    embedding_model_name: str = os.getenv(
        "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
    )
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "3"))

    # LLM
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "claude-opus-5-5")
    llm_effort: str = os.getenv("LLM_EFFORT", "high")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "300"))


settings = Settings()
