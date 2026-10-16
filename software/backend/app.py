"""Local read-only REST API for inspection history and edge telemetry."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import psutil
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from software.backend.config import BackendSettings
from software.backend.database import AuditStore
from software.backend.websocket import WebSocketHub
from software.common.schemas import InspectionDecision, InspectionResult

_MIB = 1024 * 1024
_LOCAL_HMI_ORIGIN = "http://localhost:5173"


class HealthResponse(BaseModel):
    status: Literal["ok"]
    uptime_seconds: float = Field(ge=0)


class InspectionHistoryResponse(BaseModel):
    items: list[InspectionResult]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)


class SystemStatusResponse(BaseModel):
    soc_temp_c: float | None
    soc_temp_timestamp: datetime | None
    ram_used_mb: float = Field(ge=0)
    ram_total_mb: float = Field(gt=0)
    fps: float = Field(ge=0)
    avg_latency_ms: float | None = Field(default=None, ge=0)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings: BackendSettings = app.state.settings
    app.state.audit_store = await asyncio.to_thread(AuditStore, settings.db_path)
    app.state.websocket_hub = WebSocketHub()
    app.state.started_at = time.monotonic()
    yield


def create_app(db_path: str | Path | None = None) -> FastAPI:
    settings = BackendSettings.from_environment()
    if db_path is not None:
        settings = BackendSettings(db_path=Path(db_path), host=settings.host, port=settings.port)
    app = FastAPI(title="ForgeSight Local Backend", lifespan=_lifespan)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[_LOCAL_HMI_ORIGIN],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        uptime = time.monotonic() - request.app.state.started_at
        return HealthResponse(status="ok", uptime_seconds=uptime)

    @app.get(
        "/api/v1/inspections/latest", response_model=InspectionResult | None
    )
    async def latest_inspection(request: Request) -> InspectionResult | None:
        try:
            return await asyncio.to_thread(request.app.state.audit_store.latest_inspection)
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503, detail="audit database unavailable") from exc

    @app.get("/api/v1/inspections/history", response_model=InspectionHistoryResponse)
    async def inspection_history(
        request: Request,
        result: InspectionDecision | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> InspectionHistoryResponse:
        try:
            items, total = await asyncio.to_thread(
                request.app.state.audit_store.inspection_history,
                result,
                limit,
                offset,
            )
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503, detail="audit database unavailable") from exc
        return InspectionHistoryResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    @app.get("/api/v1/system/status", response_model=SystemStatusResponse)
    async def system_status(request: Request) -> SystemStatusResponse:
        now = datetime.now(timezone.utc)
        try:
            snapshot, memory = await asyncio.gather(
                asyncio.to_thread(request.app.state.audit_store.status_snapshot, now),
                asyncio.to_thread(psutil.virtual_memory),
            )
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503, detail="audit database unavailable") from exc
        except (psutil.Error, OSError) as exc:
            raise HTTPException(status_code=503, detail="system metrics unavailable") from exc
        soc_temp = snapshot["soc_temp_c"]
        soc_timestamp = snapshot["soc_temp_timestamp"]
        if soc_temp is None or soc_temp == -1.0:
            soc_temp = None
            soc_timestamp = None
        return SystemStatusResponse(
            soc_temp_c=soc_temp,
            soc_temp_timestamp=soc_timestamp,
            ram_used_mb=memory.used / _MIB,
            ram_total_mb=memory.total / _MIB,
            fps=snapshot["fps"],
            avg_latency_ms=snapshot["avg_latency_ms"],
        )

    @app.websocket("/ws/live")
    async def live_events(socket: WebSocket) -> None:
        hub: WebSocketHub = socket.app.state.websocket_hub
        await hub.connect(socket)
        try:
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            await hub.disconnect(socket, close=False)

    return app


app = create_app()
