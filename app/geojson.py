"""把分析结果转换为 GeoJSON FeatureCollection。"""
from __future__ import annotations

from typing import Any

from .geo import Point


def _seg_props(seg: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": seg["type"],
        "seq": seg["seq"],
        "start_index": seg["start_index"],
        "end_index": seg["end_index"],
        "enter_time": seg["enter_time"],
        "leave_time": seg["leave_time"],
        "duration_s": seg["duration_s"],
        "point_count": seg["point_count"],
        "distance_m": round(seg["distance_m"], 3),
        "gap_count": len(seg["gaps"]),
    }


def to_geojson(points: list[Point], result: dict[str, Any]) -> dict[str, Any]:
    """生成 FeatureCollection：

    - stay  ：停留中心点（Point，带半径 / 时长 / 进入离开）；
    - stay_extent / move：区段原始点范围（LineString）；
    - enter / leave：停留进入点与离开点（Point）；
    - gap   ：跨采样间断（虚线语义由 properties 标记，LineString）。
    """
    features: list[dict[str, Any]] = []

    def line(coords: list[list[float]], props: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": props,
        }

    def marker(coords: list[float], props: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coords},
            "properties": props,
        }

    ordered = sorted(
        result["stays"] + result["moves"], key=lambda s: s["start_index"]
    )
    for seg in ordered:
        coords = [p.as_coords() for p in points[seg["start_index"] : seg["end_index"] + 1]]
        geometry_type = "stay_extent" if seg["type"] == "stay" else "move"
        features.append(line(coords, {**_seg_props(seg), "geometry_kind": geometry_type}))

    for stay in result["stays"]:
        center = stay["center"]
        features.append(
            marker(
                [center["lon"], center["lat"]],
                {
                    "geometry_kind": "stay_center",
                    "seq": stay["seq"],
                    "type": "stay",
                    "start_index": stay["start_index"],
                    "end_index": stay["end_index"],
                    "enter_time": stay["enter_time"],
                    "leave_time": stay["leave_time"],
                    "duration_s": stay["duration_s"],
                    "radius_m": round(stay["radius_m"], 3),
                    "point_count": stay["point_count"],
                },
            )
        )
        features.append(
            marker(
                stay["enter_coords"],
                {
                    "geometry_kind": "enter",
                    "seq": stay["seq"],
                    "type": "stay",
                    "time": stay["enter_time"],
                    "point_index": stay["start_index"],
                },
            )
        )
        features.append(
            marker(
                stay["leave_coords"],
                {
                    "geometry_kind": "leave",
                    "seq": stay["seq"],
                    "type": "stay",
                    "time": stay["leave_time"],
                    "point_index": stay["end_index"],
                },
            )
        )

    for gap in result["gaps"]:
        features.append(
            line(
                [gap["from_coords"], gap["to_coords"]],
                {
                    "geometry_kind": "gap",
                    "segment_type": gap["segment_type"],
                    "boundary": gap["boundary"],
                    "start_time": gap["start_time"],
                    "end_time": gap["end_time"],
                    "duration_s": gap["duration_s"],
                    "distance_m": round(gap["distance_m"], 3),
                    "from_index": gap["from_index"],
                    "to_index": gap["to_index"],
                },
            )
        )

    return {"type": "FeatureCollection", "features": features}
