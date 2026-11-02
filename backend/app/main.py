import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.audit import router as audit_router
from app.api.execute import router as execute_router
from app.api.rag import router as rag_router
from app.api.routes import router
from app.config import settings
from app.services.docker_sandbox import SandboxUnavailableError
from app.services.llm_service import LLMNotConfiguredError
from app.services.rag_service import get_rag_service
from app.services.script_runner import prepare_sandbox

logger = logging.getLogger(__name__)


def _warm_up() -> None:
    """Load the embedding model and start the first sandbox container in the
    background, so the first request does not wait for them."""
    for name, step in (("RAG", lambda: get_rag_service().warm_up()), ("sandbox", prepare_sandbox)):
        try:
            step()
        except Exception as exc:
            logger.warning("%s warm-up failed (it will be retried on first use): %s", name, exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=_warm_up, name="warm-up", daemon=True).start()
    yield


app = FastAPI(title=settings.api_title, version=settings.api_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(LLMNotConfiguredError)
def llm_not_configured(_: Request, exc: LLMNotConfiguredError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(SandboxUnavailableError)
def sandbox_unavailable(_: Request, exc: SandboxUnavailableError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


app.include_router(router)
app.include_router(execute_router)
app.include_router(rag_router)
app.include_router(audit_router)
