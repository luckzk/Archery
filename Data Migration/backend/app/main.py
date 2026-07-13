from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .instances import router as instances_router
from .migration_tasks import router as migration_tasks_router
from .sql_editor import router as sql_editor_router
from .tasks import router as tasks_router

app = FastAPI(
    title="PostgreSQL Migration API",
    description="PostgreSQL 迁移控制台后端 MVP",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


app.include_router(instances_router)
app.include_router(tasks_router)
app.include_router(migration_tasks_router)
app.include_router(sql_editor_router)
