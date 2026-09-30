import os

from dotenv import load_dotenv

load_dotenv()


def _parse_origins(value: str) -> list[str]:
    return [origin.strip() for origin in value.split(",") if origin.strip()]


class Settings:
    api_title: str = "Carbon Footprint Optimizer API"
    api_version: str = "0.1.0"
    cors_origins: list[str] = _parse_origins(
        os.getenv("CORS_ORIGINS", "http://localhost:3000")
    )
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(1 * 1024 * 1024)))
    execution_timeout_seconds: float = float(
        os.getenv("EXECUTION_TIMEOUT_SECONDS", "5")
    )
    chroma_db_dir: str = os.getenv("CHROMA_DB_DIR", "./chroma_db")
    embedding_model_name: str = os.getenv(
        "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
    )
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "3"))


settings = Settings()

