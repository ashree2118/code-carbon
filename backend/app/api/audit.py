from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.uploads import read_python_upload
from app.schemas import AnalyzeResponse, AuditResponse
from app.services.auditor import audit_code
from app.services.llm_service import LLMClient, LLMError, get_llm_client
from app.services.pipeline import run_analysis
from app.services.rag_service import GreenCodingRAGService, RAGUnavailableError, get_rag_service

router = APIRouter()


@router.post("/audit", response_model=AuditResponse)
def audit(
    file: UploadFile = File(...),
    llm: LLMClient = Depends(get_llm_client),
    rag: GreenCodingRAGService = Depends(get_rag_service),
) -> AuditResponse:
    """Static audit only. The uploaded code is not executed."""
    source = read_python_upload(file)
    try:
        return audit_code(source, llm, rag)
    except SyntaxError as exc:
        raise HTTPException(status_code=400, detail=f"Syntax error on line {exc.lineno}: {exc.msg}")
    except RAGUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(
    file: UploadFile = File(...),
    llm: LLMClient = Depends(get_llm_client),
    rag: GreenCodingRAGService = Depends(get_rag_service),
) -> AnalyzeResponse:
    """Full pipeline: measure, audit, optimize, verify, measure again, compare."""
    return run_analysis(read_python_upload(file), llm, rag)
