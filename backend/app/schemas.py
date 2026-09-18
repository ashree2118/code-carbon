from pydantic import BaseModel


class ExecuteResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int | None
    execution_time_seconds: float
    timed_out: bool = False
