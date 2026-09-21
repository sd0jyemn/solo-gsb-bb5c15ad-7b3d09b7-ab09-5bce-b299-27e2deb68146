import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import parse_time

client = TestClient(app)


PAYLOAD = {
    "distance_threshold_m": 100.0,
    "min_stay_seconds": 300,
    "gap_seconds": 300,
    "points": [
        {"lon": 116.391, "lat": 39.907, "time": "2026-09-21T08:00:00Z"},
        {"lon": 116.3912, "lat": 39.9071, "time": "2026-09-21T08:05:00Z"},
        {"lon": 116.391, "lat": 39.907, "time": "2026-09-21T08:30:00Z"},
        {"lon": 116.3960, "lat": 39.9120, "time": "2026-09-21T08:45:00Z"},
        {"lon": 116.402, "lat": 39.918, "time": "2026-09-21T09:00:00Z"},
        {"lon": 116.4022, "lat": 39.9181, "time": "2026-09-21T09:05:00Z"},
        {"lon": 116.4018, "lat": 39.9179, "time": "2026-09-21T09:10:00Z"},
    ],
}


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_analyze_json():
    resp = client.post("/api/v1/analyze", json=PAYLOAD)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["summary"]["stay_count"] == 2
    assert data["stays"][0]["duration_s"] == 1800
    # 时间统一输出为 UTC ISO 字符串（Pydantic 以 Z 结尾）
    assert data["stays"][0]["enter_time"].endswith("Z")
    # 08:05 -> 08:30 为停留区内的一次跨采样间断（1500s）
    assert len(data["stays"][0]["gaps"]) == 1
    assert data["stays"][0]["gaps"][0]["duration_s"] == 1500


def test_analyze_geojson():
    resp = client.post("/api/v1/analyze.geojson", json=PAYLOAD)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/geo+json"
    gj = resp.json()
    assert gj["type"] == "FeatureCollection"
    kinds = {f["properties"]["geometry_kind"] for f in gj["features"]}
    assert {"stay_center", "stay_extent", "move", "enter", "leave"} <= kinds


def test_epoch_seconds_and_millis():
    p1 = {"lon": 116.391, "lat": 39.907, "time": 1789999200}        # 秒
    p2 = {"lon": 116.391, "lat": 39.907, "time": 1789999200000}     # 毫秒
    assert parse_time(p1["time"]) == parse_time(p2["time"])


def test_validation_bad_coords():
    payload = {
        "points": [
            {"lon": 200, "lat": 39.9, "time": "2026-09-21T08:00:00Z"},
            {"lon": 116.4, "lat": 39.9, "time": "2026-09-21T08:05:00Z"},
        ]
    }
    resp = client.post("/api/v1/analyze", json=payload)
    assert resp.status_code == 422


def test_validation_bad_time_order():
    payload = {
        "points": [
            {"lon": 116.4, "lat": 39.9, "time": "2026-09-21T09:00:00Z"},
            {"lon": 116.4, "lat": 39.9, "time": "2026-09-21T08:00:00Z"},
        ]
    }
    resp = client.post("/api/v1/analyze", json=payload)
    assert resp.status_code == 400
    assert "升序" in resp.json()["detail"]


def test_sort_points_flag():
    payload = {
        "sort_points": True,
        "points": [
            {"lon": 116.402, "lat": 39.918, "time": "2026-09-21T09:00:00Z"},
            {"lon": 116.391, "lat": 39.907, "time": "2026-09-21T08:00:00Z"},
            {"lon": 116.391, "lat": 39.907, "time": "2026-09-21T08:05:00Z"},
        ],
    }
    resp = client.post("/api/v1/analyze", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["summary"]["input_was_sorted"] is False
    assert data["stays"][0]["enter_time"].startswith("2026-09-21T08:00:00")


def test_openapi_available():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/api/v1/analyze" in resp.json()["paths"]
