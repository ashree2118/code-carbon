from fastapi import HTTPException, UploadFile

from app.config import settings


def read_python_upload(file: UploadFile) -> str:
    """Read and validate an uploaded .py file. Returns its source text."""
    if not file.filename or not file.filename.lower().endswith(".py"):
        raise HTTPException(status_code=400, detail="Only .py files are allowed")

    # Read one byte past the limit so large uploads are never fully loaded.
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_upload_bytes} byte limit",
        )
    if not content.strip():
        raise HTTPException(status_code=400, detail="The uploaded file is empty")

    try:
        source = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="The file must be UTF-8 text")
    if "\x00" in source:
        raise HTTPException(status_code=400, detail="The file contains null bytes")
    return source
