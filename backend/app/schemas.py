from pydantic import BaseModel


class CarbonMetrics(BaseModel):
    energy_kwh: float | None = None
    co2_kg: float | None = None


class ExecuteResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int | None
    execution_time_seconds: float
    timed_out: bool = False
    carbon: CarbonMetrics | None = None


class RAGSearchRequest(BaseModel):
    query: str
    top_k: int = 3


class PracticeResult(BaseModel):
    title: str
    content: str
    category: str
    relevance_score: float


class RAGSearchResponse(BaseModel):
    query: str
    results: list[PracticeResult]

