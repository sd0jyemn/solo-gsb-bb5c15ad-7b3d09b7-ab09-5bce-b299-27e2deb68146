"""请求 / 响应 Pydantic 模型。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# 小于该阈值的 epoch 数字视为秒，否则视为毫秒（约公元 5138 年分界）
EPOCH_MS_CUTOFF = 1e11


def parse_time(value: Any) -> datetime:
    """时间字段：支持 ISO 8601 字符串、epoch 秒 / 毫秒数字。

    不带时区的 ISO 时间按 UTC 处理；输出统一为 UTC。
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value) / 1000.0 if value >= EPOCH_MS_CUTOFF else float(value)
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"无法解析时间: {value!r}") from exc
    else:
        raise ValueError(f"不支持的时间类型: {type(value).__name__}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class TrackPoint(BaseModel):
    lon: float = Field(..., ge=-180, le=180, description="经度（WGS84）")
    lat: float = Field(..., ge=-90, le=90, description="纬度（WGS84）")
    time: datetime = Field(
        ..., description="时间戳：ISO 8601 字符串或 epoch（秒/毫秒）"
    )

    @field_validator("time", mode="before")
    @classmethod
    def _parse_time(cls, v: Any) -> datetime:
        return parse_time(v)


class AnalyzeRequest(BaseModel):
    points: list[TrackPoint] = Field(..., min_length=2, description="按时间升序排列的轨迹点")
    distance_threshold_m: float = Field(
        100.0, ge=0, alias="distance_threshold_m", description="停留合并距离阈值（米）"
    )
    min_stay_seconds: float = Field(
        300.0, ge=0, description="最短停留时长阈值（秒）"
    )
    gap_seconds: float = Field(
        300.0,
        ge=0,
        description="采样间断阈值（秒）：相邻点时间间隔超过它即记为一次间断",
    )
    sort_points: bool = Field(
        False, description="为 true 时服务端先按时间排序再分析"
    )

    model_config = {"populate_by_name": True}


class GapInfo(BaseModel):
    from_index: int
    to_index: int
    segment_type: Literal["stay", "move", "between"]
    boundary: bool
    start_time: datetime
    end_time: datetime
    duration_s: float
    distance_m: float
    from_coords: list[float]
    to_coords: list[float]


class StaySegment(BaseModel):
    type: Literal["stay"]
    seq: int
    start_index: int
    end_index: int
    enter_time: datetime
    leave_time: datetime
    duration_s: float
    point_count: int
    distance_m: float
    center: dict[str, float]
    radius_m: float
    enter_coords: list[float]
    leave_coords: list[float]
    gaps: list[GapInfo]


class MoveSegment(BaseModel):
    type: Literal["move"]
    seq: int
    start_index: int
    end_index: int
    enter_time: datetime
    leave_time: datetime
    duration_s: float
    point_count: int
    distance_m: float
    gaps: list[GapInfo]


class Summary(BaseModel):
    point_count: int
    total_distance_m: float
    total_duration_s: float
    moving_distance_m: float
    stay_distance_m: float
    stay_count: int
    total_stay_seconds: float
    gap_count: int
    total_gap_seconds: float
    in_stay_gap_seconds: float
    max_gap_seconds: float
    distance_threshold_m: float
    min_stay_seconds: float
    gap_seconds: float
    input_was_sorted: bool


class AnalyzeResponse(BaseModel):
    summary: Summary
    stays: list[StaySegment]
    moves: list[MoveSegment]
    gaps: list[GapInfo]


class HealthResponse(BaseModel):
    status: str
