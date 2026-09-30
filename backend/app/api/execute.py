from fastapi import APIRouter, File, UploadFile

from app.api.uploads import read_python_upload
from app.config import settings
from app.schemas import ExecuteResponse
from app.services.measurement_service import measure_script_execution

router = APIRouter()


# A plain `def` route runs in FastAPI's thread pool, so a running script does
# not block other requests.
@router.post("/execute", response_model=ExecuteResponse)
def execute_python(file: UploadFile = File(...)) -> ExecuteResponse:
    source = read_python_upload(file)
    measured = measure_script_execution(source.encode("utf-8"), settings.execution_timeout_seconds)
    return measured.to_response()
