from fastapi import APIRouter, Depends, HTTPException

from app.schemas import RAGSearchRequest, RAGSearchResponse
from app.services.rag_service import GreenCodingRAGService, RAGUnavailableError, get_rag_service

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/search", response_model=RAGSearchResponse)
def search_rag(
    payload: RAGSearchRequest,
    rag: GreenCodingRAGService = Depends(get_rag_service),
) -> RAGSearchResponse:
    try:
        results = rag.search(payload.query, top_k=payload.top_k)
    except RAGUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return RAGSearchResponse(query=payload.query, results=results)
