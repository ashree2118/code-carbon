from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.audit import router as audit_router
from app.api.execute import router as execute_router
from app.api.rag import router as rag_router
from app.api.routes import router
from app.config import settings
from app.services.llm_service import LLMNotConfiguredError

app = FastAPI(title=settings.api_title, version=settings.api_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(LLMNotConfiguredError)
def llm_not_configured(_: Request, exc: LLMNotConfiguredError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


app.include_router(router)
app.include_router(execute_router)
app.include_router(rag_router)
app.include_router(audit_router)
