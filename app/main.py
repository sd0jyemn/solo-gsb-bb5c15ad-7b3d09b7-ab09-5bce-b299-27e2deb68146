"""FastAPI 入口：轨迹停留分析服务。"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from .analyzer import analyze_track
from .geo import Point
from .geojson import to_geojson
from .schemas import AnalyzeRequest, AnalyzeResponse, HealthResponse

app = FastAPI(
    title="轨迹停留分析 API",
    description=(
        "提交带时间戳、经纬度的有序轨迹，服务按 Haversine 距离流式合并连续点，"
        "识别停留区段（进入 / 离开 / 跨采样间断），并提供 GeoJSON 与里程、停留统计。"
    ),
    version="1.0.0",
)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """业务参数错误（如轨迹未按时间升序）统一返回 400。"""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _to_points(req: AnalyzeRequest) -> list[Point]:
    ordered = sorted(req.points, key=lambda p: p.time) if req.sort_points else req.points
    return [Point(lon=p.lon, lat=p.lat, ts=p.time.timestamp()) for p in ordered]


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post(
    "/api/v1/analyze",
    response_model=AnalyzeResponse,
    tags=["analyze"],
    summary="停留分析（JSON）",
)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    points = _to_points(req)
    result = analyze_track(
        points,
        distance_threshold_m=req.distance_threshold_m,
        min_stay_seconds=req.min_stay_seconds,
        gap_seconds=req.gap_seconds,
        sorted_input=not req.sort_points,
    )
    return AnalyzeResponse.model_validate(result)


@app.post(
    "/api/v1/analyze.geojson",
    tags=["analyze"],
    summary="停留分析（GeoJSON FeatureCollection）",
)
def analyze_geojson(req: AnalyzeRequest) -> JSONResponse:
    points = _to_points(req)
    result = analyze_track(
        points,
        distance_threshold_m=req.distance_threshold_m,
        min_stay_seconds=req.min_stay_seconds,
        gap_seconds=req.gap_seconds,
        sorted_input=not req.sort_points,
    )
    return JSONResponse(
        content=jsonable_encoder(to_geojson(points, result)),
        media_type="application/geo+json",
    )
