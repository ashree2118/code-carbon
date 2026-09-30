from fastapi import APIRouter

from app.config import settings
from app.schemas import RAGSearchRequest, RAGSearchResponse
from app.services.rag_service import rag_service

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/search", response_model=RAGSearchResponse)
async def search_rag(payload: RAGSearchRequest) -> RAGSearchResponse:
    top_k = payload.top_k if payload.top_k > 0 else settings.rag_top_k
    results = rag_service.search_practices(payload.query, top_k=top_k)
    return RAGSearchResponse(query=payload.query, results=results)
