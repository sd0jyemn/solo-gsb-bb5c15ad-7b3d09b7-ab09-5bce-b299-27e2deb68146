"""地理计算：Haversine 距离与中心点。"""
from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_008.8  # 平均半径（米）


@dataclass(frozen=True, slots=True)
class Point:
    """内部使用的不可变轨迹点。"""

    lon: float
    lat: float
    ts: float

    def as_coords(self) -> list[float]:
        return [self.lon, self.lat]


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """两点之间的大圆距离（米），纬度按度规、经度按所在纬度圈修正。"""
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = lat2_r - lat1_r
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def centroid(points: list[Point]) -> tuple[float, float]:
    """等权中心点（经度、纬度）。

    适用于停留点这类跨度很小的集合；不做日期变更线/高纬度展开，
    输入请使用 WGS84 坐标，且尽量避免跨越 ±180° 经线。
    """
    if not points:
        raise ValueError("centroid requires at least one point")
    lon = sum(p.lon for p in points) / len(points)
    lat = sum(p.lat for p in points) / len(points)
    return lon, lat


def radius_m(points: list[Point], center_lon: float, center_lat: float) -> float:
    """各点到中心点的最大距离（米）。"""
    return max(haversine_m(center_lon, center_lat, p.lon, p.lat) for p in points)
