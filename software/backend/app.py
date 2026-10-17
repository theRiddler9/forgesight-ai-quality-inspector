"""Local read-only REST API for inspection history and edge telemetry."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID

import psutil
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from software.backend.config import BackendSettings
from software.backend.database import AuditStore
from software.backend.websocket import WebSocketHub
from software.common.schemas import InspectionDecision, InspectionResult
from software.inspection.replay import ReplayError
from software.inspection.service import ReplayService

_MIB = 1024 * 1024
log = logging.getLogger(__name__)
_LOCAL_HMI_ORIGIN = "http://localhost:5173"
_LOCAL_ORIGINS = {_LOCAL_HMI_ORIGIN, "http://127.0.0.1:5173"}
_LOOPBACK_CLIENTS = {"127.0.0.1", "::1", "testclient"}


class ReplayRequest(BaseModel):
    scenario: str = Field(min_length=1, max_length=80)
    event_id: UUID | None = None


class ReplayResponse(BaseModel):
    event: dict
    inserted: bool


class ReviewRequest(BaseModel):
    reviewer_id: str = Field(min_length=1, max_length=80)
    corrected_result: InspectionDecision
    note: str = Field(min_length=1, max_length=1000)


def _require_local_client(request: Request) -> None:
    if request.client is None or request.client.host not in _LOOPBACK_CLIENTS:
        raise HTTPException(status_code=403, detail="local operator access only")


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
    app.state.replay_service = ReplayService(app.state.audit_store, settings.fixture_dir)
    app.state.started_at = time.monotonic()
    yield


def create_app(db_path: str | Path | None = None, fixture_dir: str | Path | None = None) -> FastAPI:
    settings = BackendSettings.from_environment()
    if db_path is not None or fixture_dir is not None:
        settings = BackendSettings(
            db_path=Path(db_path) if db_path is not None else settings.db_path,
            host=settings.host, port=settings.port,
            fixture_dir=Path(fixture_dir) if fixture_dir is not None else settings.fixture_dir,
        )
    app = FastAPI(title="ForgeSight Local Backend", lifespan=_lifespan)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(_LOCAL_ORIGINS),
        allow_methods=["GET", "POST"],
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
        if socket.client is None or socket.client.host not in _LOOPBACK_CLIENTS or socket.headers.get("origin") not in (*_LOCAL_ORIGINS, None):
            await socket.close(code=1008)
            return
        hub: WebSocketHub = socket.app.state.websocket_hub
        await hub.connect(socket)
        try:
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            await hub.disconnect(socket, close=False)

    @app.websocket("/ws/inspections")
    async def inspection_events(socket: WebSocket) -> None:
        await live_events(socket)

    @app.get("/api/v1/health")
    async def inspection_health(request: Request) -> dict:
        service: ReplayService = request.app.state.replay_service
        state = service.gpio.state
        return {
            "status": "ok", "frame_source": "synthetic recorded replay",
            "detector": "scenario-driven simulation", "io": "mock",
            "mock_io_state": vars(state),
        }

    @app.get("/api/v1/scenarios")
    async def scenarios(request: Request) -> list[str]:
        return request.app.state.replay_service.catalog.names()

    @app.get("/api/v1/fixtures/{scenario_name}")
    async def fixture_preview(request: Request, scenario_name: str):
        service: ReplayService = request.app.state.replay_service
        try:
            scenario = service.catalog.get(scenario_name)
        except ReplayError as exc:
            raise HTTPException(status_code=404, detail=exc.code) from exc
        if scenario.image_name is None:
            raise HTTPException(status_code=404, detail="scenario has no image")
        path = service.catalog.fixture_dir / "images" / scenario.image_name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="fixture unavailable")
        return FileResponse(path, media_type="image/png")

    @app.post("/api/v1/inspections/replay", response_model=ReplayResponse)
    async def replay_inspection(request: Request, payload: ReplayRequest) -> ReplayResponse:
        _require_local_client(request)
        service: ReplayService = request.app.state.replay_service
        try:
            event, inserted = await asyncio.to_thread(
                service.inspect, payload.scenario,
                str(payload.event_id) if payload.event_id else None,
            )
        except ReplayError as exc:
            raise HTTPException(status_code=404, detail=exc.code) from exc
        except (sqlite3.Error, OSError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail="inspection or audit unavailable") from exc
        if inserted:
            try:
                request.app.state.websocket_hub.publish({"event": "inspection_event", "data": event})
            except Exception:
                # The committed record remains authoritative; REST history repairs missed live updates.
                log.exception("inspection committed but live event publication failed: %s", event["event_id"])
        return ReplayResponse(event=event, inserted=inserted)

    @app.get("/api/v1/inspections")
    async def canonical_history(
        request: Request, result: InspectionDecision | None = None,
        limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0),
    ) -> dict:
        try:
            items, total = await asyncio.to_thread(
                request.app.state.audit_store.canonical_history,
                result.value if result else None, limit, offset,
            )
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503, detail="audit database unavailable") from exc
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @app.get("/api/v1/metrics/summary")
    async def metrics_summary(request: Request) -> dict:
        try:
            return await asyncio.to_thread(request.app.state.audit_store.canonical_metrics)
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503, detail="audit database unavailable") from exc

    @app.get("/api/v1/inspections/{event_id}")
    async def canonical_detail(request: Request, event_id: UUID) -> dict:
        event = await asyncio.to_thread(
            request.app.state.audit_store.canonical_inspection, str(event_id)
        )
        if event is None:
            raise HTTPException(status_code=404, detail="inspection not found")
        return event

    @app.get("/api/v1/inspections/{event_id}/reviews")
    async def reviews(request: Request, event_id: UUID) -> list[dict]:
        return await asyncio.to_thread(request.app.state.audit_store.review_history, str(event_id))

    @app.post("/api/v1/inspections/{event_id}/review")
    async def review(request: Request, event_id: UUID, payload: ReviewRequest) -> dict:
        _require_local_client(request)
        try:
            return await asyncio.to_thread(
                request.app.state.audit_store.append_review,
                str(event_id), payload.reviewer_id, payload.corrected_result.value, payload.note,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="inspection not found") from exc
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503, detail="audit database unavailable") from exc

    return app


app = create_app()
