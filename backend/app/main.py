from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.execute import router as execute_router
from app.api.routes import router
from app.config import settings

app = FastAPI(title=settings.api_title, version=settings.api_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(execute_router)
