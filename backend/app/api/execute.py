from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings
from app.schemas import ExecuteResponse
from app.services.measurement_service import measure_script_execution

router = APIRouter()


def _validate_python_file(filename: str | None, content: bytes) -> None:
    if not filename or not filename.lower().endswith(".py"):
        raise HTTPException(status_code=400, detail="Only .py files are allowed")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_upload_bytes} byte limit",
        )


@router.post("/execute", response_model=ExecuteResponse)
async def execute_python(file: UploadFile = File(...)) -> ExecuteResponse:
    content = await file.read()
    _validate_python_file(file.filename, content)

    result, carbon = measure_script_execution(content, settings.execution_timeout_seconds)
    return ExecuteResponse(
        success=result.success,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        execution_time_seconds=result.execution_time_seconds,
        timed_out=result.timed_out,
        carbon=carbon,
    )

