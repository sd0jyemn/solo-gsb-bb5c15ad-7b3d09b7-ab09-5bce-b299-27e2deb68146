import math

from app.geo import centroid, haversine_m, radius_m
from app.geo import Point


def test_haversine_known_distance():
    # 赤道上经度 1 度约为 111.195 km（使用平均地球半径）
    d = haversine_m(0, 0, 1, 0)
    assert math.isclose(d, 111_194.9, rel_tol=1e-3)


def test_haversine_zero():
    assert haversine_m(116.4, 39.9, 116.4, 39.9) == 0.0


def test_haversine_symmetric():
    d1 = haversine_m(116.39, 39.90, 116.41, 39.92)
    d2 = haversine_m(116.41, 39.92, 116.39, 39.90)
    assert math.isclose(d1, d2, rel_tol=1e-12)


def test_centroid_and_radius():
    pts = [
        Point(0.0, 0.0, 0.0),
        Point(0.002, 0.0, 10.0),
        Point(0.0, 0.002, 20.0),
    ]
    lon, lat = centroid(pts)
    assert math.isclose(lon, 0.002 / 3)
    assert math.isclose(lat, 0.002 / 3)
    assert radius_m(pts, lon, lat) > 0
