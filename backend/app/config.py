import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BACKEND_DIR / ".env")


def _resolve_dir(value: str) -> str:
    """Relative paths are relative to backend/. Empty stays empty."""
    if not value.strip():
        return ""
    path = Path(value)
    return str(path if path.is_absolute() else BACKEND_DIR / path)


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
    # docker: every script runs in a fresh locked-down container (recommended,
    # uploaded code is untrusted). subprocess: a plain child process on the host,
    # which is process isolation only, not a security sandbox.
    execution_sandbox: str = os.getenv("EXECUTION_SANDBOX", "docker")
    docker_image: str = os.getenv("DOCKER_IMAGE", "python:3.12-slim")
    docker_memory: str = os.getenv("DOCKER_MEMORY", "512m")
    docker_cpus: float = float(os.getenv("DOCKER_CPUS", "1"))
    docker_start_timeout_seconds: float = float(os.getenv("DOCKER_START_TIMEOUT_SECONDS", "60"))

    # Carbon measurement. The offline tracker uses the grid carbon intensity of
    # this country (ISO 3166-1 alpha-3) instead of looking up the location over
    # the network, which would otherwise be counted as program run time.
    codecarbon_country_iso_code: str = os.getenv("CODECARBON_COUNTRY_ISO_CODE", "IND")
    # CodeCarbon's default is 15 s, longer than the execution timeout, so a run
    # would get no power readings between its start and end.
    codecarbon_measure_power_secs: float = float(os.getenv("CODECARBON_MEASURE_POWER_SECS", "1"))
    comparison_runs: int = int(os.getenv("COMPARISON_RUNS", "3"))

    # RAG
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "3"))
    # auto: vector search, falling back to keyword (BM25) search if the
    # embedding model or vector store cannot load. vector | keyword: force one.
    rag_backend: str = os.getenv("RAG_BACKEND", "auto")
    rag_embedding_model: str = os.getenv(
        "RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    # ChromaDB directory. Empty means an in-memory store rebuilt on each start.
    rag_persist_dir: str = _resolve_dir(os.getenv("RAG_PERSIST_DIR", ".chroma"))
    # Vector hits below this cosine similarity are not returned.
    rag_min_relevance: float = float(os.getenv("RAG_MIN_RELEVANCE", "0.2"))

    # LLM (Groq). The model must support strict JSON schema output.
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
    llm_effort: str = os.getenv("LLM_EFFORT", "high")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "300"))


settings = Settings()
